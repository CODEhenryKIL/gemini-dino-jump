import contextlib
import datetime as dt
import json
from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))
import claim_retention as retention
from test_migration_acceptance import TemporaryAuditDatabase


@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(), "isolated PostgreSQL required")
class ClaimRetentionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        cls.database.create()
        for migration in sorted((ROOT / "supabase/migrations").glob("*.sql")):
            cls.database.apply(migration)
        with psycopg.connect(cls.database.dsn) as conn:
            conn.execute("create schema retention_unrelated")
            conn.execute("create table retention_unrelated.sentinel(id integer primary key)")
            conn.execute("insert into retention_unrelated.sentinel values(7)")

    @classmethod
    def tearDownClass(cls):
        cls.database.drop()

    def setUp(self):
        self.campaign = "retention-test"
        self.admin = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("truncate dino_dev.campaign,dino_dev.admin_audit,dino_dev.admin_member,dino_dev.environment_guard restart identity cascade")
            conn.execute("""insert into dino_dev.campaign
                (id,title,game_version,benefit_url,probability_version,opens_at,closes_at,settings)
                values(%s,'retention','2.1.0','https://gemini.google.com/students','test',
                  clock_timestamp()-interval '3 days',clock_timestamp()-interval '2 days',
                  jsonb_build_object('claim_submission_cutoff',clock_timestamp()-interval '1 day'))""", (self.campaign,))
            conn.execute("""insert into dino_dev.environment_guard(environment,project_ref,campaign_id,test_seed)
                values('test','local',%s,true)""", (self.campaign,))
            conn.execute("""insert into dino_dev.admin_member(auth_user_id,display_name,permissions)
                values(%s,'TEST owner',array['claims:write'])""", (self.admin,))
        self.add_claim("due", 31)
        self.add_claim("day29", 29)
        self.add_claim("recent", 28)
        self.add_claim("unpaid", 60, "CONTACTED")
        self.add_claim("nullpaid", None)

    @contextlib.contextmanager
    def connection(self):
        with psycopg.connect(self.database.dsn, autocommit=True, row_factory=dict_row) as conn:
            yield conn

    def add_claim(self, suffix, days, status="PAID"):
        with self.connection() as conn, conn.transaction():
            pid = "p_"+suffix
            conn.execute("""insert into dino_dev.participant(id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                values(%s,%s,%s,clock_timestamp()+interval '2 days',%s,%s,'test')""",
                (pid, self.campaign, uuid.uuid4().hex*2, "TEST", "ref_"+suffix+"_0000"))
            conn.execute("""insert into dino_dev.claim(id,campaign_id,participant_id,claim_type,status,paid_at)
                values(%s,%s,%s,'RANKING',%s,case when %s::integer is null then null else clock_timestamp()-make_interval(days=>%s) end)""",
                (suffix, self.campaign, pid, status, days, days))
            conn.execute("""insert into dino_dev.claim_contact(claim_id,recipient_name,contact,school,synthetic)
                values(%s,'TEST secret name','01000000000','TEST secret school',true)""", (suffix,))
            conn.execute("""insert into dino_dev.claim_contact_draft(claim_id,recipient_name,contact,school,synthetic,consent_at,consent_version)
                values(%s,'TEST draft name','01000000000','TEST draft school',true,clock_timestamp(),'claim-contact-v1')""", (suffix,))

    def plan(self, conn):
        return retention.build_plan(conn, "test", self.campaign, self.admin)

    def record_completion(self, conn, reference="TEST_REF_fulfillment_001"):
        return retention.record_fulfillment_complete(conn, "test", self.campaign, self.admin, reference)

    def age_completion(self, conn, days=29):
        conn.execute("""update dino_dev.admin_audit set created_at=clock_timestamp()-make_interval(days=>%s)
            where action=%s and target_id=%s""", (days, retention.FULFILLMENT_ACTION, self.campaign))

    def add_ranking_award(self, conn, rank, claim_id):
        prize_id = f"retention-rank-prize-{rank}"
        item_id = f"retention-rank-item-{rank}"
        conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
            values(%s,%s,%s,'COUPON','/test.png',0)""", (prize_id, self.campaign, f"TEST rank {rank}"))
        conn.execute("insert into dino_dev.inventory_item(id,prize_id) values(%s,%s)", (item_id, prize_id))
        conn.execute("update dino_dev.claim set prize_id=%s,inventory_item_id=%s where id=%s",
            (prize_id, item_id, claim_id))
        conn.execute("""insert into dino_dev.ranking_award(campaign_id,rank,prize_id,inventory_item_id)
            values(%s,%s,%s,%s)""", (self.campaign, rank, prize_id, item_id))

    def finalize_ranking_awards(self, conn, bindings):
        conn.execute("""insert into dino_dev.ranking_snapshot
            (id,campaign_id,status,tie_policy,campaign_closes_at,created_by,finalized_at,finalized_by)
            select 'retention-final',id,'FINAL','EARLIEST_ACHIEVED_AT',closes_at,%s,clock_timestamp(),%s
            from dino_dev.campaign where id=%s""", (self.admin, self.admin, self.campaign))
        for rank, claim_id in bindings:
            participant_id = "p_" + claim_id
            conn.execute("""insert into dino_dev.ranking_snapshot_entry
                (snapshot_id,participant_id,score,rank,tied,contact_status,achieved_at)
                values('retention-final',%s,%s,%s,false,'TERMINAL',clock_timestamp())""",
                (participant_id, 100-rank, rank))
            conn.execute("""update dino_dev.ranking_award set snapshot_id='retention-final',
                participant_id=%s,claim_id=%s,finalized_at=clock_timestamp()
                where campaign_id=%s and rank=%s""", (participant_id, claim_id, self.campaign, rank))

    def test_dry_run_is_read_only_and_plan_has_no_contact_values(self):
        with self.connection() as conn, conn.transaction():
            conn.execute("set transaction read only")
            plan = self.plan(conn)
            self.assertEqual([r["claim_id"] for r in plan["rows"]], ["day29", "due"])
            self.assertEqual(plan["summary"], {"manual_issue_count": 1, "paid_not_due_count": 1,
                "nonpaid_waiting_for_completion_count": 1, "nonpaid_not_due_count": 0,
                "nonpaid_blocked_count": 0, "fulfillment_state_error": None,
                "due_paid_count": 2, "due_nonpaid_count": 0, "due_count": 2, "overdue_count": 1})
            self.assertIsNone(plan["fulfillment_marker"])
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.claim_contact").fetchone()["n"], 5)
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.admin_audit").fetchone()["n"], 0)
            self.assertNotIn("01000000000", json.dumps(plan))
            self.assertNotIn("TEST secret", json.dumps(plan))

    def test_apply_erases_both_copies_preserves_claims_and_records_audit_and_replay(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            result = retention.apply_plan(conn, plan, plan["sha256"])
            self.assertEqual((result["claim_contacts_deleted"], result["drafts_deleted"]), (2, 2))
            self.assertTrue(retention.apply_plan(conn, plan, plan["sha256"])["replayed"])
            for table in ("claim_contact", "claim_contact_draft"):
                rows = conn.execute(f"select claim_id from dino_dev.{table} order by claim_id").fetchall()
                self.assertEqual([r["claim_id"] for r in rows], ["nullpaid", "recent", "unpaid"])
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.claim").fetchone()["n"], 5)
            audit = conn.execute("select * from dino_dev.admin_audit").fetchall()
            self.assertEqual(len(audit), 3)
            self.assertNotIn("01000000000", str(audit))
            self.assertEqual(conn.execute("select id from retention_unrelated.sentinel").fetchone()["id"], 7)
            self.assertEqual(self.plan(conn)["summary"]["due_count"], 0)

    def test_unpaid_contact_waits_for_completion_and_for_the_retention_period(self):
        with self.connection() as conn:
            self.assertNotIn("unpaid", [row["claim_id"] for row in self.plan(conn)["rows"]])
            marker = self.record_completion(conn)
            self.assertFalse(marker["replayed"])
            fresh = self.plan(conn)
            self.assertNotIn("unpaid", [row["claim_id"] for row in fresh["rows"]])
            self.assertEqual(fresh["summary"]["nonpaid_not_due_count"], 1)
            self.age_completion(conn)
            aged = self.plan(conn)
            self.assertIn("unpaid", [row["claim_id"] for row in aged["rows"]])
            result = retention.apply_plan(conn, aged, aged["sha256"])
            self.assertEqual((result["claim_contacts_deleted"], result["drafts_deleted"]), (3, 3))
            for table in ("claim_contact", "claim_contact_draft"):
                remaining = [row["claim_id"] for row in conn.execute(
                    f"select claim_id from dino_dev.{table} order by claim_id")]
                self.assertEqual(remaining, ["nullpaid", "recent"])

    def test_completion_marker_uses_database_time_and_is_idempotent(self):
        with self.connection() as conn:
            before = conn.execute("select clock_timestamp() as now").fetchone()["now"]
            first = self.record_completion(conn)
            after = conn.execute("select clock_timestamp() as now").fetchone()["now"]
            completed = dt.datetime.fromisoformat(first["completed_at"])
            self.assertLessEqual(before, completed)
            self.assertLessEqual(completed, after)
            replay = self.record_completion(conn)
            self.assertTrue(replay["replayed"])
            self.assertEqual(replay["audit_id"], first["audit_id"])
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.admin_audit where action=%s",
                (retention.FULFILLMENT_ACTION,)).fetchone()["n"], 1)
            with self.assertRaisesRegex(retention.RetentionError, "ALREADY_RECORDED"):
                self.record_completion(conn, "TEST_REF_different_002")

    def test_completion_marker_rejects_bad_or_open_windows(self):
        with self.connection() as conn:
            conn.execute("update dino_dev.campaign set settings='{}'::jsonb where id=%s", (self.campaign,))
            with self.assertRaisesRegex(retention.RetentionError, "WINDOW_INVALID"):
                self.record_completion(conn)
            conn.execute("""update dino_dev.campaign set closes_at=clock_timestamp()+interval '1 day',
                settings=jsonb_build_object('claim_submission_cutoff',clock_timestamp()+interval '2 days') where id=%s""",
                (self.campaign,))
            with self.assertRaisesRegex(retention.RetentionError, "TOO_EARLY"):
                self.record_completion(conn)
            with self.assertRaisesRegex(retention.RetentionError, "EVIDENCE_REFERENCE_INVALID"):
                retention.record_fulfillment_complete(conn, "test", self.campaign, self.admin, "REF_prod_not_test")

    def test_completion_marker_blocks_unresolved_allocated_claim_and_unfinalized_ranking(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
                values('retention-prize',%s,'TEST prize','COUPON','/test.png',0)""", (self.campaign,))
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('retention-item','retention-prize')")
            conn.execute("""update dino_dev.claim set prize_id='retention-prize',inventory_item_id='retention-item'
                where id='unpaid'""")
            with self.assertRaisesRegex(retention.RetentionError, "UNRESOLVED_CLAIMS"):
                self.record_completion(conn)
            conn.execute("update dino_dev.claim set status='NO_RESPONSE' where id='unpaid'")
            conn.execute("update dino_dev.claim set prize_id=null,inventory_item_id=null where id='unpaid'")
            conn.execute("delete from dino_dev.inventory_item where id='retention-item'")
            conn.execute("delete from dino_dev.prize where id='retention-prize'")
            self.add_ranking_award(conn, 1, "unpaid")
            with self.assertRaisesRegex(retention.RetentionError, "AWARD_CONFIG_INVALID"):
                self.record_completion(conn)
            self.add_ranking_award(conn, 2, "due")
            self.add_ranking_award(conn, 3, "day29")
            with self.assertRaisesRegex(retention.RetentionError, "RANKING_NOT_FINAL"):
                self.record_completion(conn)
            self.finalize_ranking_awards(conn, [(1, "unpaid"), (2, "due"), (3, "day29")])
            conn.execute("update dino_dev.ranking_award set claim_id='recent' where campaign_id=%s and rank=1",
                (self.campaign,))
            with self.assertRaisesRegex(retention.RetentionError, "AWARD_BINDING_INVALID"):
                self.record_completion(conn)
            conn.execute("update dino_dev.ranking_award set claim_id='unpaid' where campaign_id=%s and rank=1",
                (self.campaign,))
            self.assertFalse(self.record_completion(conn)["replayed"])

    def test_production_requires_exactly_three_ranking_awards(self):
        with self.connection() as conn:
            target = {"schema": "dino_dev", "environment": "production", "campaign_id": self.campaign}
            now = conn.execute("select clock_timestamp() as now").fetchone()["now"]
            with self.assertRaisesRegex(retention.RetentionError, "AWARD_CONFIG_INVALID"):
                retention.validate_fulfillment_state(conn, target, now)

    def test_invalid_aged_fulfillment_blocks_only_nonpaid_rows(self):
        with self.connection() as conn:
            self.record_completion(conn)
            self.age_completion(conn)
            conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
                values('late-prize',%s,'TEST late','COUPON','/test.png',0)""", (self.campaign,))
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('late-item','late-prize')")
            conn.execute("""update dino_dev.claim set prize_id='late-prize',inventory_item_id='late-item'
                where id='unpaid'""")
            plan = self.plan(conn)
            self.assertEqual([row["claim_id"] for row in plan["rows"]], ["day29", "due"])
            self.assertEqual(plan["summary"]["nonpaid_blocked_count"], 1)
            self.assertEqual(plan["summary"]["fulfillment_state_error"],
                "RETENTION_FULFILLMENT_UNRESOLVED_CLAIMS")
            result = retention.apply_plan(conn, plan, plan["sha256"])
            self.assertEqual((result["claim_contacts_deleted"], result["drafts_deleted"]), (2, 2))
            self.assertIsNotNone(conn.execute(
                "select claim_id from dino_dev.claim_contact where claim_id='unpaid'").fetchone())

    def test_marker_replay_revalidates_current_fulfillment_state(self):
        with self.connection() as conn:
            self.record_completion(conn)
            conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
                values('late-prize',%s,'TEST late','COUPON','/test.png',0)""", (self.campaign,))
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('late-item','late-prize')")
            conn.execute("""update dino_dev.claim set prize_id='late-prize',inventory_item_id='late-item'
                where id='unpaid'""")
            with self.assertRaisesRegex(retention.RetentionError, "UNRESOLVED_CLAIMS"):
                self.record_completion(conn)

    def test_apply_revalidates_marker_and_late_fulfillment_state(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
                values('retention-prize',%s,'TEST prize','COUPON','/test.png',0)""", (self.campaign,))
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('retention-item','retention-prize')")
            conn.execute("""update dino_dev.claim set prize_id='retention-prize',inventory_item_id='retention-item',status='NO_RESPONSE'
                where id='unpaid'""")
            self.record_completion(conn)
            self.age_completion(conn)
            plan = self.plan(conn)
            conn.execute("update dino_dev.claim set status='ON_HOLD',version=version+1 where id='unpaid'")
            with self.assertRaisesRegex(retention.RetentionError, "UNRESOLVED_CLAIMS"):
                retention.apply_plan(conn, plan, plan["sha256"])
            self.assertIsNotNone(conn.execute("select claim_id from dino_dev.claim_contact where claim_id='unpaid'").fetchone())

    def test_changed_draft_rolls_back_whole_batch(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            # 'day29' is first; changing the second forces rollback of the first deletion.
            conn.execute("update dino_dev.claim_contact_draft set updated_at=clock_timestamp() where claim_id='due'")
            with self.assertRaisesRegex(retention.RetentionError, "CLAIM_CHANGED"):
                retention.apply_plan(conn, plan, plan["sha256"])
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.claim_contact").fetchone()["n"], 5)
            self.assertEqual(conn.execute("select count(*) as n from dino_dev.admin_audit").fetchone()["n"], 0)

    def test_restored_contact_is_not_silently_reported_deleted_on_replay(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            retention.apply_plan(conn, plan, plan["sha256"])
            conn.execute("""insert into dino_dev.claim_contact(claim_id,recipient_name,contact,synthetic)
                values('due','TEST restored','01000000000',true)""")
            with self.assertRaisesRegex(retention.RetentionError, "REPLAY_STATE_MISMATCH"):
                retention.apply_plan(conn, plan, plan["sha256"])
            self.assertIsNotNone(conn.execute("select claim_id from dino_dev.claim_contact where claim_id='due'").fetchone())

    def test_audit_failure_rolls_back_contact_deletion(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            conn.execute("""alter table dino_dev.admin_audit add constraint test_reject_retention_audit
                check(action <> 'CLAIM_PII_RETENTION_DELETE')""")
            try:
                with self.assertRaises(psycopg.errors.CheckViolation):
                    retention.apply_plan(conn, plan, plan["sha256"])
                self.assertEqual(conn.execute("select count(*) as n from dino_dev.claim_contact").fetchone()["n"], 5)
                self.assertEqual(conn.execute("select count(*) as n from dino_dev.claim_contact_draft").fetchone()["n"], 5)
            finally:
                conn.execute("alter table dino_dev.admin_audit drop constraint test_reject_retention_audit")

    def test_tampered_or_expired_plan_rejected(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            with self.assertRaisesRegex(retention.RetentionError, "CONFIRMATION"):
                retention.apply_plan(conn, plan, "0"*64)
            plan["reviewed_at"] = retention.stamp(dt.datetime.now(dt.timezone.utc)-dt.timedelta(days=2))
            plan["sha256"] = retention.digest(plan)
            with self.assertRaisesRegex(retention.RetentionError, "EXPIRED"):
                retention.apply_plan(conn, plan, plan["sha256"])

    def test_unpaid_claim_cannot_be_added_even_to_rehashed_plan(self):
        with self.connection() as conn:
            plan = self.plan(conn)
            plan["rows"] = [retention.claim_metadata(conn, "dino_dev", self.campaign, "unpaid")]
            plan["sha256"] = retention.digest(plan)
            with self.assertRaisesRegex(retention.RetentionError, "CLAIM_CHANGED"):
                retention.apply_plan(conn, plan, plan["sha256"])

    def test_guard_admin_and_application_role_are_checked(self):
        with self.connection() as conn:
            with self.assertRaisesRegex(retention.RetentionError, "ADMIN_NOT_AUTHORIZED"):
                retention.build_plan(conn, "test", self.campaign, uuid.uuid4())
            conn.execute("update dino_dev.environment_guard set project_ref='wrong'")
            with self.assertRaisesRegex(retention.RetentionError, "GUARD"):
                self.plan(conn)
            conn.execute("update dino_dev.environment_guard set project_ref='local'")
            with conn.transaction():
                conn.execute("set local role dino_dev_app")
                with self.assertRaisesRegex(retention.RetentionError, "MAINTENANCE_ROLE"):
                    self.plan(conn)

    def test_connection_guard_rejects_remote_or_unrelated_target_before_connect(self):
        for dsn, environment in (
                ("postgresql://postgres@127.0.0.1:55433/postgres", "test"),
                ("postgresql://postgres@bad.example:5432/postgres", "production"),
                ("postgresql://postgres@127.0.0.1:55433/dino_phase1_audit_fake?options=bad", "test")):
            with self.subTest(environment=environment), self.assertRaises(retention.RetentionError):
                retention.connect(dsn, environment)

    def test_old_campaign_remains_accessible_after_guard_current_campaign_changes(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.campaign(id,title,game_version,benefit_url,probability_version)
                values('next-event','next','2.1.0','https://gemini.google.com/students','test')""")
            conn.execute("update dino_dev.environment_guard set campaign_id='next-event'")
            self.assertEqual(self.plan(conn)["summary"]["due_count"], 2)
