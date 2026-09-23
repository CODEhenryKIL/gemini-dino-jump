"""Real PostgreSQL integration tests for the Phase 1 business transaction layer.

The suite only targets the dedicated local database named dino_operations_test.
Migration/bootstrap/seed are intentionally separate setup steps.
"""
from concurrent.futures import ThreadPoolExecutor
import datetime as dt
import os
import sys
import unittest
from urllib.parse import urlparse

import psycopg
from psycopg import errors
from psycopg.rows import dict_row

ROOT = os.path.dirname(os.path.dirname(__file__))
sys.path.insert(0, ROOT)
from server.services.operations import DomainError, dispatch  # noqa: E402


DB_URL = os.environ.get(
    "DINO_OPERATIONS_TEST_DATABASE_URL",
    "postgresql://postgres@127.0.0.1:55432/dino_operations_test",
)
_db_target = urlparse(DB_URL)
assert (_db_target.hostname in ("127.0.0.1", "localhost") and _db_target.port == 55432
        and _db_target.path == "/dino_operations_test"), "tests require loopback:55432/dino_operations_test"


class raises:
    def __init__(self, expected):
        self.expected = expected
        self.value = None

    def __enter__(self):
        return self

    def __exit__(self, kind, value, traceback):
        if kind is None:
            raise AssertionError(f"{self.expected.__name__} was not raised")
        if not issubclass(kind, self.expected):
            return False
        self.value = value
        return True


def admin_conn():
    return psycopg.connect(DB_URL, autocommit=True, row_factory=dict_row, prepare_threshold=None)


def app_conn():
    conn = admin_conn()
    conn.execute("set role dino_app")
    return conn


def ctx(token_hash="", **overrides):
    value = {
        "environment": "local", "base_url": "http://127.0.0.1:3000",
        "benefit_url": "https://gemini.google.com/students", "game_version": "1.2.0",
        "participant_token_hash": token_hash, "new_token_hash": "",
        "admin_user_id": None, "request_id": "test-request", "synthetic": True,
    }
    value.update(overrides)
    return value


def call(conn, method, path, body=None, query=None, context=None):
    with conn.transaction():
        return dispatch(conn, method, path, body or {}, query or {}, context or ctx())


def create_participant(conn, marker, referral_code=None):
    token_hash = (marker * 64)[:64]
    context = ctx(new_token_hash=token_hash)
    body = {"channel": "qr"}
    if referral_code:
        body["referral_code"] = referral_code
    status, result = call(conn, "POST", "/api/participants/anonymous", body, context=context)
    assert status == 201
    return token_hash, result["participant"], result["referral_applied"]


def verified_session(conn, token_hash, key, score=100):
    context = ctx(token_hash)
    _, created = call(conn, "POST", "/api/game-sessions", {"idempotency_key": key}, context=context)
    session_id = created["session_id"]
    _, started = call(conn, "POST", f"/api/game-sessions/{session_id}/start", context=context)
    assert started["status"] == "ACTIVE"
    finish_context = ctx(token_hash, verification={"valid": True, "score": score, "valid_ticks": 1, "reason": "VERIFIED"})
    _, result = call(conn, "POST", f"/api/game-sessions/{session_id}/finish",
                     {"score": score, "valid_ticks": 1, "version": "1.2.0"}, context=finish_context)
    return session_id, result


def clean_database():
    with admin_conn() as conn:
        version = conn.execute("select version from dino.schema_version").fetchone()
        guard = conn.execute("select environment,project_ref,synthetic_only from dino.environment_guard where singleton").fetchone()
        assert version["version"] == "20260923033611"
        assert guard == {"environment": "local", "project_ref": "local", "synthetic_only": True}
        conn.execute("""truncate dino.claim_recipient,dino.delivery_attempt,dino.claim,dino.inventory_history,
            dino.draw,dino.best_score,dino.referral,dino.ticket_ledger,dino.game_session,
            dino.benefit_verification,dino.analytics_event,dino.admin_audit,dino.admin_member,
            dino.participant,dino.rate_limit_bucket restart identity cascade""")
        conn.execute("""insert into dino.inventory_item(id,prize_id)
            select 'test_coffee_' || lpad(n::text,3,'0'),'test_coffee' from generate_series(1,20) n
            on conflict(id) do update set status='AVAILABLE',reserved_by_draw_id=null,reserved_at=null,issued_at=null""")
        conn.execute("""insert into dino.inventory_item(id,prize_id)
            select 'test_shipping_' || lpad(n::text,3,'0'),'test_shipping' from generate_series(1,5) n
            on conflict(id) do update set status='AVAILABLE',reserved_by_draw_id=null,reserved_at=null,issued_at=null""")
        conn.execute("update dino.prize set is_active=true")
        conn.execute("update dino.prize set probability=case id when 'test_coffee' then .20 when 'test_shipping' then .05 else .75 end")
        conn.execute("update dino.campaign set status='ACTIVE'")


def phase1_transactions_ownership_referral_stock_claim_and_metrics():
    with app_conn() as conn:
        token_a, participant_a, _ = create_participant(conn, "a")
        assert call(conn, "GET", "/api/me", context=ctx(token_a))[1]["tickets"] == 3

        session_a, first_finish = verified_session(conn, token_a, "session-a", 120)
        assert first_finish["eligible_for_draw"] is True
        retry_context = ctx(token_a, verification={"valid": False, "score": 9999, "valid_ticks": 1, "reason": "REJECTED"})
        _, retry_finish = call(conn, "POST", f"/api/game-sessions/{session_a}/finish",
                               {"score": 9999, "valid_ticks": 1, "version": "1.2.0"}, context=retry_context)
        assert retry_finish == first_finish
        assert call(conn, "GET", "/api/me", context=ctx(token_a))[1]["tickets"] == 2
        leaderboard = call(conn, "GET", "/api/leaderboard", query={"limit": "10"}, context=ctx(token_a))[1]["leaderboard"]
        assert leaderboard[0]["score"] == 120 and leaderboard[0]["rank"] == 1

        token_b, participant_b, applied = create_participant(conn, "b", participant_a["referral_code"])
        assert applied is True
        session_b, _ = verified_session(conn, token_b, "session-b", 110)
        referral_balance = conn.execute("select coalesce(sum(delta),0)::int n from dino.ticket_ledger where participant_id=%s and source_type='REFERRAL'", (participant_a["id"],)).fetchone()["n"]
        assert referral_balance == 1
        call(conn, "POST", f"/api/game-sessions/{session_b}/finish",
             {"score": 110, "valid_ticks": 1, "version": "1.2.0"},
             context=ctx(token_b, verification={"valid": True, "score": 110, "valid_ticks": 1, "reason": "VERIFIED"}))
        assert conn.execute("select count(*)::int n from dino.ticket_ledger where participant_id=%s and source_type='REFERRAL'", (participant_a["id"],)).fetchone()["n"] == 1

        with raises(DomainError) as owner_error:
            call(conn, "GET", f"/api/game-sessions/{session_a}", context=ctx(token_b))
        assert (owner_error.value.code, owner_error.value.status) == ("SESSION_NOT_FOUND", 404)

    # Force a deterministic one-item last-stock competition.
    with admin_conn() as conn:
        conn.execute("update dino.prize set is_active=(id in ('test_coffee','test_no_prize')),probability=case id when 'test_coffee' then 1 else 0 end")
        conn.execute("update dino.inventory_item set status='VOID'")
        conn.execute("update dino.inventory_item set status='AVAILABLE' where id=(select id from dino.inventory_item where prize_id='test_coffee' order by id limit 1)")

    with app_conn() as conn:
        token_c, _, _ = create_participant(conn, "c")
        token_d, _, _ = create_participant(conn, "d")
        session_c, _ = verified_session(conn, token_c, "session-c", 100)
        session_d, _ = verified_session(conn, token_d, "session-d", 100)

    def do_draw(token_hash, session_id):
        with app_conn() as conn:
            return call(conn, "POST", "/api/draws", {"session_id": session_id, "pouch_index": 1}, context=ctx(token_hash))[1]

    with ThreadPoolExecutor(max_workers=2) as pool:
        draws = list(pool.map(lambda args: do_draw(*args), [(token_c, session_c), (token_d, session_d)]))
    assert sum(1 for draw in draws if draw["is_won"]) == 1
    winner = next(draw for draw in draws if draw["is_won"])
    winner_token = token_c if winner["session_id"] == session_c else token_d
    loser_token = token_d if winner_token == token_c else token_c

    with app_conn() as conn:
        with raises(DomainError) as owner_error:
            call(conn, "POST", f"/api/claims/{winner['claim_id']}/submit",
                 {"recipient_name": "TEST_BAD", "contact_phone": "01000000000", "consent": True}, context=ctx(loser_token))
        assert owner_error.value.status == 404
        with raises(DomainError) as synthetic_error:
            call(conn, "POST", f"/api/claims/{winner['claim_id']}/submit",
                 {"recipient_name": "실명", "contact_phone": "01012345678", "consent": True}, context=ctx(winner_token))
        assert synthetic_error.value.code == "SYNTHETIC_DATA_REQUIRED"
        payload = {"recipient_name": "TEST_USER", "contact_phone": "01000000000", "consent": True}
        _, claim = call(conn, "POST", f"/api/claims/{winner['claim_id']}/submit", payload, context=ctx(winner_token))
        _, retry_claim = call(conn, "POST", f"/api/claims/{winner['claim_id']}/submit", payload, context=ctx(winner_token))
        assert claim == retry_claim
        assert claim["status"] == "TEST_ISSUED" and claim["coupon_code"].startswith("TEST-")
        assert conn.execute("select count(*)::int n from dino.delivery_attempt where claim_id=%s", (winner["claim_id"],)).fetchone()["n"] == 1

        token_replay, _, _ = create_participant(conn, "r")
        _, replay_session = call(conn, "POST", "/api/game-sessions", {"idempotency_key": "replay-session"}, context=ctx(token_replay))
        call(conn, "POST", f"/api/game-sessions/{replay_session['session_id']}/start", context=ctx(token_replay))
        _, replay_result = call(conn, "POST", f"/api/game-sessions/{replay_session['session_id']}/finish",
            {"score": 1000, "valid_ticks": 600, "version": "1.2.0"},
            context=ctx(token_replay, verification={"valid": True, "score": 1000, "valid_ticks": 600, "reason": "VERIFIED"}))
        assert replay_result["eligible_for_draw"] is False
        assert replay_result["verification_result"] == "IMPOSSIBLE_WALLCLOCK_DURATION"

        events = [
            {"event_id": "metric-home-view", "event_name": "page_view", "screen": "home", "channel": "qr"},
            {"event_id": "metric-gemini-click", "event_name": "gemini_link_click", "screen": "benefit", "channel": "qr"},
            {"event_id": "metric-benefit-view", "event_name": "page_view", "screen": "benefit", "channel": "qr"},
            {"event_id": "metric-privacy-check", "event_name": "client_error", "screen": "phone-01012345678", "channel": "token-secret", "error_code": "name-hong"},
        ]
        call(conn, "POST", "/api/events", {"events": events}, context=ctx(winner_token))
        sanitized = conn.execute("select screen,channel,error_code from dino.analytics_event where event_id='metric-privacy-check'").fetchone()
        assert sanitized == {"screen": "unknown", "channel": "qr", "error_code": "unknown"}

    with admin_conn() as conn:
        conn.execute("""update dino.inventory_item set status='AVAILABLE',reserved_by_draw_id=null,reserved_at=null,issued_at=null
            where id=(select id from dino.inventory_item where status='VOID' and prize_id='test_coffee' order by id limit 1)""")
    with app_conn() as conn:
        token_expiry, _, _ = create_participant(conn, "e")
        session_expiry, _ = verified_session(conn, token_expiry, "session-expiry", 90)
        _, expiry_draw = call(conn, "POST", "/api/draws", {"session_id": session_expiry, "pouch_index": 0}, context=ctx(token_expiry))
        assert expiry_draw["is_won"] is True
    with admin_conn() as conn:
        conn.execute("update dino.claim set expires_at=now()-interval '1 second' where id=%s", (expiry_draw["claim_id"],))
    with app_conn() as conn:
        _, owned_claims = call(conn, "GET", "/api/claims", context=ctx(token_expiry))
        expired = next(item for item in owned_claims["claims"] if item["id"] == expiry_draw["claim_id"])
        assert expired["status"] == "EXPIRED"
        inventory_status = conn.execute("select i.status from dino.inventory_item i join dino.claim c on c.inventory_item_id=i.id where c.id=%s", (expiry_draw["claim_id"],)).fetchone()["status"]
        assert inventory_status == "EXPIRED"

    admin_id = "00000000-0000-0000-0000-000000000001"
    with admin_conn() as conn:
        conn.execute("insert into dino.admin_member(auth_user_id) values(%s)", (admin_id,))
    today = dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date().isoformat()
    with app_conn() as conn:
        _, default_metrics = call(conn, "GET", "/api/admin/overview", query={"from": today, "to": today}, context=ctx(admin_user_id=admin_id))
        assert default_metrics["totals"]["participants"] == 0
        _, metrics = call(conn, "GET", "/api/admin/overview", query={"from": today, "to": today, "include_synthetic": "true"}, context=ctx(admin_user_id=admin_id))
        qr = next(row for row in metrics["channels"] if row["channel"] == "qr")
        assert qr["gemini_clicks"] == 1 and qr["page_views"] == 2
        benefit = next(row for row in metrics["screen_metrics"] if row["screen"] == "benefit")
        assert benefit["estimated_exits"] == 1
        _, adjusted = call(conn, "POST", "/api/admin/tickets/adjust",
            {"participant_id": participant_a["id"], "delta": 2, "reason": "integration test", "idempotency_key": "admin-adjust-01"},
            context=ctx(admin_user_id=admin_id))
        assert adjusted["tickets"] >= 2
        with raises(DomainError) as conflict:
            call(conn, "POST", "/api/admin/tickets/adjust",
                {"participant_id": participant_a["id"], "delta": 3, "reason": "integration test", "idempotency_key": "admin-adjust-01"},
                context=ctx(admin_user_id=admin_id))
        assert conflict.value.code == "IDEMPOTENCY_CONFLICT"


def dino_app_cannot_mutate_provisioning_or_membership():
    for statement in (
        "update dino.environment_guard set project_ref='changed'",
        "insert into dino.schema_version(version) values('bad')",
        "insert into dino.admin_member(auth_user_id) values('00000000-0000-0000-0000-000000000002')",
        "delete from dino.ticket_ledger",
    ):
        with app_conn() as conn, raises(errors.InsufficientPrivilege):
            with conn.transaction():
                conn.execute(statement)


class OperationsIntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        clean_database()

    def test_01_phase1_transactions(self):
        phase1_transactions_ownership_referral_stock_claim_and_metrics()

    def test_02_privilege_boundaries(self):
        dino_app_cannot_mutate_provisioning_or_membership()
