import contextlib
import sys
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))

import operations
from test_migration_acceptance import (
    ADDITIONS,
    CLAIM_FIX,
    FOUNDATION,
    GAME_V21,
    INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK,
    PHASE2,
    PHASE3,
    REAL_TOP3_CONTACT,
    TemporaryAuditDatabase,
)

CLAIM_DRAFT = ROOT / "supabase/migrations/20260926215000_claim_contact_draft.sql"
LOW_SCORE_REFUND = ROOT / "supabase/migrations/20260927090000_low_score_ticket_refund.sql"
CAMPAIGN_ID = "phase3-claim-payment-test"


@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(), "isolated local PostgreSQL fixture is unavailable")
class Phase3ClaimPaymentTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        try:
            cls.database.create()
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f"isolated local PostgreSQL fixture is unavailable: {error}") from error
        for migration in (
            FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT,
            CLAIM_DRAFT, LOW_SCORE_REFUND, KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE, PHASE3,
        ):
            cls.database.apply(migration)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    def setUp(self):
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """truncate dino_dev.inventory_history,dino_dev.claim_contact,dino_dev.claim,
                dino_dev.inventory_item,dino_dev.prize,dino_dev.participant,dino_dev.admin_audit,
                dino_dev.admin_member,dino_dev.environment_guard,dino_dev.campaign restart identity cascade"""
            )
            conn.execute(
                """insert into dino_dev.campaign(id,title,game_version,benefit_url,probability_version)
                values(%s,'Phase 3 claim payment','2.1.0','https://gemini.google.com/students','test-v1')""",
                (CAMPAIGN_ID,),
            )
            conn.execute(
                """insert into dino_dev.environment_guard(environment,project_ref,test_seed,campaign_id)
                values('test','local',true,%s)""",
                (CAMPAIGN_ID,),
            )
            self.admin_id = str(uuid.uuid4())
            conn.execute(
                """insert into dino_dev.admin_member(auth_user_id,display_name,permissions)
                values(%s,'TEST_admin',array['claims:write'])""",
                (self.admin_id,),
            )

    @contextlib.contextmanager
    def app_tx(self):
        with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("set local role dino_dev_app")
                yield conn

    def ctx(self):
        return {
            "admin_user_id": self.admin_id,
            "environment": "test",
            "deployment": "phase3-claim-payment",
            "event_version": "phase3-v1",
            "campaign_id": CAMPAIGN_ID,
        }

    def seed_claim(self, suffix, *, verification_status="VERIFIED", verification_reference="TEST_REF_student", external_delivery=False):
        participant_id = f"p_{suffix}"
        prize_id = f"prize_{suffix}"
        inventory_id = f"inventory_{suffix}"
        claim_id = f"claim_{suffix}"
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                values(%s,%s,%s,clock_timestamp()+interval '1 day','TEST_user',%s,'test')""",
                (participant_id, CAMPAIGN_ID, suffix.ljust(64, "0")[:64], f"ref_{suffix}_000000000000"),
            )
            conn.execute(
                """insert into dino_dev.prize(id,campaign_id,name,category,probability,image_url)
                values(%s,%s,'TEST_prize','COUPON',0,'/test.png')""",
                (prize_id, CAMPAIGN_ID),
            )
            conn.execute(
                """insert into dino_dev.inventory_item(id,prize_id,status,reserved_at)
                values(%s,%s,'RESERVED',clock_timestamp())""",
                (inventory_id, prize_id),
            )
            conn.execute(
                """insert into dino_dev.claim
                (id,campaign_id,participant_id,claim_type,prize_id,inventory_item_id,status,
                 contact_submitted_at,contacted_at,verification_status,verification_reference,external_delivery)
                values(%s,%s,%s,'DRAW',%s,%s,'CONTACTED',clock_timestamp(),clock_timestamp(),%s,%s,%s)""",
                (claim_id, CAMPAIGN_ID, participant_id, prize_id, inventory_id,
                 verification_status, verification_reference, external_delivery),
            )
            conn.execute(
                """insert into dino_dev.claim_contact(claim_id,recipient_name,contact,school)
                values(%s,'TEST_user','01000000000','TEST_school')""",
                (claim_id,),
            )
        return claim_id, inventory_id

    def snapshot(self, claim_id, inventory_id):
        with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
            claim = conn.execute(
                "select status,version,verification_status,verification_reference,external_delivery,paid_at from dino_dev.claim where id=%s",
                (claim_id,),
            ).fetchone()
            inventory = conn.execute(
                "select status,paid_at from dino_dev.inventory_item where id=%s", (inventory_id,)
            ).fetchone()
            history = conn.execute(
                "select count(*)::int n from dino_dev.inventory_history where inventory_item_id=%s", (inventory_id,)
            ).fetchone()["n"]
            audits = conn.execute(
                "select count(*)::int n from dino_dev.admin_audit where target_id=%s", (claim_id,)
            ).fetchone()["n"]
        return dict(claim), dict(inventory), history, audits

    def test_paid_rejects_each_missing_evidence_without_mutation(self):
        cases = (
            ("verification", {"verification_status": "PENDING", "verification_reference": "TEST_REF_pending", "external_delivery": True, "reason": "전달 확인"}, "CLAIM_VERIFICATION_REQUIRED"),
            ("reference", {"verification_status": "VERIFIED", "verification_reference": None, "external_delivery": True, "reason": "전달 확인"}, "DELIVERY_EVIDENCE_REQUIRED"),
            ("delivery", {"verification_status": "VERIFIED", "verification_reference": "TEST_REF_student", "external_delivery": False, "reason": "전달 확인"}, "DELIVERY_CONFIRMATION_REQUIRED"),
            ("strict_delivery", {"verification_status": "VERIFIED", "verification_reference": "TEST_REF_student", "external_delivery": "true", "reason": "전달 확인"}, "DELIVERY_CONFIRMATION_REQUIRED"),
            ("reason", {"verification_status": "VERIFIED", "verification_reference": "TEST_REF_student", "external_delivery": True}, "DELIVERY_EVIDENCE_REQUIRED"),
        )
        for index, (label, evidence, code) in enumerate(cases):
            with self.subTest(label=label):
                claim_id, inventory_id = self.seed_claim(f"missing_{index}")
                before = self.snapshot(claim_id, inventory_id)
                with self.app_tx() as conn, self.assertRaises(operations.DomainError) as caught:
                    operations.admin_claim_patch(
                        conn, claim_id,
                        {"status": "PAID", "expected_version": 1, "event_id": f"evt_{label}", **evidence},
                        self.ctx(),
                    )
                self.assertEqual((caught.exception.code, caught.exception.status), (code, 409))
                self.assertEqual(self.snapshot(claim_id, inventory_id), before)

    def test_paid_updates_claim_inventory_history_and_audit_once(self):
        claim_id, inventory_id = self.seed_claim("success")
        with self.app_tx() as conn:
            result = operations.admin_claim_patch(
                conn, claim_id,
                {"status": "PAID", "expected_version": 1, "external_delivery": True,
                 "reason": "실제 전달 완료", "event_id": "evt_paid_success"},
                self.ctx(),
            )[1]
        claim, inventory, history, audits = self.snapshot(claim_id, inventory_id)
        self.assertEqual((result["status"], result["version"], result["verification_status"], result["external_delivery"]), ("PAID", 2, "VERIFIED", True))
        self.assertEqual((claim["status"], claim["version"], claim["external_delivery"]), ("PAID", 2, True))
        self.assertIsNotNone(claim["paid_at"])
        self.assertEqual(inventory["status"], "PAID")
        self.assertIsNotNone(inventory["paid_at"])
        self.assertEqual((history, audits), (1, 1))
        with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
            audit = conn.execute(
                "select before_value,after_value,reason from dino_dev.admin_audit where target_id=%s",
                (claim_id,),
            ).fetchone()
            ledger = conn.execute(
                "select from_status,to_status,reason,related_type,related_id from dino_dev.inventory_history where inventory_item_id=%s",
                (inventory_id,),
            ).fetchone()
        self.assertEqual(audit["before_value"]["external_delivery"], False)
        self.assertEqual(audit["after_value"]["verification_reference"], "TEST_REF_student")
        self.assertEqual(audit["after_value"]["external_delivery"], True)
        self.assertEqual(audit["reason"], "실제 전달 완료")
        self.assertEqual(tuple(ledger.values()), ("RESERVED", "PAID", "CLAIM_PAID", "claim", claim_id))

        before_replay = self.snapshot(claim_id, inventory_id)
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as stale:
            operations.admin_claim_patch(
                conn, claim_id,
                {"status": "PAID", "expected_version": 1, "external_delivery": True,
                 "reason": "중복 전달", "event_id": "evt_paid_replay"},
                self.ctx(),
            )
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")
        self.assertEqual(self.snapshot(claim_id, inventory_id), before_replay)

    def test_paid_claim_cannot_withdraw_required_evidence(self):
        claim_id, inventory_id = self.seed_claim("withdraw")
        with self.app_tx() as conn:
            operations.admin_claim_patch(
                conn, claim_id,
                {"status": "PAID", "expected_version": 1, "external_delivery": True,
                 "reason": "실제 전달 완료", "event_id": "evt_paid_before_withdraw"},
                self.ctx(),
            )
        for label, change, code in (
            ("verification", {"verification_status": "PENDING"}, "CLAIM_VERIFICATION_REQUIRED"),
            ("reference", {"verification_reference": None}, "DELIVERY_EVIDENCE_REQUIRED"),
            ("delivery", {"external_delivery": False}, "DELIVERY_CONFIRMATION_REQUIRED"),
        ):
            with self.subTest(label=label):
                before = self.snapshot(claim_id, inventory_id)
                with self.app_tx() as conn, self.assertRaises(operations.DomainError) as caught:
                    operations.admin_claim_patch(
                        conn, claim_id,
                        {"expected_version": 2, "event_id": f"evt_withdraw_{label}", **change},
                        self.ctx(),
                    )
                self.assertEqual(caught.exception.code, code)
                self.assertEqual(self.snapshot(claim_id, inventory_id), before)


if __name__ == "__main__":
    unittest.main()
