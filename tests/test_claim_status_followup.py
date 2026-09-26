import concurrent.futures
import contextlib
import hashlib
import hmac
import os
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import operations
import config


PG_BIN = Path("/private/tmp/dino-phase1-v2-postgres/bin")
ADMIN_DSN = "postgresql://postgres@127.0.0.1:55433/postgres"
FOUNDATION = ROOT / "supabase/migrations/20260925083548_phase1_dino_dev_foundation.sql"
ADDITIONS = ROOT / "supabase/migrations/20260925092759_phase1_acceptance_additions.sql"
CLAIM_FIX = ROOT / "supabase/migrations/20260925125939_add_awaiting_claim_information_status.sql"
CAMPAIGN_ID = "gemini_dino_phase1_test"
PEPPER = "claim-followup-pepper-0123456789"


def _database_dsn(name):
    if not name.startswith("dino_phase1_v2_claim_fixes"):
        raise RuntimeError("claim follow-up tests require the dedicated database prefix")
    parsed = urlsplit(ADMIN_DSN)
    if parsed.hostname not in {"127.0.0.1", "localhost", "::1"} or parsed.port != 55433:
        raise RuntimeError("claim follow-up tests require loopback postgres on port 55433")
    return f"postgresql://postgres@127.0.0.1:55433/{name}"


def _recreate_database(name):
    _database_dsn(name)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname=%s and pid<>pg_backend_pid()",
            (name,),
        )
        conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(name)))
        conn.execute(sql.SQL("create database {}").format(sql.Identifier(name)))


def _drop_database(name):
    _database_dsn(name)
    with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
        conn.execute(
            "select pg_terminate_backend(pid) from pg_stat_activity "
            "where datname=%s and pid<>pg_backend_pid()",
            (name,),
        )
        conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(name)))


def _apply(dsn, migration):
    database = urlsplit(dsn).path.lstrip("/")
    result = subprocess.run(
        [
            str(PG_BIN / "psql"),
            "-X",
            "-v",
            "ON_ERROR_STOP=1",
            "-h",
            "127.0.0.1",
            "-p",
            "55433",
            "-U",
            "postgres",
            "-d",
            database,
            "-f",
            str(migration),
        ],
        check=False,
        capture_output=True,
        text=True,
        env={**os.environ, "PGOPTIONS": "-c client_min_messages=warning"},
    )
    if result.returncode:
        raise AssertionError(f"migration failed: {migration.name}\n{result.stdout}\n{result.stderr}")


def _seed_campaign(conn):
    conn.execute(
        """insert into dino_dev.campaign
        (id,title,game_version,benefit_url,probability_version)
        values(%s,'Claim follow-up test','1.2.0','https://gemini.google.com/students','test-v1')""",
        (CAMPAIGN_ID,),
    )
    conn.execute(
        """insert into dino_dev.environment_guard
        (environment,project_ref,test_seed,campaign_id)
        values('test','local',true,%s)""",
        (CAMPAIGN_ID,),
    )


def _participant_hash(label):
    return hmac.new(PEPPER.encode(), label.encode(), hashlib.sha256).hexdigest()


def _insert_participant(conn, label="owner"):
    participant_id = f"p_{label}_{uuid.uuid4().hex}"
    token_hash = _participant_hash(participant_id)
    conn.execute(
        """insert into dino_dev.participant
        (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
        values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,'test')""",
        (participant_id, CAMPAIGN_ID, token_hash, f"TEST_{label}"[:24], f"ref_{uuid.uuid4().hex}"),
    )
    return participant_id, token_hash


def _context(**extra):
    value = {
        "environment": "test",
        "deployment": "claim-followup",
        "event_version": "phase1-v1",
        "campaign_id": CAMPAIGN_ID,
        "request_id": "claim-followup",
    }
    value.update(extra)
    return value


class ClaimMigrationFollowupTest(unittest.TestCase):
    DATABASE_NAME = "dino_phase1_v2_claim_fixes_migration"

    @classmethod
    def setUpClass(cls):
        cls.dsn = _database_dsn(cls.DATABASE_NAME)
        _recreate_database(cls.DATABASE_NAME)
        _apply(cls.dsn, FOUNDATION)
        _apply(cls.dsn, ADDITIONS)

    @classmethod
    def tearDownClass(cls):
        _drop_database(cls.DATABASE_NAME)

    def setUp(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "truncate dino_dev.claim_contact,dino_dev.claim,dino_dev.participant,"
                "dino_dev.environment_guard,dino_dev.campaign cascade"
            )
            _seed_campaign(conn)
            fixtures = (
                ("legacy_missing", "INFORMATION_RECEIVED"),
                ("legacy_with_contact", "INFORMATION_RECEIVED"),
                ("legacy_progressed", "PENDING_REVIEW"),
                ("legacy_paid", "PAID"),
                ("legacy_versioned", "INFORMATION_RECEIVED"),
                ("legacy_assigned", "INFORMATION_RECEIVED"),
                ("legacy_verified", "INFORMATION_RECEIVED"),
                ("legacy_external", "INFORMATION_RECEIVED"),
                ("legacy_audited", "INFORMATION_RECEIVED"),
            )
            for claim_id, status in fixtures:
                participant_id, _ = _insert_participant(conn, claim_id)
                conn.execute(
                    """insert into dino_dev.claim
                    (id,campaign_id,participant_id,claim_type,status,contact_submitted_at)
                    values(%s,%s,%s,'DRAW',%s,null)""",
                    (claim_id, CAMPAIGN_ID, participant_id, status),
                )
            conn.execute("update dino_dev.claim set version=2 where id='legacy_versioned'")
            conn.execute(
                "update dino_dev.claim set assignee_user_id=%s where id='legacy_assigned'",
                (str(uuid.uuid4()),),
            )
            conn.execute(
                "update dino_dev.claim set verification_status='PENDING',"
                "verification_reference='TEST_REF_legacy' where id='legacy_verified'"
            )
            conn.execute(
                "update dino_dev.claim set external_delivery=true where id='legacy_external'"
            )
            conn.execute(
                """insert into dino_dev.admin_audit
                (admin_user_id,action,target_type,target_id,event_id)
                values(%s,'CLAIM_UPDATE','claim','legacy_audited','evt_legacy_audited')""",
                (str(uuid.uuid4()),),
            )
            conn.execute(
                """insert into dino_dev.claim_contact
                (claim_id,recipient_name,contact,school)
                values('legacy_with_contact','TEST_user','01000000000','TEST_school')"""
            )

    def test_migration_backfills_only_unsubmitted_information_received_claims(self):
        self.assertGreaterEqual(config.SCHEMA_VERSION, CLAIM_FIX.name.split("_", 1)[0])
        _apply(self.dsn, CLAIM_FIX)
        _apply(self.dsn, CLAIM_FIX)

        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                "select id,status,contact_submitted_at from dino_dev.claim order by id"
            ).fetchall()
            default = conn.execute(
                "select column_default from information_schema.columns "
                "where table_schema='dino_dev' and table_name='claim' and column_name='status'"
            ).fetchone()[0]
            version_count = conn.execute(
                "select count(*) from dino_dev.schema_version where version='20260925125939'"
            ).fetchone()[0]

        by_id = {row[0]: row[1:] for row in rows}
        self.assertEqual(by_id["legacy_missing"], ("AWAITING_INFORMATION", None))
        self.assertEqual(by_id["legacy_progressed"], ("PENDING_REVIEW", None))
        self.assertEqual(by_id["legacy_paid"], ("PAID", None))
        self.assertEqual(by_id["legacy_with_contact"][0], "INFORMATION_RECEIVED")
        self.assertIsNotNone(by_id["legacy_with_contact"][1])
        for claim_id in (
            "legacy_versioned",
            "legacy_assigned",
            "legacy_verified",
            "legacy_external",
            "legacy_audited",
        ):
            self.assertEqual(by_id[claim_id], ("INFORMATION_RECEIVED", None))
        self.assertIn("AWAITING_INFORMATION", default)
        self.assertEqual(version_count, 1)


class ClaimOperationsFollowupTest(unittest.TestCase):
    DATABASE_NAME = "dino_phase1_v2_claim_fixes_operations"

    @classmethod
    def setUpClass(cls):
        cls.dsn = _database_dsn(cls.DATABASE_NAME)
        _recreate_database(cls.DATABASE_NAME)
        for migration in (FOUNDATION, ADDITIONS, CLAIM_FIX, ROOT / "supabase/migrations/20260926103809_allow_real_top3_contact.sql"):
            _apply(cls.dsn, migration)
        with psycopg.connect(cls.dsn) as conn:
            _seed_campaign(conn)

    @classmethod
    def tearDownClass(cls):
        _drop_database(cls.DATABASE_NAME)

    def setUp(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "truncate dino_dev.idempotency_request,dino_dev.analytics_event,"
                "dino_dev.admin_audit,dino_dev.claim_contact,dino_dev.claim,"
                "dino_dev.ranking_contact,dino_dev.participant,dino_dev.admin_member "
                "restart identity cascade"
            )
            self.participant_id, self.token_hash = _insert_participant(conn)
            self.admin_id = str(uuid.uuid4())
            conn.execute(
                "insert into dino_dev.admin_member(auth_user_id,display_name,permissions) "
                "values(%s,'TEST_admin',array['claims:read','claims:write'])",
                (self.admin_id,),
            )

    @contextlib.contextmanager
    def app_tx(self):
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("set local role dino_dev_app")
                yield conn

    def _insert_claim(self, claim_id, status=None, claim_type="DRAW", participant_id=None):
        participant_id = participant_id or self.participant_id
        with psycopg.connect(self.dsn) as conn:
            if status is None:
                conn.execute(
                    "insert into dino_dev.claim(id,campaign_id,participant_id,claim_type) "
                    "values(%s,%s,%s,%s)",
                    (claim_id, CAMPAIGN_ID, participant_id, claim_type),
                )
            else:
                conn.execute(
                    "insert into dino_dev.claim(id,campaign_id,participant_id,claim_type,status) "
                    "values(%s,%s,%s,%s,%s)",
                    (claim_id, CAMPAIGN_ID, participant_id, claim_type, status),
                )

    def _submit(self, claim_id, token_hash=None, body=None):
        if body is None:
            body = {
                "name": "TEST_user",
                "contact": "01000000000",
                "school": "TEST_school",
                "address": "TEST_address",
            }
        with self.app_tx() as conn:
            return operations.submit_claim(
                conn,
                claim_id,
                body,
                _context(participant_token_hash=token_hash or self.token_hash),
            )[1]

    def test_new_claim_waits_for_information_and_blocks_every_admin_patch(self):
        self._insert_claim("claim_waiting")
        with self.app_tx() as conn:
            listed = operations.claims(
                conn, _context(participant_token_hash=self.token_hash)
            )[1]["claims"]
            with self.assertRaises(operations.DomainError) as stale:
                operations.admin_claim_patch(
                    conn,
                    "claim_waiting",
                    {"status": "PENDING_REVIEW", "expected_version": 0, "event_id": "evt_stale"},
                    _context(admin_user_id=self.admin_id),
                )
        self.assertEqual(listed[0]["status"], "AWAITING_INFORMATION")
        self.assertEqual(listed[0]["claim_type"], "DRAW")
        self.assertEqual(stale.exception.code, "VERSION_CONFLICT")

        with self.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as blocked:
                operations.admin_claim_patch(
                    conn,
                    "claim_waiting",
                    {
                        "status": "PENDING_REVIEW",
                        "expected_version": 1,
                        "external_delivery": True,
                        "event_id": "evt_blocked",
                    },
                    _context(admin_user_id=self.admin_id),
                )
        self.assertEqual(blocked.exception.code, "CLAIM_INFORMATION_REQUIRED")
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                "select status,version,external_delivery,assignee_user_id "
                "from dino_dev.claim where id='claim_waiting'"
            ).fetchone()
        self.assertEqual(row, ("AWAITING_INFORMATION", 1, False, None))

    def test_submission_is_concurrent_safe_and_enables_review(self):
        self._insert_claim("claim_submit")
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:
            results = list(pool.map(lambda _: self._submit("claim_submit"), range(2)))

        self.assertEqual({result["status"] for result in results}, {"INFORMATION_RECEIVED"})
        self.assertEqual(len({result["submitted_at"] for result in results}), 1)
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                "select status,contact_submitted_at,version from dino_dev.claim "
                "where id='claim_submit'"
            ).fetchone()
            contacts = conn.execute(
                "select count(*) from dino_dev.claim_contact where claim_id='claim_submit'"
            ).fetchone()[0]
        self.assertEqual((row[0], row[2], contacts), ("INFORMATION_RECEIVED", 1, 1))
        self.assertIsNotNone(row[1])

        with self.app_tx() as conn:
            reviewed = operations.admin_claim_patch(
                conn,
                "claim_submit",
                {"status": "PENDING_REVIEW", "expected_version": 1, "event_id": "evt_review"},
                _context(admin_user_id=self.admin_id),
            )[1]
        self.assertEqual((reviewed["status"], reviewed["version"]), ("PENDING_REVIEW", 2))

    def test_new_submission_requires_school_without_partial_mutation_and_replay_stays_idempotent(self):
        self._insert_claim("claim_school_required")
        base_body = {
            "name": "TEST_user",
            "contact": "01000000000",
            "address": "TEST_address",
        }
        invalid_schools = (
            (None, "VALIDATION_ERROR"),
            ("", "VALIDATION_ERROR"),
            ("   ", "VALIDATION_ERROR"),
            ("대학교", "SYNTHETIC_DATA_REQUIRED"),
        )
        for school, expected_code in invalid_schools:
            with self.subTest(school=school):
                with self.assertRaises(operations.DomainError) as rejected:
                    self._submit("claim_school_required", body={**base_body, "school": school})
                self.assertEqual(rejected.exception.code, expected_code)

                with psycopg.connect(self.dsn) as conn:
                    claim = conn.execute(
                        "select status,contact_submitted_at from dino_dev.claim "
                        "where id='claim_school_required'"
                    ).fetchone()
                    contacts = conn.execute(
                        "select count(*) from dino_dev.claim_contact "
                        "where claim_id='claim_school_required'"
                    ).fetchone()[0]
                    events = conn.execute(
                        "select count(*) from dino_dev.analytics_event "
                        "where participant_id=%s and event_name='claim_information_received'",
                        (self.participant_id,),
                    ).fetchone()[0]
                self.assertEqual(claim, ("AWAITING_INFORMATION", None))
                self.assertEqual((contacts, events), (0, 0))

        submitted = self._submit(
            "claim_school_required", body={**base_body, "school": "TEST_school"}
        )
        replay = self._submit("claim_school_required", body={**base_body, "school": ""})
        self.assertEqual(replay, submitted)
        with psycopg.connect(self.dsn) as conn:
            row = conn.execute(
                "select c.status,c.contact_submitted_at is not null,cc.school "
                "from dino_dev.claim c join dino_dev.claim_contact cc on cc.claim_id=c.id "
                "where c.id='claim_school_required'"
            ).fetchone()
            events = conn.execute(
                "select count(*) from dino_dev.analytics_event "
                "where participant_id=%s and event_name='claim_information_received'",
                (self.participant_id,),
            ).fetchone()[0]
        self.assertEqual(row, ("INFORMATION_RECEIVED", True, "TEST_school"))
        self.assertEqual(events, 1)

    def test_late_submission_never_rolls_back_progressed_or_terminal_status(self):
        self._insert_claim("claim_progressed", "PENDING_REVIEW")
        with self.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as blocked:
                operations.admin_claim_patch(
                    conn,
                    "claim_progressed",
                    {"status": "CONTACTED", "expected_version": 1, "event_id": "evt_no_contact"},
                    _context(admin_user_id=self.admin_id),
                )
        self.assertEqual(blocked.exception.code, "CLAIM_INFORMATION_REQUIRED")

        self._insert_claim("claim_paid", "PAID", "RANKING")
        for claim_id, status in (("claim_progressed", "PENDING_REVIEW"), ("claim_paid", "PAID")):
            first = self._submit(claim_id)
            replay = self._submit(claim_id)
            self.assertEqual(first, replay)
            self.assertEqual(first["status"], status)

        with self.app_tx() as conn:
            contacted = operations.admin_claim_patch(
                conn,
                "claim_progressed",
                {"status": "CONTACTED", "expected_version": 1, "event_id": "evt_after_contact"},
                _context(admin_user_id=self.admin_id),
            )[1]
        self.assertEqual(contacted["status"], "CONTACTED")

        with psycopg.connect(self.dsn) as conn:
            rows = conn.execute(
                "select id,status,contact_submitted_at from dino_dev.claim order by id"
            ).fetchall()
            contacts = conn.execute("select count(*) from dino_dev.claim_contact").fetchone()[0]
        self.assertEqual([(row[0], row[1]) for row in rows], [("claim_paid", "PAID"), ("claim_progressed", "CONTACTED")])
        self.assertTrue(all(row[2] is not None for row in rows))
        self.assertEqual(contacts, 2)

    def test_ranking_submission_sets_information_received_without_state_regression(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "insert into dino_dev.ranking_contact(participant_id) values(%s)",
                (self.participant_id,),
            )
        with self.app_tx() as conn:
            result = operations.ranking_profile_post(
                conn,
                {"name": "TEST_ranker", "contact": "01000000000", "school": "TEST_school",
                 "consent": True, "notice_version": "top3-contact-v1"},
                _context(participant_token_hash=self.token_hash),
            )[1]
        with psycopg.connect(self.dsn) as conn:
            claim = conn.execute(
                "select status,contact_submitted_at from dino_dev.claim where id=%s",
                (result["claim_id"],),
            ).fetchone()
        self.assertEqual(claim[0], "INFORMATION_RECEIVED")
        self.assertIsNotNone(claim[1])

    def test_missing_contact_nonterminal_states_accept_information_then_continue(self):
        cases = (
            ("ON_HOLD", "PENDING_REVIEW"),
            ("NO_RESPONSE", "PENDING_REVIEW"),
            ("CONTACTED", "PAID"),
        )
        for index, (initial_status, next_status) in enumerate(cases):
            with psycopg.connect(self.dsn) as conn:
                participant_id, token_hash = _insert_participant(
                    conn, f"repair_{initial_status.lower()}_{index}"
                )
            claim_id = f"claim_repair_{initial_status.lower()}"
            self._insert_claim(claim_id, initial_status, participant_id=participant_id)

            submitted = self._submit(claim_id, token_hash)
            self.assertEqual(submitted["status"], initial_status)

            with self.app_tx() as conn:
                continued = operations.admin_claim_patch(
                    conn,
                    claim_id,
                    {
                        "status": next_status,
                        "expected_version": 1,
                        "event_id": f"evt_continue_{initial_status.lower()}",
                    },
                    _context(admin_user_id=self.admin_id),
                )[1]
            self.assertEqual(continued["status"], next_status)


if __name__ == "__main__":
    unittest.main()
