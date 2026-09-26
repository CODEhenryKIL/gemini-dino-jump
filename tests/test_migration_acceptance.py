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

PHASE2 = ROOT / "supabase/migrations/20260925140902_phase2_game_versions_and_tracking.sql"
GAME_V21 = ROOT / "supabase/migrations/20260926093414_game_rules_v21.sql"

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
        self.database.apply(PHASE2)
        self.database.apply(GAME_V21)

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
            [("20260925083548",), ("20260925092759",), ("20260925125939",), ("20260925140902",), ("20260926093414",)],
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
        self.database.apply(PHASE2)
        self.database.apply(GAME_V21)
        self.database.apply(CLAIM_FIX)
        self.database.apply(PHASE2)
        self.database.apply(GAME_V21)

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
                ("20260925140902", 1),
                ("20260926093414", 1),
            ],
        )
        self.assertIn(("fault_review_status",), columns)
        self.assertEqual(len(policies), 4)
        self.assert_sentinel_preserved()

    def test_v21_extends_version_constraints_without_mixing_v2_scores(self):
        for migration in (FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21):
            self.database.apply(migration)
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute("""insert into dino_dev.campaign(id,title,game_version,benefit_url,probability_version)
              values('v21-test','v21','2.1.0','https://gemini.google.com/students','test')""")
            conn.execute("""insert into dino_dev.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
              values('p_v21migration000000000000000000','v21-test',repeat('a',64),clock_timestamp()+interval '1 day','v21','V21migration1','test')""")
            for version, suffix, score in (("2.0.0", "v20", 800), ("2.1.0", "v21", 700)):
                session_id = "gs_" + suffix
                conn.execute("""insert into dino_dev.game_session
                  (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
                   ticket_refund_status,expires_at,score,valid_ticks,verification_result,end_reason,finished_at,environment)
                  values(%s,'p_v21migration000000000000000000','v21-test',%s,1,%s,'FINISHED','INITIAL',
                   'NOT_DUE',clock_timestamp()+interval '1 minute',%s,600,'VERIFIED','COLLISION',clock_timestamp(),'test')""",
                  (session_id, "key_" + suffix, version, score))
                conn.execute("""insert into dino_dev.versioned_best_score
                  (participant_id,game_version,session_id,score,achieved_at)
                  values('p_v21migration000000000000000000',%s,%s,%s,clock_timestamp())""",
                  (version, session_id, score))
            scores = conn.execute("""select game_version,score from dino_dev.versioned_best_score
              where participant_id='p_v21migration000000000000000000' order by game_version""").fetchall()
        self.assertEqual(scores, [("2.0.0", 800), ("2.1.0", 700)])
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
