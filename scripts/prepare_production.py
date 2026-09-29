"""Prepare a reviewed, isolated production schema and disabled campaign.

Default operation writes only a SQL artifact. No network connection is made.
Applying the artifact is a separate deployment operation. Existing beta objects,
rows, permissions, credentials, and active campaign are never changed.
"""
import argparse
import hashlib
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
LOCK = ROOT / 'config/production-schema-sources.json'
MANIFEST = ROOT / 'config/phase3-launch.json'
ARTIFACT = ROOT / 'server/production-launch-manifest.json'


def inventory_counts(manifest):
    try:
        pool_total = manifest['draw_pool']['total_slots']
        benefit_slots = manifest['draw_pool']['benefit_slots']
        draw_quantities = [row['quantity'] for row in manifest['draw_prizes']]
        ranking_quantities = [row['quantity'] for row in manifest['ranking_prizes']]
    except (KeyError, TypeError):
        raise ValueError('Invalid manifest inventory') from None
    if any(type(value) is not int or value <= 0 for value in [*draw_quantities, *ranking_quantities]):
        raise ValueError('Invalid manifest inventory')
    draw_prizes = sum(draw_quantities)
    ranking_prizes = sum(ranking_quantities)
    values = (pool_total, benefit_slots, draw_prizes, ranking_prizes)
    if any(type(value) is not int or value <= 0 for value in values) or pool_total != benefit_slots + draw_prizes:
        raise ValueError('Manifest inventory totals do not reconcile')
    return values


def source_migrations():
    entries = json.loads(LOCK.read_text())
    for entry in entries:
        path = ROOT / 'supabase/migrations' / entry['file']
        data = path.read_bytes()
        if hashlib.sha256(data).hexdigest() != entry['sha256']:
            raise ValueError(f'Review changed schema source before provisioning: {path.name}')
        yield path.name, data.decode()


def render_schema():
    manifest = json.loads(MANIFEST.read_text(encoding='utf-8'))
    pool_total, _benefit_slots, draw_prizes, ranking_prizes = inventory_counts(manifest)
    pieces = ["""begin;
select pg_advisory_xact_lock(hashtext('dino-prod-bootstrap'));
do $$ begin
  if exists(select 1 from pg_namespace where nspname='dino_prod') then
    raise exception 'Production schema already exists; refusing overwrite';
  end if;
  if exists(select 1 from pg_roles where rolname='dino_prod_app' and
    (rolsuper or rolcreatedb or rolcreaterole or rolinherit or rolbypassrls)) then
    raise exception 'Production application role has unexpected privileges';
  end if;
end $$;
"""]
    replacements = {
        "environment in ('local','test','preview')": "environment = 'production'",
        'synthetic_only boolean not null default true check (synthetic_only)': 'synthetic_only boolean not null default false check (not synthetic_only)',
        'synthetic boolean not null default true check (synthetic)': 'synthetic boolean not null default false check (not synthetic)',
        'synthetic boolean not null default true': 'synthetic boolean not null default false',
        'is_test boolean not null default true check (is_test)': 'is_test boolean not null default false check (not is_test)',
        'real_prizes_enabled boolean not null default false check (not real_prizes_enabled)': 'real_prizes_enabled boolean not null default false',
    }
    for name, source in source_migrations():
        # Only pinned repository migrations are templates. User SQL is never accepted.
        rendered = source.replace('dino_dev', 'dino_prod')
        rendered = re.sub(r'(?m)^(?:begin|commit);\s*$', '', rendered)
        for before, after in replacements.items():
            rendered = rendered.replace(before, after)
        if 'dino_dev' in rendered or re.search(r'check\s*\((?:synthetic|synthetic_only|is_test)\)', rendered):
            raise ValueError(f'Unconverted beta constraint in {name}')
        pieces.append(f'-- Reviewed source: {name}\n{rendered}\n')
    pieces.append(f"""
alter table dino_prod.environment_guard
  add column launch_manifest_sha256 text not null check (launch_manifest_sha256 ~ '^[0-9a-f]{{64}}$'),
  add column event_enabled boolean not null default false,
  add column campaign_opens_at timestamptz not null,
  add column campaign_closes_at timestamptz not null check (campaign_closes_at > campaign_opens_at),
  add column claim_closes_at timestamptz not null check (claim_closes_at > campaign_closes_at),
  add column draw_pool_total integer not null check (draw_pool_total={pool_total}),
  add column draw_prize_quantity integer not null check (draw_prize_quantity={draw_prizes}),
  add column ranking_prize_quantity integer not null check (ranking_prize_quantity={ranking_prizes}),
  add column unlimited_play boolean not null default false check(not unlimited_play),
  add column synthetic_inventory boolean not null default false check(not synthetic_inventory),
  add column shortened_clock boolean not null default false check(not shortened_clock);
-- No login, password, membership, or cross-schema grant is added by this script.
do $$ begin
  if exists(select 1 from pg_roles where rolname='dino_dev_app') then
    revoke all on schema dino_prod from dino_dev_app;
  end if;
end $$;
commit;
""")
    return '\n'.join(pieces)


def _same_json_value(left, right):
    if type(left) is not type(right):
        return False
    if isinstance(left, dict):
        return left.keys() == right.keys() and all(_same_json_value(left[key], right[key]) for key in left)
    if isinstance(left, list):
        return len(left) == len(right) and all(_same_json_value(a, b) for a, b in zip(left, right))
    return left == right


def provision(conn, manifest, digest, source_bytes):
    """Provision a fresh PAUSED real inventory; never activate or overwrite."""
    if __package__:
        from .phase3_preflight import validate
    else:
        from phase3_preflight import validate
    if not isinstance(source_bytes, bytes):
        raise ValueError('Invalid manifest source bytes')
    try:
        source_manifest = json.loads(source_bytes)
    except (TypeError, UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise ValueError('Invalid manifest source bytes') from exc
    if not _same_json_value(source_manifest, manifest) or not re.fullmatch(r'[0-9a-f]{64}', digest) or hashlib.sha256(source_bytes).hexdigest() != digest:
        raise ValueError('Manifest bytes and digest do not match the reviewed manifest')
    manifest = source_manifest
    result = validate(manifest)
    if not result['preparation_ready'] or manifest['event_enabled']:
        raise ValueError('A preparation-ready manifest with event_enabled=false is required')
    if not re.fullmatch(r'[a-z][a-z0-9_]{1,63}', manifest['campaign']['id']):
        raise ValueError('Invalid production campaign ID')
    pool_total, benefit_slots, draw_prize_quantity, ranking_prize_quantity = inventory_counts(manifest)
    conn.execute("select pg_advisory_xact_lock(hashtext('dino-prod-provision'))")
    mutable_tables = conn.execute("""select tablename from pg_tables
      where schemaname='dino_prod' and tablename<>'schema_version' order by tablename""").fetchall()
    for row in mutable_tables:
        table = row[0]
        quoted_table = table.replace('"', '""')
        if conn.execute(f'select count(*) from dino_prod."{quoted_table}"').fetchone()[0]:
            raise ValueError('Production area is not empty; refusing to overwrite')
    campaign = manifest['campaign']; cid = campaign['id']
    settings = {'initial_tickets': 1, 'invitation_balance_max': 3, 'invitation_cooldown_hours': 10,
                'draw_max_rounds': 10, 'phase3_manifest_hash': digest,
                'phase3_draw_prize_quantity': draw_prize_quantity,
                'claim_submission_cutoff': campaign['claim_closes_at'], 'ranking_finish_acceptance_cutoff': campaign['closes_at'], 'finish_after_close': 'RECEIVED_BEFORE_CLOSE',
                'ranking_finalization_approved': True, 'ranking_inventory_separate': manifest['ranking_prizes']}
    conn.execute("""insert into dino_prod.campaign(id,title,status,game_version,benefit_url,settings,probability_version,opens_at,closes_at,real_prizes_enabled)
      values(%s,'2026 캠퍼스 공룡 점프','PAUSED','2.1.0','https://VQyu3J.s.gy/Game',%s::jsonb,%s,%s,%s,true)""",
      (cid,json.dumps(settings),manifest['version'],campaign['opens_at'],campaign['closes_at']))
    slot = 0
    for prize in manifest['draw_prizes']:
        prize_id = cid + '_' + prize['id']
        conn.execute("insert into dino_prod.prize(id,campaign_id,name,category,image_url,probability) values(%s,%s,%s,%s,'/assets/icons/Picture-Light.png',%s)",
                     (prize_id,cid,prize['name'],prize['category'],prize['quantity']/pool_total))
        for number in range(1,prize['quantity']+1):
            slot += 1; item = f'{prize_id}_{number:03d}'
            conn.execute('insert into dino_prod.inventory_item(id,prize_id) values(%s,%s)',(item,prize_id))
            conn.execute("insert into dino_prod.inventory_history(inventory_item_id,to_status,reason,related_type,related_id) values(%s,'AVAILABLE','PRODUCTION_MANIFEST','manifest',%s)",(item,manifest['version']))
            conn.execute("insert into dino_prod.draw_pool_slot(campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id) values(%s,%s,'PRIZE',%s,%s)",(cid,slot,prize_id,item))
    conn.execute("insert into dino_prod.prize(id,campaign_id,name,category,image_url,probability) values(%s,%s,'Gemini 혜택','NO_PRIZE','/assets/icons/Picture-Light.png',%s)",(cid+'_benefit',cid,benefit_slots/pool_total))
    conn.execute("insert into dino_prod.draw_pool_slot(campaign_id,slot_number,outcome_kind) select %s,n,'BENEFIT' from generate_series(%s::integer,%s::integer)n",(cid,draw_prize_quantity+1,pool_total))
    for prize in manifest['ranking_prizes']:
        prize_id = f"{cid}_rank_{prize['rank']}"; item = prize_id+'_001'
        conn.execute("insert into dino_prod.prize(id,campaign_id,name,category,image_url,probability) values(%s,%s,%s,'COUPON','/assets/icons/Picture-Light.png',0)",(prize_id,cid,prize['name']))
        conn.execute('insert into dino_prod.inventory_item(id,prize_id) values(%s,%s)',(item,prize_id))
        conn.execute("insert into dino_prod.inventory_history(inventory_item_id,to_status,reason,related_type,related_id) values(%s,'AVAILABLE','PRODUCTION_RANKING_MANIFEST','manifest',%s)",(item,manifest['version']))
        conn.execute('insert into dino_prod.ranking_award(campaign_id,rank,prize_id,inventory_item_id) values(%s,%s,%s,%s)',(cid,prize['rank'],prize_id,item))
    counts = conn.execute("select count(*),count(*) filter(where outcome_kind='PRIZE') from dino_prod.draw_pool_slot where campaign_id=%s",(cid,)).fetchone()
    inventory = conn.execute('select count(*) from dino_prod.inventory_item').fetchone()[0]
    if tuple(counts)!=(pool_total,draw_prize_quantity) or inventory!=draw_prize_quantity+ranking_prize_quantity:
        raise ValueError('Production inventory reconciliation failed')
    conn.execute("""insert into dino_prod.environment_guard(environment,project_ref,schema_name,synthetic_only,test_seed,campaign_id,
      launch_manifest_sha256,event_enabled,campaign_opens_at,campaign_closes_at,claim_closes_at,draw_pool_total,draw_prize_quantity,ranking_prize_quantity)
      values('production','igfrnexknwtiljdqjrbp','dino_prod',false,false,%s,%s,false,%s,%s,%s,%s,%s,%s)""",
      (cid,digest,campaign['opens_at'],campaign['closes_at'],campaign['claim_closes_at'],pool_total,draw_prize_quantity,ranking_prize_quantity))
    return {'campaign_id':cid,'status':'PAUSED','event_enabled':False,'draw_slots':pool_total,'draw_prizes':draw_prize_quantity,'ranking_prizes':ranking_prize_quantity}


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--schema-output', type=Path, required=True)
    args=parser.parse_args()
    rendered=render_schema()
    args.schema_output.parent.mkdir(parents=True,exist_ok=True)
    args.schema_output.write_text(rendered)
    print(json.dumps({'schema_artifact':str(args.schema_output),'sha256':hashlib.sha256(rendered.encode()).hexdigest(),'applied':False}))


if __name__=='__main__':main()
