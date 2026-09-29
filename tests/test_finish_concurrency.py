import datetime as dt
import sys
import threading
import unittest
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))

import operations
from test_migration_acceptance import (
    ADDITIONS, CLAIM_DRAFT, CLAIM_FIX, FOUNDATION, GAME_V21,
    INTERRUPTED_AND_SHARE, KAKAO_SHARE_WEBHOOK, LOW_SCORE_REFUND, PHASE2,
    PHASE3, RANKING_FINALIZATION, REAL_TOP3_CONTACT, TemporaryAuditDatabase,
)


CAMPAIGN_ID = "finish-concurrency-test"
MIGRATIONS = (
    FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT,
    CLAIM_DRAFT, LOW_SCORE_REFUND, KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE,
    PHASE3, RANKING_FINALIZATION,
)


@unittest.skipUnless(
    Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(),
    "isolated local PostgreSQL fixture is unavailable",
)
class FinishConcurrencyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        try:
            cls.database.create()
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(
                f"isolated local PostgreSQL fixture is unavailable: {error}"
            ) from error
        for migration in MIGRATIONS:
            cls.database.apply(migration)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    def setUp(self):
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.campaign
                (id,title,game_version,benefit_url,probability_version,status)
                values(%s,'Finish concurrency','2.1.0',
                  'https://gemini.google.com/students','finish-concurrency-v1','ACTIVE')""",
                (CAMPAIGN_ID,),
            )
            conn.execute(
                """insert into dino_dev.environment_guard
                (environment,project_ref,test_seed,campaign_id)
                values('test','local',true,%s)""",
                (CAMPAIGN_ID,),
            )
            for label in ("a", "b"):
                participant_id = f"finish_participant_{label}"
                session_id = f"finish_session_{label}"
                conn.execute(
                    """insert into dino_dev.participant
                    (id,campaign_id,token_hash,token_expires_at,nickname,
                     referral_code,environment)
                    values(%s,%s,%s,clock_timestamp()+interval '1 day',
                      %s,%s,'test')""",
                    (
                        participant_id,
                        CAMPAIGN_ID,
                        label * 64,
                        f"finish-{label}",
                        f"finish_ref_{label}",
                    ),
                )
                conn.execute(
                    """insert into dino_dev.game_session
                    (id,participant_id,campaign_id,idempotency_key,seed,version,
                     status,ticket_kind,ticket_refund_status,started_at,
                     expires_at,environment)
                    values(%s,%s,%s,%s,1,'2.1.0','ACTIVE','INITIAL','NOT_DUE',
                      clock_timestamp()-interval '2 seconds',
                      clock_timestamp()+interval '5 minutes','test')""",
                    (session_id, participant_id, CAMPAIGN_ID, f"finish-key-{label}"),
                )

    def finish_context(self, label):
        return {
            "participant_token_hash": label * 64,
            "campaign_id": CAMPAIGN_ID,
            "environment": "test",
            "deployment": "finish-concurrency-test",
            "event_version": "phase3-v1",
            "game_version": "2.1.0",
            "verification": {
                "valid": True,
                "score": 222,
                "ticks": 60,
                "reason": "VERIFIED",
                "summary": {},
                "end_reason": "COLLISION",
            },
        }

    def test_distinct_finishes_share_campaign_lock_but_block_admin_update(self):
        release = threading.Event()
        completed = {label: threading.Event() for label in ("a", "b")}
        outcomes = {}
        errors = []

        def finish(label):
            try:
                with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
                    with conn.transaction():
                        conn.execute("set local role dino_dev_app")
                        status, result = operations.finish_session(
                            conn,
                            f"finish_session_{label}",
                            {},
                            self.finish_context(label),
                        )
                        outcomes[label] = (status, result["status"])
                        completed[label].set()
                        release.wait(timeout=5)
            except Exception as error:
                errors.append(error)
                completed[label].set()

        first = threading.Thread(target=finish, args=("a",))
        second = threading.Thread(target=finish, args=("b",))
        first.start()
        self.assertTrue(completed["a"].wait(timeout=5))
        second.start()
        second_completed_while_first_open = completed["b"].wait(timeout=1)
        try:
            self.assertTrue(
                second_completed_while_first_open,
                "a distinct finish must not wait for the first finish transaction",
            )
            self.assertEqual(errors, [])
            with psycopg.connect(self.database.dsn, autocommit=True) as conn:
                conn.execute("set lock_timeout='200ms'")
                with self.assertRaises(psycopg.errors.LockNotAvailable):
                    conn.execute(
                        "select id from dino_dev.campaign where id=%s for update",
                        (CAMPAIGN_ID,),
                    )
        finally:
            release.set()
            first.join(timeout=5)
            second.join(timeout=5)

        self.assertFalse(first.is_alive())
        self.assertFalse(second.is_alive())
        self.assertEqual(errors, [])
        self.assertEqual(
            outcomes,
            {"a": (200, "FINISHED"), "b": (200, "FINISHED")},
        )
        with psycopg.connect(self.database.dsn) as conn:
            finished = conn.execute(
                """select count(*) from dino_dev.game_session
                where campaign_id=%s and status='FINISHED'""",
                (CAMPAIGN_ID,),
            ).fetchone()[0]
        self.assertEqual(finished, 2)


if __name__ == "__main__":
    unittest.main()
