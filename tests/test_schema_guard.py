import sys
import unittest
from pathlib import Path
from types import SimpleNamespace

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import config
import db

sys.path.insert(0, str(ROOT / "tests"))
from test_migration_acceptance import ADDITIONS, CLAIM_FIX, FOUNDATION, GAME_V21, PHASE2, REAL_TOP3_CONTACT, PG_BIN, TemporaryAuditDatabase

import psycopg
from psycopg.rows import dict_row


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, versions):
        self.versions = set(versions)
        self.query = None
        self.params = None

    def execute(self, query, params):
        self.query = query
        self.params = params
        required = set(params[0])
        return FakeResult({
            "environment": "test",
            "project_ref": "local",
            "schema_name": config.SCHEMA_NAME,
            "synthetic_only": True,
            "test_seed": True,
            "campaign_id": "phase2-test",
            "connection_role": config.APP_ROLE,
            "required_versions_present": required.issubset(self.versions),
        })


SETTINGS = SimpleNamespace(environment="test", project_ref="local", synthetic_only=True)


class SchemaGuardTest(unittest.TestCase):
    def test_latest_present_but_claim_status_migration_absent_is_rejected(self):
        versions = set(config.REQUIRED_SCHEMA_VERSIONS)
        versions.remove("20260925125939")
        self.assertIn(config.SCHEMA_VERSION, versions)
        conn = FakeConnection(versions)
        with self.assertRaisesRegex(config.ConfigurationError, "DATABASE_NOT_PROVISIONED"):
            db.check_environment(conn, SETTINGS)
        self.assertIn("unnest", conn.query.lower())
        self.assertEqual(tuple(conn.params[0]), config.REQUIRED_SCHEMA_VERSIONS)

    def test_all_required_versions_pass_and_schema_version_remains_latest(self):
        conn = FakeConnection(config.REQUIRED_SCHEMA_VERSIONS)
        guard = db.check_environment(conn, SETTINGS)
        self.assertEqual(config.SCHEMA_VERSION, "20260926103809")
        self.assertNotIn("required_versions_present", guard)
        self.assertEqual(guard["campaign_id"], "phase2-test")


@unittest.skipUnless((PG_BIN / "psql").exists(), "isolated local PostgreSQL fixture is unavailable")
class IsolatedPostgresSchemaGuardTest(unittest.TestCase):
    def setUp(self):
        self.audit_database = TemporaryAuditDatabase()
        try:
            self.audit_database.create()
        except psycopg.OperationalError as error:
            self.skipTest(f"isolated local PostgreSQL fixture is unavailable: {error}")
        for migration in (FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT):
            self.audit_database.apply(migration)
        with psycopg.connect(self.audit_database.dsn, row_factory=dict_row) as conn:
            conn.execute("""insert into dino_dev.campaign(id,title,game_version,benefit_url,probability_version)
              values('phase2-test','Phase 2 test','2.0.0','https://gemini.google.com/students','test-v1')""")
            conn.execute("""insert into dino_dev.environment_guard(environment,project_ref,test_seed,campaign_id)
              values('test','local',true,'phase2-test')""")

    def tearDown(self):
        if hasattr(self, "audit_database"):
            self.audit_database.drop()

    def test_missing_prerequisite_is_rejected_and_rollback_restores_full_stack(self):
        with psycopg.connect(self.audit_database.dsn, row_factory=dict_row) as conn:
            conn.execute("delete from dino_dev.schema_version where version='20260925125939'")
            conn.execute("set local role dino_dev_app")
            with self.assertRaisesRegex(config.ConfigurationError, "DATABASE_NOT_PROVISIONED"):
                db.check_environment(conn, SETTINGS)
            conn.rollback()

            conn.execute("set local role dino_dev_app")
            guard = db.check_environment(conn, SETTINGS)
            self.assertEqual(guard["campaign_id"], "phase2-test")
            conn.rollback()


if __name__ == "__main__":
    unittest.main()
