import concurrent.futures
import contextlib
import datetime as dt
import hashlib
import hmac
import os
import secrets
import sys
import threading
import unittest
import uuid
from pathlib import Path
from urllib.parse import urlsplit

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import operations


DATABASE_NAME = "dino_phase1_v2_audit_backend"
DSN = os.getenv(
    "PHASE1_ACCEPTANCE_DATABASE_URL",
    f"postgres://postgres@127.0.0.1:55433/{DATABASE_NAME}",
)
CAMPAIGN_ID = "gemini_dino_phase1_test"
PEPPER = "acceptance-regression-pepper-0123456789"


def _guard_destructive_dsn():
    target = urlsplit(DSN)
    if target.hostname not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("acceptance regression DB must be loopback-only")
    if target.path.lstrip("/") != DATABASE_NAME:
        raise RuntimeError("acceptance regression DB name is not the dedicated known database")


def token_hash(value):
    return hmac.new(PEPPER.encode(), value.encode(), hashlib.sha256).hexdigest()


def context(**extra):
    value = {
        "environment": "test",
        "deployment": "acceptance-regression",
        "event_version": "phase1-v1",
        "campaign_id": CAMPAIGN_ID,
        "base_url": "http://127.0.0.1:3000",
        "project_ref": "local",
        "request_id": "acceptance-regression",
        "invite_active_ms": 3000,
        "participant_cookie_max_age": 2592000,
        "ip_subject": "acceptance-regression-ip",
    }
    value.update(extra)
    return value


@contextlib.contextmanager
def app_tx():
    with psycopg.connect(DSN, row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("set local role dino_dev_app")
            yield conn


class AcceptanceRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        _guard_destructive_dsn()
        with psycopg.connect(DSN) as conn:
            version = conn.execute(
                "select version from dino_dev.schema_version order by applied_at desc limit 1"
            ).fetchone()
        if not version:
            raise RuntimeError("acceptance regression DB is not migrated")

    def setUp(self):
        _guard_destructive_dsn()
        with psycopg.connect(DSN) as conn:
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
            conn.execute(
                "update dino_dev.inventory_item set status='VOID',"
                "reserved_by_draw_id=null,reserved_at=null,paid_at=null"
            )

    def participant(self, label, initial=1):
        raw = secrets.token_urlsafe(32)
        participant_id = f"p_{label}_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,
                 environment,initial_balance)
                values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,'test',%s)""",
                (
                    participant_id,
                    CAMPAIGN_ID,
                    token_hash(raw),
                    f"TEST_{label}"[:24],
                    f"ref_{secrets.token_urlsafe(12)}",
                    initial,
                ),
            )
        return {"id": participant_id, "token_hash": token_hash(raw)}

    def admin(self, permissions):
        admin_id = str(uuid.uuid4())
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "insert into dino_dev.admin_member(auth_user_id,display_name,permissions) "
                "values(%s,'TEST_admin',%s)",
                (admin_id, permissions),
            )
        return admin_id

    def finished_session(self, participant, label):
        session_id = f"gs_{label}_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,
                 ticket_kind,ticket_refund_status,expires_at,score,valid_ticks,
                 verification_result,finished_at,environment)
                values(%s,%s,%s,%s,1,'1.2.0','FINISHED','INITIAL','NOT_DUE',
                       clock_timestamp()+interval '1 hour',10,60,'VERIFIED',
                       clock_timestamp(),'test')""",
                (session_id, participant["id"], CAMPAIGN_ID, f"finished_{label}"),
            )
        return session_id

    def test_revoked_participant_cannot_replay_cached_mutation_response(self):
        participant = self.participant("revoked")
        participant_ctx = context(
            participant_token_hash=participant["token_hash"],
            idempotency_key="participant-replay-key",
        )
        with app_tx() as conn:
            first = operations.dispatch(
                conn, "POST", "/api/game-sessions", {}, {}, participant_ctx
            )
        self.assertEqual(first[0], 201)
        with app_tx() as conn:
            authorized_replay = operations.dispatch(
                conn, "POST", "/api/game-sessions", {}, {}, participant_ctx
            )
        self.assertEqual(authorized_replay, first)

        admin_id = self.admin(["participants:write"])
        with app_tx() as conn:
            operations.admin_participant_patch(
                conn,
                participant["id"],
                {
                    "status": "BLOCKED",
                    "expected_status": "ACTIVE",
                    "revoke_session": True,
                    "reason": "TEST revoked replay",
                    "event_id": "evt_revoke_replay",
                },
                context(admin_user_id=admin_id),
            )
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as raised:
                operations.dispatch(
                    conn, "POST", "/api/game-sessions", {}, {}, participant_ctx
                )
        self.assertEqual(raised.exception.code, "SESSION_INVALID")

    def test_admin_permission_removal_blocks_cached_claim_replay(self):
        participant = self.participant("claim")
        claim_id = f"claim_{uuid.uuid4().hex}"
        admin_id = self.admin(["claims:read", "claims:write"])
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "insert into dino_dev.claim(id,campaign_id,participant_id,claim_type,status) "
                "values(%s,%s,%s,'DRAW','PENDING_REVIEW')",
                (claim_id, CAMPAIGN_ID, participant["id"]),
            )
        body = {
            "status": "CONTACTED",
            "expected_version": 1,
            "event_id": "evt_claim_replay",
        }
        admin_ctx = context(
            admin_user_id=admin_id,
            idempotency_key="admin-claim-replay-key",
        )
        path = f"/api/admin/claims/{claim_id}"
        with app_tx() as conn:
            first = operations.dispatch(conn, "PATCH", path, body, {}, admin_ctx)
        self.assertEqual(first[1]["status"], "CONTACTED")
        with app_tx() as conn:
            authorized_replay = operations.dispatch(conn, "PATCH", path, body, {}, admin_ctx)
        self.assertEqual(authorized_replay, first)
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "update dino_dev.admin_member set permissions=array['claims:read']::text[] "
                "where auth_user_id=%s",
                (admin_id,),
            )
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as raised:
                operations.dispatch(conn, "PATCH", path, body, {}, admin_ctx)
        self.assertEqual(raised.exception.code, "ADMIN_FORBIDDEN")

    def test_denied_fault_remains_not_due_on_repeated_fault_request(self):
        participant = self.participant("denied", initial=0)
        session_id = f"gs_denied_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,
                 ticket_kind,ticket_refund_status,started_at,expires_at,
                 last_checkpoint_tick,fault_reason,fault_reported_at,
                 fault_review_status,fault_review_version,environment)
                values(%s,%s,%s,%s,1,'1.2.0','FAULT_REPORTED','INITIAL','PENDING',
                       clock_timestamp()-interval '20 seconds',
                       clock_timestamp()+interval '1 hour',120,'CLIENT_ERROR',
                       clock_timestamp()-interval '10 seconds','PENDING',1,'test')""",
                (session_id, participant["id"], CAMPAIGN_ID, f"deny_{session_id}"),
            )
        admin_id = self.admin(["faults:write"])
        with app_tx() as conn:
            operations.admin_fault_patch(
                conn,
                session_id,
                {
                    "decision": "DENY",
                    "reason": "TEST intentional exit",
                    "expected_version": 1,
                    "event_id": "evt_fault_deny",
                },
                context(admin_user_id=admin_id),
            )
        with app_tx() as conn:
            _status, repeated = operations.report_fault(
                conn,
                session_id,
                {"reason": "CLIENT_ERROR", "last_tick": 120},
                context(participant_token_hash=participant["token_hash"]),
            )
        self.assertEqual(repeated["status"], "ABORTED")
        self.assertEqual(repeated["refund"]["status"], "NOT_DUE")
        self.assertEqual(repeated["fault_review"]["status"], "DENIED")

    def test_concurrent_same_participant_draws_return_one_fixed_result(self):
        participant = self.participant("draw", initial=0)
        self.finished_session(participant, "draw")
        inventory_id = f"inventory_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "update dino_dev.prize set probability=case when id='test_coffee' then 1 else 0 end"
            )
            conn.execute(
                "insert into dino_dev.inventory_item(id,prize_id,status) "
                "values(%s,'test_coffee','AVAILABLE')",
                (inventory_id,),
            )

        barrier = threading.Barrier(2)

        def draw(index):
            barrier.wait(timeout=5)
            with app_tx() as conn:
                return operations.dispatch(
                    conn,
                    "POST",
                    "/api/draws",
                    {"pouch_index": index},
                    {},
                    context(
                        participant_token_hash=participant["token_hash"],
                        idempotency_key=f"concurrent-draw-{index}",
                    ),
                )

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(draw, (0, 1)))
        self.assertEqual({result[1]["draw_id"] for result in results}, {results[0][1]["draw_id"]})
        self.assertEqual({result[1]["pouch_index"] for result in results}, {results[0][1]["pouch_index"]})
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            counts = conn.execute(
                "select count(*) n,count(distinct inventory_item_id) inventory_n "
                "from dino_dev.draw where participant_id=%s",
                (participant["id"],),
            ).fetchone()
            events = conn.execute(
                "select count(*) n from dino_dev.analytics_event "
                "where participant_id=%s and event_name='draw_fixed'",
                (participant["id"],),
            ).fetchone()["n"]
        self.assertEqual((counts["n"], counts["inventory_n"], events), (1, 1, 1))

    def test_game_start_event_uses_only_owned_observation_attribution(self):
        owner = self.participant("attribution_owner")
        other = self.participant("attribution_other")
        owned_observation = f"obs_{uuid.uuid4().hex}"
        foreign_observation = f"obs_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            for observation_id, participant_id in (
                (owned_observation, owner["id"]),
                (foreign_observation, other["id"]),
            ):
                conn.execute(
                    """insert into dino_dev.observation
                    (id,event_id,actor_key,idempotency_key,request_hash,participant_id,
                     link_kind,channel_code,environment)
                    values(%s,%s,%s,%s,%s,%s,'direct','acceptance_test','test')""",
                    (
                        observation_id,
                        f"evt_{uuid.uuid4().hex}",
                        f"actor_{uuid.uuid4().hex}",
                        secrets.token_urlsafe(32),
                        "a" * 64,
                        participant_id,
                    ),
                )
        with app_tx() as conn:
            status, created = operations.create_session(
                conn,
                {
                    "observation_id": owned_observation,
                    "visit_session_id": "visit_session_owned_1234",
                },
                context(
                    participant_token_hash=owner["token_hash"],
                    idempotency_key="owned-attribution-session",
                ),
            )
        self.assertEqual(status, 201)
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            event = conn.execute(
                "select observation_id,visit_session_id from dino_dev.analytics_event "
                "where event_name='game_start_approved' and game_session_id=%s",
                (created["session_id"],),
            ).fetchone()
        self.assertEqual(
            (event["observation_id"], event["visit_session_id"]),
            (owned_observation, "visit_session_owned_1234"),
        )

        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as raised:
                operations.create_session(
                    conn,
                    {
                        "observation_id": foreign_observation,
                        "visit_session_id": "visit_session_foreign_1234",
                    },
                    context(
                        participant_token_hash=owner["token_hash"],
                        idempotency_key="foreign-attribution-session",
                    ),
                )
        self.assertEqual(raised.exception.code, "INVALID_OBSERVATION_ATTRIBUTION")

    def test_entry_codes_and_new_tracking_catalogue_are_bounded(self):
        valid = context(
            idempotency_key=secrets.token_urlsafe(32),
            bootstrap_token="bootstrap-valid",
            bootstrap_token_hash="b" * 64,
        )
        valid["bootstrap_token"] = "bootstrap-valid"
        valid["bootstrap_token_hash"] = "b" * 64
        with app_tx() as conn:
            status, _response = operations.create_observation(
                conn,
                {
                    "observation_id": "obs_valid_codes_1234",
                    "event_id": "evt_valid_codes_1234",
                    "channel_code": "channel_1",
                    "campaign_code": "campaign_1",
                },
                valid,
            )
        self.assertEqual(status, 201)
        for field, value in (
            ("channel_code", "01012345678"),
            ("campaign_code", "9campaign"),
            ("channel_code", "a" * 33),
        ):
            ctx = context(
                idempotency_key=secrets.token_urlsafe(32),
                bootstrap_token="bootstrap-invalid",
                bootstrap_token_hash="c" * 64,
            )
            with app_tx() as conn:
                with self.assertRaises(operations.DomainError):
                    operations.create_observation(
                        conn,
                        {
                            "observation_id": f"obs_{uuid.uuid4().hex}",
                            "event_id": f"evt_{uuid.uuid4().hex}",
                            field: value,
                        },
                        ctx,
                    )
        with app_tx() as conn:
            status, result = operations.events_batch(
                conn,
                {
                    "events": [
                        {
                            "event_id": "evt_loading_ready_1234",
                            "name": "loading_ready",
                            "screen": "loading",
                            "occurred_at": dt.datetime.now(dt.timezone.utc)
                            .isoformat()
                            .replace("+00:00", "Z"),
                            "dimensions": {"source": "gemini"},
                        }
                    ]
                },
                context(),
            )
        self.assertEqual((status, result), (202, {"accepted": 1, "duplicates": 0, "rejected": 0}))


if __name__ == "__main__":
    unittest.main()
