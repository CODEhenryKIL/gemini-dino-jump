"""Prepare one untouched provisional RANKING claim for bounded mobile QA.

This operator-only helper never creates a participant, changes a score, reserves
inventory, or edits an existing claim/contact. It can emit checked SQL for the
Supabase SQL connector when no maintenance DSN is available.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
from pathlib import Path
import re
import sys
import uuid

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
from beta_reset import connect

SCHEMA = "dino_dev"
PROJECT_REF = "igfrnexknwtiljdqjrbp"
PLAN_VERSION = 2
PLAN_MAX_AGE = dt.timedelta(minutes=30)
APPLY_CONFIRMATION = "PREPARE_SYNTHETIC_RANKING_CLAIM_QA"
CLEANUP_CONFIRMATION = "CLEANUP_SYNTHETIC_RANKING_CLAIM_QA"
LOCK_PREFIX = "claim-qa-ranking:"
RUNTIME_GAME_VERSION = "2.1.0"


class ClaimQaError(ValueError):
    pass


def _normalize(value):
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, dict):
        return {key: _normalize(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_normalize(item) for item in value]
    return value


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def _with_hash(value):
    result = dict(value)
    result["sha256"] = _digest(result)
    return result


def _verify_hash(value):
    if not isinstance(value, dict) or not re.fullmatch(r"[0-9a-f]{64}", str(value.get("sha256") or "")):
        raise ClaimQaError("CLAIM_QA_PLAN_INVALID")
    body = {key: item for key, item in value.items() if key != "sha256"}
    if _digest(body) != value["sha256"]:
        raise ClaimQaError("CLAIM_QA_PLAN_INVALID")


def _validate_scope(environment, participant_id):
    if environment not in {"test", "preview"} or not re.fullmatch(r"p_[A-Za-z0-9_-]{8,120}", participant_id or ""):
        raise ClaimQaError("CLAIM_QA_SCOPE_INVALID")


def _lit(value):
    return "'" + str(value).replace("'", "''") + "'"


def _snapshot_sql(environment, participant_id):
    _validate_scope(environment, participant_id)
    expected_project = "local" if environment == "test" else PROJECT_REF
    env, pid, project = map(_lit, (environment, participant_id, expected_project))
    return f"""with ranked as (
      select b.participant_id,b.session_id,b.score,b.achieved_at,s.valid_ticks,
        row_number() over(order by b.score desc,b.achieved_at asc,b.participant_id asc)::int rank,
        count(*) over()::int participant_count
      from {SCHEMA}.versioned_best_score b
      join {SCHEMA}.participant p on p.id=b.participant_id
      join {SCHEMA}.game_session s on s.id=b.session_id and s.participant_id=b.participant_id
        and s.campaign_id=p.campaign_id and s.version=b.game_version
      join {SCHEMA}.environment_guard g on g.singleton and g.campaign_id=p.campaign_id
      join {SCHEMA}.campaign c on c.id=g.campaign_id
      where p.status='ACTIVE' and b.game_version='{RUNTIME_GAME_VERSION}'
    ), state as (
      select jsonb_build_object(
        'maintenance_role_ok',coalesce((select rolsuper or rolbypassrls from pg_roles where rolname=current_user),false),
        'runtime_game_version','{RUNTIME_GAME_VERSION}',
        'guard',(select to_jsonb(g) - 'updated_at' from {SCHEMA}.environment_guard g where singleton),
        'campaign',(select jsonb_build_object('id',c.id,'status',c.status,'version',c.version,'game_version',c.game_version,
          'is_test',c.is_test,'real_prizes_enabled',c.real_prizes_enabled,'closes_at',c.closes_at,
          'claim_submission_cutoff',c.settings->>'claim_submission_cutoff')
          from {SCHEMA}.campaign c join {SCHEMA}.environment_guard g on g.campaign_id=c.id and g.singleton),
        'participant',(select jsonb_build_object('id',p.id,'campaign_id',p.campaign_id,'status',p.status,
          'environment',p.environment,'synthetic',p.synthetic) from {SCHEMA}.participant p where p.id={pid}),
        'ranking_contact',(select jsonb_build_object('participant_id',r.participant_id,'status',r.status,
          'game_version',r.game_version,'submitted_at',r.submitted_at) from {SCHEMA}.ranking_contact r where r.participant_id={pid}),
        'ranking',(select to_jsonb(r) from ranked r where r.participant_id={pid}),
        'ranking_claim_count',(select count(*)::int from {SCHEMA}.claim c where c.participant_id={pid} and c.claim_type='RANKING'),
        'draw_claims',coalesce((select jsonb_agg(jsonb_build_object('claim',
          jsonb_build_object('id',c.id,'claim_type',c.claim_type,'status',c.status,'version',c.version,
            'draw_id',c.draw_id,'prize_id',c.prize_id,'inventory_item_id',c.inventory_item_id,
            'contact_submitted_at',c.contact_submitted_at,'contacted_at',c.contacted_at,'paid_at',c.paid_at,
            'row_version',c.xmin::text),'contact',
          jsonb_build_object('present',cc.claim_id is not null,'row_version',cc.xmin::text,
            'synthetic',cc.synthetic,'created_at',cc.created_at,'consent_at',cc.consent_at,
            'consent_version',cc.consent_version)) order by c.id)
          from {SCHEMA}.claim c left join {SCHEMA}.claim_contact cc on cc.claim_id=c.id
          where c.participant_id={pid} and c.claim_type='DRAW'),'[]'::jsonb),
        'participant_draw_fingerprint',(select md5(coalesce(jsonb_agg(to_jsonb(d) order by d.id),'[]'::jsonb)::text)
          from {SCHEMA}.draw d where d.participant_id={pid}),
        'inventory_fingerprint',(select md5(coalesce(jsonb_agg(to_jsonb(i) order by i.id),'[]'::jsonb)::text)
          from {SCHEMA}.inventory_item i),
        'scope_expected',jsonb_build_object('environment',{env},'project_ref',{project},'schema_name','{SCHEMA}')
      ) snapshot
    ) select snapshot from state"""


def render_state_sql(environment, participant_id):
    return _snapshot_sql(environment, participant_id) + ";"


def _check_snapshot(state, environment, participant_id):
    _validate_scope(environment, participant_id)
    state = _normalize(state)
    expected_project = "local" if environment == "test" else PROJECT_REF
    guard, campaign, participant = state.get("guard"), state.get("campaign"), state.get("participant")
    contact, ranking = state.get("ranking_contact"), state.get("ranking")
    if state.get("maintenance_role_ok") is not True:
        raise ClaimQaError("CLAIM_QA_MAINTENANCE_ROLE_REQUIRED")
    if (not guard or guard.get("environment") != environment or guard.get("project_ref") != expected_project
            or guard.get("schema_name") != SCHEMA or guard.get("synthetic_only") is not True
            or guard.get("test_seed") is not True):
        raise ClaimQaError("CLAIM_QA_GUARD_MISMATCH")
    if (not campaign or campaign.get("id") != guard.get("campaign_id") or campaign.get("status") != "ACTIVE"
            or campaign.get("is_test") is not True or campaign.get("real_prizes_enabled") is not False):
        raise ClaimQaError("CLAIM_QA_CAMPAIGN_NOT_SYNTHETIC_ACTIVE")
    cutoff = campaign.get("claim_submission_cutoff")
    if campaign.get("closes_at") is not None or cutoff is not None:
        try:
            parsed_cutoff = dt.datetime.fromisoformat(cutoff.replace("Z", "+00:00"))
        except (AttributeError, ValueError) as exc:
            raise ClaimQaError("CLAIM_QA_CLAIM_DEADLINE_INVALID") from exc
        if parsed_cutoff.tzinfo is None or dt.datetime.now(dt.timezone.utc) >= parsed_cutoff:
            raise ClaimQaError("CLAIM_QA_CLAIM_SUBMISSION_CLOSED")
    if (not participant or participant.get("id") != participant_id or participant.get("campaign_id") != campaign.get("id")
            or participant.get("status") != "ACTIVE" or participant.get("environment") != environment
            or participant.get("synthetic") is not True):
        raise ClaimQaError("CLAIM_QA_PARTICIPANT_INVALID")
    if state.get("runtime_game_version") != RUNTIME_GAME_VERSION:
        raise ClaimQaError("CLAIM_QA_RUNTIME_VERSION_INVALID")
    if (not contact or contact.get("status") != "REQUESTED" or contact.get("submitted_at") is not None
            or contact.get("game_version") != RUNTIME_GAME_VERSION):
        raise ClaimQaError("CLAIM_QA_RANKING_CONTACT_INVALID")
    if (not ranking or ranking.get("rank") not in {1, 2, 3} or ranking.get("score") is None
            or ranking.get("session_id") is None):
        raise ClaimQaError("CLAIM_QA_TOP3_REQUIRED")
    if state.get("ranking_claim_count") != 0:
        raise ClaimQaError("CLAIM_QA_RANKING_CLAIM_EXISTS")
    return state


def snapshot(conn, environment, participant_id):
    row = conn.execute(_snapshot_sql(environment, participant_id)).fetchone()
    raw = row["snapshot"] if isinstance(row, dict) else row[0]
    return _check_snapshot(raw, environment, participant_id)


def plan_from_snapshot(raw, environment, participant_id):
    if isinstance(raw, str):
        raw = json.loads(raw)
    if isinstance(raw, dict) and set(raw) == {"snapshot"}:
        raw = raw["snapshot"]
    state = _check_snapshot(raw, environment, participant_id)
    return _with_hash({
        "plan_version": PLAN_VERSION,
        "created_at": dt.datetime.now(dt.timezone.utc).isoformat(),
        "environment": environment,
        "participant_id": participant_id,
        "database_state": state,
        "database_state_sha256": _digest(state),
        "fixture": {"claim_id": "claim_qa_rank_" + uuid.uuid4().hex, "claim_type": "RANKING"},
        "expected": {"new_claims": 1, "status": "AWAITING_INFORMATION", "inventory_changes": 0},
    })


def plan_fixture(conn, environment, participant_id):
    return plan_from_snapshot(snapshot(conn, environment, participant_id), environment, participant_id)


def _validate_plan(plan, *, check_age=True):
    _verify_hash(plan)
    if (plan.get("plan_version") != PLAN_VERSION or plan.get("database_state_sha256") != _digest(plan.get("database_state"))
            or plan.get("fixture", {}).get("claim_type") != "RANKING"
            or not re.fullmatch(r"claim_qa_rank_[0-9a-f]{32}", plan.get("fixture", {}).get("claim_id", ""))):
        raise ClaimQaError("CLAIM_QA_PLAN_INVALID")
    _check_snapshot(plan["database_state"], plan.get("environment"), plan.get("participant_id"))
    try:
        created = dt.datetime.fromisoformat(plan["created_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise ClaimQaError("CLAIM_QA_PLAN_INVALID") from exc
    now = dt.datetime.now(dt.timezone.utc)
    if created.tzinfo is None or created > now + dt.timedelta(minutes=2) or (check_age and now - created > PLAN_MAX_AGE):
        raise ClaimQaError("CLAIM_QA_PLAN_EXPIRED")


def _sql_json(value, tag="claimqa"):
    payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
    if f"${tag}$" in payload:
        raise ClaimQaError("CLAIM_QA_PLAN_INVALID")
    return f"${tag}${payload}${tag}$::jsonb"


def render_apply_sql(plan, confirmation):
    _validate_plan(plan)
    if confirmation != APPLY_CONFIRMATION:
        raise ClaimQaError("CLAIM_QA_CONFIRMATION_REQUIRED")
    participant = plan["participant_id"].replace("'", "''")
    claim_id = plan["fixture"]["claim_id"].replace("'", "''")
    created = plan["created_at"].replace("'", "''")
    query = _snapshot_sql(plan["environment"], plan["participant_id"])
    baseline = _sql_json(plan["database_state"], "baseline")
    cutoff = plan["database_state"]["campaign"].get("claim_submission_cutoff")
    deadline_sql = ""
    if cutoff is not None:
        deadline_sql = f"if clock_timestamp() >= {_lit(cutoff)}::timestamptz then raise exception 'CLAIM_QA_CLAIM_SUBMISSION_CLOSED'; end if;"
    return f"""begin;
set local statement_timeout='15s'; set local lock_timeout='3s';
do $claimqa$
declare v_actual jsonb; v_baseline jsonb := {baseline};
begin
  if clock_timestamp() > '{created}'::timestamptz + interval '30 minutes' then raise exception 'CLAIM_QA_PLAN_EXPIRED'; end if;
  {deadline_sql}
  perform pg_advisory_xact_lock(hashtext('{LOCK_PREFIX}{participant}'));
  perform 1 from {SCHEMA}.environment_guard where singleton for update;
  perform 1 from {SCHEMA}.campaign where id=v_baseline#>>'{{campaign,id}}' for update;
  perform 1 from {SCHEMA}.participant where id='{participant}' for update;
  perform 1 from {SCHEMA}.ranking_contact where participant_id='{participant}' for update;
  select snapshot into v_actual from ({query}) q;
  if v_actual is distinct from v_baseline then raise exception 'CLAIM_QA_PLAN_STALE'; end if;
  insert into {SCHEMA}.claim(id,campaign_id,participant_id,claim_type,status)
    values('{claim_id}',v_baseline#>>'{{campaign,id}}','{participant}','RANKING','AWAITING_INFORMATION');
  select snapshot into v_actual from ({query}) q;
  if (v_actual - 'ranking_claim_count') is distinct from (v_baseline - 'ranking_claim_count')
     or (v_actual->>'ranking_claim_count')::int <> 1 then raise exception 'CLAIM_QA_POSTCONDITION_FAILED'; end if;
end $claimqa$;
select jsonb_build_object('prepared',true,'claim_id','{claim_id}','participant_id','{participant}',
  'claim_type','RANKING','status','AWAITING_INFORMATION') result;
commit;"""


def render_cleanup_sql(plan, confirmation):
    _validate_plan(plan, check_age=False)
    if confirmation != CLEANUP_CONFIRMATION:
        raise ClaimQaError("CLAIM_QA_CLEANUP_CONFIRMATION_REQUIRED")
    participant = plan["participant_id"].replace("'", "''")
    claim_id = plan["fixture"]["claim_id"].replace("'", "''")
    query = _snapshot_sql(plan["environment"], plan["participant_id"])
    baseline = _sql_json(plan["database_state"], "baseline")
    return f"""begin;
set local statement_timeout='15s'; set local lock_timeout='3s';
do $claimqa$
declare v_actual jsonb; v_baseline jsonb := {baseline};
begin
  perform pg_advisory_xact_lock(hashtext('{LOCK_PREFIX}{participant}'));
  perform 1 from {SCHEMA}.environment_guard where singleton for update;
  perform 1 from {SCHEMA}.participant where id='{participant}' for update;
  perform 1 from {SCHEMA}.ranking_contact where participant_id='{participant}' for update;
  perform 1 from {SCHEMA}.claim where id='{claim_id}' and participant_id='{participant}' for update;
  if not found then raise exception 'CLAIM_QA_FIXTURE_TOUCHED'; end if;
  select snapshot into v_actual from ({query}) q;
  if (v_actual - 'ranking_claim_count') is distinct from (v_baseline - 'ranking_claim_count')
     or (v_actual->>'ranking_claim_count')::int <> 1 then raise exception 'CLAIM_QA_PLAN_STALE'; end if;
  if not exists (select 1 from {SCHEMA}.claim where id='{claim_id}' and participant_id='{participant}'
      and claim_type='RANKING' and status='AWAITING_INFORMATION' and version=1
      and draw_id is null and prize_id is null and inventory_item_id is null and contact_submitted_at is null)
    or exists(select 1 from {SCHEMA}.claim_contact where claim_id='{claim_id}')
    or exists(select 1 from {SCHEMA}.claim_contact_draft where claim_id='{claim_id}')
    or exists(select 1 from {SCHEMA}.kakao_share_intent where claim_id='{claim_id}')
  then raise exception 'CLAIM_QA_FIXTURE_TOUCHED'; end if;
  delete from {SCHEMA}.claim where id='{claim_id}';
  select snapshot into v_actual from ({query}) q;
  if v_actual is distinct from v_baseline then raise exception 'CLAIM_QA_CLEANUP_POSTCONDITION_FAILED'; end if;
end $claimqa$;
select jsonb_build_object('cleaned',true,'claim_id','{claim_id}') result;
commit;"""


def apply_fixture(conn, plan, confirmation):
    conn.execute(render_apply_sql(plan, confirmation))
    return {"prepared": True, "claim_id": plan["fixture"]["claim_id"]}


def cleanup_fixture(conn, plan, confirmation):
    conn.execute(render_cleanup_sql(plan, confirmation))
    return {"cleaned": True, "claim_id": plan["fixture"]["claim_id"]}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("test", "preview"), required=True)
    parser.add_argument("--participant-id", required=True)
    parser.add_argument("--dsn-env", default="DINO_QA_MAINTENANCE_DATABASE_URL")
    parser.add_argument("--snapshot-input", type=Path)
    parser.add_argument("--plan", type=Path)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--confirm", default="")
    actions = parser.add_mutually_exclusive_group(required=True)
    actions.add_argument("--print-state-sql", action="store_true")
    actions.add_argument("--create-plan", action="store_true")
    actions.add_argument("--render-apply-sql", action="store_true")
    actions.add_argument("--render-cleanup-sql", action="store_true")
    actions.add_argument("--apply", action="store_true")
    actions.add_argument("--cleanup", action="store_true")
    args = parser.parse_args()
    if args.print_state_sql:
        print(render_state_sql(args.environment, args.participant_id)); return
    if args.create_plan:
        if not args.output:
            parser.error("--output is required")
        if args.snapshot_input:
            plan = plan_from_snapshot(json.loads(args.snapshot_input.read_text()), args.environment, args.participant_id)
        else:
            import os
            dsn = os.getenv(args.dsn_env, "")
            if not dsn: parser.error(f"{args.dsn_env} or --snapshot-input is required")
            with connect(dsn, args.environment) as conn: plan = plan_fixture(conn, args.environment, args.participant_id)
        args.output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n"); return
    if not args.plan:
        parser.error("--plan is required")
    plan = json.loads(args.plan.read_text())
    if args.render_apply_sql:
        print(render_apply_sql(plan, args.confirm)); return
    if args.render_cleanup_sql:
        print(render_cleanup_sql(plan, args.confirm)); return
    import os
    dsn = os.getenv(args.dsn_env, "")
    if not dsn: parser.error(f"{args.dsn_env} is required")
    with connect(dsn, args.environment) as conn:
        result = apply_fixture(conn, plan, args.confirm) if args.apply else cleanup_fixture(conn, plan, args.confirm)
    print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
