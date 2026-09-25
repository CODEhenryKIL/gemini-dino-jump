import json
import io
import os
import sys
import tempfile
import threading
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase2_load


def health(environment="preview"):
    return {
        "ok": True,
        "database": "ready",
        "service": "gemini-dino-jump",
        "environment": environment,
        "project_ref": phase2_load.base.EXPECTED_PROJECT_REF,
        "schema": phase2_load.base.EXPECTED_SCHEMA,
        "synthetic_only": True,
        "test_seed": True,
        "deployment": "dpl_phase2",
    }


def config(version="2.0.0"):
    project = phase2_load.base.EXPECTED_PROJECT_REF
    return {
        "campaign": {"id": "phase2-test", "status": "ACTIVE", "game_version": version},
        "auth": {"supabase_url": f"https://{project}.supabase.co"},
    }


class Phase2LoadSafetyTests(unittest.TestCase):
    def test_dry_run_is_default_and_never_touches_network_or_fixture_subprocess(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network attempted")), mock.patch(
            "subprocess.run", side_effect=AssertionError("fixture subprocess attempted")
        ):
            self.assertEqual(phase2_load.main([]), 0)
        report = phase2_load.dry_run()
        self.assertEqual(report["network_calls"], 0)
        self.assertEqual(report["phase"], 2)
        self.assertEqual(report["absolute_api_calls_ceiling"], 6632)
        self.assertEqual(report["estimated_cost"], "TBD")

    def test_phase2_budget_exhaustion_is_fail_closed(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phase2-ledger.json"
            path.write_text(json.dumps({
                "version": 2,
                "phase": 2,
                "admitted_api_calls": phase2_load.MAX_API_CALLS,
                "completed_api_calls": phase2_load.MAX_API_CALLS,
                "duration_reserved_seconds": 0,
                "runs": [],
                "cohorts": {},
                "external_cohort_calls": {},
            }))
            os.chmod(path, 0o600)
            with phase2_load.Phase2BudgetLedger(path) as ledger:
                with self.assertRaises(phase2_load.BudgetExceeded):
                    ledger.admit_call()

    def test_phase1_ledger_cannot_be_reused_or_overwritten(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phase1-ledger.json"
            path.write_text(json.dumps({
                "version": 2,
                "admitted_api_calls": 10,
                "completed_api_calls": 10,
                "duration_reserved_seconds": 10,
                "runs": [],
                "cohorts": {},
                "external_cohort_calls": {},
            }))
            os.chmod(path, 0o600)
            before = path.read_bytes()
            with self.assertRaisesRegex(phase2_load.SafetyError, "non-Phase-2 ledger"):
                phase2_load.Phase2BudgetLedger(path)
            self.assertEqual(path.read_bytes(), before)

    def test_version_mismatch_is_rejected(self):
        with self.assertRaisesRegex(phase2_load.SafetyError, "game version 2.0.0"):
            phase2_load.validate_phase2_preflight(
                "remote", health(), config("1.2.0"), phase2_load.base.EXPECTED_PROJECT_REF,
                "dpl_phase2", "phase2-test",
            )

    def test_remote_approval_is_phase2_and_exactly_bounded(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "approval.json"
            marker = {
                "phase": 2,
                "approved_remote": True,
                "base_url": "https://phase2-preview.vercel.app",
                "deployment_id": "dpl_phase2",
                "campaign_id": "phase2-test",
                "max_api_calls": 10_000,
                "max_duration_seconds": 720,
                "stages": ["100-stage", "200-burst"],
            }
            path.write_text(json.dumps(marker))
            os.chmod(path, 0o600)
            loaded = phase2_load.load_approval_marker(
                path, marker["base_url"], marker["deployment_id"], marker["campaign_id"]
            )
            self.assertEqual(loaded["phase"], 2)
            marker["max_api_calls"] = 10_001
            path.write_text(json.dumps(marker))
            os.chmod(path, 0o600)
            with self.assertRaisesRegex(phase2_load.SafetyError, "does not match"):
                phase2_load.load_approval_marker(
                    path, marker["base_url"], marker["deployment_id"], marker["campaign_id"]
                )

    def test_platform_auth_files_require_private_permissions_and_exact_formats(self):
        with tempfile.TemporaryDirectory() as temporary:
            root = Path(temporary)
            token = root / "protection-token"
            cookie = root / "deployment-cookie"
            token.write_text("private-protection-token", encoding="utf-8")
            cookie.write_text("_vercel_sso_nonce=" + "v" * 32, encoding="utf-8")
            token.chmod(0o644)
            cookie.chmod(0o600)
            with self.assertRaisesRegex(phase2_load.SafetyError, "permissions"):
                phase2_load.load_platform_auth(token, cookie)

            token.chmod(0o600)
            token.write_text("short", encoding="utf-8")
            with self.assertRaisesRegex(phase2_load.SafetyError, "protection bypass token"):
                phase2_load.load_platform_auth(token, cookie)

            token.write_text("private-protection-token", encoding="utf-8")
            cookie.write_text("two=cookies; forbidden=yes", encoding="utf-8")
            with self.assertRaisesRegex(phase2_load.SafetyError, "authentication cookie"):
                phase2_load.load_platform_auth(token, cookie)

            cookie.write_text("_vercel_sso_nonce=" + "v" * 32, encoding="utf-8")
            self.assertEqual(
                phase2_load.load_platform_auth(token, cookie),
                ("private-protection-token", "_vercel_sso_nonce=" + "v" * 32),
            )

    def test_platform_auth_headers_are_sent_but_never_enter_metrics_or_output(self):
        class Ledger:
            def admit_call(self): pass
            def complete_call(self): pass

        class Response:
            status = 200
            def __init__(self, url): self.url = url
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def geturl(self): return self.url
            def read(self, _limit): return b'{"ok":true}'

        protection = "private-protection-token"
        auth_cookie = "_vercel_sso_nonce=" + "v" * 32
        metrics = phase2_load.base.Metrics()
        client = phase2_load.base.HttpClient(
            "http://127.0.0.1:8080", Ledger(), metrics, 1, threading.Event(),
            phase2_load.time.monotonic() + 5, protection, auth_cookie,
        )
        captured = {}

        def respond(request, **_kwargs):
            captured.update({key.lower(): value for key, value in request.header_items()})
            return Response(request.full_url)

        output = io.StringIO()
        with redirect_stdout(output), redirect_stderr(output), mock.patch.object(
            phase2_load.urllib.request, "urlopen", side_effect=respond
        ):
            client.request("GET", "/api/health", "preflight")
        self.assertEqual(captured["x-vercel-protection-bypass"], protection)
        self.assertEqual(captured["cookie"], auth_cookie)
        observable = output.getvalue() + json.dumps(metrics.report(1), sort_keys=True)
        self.assertNotIn(protection, observable)
        self.assertNotIn(auth_cookie, observable)

    def test_known_v2_fixture_has_server_verifiable_coin_and_repeat_revive_path(self):
        result = phase2_load.rich_fixture(4)
        self.assertGreaterEqual(result["summary"]["coins"], 1)
        self.assertGreaterEqual(result["summary"]["revives"], 2)
        self.assertEqual(result["end_reason"], "COLLISION")
        self.assertLessEqual(result["ticks"], phase2_load.MAX_FIXTURE_TICKS)

    def test_long_rich_path_falls_back_to_a_real_bounded_collision(self):
        result = phase2_load.rich_fixture(5)
        verified = phase2_load.game_verifier.verify_game(
            phase2_load.GAME_VERSION, 5, result["jump_ticks"], result["score"], result["ticks"]
        )
        self.assertTrue(verified["valid"])
        self.assertEqual(result["end_reason"], "COLLISION")
        self.assertLessEqual(result["ticks"], phase2_load.MAX_FIXTURE_TICKS)
        self.assertLess(result["summary"]["revives"], 2)

    def test_burst_workers_attempt_exactly_one_flow_even_at_minimum_think_time(self):
        attempts = []

        class Ledger:
            def __init__(self): self.next = 0
            def claim_participant(self, *_args):
                value = self.next
                self.next += 1
                return value

        class Client:
            def __init__(self):
                self.stop = threading.Event()
                self.metrics = phase2_load.base.Metrics()
                self.stage_metrics = None

        cohort = {"participants": [{"cookie": str(index)} for index in range(8)], "campaign_id": "phase2-test"}
        with mock.patch.object(phase2_load, "phase2_user_flow", side_effect=lambda _client, participant, _sequence: attempts.append(participant["cookie"])):
            report = phase2_load.run_stage(
                Client(), cohort, Ledger(), "fingerprint", 4, 30, True, "200-burst",
                [0], threading.Lock(), 10,
            )
        self.assertEqual(len(attempts), 4)
        self.assertEqual(len(set(attempts)), 4)
        self.assertEqual(report["metrics"]["flows_completed"], 0)

    def test_default_envelope_and_per_stage_cleanup_reservation_remain_bounded(self):
        estimate = phase2_load.estimate_profile()
        self.assertEqual(estimate["flow_attempts_ceiling"], 600)
        self.assertEqual(estimate["absolute_api_calls_ceiling"], 6632)
        self.assertEqual(estimate["stages"][1]["flow_attempts_ceiling"], 200)
        self.assertEqual(phase2_load.estimate_profile(10)["stages"][1]["flow_attempts_ceiling"], 200)
        self.assertEqual(phase2_load.reserved_duration(), 390)
        self.assertLessEqual(phase2_load.reserved_duration(), phase2_load.MAX_DURATION_SECONDS)

    def test_rate_limit_timeout_and_unexpected_response_fail_the_stage(self):
        class Ledger:
            def claim_participant(self, *_args): return 0

        class Client:
            def __init__(self):
                self.stop = threading.Event()
                self.metrics = phase2_load.base.Metrics()
                self.stage_metrics = None

        cohort = {"participants": [{"cookie": "cookie"}], "campaign_id": "phase2-test"}
        for error in (
            phase2_load.RateLimited("limited"),
            TimeoutError("timed out"),
            phase2_load.UnexpectedResponse("unexpected"),
        ):
            with self.subTest(error=type(error).__name__), mock.patch.object(phase2_load, "phase2_user_flow", side_effect=error):
                client = Client()
                with self.assertRaises(type(error)):
                    phase2_load.run_stage(
                        client, cohort, Ledger(), "fingerprint", 1, 1, False, "stage",
                        [0], threading.Lock(), 10,
                    )
                self.assertTrue(client.stop.is_set())

    def test_failure_metrics_cannot_produce_a_successful_final_status(self):
        clean = {"rate_limited_429": 0, "timeouts": 0, "unexpected_failures": 0}
        self.assertIsNone(phase2_load.metrics_failure(clean))
        for field in clean:
            with self.subTest(field=field):
                report = {**clean, field: 1}
                failure = phase2_load.metrics_failure(report)
                self.assertEqual(failure["type"], "LoadMetricsFailure")
                self.assertIn(f"{field}=1", failure["reason"])

    def test_production_environment_is_rejected(self):
        with self.assertRaisesRegex(phase2_load.SafetyError, "Production"):
            phase2_load.validate_phase2_preflight(
                "remote", health("production"), config(), phase2_load.base.EXPECTED_PROJECT_REF,
                "dpl_phase2", "phase2-test",
            )


if __name__ == "__main__":
    unittest.main()
