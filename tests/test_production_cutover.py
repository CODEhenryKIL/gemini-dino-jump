import copy
import datetime as dt
import hashlib
import json
from pathlib import Path
import sys
import unittest
from unittest import mock

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

from prepare_production import provision, render_schema
from production_cutover import (
    CutoverError, _json_sha, apply_transition, plan_from_snapshot, plan_transition,
    render_apply_sql, render_state_sql, transition_spec,
)
from test_migration_acceptance import TemporaryAuditDatabase
from test_production_schema import approved_manifest


def encoded(manifest):
    payload = json.dumps(manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True).encode()
    return payload, hashlib.sha256(payload).hexdigest()


def transition_manifests():
    off = approved_manifest()
    off["version"] = "cutover-off-v1"
    off["status"] = "APPROVED"
    off["event_enabled"] = False
    off["campaign"]["id"] = "gemini_dino_cutover_test"
    active = copy.deepcopy(off)
    active["version"] = "cutover-active-v1"
    active["event_enabled"] = True
    active["approvals"] = {
        key: {"status": "APPROVED", "detail": "reviewed", "reference": "test://approval"}
        for key in active["approvals"]
    }
    active["evidence"] = {
        key: {"status": "VERIFIED", "detail": "checked", "reference": "test://evidence"}
        for key in active["evidence"]
    }
    return encoded(off)[0], encoded(active)[0]


class ProductionCutoverManifestTest(unittest.TestCase):
    def test_only_transition_metadata_may_change(self):
        off, active = transition_manifests()
        changed = json.loads(active)
        changed["campaign"]["closes_at"] = "2026-10-04T00:00:00+09:00"
        with self.assertRaisesRegex(CutoverError, "IMMUTABLE_MANIFEST_FIELDS_CHANGED"):
            transition_spec(off, encoded(changed)[0], "activate", 1)

    def test_active_target_requires_real_launch_completeness(self):
        off, active = transition_manifests()
        incomplete = json.loads(active)
        incomplete["evidence"]["final_load_test"] = None
        with self.assertRaisesRegex(CutoverError, "TARGET_NOT_LAUNCH_READY"):
            transition_spec(off, encoded(incomplete)[0], "activate", 1)

    def test_rendered_sql_is_bounded_and_uses_the_runtime_cutover_lock(self):
        off, active = transition_manifests()
        spec = transition_spec(off, active, "activate", 7)
        state = {
            "guard": {}, "campaign": {},
            "record_counts": {"participant": 0, "game_session": 0, "draw": 0, "claim": 0},
            "draw_pool": {"total": 5000, "prize": 77, "benefit": 4923},
            "inventory_by_prize": spec["inventory_by_prize"], "inventory_total": 80,
            "schema_versions": [],
        }
        plan = {
            "plan_version": 1, "created_at": "2026-09-29T08:00:00+00:00", "maintenance_role": "postgres",
            "spec": spec, "database_state": state,
        }
        plan["database_state_sha256"] = _json_sha(state)
        plan["sha256"] = _json_sha(plan)
        # Keep the fixture current enough for the one-hour plan lifetime check.
        import datetime as dt
        plan["created_at"] = dt.datetime.now(dt.timezone.utc).isoformat()
        plan["sha256"] = _json_sha({key: value for key, value in plan.items() if key != "sha256"})
        sql = render_apply_sql(plan, off, active)
        self.assertIn("pg_advisory_xact_lock(hashtext('dino-prod-cutover'))", sql)
        self.assertIn("lock table dino_prod.environment_guard", sql)
        self.assertIn("CUTOVER_PLAN_STALE", sql)
        self.assertIn("CUTOVER_PLAN_EXPIRED", sql)
        self.assertIn("PRODUCTION_SCHEMA_VERSION_MISMATCH", sql)
        self.assertNotRegex(sql.lower(), r"\b(delete|truncate|drop)\b")

    def test_connector_snapshot_path_is_read_only_and_builds_the_same_plan_shape(self):
        off, active = transition_manifests()
        spec = transition_spec(off, active, "activate", 1)
        sql = render_state_sql(spec)
        self.assertTrue(sql.lstrip().startswith("with guard_row"))
        self.assertNotRegex(sql.lower(), r"\b(insert|update|delete|truncate|drop)\b")
        self.assertIn("maintenance_role_ok", sql)


@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(), "isolated local PostgreSQL fixture is unavailable")
class ProductionCutoverDatabaseTest(unittest.TestCase):
    maxDiff = None

    def setUp(self):
        self.database = TemporaryAuditDatabase()
        self.database.create()
        with psycopg.connect(self.database.dsn, autocommit=True) as conn:
            conn.execute(render_schema(), prepare=False)
        self.off_bytes, self.active_bytes = transition_manifests()
        off = json.loads(self.off_bytes)
        with psycopg.connect(self.database.dsn) as conn:
            provision(conn, off, hashlib.sha256(self.off_bytes).hexdigest(), self.off_bytes)

    def tearDown(self):
        if hasattr(self, "database"):
            self.database.drop()

    def connect(self):
        return psycopg.connect(self.database.dsn, row_factory=dict_row)

    def campaign_version(self):
        with self.connect() as conn:
            return conn.execute("select version from dino_prod.campaign where id='gemini_dino_cutover_test'").fetchone()["version"]

    def transition_state(self):
        with self.connect() as conn:
            guard = conn.execute("""select event_enabled,launch_manifest_sha256,campaign_opens_at,
              campaign_closes_at,claim_closes_at from dino_prod.environment_guard where singleton""").fetchone()
            campaign = conn.execute("""select status,version,opens_at,closes_at,settings
              from dino_prod.campaign where id='gemini_dino_cutover_test'""").fetchone()
        return {"guard": dict(guard), "campaign": dict(campaign)}

    def _insert_real_records(self):
        cid = "gemini_dino_cutover_test"
        with self.connect() as conn:
            conn.execute("""insert into dino_prod.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,synthetic)
              values('participant_keep',%s,%s,clock_timestamp()+interval '1 day','keep','KEEPREFERRAL1','production',false)""",
              (cid, "a" * 64))
            conn.execute("""insert into dino_prod.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
               expires_at,score,valid_ticks,environment,synthetic)
              values('session_keep','participant_keep',%s,'idem_keep',1,'2.1.0','FINISHED','INITIAL','NOT_DUE',
                clock_timestamp()+interval '1 hour',101,120,'production',false)""", (cid,))
            conn.execute("""insert into dino_prod.draw
              (id,campaign_id,participant_id,eligible_session_id,pouch_index,prize_id,is_won,probability_version,random_audit_hash)
              values('draw_keep',%s,'participant_keep','session_keep',0,%s,false,'cutover-off-v1',%s)""",
              (cid, cid + "_benefit", "b" * 64))
            conn.execute("""insert into dino_prod.claim
              (id,campaign_id,participant_id,draw_id,claim_type,prize_id,status)
              values('claim_keep',%s,'participant_keep','draw_keep','DRAW',%s,'INFORMATION_RECEIVED')""",
              (cid, cid + "_benefit"))

    def test_activate_then_rollback_preserves_all_operational_records(self):
        version = self.campaign_version()
        with self.connect() as conn:
            plan = plan_transition(conn, self.off_bytes, self.active_bytes, "activate", version)
        plan = json.loads(json.dumps(plan))
        with self.connect() as conn:
            with self.assertRaisesRegex(CutoverError, "CUTOVER_CONFIRMATION_REQUIRED"):
                apply_transition(conn, plan, self.off_bytes, self.active_bytes, "wrong")
        with self.connect() as conn:
            result = apply_transition(conn, plan, self.off_bytes, self.active_bytes, "ACTIVATE_DINO_PRODUCTION")
        self.assertTrue(result["event_enabled"])
        self._insert_real_records()
        version = self.campaign_version()
        with self.connect() as conn:
            rollback = plan_transition(conn, self.active_bytes, self.off_bytes, "rollback", version)
        rollback = json.loads(json.dumps(rollback))
        before = rollback["database_state"]["record_counts"]
        self.assertEqual(before, {"participant": 1, "game_session": 1, "draw": 1, "claim": 1})
        rollback_sql = render_apply_sql(rollback, self.active_bytes, self.off_bytes)
        with psycopg.connect(self.database.dsn, autocommit=True, row_factory=dict_row) as conn:
            conn.execute(rollback_sql, prepare=False)
        with self.connect() as conn:
            after = {
                table: conn.execute(f"select count(*) count from dino_prod.{table}").fetchone()["count"]
                for table in ("participant", "game_session", "draw", "claim")
            }
            guard = conn.execute("select event_enabled,launch_manifest_sha256 from dino_prod.environment_guard where singleton").fetchone()
            campaign = conn.execute("select status,version from dino_prod.campaign where id='gemini_dino_cutover_test'").fetchone()
        self.assertEqual(after, before)
        self.assertEqual((guard["event_enabled"], guard["launch_manifest_sha256"]), (False, hashlib.sha256(self.off_bytes).hexdigest()))
        self.assertEqual((campaign["status"], campaign["version"]), ("PAUSED", version + 1))
        # This assertion belongs to the same self-contained lifecycle fixture:
        # rollback preserves records, so a subsequent activation must be refused.
        version = campaign["version"]
        with self.connect() as conn:
            with self.assertRaisesRegex(CutoverError, "PRODUCTION_NOT_EMPTY"):
                plan_transition(conn, self.off_bytes, self.active_bytes, "activate", version)

    def test_connector_snapshot_round_trip_matches_direct_plan(self):
        version = self.campaign_version()
        spec = transition_spec(self.off_bytes, self.active_bytes, "activate", version)
        with self.connect() as conn:
            direct = plan_transition(conn, self.off_bytes, self.active_bytes, "activate", version)
            conn.execute("set timezone='Asia/Seoul'")
            snapshot = conn.execute(render_state_sql(spec), prepare=False).fetchone()["snapshot"]
        connector = plan_from_snapshot(snapshot, self.off_bytes, self.active_bytes, "activate", version)
        self.assertEqual(connector["spec"], direct["spec"])
        self.assertEqual(connector["database_state"], direct["database_state"])
        self.assertEqual(connector["database_state_sha256"], direct["database_state_sha256"])

    def test_rendered_sql_rejects_expired_plan_without_transition(self):
        version = self.campaign_version()
        with self.connect() as conn:
            plan = plan_transition(conn, self.off_bytes, self.active_bytes, "activate", version)
        plan["created_at"] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=2)).isoformat()
        plan["sha256"] = _json_sha({key: value for key, value in plan.items() if key != "sha256"})
        with mock.patch("production_cutover.PLAN_MAX_AGE", dt.timedelta(hours=3)):
            sql = render_apply_sql(plan, self.off_bytes, self.active_bytes)
        before = self.transition_state()
        with psycopg.connect(self.database.dsn, autocommit=True, row_factory=dict_row) as conn:
            with self.assertRaisesRegex(psycopg.Error, "CUTOVER_PLAN_EXPIRED"):
                conn.execute(sql, prepare=False)
        self.assertEqual(self.transition_state(), before)

    def test_rendered_sql_rejects_empty_schema_versions_without_transition(self):
        version = self.campaign_version()
        with self.connect() as conn:
            plan = plan_transition(conn, self.off_bytes, self.active_bytes, "activate", version)
        sql = render_apply_sql(plan, self.off_bytes, self.active_bytes)
        before = self.transition_state()
        with self.connect() as conn:
            conn.execute("delete from dino_prod.schema_version")
        with psycopg.connect(self.database.dsn, autocommit=True, row_factory=dict_row) as conn:
            with self.assertRaisesRegex(psycopg.Error, "PRODUCTION_SCHEMA_VERSION_MISMATCH"):
                conn.execute(sql, prepare=False)
        self.assertEqual(self.transition_state(), before)
        with self.connect() as conn:
            count = conn.execute("select count(*) count from dino_prod.schema_version").fetchone()["count"]
        self.assertEqual(count, 0)


if __name__ == "__main__":
    unittest.main()
