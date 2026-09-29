"""Review then erase claim contact data after its retention deadline.

Uses an existing privileged maintenance credential, never grants the web role
DELETE, and never prints personal fields or connection credentials.
"""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import re
import sys
from urllib.parse import urlsplit
import uuid

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
from config import REQUIRED_SCHEMA_VERSIONS

PROJECT = "igfrnexknwtiljdqjrbp"
SCHEMAS = {"test": "dino_dev", "preview": "dino_dev", "production": "dino_prod"}
# A daily operator run on day 29 leaves a day before the promised day-30 limit.
ELIGIBLE_DAYS = 29
PLAN_HOURS = 24
PLAN_VERSION = 2
FULFILLMENT_ACTION = "PRIZE_FULFILLMENT_COMPLETE"
TERMINAL_FULFILLMENT_STATUSES = {"PAID", "INELIGIBLE", "NO_RESPONSE"}


class RetentionError(ValueError):
    pass


def stamp(value):
    return value.astimezone(dt.timezone.utc).isoformat() if value else None


def digest(plan):
    payload = {key: value for key, value in plan.items() if key != "sha256"}
    return hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":")).encode()).hexdigest()


def connect(dsn, environment):
    parsed = urlsplit(dsn)
    if environment not in SCHEMAS or parsed.scheme not in {"postgres", "postgresql"}:
        raise RetentionError("RETENTION_TARGET_INVALID")
    if parsed.query or parsed.fragment:
        raise RetentionError("RETENTION_DSN_OPTIONS_FORBIDDEN")
    options = {"autocommit": True, "row_factory": dict_row, "connect_timeout": 5, "prepare_threshold": None}
    if environment == "test":
        if (parsed.hostname not in {"localhost", "127.0.0.1", "::1"} or parsed.port != 55433
                or not re.fullmatch(r"/dino_phase1_audit_[a-z0-9_]+", parsed.path)):
            raise RetentionError("RETENTION_ISOLATED_TEST_DB_REQUIRED")
    else:
        direct = parsed.hostname == f"db.{PROJECT}.supabase.co" and parsed.port == 5432 and parsed.username == "postgres"
        pooled = (bool(parsed.hostname) and parsed.hostname.endswith(".pooler.supabase.com")
                  and parsed.port in {5432, 6543} and parsed.username == f"postgres.{PROJECT}")
        if not (direct or pooled) or parsed.path != "/postgres":
            raise RetentionError("RETENTION_APPROVED_PROJECT_REQUIRED")
        options.update(sslmode="verify-full", sslrootcert=str(ROOT / "server/certs/supabase-ca-2021.crt"))
    return psycopg.connect(dsn, **options)


def scope(conn, environment, campaign_id, admin_user_id, lock=False):
    schema = SCHEMAS.get(environment)
    if schema is None or not re.fullmatch(r"[A-Za-z0-9_-]{3,100}", campaign_id or ""):
        raise RetentionError("RETENTION_SCOPE_INVALID")
    try:
        admin_user_id = str(uuid.UUID(str(admin_user_id)))
    except ValueError:
        raise RetentionError("RETENTION_ADMIN_INVALID") from None
    role = conn.execute("""select current_user as name, rolsuper or rolbypassrls as maintenance
        from pg_roles where rolname=current_user""").fetchone()
    if not role or not role["maintenance"] or role["name"] in {"dino_dev_app", "dino_prod_app"}:
        raise RetentionError("RETENTION_MAINTENANCE_ROLE_REQUIRED")
    guard = conn.execute(f"select * from {schema}.environment_guard where singleton"
        + (" for share" if lock else "")).fetchone()
    expected_project = "local" if environment == "test" else PROJECT
    if (not guard or guard["environment"] != environment or guard["project_ref"] != expected_project
            or guard["schema_name"] != schema or bool(guard["synthetic_only"]) != (environment != "production")):
        raise RetentionError("RETENTION_GUARD_MISMATCH")
    if environment == "production" and (guard["test_seed"] is not False
            or not re.fullmatch(r"[0-9a-f]{64}", str(guard.get("launch_manifest_sha256", "")))):
        raise RetentionError("RETENTION_PRODUCTION_GUARD_INVALID")
    versions = {row["version"] for row in conn.execute(f"select version from {schema}.schema_version")}
    if not set(REQUIRED_SCHEMA_VERSIONS).issubset(versions):
        raise RetentionError("RETENTION_SCHEMA_INCOMPLETE")
    if not conn.execute(f"select id from {schema}.campaign where id=%s" + (" for share" if lock else ""),
            (campaign_id,)).fetchone():
        raise RetentionError("RETENTION_CAMPAIGN_NOT_FOUND")
    # Old campaigns in the same guarded schema remain manageable after a new event starts.
    admin = conn.execute(f"""select auth_user_id from {schema}.admin_member
        where auth_user_id=%s and active and 'claims:write'=any(permissions)"""
        + (" for share" if lock else ""), (admin_user_id,)).fetchone()
    if not admin:
        raise RetentionError("RETENTION_ADMIN_NOT_AUTHORIZED")
    database = conn.execute("select current_database() as name").fetchone()["name"]
    return {"environment": environment, "schema": schema, "project_ref": expected_project,
            "campaign_id": campaign_id, "admin_user_id": admin_user_id, "database": database,
            "manifest_sha256": guard.get("launch_manifest_sha256")}


def claim_metadata(conn, schema, campaign_id, claim_id, lock=False):
    row = conn.execute(f"""select id, status, paid_at, version from {schema}.claim
        where id=%s and campaign_id=%s""" + (" for update" if lock else ""),
        (claim_id, campaign_id)).fetchone()
    if not row:
        raise RetentionError("RETENTION_CLAIM_CHANGED")
    contact = conn.execute(f"select created_at from {schema}.claim_contact where claim_id=%s"
        + (" for update" if lock else ""), (claim_id,)).fetchone()
    draft = conn.execute(f"select updated_at from {schema}.claim_contact_draft where claim_id=%s"
        + (" for update" if lock else ""), (claim_id,)).fetchone()
    return {"claim_id": row["id"], "status": row["status"], "paid_at": stamp(row["paid_at"]),
            "version": row["version"], "contact_created_at": stamp(contact["created_at"]) if contact else None,
            "draft_updated_at": stamp(draft["updated_at"]) if draft else None}


def fulfillment_marker(conn, schema, campaign_id):
    row = conn.execute(f"""select id,event_id,admin_user_id,after_value,created_at
        from {schema}.admin_audit where action=%s and target_type='campaign' and target_id=%s
        order by id""", (FULFILLMENT_ACTION, campaign_id)).fetchall()
    if len(row) > 1:
        raise RetentionError("RETENTION_FULFILLMENT_MARKER_AMBIGUOUS")
    if not row:
        return None
    item = row[0]
    reference = (item["after_value"] or {}).get("evidence_reference")
    if not isinstance(reference, str):
        raise RetentionError("RETENTION_FULFILLMENT_MARKER_INVALID")
    return {"audit_id": item["id"], "event_id": item["event_id"],
            "admin_user_id": str(item["admin_user_id"]), "completed_at": stamp(item["created_at"]),
            "evidence_reference": reference}


def _parse_deadline(value):
    if isinstance(value, dt.datetime):
        parsed = value
    elif isinstance(value, str):
        try:
            parsed = dt.datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
    else:
        return None
    return parsed if parsed.tzinfo is not None else None


def _campaign_deadlines(conn, schema, campaign, environment):
    closes_at = _parse_deadline(campaign.get("closes_at"))
    claim_cutoff = _parse_deadline((campaign.get("settings") or {}).get("claim_submission_cutoff"))
    if environment != "production":
        return closes_at, claim_cutoff
    columns = {row["column_name"] for row in conn.execute("""select column_name
        from information_schema.columns where table_schema=%s and table_name='environment_guard'
        and column_name in ('campaign_id','campaign_closes_at','claim_closes_at')""", (schema,))}
    if {"campaign_id", "campaign_closes_at", "claim_closes_at"}.issubset(columns):
        guard = conn.execute(f"""select campaign_id,campaign_closes_at,claim_closes_at
            from {schema}.environment_guard where singleton""").fetchone()
        # The singleton guard describes the current campaign. Historical campaigns
        # retain their own immutable deadline copy in campaign.settings.
        if guard and guard["campaign_id"] == campaign.get("id"):
            guard_closes = _parse_deadline(guard["campaign_closes_at"])
            guard_claim_cutoff = _parse_deadline(guard["claim_closes_at"])
            if closes_at != guard_closes or claim_cutoff != guard_claim_cutoff:
                raise RetentionError("RETENTION_FULFILLMENT_WINDOW_INVALID")
            return guard_closes, guard_claim_cutoff
    return closes_at, claim_cutoff


def validate_fulfillment_state(conn, target, now, lock=False):
    schema = target["schema"]
    campaign = conn.execute(f"select id,closes_at,settings from {schema}.campaign where id=%s"
        + (" for update" if lock else ""), (target["campaign_id"],)).fetchone()
    closes_at, claim_cutoff = _campaign_deadlines(conn, schema, campaign or {}, target["environment"])
    if not closes_at or not claim_cutoff or claim_cutoff <= closes_at:
        raise RetentionError("RETENTION_FULFILLMENT_WINDOW_INVALID")
    if now < closes_at or now < claim_cutoff:
        raise RetentionError("RETENTION_FULFILLMENT_TOO_EARLY")
    awards = conn.execute(f"""select rank,snapshot_id,participant_id,claim_id,prize_id,inventory_item_id,finalized_at
        from {schema}.ranking_award where campaign_id=%s order by rank"""
        + (" for update" if lock else ""), (target["campaign_id"],)).fetchall()
    if (target["environment"] == "production" and len(awards) != 3) or (awards and len(awards) != 3):
        raise RetentionError("RETENTION_RANKING_AWARD_CONFIG_INVALID")
    if awards:
        if [row["rank"] for row in awards] != [1, 2, 3]:
            raise RetentionError("RETENTION_RANKING_AWARD_CONFIG_INVALID")
        final = conn.execute(f"select id from {schema}.ranking_snapshot where campaign_id=%s and status='FINAL'"
            + (" for update" if lock else ""), (target["campaign_id"],)).fetchall()
        if len(final) != 1:
            raise RetentionError("RETENTION_RANKING_NOT_FINAL")
        final_id = final[0]["id"]
        for award in awards:
            if (award["snapshot_id"] != final_id or not award["participant_id"] or not award["claim_id"]
                    or not award["finalized_at"]):
                raise RetentionError("RETENTION_RANKING_AWARD_BINDING_INVALID")
            entry = conn.execute(f"""select rank from {schema}.ranking_snapshot_entry
                where snapshot_id=%s and participant_id=%s""" + (" for update" if lock else ""),
                (award["snapshot_id"], award["participant_id"])).fetchone()
            claim = conn.execute(f"""select campaign_id,participant_id,prize_id,inventory_item_id
                from {schema}.claim where id=%s""" + (" for update" if lock else ""),
                (award["claim_id"],)).fetchone()
            if (not entry or entry["rank"] != award["rank"] or not claim
                    or claim["campaign_id"] != target["campaign_id"]
                    or claim["participant_id"] != award["participant_id"]
                    or claim["prize_id"] != award["prize_id"]
                    or claim["inventory_item_id"] != award["inventory_item_id"]):
                raise RetentionError("RETENTION_RANKING_AWARD_BINDING_INVALID")
    allocated = conn.execute(f"""select id,status from {schema}.claim
        where campaign_id=%s and (prize_id is not null or inventory_item_id is not null) order by id"""
        + (" for update" if lock else ""), (target["campaign_id"],)).fetchall()
    unresolved = [row["id"] for row in allocated if row["status"] not in TERMINAL_FULFILLMENT_STATUSES]
    if unresolved:
        raise RetentionError("RETENTION_FULFILLMENT_UNRESOLVED_CLAIMS")
    return {"campaign_closes_at": stamp(closes_at), "claim_closes_at": stamp(claim_cutoff),
            "ranking_award_count": len(awards), "allocated_claim_count": len(allocated)}


def _evidence_reference(environment, value):
    prefix = "REF_" if environment == "production" else "TEST_REF_"
    if not isinstance(value, str) or not re.fullmatch(re.escape(prefix) + r"[A-Za-z0-9][A-Za-z0-9._:-]{3,119}", value):
        raise RetentionError("RETENTION_EVIDENCE_REFERENCE_INVALID")
    return value


def record_fulfillment_complete(conn, environment, campaign_id, admin_user_id, evidence_reference):
    target = scope(conn, environment, campaign_id, admin_user_id)
    reference = _evidence_reference(environment, evidence_reference)
    schema = target["schema"]
    with conn.transaction():
        conn.execute("set local statement_timeout='10s'; set local lock_timeout='2s'")
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", ("retention:"+schema+":"+campaign_id,))
        actual = scope(conn, environment, campaign_id, admin_user_id, lock=True)
        if actual != target:
            raise RetentionError("RETENTION_SCOPE_CHANGED")
        existing = fulfillment_marker(conn, schema, campaign_id)
        if existing:
            if existing["evidence_reference"] != reference:
                raise RetentionError("RETENTION_FULFILLMENT_ALREADY_RECORDED")
        now = conn.execute("select clock_timestamp() as now").fetchone()["now"]
        gate = validate_fulfillment_state(conn, target, now, lock=True)
        if existing:
            return {**existing, "replayed": True}
        event_id = "fulfillment_complete:" + hashlib.sha256(campaign_id.encode()).hexdigest()[:32]
        after = {"completed_at": stamp(now), "evidence_reference": reference, **gate}
        row = conn.execute(f"""insert into {schema}.admin_audit
            (admin_user_id,action,target_type,target_id,after_value,reason,event_id,created_at)
            values(%s,%s,'campaign',%s,%s::jsonb,%s,%s,%s) returning id""",
            (admin_user_id, FULFILLMENT_ACTION, campaign_id, json.dumps(after),
             "Operator confirmed all allocated prize claims reached a terminal fulfillment state", event_id, now)).fetchone()
        return {"audit_id": row["id"], "event_id": event_id, "admin_user_id": admin_user_id,
                "completed_at": stamp(now), "evidence_reference": reference, "replayed": False}


def build_plan(conn, environment, campaign_id, admin_user_id):
    target = scope(conn, environment, campaign_id, admin_user_id)
    schema = target["schema"]
    now = conn.execute("select clock_timestamp() as now").fetchone()["now"]
    marker = fulfillment_marker(conn, schema, campaign_id)
    marker_at = dt.datetime.fromisoformat(marker["completed_at"]) if marker else None
    marker_due = marker_at is not None and marker_at <= now-dt.timedelta(days=ELIGIBLE_DAYS)
    fulfillment_state_error = None
    nonpaid_eligible = marker_due
    if marker_due:
        try:
            validate_fulfillment_state(conn, target, now)
        except RetentionError as error:
            fulfillment_state_error = str(error)
            nonpaid_eligible = False
    candidates = conn.execute(f"""select c.id from {schema}.claim c where c.campaign_id=%s
        and ((c.status='PAID' and c.paid_at is not null and c.paid_at<=%s)
          or (c.status<>'PAID' and %s))
        and (exists(select 1 from {schema}.claim_contact p where p.claim_id=c.id)
          or exists(select 1 from {schema}.claim_contact_draft p where p.claim_id=c.id))
        order by c.id""", (campaign_id, now-dt.timedelta(days=ELIGIBLE_DAYS), nonpaid_eligible)).fetchall()
    rows = [claim_metadata(conn, schema, campaign_id, row["id"]) for row in candidates]
    summary = conn.execute(f"""select
        count(*) filter(where status='PAID' and paid_at is null)::int manual_issue_count,
        count(*) filter(where status='PAID' and paid_at>%s)::int paid_not_due_count,
        count(*) filter(where status<>'PAID')::int nonpaid_count
        from {schema}.claim c where campaign_id=%s
        and (exists(select 1 from {schema}.claim_contact p where p.claim_id=c.id)
          or exists(select 1 from {schema}.claim_contact_draft p where p.claim_id=c.id))""",
        (now-dt.timedelta(days=ELIGIBLE_DAYS), campaign_id)).fetchone()
    due_paid = sum(row["status"] == "PAID" for row in rows)
    due_nonpaid = len(rows)-due_paid
    plan = {"version": PLAN_VERSION, "scope": target, "reviewed_at": stamp(now),
            "eligible_after_days": ELIGIBLE_DAYS, "fulfillment_marker": marker, "rows": rows,
            "summary": {**dict(summary),
              "nonpaid_waiting_for_completion_count": summary["nonpaid_count"] if not marker else 0,
              "nonpaid_not_due_count": summary["nonpaid_count"] if marker and not marker_due else 0,
              "nonpaid_blocked_count": summary["nonpaid_count"] if marker_due and fulfillment_state_error else 0,
              "fulfillment_state_error": fulfillment_state_error,
              "due_paid_count": due_paid, "due_nonpaid_count": due_nonpaid, "due_count": len(rows),
              "overdue_count": sum(
                  (dt.datetime.fromisoformat(row["paid_at"]) if row["status"] == "PAID" else marker_at)
                  <= now-dt.timedelta(days=30) for row in rows)}}
    del plan["summary"]["nonpaid_count"]
    plan["sha256"] = digest(plan)
    return plan


def apply_plan(conn, plan, confirmation):
    if (plan.get("version") != PLAN_VERSION or plan.get("eligible_after_days") != ELIGIBLE_DAYS
            or not re.fullmatch(r"[0-9a-f]{64}", confirmation or "")
            or plan.get("sha256") != confirmation or digest(plan) != confirmation):
        raise RetentionError("RETENTION_PLAN_CONFIRMATION_MISMATCH")
    target = plan["scope"]
    with conn.transaction():
        conn.execute("set local statement_timeout='10s'; set local lock_timeout='2s'")
        schema = target["schema"]
        conn.execute("select pg_advisory_xact_lock(hashtext(%s))", ("retention:"+schema+":"+target["campaign_id"],))
        actual = scope(conn, target["environment"], target["campaign_id"], target["admin_user_id"], lock=True)
        if actual != target:
            raise RetentionError("RETENTION_PLAN_SCOPE_CHANGED")
        marker = fulfillment_marker(conn, schema, actual["campaign_id"])
        if marker != plan.get("fulfillment_marker"):
            raise RetentionError("RETENTION_FULFILLMENT_MARKER_CHANGED")
        has_nonpaid_rows = any(row["status"] != "PAID" for row in plan["rows"])
        now = conn.execute("select clock_timestamp() as now").fetchone()["now"]
        if has_nonpaid_rows:
            validate_fulfillment_state(conn, actual, now, lock=True)
        event_id = "retention_batch:" + confirmation
        previous = conn.execute(f"select after_value from {schema}.admin_audit where event_id=%s and action='RETENTION_BATCH_COMPLETE'",
                                (event_id,)).fetchone()
        if previous:
            for row in plan["rows"]:
                current = claim_metadata(conn, schema, actual["campaign_id"], row["claim_id"], lock=True)
                if current["contact_created_at"] or current["draft_updated_at"]:
                    raise RetentionError("RETENTION_REPLAY_STATE_MISMATCH")
            return {**previous["after_value"], "replayed": True}
        reviewed = dt.datetime.fromisoformat(plan["reviewed_at"])
        if reviewed.tzinfo is None or not dt.timedelta(0) <= now-reviewed <= dt.timedelta(hours=PLAN_HOURS):
            raise RetentionError("RETENTION_PLAN_EXPIRED")
        ids = [row["claim_id"] for row in plan["rows"]]
        if ids != sorted(set(ids)):
            raise RetentionError("RETENTION_PLAN_INVALID")
        counts = {"claim_contacts_deleted": 0, "drafts_deleted": 0, "claims_processed": len(ids)}
        marker_at = dt.datetime.fromisoformat(marker["completed_at"]) if marker else None
        for expected in plan["rows"]:
            current = claim_metadata(conn, schema, actual["campaign_id"], expected["claim_id"], lock=True)
            paid_at = dt.datetime.fromisoformat(current["paid_at"]) if current["paid_at"] else None
            eligible = ((current["status"] == "PAID" and paid_at is not None
                         and paid_at <= now-dt.timedelta(days=ELIGIBLE_DAYS))
                        or (current["status"] != "PAID" and marker_at is not None
                            and marker_at <= now-dt.timedelta(days=ELIGIBLE_DAYS)))
            if current != expected or not eligible:
                raise RetentionError("RETENTION_CLAIM_CHANGED")
            cid = current["claim_id"]
            drafts = conn.execute(f"delete from {schema}.claim_contact_draft where claim_id=%s", (cid,)).rowcount
            contacts = conn.execute(f"delete from {schema}.claim_contact where claim_id=%s", (cid,)).rowcount
            counts["claim_contacts_deleted"] += contacts
            counts["drafts_deleted"] += drafts
            conn.execute(f"""insert into {schema}.admin_audit
                (admin_user_id,action,target_type,target_id,before_value,after_value,reason,event_id)
                values(%s,'CLAIM_PII_RETENTION_DELETE','claim',%s,%s::jsonb,%s::jsonb,%s,%s)""",
                (actual["admin_user_id"], cid, json.dumps({"contact": bool(contacts), "draft": bool(drafts)}),
                 json.dumps({"contact": False, "draft": False, "plan_sha256": confirmation}),
                 "Claim contact retention deadline", "retention:" + confirmation + ":" + hashlib.sha256(cid.encode()).hexdigest()[:24]))
        result = {**counts, "plan_sha256": confirmation, "completed_at": stamp(now), "replayed": False}
        conn.execute(f"""insert into {schema}.admin_audit
            (admin_user_id,action,target_type,target_id,after_value,reason,event_id)
            values(%s,'RETENTION_BATCH_COMPLETE','campaign',%s,%s::jsonb,%s,%s)""",
            (actual["admin_user_id"], actual["campaign_id"], json.dumps(result),
             "Reviewed retention batch completed; no contact fields in audit", event_id))
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--environment", choices=tuple(SCHEMAS), required=True)
    parser.add_argument("--campaign", required=True)
    parser.add_argument("--admin-user", required=True)
    mode = parser.add_mutually_exclusive_group(required=True)
    mode.add_argument("--plan-output", type=Path)
    mode.add_argument("--apply-plan", type=Path)
    mode.add_argument("--record-fulfillment-complete", action="store_true")
    parser.add_argument("--confirm-plan-sha256")
    parser.add_argument("--evidence-reference")
    args = parser.parse_args()
    try:
        args.admin_user = str(uuid.UUID(args.admin_user))
        with connect(os.environ.get("RETENTION_DATABASE_URL", ""), args.environment) as conn:
            if args.record_fulfillment_complete:
                if args.confirm_plan_sha256 or not args.evidence_reference:
                    raise RetentionError("RETENTION_FULFILLMENT_ARGUMENTS_INVALID")
                print(json.dumps(record_fulfillment_complete(conn, args.environment, args.campaign,
                    args.admin_user, args.evidence_reference)))
            elif args.plan_output:
                if args.confirm_plan_sha256 or args.evidence_reference:
                    raise RetentionError("RETENTION_DRY_RUN_CONFIRMATION_UNEXPECTED")
                with conn.transaction():
                    conn.execute("set transaction read only")
                    plan = build_plan(conn, args.environment, args.campaign, args.admin_user)
                args.plan_output.parent.mkdir(parents=True, exist_ok=True)
                fd = os.open(args.plan_output, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
                with os.fdopen(fd, "w") as output:
                    json.dump(plan, output, ensure_ascii=False, indent=2)
                print(json.dumps({"dry_run": True, "plan": str(args.plan_output), "sha256": plan["sha256"], **plan["summary"]}))
            else:
                if args.evidence_reference:
                    raise RetentionError("RETENTION_APPLY_ARGUMENTS_INVALID")
                plan = json.loads(args.apply_plan.read_text())
                if any(plan["scope"][key] != value for key, value in (
                        ("environment", args.environment), ("campaign_id", args.campaign), ("admin_user_id", args.admin_user))):
                    raise RetentionError("RETENTION_ARGUMENT_SCOPE_MISMATCH")
                print(json.dumps(apply_plan(conn, plan, args.confirm_plan_sha256)))
    except RetentionError as error:
        parser.exit(1, str(error)+"\n")
    except (psycopg.Error, OSError, ValueError, KeyError, TypeError):
        parser.exit(1, "RETENTION_FAILED: no credentials or database error details printed; check scope and operator privileges.\n")


if __name__ == "__main__":
    main()
