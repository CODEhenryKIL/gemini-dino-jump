import importlib.util
import ipaddress
import json
import os
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from urllib.parse import urlparse

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
SCRIPT = ROOT / "scripts" / "prepare_phase1_cohort.py"
SPEC = importlib.util.spec_from_file_location("prepare_phase1_cohort", SCRIPT)
cohort = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = cohort
SPEC.loader.exec_module(cohort)

LOAD_SPEC = importlib.util.spec_from_file_location(
    "phase1_load_for_cohort_test", ROOT / "scripts" / "phase1_load.py"
)
load = importlib.util.module_from_spec(LOAD_SPEC)
sys.modules[LOAD_SPEC.name] = load
LOAD_SPEC.loader.exec_module(load)


REMOTE_URL = "https://gemini-dino-phase1-preview.vercel.app"
DEPLOYMENT_ID = "dpl_phase1_cohort_test"
PEPPER = "cohort-test-pepper-0123456789abcdef"
DESTRUCTIVE_TEST_DATABASE = "/dino_phase1_v2_concurrency"


def validate_destructive_test_dsn(dsn):
    parsed = urlparse(dsn)
    try:
        loopback = parsed.hostname == "localhost" or ipaddress.ip_address(
            parsed.hostname or ""
        ).is_loopback
    except ValueError:
        loopback = False
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or not loopback
        or parsed.path != DESTRUCTIVE_TEST_DATABASE
        or parsed.username != "postgres"
        or parsed.params
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "Destructive cohort tests require the local owner DSN "
            "postgres@loopback/dino_phase1_v2_concurrency"
        )
    return dsn


class CohortGuardTest(unittest.TestCase):
    def remote_target(self):
        return cohort.validate_target(
            "remote",
            REMOTE_URL,
            DEPLOYMENT_ID,
            cohort.APPROVED_PREVIEW_PROJECT_REF,
            "test",
        )

    def test_cli_does_not_accept_plaintext_dsn_or_pepper_arguments(self):
        destinations = {action.dest for action in cohort.build_parser()._actions}
        self.assertNotIn("database_url", destinations)
        self.assertNotIn("pepper", destinations)
        self.assertIn("database_url_file", destinations)
        self.assertIn("pepper_file", destinations)

    def test_remote_and_local_target_guards_are_distinct_and_fail_closed(self):
        remote = self.remote_target()
        self.assertEqual(remote["environment"], "preview")
        local = cohort.validate_target(
            "local", "http://127.0.0.1:3000", "local-test", "local", "test"
        )
        self.assertEqual(local["environment"], "test")
        invalid = [
            ("remote", "https://example.com", DEPLOYMENT_ID, cohort.APPROVED_PREVIEW_PROJECT_REF),
            ("remote", REMOTE_URL, DEPLOYMENT_ID, "wrong-project"),
            ("local", REMOTE_URL, "local-test", "local"),
        ]
        for mode, url, deployment, project_ref in invalid:
            with self.subTest(mode=mode, url=url, project_ref=project_ref):
                with self.assertRaises(cohort.PreparationError):
                    cohort.validate_target(mode, url, deployment, project_ref, "test")

    def test_manifest_is_private_exact_unique_and_load_runner_compatible(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            manifest, created = cohort.ensure_manifest(
                path, self.remote_target(), cohort.DEFAULT_CAMPAIGN_ID
            )
            self.assertTrue(created)
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            self.assertEqual(len(manifest["participants"]), 5_000)
            self.assertEqual(
                len({entry["cookie"] for entry in manifest["participants"]}), 5_000
            )
            self.assertEqual(
                len({entry["participant_id"] for entry in manifest["participants"]}), 5_000
            )
            loaded = load.load_cohort(
                path,
                "remote",
                REMOTE_URL,
                cohort.APPROVED_PREVIEW_PROJECT_REF,
                DEPLOYMENT_ID,
            )
            self.assertEqual(len(loaded["participants"]), 5_000)
            self.assertEqual(loaded["preparation_api_calls"], 0)

    def test_existing_prepared_manifest_recovers_without_rotating_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            first, created = cohort.ensure_manifest(
                path, self.remote_target(), cohort.DEFAULT_CAMPAIGN_ID
            )
            original = path.read_bytes()
            first_cookie = first["participants"][0]["cookie"]
            second, created_again = cohort.ensure_manifest(
                path, self.remote_target(), cohort.DEFAULT_CAMPAIGN_ID
            )
            self.assertTrue(created)
            self.assertFalse(created_again)
            self.assertEqual(path.read_bytes(), original)
            self.assertEqual(second["participants"][0]["cookie"], first_cookie)
            self.assertEqual(second["state"], "PREPARED")

    def test_private_secret_file_rejects_group_or_world_permissions(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "secret"
            path.write_text("private", encoding="utf-8")
            path.chmod(0o644)
            with self.assertRaises(cohort.PreparationError):
                cohort.private_text(path, "Secret")
            path.chmod(0o600)
            self.assertEqual(cohort.private_text(path, "Secret"), "private")

    def test_remote_dsn_requires_exact_scoped_pooler_role(self):
        valid = (
            "postgresql://dino_dev_app."
            + cohort.APPROVED_PREVIEW_PROJECT_REF
            + ":secret@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres"
        )
        cohort.validate_dsn(valid, "remote", cohort.APPROVED_PREVIEW_PROJECT_REF)
        with self.assertRaises(cohort.PreparationError):
            cohort.validate_dsn(
                valid.replace("dino_dev_app.", "postgres."),
                "remote",
                cohort.APPROVED_PREVIEW_PROJECT_REF,
            )

    def test_destructive_postgres_test_dsn_requires_local_dedicated_owner_database(self):
        valid = [
            "postgres://postgres@127.0.0.1:55433/dino_phase1_v2_concurrency",
            "postgresql://postgres:secret@localhost:55433/dino_phase1_v2_concurrency",
            "postgresql://postgres@[::1]:55433/dino_phase1_v2_concurrency",
        ]
        for dsn in valid:
            with self.subTest(dsn=dsn):
                self.assertEqual(validate_destructive_test_dsn(dsn), dsn)

        invalid = [
            "postgresql://postgres@db.example.com:5432/dino_phase1_v2_concurrency",
            "postgresql://postgres@127.0.0.1:55433/postgres",
            "postgresql://dino_dev_app@127.0.0.1:55433/dino_phase1_v2_concurrency",
            "postgresql://postgres@127.0.0.1:55433/dino_phase1_v2_concurrency?sslmode=require",
        ]
        for dsn in invalid:
            with self.subTest(dsn=dsn):
                with self.assertRaises(RuntimeError):
                    validate_destructive_test_dsn(dsn)


@unittest.skipUnless(
    os.getenv("PHASE1_COHORT_TEST_DATABASE_URL"),
    "Set PHASE1_COHORT_TEST_DATABASE_URL to run the isolated PostgreSQL cohort test",
)
class CohortPostgresTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.dsn = validate_destructive_test_dsn(
            os.environ["PHASE1_COHORT_TEST_DATABASE_URL"]
        )

    def setUp(self):
        self._clear_database()

    def tearDown(self):
        self._clear_database()

    def _clear_database(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "truncate dino_dev.rate_limit_bucket,dino_dev.idempotency_request,"
                "dino_dev.analytics_event,dino_dev.admin_audit,dino_dev.claim_contact,"
                "dino_dev.claim,dino_dev.inventory_history,dino_dev.draw,"
                "dino_dev.ranking_contact,dino_dev.best_score,dino_dev.game_session,"
                "dino_dev.invitation_reward,dino_dev.invitation_visit,dino_dev.ticket_ledger,"
                "dino_dev.bootstrap,dino_dev.observation,dino_dev.participant restart identity cascade"
            )

    def test_real_postgres_resume_is_idempotent_and_does_not_reset_balance(self):
        target = cohort.validate_target(
            "local", "http://127.0.0.1:3000", "local-cohort", "local", "test"
        )
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            manifest, _created = cohort.ensure_manifest(
                path, target, cohort.DEFAULT_CAMPAIGN_ID
            )
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                with conn.transaction():
                    conn.execute("set local role dino_dev_app")
                    cohort.validate_database_guard(
                        conn, "test", "local", cohort.DEFAULT_CAMPAIGN_ID
                    )
                    first = cohort.seed_cohort(conn, manifest, PEPPER)
            self.assertEqual(first, {"inserted": 5_000, "existing": 0, "total": 5_000})

            participant_id = manifest["participants"][0]["participant_id"]
            with psycopg.connect(self.dsn) as conn:
                conn.execute(
                    "update dino_dev.participant set initial_balance=0 where id=%s",
                    (participant_id,),
                )
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                with conn.transaction():
                    conn.execute("set local role dino_dev_app")
                    cohort.validate_database_guard(
                        conn, "test", "local", cohort.DEFAULT_CAMPAIGN_ID
                    )
                    second = cohort.seed_cohort(conn, manifest, PEPPER)
            with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
                state = conn.execute(
                    "select initial_balance from dino_dev.participant where id=%s",
                    (participant_id,),
                ).fetchone()
                ledger = conn.execute(
                    "select count(*) n from dino_dev.ticket_ledger "
                    "where source_type='INITIAL_GRANT' and source_id='initial'"
                ).fetchone()["n"]
            self.assertEqual(second, {"inserted": 0, "existing": 5_000, "total": 5_000})
            self.assertEqual(state["initial_balance"], 0)
            self.assertEqual(ledger, 5_000)


if __name__ == "__main__":
    unittest.main()
