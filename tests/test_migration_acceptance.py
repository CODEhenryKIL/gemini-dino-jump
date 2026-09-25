import os
import re
import subprocess
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg import sql


ROOT = Path(__file__).resolve().parents[1]
PG_BIN = Path("/private/tmp/dino-phase1-v2-postgres/bin")
ADMIN_DSN = os.getenv(
    "PHASE1_AUDIT_ADMIN_DATABASE_URL",
    "postgresql://postgres@127.0.0.1:55433/postgres",
)
FOUNDATION = ROOT / "supabase/migrations/20260925083548_phase1_dino_dev_foundation.sql"
ADDITIONS = ROOT / "supabase/migrations/20260925092759_phase1_acceptance_additions.sql"
CLAIM_FIX = ROOT / "supabase/migrations/20260925125939_add_awaiting_claim_information_status.sql"


def _guard_admin_dsn():
    parsed = urlsplit(ADMIN_DSN)
    if (
        parsed.scheme not in {"postgres", "postgresql"}
        or parsed.hostname not in {"127.0.0.1", "localhost", "::1"}
        or parsed.port != 55433
        or parsed.username != "postgres"
        or parsed.path != "/postgres"
        or parsed.query
        or parsed.fragment
    ):
        raise RuntimeError(
            "migration audit requires postgres on loopback port 55433 and database postgres"
        )


def _guard_database_name(name):
    if not re.fullmatch(r"dino_phase1_audit_[a-z0-9_]+", name):
        raise RuntimeError("refusing database operation outside dino_phase1_audit_ prefix")


class TemporaryAuditDatabase:
    def __init__(self):
        self.name = f"dino_phase1_audit_migration_{os.getpid()}_{uuid.uuid4().hex}"
        _guard_database_name(self.name)
        self.dsn = f"postgresql://postgres@127.0.0.1:55433/{self.name}"

    def create(self):
        _guard_admin_dsn()
        _guard_database_name(self.name)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(self.name)))

    def drop(self):
        _guard_admin_dsn()
        _guard_database_name(self.name)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(
                "select pg_terminate_backend(pid) from pg_stat_activity "
                "where datname=%s and pid<>pg_backend_pid()",
                (self.name,),
            )
            conn.execute(sql.SQL("drop database if exists {}").format(sql.Identifier(self.name)))

    def apply(self, migration, *, succeeds=True):
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
                self.name,
                "-f",
                str(migration),
            ],
            text=True,
            capture_output=True,
            check=False,
            env={**os.environ, "PGOPTIONS": "-c client_min_messages=warning"},
        )
        if succeeds and result.returncode:
            raise AssertionError(
                f"migration failed: {migration.name}\n{result.stdout}\n{result.stderr}"
            )
        if not succeeds and result.returncode == 0:
            raise AssertionError(f"migration unexpectedly succeeded: {migration.name}")
        return result


class MigrationAcceptanceTest(unittest.TestCase):
    def setUp(self):
        self.database = TemporaryAuditDatabase()
        self.database.create()
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute("create schema unrelated")
            conn.execute(
                "create table unrelated.sentinel(id integer primary key, payload text not null)"
            )
            conn.execute("insert into unrelated.sentinel values (7, 'keep-me')")

    def tearDown(self):
        self.database.drop()

    def assert_sentinel_preserved(self):
        with psycopg.connect(self.database.dsn) as conn:
            row = conn.execute(
                "select id,payload from unrelated.sentinel"
            ).fetchone()
        self.assertEqual(row, (7, "keep-me"))

    def test_full_migration_stack_applies_to_database_without_dino_schema(self):
        self.database.apply(FOUNDATION)
        self.database.apply(ADDITIONS)
        self.database.apply(CLAIM_FIX)

        with psycopg.connect(self.database.dsn) as conn:
            versions = conn.execute(
                "select version from dino_dev.schema_version order by version"
            ).fetchall()
            required_tables = conn.execute(
                "select tablename from pg_tables where schemaname='dino_dev'"
            ).fetchall()
            rls = conn.execute(
                "select relrowsecurity,relforcerowsecurity from pg_class c "
                "join pg_namespace n on n.oid=c.relnamespace "
                "where n.nspname='dino_dev' and c.relname='participant'"
            ).fetchone()

        self.assertEqual(
            versions,
            [("20260925083548",), ("20260925092759",), ("20260925125939",)],
        )
        self.assertTrue(
            {"participant", "game_session", "ranking_snapshot"}.issubset(
                {row[0] for row in required_tables}
            )
        )
        self.assertEqual(rls, (True, True))
        self.assert_sentinel_preserved()

    def test_additions_apply_to_foundation_only_and_are_idempotent(self):
        self.database.apply(FOUNDATION)
        self.database.apply(ADDITIONS)
        self.database.apply(ADDITIONS)
        self.database.apply(CLAIM_FIX)
        self.database.apply(CLAIM_FIX)

        with psycopg.connect(self.database.dsn) as conn:
            versions = conn.execute(
                "select version,count(*) from dino_dev.schema_version "
                "group by version order by version"
            ).fetchall()
            columns = conn.execute(
                "select column_name from information_schema.columns "
                "where table_schema='dino_dev' and table_name='game_session'"
            ).fetchall()
            policies = conn.execute(
                "select tablename,policyname from pg_policies "
                "where schemaname='dino_dev' and tablename like 'ranking_snapshot%'"
            ).fetchall()

        self.assertEqual(
            versions,
            [
                ("20260925083548", 1),
                ("20260925092759", 1),
                ("20260925125939", 1),
            ],
        )
        self.assertIn(("fault_review_status",), columns)
        self.assertEqual(len(policies), 4)
        self.assert_sentinel_preserved()

    def test_foundation_reapply_fails_without_damaging_existing_data(self):
        self.database.apply(FOUNDATION)
        result = self.database.apply(FOUNDATION, succeeds=False)

        self.assertRegex(result.stderr.lower(), r"already exists|duplicate key")
        with psycopg.connect(self.database.dsn) as conn:
            version_count = conn.execute(
                "select count(*) from dino_dev.schema_version "
                "where version='20260925083548'"
            ).fetchone()[0]
            participant_exists = conn.execute(
                "select to_regclass('dino_dev.participant') is not null"
            ).fetchone()[0]
        self.assertEqual(version_count, 1)
        self.assertTrue(participant_exists)
        self.assert_sentinel_preserved()


if __name__ == "__main__":
    unittest.main()
