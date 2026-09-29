import copy
import contextlib
import datetime as dt
import hashlib
import hmac
import json
import secrets
import sys
import threading
import time
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
from config import ConfigurationError, Settings, schema_context
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
            provision(conn, copy.deepcopy(cls.manifest), cls.digest, payload)

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

    def test_late_beta_callbacks_cannot_grant_production_rewards(self):
        beta_participant = "beta_callback_" + secrets.token_hex(8)
        beta_token_hash = hashlib.sha256(beta_participant.encode()).hexdigest()
        beta_referral_code = "BetaCallback" + secrets.token_hex(8)
        production_participant = "prod_callback_" + secrets.token_hex(8)
        production_token_hash = hashlib.sha256(production_participant.encode()).hexdigest()
        production_referral_code = "ProdCallback" + secrets.token_hex(8)

        def cleanup():
            with psycopg.connect(self.database.dsn) as conn:
                conn.execute("delete from dino_prod.participant where id=%s", (production_participant,))
                conn.execute("delete from dino_dev.participant where id=%s", (beta_participant,))

        self.addCleanup(cleanup)
        beta_callbacks = []
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                values(%s,'gemini_dino_phase1_test',%s,clock_timestamp()+interval '1 hour',
                       'beta_callback',%s,'test')""",
                (beta_participant, beta_token_hash, beta_referral_code),
            )
            for kind, reward_type in (("retry_invite", "GAME"), ("draw_retry", "DRAW")):
                share_id = "share_" + secrets.token_hex(16)
                callback_token = secrets.token_urlsafe(32)
                beta_callbacks.append((share_id, callback_token, reward_type))
                conn.execute(
                    """insert into dino_dev.kakao_share_intent
                    (id,participant_id,campaign_id,kind,reward_type,reward_contract_version,
                     callback_token_hash,environment,expires_at)
                    values(%s,%s,'gemini_dino_phase1_test',%s,%s,2,%s,'test',
                           clock_timestamp()+interval '30 minutes')""",
                    (share_id, beta_participant, kind, reward_type,
                     auth.token_hash(callback_token, PEPPER)),
                )

        with psycopg.connect(self.database.dsn) as conn:
            beta_before = conn.execute(
                """select id,status,reward_status,resource_id from dino_dev.kakao_share_intent
                where participant_id=%s order by id""", (beta_participant,)
            ).fetchall()
            prod_before = conn.execute(
                """select
                (select count(*) from dino_prod.ticket_ledger),
                (select count(*) from dino_prod.draw_credit_ledger),
                (select coalesce(sum(invitation_balance),0) from dino_prod.participant)"""
            ).fetchone()

        for share_id, callback_token, reward_type in beta_callbacks:
            with self.subTest(reward_type=reward_type), self.assertRaises(operations.DomainError) as caught:
                with self.app_tx() as conn:
                    db.check_business_environment(conn, self.settings)
                    operations.dispatch(
                        conn,
                        "POST",
                        "/api/webhooks/kakao-share",
                        {"share_id": share_id, "callback_token": callback_token,
                         "CHAT_TYPE": "DirectChat", "HASH_CHAT_ID": "beta-chat"},
                        {},
                        self.context(kakao_webhook_verified=True,
                                     kakao_resource_id="late-beta-" + reward_type,
                                     share_callback_token_hash=auth.token_hash(callback_token, PEPPER)),
                    )
            self.assertEqual(caught.exception.code, "SHARE_INTENT_NOT_FOUND")

        guard_token = secrets.token_urlsafe(32)
        guard_share_id = "share_" + secrets.token_hex(16)
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_prod.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,synthetic)
                values(%s,%s,%s,clock_timestamp()+interval '1 hour','prod_callback',%s,'production',false)""",
                (production_participant, self.settings.campaign_id, production_token_hash,
                 production_referral_code),
            )
            conn.execute(
                """insert into dino_prod.kakao_share_intent
                (id,participant_id,campaign_id,kind,reward_type,reward_contract_version,
                 callback_token_hash,environment,expires_at)
                values(%s,%s,%s,'retry_invite','GAME',2,%s,'production',
                       clock_timestamp()+interval '30 minutes')""",
                (guard_share_id, production_participant, self.settings.campaign_id,
                 auth.token_hash(guard_token, PEPPER)),
            )

        for label, mismatched_context in (
            ("environment", {"environment": "preview"}),
            ("campaign", {"campaign_id": "beta_campaign"}),
        ):
            with self.subTest(guard=label), self.assertRaises(operations.DomainError) as caught:
                with self.app_tx() as conn:
                    db.check_business_environment(conn, self.settings)
                    operations.dispatch(
                        conn,
                        "POST",
                        "/api/webhooks/kakao-share",
                        {"share_id": guard_share_id, "callback_token": guard_token,
                         "CHAT_TYPE": "DirectChat", "HASH_CHAT_ID": "guard-chat"},
                        {},
                        self.context(kakao_webhook_verified=True,
                                     kakao_resource_id="guard-" + label,
                                     share_callback_token_hash=auth.token_hash(guard_token, PEPPER),
                                     **mismatched_context),
                    )
            self.assertEqual(caught.exception.code, "INVALID_WEBHOOK")

        with psycopg.connect(self.database.dsn) as conn:
            beta_after = conn.execute(
                """select id,status,reward_status,resource_id from dino_dev.kakao_share_intent
                where participant_id=%s order by id""", (beta_participant,)
            ).fetchall()
            prod_after = conn.execute(
                """select
                (select count(*) from dino_prod.ticket_ledger),
                (select count(*) from dino_prod.draw_credit_ledger),
                (select coalesce(sum(invitation_balance),0) from dino_prod.participant)"""
            ).fetchone()
        self.assertEqual(beta_after, beta_before)
        self.assertEqual(prod_after, prod_before)
        cleanup()
        with psycopg.connect(self.database.dsn) as conn:
            self.assertEqual(self._beta_snapshot(conn), self.beta_before)

    def test_cutover_waits_for_business_commit_then_stale_runtime_is_refused(self):
        marker = "rollback_lock_" + secrets.token_hex(8)
        stale_marker = "rollback_stale_" + secrets.token_hex(8)
        off_hash = hashlib.sha256((marker + "|off").encode()).hexdigest()
        attempting = threading.Event()
        acquired = threading.Event()
        completed = threading.Event()
        worker_pid = []
        worker_errors = []

        def cutover():
            try:
                with psycopg.connect(self.database.dsn, autocommit=True) as conn:
                    worker_pid.append(conn.info.backend_pid)
                    with conn.transaction():
                        conn.execute("set local statement_timeout='5000ms'")
                        attempting.set()
                        conn.execute("select pg_advisory_xact_lock(hashtext('dino-prod-cutover'))")
                        acquired.set()
                        conn.execute(
                            """update dino_prod.campaign set status='PAUSED',
                            settings=jsonb_set(settings,'{phase3_manifest_hash}',to_jsonb(%s::text),true)
                            where id=%s""",
                            (off_hash, self.settings.campaign_id),
                        )
                        conn.execute(
                            """update dino_prod.environment_guard set event_enabled=false,
                            launch_manifest_sha256=%s where singleton""",
                            (off_hash,),
                        )
                completed.set()
            except Exception as error:  # surfaced by the assertions below
                worker_errors.append(error)
                completed.set()

        thread = None
        try:
            with self.app_tx() as conn:
                guard = db.check_business_environment(conn, self.settings)
                self.assertTrue(guard["event_enabled"])
                thread = threading.Thread(target=cutover, daemon=True)
                thread.start()
                self.assertTrue(attempting.wait(2), "cutover did not start")

                deadline = time.monotonic() + 2
                blocked = False
                while time.monotonic() < deadline:
                    with psycopg.connect(self.database.dsn) as observer:
                        wait = observer.execute(
                            "select wait_event_type,wait_event from pg_stat_activity where pid=%s",
                            (worker_pid[0],),
                        ).fetchone()
                    if wait and wait[0] == "Lock" and wait[1] == "advisory":
                        blocked = True
                        break
                    time.sleep(0.02)
                self.assertTrue(blocked, "exclusive cutover lock was not blocked by the business transaction")
                self.assertFalse(acquired.is_set())
                conn.execute(
                    """insert into dino_prod.observation
                    (id,event_id,actor_key,idempotency_key,request_hash,campaign_code,environment,synthetic)
                    values(%s,%s,'rollback-lock','rollback-lock','rollback-lock',%s,'production',false)""",
                    (marker, marker, self.settings.campaign_id),
                )

            self.assertTrue(acquired.wait(2), "cutover did not acquire after business commit")
            self.assertTrue(completed.wait(2), "cutover did not complete")
            thread.join(timeout=2)
            self.assertFalse(thread.is_alive())
            self.assertEqual(worker_errors, [])

            with psycopg.connect(self.database.dsn) as conn:
                state = conn.execute(
                    """select c.status,g.event_enabled,g.launch_manifest_sha256,
                    c.settings->>'phase3_manifest_hash'
                    from dino_prod.campaign c cross join dino_prod.environment_guard g
                    where c.id=%s and g.singleton""",
                    (self.settings.campaign_id,),
                ).fetchone()
                committed = conn.execute(
                    "select count(*) from dino_prod.observation where id=%s", (marker,)
                ).fetchone()[0]
            self.assertEqual(state, ("PAUSED", False, off_hash, off_hash))
            self.assertEqual(committed, 1)

            with self.assertRaisesRegex(ConfigurationError, "PRODUCTION_GUARD_MISMATCH"):
                with self.app_tx() as conn:
                    db.check_business_environment(conn, self.settings)
                    conn.execute(
                        """insert into dino_prod.observation
                        (id,event_id,actor_key,idempotency_key,request_hash,campaign_code,environment,synthetic)
                        values(%s,%s,'stale-runtime','stale-runtime','stale-runtime',%s,'production',false)""",
                        (stale_marker, stale_marker, self.settings.campaign_id),
                    )
            with psycopg.connect(self.database.dsn) as conn:
                stale_writes = conn.execute(
                    "select count(*) from dino_prod.observation where id=%s", (stale_marker,)
                ).fetchone()[0]
            self.assertEqual(stale_writes, 0)
        finally:
            if thread and thread.is_alive():
                thread.join(timeout=6)
            with psycopg.connect(self.database.dsn) as conn:
                with conn.transaction():
                    conn.execute("select pg_advisory_xact_lock(hashtext('dino-prod-cutover'))")
                    conn.execute(
                        """update dino_prod.campaign set status='ACTIVE',
                        settings=jsonb_set(settings,'{phase3_manifest_hash}',to_jsonb(%s::text),true)
                        where id=%s""",
                        (self.digest, self.settings.campaign_id),
                    )
                    conn.execute(
                        """update dino_prod.environment_guard set event_enabled=true,
                        launch_manifest_sha256=%s where singleton""",
                        (self.digest,),
                    )
                    conn.execute(
                        "delete from dino_prod.observation where id in (%s,%s)",
                        (marker, stale_marker),
                    )
        with self.app_tx() as conn:
            restored = db.check_business_environment(conn, self.settings)
        self.assertTrue(restored["event_enabled"])

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
