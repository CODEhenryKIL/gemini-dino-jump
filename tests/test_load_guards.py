import importlib.util
import json
import stat
import tempfile
import time
import unittest
import urllib.error
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase1_load", ROOT / "scripts" / "phase1_load.py")
load = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(load)


class LoadGuardTests(unittest.TestCase):
    def test_required_profiles_are_exact_and_full_is_690_seconds(self):
        self.assertEqual(load.PROFILES["10"], ((10, 60, False),))
        self.assertEqual(load.PROFILES["50"], ((50, 120, False),))
        self.assertEqual(load.PROFILES["100"], ((100, 180, False),))
        self.assertEqual(load.PROFILES["200"], ((200, 300, False),))
        self.assertEqual(load.PROFILES["burst"], ((200, 30, True),))
        self.assertEqual(sum(stage[1] for stage in load.PROFILES["full"]), 690)

    def test_remote_target_and_preflight_reject_production_or_wrong_project(self):
        self.assertEqual(load.validate_target("https://exact-preview.vercel.app", "remote"), "https://exact-preview.vercel.app")
        with self.assertRaises(load.SafetyError): load.validate_target("https://example.com", "remote")
        health = {"status": "ok", "database": "ok", "synthetic_only": True, "environment": "preview", "project_ref": load.EXPECTED_PROJECT_REF}
        config = {"environment": "preview", "game_version": load.GAME_VERSION}
        campaign = {"is_test": True, "real_prizes_enabled": False, "game_version": load.GAME_VERSION}
        load.validate_preflight("remote", health, config, campaign)
        with self.assertRaises(load.SafetyError): load.validate_preflight("remote", {**health, "environment": "production"}, {**config, "environment": "production"}, campaign)
        with self.assertRaises(load.SafetyError): load.validate_preflight("remote", {**health, "project_ref": "wrong"}, config, campaign)

    def test_budget_ledger_is_0600_cumulative_and_has_no_silent_reset(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            with load.BudgetLedger(path) as ledger:
                ledger.reserve_duration(690, "full"); ledger.consume_call(); ledger.consume_call()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.data["duration_seconds"], 690); self.assertEqual(ledger.data["api_calls"], 2)
                ledger.data["api_calls"] = load.MAX_API_CALLS; ledger._write()
                with self.assertRaises(load.BudgetExceeded): ledger.consume_call()
            with load.BudgetLedger(path) as ledger:
                ledger.data["duration_seconds"] = load.MAX_DURATION_SECONDS; ledger._write()
                with self.assertRaises(load.BudgetExceeded): ledger.reserve_duration(1, "over")

    def test_ledger_lock_is_nonblocking_and_token_cursor_persists(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            fingerprint = load.cohort_fingerprint(["private-token-0000", "private-token-0001"])
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.claim_token(fingerprint, 2), 0)
                with self.assertRaises(load.SafetyError): load.BudgetLedger(path)
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.claim_token(fingerprint, 2), 1)
                self.assertEqual(ledger.tokens_remaining(fingerprint, 2), 0)

    def test_token_file_requires_5000_unique_private_tokens_for_remote(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "tokens.json"
            cohort = {"schema": "dino-load-cohort-v1", "environment": "preview", "project_ref": load.EXPECTED_PROJECT_REF, "tokens": [f"private-token-{i:05d}" for i in range(4999)]}
            path.write_text(json.dumps(cohort)); path.chmod(0o600)
            with self.assertRaises(load.SafetyError): load.load_tokens(path, "remote")
            cohort["tokens"].append("private-token-04999"); path.write_text(json.dumps(cohort)); path.chmod(0o600)
            self.assertEqual(len(load.load_tokens(path, "remote")), 5000)
            cohort["project_ref"] = "wrongprojectrefxxxxx"; path.write_text(json.dumps(cohort)); path.chmod(0o600)
            with self.assertRaises(load.SafetyError): load.load_tokens(path, "remote")

    def test_no_jump_payload_is_verified_by_real_simulator_and_waits_real_time(self):
        score, ticks, wait_seconds = load.legal_no_jump(123456)
        valid, verified_score, verified_ticks, reason = load.game_verifier.simulate_and_verify(123456, [], score, ticks)
        self.assertEqual((valid, verified_score, verified_ticks, reason), (True, score, ticks, "VERIFIED"))
        self.assertGreaterEqual(wait_seconds, ticks / 60)

    def test_reports_normalize_dynamic_ids_and_dry_run_stays_bounded(self):
        self.assertEqual(load.endpoint_label("POST", "/api/game-sessions/gs_secret/finish"), "POST /api/game-sessions/{id}/finish")
        self.assertEqual(load.endpoint_label("POST", "/api/claims/claim_secret/submit"), "POST /api/claims/{id}/submit")
        report = load.dry_run("full", 5000)
        self.assertEqual(report["planned_duration_seconds"], 690)
        self.assertEqual(report["reserved_duration_seconds"], 780)
        self.assertEqual(report["think_time_seconds"], 45)
        self.assertEqual(report["flow_attempts_ceiling"], 2170)
        self.assertEqual(report["cohort_tokens_required_ceiling"], 2172)
        self.assertEqual(report["script_api_calls_ceiling"], 17801)
        self.assertEqual(report["absolute_api_calls_ceiling"], 23877)
        self.assertEqual(report["mutating_api_requests_ceiling"], 15626)
        self.assertEqual(report["client_analytics_events_ceiling"], 2170)
        self.assertEqual(report["server_domain_event_attempts_ceiling"], 6727)
        self.assertTrue(report["within_hard_api_call_cap"])
        self.assertTrue(report["within_prepared_cohort"])
        self.assertIn("not database-row counts or monetary price estimates", report["traffic_estimate_note"])
        self.assertEqual(report["hard_api_call_ceiling"], 30_000)
        self.assertFalse(report["real_prizes"])

    def test_preflight_network_failure_still_writes_sanitized_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory); token_path = root / "tokens.json"; ledger_path = root / "ledger.json"; report_path = root / "report.json"
            token_path.write_text(json.dumps({"schema": "dino-load-cohort-v1", "environment": "local", "tokens": [f"private-token-{index:04d}" for index in range(12)]})); token_path.chmod(0o600)
            result = load.main(["--mode", "local", "--base-url", "http://127.0.0.1:9", "--tokens", str(token_path), "--ledger", str(ledger_path), "--report", str(report_path), "--timeout", "0.1"])
            self.assertEqual(result, 2)
            report = json.loads(report_path.read_text())
            self.assertTrue(report["serious_stop"])
            self.assertEqual(report["failure"]["reason"], "Network preflight or request failed")
            self.assertNotIn("private-token", report_path.read_text())

    def test_valid_token_auth_rejection_is_a_serious_stop(self):
        with tempfile.TemporaryDirectory() as directory, load.BudgetLedger(Path(directory) / "ledger.json") as ledger:
            stop = load.threading.Event(); client = load.Client("http://127.0.0.1:8080", ledger, load.Metrics(), 1, stop, time.monotonic() + 5)
            rejected = urllib.error.HTTPError("http://127.0.0.1:8080/api/me", 401, "unauthorized", {}, None)
            with mock.patch.object(load.urllib.request, "urlopen", side_effect=rejected):
                with self.assertRaises(load.SeriousFailure): client.request("GET", "/api/me", "valid-private-token")
            self.assertTrue(stop.is_set())


if __name__ == "__main__": unittest.main()
