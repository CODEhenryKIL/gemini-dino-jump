"""Plan and apply a guarded dino_prod manifest transition.

The default validation and SQL rendering modes never connect to a network.
Direct plan/apply modes require an explicitly supplied maintenance DSN.  The
tool changes only the production campaign status/version/settings and the
single environment guard row; it never deletes gameplay, draw, claim, or
inventory records.
"""
from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "server"))
from phase3_preflight import validate
from config import REQUIRED_SCHEMA_VERSIONS


SCHEMA = "dino_prod"
PROJECT_REF = "igfrnexknwtiljdqjrbp"
LOCK_KEY = "dino-prod-cutover"
PLAN_VERSION = 1
PLAN_MAX_AGE = dt.timedelta(hours=1)
CONFIRMATIONS = {
    "activate": "ACTIVATE_DINO_PRODUCTION",
    "rollback": "ROLLBACK_DINO_PRODUCTION",
}
LOCK_TABLES = (
    "environment_guard", "campaign", "participant", "ticket_ledger", "observation", "bootstrap",
    "invitation_visit", "invitation_reward", "game_session", "best_score", "versioned_best_score",
    "ranking_contact", "ranking_contact_version", "prize", "inventory_item", "draw",
    "inventory_history", "claim", "claim_contact", "claim_contact_draft", "analytics_event",
    "idempotency_request", "ranking_snapshot", "ranking_snapshot_entry", "ranking_award",
    "admin_audit", "rate_limit_bucket", "kakao_share_intent", "draw_credit_ledger", "draw_pool_slot",
)
EMPTY_ON_ACTIVATION = ("participant", "game_session", "draw", "claim")
ALLOWED_MANIFEST_CHANGES = frozenset(("version", "status", "event_enabled", "approvals", "evidence"))


class CutoverError(ValueError):
    pass


def _sha_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def _json_sha(value) -> str:
    payload = json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"), default=str)
    return hashlib.sha256(payload.encode()).hexdigest()


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _manifest(raw: bytes) -> dict:
    if not isinstance(raw, bytes):
        raise CutoverError("MANIFEST_BYTES_REQUIRED")
    try:
        value = json.loads(raw)
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise CutoverError("MANIFEST_INVALID") from exc
    if not isinstance(value, dict):
        raise CutoverError("MANIFEST_INVALID")
    return value


def _freeze_without_transition_fields(manifest: dict) -> dict:
    return {key: value for key, value in manifest.items() if key not in ALLOWED_MANIFEST_CHANGES}


def transition_spec(source_bytes: bytes, target_bytes: bytes, mode: str, expected_campaign_version: int) -> dict:
    if mode not in CONFIRMATIONS:
        raise CutoverError("CUTOVER_MODE_INVALID")
    if type(expected_campaign_version) is not int or expected_campaign_version < 1:
        raise CutoverError("CAMPAIGN_VERSION_INVALID")
    source = _manifest(source_bytes)
    target = _manifest(target_bytes)
    source_result = validate(source)
    target_result = validate(target)
    if _freeze_without_transition_fields(source) != _freeze_without_transition_fields(target):
        raise CutoverError("IMMUTABLE_MANIFEST_FIELDS_CHANGED")
    if source.get("campaign", {}).get("id") != target.get("campaign", {}).get("id"):
        raise CutoverError("CAMPAIGN_CHANGED")
    if mode == "activate":
        if source.get("event_enabled") is not False or not source_result["preparation_ready"]:
            raise CutoverError("SOURCE_NOT_PREPARATION_READY")
        if target.get("event_enabled") is not True or target.get("status") != "APPROVED" or not target_result["launch_ready"]:
            raise CutoverError("TARGET_NOT_LAUNCH_READY")
        source_statuses, target_status = ("PAUSED",), "ACTIVE"
    else:
        if source.get("event_enabled") is not True or source.get("status") != "APPROVED" or not source_result["launch_ready"]:
            raise CutoverError("SOURCE_NOT_LAUNCH_READY")
        if target.get("event_enabled") is not False or not target_result["preparation_ready"]:
            raise CutoverError("TARGET_NOT_PREPARATION_READY")
        source_statuses, target_status = ("ACTIVE", "PAUSED"), "PAUSED"
    campaign = target["campaign"]
    return {
        "mode": mode,
        "source_sha256": _sha_bytes(source_bytes),
        "target_sha256": _sha_bytes(target_bytes),
        "campaign_id": campaign["id"],
        "expected_campaign_version": expected_campaign_version,
        "source_event_enabled": source["event_enabled"],
        "target_event_enabled": target["event_enabled"],
        "allowed_source_statuses": list(source_statuses),
        "target_campaign_status": target_status,
        "campaign": {
            "opens_at": campaign["opens_at"],
            "closes_at": campaign["closes_at"],
            "claim_closes_at": campaign["claim_closes_at"],
        },
        "draw_pool_total": target["draw_pool"]["total_slots"],
        "draw_prize_quantity": sum(item["quantity"] for item in target["draw_prizes"]),
        "source_draw_prize_quantity": sum(item["quantity"] for item in source["draw_prizes"]),
        "draw_benefit_quantity": target["draw_pool"]["benefit_slots"],
        "ranking_prize_quantity": sum(item["quantity"] for item in target["ranking_prizes"]),
        "inventory_by_prize": {
            campaign["id"] + "_" + item["id"]: item["quantity"] for item in target["draw_prizes"]
        } | {
            f"{campaign['id']}_rank_{item['rank']}": item["quantity"] for item in target["ranking_prizes"]
        },
    }


def _maintenance_role(conn) -> str:
    row = conn.execute("select current_user name, rolsuper or rolbypassrls maintenance from pg_roles where rolname=current_user").fetchone()
    if not row or not row["maintenance"] or row["name"] in {"dino_dev_app", "dino_prod_app"}:
        raise CutoverError("MAINTENANCE_ROLE_REQUIRED")
    return row["name"]


def _state(conn, spec: dict, lock: bool = False) -> dict:
    suffix = " for update" if lock else ""
    guard = conn.execute(f"select * from {SCHEMA}.environment_guard where singleton{suffix}").fetchone()
    campaign = conn.execute(f"select * from {SCHEMA}.campaign where id=%s{suffix}", (spec["campaign_id"],)).fetchone()
    if not guard or not campaign:
        raise CutoverError("PRODUCTION_STATE_MISSING")
    counts = {
        table: conn.execute(f"select count(*) count from {SCHEMA}.{table}").fetchone()["count"]
        for table in EMPTY_ON_ACTIVATION
    }
    slots = conn.execute(f"""select count(*) total,
      count(*) filter(where outcome_kind='PRIZE') prize,
      count(*) filter(where outcome_kind='BENEFIT') benefit
      from {SCHEMA}.draw_pool_slot where campaign_id=%s""", (spec["campaign_id"],)).fetchone()
    inventory_rows = conn.execute(f"""select p.id,count(i.id) quantity
      from {SCHEMA}.prize p left join {SCHEMA}.inventory_item i on i.prize_id=p.id
      where p.campaign_id=%s and p.category<>'NO_PRIZE' group by p.id order by p.id""", (spec["campaign_id"],)).fetchall()
    versions = [row["version"] for row in conn.execute(f"select version from {SCHEMA}.schema_version order by version").fetchall()]
    guard_state = {
            key: guard[key] for key in (
                "environment", "project_ref", "schema_name", "synthetic_only", "test_seed", "campaign_id",
                "launch_manifest_sha256", "event_enabled", "campaign_opens_at", "campaign_closes_at",
                "claim_closes_at", "draw_pool_total", "draw_prize_quantity", "ranking_prize_quantity",
                "unlimited_play", "synthetic_inventory", "shortened_clock",
            )
        }
    for key in ("campaign_opens_at", "campaign_closes_at", "claim_closes_at"):
        guard_state[key] = _iso(guard_state[key])
    campaign_state = {
            "id": campaign["id"], "status": campaign["status"], "version": campaign["version"],
            "game_version": campaign["game_version"], "is_test": campaign["is_test"],
            "real_prizes_enabled": campaign["real_prizes_enabled"], "opens_at": campaign["opens_at"],
            "closes_at": campaign["closes_at"], "phase3_manifest_hash": (campaign["settings"] or {}).get("phase3_manifest_hash"),
            "claim_submission_cutoff": (campaign["settings"] or {}).get("claim_submission_cutoff"),
            "ranking_finish_acceptance_cutoff": (campaign["settings"] or {}).get("ranking_finish_acceptance_cutoff"),
        }
    for key in ("opens_at", "closes_at"):
        campaign_state[key] = _iso(campaign_state[key])
    return {
        "guard": guard_state,
        "campaign": campaign_state,
        "record_counts": counts,
        "draw_pool": dict(slots),
        "inventory_by_prize": {row["id"]: row["quantity"] for row in inventory_rows},
        "inventory_total": sum(row["quantity"] for row in inventory_rows),
        "schema_versions": versions,
    }


def _iso(value) -> str:
    if isinstance(value, dt.datetime):
        return value.astimezone(dt.timezone.utc).isoformat()
    if isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return value
        if parsed.tzinfo is not None:
            return parsed.astimezone(dt.timezone.utc).isoformat()
    return str(value)


def _assert_state(state: dict, spec: dict, *, target: bool = False) -> None:
    guard = state["guard"]
    campaign = state["campaign"]
    expected_hash = spec["target_sha256"] if target else spec["source_sha256"]
    expected_event = spec["target_event_enabled"] if target else spec["source_event_enabled"]
    expected_statuses = (spec["target_campaign_status"],) if target else tuple(spec["allowed_source_statuses"])
    expected_version = spec["expected_campaign_version"] + (1 if target else 0)
    expected_guard = {
        "environment": "production", "project_ref": PROJECT_REF, "schema_name": SCHEMA,
        "synthetic_only": False, "test_seed": False, "campaign_id": spec["campaign_id"],
        "launch_manifest_sha256": expected_hash, "event_enabled": expected_event,
        "draw_pool_total": spec["draw_pool_total"],
        "draw_prize_quantity": (spec["draw_prize_quantity"] if target else spec["source_draw_prize_quantity"]),
        "ranking_prize_quantity": spec["ranking_prize_quantity"],
        "unlimited_play": False, "synthetic_inventory": False, "shortened_clock": False,
    }
    if any(guard.get(key) != value for key, value in expected_guard.items()):
        raise CutoverError("PRODUCTION_GUARD_MISMATCH")
    for key in ("campaign_opens_at", "campaign_closes_at", "claim_closes_at"):
        manifest_key = {"campaign_opens_at": "opens_at", "campaign_closes_at": "closes_at", "claim_closes_at": "claim_closes_at"}[key]
        if _iso(guard[key]) != _iso(dt.datetime.fromisoformat(spec["campaign"][manifest_key])):
            raise CutoverError("PRODUCTION_GUARD_SCHEDULE_MISMATCH")
    if campaign["id"] != spec["campaign_id"] or campaign["status"] not in expected_statuses or campaign["version"] != expected_version:
        raise CutoverError("PRODUCTION_CAMPAIGN_MISMATCH")
    if campaign["game_version"] != "2.1.0" or campaign["is_test"] or not campaign["real_prizes_enabled"]:
        raise CutoverError("PRODUCTION_CAMPAIGN_FLAGS_MISMATCH")
    if _iso(campaign["opens_at"]) != _iso(dt.datetime.fromisoformat(spec["campaign"]["opens_at"])) or _iso(campaign["closes_at"]) != _iso(dt.datetime.fromisoformat(spec["campaign"]["closes_at"])):
        raise CutoverError("PRODUCTION_CAMPAIGN_SCHEDULE_MISMATCH")
    if campaign["phase3_manifest_hash"] != expected_hash:
        raise CutoverError("PRODUCTION_CAMPAIGN_HASH_MISMATCH")
    if campaign["claim_submission_cutoff"] != spec["campaign"]["claim_closes_at"] or campaign["ranking_finish_acceptance_cutoff"] != spec["campaign"]["closes_at"]:
        raise CutoverError("PRODUCTION_CAMPAIGN_CUTOFF_MISMATCH")
    if state["draw_pool"] != {
        "total": spec["draw_pool_total"],
        "prize": spec["draw_prize_quantity"],
        "benefit": spec["draw_benefit_quantity"],
    }:
        raise CutoverError("PRODUCTION_DRAW_POOL_MISMATCH")
    expected_inventory_total = spec["draw_prize_quantity"] + spec["ranking_prize_quantity"]
    if state["inventory_by_prize"] != spec["inventory_by_prize"] or state["inventory_total"] != expected_inventory_total:
        raise CutoverError("PRODUCTION_INVENTORY_MISMATCH")
    if state["schema_versions"] != list(REQUIRED_SCHEMA_VERSIONS):
        raise CutoverError("PRODUCTION_SCHEMA_VERSION_MISMATCH")
    if not target and spec["mode"] == "activate" and any(state["record_counts"].values()):
        raise CutoverError("PRODUCTION_NOT_EMPTY")


def plan_transition(conn, source_bytes: bytes, target_bytes: bytes, mode: str, expected_campaign_version: int) -> dict:
    spec = transition_spec(source_bytes, target_bytes, mode, expected_campaign_version)
    with conn.transaction():
        conn.execute("set local transaction read only")
        conn.execute("set local statement_timeout='10s'; set local lock_timeout='1500ms'")
        conn.execute("select pg_advisory_xact_lock_shared(hashtext(%s))", (LOCK_KEY,))
        role = _maintenance_role(conn)
        state = _state(conn, spec)
        _assert_state(state, spec)
    return build_plan_from_state(state, role, spec)


def build_plan_from_state(state: dict, maintenance_role: str, spec: dict) -> dict:
    _assert_state(state, spec)
    if not maintenance_role or maintenance_role in {"dino_dev_app", "dino_prod_app"}:
        raise CutoverError("MAINTENANCE_ROLE_REQUIRED")
    plan = {
        "plan_version": PLAN_VERSION,
        "created_at": _utc(dt.datetime.now(dt.timezone.utc)),
        "maintenance_role": maintenance_role,
        "spec": spec,
        "database_state": state,
        "database_state_sha256": _json_sha(state),
    }
    plan["sha256"] = _json_sha(plan)
    return plan


def _validate_plan(plan: dict, spec: dict) -> None:
    if not isinstance(plan, dict) or plan.get("plan_version") != PLAN_VERSION:
        raise CutoverError("CUTOVER_PLAN_INVALID")
    supplied = plan.get("sha256")
    body = {key: value for key, value in plan.items() if key != "sha256"}
    if not re.fullmatch(r"[0-9a-f]{64}", str(supplied or "")) or _json_sha(body) != supplied:
        raise CutoverError("CUTOVER_PLAN_DIGEST_MISMATCH")
    if plan.get("spec") != spec or plan.get("database_state_sha256") != _json_sha(plan.get("database_state")):
        raise CutoverError("CUTOVER_PLAN_TARGET_MISMATCH")
    try:
        created = dt.datetime.fromisoformat(plan["created_at"])
    except (KeyError, TypeError, ValueError) as exc:
        raise CutoverError("CUTOVER_PLAN_INVALID") from exc
    now = dt.datetime.now(dt.timezone.utc)
    created = created.astimezone(dt.timezone.utc) if created.tzinfo is not None else created
    if created.tzinfo is None or created > now + dt.timedelta(minutes=5) or now - created > PLAN_MAX_AGE:
        raise CutoverError("CUTOVER_PLAN_EXPIRED")


def apply_transition(conn, plan: dict, source_bytes: bytes, target_bytes: bytes, confirmation: str) -> dict:
    raw_spec = plan.get("spec") if isinstance(plan, dict) else {}
    spec = transition_spec(source_bytes, target_bytes, raw_spec.get("mode"), raw_spec.get("expected_campaign_version"))
    _validate_plan(plan, spec)
    if confirmation != CONFIRMATIONS[spec["mode"]]:
        raise CutoverError("CUTOVER_CONFIRMATION_REQUIRED")
    tables = ",".join(f"{SCHEMA}.{table}" for table in LOCK_TABLES)
    with conn.transaction():
        conn.execute("set local statement_timeout='20s'; set local lock_timeout='5s'")
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (LOCK_KEY,))
        conn.execute(f"lock table {tables} in access exclusive mode")
        _maintenance_role(conn)
        before = _state(conn, spec, lock=True)
        _assert_state(before, spec)
        if before != plan["database_state"]:
            raise CutoverError("CUTOVER_PLAN_STALE")
        campaign = spec["campaign"]
        conn.execute(f"""update {SCHEMA}.campaign set status=%s,version=version+1,opens_at=%s,closes_at=%s,
          settings=jsonb_set(jsonb_set(jsonb_set(settings,'{{phase3_manifest_hash}}',to_jsonb(%s::text)),
          '{{claim_submission_cutoff}}',to_jsonb(%s::text)),'{{ranking_finish_acceptance_cutoff}}',to_jsonb(%s::text)),
          updated_at=clock_timestamp() where id=%s and version=%s""",
          (spec["target_campaign_status"], campaign["opens_at"], campaign["closes_at"], spec["target_sha256"],
           campaign["claim_closes_at"], campaign["closes_at"], spec["campaign_id"], spec["expected_campaign_version"]))
        conn.execute(f"""update {SCHEMA}.environment_guard set launch_manifest_sha256=%s,event_enabled=%s,
          campaign_opens_at=%s,campaign_closes_at=%s,claim_closes_at=%s,draw_pool_total={spec['draw_pool_total']},
          draw_prize_quantity={spec['draw_prize_quantity']},ranking_prize_quantity={spec['ranking_prize_quantity']} where singleton""",
          (spec["target_sha256"], spec["target_event_enabled"], campaign["opens_at"], campaign["closes_at"], campaign["claim_closes_at"]))
        after = _state(conn, spec, lock=True)
        _assert_state(after, spec, target=True)
        if any(after[key] != before[key] for key in ("record_counts", "inventory_by_prize", "inventory_total", "draw_pool")):
            raise CutoverError("CUTOVER_RECORDS_CHANGED")
    return {
        "applied": True, "mode": spec["mode"], "campaign_id": spec["campaign_id"],
        "source_sha256": spec["source_sha256"], "target_sha256": spec["target_sha256"],
        "campaign_version": spec["expected_campaign_version"] + 1,
        "event_enabled": spec["target_event_enabled"], "records_preserved": True,
    }


def _sql_literal(value: str) -> str:
    return "'" + value.replace("'", "''") + "'"


def render_state_sql(spec: dict) -> str:
    """Render one read-only snapshot query for an approved SQL connector."""
    cid = _sql_literal(spec["campaign_id"])
    return f"""with guard_row as (
  select * from dino_prod.environment_guard where singleton
), campaign_row as (
  select * from dino_prod.campaign where id={cid}
), inventory as (
  select coalesce(jsonb_object_agg(id,quantity order by id),'{{}}'::jsonb) value,
         coalesce(sum(quantity),0)::int total from (
    select p.id,count(i.id)::int quantity from dino_prod.prize p
    left join dino_prod.inventory_item i on i.prize_id=p.id
    where p.campaign_id={cid} and p.category<>'NO_PRIZE' group by p.id
  ) q
), slots as (
  select count(*)::int total,count(*) filter(where outcome_kind='PRIZE')::int prize,
    count(*) filter(where outcome_kind='BENEFIT')::int benefit
  from dino_prod.draw_pool_slot where campaign_id={cid}
)
select jsonb_build_object(
  'maintenance_role',current_user,
  'maintenance_role_ok',coalesce((select rolsuper or rolbypassrls from pg_roles where rolname=current_user),false)
    and current_user not in ('dino_dev_app','dino_prod_app'),
  'database_state',jsonb_build_object(
    'guard',(select jsonb_build_object(
      'environment',environment,'project_ref',project_ref,'schema_name',schema_name,'synthetic_only',synthetic_only,
      'test_seed',test_seed,'campaign_id',campaign_id,'launch_manifest_sha256',launch_manifest_sha256,
      'event_enabled',event_enabled,'campaign_opens_at',campaign_opens_at,'campaign_closes_at',campaign_closes_at,
      'claim_closes_at',claim_closes_at,'draw_pool_total',draw_pool_total,'draw_prize_quantity',draw_prize_quantity,
      'ranking_prize_quantity',ranking_prize_quantity,'unlimited_play',unlimited_play,
      'synthetic_inventory',synthetic_inventory,'shortened_clock',shortened_clock) from guard_row),
    'campaign',(select jsonb_build_object(
      'id',id,'status',status,'version',version,'game_version',game_version,'is_test',is_test,
      'real_prizes_enabled',real_prizes_enabled,'opens_at',opens_at,'closes_at',closes_at,
      'phase3_manifest_hash',settings->>'phase3_manifest_hash',
      'claim_submission_cutoff',settings->>'claim_submission_cutoff',
      'ranking_finish_acceptance_cutoff',settings->>'ranking_finish_acceptance_cutoff') from campaign_row),
    'record_counts',jsonb_build_object(
      'participant',(select count(*)::int from dino_prod.participant),
      'game_session',(select count(*)::int from dino_prod.game_session),
      'draw',(select count(*)::int from dino_prod.draw),
      'claim',(select count(*)::int from dino_prod.claim)),
    'draw_pool',(select to_jsonb(slots) from slots),
    'inventory_by_prize',(select value from inventory),
    'inventory_total',(select total from inventory),
    'schema_versions',(select coalesce(jsonb_agg(version order by version),'[]'::jsonb) from dino_prod.schema_version)
  )
) snapshot;
"""


def plan_from_snapshot(snapshot: dict, source_bytes: bytes, target_bytes: bytes, mode: str, expected_campaign_version: int) -> dict:
    spec = transition_spec(source_bytes, target_bytes, mode, expected_campaign_version)
    if not isinstance(snapshot, dict) or snapshot.get("maintenance_role_ok") is not True or not isinstance(snapshot.get("database_state"), dict):
        raise CutoverError("CUTOVER_SNAPSHOT_INVALID")
    raw_state = snapshot["database_state"]
    state = {**raw_state, "guard": dict(raw_state.get("guard") or {}), "campaign": dict(raw_state.get("campaign") or {})}
    for key in ("campaign_opens_at", "campaign_closes_at", "claim_closes_at"):
        if key in state["guard"]:
            state["guard"][key] = _iso(state["guard"][key])
    for key in ("opens_at", "closes_at"):
        if key in state["campaign"]:
            state["campaign"][key] = _iso(state["campaign"][key])
    return build_plan_from_state(state, str(snapshot.get("maintenance_role") or ""), spec)


def render_apply_sql(plan: dict, source_bytes: bytes, target_bytes: bytes) -> str:
    """Render a checked transaction for an approved SQL connector.

    The SQL embeds the reviewed plan state and repeats every runtime guard,
    inventory, empty-on-activation, and plan-token assertion before updating.
    """
    raw_spec = plan.get("spec") if isinstance(plan, dict) else {}
    spec = transition_spec(source_bytes, target_bytes, raw_spec.get("mode"), raw_spec.get("expected_campaign_version"))
    _validate_plan(plan, spec)
    state = plan["database_state"]
    g = state["guard"]; c = state["campaign"]
    inventory = json.dumps(spec["inventory_by_prize"], sort_keys=True, separators=(",", ":"))
    record_counts = plan["database_state"]["record_counts"]
    empty_assert = ""
    if spec["mode"] == "activate":
        empty_assert = "\n  if exists(select 1 from dino_prod.participant) or exists(select 1 from dino_prod.game_session) or exists(select 1 from dino_prod.draw) or exists(select 1 from dino_prod.claim) then raise exception 'PRODUCTION_NOT_EMPTY'; end if;"
    target_event = "true" if spec["target_event_enabled"] else "false"
    source_event = "true" if spec["source_event_enabled"] else "false"
    statuses = ",".join(_sql_literal(value) for value in spec["allowed_source_statuses"])
    tables = ",".join(f"dino_prod.{table}" for table in LOCK_TABLES)
    return f"""begin;
set local statement_timeout='20s';
set local lock_timeout='5s';
select pg_advisory_xact_lock(hashtext('{LOCK_KEY}'));
lock table {tables} in access exclusive mode;
do $$
declare inventory jsonb; slot_total bigint; slot_prize bigint; slot_benefit bigint;
begin
  if clock_timestamp()>{_sql_literal(plan['created_at'])}::timestamptz+interval '1 hour'
    or clock_timestamp()<{_sql_literal(plan['created_at'])}::timestamptz-interval '5 minutes'
    then raise exception 'CUTOVER_PLAN_EXPIRED'; end if;
  if not exists(select 1 from pg_roles where rolname=current_user and (rolsuper or rolbypassrls))
     or current_user in ('dino_dev_app','dino_prod_app') then raise exception 'MAINTENANCE_ROLE_REQUIRED'; end if;
  if not exists(select 1 from dino_prod.environment_guard where singleton and environment='production'
    and project_ref='{PROJECT_REF}' and schema_name='dino_prod' and not synthetic_only and not test_seed
    and campaign_id={_sql_literal(spec['campaign_id'])} and launch_manifest_sha256={_sql_literal(spec['source_sha256'])}
    and event_enabled={source_event}
    and campaign_opens_at={_sql_literal(spec['campaign']['opens_at'])}::timestamptz
    and campaign_closes_at={_sql_literal(spec['campaign']['closes_at'])}::timestamptz
    and claim_closes_at={_sql_literal(spec['campaign']['claim_closes_at'])}::timestamptz
    and draw_pool_total={spec['draw_pool_total']} and draw_prize_quantity={spec['source_draw_prize_quantity']} and ranking_prize_quantity={spec['ranking_prize_quantity']}
    and not unlimited_play and not synthetic_inventory and not shortened_clock) then raise exception 'PRODUCTION_GUARD_MISMATCH'; end if;
  if not exists(select 1 from dino_prod.campaign where id={_sql_literal(spec['campaign_id'])}
    and status in ({statuses}) and version={spec['expected_campaign_version']} and game_version='2.1.0'
    and not is_test and real_prizes_enabled
    and opens_at={_sql_literal(spec['campaign']['opens_at'])}::timestamptz
    and closes_at={_sql_literal(spec['campaign']['closes_at'])}::timestamptz
    and settings->>'phase3_manifest_hash'={_sql_literal(spec['source_sha256'])}
    and settings->>'claim_submission_cutoff'={_sql_literal(spec['campaign']['claim_closes_at'])}
    and settings->>'ranking_finish_acceptance_cutoff'={_sql_literal(spec['campaign']['closes_at'])})
    then raise exception 'PRODUCTION_CAMPAIGN_MISMATCH'; end if;{empty_assert}
  if (select count(*) from dino_prod.participant)<>{record_counts['participant']}
    or (select count(*) from dino_prod.game_session)<>{record_counts['game_session']}
    or (select count(*) from dino_prod.draw)<>{record_counts['draw']}
    or (select count(*) from dino_prod.claim)<>{record_counts['claim']}
    then raise exception 'CUTOVER_PLAN_STALE'; end if;
  select count(*),count(*) filter(where outcome_kind='PRIZE'),count(*) filter(where outcome_kind='BENEFIT')
    into slot_total,slot_prize,slot_benefit from dino_prod.draw_pool_slot where campaign_id={_sql_literal(spec['campaign_id'])};
  if (slot_total,slot_prize,slot_benefit)<>({spec['draw_pool_total']},{spec['draw_prize_quantity']},{spec['draw_benefit_quantity']}) then raise exception 'PRODUCTION_DRAW_POOL_MISMATCH'; end if;
  select jsonb_object_agg(id,quantity order by id) into inventory from (
    select p.id,count(i.id)::int quantity from dino_prod.prize p left join dino_prod.inventory_item i on i.prize_id=p.id
    where p.campaign_id={_sql_literal(spec['campaign_id'])} and p.category<>'NO_PRIZE' group by p.id) q;
  if inventory is distinct from {_sql_literal(inventory)}::jsonb then raise exception 'PRODUCTION_INVENTORY_MISMATCH'; end if;
  if (select array_agg(version order by version) from dino_prod.schema_version) is distinct from
    array[{','.join(_sql_literal(value) for value in REQUIRED_SCHEMA_VERSIONS)}]::text[]
    then raise exception 'PRODUCTION_SCHEMA_VERSION_MISMATCH'; end if;
end $$;
update dino_prod.campaign set status={_sql_literal(spec['target_campaign_status'])},version=version+1,
  opens_at={_sql_literal(spec['campaign']['opens_at'])}::timestamptz,closes_at={_sql_literal(spec['campaign']['closes_at'])}::timestamptz,
  settings=jsonb_set(jsonb_set(jsonb_set(settings,'{{phase3_manifest_hash}}',to_jsonb({_sql_literal(spec['target_sha256'])}::text)),
    '{{claim_submission_cutoff}}',to_jsonb({_sql_literal(spec['campaign']['claim_closes_at'])}::text)),
    '{{ranking_finish_acceptance_cutoff}}',to_jsonb({_sql_literal(spec['campaign']['closes_at'])}::text)),updated_at=clock_timestamp()
  where id={_sql_literal(spec['campaign_id'])} and version={spec['expected_campaign_version']};
update dino_prod.environment_guard set launch_manifest_sha256={_sql_literal(spec['target_sha256'])},event_enabled={target_event},
  campaign_opens_at={_sql_literal(spec['campaign']['opens_at'])}::timestamptz,campaign_closes_at={_sql_literal(spec['campaign']['closes_at'])}::timestamptz,
  claim_closes_at={_sql_literal(spec['campaign']['claim_closes_at'])}::timestamptz,
  draw_pool_total={spec['draw_pool_total']},draw_prize_quantity={spec['draw_prize_quantity']},ranking_prize_quantity={spec['ranking_prize_quantity']} where singleton;
do $$ begin
  if not exists(select 1 from dino_prod.environment_guard where singleton
    and launch_manifest_sha256={_sql_literal(spec['target_sha256'])} and event_enabled={target_event})
    or not exists(select 1 from dino_prod.campaign where id={_sql_literal(spec['campaign_id'])}
      and status={_sql_literal(spec['target_campaign_status'])} and version={spec['expected_campaign_version'] + 1}
      and settings->>'phase3_manifest_hash'={_sql_literal(spec['target_sha256'])})
    then raise exception 'CUTOVER_POSTCONDITION_FAILED'; end if;
end $$;
commit;
select {_sql_literal(json.dumps({'plan_sha256': plan['sha256'], 'mode': spec['mode'], 'target_sha256': spec['target_sha256'], 'event_enabled': spec['target_event_enabled'], 'records_preserved': True}, separators=(',', ':')))}::jsonb result;
"""


def _connect(dsn: str):
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or not parsed.hostname or parsed.query or parsed.fragment:
        raise CutoverError("CUTOVER_DSN_INVALID")
    options = {"row_factory": dict_row, "connect_timeout": 5, "prepare_threshold": None}
    if parsed.hostname in {"localhost", "127.0.0.1", "::1"}:
        if parsed.port != 55433 or parsed.username != "postgres" or not re.fullmatch(r"/dino_phase1_audit_[a-z0-9_]+", parsed.path):
            raise CutoverError("CUTOVER_ISOLATED_TEST_DB_REQUIRED")
        return psycopg.connect(dsn, **options)
    direct = parsed.hostname == f"db.{PROJECT_REF}.supabase.co" and parsed.port == 5432 and parsed.username == "postgres"
    pooled = (bool(parsed.hostname) and parsed.hostname.endswith(".pooler.supabase.com")
              and parsed.port in {5432, 6543} and parsed.username == f"postgres.{PROJECT_REF}")
    if not (direct or pooled) or parsed.path != "/postgres":
        raise CutoverError("CUTOVER_MAINTENANCE_DSN_REQUIRED")
    return psycopg.connect(dsn, sslmode="verify-full", sslrootcert=str(ROOT / "server/certs/supabase-ca-2021.crt"), **options)


def _read(path: Path) -> bytes:
    return path.read_bytes()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source-manifest", type=Path, required=True)
    parser.add_argument("--target-manifest", type=Path, required=True)
    parser.add_argument("--mode", choices=tuple(CONFIRMATIONS), required=True)
    parser.add_argument("--expected-campaign-version", type=int, required=True)
    parser.add_argument("--dsn-env", default="DINO_PRODUCTION_MAINTENANCE_DATABASE_URL")
    modes = parser.add_mutually_exclusive_group(required=True)
    modes.add_argument("--validate-only", action="store_true")
    modes.add_argument("--plan-output", type=Path)
    modes.add_argument("--apply-plan", type=Path)
    modes.add_argument("--render-apply-sql", type=Path, metavar="PLAN_FILE")
    modes.add_argument("--print-state-sql", action="store_true")
    parser.add_argument("--snapshot-input", type=Path)
    parser.add_argument("--confirm", default="")
    args = parser.parse_args()
    source_bytes, target_bytes = _read(args.source_manifest), _read(args.target_manifest)
    spec = transition_spec(source_bytes, target_bytes, args.mode, args.expected_campaign_version)
    if args.validate_only:
        print(json.dumps({"valid": True, "network": False, "spec": spec}, ensure_ascii=False, sort_keys=True))
        return
    if args.print_state_sql:
        print(render_state_sql(spec))
        return
    if args.render_apply_sql:
        required = CONFIRMATIONS[args.mode]
        if args.confirm != required:
            parser.error(f"--confirm {required} is required to render executable cutover SQL")
        plan = json.loads(args.render_apply_sql.read_text(encoding="utf-8"))
        print(render_apply_sql(plan, source_bytes, target_bytes))
        return
    if args.plan_output and args.snapshot_input:
        raw = json.loads(args.snapshot_input.read_text(encoding="utf-8"))
        snapshot = raw.get("snapshot", raw)
        plan = plan_from_snapshot(snapshot, source_bytes, target_bytes, args.mode, args.expected_campaign_version)
        args.plan_output.parent.mkdir(parents=True, exist_ok=True)
        args.plan_output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        print(json.dumps({"applied": False, "network": False, "plan": str(args.plan_output), "sha256": plan["sha256"]}, sort_keys=True))
        return
    dsn = os.getenv(args.dsn_env, "")
    if not dsn:
        parser.error(f"{args.dsn_env} is required for direct database plan/apply")
    with _connect(dsn) as conn:
        if args.plan_output:
            plan = plan_transition(conn, source_bytes, target_bytes, args.mode, args.expected_campaign_version)
            args.plan_output.parent.mkdir(parents=True, exist_ok=True)
            args.plan_output.write_text(json.dumps(plan, ensure_ascii=False, indent=2, default=str) + "\n", encoding="utf-8")
            print(json.dumps({"applied": False, "plan": str(args.plan_output), "sha256": plan["sha256"]}, sort_keys=True))
        else:
            plan = json.loads(args.apply_plan.read_text(encoding="utf-8"))
            print(json.dumps(apply_transition(conn, plan, source_bytes, target_bytes, args.confirm), sort_keys=True))


if __name__ == "__main__":
    main()
