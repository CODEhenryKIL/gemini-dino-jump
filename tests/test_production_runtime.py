import copy
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import secrets
import sys
import unittest
from pathlib import Path
from unittest import mock

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "scripts"))
sys.path.insert(0, str(ROOT / "tests"))

import auth
import db
import metrics
import operations
import share_page
from config import Settings, schema_context
from prepare_production import provision, render_schema
from test_migration_acceptance import (
    ADDITIONS,
    CLAIM_DRAFT,
    CLAIM_FIX,
    FOUNDATION,
    GAME_V21,
    INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK,
    LOW_SCORE_REFUND,
    PHASE2,
    PHASE3,
    RANKING_FINALIZATION,
    REAL_TOP3_CONTACT,
    TemporaryAuditDatabase,
)
from test_production_schema import approved_manifest


UTC = dt.timezone.utc
PEPPER = "production-runtime-test-pepper-0123456789"
MIGRATIONS = (
    FOUNDATION,
    ADDITIONS,
    CLAIM_FIX,
    PHASE2,
    GAME_V21,
    REAL_TOP3_CONTACT,
    CLAIM_DRAFT,
    LOW_SCORE_REFUND,
    KAKAO_SHARE_WEBHOOK,
    INTERRUPTED_AND_SHARE,
    PHASE3,
    RANKING_FINALIZATION,
)
SEED = ROOT / "supabase/seed_dino_dev.sql"


@unittest.skipUnless(
    Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(),
    "isolated local PostgreSQL fixture is unavailable",
)
class ProductionRuntimeSmokeTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        try:
            cls.database.create()
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f"isolated local PostgreSQL fixture is unavailable: {error}") from error
        for migration in MIGRATIONS:
            cls.database.apply(migration)
        with psycopg.connect(cls.database.dsn) as conn:
            conn.execute(
                "insert into dino_dev.environment_guard(environment,project_ref,test_seed) values('test','local',false)"
            )
        cls.database.apply(SEED)
        with psycopg.connect(cls.database.dsn) as conn:
            cls.beta_before = cls._beta_snapshot(conn)
        with psycopg.connect(cls.database.dsn, autocommit=True) as conn:
            conn.execute(render_schema(), prepare=False)

        cls.manifest = approved_manifest()
        payload = json.dumps(
            cls.manifest, ensure_ascii=False, separators=(",", ":"), sort_keys=True
        ).encode()
        cls.digest = hashlib.sha256(payload).hexdigest()
        with psycopg.connect(cls.database.dsn) as conn:
            provision(conn, copy.deepcopy(cls.manifest), cls.digest)

        cls.now = dt.datetime.now(UTC)
        cls.opens_at = cls.now - dt.timedelta(hours=1)
        cls.closes_at = cls.now + dt.timedelta(hours=1)
        cls.claim_closes_at = cls.now + dt.timedelta(hours=2)
        with psycopg.connect(cls.database.dsn) as conn:
            campaign = conn.execute(
                "select settings from dino_prod.campaign where id=%s",
                (cls.manifest["campaign"]["id"],),
            ).fetchone()
            settings = dict(campaign[0])
            settings["claim_submission_cutoff"] = cls.claim_closes_at.isoformat()
            settings["ranking_finish_acceptance_cutoff"] = cls.closes_at.isoformat()
            conn.execute(
                """update dino_prod.campaign set status='ACTIVE',opens_at=%s,closes_at=%s,settings=%s::jsonb
                where id=%s""",
                (cls.opens_at, cls.closes_at, json.dumps(settings), cls.manifest["campaign"]["id"]),
            )
            conn.execute(
                """update dino_prod.environment_guard set event_enabled=true,
                campaign_opens_at=%s,campaign_closes_at=%s,claim_closes_at=%s""",
                (cls.opens_at, cls.closes_at, cls.claim_closes_at),
            )
        cls.settings = Settings(
            environment="production",
            database_url=cls.database.dsn,
            project_ref="igfrnexknwtiljdqjrbp",
            base_url="https://production-runtime.test",
            benefit_url="https://VQyu3J.s.gy/Game",
            supabase_url="https://igfrnexknwtiljdqjrbp.supabase.co",
            publishable_key="sb_publishable_production_runtime_test_key",
            token_pepper=PEPPER,
            allowed_origins=frozenset({"https://production-runtime.test"}),
            deployment="production-runtime-test",
            synthetic_only=False,
            schema_name="dino_prod",
            app_role="dino_prod_app",
            game_version="2.1.0",
            campaign_id=cls.manifest["campaign"]["id"],
            event_enabled=True,
            launch_manifest_sha256=cls.digest,
            campaign_opens_at=cls.opens_at.isoformat(),
            campaign_closes_at=cls.closes_at.isoformat(),
            claim_closes_at=cls.claim_closes_at.isoformat(),
            draw_pool_total=5000,
            draw_prize_quantity=77,
            ranking_prize_quantity=3,
        )

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    @staticmethod
    def _beta_snapshot(conn):
        return {
            table: conn.execute(f"select count(*) from dino_dev.{table}").fetchone()[0]
            for table in (
                "participant",
                "observation",
                "game_session",
                "draw",
                "claim",
                "analytics_event",
                "rate_limit_bucket",
                "inventory_item",
            )
        }

    @contextlib.contextmanager
    def app_tx(self):
        with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
            with conn.transaction(), schema_context(self.settings):
                conn.execute("set local role dino_prod_app")
                yield conn

    def context(self, **extra):
        value = {
            "environment": "production",
            "deployment": self.settings.deployment,
            "event_version": "phase3-v1",
            "game_version": "2.1.0",
            "campaign_id": self.settings.campaign_id,
            "base_url": self.settings.base_url,
            "project_ref": self.settings.project_ref,
            "request_id": "production-runtime-test",
            "request_received_at": self.now,
            "invite_active_ms": 3000,
            "participant_cookie_max_age": 2592000,
            "ip_subject": "production-runtime-ip",
            "event_enabled": True,
            "preview_unlimited_play": False,
        }
        value.update(extra)
        return value

    def bootstrap_participant(self):
        event_id = "event_" + secrets.token_hex(12)
        observation_id = "obs_" + secrets.token_hex(12)
        idempotency_key = secrets.token_urlsafe(32)
        bootstrap = hmac.new(
            PEPPER.encode(), ("bootstrap:" + event_id).encode(), hashlib.sha256
        ).hexdigest()
        raw_token = auth.deterministic_participant_token(bootstrap, PEPPER)
        nonce = secrets.token_urlsafe(32)
        ctx = self.context(
            idempotency_key=idempotency_key,
            bootstrap_token=bootstrap,
            bootstrap_token_hash=auth.token_hash(bootstrap, PEPPER),
            new_participant_token=raw_token,
            new_participant_token_hash=auth.token_hash(raw_token, PEPPER),
            participant_token_hash="",
            invite_nonce=nonce,
            invite_nonce_hash=auth.token_hash(nonce, PEPPER),
        )
        with self.app_tx() as conn:
            operations.dispatch(
                conn,
                "POST",
                "/api/observations",
                {"observation_id": observation_id, "event_id": event_id},
                {},
                ctx,
            )
            status, result = operations.dispatch(
                conn,
                "POST",
                "/api/participants/anonymous",
                {"bootstrap_token": bootstrap, "observation_id": observation_id},
                {},
                ctx,
            )
        self.assertEqual(status, 201)
        return raw_token, result["participant"]

    def test_production_runtime_routes_and_data_are_isolated_from_beta(self):
        raw_token, participant = self.bootstrap_participant()
        participant_hash = auth.token_hash(raw_token, PEPPER)
        base_ctx = self.context(participant_token_hash=participant_hash)

        with self.app_tx() as conn:
            guard = db.check_environment(conn, self.settings)
            self.assertEqual((guard["environment"], guard["schema_name"], guard["synthetic_only"]), ("production", "dino_prod", False))
            status, me = operations.dispatch(conn, "GET", "/api/me", {}, {}, base_ctx)
            self.assertEqual((status, me["participant"]["id"]), (200, participant["id"]))
            before_ticket = me["tickets"]["available_total"]
            with self.assertRaises(operations.DomainError) as disabled:
                operations.dispatch(
                    conn,
                    "POST",
                    "/api/game-sessions",
                    {},
                    {},
                    self.context(
                        participant_token_hash=participant_hash,
                        idempotency_key=secrets.token_urlsafe(32),
                        event_enabled=False,
                    ),
                )
            self.assertEqual(disabled.exception.code, "EVENT_NOT_ENABLED")
            self.assertEqual(operations.get_me(conn, base_ctx)[1]["tickets"]["available_total"], before_ticket)

            create_ctx = self.context(
                participant_token_hash=participant_hash,
                idempotency_key=secrets.token_urlsafe(32),
            )
            status, session = operations.dispatch(conn, "POST", "/api/game-sessions", {}, {}, create_ctx)
            self.assertEqual(status, 201)
            session_id = session["session_id"]
            operations.dispatch(
                conn,
                "POST",
                f"/api/game-sessions/{session_id}/start",
                {},
                {},
                self.context(participant_token_hash=participant_hash, idempotency_key=secrets.token_urlsafe(32)),
            )
            conn.execute(
                "update dino_prod.game_session set started_at=clock_timestamp()-interval '3 seconds' where id=%s",
                (session_id,),
            )
            status, finished = operations.dispatch(
                conn,
                "POST",
                f"/api/game-sessions/{session_id}/finish",
                {},
                {},
                self.context(
                    participant_token_hash=participant_hash,
                    idempotency_key=secrets.token_urlsafe(32),
                    verification={
                        "valid": True,
                        "score": 321,
                        "ticks": 120,
                        "reason": "VERIFIED",
                        "summary": {},
                        "end_reason": "COLLISION",
                    },
                ),
            )
            self.assertEqual((status, finished["status"], finished["score"]), (200, "FINISHED", 321))

            with mock.patch.object(operations.secrets, "randbelow", return_value=0):
                status, draw = operations.dispatch(
                    conn,
                    "POST",
                    "/api/draws",
                    {"pouch_index": 0, "expected_round_number": 1},
                    {},
                    self.context(participant_token_hash=participant_hash, idempotency_key=secrets.token_urlsafe(32)),
                )
            self.assertEqual((status, draw["outcome_kind"], draw["is_won"]), (201, "PRIZE", True))
            self.assertTrue(draw["claim_id"])
            operations.dispatch(
                conn,
                "PATCH",
                f"/api/draws/{draw['draw_id']}/scratch-complete",
                {},
                {},
                self.context(participant_token_hash=participant_hash, idempotency_key=secrets.token_urlsafe(32)),
            )

            self.assertTrue(db.rate_limits(conn, [("runtime:production", 2)], window=60))
            card = share_page.public_card(
                conn,
                participant["referral_code"],
                "prize_share",
                "2.1.0",
                self.settings.campaign_id,
            )
            self.assertIn("뽑았다", card["title"])
            _, overview = metrics.build_overview(
                conn,
                {"environment": "production", "from": (self.now - dt.timedelta(days=1)).isoformat(), "to": (self.now + dt.timedelta(minutes=1)).isoformat()},
                base_ctx,
            )
            self.assertFalse(overview["synthetic_only"])
            self.assertEqual(overview["game"]["finished"], 1)
            rows = conn.execute(
                """select
                (select count(*) from dino_prod.participant where synthetic) synthetic_participants,
                (select count(*) from dino_prod.observation where synthetic) synthetic_observations,
                (select count(*) from dino_prod.game_session where synthetic) synthetic_games,
                (select count(*) from dino_prod.analytics_event where synthetic) synthetic_events"""
            ).fetchone()
            self.assertEqual(tuple(rows.values()), (0, 0, 0, 0))

            closed_ctx = self.context(
                participant_token_hash=participant_hash,
                idempotency_key=secrets.token_urlsafe(32),
                request_received_at=self.closes_at,
            )
            conn.execute(
                "update dino_prod.participant set initial_balance=1 where id=%s",
                (participant["id"],),
            )
            _, late_session = operations.create_session(
                conn,
                {},
                self.context(
                    participant_token_hash=participant_hash,
                    idempotency_key=secrets.token_urlsafe(32),
                ),
            )
            with self.assertRaises(operations.DomainError) as closed_game:
                operations.start_session(conn, late_session["session_id"], closed_ctx)
            self.assertEqual(closed_game.exception.code, "CAMPAIGN_CLOSED")
            with self.assertRaises(operations.DomainError) as closed_claim:
                operations.claim_draft_post(
                    conn,
                    draw["claim_id"],
                    {
                        "name": "TEST_RUNTIME",
                        "contact": "01000000000",
                        "school": "TEST_SCHOOL",
                        "address": "",
                        "consent": True,
                        "notice_version": "claim-contact-v1",
                    },
                    {**closed_ctx, "request_received_at": self.claim_closes_at},
                )
            self.assertEqual(closed_claim.exception.code, "CLAIM_SUBMISSION_CLOSED")
            with self.assertRaises(operations.DomainError) as closed_top3:
                operations.ranking_profile_post(
                    conn,
                    {
                        "name": "TEST_RUNTIME",
                        "contact": "01000000000",
                        "school": "TEST_SCHOOL",
                        "consent": True,
                        "notice_version": "top3-contact-v1",
                    },
                    {**closed_ctx, "request_received_at": self.claim_closes_at},
                )
            self.assertEqual(closed_top3.exception.code, "CLAIM_SUBMISSION_CLOSED")

        with psycopg.connect(self.database.dsn) as conn:
            self.assertEqual(self._beta_snapshot(conn), self.beta_before)
            prod = conn.execute(
                """select
                (select count(*) from dino_prod.participant),
                (select count(*) from dino_prod.game_session where status='FINISHED'),
                (select count(*) from dino_prod.draw where outcome_kind='PRIZE'),
                (select count(*) from dino_prod.claim where claim_type='DRAW'),
                (select count(*) from dino_prod.rate_limit_bucket)"""
            ).fetchone()
        self.assertEqual(prod, (1, 1, 1, 1, 1))


if __name__ == "__main__":
    unittest.main()
