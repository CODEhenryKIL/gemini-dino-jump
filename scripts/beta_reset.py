"""Plan and apply the narrowly scoped Gemini Dino Jump beta reset.

The tool never drops or truncates objects.  A reset can only be applied after
the beta ingress has been disabled externally, the beta campaign is paused,
and an apply-time snapshot exactly matches a recent plan.
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
sys.path.insert(0, str(ROOT / "server"))
from config import REQUIRED_SCHEMA_VERSIONS


SCHEMA = "dino_dev"
CAMPAIGN_ID = "gemini_dino_phase1_test"
PROJECT_REF = "igfrnexknwtiljdqjrbp"
PLAN_VERSION = 1
PLAN_MAX_AGE = dt.timedelta(hours=1)
INGRESS_CONFIRMATION = "BETA_INGRESS_DISABLED"

LOCK_TABLES = (
    "environment_guard", "campaign", "participant", "ticket_ledger", "observation", "bootstrap",
    "invitation_visit", "invitation_reward", "game_session", "best_score", "versioned_best_score",
    "ranking_contact", "ranking_contact_version", "prize", "inventory_item", "draw",
    "inventory_history", "claim", "claim_contact", "claim_contact_draft", "analytics_event",
    "idempotency_request", "ranking_snapshot", "ranking_snapshot_entry", "ranking_award",
    "admin_audit", "rate_limit_bucket", "kakao_share_intent", "draw_credit_ledger", "draw_pool_slot",
)
QUARANTINE_TABLES = tuple(table for table in LOCK_TABLES if table not in {
    "environment_guard", "admin_member",
})
NON_DELETED_SCOPE_KEYS = {"campaign", "participant_token_hash"}


class BetaResetError(ValueError):
    pass


def _utc(value: dt.datetime) -> str:
    return value.astimezone(dt.timezone.utc).isoformat()


def _sha(payload) -> str:
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"), default=str).encode()).hexdigest()


def _plan_digest(plan: dict) -> str:
    return _sha({key: value for key, value in plan.items() if key != "sha256"})


def _id_digest(values: list[str]) -> str:
    payload = "|".join(f"{len(value.encode('utf-8'))}:{value}" for value in sorted(values))
    return hashlib.sha256(payload.encode()).hexdigest()


def _scope_stats(ids: dict[str, list[str]]) -> dict[str, dict[str, int | str]]:
    return {
        name: {"count": len(values), "id_sha256": _id_digest(values)}
        for name, values in sorted(ids.items())
    }


def _scope_token(tables: dict[str, dict[str, int | str]]) -> str:
    payload = "\n".join(
        f"{name}:{spec['count']}:{spec['id_sha256']}" for name, spec in sorted(tables.items())
    )
    return hashlib.sha256(payload.encode()).hexdigest()


def connect(dsn: str, environment: str):
    parsed = urlsplit(dsn)
    if parsed.scheme not in {"postgres", "postgresql"} or parsed.query or parsed.fragment:
        raise BetaResetError("BETA_RESET_DSN_INVALID")
    if environment == "test":
        if (parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.port != 55433
                or parsed.username != "postgres" or not re.fullmatch(r"/dino_phase1_audit_[a-z0-9_]+", parsed.path)):
            raise BetaResetError("BETA_RESET_ISOLATED_TEST_DB_REQUIRED")
        ssl = {}
    elif environment == "preview":
        direct = parsed.hostname == f"db.{PROJECT_REF}.supabase.co" and parsed.port == 5432 and parsed.username == "postgres"
        pooled = (bool(parsed.hostname) and parsed.hostname.endswith(".pooler.supabase.com")
                  and parsed.port in {5432, 6543} and parsed.username == f"postgres.{PROJECT_REF}")
        if not (direct or pooled) or parsed.path != "/postgres":
            raise BetaResetError("BETA_RESET_APPROVED_PROJECT_REQUIRED")
        ssl = {"sslmode": "verify-full", "sslrootcert": str(ROOT / "server/certs/supabase-ca-2021.crt")}
    else:
        raise BetaResetError("BETA_RESET_PREVIEW_ONLY")
    return psycopg.connect(
        dsn, autocommit=True, row_factory=dict_row, connect_timeout=5, prepare_threshold=None, **ssl
    )


def _values(rows, key="id"):
    return [str(row[key]) for row in rows]


def _select_ids(conn, query, params=(), key="id"):
    return _values(conn.execute(query, params).fetchall(), key)


def _scope(conn, environment: str, *, lock: bool = False) -> dict[str, list[str]]:
    expected_project = "local" if environment == "test" else PROJECT_REF
    role = conn.execute("""select current_user name, rolsuper or rolbypassrls maintenance
        from pg_roles where rolname=current_user""").fetchone()
    if not role or not role["maintenance"] or role["name"] in {"dino_dev_app", "dino_prod_app"}:
        raise BetaResetError("BETA_RESET_MAINTENANCE_ROLE_REQUIRED")
    guard = conn.execute(f"select * from {SCHEMA}.environment_guard where singleton"
                         + (" for update" if lock else "")).fetchone()
    if (not guard or guard["environment"] != environment or guard["project_ref"] != expected_project
            or guard["schema_name"] != SCHEMA or guard["synthetic_only"] is not True
            or guard["campaign_id"] != CAMPAIGN_ID
            or (environment == "preview" and guard["test_seed"] is not True)):
        raise BetaResetError("BETA_RESET_GUARD_MISMATCH")
    versions = {row["version"] for row in conn.execute(f"select version from {SCHEMA}.schema_version")}
    if not set(REQUIRED_SCHEMA_VERSIONS).issubset(versions):
        raise BetaResetError("BETA_RESET_SCHEMA_INCOMPLETE")
    campaign = conn.execute(f"select id,status,is_test,real_prizes_enabled from {SCHEMA}.campaign where id=%s"
                            + (" for update" if lock else ""), (CAMPAIGN_ID,)).fetchone()
    if not campaign:
        raise BetaResetError("BETA_RESET_CAMPAIGN_NOT_FOUND")
    if campaign["status"] not in {"PAUSED", "ENDED"}:
        raise BetaResetError("BETA_RESET_CAMPAIGN_NOT_FROZEN")
    if campaign["is_test"] is not True or campaign["real_prizes_enabled"] is not False:
        raise BetaResetError("BETA_RESET_CAMPAIGN_NOT_SYNTHETIC")
    writable = conn.execute("""select table_name from unnest(%s::text[]) table_list(table_name)
        where has_table_privilege('dino_dev_app',format('%%I.%%I',%s::text,table_name),'INSERT')
           or has_table_privilege('dino_dev_app',format('%%I.%%I',%s::text,table_name),'UPDATE')
           or has_table_privilege('dino_dev_app',format('%%I.%%I',%s::text,table_name),'DELETE')
           or has_any_column_privilege('dino_dev_app',format('%%I.%%I',%s::text,table_name),'INSERT')
           or has_any_column_privilege('dino_dev_app',format('%%I.%%I',%s::text,table_name),'UPDATE')
        order by table_name""", (list(QUARANTINE_TABLES), SCHEMA, SCHEMA, SCHEMA, SCHEMA, SCHEMA)).fetchall()
    if writable:
        raise BetaResetError("BETA_RESET_DATABASE_QUARANTINE_REQUIRED")

    ids: dict[str, list[str]] = {"campaign": [CAMPAIGN_ID]}
    ids["participant"] = _select_ids(conn, f"select id from {SCHEMA}.participant where campaign_id=%s order by id", (CAMPAIGN_ID,))
    participant_ids = ids["participant"]
    ids["participant_token_hash"] = _select_ids(
        conn, f"select token_hash id from {SCHEMA}.participant where campaign_id=%s order by token_hash", (CAMPAIGN_ID,)
    )
    ids["prize"] = _select_ids(conn, f"select id from {SCHEMA}.prize where campaign_id=%s order by id", (CAMPAIGN_ID,))
    prize_ids = ids["prize"]
    ids["inventory_item"] = _select_ids(conn, f"""select i.id from {SCHEMA}.inventory_item i
        join {SCHEMA}.prize p on p.id=i.prize_id where p.campaign_id=%s order by i.id""", (CAMPAIGN_ID,))
    inventory_ids = ids["inventory_item"]
    ids["game_session"] = _select_ids(conn, f"select id from {SCHEMA}.game_session where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["draw"] = _select_ids(conn, f"select id from {SCHEMA}.draw where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["claim"] = _select_ids(conn, f"select id from {SCHEMA}.claim where campaign_id=%s order by id", (CAMPAIGN_ID,))
    claim_ids = ids["claim"]
    ids["ranking_snapshot"] = _select_ids(conn, f"select id from {SCHEMA}.ranking_snapshot where campaign_id=%s order by id", (CAMPAIGN_ID,))
    snapshot_ids = ids["ranking_snapshot"]

    def by_participant(table, id_expr="id"):
        if not participant_ids:
            return []
        return _select_ids(conn, f"select {id_expr} id from {SCHEMA}.{table} where participant_id=any(%s) order by 1", (participant_ids,))

    ids["ticket_ledger"] = by_participant("ticket_ledger")
    ids["best_score"] = by_participant("best_score", "participant_id")
    ids["versioned_best_score"] = _select_ids(conn, f"""select participant_id||'|'||game_version id
        from {SCHEMA}.versioned_best_score where participant_id=any(%s) order by 1""", (participant_ids,)) if participant_ids else []
    ids["ranking_contact"] = by_participant("ranking_contact", "participant_id")
    ids["ranking_contact_version"] = _select_ids(conn, f"""select participant_id||'|'||game_version id
        from {SCHEMA}.ranking_contact_version where participant_id=any(%s) order by 1""", (participant_ids,)) if participant_ids else []
    ids["invitation_visit"] = _select_ids(conn, f"select id from {SCHEMA}.invitation_visit where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["invitation_reward"] = _select_ids(conn, f"select id from {SCHEMA}.invitation_reward where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["kakao_share_intent"] = _select_ids(conn, f"select id from {SCHEMA}.kakao_share_intent where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["draw_credit_ledger"] = _select_ids(conn, f"select id from {SCHEMA}.draw_credit_ledger where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["draw_pool_slot"] = _select_ids(conn, f"select id from {SCHEMA}.draw_pool_slot where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["ranking_award"] = _select_ids(conn, f"select campaign_id||'|'||rank id from {SCHEMA}.ranking_award where campaign_id=%s order by rank", (CAMPAIGN_ID,))
    ids["ranking_snapshot_entry"] = _select_ids(conn, f"""select snapshot_id||'|'||participant_id id
        from {SCHEMA}.ranking_snapshot_entry where snapshot_id=any(%s) order by 1""", (snapshot_ids,)) if snapshot_ids else []
    ids["claim_contact"] = _select_ids(conn, f"select claim_id id from {SCHEMA}.claim_contact where claim_id=any(%s) order by claim_id", (claim_ids,)) if claim_ids else []
    ids["claim_contact_draft"] = _select_ids(conn, f"select claim_id id from {SCHEMA}.claim_contact_draft where claim_id=any(%s) order by claim_id", (claim_ids,)) if claim_ids else []
    ids["inventory_history"] = _select_ids(conn, f"select id from {SCHEMA}.inventory_history where inventory_item_id=any(%s) order by id", (inventory_ids,)) if inventory_ids else []
    ids["analytics_event"] = _select_ids(conn, f"select id from {SCHEMA}.analytics_event where campaign_id=%s order by id", (CAMPAIGN_ID,))
    ids["observation"] = _select_ids(conn, f"""select id from {SCHEMA}.observation
        where participant_id=any(%s) or (participant_id is null and campaign_code=%s
          and environment=%s and synthetic) order by id""",
        (participant_ids, CAMPAIGN_ID, environment)) if participant_ids else _select_ids(
            conn, f"""select id from {SCHEMA}.observation where participant_id is null
              and campaign_code=%s and environment=%s and synthetic order by id""",
            (CAMPAIGN_ID, environment))
    observation_ids = ids["observation"]
    ids["bootstrap"] = _select_ids(conn, f"""select token_hash id from {SCHEMA}.bootstrap
        where observation_id=any(%s) or participant_id=any(%s) order by token_hash""",
        (observation_ids, participant_ids)) if observation_ids or participant_ids else []
    ids["idempotency_request"] = _select_ids(conn, f"""select actor_key||'|'||route||'|'||idempotency_key id
        from {SCHEMA}.idempotency_request
        where actor_key=any(%s) or response_body#>>'{{participant,id}}'=any(%s) order by 1""",
        (ids["participant_token_hash"], participant_ids)) if participant_ids else []
    ids["rate_limit_bucket"] = _select_ids(conn, f"""select bucket_key id from {SCHEMA}.rate_limit_bucket
        where exists (select 1 from unnest(%s::text[]) token where bucket_key like 'route:%%:'||token) order by bucket_key""",
        (ids["participant_token_hash"],)) if ids["participant_token_hash"] else []

    audit_clauses = []
    audit_params = []
    for target_type, target_ids in (
        ("campaign", [CAMPAIGN_ID]),
        ("participant", participant_ids),
        ("game_session", ids["game_session"]),
        ("draw", ids["draw"]),
        ("claim", claim_ids),
        ("ranking_snapshot", snapshot_ids),
        ("ranking_snapshot_candidate", [
            f"{snapshot_id}:{participant_id}"
            for snapshot_id in snapshot_ids for participant_id in participant_ids
        ]),
    ):
        if target_ids:
            audit_clauses.append("(target_type=%s and target_id=any(%s))")
            audit_params.extend((target_type, target_ids))
    ids["admin_audit"] = _select_ids(
        conn, f"select id from {SCHEMA}.admin_audit where {' or '.join(audit_clauses)} order by id",
        tuple(audit_params),
    ) if audit_clauses else []

    _reject_mixed_campaign_references(conn, participant_ids, prize_ids, snapshot_ids)
    return ids


def _reject_mixed_campaign_references(conn, participant_ids, prize_ids, snapshot_ids):
    if participant_ids:
        checks = (
            ("game_session", "participant_id=any(%s) and campaign_id<>%s"),
            ("invitation_visit", "(inviter_id=any(%s) or visitor_id=any(%s)) and campaign_id<>%s"),
            ("invitation_reward", "(inviter_id=any(%s) or visitor_id=any(%s)) and campaign_id<>%s"),
            ("draw", "participant_id=any(%s) and campaign_id<>%s"),
            ("claim", "participant_id=any(%s) and campaign_id<>%s"),
            ("analytics_event", "participant_id=any(%s) and campaign_id<>%s"),
            ("kakao_share_intent", "participant_id=any(%s) and campaign_id<>%s"),
            ("draw_credit_ledger", "participant_id=any(%s) and campaign_id<>%s"),
        )
        for table, where in checks:
            params = (participant_ids, participant_ids, CAMPAIGN_ID) if " or " in where else (participant_ids, CAMPAIGN_ID)
            if conn.execute(f"select 1 from {SCHEMA}.{table} where {where} limit 1", params).fetchone():
                raise BetaResetError("BETA_RESET_CROSS_CAMPAIGN_REFERENCE")
        if conn.execute(f"""select 1 from {SCHEMA}.ranking_snapshot_entry e
            join {SCHEMA}.participant p on p.id=e.participant_id
            join {SCHEMA}.ranking_snapshot s on s.id=e.snapshot_id
            where e.participant_id=any(%s) and s.campaign_id<>%s limit 1""",
            (participant_ids, CAMPAIGN_ID)).fetchone():
            raise BetaResetError("BETA_RESET_CROSS_CAMPAIGN_REFERENCE")
    if snapshot_ids and conn.execute(f"""select 1 from {SCHEMA}.ranking_snapshot_entry e
        join {SCHEMA}.participant p on p.id=e.participant_id
        where e.snapshot_id=any(%s) and p.campaign_id<>%s limit 1""",
        (snapshot_ids, CAMPAIGN_ID)).fetchone():
        raise BetaResetError("BETA_RESET_CROSS_CAMPAIGN_REFERENCE")
    if prize_ids:
        for table in ("draw", "draw_pool_slot", "ranking_award"):
            if conn.execute(f"select 1 from {SCHEMA}.{table} where prize_id=any(%s) and campaign_id<>%s limit 1",
                            (prize_ids, CAMPAIGN_ID)).fetchone():
                raise BetaResetError("BETA_RESET_CROSS_CAMPAIGN_REFERENCE")


def build_plan(conn, environment: str, now: dt.datetime | None = None) -> dict:
    now = now or dt.datetime.now(dt.timezone.utc)
    # Acquiring and releasing these locks after DML revocation drains transactions
    # that authenticated before quarantine. New app-role writers cannot start.
    with conn.transaction():
        conn.execute("set local statement_timeout='20s'; set local lock_timeout='1500ms'")
        for table in QUARANTINE_TABLES:
            conn.execute(f"lock table {SCHEMA}.{table} in access exclusive mode")
        ids = _scope(conn, environment)
    tables = _scope_stats(ids)
    plan = {
        "version": PLAN_VERSION,
        "created_at": _utc(now),
        "expires_at": _utc(now + PLAN_MAX_AGE),
        "target": {"environment": environment, "project_ref": "local" if environment == "test" else PROJECT_REF,
                   "schema": SCHEMA, "campaign_id": CAMPAIGN_ID},
        "preconditions": {"campaign_frozen": True, "ingress_disabled_required_for_apply": True,
                          "exclusive_table_locks_required": True},
        "tables": tables,
        "scope_sha256": _scope_token(tables),
        "preserved": ["schema_version", "environment_guard", "campaign", "admin_member", "database schema", "unrelated campaigns"],
    }
    plan["sha256"] = _plan_digest(plan)
    return plan


def _validate_plan(plan: dict, now: dt.datetime | None = None) -> dict:
    if plan.get("version") != PLAN_VERSION or plan.get("sha256") != _plan_digest(plan):
        raise BetaResetError("BETA_RESET_PLAN_INVALID")
    try:
        created = dt.datetime.fromisoformat(plan["created_at"])
        expiry = dt.datetime.fromisoformat(plan["expires_at"])
    except (KeyError, TypeError, ValueError) as error:
        raise BetaResetError("BETA_RESET_PLAN_INVALID") from error
    now = now or dt.datetime.now(dt.timezone.utc)
    if (created.tzinfo is None or expiry.tzinfo is None or expiry <= created
            or expiry - created > PLAN_MAX_AGE or created > now + dt.timedelta(minutes=1)):
        raise BetaResetError("BETA_RESET_PLAN_INVALID")
    if now > expiry:
        raise BetaResetError("BETA_RESET_PLAN_EXPIRED")
    return plan


def _load_plan(path: Path) -> dict:
    try:
        plan = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise BetaResetError("BETA_RESET_PLAN_INVALID") from error
    return _validate_plan(plan)


def _delete_any(conn, table, column, values):
    if values:
        conn.execute(f"delete from {SCHEMA}.{table} where {column}=any(%s)", (values,))


def _apply_deletes(conn, ids):
    _delete_any(conn, "claim_contact_draft", "claim_id", ids["claim"])
    _delete_any(conn, "claim_contact", "claim_id", ids["claim"])
    _delete_any(conn, "kakao_share_intent", "id", ids["kakao_share_intent"])
    conn.execute(f"delete from {SCHEMA}.ranking_award where campaign_id=%s", (CAMPAIGN_ID,))
    _delete_any(conn, "admin_audit", "id", ids["admin_audit"])
    _delete_any(conn, "ranking_snapshot_entry", "snapshot_id", ids["ranking_snapshot"])
    _delete_any(conn, "ranking_snapshot", "id", ids["ranking_snapshot"])
    _delete_any(conn, "claim", "id", ids["claim"])
    conn.execute(f"delete from {SCHEMA}.draw_pool_slot where campaign_id=%s", (CAMPAIGN_ID,))
    _delete_any(conn, "draw", "id", ids["draw"])
    conn.execute(f"delete from {SCHEMA}.draw_credit_ledger where campaign_id=%s", (CAMPAIGN_ID,))
    _delete_any(conn, "inventory_history", "inventory_item_id", ids["inventory_item"])
    _delete_any(conn, "inventory_item", "id", ids["inventory_item"])
    _delete_any(conn, "prize", "id", ids["prize"])
    for table in ("best_score", "versioned_best_score", "ranking_contact_version", "ranking_contact"):
        _delete_any(conn, table, "participant_id", ids["participant"])
    conn.execute(f"delete from {SCHEMA}.analytics_event where campaign_id=%s", (CAMPAIGN_ID,))
    conn.execute(f"delete from {SCHEMA}.invitation_reward where campaign_id=%s", (CAMPAIGN_ID,))
    conn.execute(f"delete from {SCHEMA}.invitation_visit where campaign_id=%s", (CAMPAIGN_ID,))
    _delete_any(conn, "ticket_ledger", "participant_id", ids["participant"])
    _delete_any(conn, "bootstrap", "token_hash", ids["bootstrap"])
    _delete_any(conn, "observation", "id", ids["observation"])
    if ids["idempotency_request"]:
        conn.execute(f"""delete from {SCHEMA}.idempotency_request
            where actor_key||'|'||route||'|'||idempotency_key=any(%s)""", (ids["idempotency_request"],))
    _delete_any(conn, "rate_limit_bucket", "bucket_key", ids["rate_limit_bucket"])
    _delete_any(conn, "game_session", "id", ids["game_session"])
    _delete_any(conn, "participant", "id", ids["participant"])


def apply_plan(conn, environment: str, plan: dict, ingress_confirmation: str) -> dict:
    _validate_plan(plan)
    expected_target = {"environment": environment, "project_ref": "local" if environment == "test" else PROJECT_REF,
                       "schema": SCHEMA, "campaign_id": CAMPAIGN_ID}
    if plan.get("target") != expected_target:
        raise BetaResetError("BETA_RESET_PLAN_TARGET_MISMATCH")
    if ingress_confirmation != INGRESS_CONFIRMATION:
        raise BetaResetError("BETA_RESET_INGRESS_CONFIRMATION_REQUIRED")
    with conn.transaction():
        conn.execute("set local statement_timeout='20s'; set local lock_timeout='1500ms'")
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", (f"beta-reset:{PROJECT_REF}:{CAMPAIGN_ID}",))
        for table in LOCK_TABLES:
            conn.execute(f"lock table {SCHEMA}.{table} in access exclusive mode nowait")
        guard_before = conn.execute(f"select * from {SCHEMA}.environment_guard where singleton").fetchone()
        campaign_before = conn.execute(f"select * from {SCHEMA}.campaign where id=%s", (CAMPAIGN_ID,)).fetchone()
        ids = _scope(conn, environment, lock=True)
        now = dt.datetime.now(dt.timezone.utc)
        actual = build_plan(conn, environment, now=dt.datetime.fromisoformat(plan["created_at"]))
        if actual != plan:
            raise BetaResetError("BETA_RESET_PLAN_STALE")
        _apply_deletes(conn, ids)
        guard_after = conn.execute(f"select * from {SCHEMA}.environment_guard where singleton").fetchone()
        campaign_after = conn.execute(f"select * from {SCHEMA}.campaign where id=%s", (CAMPAIGN_ID,)).fetchone()
        if not guard_after or dict(guard_after) != dict(guard_before) or not campaign_after or dict(campaign_after) != dict(campaign_before):
            raise BetaResetError("BETA_RESET_POSTCONDITION_FAILED")
        return {"applied": True, "applied_at": _utc(now), "plan_sha256": plan["sha256"],
                "deleted": {name: spec["count"] for name, spec in plan["tables"].items()
                            if name not in NON_DELETED_SCOPE_KEYS}}


def _guard_sql(environment: str, project_ref: str) -> str:
    test_seed = " and test_seed" if environment == "preview" else ""
    return (f"singleton and environment='{environment}' and project_ref='{project_ref}' "
            f"and schema_name='{SCHEMA}' and synthetic_only{test_seed} and campaign_id='{CAMPAIGN_ID}'")


def _schema_incomplete_sql() -> str:
    required = ",".join(f"('{version}')" for version in REQUIRED_SCHEMA_VERSIONS)
    return (f"exists(select 1 from (values {required}) required(version) "
            f"where not exists(select 1 from {SCHEMA}.schema_version s where s.version=required.version))")


def quarantine_sql(environment: str = "preview", project_ref: str = PROJECT_REF) -> str:
    """Return reviewable SQL suitable for a privileged SQL console/MCP call."""
    _mcp_target(environment, project_ref)
    tables = ",".join(f"{SCHEMA}.{table}" for table in QUARANTINE_TABLES)
    guard = _guard_sql(environment, project_ref)
    return f"""begin;
set local statement_timeout='20s';
set local lock_timeout='1500ms';
select pg_advisory_xact_lock(hashtext('beta-quarantine:{PROJECT_REF}:{CAMPAIGN_ID}'));
do $$
declare c record;
begin
  if not exists(select 1 from {SCHEMA}.environment_guard where {guard}) then
    raise exception 'BETA_RESET_GUARD_MISMATCH';
  end if;
  if {_schema_incomplete_sql()} then raise exception 'BETA_RESET_SCHEMA_INCOMPLETE'; end if;
  select id,status,is_test,real_prizes_enabled into c
  from {SCHEMA}.campaign where id='{CAMPAIGN_ID}' for update;
  if c.id is null or c.is_test is not true or c.real_prizes_enabled is not false then
    raise exception 'BETA_RESET_CAMPAIGN_NOT_SYNTHETIC';
  end if;
  update {SCHEMA}.campaign set status='PAUSED',version=version+1,updated_at=clock_timestamp()
  where id='{CAMPAIGN_ID}' and status<>'PAUSED';
end $$;
revoke insert,update,delete on {tables} from dino_dev_app;
revoke update(status,version,updated_at) on {SCHEMA}.campaign from dino_dev_app;
commit;
begin;
set local statement_timeout='20s';
set local lock_timeout='1500ms';
select pg_advisory_xact_lock(hashtext('beta-quarantine:{PROJECT_REF}:{CAMPAIGN_ID}'));
lock table {tables} in access exclusive mode;
do $$
declare writable_count integer;
begin
  if not exists(select 1 from {SCHEMA}.environment_guard where {guard}) then
    raise exception 'BETA_RESET_GUARD_MISMATCH';
  end if;
  if {_schema_incomplete_sql()} then raise exception 'BETA_RESET_SCHEMA_INCOMPLETE'; end if;
  if not exists(select 1 from {SCHEMA}.campaign where id='{CAMPAIGN_ID}'
      and status in ('PAUSED','ENDED') and is_test and not real_prizes_enabled) then
    raise exception 'BETA_RESET_CAMPAIGN_NOT_FROZEN';
  end if;
  select count(*) into writable_count from unnest(array{list(QUARANTINE_TABLES)!r}::text[]) t(table_name)
  where has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'DELETE')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE');
  if writable_count<>0 then raise exception 'BETA_RESET_DATABASE_QUARANTINE_REQUIRED'; end if;
end $$;
commit;
"""


def _mcp_target(environment: str, project_ref: str):
    if environment not in {"preview", "test"}:
        raise BetaResetError("BETA_RESET_PREVIEW_ONLY")
    expected = PROJECT_REF if environment == "preview" else "local"
    if project_ref != expected:
        raise BetaResetError("BETA_RESET_APPROVED_PROJECT_REQUIRED")


def _mcp_scope_union(environment: str = "preview") -> str:
    cid = CAMPAIGN_ID
    env = environment
    parts = [
        f"select 'campaign' kind,id::text from {SCHEMA}.campaign where id='{cid}'",
        f"select 'participant',id::text from {SCHEMA}.participant where campaign_id='{cid}'",
        f"select 'participant_token_hash',token_hash::text from {SCHEMA}.participant where campaign_id='{cid}'",
        f"select 'ticket_ledger',id::text from {SCHEMA}.ticket_ledger where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'observation',id::text from {SCHEMA}.observation where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}') or (participant_id is null and campaign_code='{cid}' and environment='{env}' and synthetic)",
        f"select 'bootstrap',token_hash::text from {SCHEMA}.bootstrap where observation_id in (select id from {SCHEMA}.observation where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}') or (participant_id is null and campaign_code='{cid}' and environment='{env}' and synthetic)) or participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'invitation_visit',id::text from {SCHEMA}.invitation_visit where campaign_id='{cid}'",
        f"select 'invitation_reward',id::text from {SCHEMA}.invitation_reward where campaign_id='{cid}'",
        f"select 'game_session',id::text from {SCHEMA}.game_session where campaign_id='{cid}'",
        f"select 'best_score',participant_id::text from {SCHEMA}.best_score where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'versioned_best_score',participant_id||'|'||game_version from {SCHEMA}.versioned_best_score where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'ranking_contact',participant_id::text from {SCHEMA}.ranking_contact where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'ranking_contact_version',participant_id||'|'||game_version from {SCHEMA}.ranking_contact_version where participant_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'prize',id::text from {SCHEMA}.prize where campaign_id='{cid}'",
        f"select 'inventory_item',i.id::text from {SCHEMA}.inventory_item i join {SCHEMA}.prize p on p.id=i.prize_id where p.campaign_id='{cid}'",
        f"select 'draw',id::text from {SCHEMA}.draw where campaign_id='{cid}'",
        f"select 'inventory_history',h.id::text from {SCHEMA}.inventory_history h join {SCHEMA}.inventory_item i on i.id=h.inventory_item_id join {SCHEMA}.prize p on p.id=i.prize_id where p.campaign_id='{cid}'",
        f"select 'claim',id::text from {SCHEMA}.claim where campaign_id='{cid}'",
        f"select 'claim_contact',claim_id::text from {SCHEMA}.claim_contact where claim_id in (select id from {SCHEMA}.claim where campaign_id='{cid}')",
        f"select 'claim_contact_draft',claim_id::text from {SCHEMA}.claim_contact_draft where claim_id in (select id from {SCHEMA}.claim where campaign_id='{cid}')",
        f"select 'analytics_event',id::text from {SCHEMA}.analytics_event where campaign_id='{cid}'",
        f"select 'idempotency_request',actor_key||'|'||route||'|'||idempotency_key from {SCHEMA}.idempotency_request where actor_key in (select token_hash from {SCHEMA}.participant where campaign_id='{cid}') or response_body#>>'{{participant,id}}' in (select id from {SCHEMA}.participant where campaign_id='{cid}')",
        f"select 'ranking_snapshot',id::text from {SCHEMA}.ranking_snapshot where campaign_id='{cid}'",
        f"select 'ranking_snapshot_entry',snapshot_id||'|'||participant_id from {SCHEMA}.ranking_snapshot_entry where snapshot_id in (select id from {SCHEMA}.ranking_snapshot where campaign_id='{cid}')",
        f"select 'ranking_award',campaign_id||'|'||rank::text from {SCHEMA}.ranking_award where campaign_id='{cid}'",
        f"select 'admin_audit',id::text from {SCHEMA}.admin_audit where (target_type='campaign' and target_id='{cid}') or (target_type='participant' and target_id in (select id from {SCHEMA}.participant where campaign_id='{cid}')) or (target_type='game_session' and target_id in (select id from {SCHEMA}.game_session where campaign_id='{cid}')) or (target_type='draw' and target_id in (select id from {SCHEMA}.draw where campaign_id='{cid}')) or (target_type='claim' and target_id in (select id from {SCHEMA}.claim where campaign_id='{cid}')) or (target_type='ranking_snapshot' and target_id in (select id from {SCHEMA}.ranking_snapshot where campaign_id='{cid}')) or (target_type='ranking_snapshot_candidate' and target_id in (select s.id||':'||p.id from {SCHEMA}.ranking_snapshot s cross join {SCHEMA}.participant p where s.campaign_id='{cid}' and p.campaign_id='{cid}'))",
        f"select 'rate_limit_bucket',bucket_key::text from {SCHEMA}.rate_limit_bucket where exists(select 1 from {SCHEMA}.participant p where p.campaign_id='{cid}' and bucket_key like 'route:%:'||p.token_hash)",
        f"select 'kakao_share_intent',id::text from {SCHEMA}.kakao_share_intent where campaign_id='{cid}'",
        f"select 'draw_credit_ledger',id::text from {SCHEMA}.draw_credit_ledger where campaign_id='{cid}'",
        f"select 'draw_pool_slot',id::text from {SCHEMA}.draw_pool_slot where campaign_id='{cid}'",
    ]
    return "\nunion all\n".join(parts)


def _mcp_stats_cte(environment: str = "preview") -> str:
    scope_union = _mcp_scope_union(environment)
    kinds = sorted({line.split("'", 2)[1] for line in scope_union.splitlines() if line.startswith("select '")})
    values = ",".join(f"('{kind}')" for kind in kinds)
    return f"""scope(kind,id) as (
{scope_union}
), kinds(kind) as (values {values}), grouped as (
  select k.kind,count(s.id)::bigint row_count,
    encode(sha256(convert_to(coalesce(string_agg(octet_length(s.id)::text||':'||s.id,'|' order by s.id),''),'UTF8')),'hex') id_sha256
  from kinds k left join scope s on s.kind=k.kind group by k.kind
), stats as (
  select jsonb_object_agg(kind,jsonb_build_object('count',row_count,'id_sha256',id_sha256) order by kind) value,
    encode(sha256(convert_to(string_agg(kind||':'||row_count::text||':'||id_sha256,E'\n' order by kind),'UTF8')),'hex') plan_token
  from grouped
)"""


def mcp_plan_sql(environment: str = "preview", project_ref: str = PROJECT_REF) -> str:
    """Read-only SQL that produces the token consumed by mcp_apply_sql()."""
    _mcp_target(environment, project_ref)
    tables = list(QUARANTINE_TABLES)
    locks = ",".join(f"{SCHEMA}.{table}" for table in QUARANTINE_TABLES)
    guard = _guard_sql(environment, project_ref)
    return f"""begin;
set local statement_timeout='20s';
set local lock_timeout='1500ms';
lock table {locks} in access exclusive mode;
commit;
with {_mcp_stats_cte(environment)},
guard_check as (
  select count(*)=1 ok from {SCHEMA}.environment_guard
  where {_guard_sql(environment, project_ref)}
), campaign_check as (
  select count(*)=1 ok from {SCHEMA}.campaign where id='{CAMPAIGN_ID}'
    and status in ('PAUSED','ENDED') and is_test and not real_prizes_enabled
), writable as (
  select table_name from unnest(array{tables!r}::text[]) table_list(table_name)
  where has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'DELETE')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE')
)
select '{project_ref}' project_ref,'{SCHEMA}' schema_name,'{CAMPAIGN_ID}' campaign_id,
       (select ok from guard_check) guard_ok,(select ok from campaign_check) campaign_frozen,
       not {_schema_incomplete_sql()} schema_complete,
       not exists(select 1 from writable) database_quarantined,
       value counts_and_digests,plan_token
from stats;
"""


def _mcp_mixed_reference_sql() -> str:
    cid = CAMPAIGN_ID
    participant = f"select id from {SCHEMA}.participant where campaign_id='{cid}'"
    prize = f"select id from {SCHEMA}.prize where campaign_id='{cid}'"
    checks = [
        f"select 1 from {SCHEMA}.game_session where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.invitation_visit where (inviter_id in ({participant}) or visitor_id in ({participant})) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.invitation_reward where (inviter_id in ({participant}) or visitor_id in ({participant})) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.draw where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.claim where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.analytics_event where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.kakao_share_intent where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.draw_credit_ledger where participant_id in ({participant}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.draw where prize_id in ({prize}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.draw_pool_slot where prize_id in ({prize}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.ranking_award where prize_id in ({prize}) and campaign_id<>'{cid}'",
        f"select 1 from {SCHEMA}.ranking_snapshot_entry e join {SCHEMA}.ranking_snapshot s on s.id=e.snapshot_id join {SCHEMA}.participant p on p.id=e.participant_id where (s.campaign_id='{cid}' and p.campaign_id<>'{cid}') or (p.campaign_id='{cid}' and s.campaign_id<>'{cid}')",
    ]
    return "\nunion all\n".join(checks)


def mcp_apply_sql(expected_plan_token: str, environment: str = "preview", project_ref: str = PROJECT_REF) -> str:
    """Generate one transaction for a privileged Supabase SQL/MCP execution."""
    _mcp_target(environment, project_ref)
    if not re.fullmatch(r"[0-9a-f]{64}", expected_plan_token or ""):
        raise BetaResetError("BETA_RESET_MCP_PLAN_TOKEN_INVALID")
    locks = ",".join(f"{SCHEMA}.{table}" for table in LOCK_TABLES)
    quarantine_tables = list(QUARANTINE_TABLES)
    cid = CAMPAIGN_ID
    participant = f"select id from {SCHEMA}.participant where campaign_id='{cid}'"
    prize = f"select id from {SCHEMA}.prize where campaign_id='{cid}'"
    inventory = f"select i.id from {SCHEMA}.inventory_item i join {SCHEMA}.prize p on p.id=i.prize_id where p.campaign_id='{cid}'"
    claim = f"select id from {SCHEMA}.claim where campaign_id='{cid}'"
    snapshot = f"select id from {SCHEMA}.ranking_snapshot where campaign_id='{cid}'"
    observation = f"select id from {SCHEMA}.observation where participant_id in ({participant}) or (participant_id is null and campaign_code='{cid}' and environment='{environment}' and synthetic)"
    deletes = [
        f"delete from {SCHEMA}.claim_contact_draft where claim_id in ({claim});",
        f"delete from {SCHEMA}.claim_contact where claim_id in ({claim});",
        f"delete from {SCHEMA}.kakao_share_intent where campaign_id='{cid}';",
        f"delete from {SCHEMA}.ranking_award where campaign_id='{cid}';",
        f"delete from {SCHEMA}.admin_audit where (target_type='campaign' and target_id='{cid}') or (target_type='participant' and target_id in ({participant})) or (target_type='game_session' and target_id in (select id from {SCHEMA}.game_session where campaign_id='{cid}')) or (target_type='draw' and target_id in (select id from {SCHEMA}.draw where campaign_id='{cid}')) or (target_type='claim' and target_id in ({claim})) or (target_type='ranking_snapshot' and target_id in ({snapshot})) or (target_type='ranking_snapshot_candidate' and target_id in (select s.id||':'||p.id from {SCHEMA}.ranking_snapshot s cross join {SCHEMA}.participant p where s.campaign_id='{cid}' and p.campaign_id='{cid}'));",
        f"delete from {SCHEMA}.ranking_snapshot_entry where snapshot_id in ({snapshot});",
        f"delete from {SCHEMA}.ranking_snapshot where campaign_id='{cid}';",
        f"delete from {SCHEMA}.claim where campaign_id='{cid}';",
        f"delete from {SCHEMA}.draw_pool_slot where campaign_id='{cid}';",
        f"delete from {SCHEMA}.draw where campaign_id='{cid}';",
        f"delete from {SCHEMA}.draw_credit_ledger where campaign_id='{cid}';",
        f"delete from {SCHEMA}.inventory_history where inventory_item_id in ({inventory});",
        f"delete from {SCHEMA}.inventory_item where id in ({inventory});",
        f"delete from {SCHEMA}.prize where campaign_id='{cid}';",
        f"delete from {SCHEMA}.best_score where participant_id in ({participant});",
        f"delete from {SCHEMA}.versioned_best_score where participant_id in ({participant});",
        f"delete from {SCHEMA}.ranking_contact_version where participant_id in ({participant});",
        f"delete from {SCHEMA}.ranking_contact where participant_id in ({participant});",
        f"delete from {SCHEMA}.analytics_event where campaign_id='{cid}';",
        f"delete from {SCHEMA}.invitation_reward where campaign_id='{cid}';",
        f"delete from {SCHEMA}.invitation_visit where campaign_id='{cid}';",
        f"delete from {SCHEMA}.ticket_ledger where participant_id in ({participant});",
        f"delete from {SCHEMA}.bootstrap where observation_id in ({observation}) or participant_id in ({participant});",
        f"delete from {SCHEMA}.observation where id in ({observation});",
        f"delete from {SCHEMA}.idempotency_request where actor_key in (select token_hash from {SCHEMA}.participant where campaign_id='{cid}') or response_body#>>'{{participant,id}}' in ({participant});",
        f"delete from {SCHEMA}.rate_limit_bucket where exists(select 1 from {SCHEMA}.participant p where p.campaign_id='{cid}' and bucket_key like 'route:%:'||p.token_hash);",
        f"delete from {SCHEMA}.game_session where campaign_id='{cid}';",
        f"delete from {SCHEMA}.participant where campaign_id='{cid}';",
    ]
    return f"""begin;
set local statement_timeout='20s';
set local lock_timeout='1500ms';
select pg_advisory_xact_lock(hashtext('beta-reset:{project_ref}:{cid}'));
lock table {locks} in access exclusive mode nowait;
create temp table beta_reset_preserved on commit drop as
select (select to_jsonb(g) from {SCHEMA}.environment_guard g where singleton) guard_row,
       (select to_jsonb(c) from {SCHEMA}.campaign c where id='{cid}') campaign_row;
do $$
declare current_token text; writable_count integer; mixed_count integer;
begin
  if not exists(select 1 from {SCHEMA}.environment_guard where {_guard_sql(environment, project_ref)}) then
    raise exception 'BETA_RESET_GUARD_MISMATCH';
  end if;
  if {_schema_incomplete_sql()} then raise exception 'BETA_RESET_SCHEMA_INCOMPLETE'; end if;
  if not exists(select 1 from {SCHEMA}.campaign where id='{cid}' and status in ('PAUSED','ENDED')
    and is_test and not real_prizes_enabled) then raise exception 'BETA_RESET_CAMPAIGN_NOT_FROZEN'; end if;
  select count(*) into writable_count from unnest(array{quarantine_tables!r}::text[]) table_list(table_name)
  where has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE')
     or has_table_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'DELETE')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'INSERT')
     or has_any_column_privilege('dino_dev_app',format('%I.%I','{SCHEMA}',table_name),'UPDATE');
  if writable_count<>0 then raise exception 'BETA_RESET_DATABASE_QUARANTINE_REQUIRED'; end if;
  select count(*) into mixed_count from ({_mcp_mixed_reference_sql()}) q;
  if mixed_count<>0 then raise exception 'BETA_RESET_CROSS_CAMPAIGN_REFERENCE'; end if;
  with {_mcp_stats_cte(environment)} select plan_token into current_token from stats;
  if current_token<>'{expected_plan_token}' then raise exception 'BETA_RESET_PLAN_STALE'; end if;
end $$;
{chr(10).join(deletes)}
do $$
begin
  if exists(select 1 from {SCHEMA}.participant where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.prize where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.game_session where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.draw where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.claim where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.analytics_event where campaign_id='{cid}')
    or exists(select 1 from {SCHEMA}.kakao_share_intent where campaign_id='{cid}') then
    raise exception 'BETA_RESET_POSTCONDITION_FAILED';
  end if;
  if (select to_jsonb(g) from {SCHEMA}.environment_guard g where singleton)<>
     (select guard_row from beta_reset_preserved)
     or (select to_jsonb(c) from {SCHEMA}.campaign c where id='{cid}')<>
        (select campaign_row from beta_reset_preserved) then
    raise exception 'BETA_RESET_PRESERVED_ROW_CHANGED';
  end if;
end $$;
commit;
"""


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=("preview", "test"), required=True)
    parser.add_argument("--dsn-env", default="DINO_BETA_RESET_DATABASE_URL")
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-output", type=Path)
    mode.add_argument("--apply-plan", type=Path)
    mode.add_argument("--print-quarantine-sql", action="store_true")
    mode.add_argument("--print-mcp-plan-sql", action="store_true")
    mode.add_argument("--print-mcp-apply-sql", metavar="PLAN_TOKEN")
    parser.add_argument("--confirm-ingress-disabled", default="")
    args = parser.parse_args()
    if args.print_quarantine_sql:
        print(quarantine_sql(args.environment, "local" if args.environment == "test" else PROJECT_REF), end="")
        return
    if args.print_mcp_plan_sql:
        print(mcp_plan_sql(), end="")
        return
    if args.print_mcp_apply_sql:
        if args.confirm_ingress_disabled != INGRESS_CONFIRMATION:
            raise BetaResetError("BETA_RESET_INGRESS_CONFIRMATION_REQUIRED")
        print(mcp_apply_sql(args.print_mcp_apply_sql), end="")
        return
    dsn = os.getenv(args.dsn_env, "")
    if not dsn:
        raise BetaResetError("BETA_RESET_DSN_REQUIRED")
    with connect(dsn, args.environment) as conn:
        if args.plan_output:
            plan = build_plan(conn, args.environment)
            args.plan_output.parent.mkdir(parents=True, exist_ok=True)
            args.plan_output.write_text(json.dumps(plan, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
            print(json.dumps({"applied": False, "plan": str(args.plan_output), "sha256": plan["sha256"],
                              "counts": {key: value["count"] for key, value in plan["tables"].items()}}, sort_keys=True))
        else:
            plan = _load_plan(args.apply_plan)
            result = apply_plan(conn, args.environment, plan, args.confirm_ingress_disabled)
            print(json.dumps(result, sort_keys=True))


if __name__ == "__main__":
    main()
