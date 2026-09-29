import json
import sys
import unittest
from pathlib import Path
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import observability


class FakeResult:
    def __init__(self, row):
        self.row = row

    def fetchone(self):
        return self.row


class FakeConnection:
    def __init__(self, row):
        self.row = row
        self.calls = []

    def execute(self, query, params):
        self.calls.append((query, params))
        return FakeResult(self.row)


class ObservabilityTest(unittest.TestCase):
    def test_route_normalization_keeps_only_allowlisted_templates(self):
        self.assertEqual(
            observability.normalize_route("/api/game-sessions/private-session-token/finish"),
            "/api/game-sessions/{id}/finish",
        )
        self.assertEqual(
            observability.normalize_route("/api/referrals/share-intents/private-share-token"),
            "/api/referrals/share-intents/{id}",
        )
        self.assertEqual(observability.normalize_route("/api/private/user@example.com"), "/api/unknown")

    def test_request_log_has_fixed_fields_and_excludes_request_data(self):
        secret = "Bearer private-cookie-and-contact-01012345678"
        record = observability.request_log(
            environment="production",
            campaign="gemini_campaign",
            deployment="dpl_123",
            route=observability.normalize_route("/api/claims/private-claim/submit"),
            method="POST",
            status=409,
            duration_ms=12.6,
            request_id="11111111-1111-4111-8111-111111111111",
            error_code="SHARE_STEP_REQUIRED",
            operation=secret,
        )
        serialized = observability.serialize(record)
        self.assertEqual(set(record), {
            "event", "service", "env", "campaign", "deployment", "route", "method",
            "status", "duration_ms", "request_id", "outcome", "operation_outcome",
            "error_class", "error_code", "database_failure",
        })
        self.assertEqual((record["route"], record["outcome"], record["error_class"]),
                         ("/api/claims/{id}/submit", "client_error", "domain"))
        self.assertNotIn(secret, serialized)
        self.assertEqual(json.loads(serialized)["duration_ms"], 13)

    def test_database_failure_is_classified_without_exposing_exception_text(self):
        record = observability.request_log(
            environment="preview", campaign="campaign", deployment="dpl_123",
            route="/api/health", method="GET", status=503, duration_ms=3,
            request_id="11111111-1111-4111-8111-111111111111",
            error_code="SERVICE_UNAVAILABLE", database_failure="connection",
        )
        self.assertEqual((record["outcome"], record["error_class"], record["database_failure"]),
                         ("server_error", "database", "connection"))

    def test_webhook_http_success_preserves_internal_processing_outcome(self):
        route = "/api/webhooks/kakao-share"
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "status": "confirmed", "reward_status": "granted"}), "webhook_reward_granted")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "status": "confirmed", "reward_status": "blocked_cap"}), "webhook_reward_blocked")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "status": "confirmed", "reward_status": "not_eligible"}), "webhook_not_eligible")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "status": "rejected"}), "webhook_rejected")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "duplicate": True}), "webhook_duplicate")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": True, "status": "confirmed", "reward_status": "unexpected"}), "webhook_processing_failed")
        self.assertEqual(observability.operation_outcome(route, 200, {"accepted": False}), "webhook_processing_failed")

    def test_health_check_is_read_only_and_inactive_campaign_is_healthy(self):
        settings = SimpleNamespace(
            environment="production", deployment="dpl_123", project_ref="project",
            schema_name="dino_prod", synthetic_only=False,
        )
        for campaign_status in ("PAUSED", "ENDED"):
            with self.subTest(campaign_status=campaign_status):
                conn = FakeConnection({
                    "database_check": 1,
                    "campaign_status": campaign_status,
                    "game_version": "1.2.0",
                    "inventory_remaining": 12,
                })
                result = observability.health_snapshot(
                    conn, settings, {"campaign_id": "campaign", "test_seed": False}, "dino_prod"
                )
                self.assertTrue(result["ok"])
                self.assertTrue(result["schema_valid"])
                self.assertEqual((result["database"], result["campaign_status"]), ("ready", campaign_status))
                self.assertEqual(len(conn.calls), 1)
                query, params = conn.calls[0]
                self.assertIn("select 1::int database_check", query.lower())
                self.assertNotRegex(query.lower(), r"\b(insert|update|delete)\b")
                self.assertEqual(params, ("campaign",))

    def test_health_check_rejects_missing_database_result(self):
        settings = SimpleNamespace(
            environment="production", deployment="dpl_123", project_ref="project",
            schema_name="dino_prod", synthetic_only=False,
        )
        with self.assertRaises(observability.HealthCheckFailed):
            observability.health_snapshot(
                FakeConnection(None), settings,
                {"campaign_id": "campaign", "test_seed": False}, "dino_prod",
            )


if __name__ == "__main__":
    unittest.main()
