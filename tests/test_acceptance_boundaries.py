import contextlib
import datetime as dt
import hashlib
import hmac
import os
import re
import secrets
import subprocess
import sys
import unittest
import uuid
from pathlib import Path
from unittest import mock
from urllib.parse import urlsplit

import psycopg
from psycopg import sql
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import operations


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
SEED = ROOT / "supabase/seed_dino_dev.sql"
CAMPAIGN_ID = "gemini_dino_phase1_test"
PEPPER = "acceptance-boundary-pepper-0123456789"
UTC = dt.timezone.utc


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
            "acceptance audit requires postgres on loopback port 55433 and database postgres"
        )


def _guard_database_name(name):
    if not re.fullmatch(r"dino_phase1_audit_[a-z0-9_]+", name):
        raise RuntimeError("refusing database operation outside dino_phase1_audit_ prefix")


def _run_sql(database, path):
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
            str(path),
        ],
        text=True,
        capture_output=True,
        check=False,
        env={**os.environ, "PGOPTIONS": "-c client_min_messages=warning"},
    )
    if result.returncode:
        raise RuntimeError(f"SQL setup failed: {path.name}\n{result.stdout}\n{result.stderr}")


def token_hash(value):
    return hmac.new(PEPPER.encode(), value.encode(), hashlib.sha256).hexdigest()


def request_context(**extra):
    value = {
        "environment": "test",
        "deployment": "acceptance-boundaries",
        "event_version": "phase1-v1",
        "campaign_id": CAMPAIGN_ID,
        "base_url": "http://127.0.0.1:3000",
        "project_ref": "local",
        "request_id": "acceptance-boundaries",
        "invite_active_ms": 3000,
        "participant_cookie_max_age": 2592000,
        "ip_subject": "acceptance-boundaries-ip",
    }
    value.update(extra)
    return value


class AcceptanceBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _guard_admin_dsn()
        cls.database = (
            f"dino_phase1_audit_boundaries_{os.getpid()}_{uuid.uuid4().hex}"
        )
        _guard_database_name(cls.database)
        cls.dsn = f"postgresql://postgres@127.0.0.1:55433/{cls.database}"
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(sql.SQL("create database {}").format(sql.Identifier(cls.database)))
        try:
            _run_sql(cls.database, FOUNDATION)
            _run_sql(cls.database, ADDITIONS)
            _run_sql(cls.database, CLAIM_FIX)
            _run_sql(cls.database, PHASE2)
            _run_sql(cls.database, GAME_V21)
            with psycopg.connect(cls.dsn) as conn:
                conn.execute(
                    "insert into dino_dev.environment_guard"
                    "(singleton,environment,project_ref) values(true,'test','local')"
                )
            _run_sql(cls.database, SEED)
        except Exception:
            cls._drop_database()
            raise

    @classmethod
    def tearDownClass(cls):
        cls._drop_database()

    @classmethod
    def _drop_database(cls):
        _guard_admin_dsn()
        _guard_database_name(cls.database)
        with psycopg.connect(ADMIN_DSN, autocommit=True) as conn:
            conn.execute(
                "select pg_terminate_backend(pid) from pg_stat_activity "
                "where datname=%s and pid<>pg_backend_pid()",
                (cls.database,),
            )
            conn.execute(
                sql.SQL("drop database if exists {}").format(sql.Identifier(cls.database))
            )

    def setUp(self):
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "truncate dino_dev.idempotency_request,dino_dev.analytics_event,"
                "dino_dev.admin_audit,dino_dev.ranking_snapshot_entry,"
                "dino_dev.ranking_snapshot,dino_dev.claim_contact,dino_dev.claim,"
                "dino_dev.inventory_history,dino_dev.draw,dino_dev.ranking_contact,"
                "dino_dev.best_score,dino_dev.game_session,dino_dev.invitation_reward,"
                "dino_dev.invitation_visit,dino_dev.ticket_ledger,dino_dev.bootstrap,"
                "dino_dev.observation,dino_dev.participant,dino_dev.admin_member "
                "restart identity cascade"
            )

    @contextlib.contextmanager
    def app_tx(self):
        with psycopg.connect(self.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("set local role dino_dev_app")
                yield conn

    def participant(self, label, *, initial=1, invitation=0, cooldown=None):
        raw = secrets.token_urlsafe(32)
        participant_id = f"p_{label}_{uuid.uuid4().hex}"
        referral_code = f"ref_{secrets.token_urlsafe(12)}"
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,
                 environment,initial_balance,invitation_balance,cooldown_until)
                values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,'test',%s,%s,%s)""",
                (
                    participant_id,
                    CAMPAIGN_ID,
                    token_hash(raw),
                    f"TEST_{label}"[:24],
                    referral_code,
                    initial,
                    invitation,
                    cooldown,
                ),
            )
        return {
            "id": participant_id,
            "token_hash": token_hash(raw),
            "referral_code": referral_code,
        }

    def admin(self):
        admin_id = str(uuid.uuid4())
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "insert into dino_dev.admin_member(auth_user_id,display_name,permissions) "
                "values(%s,'TEST fault reviewer',array['faults:read','faults:write'])",
                (admin_id,),
            )
        return admin_id

    def pending_visit(self, inviter, visitor, now, label):
        nonce = secrets.token_urlsafe(32)
        visit_id = f"visit_{label}_{uuid.uuid4().hex}"
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                """insert into dino_dev.invitation_visit
                (id,campaign_id,inviter_id,visitor_id,nonce_hash,expires_at,created_at)
                values(%s,%s,%s,%s,%s,%s,%s)""",
                (
                    visit_id,
                    CAMPAIGN_ID,
                    inviter["id"],
                    visitor["id"],
                    token_hash(nonce),
                    now + dt.timedelta(minutes=5),
                    now - dt.timedelta(seconds=4),
                ),
            )
        return visit_id, nonce

    def qualify(self, inviter, visitor, nonce, now):
        class FixedDateTime(dt.datetime):
            @classmethod
            def now(cls, tz=None):
                return now if tz else now.replace(tzinfo=None)

        with mock.patch.object(operations.dt, "datetime", FixedDateTime):
            with self.app_tx() as conn:
                return operations.qualify_referral(
                    conn,
                    {
                        "code": inviter["referral_code"],
                        "visit_nonce": nonce,
                        "active_ms": 3000,
                        "interacted": True,
                    },
                    request_context(
                        participant_token_hash=visitor["token_hash"],
                        visit_nonce_hash=token_hash(nonce),
                    ),
                )[1]

    def create_active_session(self, participant, label):
        ctx = request_context(
            participant_token_hash=participant["token_hash"],
            idempotency_key=f"session-{label}-{secrets.token_urlsafe(24)}",
        )
        with self.app_tx() as conn:
            _, created = operations.create_session(conn, {}, ctx)
            operations.start_session(conn, created["session_id"], ctx)
            conn.execute(
                "update dino_dev.game_session set started_at=clock_timestamp()-interval '3 seconds',"
                "last_checkpoint_tick=60 where id=%s",
                (created["session_id"],),
            )
        return ctx, created["session_id"]

    def report_fault(self, participant, reason, label):
        ctx, session_id = self.create_active_session(participant, label)
        with self.app_tx() as conn:
            status, response = operations.report_fault(
                conn, session_id, {"reason": reason, "last_tick": 60}, ctx
            )
        self.assertEqual(status, 202)
        self.assertEqual(response["fault_review"], {"status": "PENDING", "version": 1})
        return ctx, session_id

    def admin_decide(self, admin_id, session_id, decision, version, label):
        with self.app_tx() as conn:
            return operations.admin_fault_patch(
                conn,
                session_id,
                {
                    "decision": decision,
                    "expected_version": version,
                    "reason": f"TEST {decision.lower()} {label}",
                    "event_id": f"evt_{label}_{uuid.uuid4().hex}",
                },
                request_context(admin_user_id=admin_id),
            )

    def test_cooldown_boundary_and_pair_dedup_after_visit_expiry(self):
        with psycopg.connect(self.dsn) as conn:
            now = conn.execute("select clock_timestamp()").fetchone()[0]

        outcomes = []
        for label, offset in (
            ("before", -dt.timedelta(microseconds=1)),
            ("equal", dt.timedelta(0)),
            ("after", dt.timedelta(microseconds=1)),
        ):
            inviter = self.participant(
                f"inviter_{label}", initial=0, cooldown=now + offset
            )
            visitor = self.participant(f"visitor_{label}", initial=0)
            _, nonce = self.pending_visit(inviter, visitor, now, label)
            outcomes.append(self.qualify(inviter, visitor, nonce, now)["status"])

        self.assertEqual(outcomes, ["REWARDED", "REWARDED", "COOLDOWN"])

        inviter = self.participant("dedup_inviter", initial=0)
        visitor = self.participant("dedup_visitor", initial=0)
        first_visit, first_nonce = self.pending_visit(inviter, visitor, now, "dedup_first")
        first = self.qualify(inviter, visitor, first_nonce, now)
        with psycopg.connect(self.dsn) as conn:
            conn.execute(
                "update dino_dev.invitation_visit set expires_at=%s where id=%s",
                (now - dt.timedelta(microseconds=1), first_visit),
            )
        _, second_nonce = self.pending_visit(inviter, visitor, now, "dedup_second")
        second = self.qualify(inviter, visitor, second_nonce, now)

        with psycopg.connect(self.dsn) as conn:
            reward_count = conn.execute(
                "select count(*) from dino_dev.invitation_reward "
                "where inviter_id=%s and visitor_id=%s",
                (inviter["id"], visitor["id"]),
            ).fetchone()[0]
            balance = conn.execute(
                "select invitation_balance from dino_dev.participant where id=%s",
                (inviter["id"],),
            ).fetchone()[0]
        self.assertEqual(first["status"], "REWARDED")
        self.assertEqual(second["status"], "ALREADY_REWARDED")
        self.assertEqual((reward_count, balance), (1, 1))

    def test_admin_fault_approve_and_deny_require_current_version(self):
        admin_id = self.admin()
        approved = self.participant("approved")
        denied = self.participant("denied")
        _, approved_session = self.report_fault(approved, "SERVER_ERROR", "approved")
        _, denied_session = self.report_fault(denied, "CLIENT_ERROR", "denied")

        approve_status, approve = self.admin_decide(
            admin_id, approved_session, "APPROVE", 1, "approve"
        )
        deny_status, deny = self.admin_decide(
            admin_id, denied_session, "DENY", 1, "deny"
        )
        self.assertEqual((approve_status, approve["fault_review"]), (200, {"status": "APPROVED", "version": 2}))
        self.assertEqual((deny_status, deny["fault_review"]), (200, {"status": "DENIED", "version": 2}))
        self.assertEqual(approve["refund"]["status"], "REFUNDED")
        self.assertEqual(deny["refund"]["status"], "NOT_DUE")

        for session_id, decision in (
            (approved_session, "APPROVE"),
            (denied_session, "DENY"),
        ):
            with self.assertRaises(operations.DomainError) as raised:
                self.admin_decide(admin_id, session_id, decision, 1, "stale")
            self.assertEqual(raised.exception.code, "VERSION_CONFLICT")

        with psycopg.connect(self.dsn) as conn:
            audits = conn.execute(
                "select count(*) from dino_dev.admin_audit where action='FAULT_REVIEW'"
            ).fetchone()[0]
        self.assertEqual(audits, 2)

    def test_client_and_server_faults_stay_pending_until_eventual_admin_refund(self):
        admin_id = self.admin()
        for label, reason in (("client", "CLIENT_ERROR"), ("server", "SERVER_ERROR")):
            participant = self.participant(label)
            ctx, session_id = self.report_fault(participant, reason, label)
            with psycopg.connect(self.dsn) as conn:
                conn.execute(
                    "update dino_dev.game_session set fault_reported_at="
                    "clock_timestamp()-interval '1 hour' where id=%s",
                    (session_id,),
                )
            with self.app_tx() as conn:
                _, pending = operations.get_session(conn, session_id, ctx)
            self.assertEqual(pending["status"], "FAULT_REPORTED")
            self.assertEqual(pending["refund"]["status"], "REVIEW_REQUIRED")

            _, reviewed = self.admin_decide(
                admin_id, session_id, "APPROVE", 1, f"eventual_{label}"
            )
            self.assertEqual(reviewed["status"], "ABORTED")
            self.assertEqual(reviewed["refund"]["status"], "REFUNDED")

    def test_finished_response_replay_is_stable_and_has_no_duplicate_effects(self):
        participant = self.participant("finished")
        ctx, session_id = self.create_active_session(participant, "finished")
        finish_ctx = {
            **ctx,
            "verification": (True, 10, 60, "VERIFIED"),
        }
        with self.app_tx() as conn:
            first_status, first = operations.finish_session(
                conn, session_id, {"score": 10, "ticks": 60}, finish_ctx
            )
        with self.app_tx() as conn:
            replay_status, replay = operations.finish_session(
                conn,
                session_id,
                {"score": 999, "ticks": 999},
                {**ctx, "verification": (True, 999, 999, "DIFFERENT")},
            )

        self.assertEqual((first_status, replay_status), (200, 200))
        self.assertEqual(replay, first)
        with psycopg.connect(self.dsn) as conn:
            best_scores = conn.execute(
                "select count(*),max(score) from dino_dev.best_score where participant_id=%s",
                (participant["id"],),
            ).fetchone()
            finish_events = conn.execute(
                "select count(*) from dino_dev.analytics_event "
                "where game_session_id=%s and event_name='game_finish_verified'",
                (session_id,),
            ).fetchone()[0]
            consumes = conn.execute(
                "select count(*) from dino_dev.ticket_ledger "
                "where participant_id=%s and source_type='PLAY_CONSUME'",
                (participant["id"],),
            ).fetchone()[0]
        self.assertEqual(best_scores, (1, 10))
        self.assertEqual((finish_events, consumes), (1, 1))

    def test_invitation_fault_refund_preserves_cooldown_and_grant_history(self):
        with psycopg.connect(self.dsn) as conn:
            cooldown = conn.execute(
                "select clock_timestamp()+interval '8 hours'"
            ).fetchone()[0]
        inviter = self.participant(
            "invite_refund", initial=0, invitation=3, cooldown=cooldown
        )
        with psycopg.connect(self.dsn) as conn:
            for index in range(3):
                visitor = self.participant(f"grant_visitor_{index}", initial=0)
                visit_id = f"visit_grant_{index}_{uuid.uuid4().hex}"
                reward_id = f"reward_grant_{index}_{uuid.uuid4().hex}"
                conn.execute(
                    """insert into dino_dev.invitation_visit
                    (id,campaign_id,inviter_id,visitor_id,nonce_hash,status,reason,
                     expires_at,qualified_at,active_ms,interacted)
                    values(%s,%s,%s,%s,%s,'REWARDED','QUALIFIED',
                           clock_timestamp()+interval '1 hour',clock_timestamp(),3000,true)""",
                    (
                        visit_id,
                        CAMPAIGN_ID,
                        inviter["id"],
                        visitor["id"],
                        token_hash(f"grant-nonce-{index}-{uuid.uuid4().hex}"),
                    ),
                )
                conn.execute(
                    "insert into dino_dev.invitation_reward"
                    "(id,campaign_id,inviter_id,visitor_id,visit_id) values(%s,%s,%s,%s,%s)",
                    (reward_id, CAMPAIGN_ID, inviter["id"], visitor["id"], visit_id),
                )
                conn.execute(
                    """insert into dino_dev.ticket_ledger
                    (participant_id,ticket_kind,delta,source_type,source_id,balance_after,cooldown_until)
                    values(%s,'INVITATION',1,'INVITATION_GRANT',%s,%s,%s)""",
                    (inviter["id"], reward_id, index + 1, cooldown if index == 2 else None),
                )

        admin_id = self.admin()
        _, session_id = self.report_fault(inviter, "SERVER_ERROR", "invite_refund")
        _, reviewed = self.admin_decide(
            admin_id, session_id, "APPROVE", 1, "invite_refund"
        )
        self.assertEqual(reviewed["refund"]["status"], "REFUNDED")

        with psycopg.connect(self.dsn) as conn:
            state = conn.execute(
                "select invitation_balance,invitation_refund_pending,cooldown_until "
                "from dino_dev.participant where id=%s",
                (inviter["id"],),
            ).fetchone()
            rewards = conn.execute(
                "select count(*) from dino_dev.invitation_reward where inviter_id=%s",
                (inviter["id"],),
            ).fetchone()[0]
            grants = conn.execute(
                "select count(*) from dino_dev.ticket_ledger "
                "where participant_id=%s and source_type='INVITATION_GRANT'",
                (inviter["id"],),
            ).fetchone()[0]
            refunds = conn.execute(
                "select count(*) from dino_dev.ticket_ledger "
                "where participant_id=%s and source_type='FAULT_REFUND'",
                (inviter["id"],),
            ).fetchone()[0]

        self.assertEqual(state[0:2], (3, 0))
        self.assertEqual(state[2], cooldown)
        self.assertEqual((rewards, grants, refunds), (3, 3, 1))


if __name__ == "__main__":
    unittest.main()
