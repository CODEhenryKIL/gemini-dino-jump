-- Run only after the policy-aware runtime is serving the canonical production URL.
-- Re-running this file never replenishes the 3,000-draw window.
begin;
set local lock_timeout = '5s';
set local statement_timeout = '15s';
select pg_advisory_xact_lock(hashtext('dino-prod-cutover'));
select pg_advisory_xact_lock(hashtextextended('draw-pool:gemini_dino_campus_2026',0));

do $activate$
declare
  cid constant text := 'gemini_dino_campus_2026';
  revision constant text := 'remaining-3000-20260930-v1';
  cfg dino_prod.campaign%rowtype;
  ceiling integer; remaining integer; prizes integer; candidate_count integer;
  total integer; total_prizes integer; before_fingerprint jsonb; after_fingerprint jsonb;
  policy jsonb;
begin
  select * into strict cfg from dino_prod.campaign where id=cid for update;
  if cfg.settings ? 'draw_pool_policy' then
    policy:=cfg.settings->'draw_pool_policy';
    if policy->>'version' is distinct from revision or cfg.probability_version<>revision
      or policy->'initial_remaining' is distinct from '3000'::jsonb
      or jsonb_typeof(policy->'active_slot_max') is distinct from 'number'
      or (policy->>'active_slot_max') !~ '^[0-9]+$'
      or policy->>'method' is distinct from 'UNIFORM_WITHOUT_REPLACEMENT'
      or policy->>'fallback' is distinct from 'BENEFIT_ONLY' then
      raise exception 'Existing policy is invalid or different; refusing to overwrite';
    end if;
    ceiling:=(policy->>'active_slot_max')::integer;
    select count(*) into remaining from dino_prod.draw_pool_slot
      where campaign_id=cid and allocated_draw_id is null and slot_number<=ceiling;
    if ceiling<1 or ceiling>5000 or remaining>3000
      or exists(select 1 from dino_prod.draw_pool_slot where campaign_id=cid
        and allocated_draw_id is null and outcome_kind='PRIZE' and slot_number>ceiling) then
      raise exception 'Existing active pool is invalid';
    end if;
    return;
  end if;
  if cfg.status <> 'ACTIVE' or cfg.is_test or not cfg.real_prizes_enabled
    or cfg.probability_version <> 'phase3-20260929-v6-preparation' then
    raise exception 'Unexpected production campaign state';
  end if;
  if not exists(select 1 from pg_trigger where tgrelid='dino_prod.draw'::regclass
      and tgname='draw_pool_policy_insert' and tgenabled='O')
    or not exists(select 1 from pg_trigger where tgrelid='dino_prod.draw_pool_slot'::regclass
      and tgname='draw_pool_policy_allocation' and tgenabled='O') then
    raise exception 'Policy protection triggers are not installed';
  end if;
  select count(*),count(*) filter(where outcome_kind='PRIZE'),
    count(*) filter(where allocated_draw_id is null),
    count(*) filter(where allocated_draw_id is null and outcome_kind='PRIZE')
    into total,total_prizes,remaining,prizes
    from dino_prod.draw_pool_slot where campaign_id=cid;
  if total<>5000 or total_prizes<>63 or remaining<3000 or prizes>3000 then
    raise exception 'Unexpected pool totals';
  end if;
  select slot_number into ceiling from dino_prod.draw_pool_slot
    where campaign_id=cid and allocated_draw_id is null
    order by slot_number offset 2999 limit 1;
  select count(*) into candidate_count from dino_prod.draw_pool_slot
    where campaign_id=cid and allocated_draw_id is null and slot_number<=ceiling;
  if candidate_count<>3000 or exists(select 1 from dino_prod.draw_pool_slot
      where campaign_id=cid and allocated_draw_id is null and outcome_kind='PRIZE' and slot_number>ceiling)
    or exists(select 1 from dino_prod.draw_pool_slot s
      left join dino_prod.inventory_item i on i.id=s.inventory_item_id
      where s.campaign_id=cid and s.allocated_draw_id is null and s.outcome_kind='PRIZE'
        and (i.id is null or i.status<>'AVAILABLE')) then
    raise exception 'Active pool does not contain exactly 3,000 slots and all available prizes';
  end if;
  select jsonb_build_object(
    'draws',(select md5(coalesce(string_agg(to_jsonb(d)::text,'' order by d.id),'')) from dino_prod.draw d where campaign_id=cid),
    'claims',(select md5(coalesce(string_agg(to_jsonb(c)::text,'' order by c.id),'')) from dino_prod.claim c where campaign_id=cid),
    'slots',(select md5(coalesce(string_agg(to_jsonb(s)::text,'' order by s.id),'')) from dino_prod.draw_pool_slot s where campaign_id=cid),
    'inventory',(select md5(coalesce(string_agg(to_jsonb(i)::text,'' order by i.id),'')) from dino_prod.inventory_item i join dino_prod.prize p on p.id=i.prize_id where p.campaign_id=cid),
    'credits',(select md5(coalesce(string_agg(to_jsonb(l)::text,'' order by l.id),'')) from dino_prod.draw_credit_ledger l where campaign_id=cid)
  ) into before_fingerprint;
  policy:=jsonb_build_object('version',revision,'active_slot_max',ceiling,
    'initial_remaining',3000,'initial_prizes',prizes,'initial_benefits',3000-prizes,
    'physical_remaining_before',remaining,'previous_probability_version',cfg.probability_version,
    'activated_at',clock_timestamp(),'method','UNIFORM_WITHOUT_REPLACEMENT',
    'fallback','BENEFIT_ONLY','preserved_state_fingerprint',before_fingerprint);
  update dino_prod.campaign set settings=settings||jsonb_build_object('draw_pool_policy',policy),
    probability_version=revision,version=version+1,updated_at=clock_timestamp() where id=cid;
  select jsonb_build_object(
    'draws',(select md5(coalesce(string_agg(to_jsonb(d)::text,'' order by d.id),'')) from dino_prod.draw d where campaign_id=cid),
    'claims',(select md5(coalesce(string_agg(to_jsonb(c)::text,'' order by c.id),'')) from dino_prod.claim c where campaign_id=cid),
    'slots',(select md5(coalesce(string_agg(to_jsonb(s)::text,'' order by s.id),'')) from dino_prod.draw_pool_slot s where campaign_id=cid),
    'inventory',(select md5(coalesce(string_agg(to_jsonb(i)::text,'' order by i.id),'')) from dino_prod.inventory_item i join dino_prod.prize p on p.id=i.prize_id where p.campaign_id=cid),
    'credits',(select md5(coalesce(string_agg(to_jsonb(l)::text,'' order by l.id),'')) from dino_prod.draw_credit_ledger l where campaign_id=cid)
  ) into after_fingerprint;
  if before_fingerprint is distinct from after_fingerprint then
    raise exception 'Existing draw, claim, slot, inventory or credit state changed';
  end if;
end
$activate$;

select clock_timestamp() at time zone 'Asia/Seoul' checked_at,
  c.probability_version,c.settings->'draw_pool_policy' policy,
  count(*) filter(where s.allocated_draw_id is null and s.slot_number<=(c.settings#>>'{draw_pool_policy,active_slot_max}')::int)::int active_remaining,
  count(*) filter(where s.allocated_draw_id is null and s.outcome_kind='PRIZE')::int remaining_prizes
from dino_prod.campaign c join dino_prod.draw_pool_slot s on s.campaign_id=c.id
where c.id='gemini_dino_campus_2026' group by c.id;
commit;
