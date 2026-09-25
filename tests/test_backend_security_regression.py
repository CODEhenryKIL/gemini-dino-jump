import contextlib
import datetime as dt
import http.client
import json
import os
import secrets
import sys
import threading
import unittest
import urllib.parse
import uuid
from pathlib import Path
from unittest import mock

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import app
from config import Settings


DSN = os.getenv(
    "PHASE1_TEST_DATABASE_URL",
    "postgres://postgres@127.0.0.1:55433/dino_phase1_v2_test",
)
PEPPER = "test-pepper-0123456789-test-pepper"
ADMIN_ID = "11111111-1111-4111-8111-111111111111"


@contextlib.contextmanager
def _application_connection(_settings):
    """Use the real test DB through the same restricted role as the server."""
    with psycopg.connect(DSN, autocommit=True, row_factory=dict_row) as conn:
        conn.execute("set role dino_dev_app")
        yield conn


class BackendSecurityRegressionTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(("127.0.0.1", 0), app.DinoJumpHandler)
        host, port = cls.server.server_address
        cls.base_url = f"http://{host}:{port}"
        cls.settings = Settings(
            environment="test",
            database_url=DSN,
            project_ref="local",
            base_url=cls.base_url,
            benefit_url="https://gemini.google.com/students",
            supabase_url="http://127.0.0.1:54321",
            publishable_key="test-publishable-key",
            token_pepper=PEPPER,
            allowed_origins=frozenset({cls.base_url}),
            deployment="security-regression",
        )
        cls.patches = [
            mock.patch.object(app.Settings, "from_env", side_effect=lambda: cls.settings),
            mock.patch.object(app.db, "connection", side_effect=_application_connection),
            mock.patch.object(app.auth, "verify_admin_identity", return_value=ADMIN_ID),
        ]
        for patcher in cls.patches:
            patcher.start()
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        for patcher in reversed(cls.patches):
            patcher.stop()

    def setUp(self):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "truncate dino_dev.rate_limit_bucket,dino_dev.idempotency_request,"
                "dino_dev.analytics_event,dino_dev.admin_audit,dino_dev.claim_contact,"
                "dino_dev.claim,dino_dev.inventory_history,dino_dev.draw,"
                "dino_dev.ranking_contact,dino_dev.best_score,dino_dev.game_session,"
                "dino_dev.invitation_reward,dino_dev.invitation_visit,dino_dev.ticket_ledger,"
                "dino_dev.bootstrap,dino_dev.observation,dino_dev.participant,"
                "dino_dev.admin_member restart identity cascade"
            )
            conn.execute(
                "update dino_dev.inventory_item set status='AVAILABLE',"
                "reserved_by_draw_id=null,reserved_at=null,paid_at=null"
            )

    def request(self, method, path, body=None, *, cookie=None, headers=None):
        parsed = urllib.parse.urlsplit(self.base_url)
        conn = http.client.HTTPConnection(parsed.hostname, parsed.port, timeout=10)
        request_headers = {"Origin": self.base_url}
        if body is not None:
            payload = json.dumps(body).encode()
            request_headers["Content-Type"] = "application/json"
            request_headers["Content-Length"] = str(len(payload))
        else:
            payload = None
        if cookie:
            request_headers["Cookie"] = cookie
        if headers:
            request_headers.update(headers)
        conn.request(method, path, body=payload, headers=request_headers)
        response = conn.getresponse()
        raw = response.read()
        result = json.loads(raw) if raw else None
        set_cookie = response.getheader("Set-Cookie")
        conn.close()
        return response.status, result, set_cookie.split(";", 1)[0] if set_cookie else None

    @staticmethod
    def idem(label):
        return f"{label}-{secrets.token_urlsafe(24)}"

    def participant(self, *, event_id=None, observation_id=None, observation_key=None):
        event_id = event_id or f"evt_{secrets.token_hex(12)}"
        observation_id = observation_id or f"obs_{secrets.token_hex(12)}"
        status, observed, _ = self.request(
            "POST",
            "/api/observations",
            {
                "event_id": event_id,
                "observation_id": observation_id,
                "link_kind": "direct",
                "channel_code": "security_test",
            },
            headers={"Idempotency-Key": observation_key or self.idem("observation")},
        )
        self.assertEqual(status, 201, observed)
        status, initialized, cookie = self.request(
            "POST",
            "/api/participants/anonymous",
            {
                "bootstrap_token": observed["bootstrap_token"],
                "observation_id": observation_id,
                "link_kind": "direct",
                "channel": "security_test",
            },
        )
        self.assertIn(status, (200, 201), initialized)
        self.assertIsNotNone(cookie)
        return initialized["participant"], cookie

    def create_started_session(self, cookie):
        status, created, _ = self.request(
            "POST",
            "/api/game-sessions",
            {"event_id": f"evt_{secrets.token_hex(12)}"},
            cookie=cookie,
            headers={"Idempotency-Key": self.idem("create-game")},
        )
        self.assertEqual(status, 201, created)
        session_id = created["session_id"]
        status, started, _ = self.request(
            "POST",
            f"/api/game-sessions/{session_id}/start",
            {"event_id": f"evt_{secrets.token_hex(12)}"},
            cookie=cookie,
            headers={"Idempotency-Key": self.idem("start-game")},
        )
        self.assertEqual(status, 200, started)
        return session_id

    def test_zero_tick_submission_cannot_finish_or_unlock_draw(self):
        _participant, cookie = self.participant()
        session_id = self.create_started_session(cookie)

        status, result, _ = self.request(
            "POST",
            f"/api/game-sessions/{session_id}/finish",
            {
                "event_id": f"evt_{secrets.token_hex(12)}",
                "score": 0,
                "ticks": 0,
                "jump_ticks": [],
            },
            cookie=cookie,
            headers={"Idempotency-Key": self.idem("zero-finish")},
        )
        self.assertGreaterEqual(status, 400, result)

        status, draw, _ = self.request("GET", "/api/draws/me", cookie=cookie)
        self.assertEqual(status, 200, draw)
        self.assertEqual(draw["status"], "LOCKED")

    def test_verifier_rejection_is_persisted_after_error_response(self):
        _participant, cookie = self.participant()
        session_id = self.create_started_session(cookie)
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "update dino_dev.game_session "
                "set started_at=clock_timestamp()-interval '2 seconds' where id=%s",
                (session_id,),
            )

        status, rejected, _ = self.request(
            "POST",
            f"/api/game-sessions/{session_id}/finish",
            {
                "event_id": f"evt_{secrets.token_hex(12)}",
                "score": 6000,
                "ticks": 120,
                "jump_ticks": [],
            },
            cookie=cookie,
            headers={"Idempotency-Key": self.idem("rejected-finish")},
        )
        self.assertEqual(status, 422, rejected)

        status, session, _ = self.request(
            "GET", f"/api/game-sessions/{session_id}", cookie=cookie
        )
        self.assertEqual(status, 200, session)
        self.assertEqual(session["status"], "REJECTED")
        self.assertEqual(session["refund"]["status"], "NOT_DUE")

    def test_paid_claim_is_terminal_and_assignee_must_be_active_admin(self):
        participant, _cookie = self.participant()
        invalid_assignee = str(uuid.uuid4())
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "insert into dino_dev.admin_member"
                "(auth_user_id,display_name,permissions) values(%s,'Security Admin',%s)",
                (ADMIN_ID, ["claims:read", "claims:write"]),
            )
            conn.execute(
                "insert into dino_dev.claim"
                "(id,campaign_id,participant_id,claim_type,status,version,paid_at) "
                "values('claim_paid_security','gemini_dino_phase1_test',%s,'RANKING','PAID',1,clock_timestamp()),"
                "('claim_pending_security','gemini_dino_phase1_test',%s,'DRAW','PENDING_REVIEW',1,null)",
                (participant["id"], participant["id"]),
            )

        admin_headers = {"Authorization": "Bearer test-admin-token"}
        paid_status, paid_result, _ = self.request(
            "PATCH",
            "/api/admin/claims/claim_paid_security",
            {
                "status": "CONTACTED",
                "expected_version": 1,
                "assignee_user_id": ADMIN_ID,
                "event_id": f"evt_{secrets.token_hex(12)}",
            },
            headers={**admin_headers, "Idempotency-Key": self.idem("paid-terminal")},
        )
        invalid_status, invalid_result, _ = self.request(
            "PATCH",
            "/api/admin/claims/claim_pending_security",
            {
                "status": "CONTACTED",
                "expected_version": 1,
                "assignee_user_id": invalid_assignee,
                "event_id": f"evt_{secrets.token_hex(12)}",
            },
            headers={**admin_headers, "Idempotency-Key": self.idem("invalid-assignee")},
        )

        self.assertGreaterEqual(paid_status, 400, paid_result)
        self.assertGreaterEqual(invalid_status, 400, invalid_result)
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            paid = conn.execute(
                "select status,version from dino_dev.claim where id='claim_paid_security'"
            ).fetchone()
            pending = conn.execute(
                "select status,assignee_user_id,version from dino_dev.claim "
                "where id='claim_pending_security'"
            ).fetchone()
        self.assertEqual((paid["status"], paid["version"]), ("PAID", 1))
        self.assertEqual(
            (pending["status"], pending["assignee_user_id"], pending["version"]),
            ("PENDING_REVIEW", None, 1),
        )

    def test_known_observation_ids_cannot_recover_existing_identity(self):
        event_id = f"evt_known_{secrets.token_hex(8)}"
        observation_id = f"obs_known_{secrets.token_hex(8)}"
        victim, victim_cookie = self.participant(
            event_id=event_id,
            observation_id=observation_id,
            observation_key=self.idem("victim-observation"),
        )

        replay_status, replay, _ = self.request(
            "POST",
            "/api/observations",
            {
                "event_id": event_id,
                "observation_id": observation_id,
                "link_kind": "direct",
                "channel_code": "security_test",
            },
            headers={"Idempotency-Key": self.idem("attacker-observation")},
        )
        if replay_status >= 400:
            self.assertLess(replay_status, 500, replay)
            return

        init_status, attacker, attacker_cookie = self.request(
            "POST",
            "/api/participants/anonymous",
            {
                "bootstrap_token": replay["bootstrap_token"],
                "observation_id": observation_id,
                "link_kind": "direct",
                "channel": "security_test",
            },
        )
        if init_status >= 400:
            self.assertLess(init_status, 500, attacker)
            return
        self.assertNotEqual(attacker["participant"]["id"], victim["id"])
        self.assertNotEqual(attacker_cookie, victim_cookie)

    def test_analytics_dimensions_reject_pii_and_preserve_frontend_catalogue(self):
        _participant, cookie = self.participant()
        now = dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00", "Z")
        valid = [
            ("loading_checkpoint", "loading", {"checkpoint": 3, "bucket": "3s+"}),
            ("game_checkpoint", "game", {"checkpoint": 36000, "stage": "stage_6"}),
            ("share_attempted", "invite", {"share_method": "copy", "status": "copied", "share_id": "share_safe_123456"}),
            ("pouch_selected", "draw", {"action": "pouch_2"}),
            ("content_clicked", "content", {"content": "study"}),
            ("gemini_cta_viewed", "benefit", {"position": "benefit_main"}),
            ("screen_left", "home", {"reason": "navigation"}),
            ("page_view", "home", {"source": "phase1_load", "channel": "school_01", "campaign_code": "gemini_2026"}),
        ]
        rejected = [
            ("content_clicked", "content", {"content": "01012345678"}),
            ("share_attempted", "invite", {"share_method": "copy", "status": "person_name"}),
            ("game_checkpoint", "game", {"checkpoint": 36001, "stage": "stage_7"}),
            ("page_view", "home", {"source": "person_name", "channel": "01012345678"}),
            ("content_clicked", "content", {"content": ["study"]}),
            ("share_attempted", "invite", {"status": {"value": "copied"}}),
        ]
        events = []
        for index, (name, screen, dimensions) in enumerate(valid + rejected):
            events.append({
                "event_id": f"evt_dimension_{index:02d}_{secrets.token_hex(6)}",
                "name": name,
                "screen": screen,
                "occurred_at": now,
                "dimensions": dimensions,
            })
        status, result, _ = self.request(
            "POST", "/api/events/batch", {"events": events}, cookie=cookie,
            headers={"Idempotency-Key": self.idem("analytics-dimensions")},
        )
        self.assertEqual(status, 202, result)
        self.assertEqual(result, {"accepted": len(valid), "duplicates": 0, "rejected": len(rejected)})
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            stored = conn.execute("select dimensions from dino_dev.analytics_event where source='client'").fetchall()
        encoded = json.dumps([row["dimensions"] for row in stored], ensure_ascii=False)
        self.assertNotIn("01012345678", encoded)
        self.assertNotIn("person_name", encoded)
        self.assertIn("stage_6", encoded)
        self.assertIn("study", encoded)


if __name__ == "__main__":
    unittest.main()
