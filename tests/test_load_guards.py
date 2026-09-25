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


def preview_health(**overrides):
    value = {
        "ok": True,
        "service": "gemini-dino-jump",
        "environment": "preview",
        "deployment": "dpl_test_123",
        "database": "ready",
        "project_ref": load.EXPECTED_PROJECT_REF,
        "schema": load.EXPECTED_SCHEMA,
        "synthetic_only": True,
        "test_seed": True,
    }
    value.update(overrides)
    return value


def preview_config(campaign_id="phase1-test"):
    return {
        "campaign": {
            "id": campaign_id,
            "title": "Synthetic test",
            "status": "ACTIVE",
            "game_version": load.GAME_VERSION,
        },
        "auth": {"supabase_url": f"https://{load.EXPECTED_PROJECT_REF}.supabase.co"},
    }


def cohort_data(count, environment="local", **overrides):
    value = {
        "schema_version": 1,
        "environment": environment,
        "project_ref": load.EXPECTED_PROJECT_REF,
        "base_url": "http://127.0.0.1:9",
        "deployment_id": None,
        "campaign_id": "phase1-test",
        "preparation_api_calls": 0,
        "participants": [
            {
                "cookie": f"dj_session={'a' * 32}{index:08d}",
                "participant_id": f"synthetic-{index}",
                "referral_code": f"ref-{index}",
            }
            for index in range(count)
        ],
    }
    value.update(overrides)
    return value


class FakeResponse:
    def __init__(self, url, status=200, body=None):
        self.url = url
        self.status = status
        self.body = json.dumps(body or {"ok": True}).encode()

    def __enter__(self):
        return self

    def __exit__(self, *_):
        return False

    def geturl(self):
        return self.url

    def read(self, _limit):
        return self.body


class ImmediateStop:
    def is_set(self):
        return False

    def wait(self, _seconds):
        return False


class LoadGuardTests(unittest.TestCase):
    def test_required_profiles_are_exact_and_total_690_seconds(self):
        self.assertEqual(load.PROFILES["10"], ((10, 60, False),))
        self.assertEqual(load.PROFILES["50"], ((50, 120, False),))
        self.assertEqual(load.PROFILES["100"], ((100, 180, False),))
        self.assertEqual(load.PROFILES["200"], ((200, 300, False),))
        self.assertEqual(load.PROFILES["burst"], ((200, 30, True),))
        self.assertEqual(sum(stage[1] for stage in load.PROFILES["full"]), 690)

    def test_remote_target_and_preflight_fail_closed(self):
        url = "https://exact-preview.vercel.app"
        self.assertEqual(load.validate_target(url, "remote"), url)
        for invalid in (
            "https://example.com",
            "http://exact-preview.vercel.app",
            "https://exact-preview.vercel.app/path",
            "https://user:pass@exact-preview.vercel.app",
        ):
            with self.assertRaises(load.SafetyError):
                load.validate_target(invalid, "remote")
        load.validate_preflight(
            "remote",
            preview_health(),
            preview_config(),
            load.EXPECTED_PROJECT_REF,
            "dpl_test_123",
            "phase1-test",
        )
        guards = (
            preview_health(environment="production"),
            preview_health(project_ref="wrong"),
            preview_health(schema="public"),
            preview_health(synthetic_only=False),
            preview_health(test_seed=False),
            preview_health(deployment="different"),
        )
        for health in guards:
            with self.assertRaises(load.SafetyError):
                load.validate_preflight(
                    "remote",
                    health,
                    preview_config(),
                    load.EXPECTED_PROJECT_REF,
                    "dpl_test_123",
                    "phase1-test",
                )

    def test_last_stock_probe_requires_one_synthetic_item(self):
        with self.assertRaises(load.SafetyError):
            load.validate_preflight(
                "remote",
                preview_health(test_inventory_remaining=2),
                preview_config(),
                load.EXPECTED_PROJECT_REF,
                "dpl_test_123",
                "phase1-test",
                True,
            )
        load.validate_preflight(
            "remote",
            preview_health(test_inventory_remaining=1),
            preview_config(),
            load.EXPECTED_PROJECT_REF,
            "dpl_test_123",
            "phase1-test",
            True,
        )

    def test_budget_ledger_is_locked_0600_and_charges_admission_before_completion(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            with load.BudgetLedger(path) as ledger:
                ledger.reserve_run(780, "full", "fingerprint", "dpl_test_123")
                ledger.admit_call()
                self.assertEqual(ledger.data["admitted_api_calls"], 1)
                self.assertEqual(ledger.data["completed_api_calls"], 0)
                with self.assertRaises(load.SafetyError):
                    load.BudgetLedger(path)
                ledger.complete_call()
            self.assertEqual(stat.S_IMODE(path.stat().st_mode), 0o600)
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.data["duration_reserved_seconds"], 780)
                self.assertEqual(ledger.data["completed_api_calls"], 1)

    def test_budget_and_fresh_participant_cursor_persist(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.claim_participant("fp", 2, "campaign"), 0)
            with load.BudgetLedger(path) as ledger:
                self.assertEqual(ledger.claim_participant("fp", 2, "campaign"), 1)
                self.assertEqual(ledger.participants_remaining("fp", 2), 0)
                with self.assertRaises(load.BudgetExceeded):
                    ledger.claim_participant("fp", 2, "campaign")
                ledger.data["admitted_api_calls"] = load.MAX_API_CALLS
                ledger._write()
                with self.assertRaises(load.BudgetExceeded):
                    ledger.admit_call()

    def test_cohort_preparation_calls_are_charged_once_to_same_cap(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "ledger.json"
            with load.BudgetLedger(path) as ledger:
                ledger.register_cohort_preparation("fp", 5_000)
                ledger.register_cohort_preparation("fp", 5_000)
                self.assertEqual(ledger.data["admitted_api_calls"], 5_000)
                self.assertEqual(ledger.data["completed_api_calls"], 5_000)
                with self.assertRaises(load.SafetyError):
                    ledger.register_cohort_preparation("fp", 4_999)

    def test_remote_cohort_requires_exactly_5000_private_cookie_identities(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "cohort.json"
            remote_url = "https://exact-preview.vercel.app"
            data = cohort_data(
                4_999,
                "preview",
                base_url=remote_url,
                deployment_id="dpl_test_123",
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            path.chmod(0o600)
            with self.assertRaises(load.SafetyError):
                load.load_cohort(path, "remote", remote_url, load.EXPECTED_PROJECT_REF, "dpl_test_123")
            data["participants"].append(
                {
                    "cookie": f"dj_session={'b' * 40}",
                    "participant_id": "synthetic-4999",
                    "referral_code": "ref-4999",
                }
            )
            path.write_text(json.dumps(data), encoding="utf-8")
            path.chmod(0o600)
            loaded = load.load_cohort(
                path, "remote", remote_url, load.EXPECTED_PROJECT_REF, "dpl_test_123"
            )
            self.assertEqual(len(loaded["participants"]), 5_000)
            path.chmod(0o644)
            with self.assertRaises(load.SafetyError):
                load.load_cohort(path, "remote", remote_url, load.EXPECTED_PROJECT_REF, "dpl_test_123")

    def test_cohort_fingerprint_is_stable_but_changes_with_identity(self):
        first = cohort_data(2)
        second = json.loads(json.dumps(first))
        self.assertEqual(load.cohort_fingerprint(first), load.cohort_fingerprint(second))
        second["participants"][0]["cookie"] += "x"
        self.assertNotEqual(load.cohort_fingerprint(first), load.cohort_fingerprint(second))

    def test_no_jump_payload_uses_real_physics_and_wait_duration(self):
        for seed in (1, 7, 123456, 2_147_483_646):
            score, ticks, wait_seconds = load.legal_no_jump(seed)
            valid, verified_score, verified_ticks, reason = load.game_verifier.simulate_and_verify(
                seed, [], score, ticks
            )
            self.assertEqual(
                (valid, verified_score, verified_ticks, reason),
                (True, score, ticks, "VERIFIED"),
            )
            self.assertGreaterEqual(wait_seconds, ticks / load.game_verifier.TICK_RATE)

    def test_stage_and_overall_flow_counts_are_both_recorded(self):
        overall = load.Metrics()
        stage = load.Metrics()
        client = mock.Mock(metrics=overall, stage_metrics=stage)
        client.metrics.flow()
        if client.stage_metrics:
            client.stage_metrics.flow()
        self.assertEqual(overall.report(1)["flows_completed"], 1)
        self.assertEqual(stage.report(1)["flows_completed"], 1)

    def test_performance_targets_separate_general_finish_draw_and_failures(self):
        report = {
            "api_calls": 200,
            "unexpected_failures": 1,
            "endpoints": {
                "GET /api/me": {"p95_ms": 900},
                "POST /api/game-sessions/{id}/finish": {"p95_ms": 1_900},
                "POST /api/draws": {"p95_ms": 2_100},
            },
        }
        result = load.evaluate_targets(report)
        self.assertTrue(result["general_api_p95_at_most_1000ms"])
        self.assertFalse(result["finish_draw_p95_at_most_2000ms"])
        self.assertTrue(result["unexpected_failure_rate_below_1_percent"])
        self.assertTrue(result["database_reconciliation_required"])

    def test_security_probe_uses_checkpointed_fault_and_recovery(self):
        calls = []
        created_sessions = []

        class StubClient:
            stop = ImmediateStop()

            def request(
                self,
                method,
                path,
                phase,
                cookie=None,
                body=None,
                idempotency_key=None,
                expected=(200,),
                expected_negative=False,
            ):
                calls.append((method, path, cookie, body, expected, expected_negative))
                if method == "GET" and path == "/api/me" and cookie is None:
                    return 401, {"error": "UNAUTHORIZED"}
                if method == "GET" and path == "/api/me":
                    return 200, {"tickets": {"initial": 1, "invitation": 0}}
                if path == "/api/observations":
                    if expected == (409,):
                        return 409, {"error": "IDEMPOTENCY_CONFLICT"}
                    return 201, {"observation_id": body["observation_id"], "bootstrap_token": "private"}
                if method == "POST" and path == "/api/game-sessions":
                    session_id = f"gs_probe_{len(created_sessions) + 1}"
                    created_sessions.append(session_id)
                    return 201, {"session_id": session_id}
                if method == "GET" and path.startswith("/api/game-sessions/gs_probe_"):
                    if cookie.endswith("2"):
                        return 404, {"error": "SESSION_NOT_FOUND"}
                    if path.endswith("_1"):
                        return 200, {
                            "status": "ABORTED",
                            "refund": {"status": "REFUNDED"},
                            "fault_review": {"status": "AUTO_APPROVED", "version": 2},
                        }
                    return 200, {
                        "status": "FAULT_REPORTED",
                        "refund": {"status": "REVIEW_REQUIRED"},
                        "fault_review": {"status": "PENDING", "version": 1},
                    }
                if path.endswith("/start"):
                    return 200, {"status": "ACTIVE"}
                if path.endswith("/checkpoint"):
                    return 202, {"tick": 60}
                if path.endswith("/fault"):
                    return 202, {
                        "refund": {"status": "REVIEW_REQUIRED"},
                        "fault_review": {"status": "PENDING", "version": 1},
                    }
                raise AssertionError((method, path))

        cohort = {
            "campaign_id": "phase1-test",
            "participants": [
                {"cookie": "dj_session=" + "a" * 39 + "1"},
                {"cookie": "dj_session=" + "a" * 39 + "2"},
            ],
        }
        with tempfile.TemporaryDirectory() as directory, load.BudgetLedger(
            Path(directory) / "ledger.json"
        ) as ledger:
            load.security_probe(StubClient(), cohort, ledger, "fingerprint")
        paths = [path for _method, path, *_rest in calls]
        self.assertIn("/api/game-sessions/gs_probe_1/checkpoint", paths)
        self.assertIn("/api/game-sessions/gs_probe_1/fault", paths)
        self.assertIn("/api/game-sessions/gs_probe_2/checkpoint", paths)
        self.assertIn("/api/game-sessions/gs_probe_2/fault", paths)
        checkpoints = [body for _method, path, _cookie, body, *_rest in calls if path.endswith("/checkpoint")]
        faults = [body for _method, path, _cookie, body, *_rest in calls if path.endswith("/fault")]
        self.assertTrue(all(body["tick"] == 60 for body in checkpoints))
        self.assertTrue(all(body["reason"] == "NETWORK_ERROR" and body["last_tick"] == 60 for body in faults))

    def test_dry_run_is_bounded_and_has_write_tracking_cost_envelopes(self):
        report = load.dry_run("full")
        self.assertEqual(report["planned_stage_seconds"], 690)
        self.assertEqual(report["reserved_duration_seconds"], 780)
        self.assertEqual(report["flow_attempts_ceiling"], 2_170)
        self.assertEqual(report["cohort_participants_required_ceiling"], 2_172)
        self.assertEqual(report["script_api_calls_ceiling"], 21_935)
        self.assertEqual(report["absolute_api_calls_ceiling"], 26_275)
        self.assertEqual(report["http_mutation_requests_ceiling"], 15_417)
        self.assertEqual(report["client_tracking_events_ceiling"], 2_170)
        self.assertEqual(report["server_domain_event_attempts_ceiling"], 13_135)
        self.assertEqual(report["database_write_statement_envelope"], 53_004)
        self.assertTrue(report["within_hard_api_call_cap"])
        self.assertTrue(report["within_prepared_cohort"])
        self.assertFalse(report["real_prizes"])

    def test_http_client_uses_cookie_idempotency_and_protection_headers(self):
        with tempfile.TemporaryDirectory() as directory, load.BudgetLedger(
            Path(directory) / "ledger.json"
        ) as ledger:
            metrics = load.Metrics()
            client = load.HttpClient(
                "http://127.0.0.1:8080",
                ledger,
                metrics,
                1,
                load.threading.Event(),
                time.monotonic() + 5,
                "private-protection-token",
                "_vercel_sso_nonce=" + "v" * 32,
            )
            captured = {}

            def respond(request, **_kwargs):
                captured.update({key.lower(): value for key, value in request.header_items()})
                return FakeResponse(request.full_url, 201, {"created": True})

            with mock.patch.object(load.urllib.request, "urlopen", side_effect=respond):
                status, _ = client.request(
                    "POST",
                    "/api/example",
                    "test",
                    "dj_session=" + "a" * 40,
                    {"event_id": "evt_example"},
                    "idem-example-123",
                    (201,),
                )
            self.assertEqual(status, 201)
            self.assertEqual(
                captured["cookie"],
                "dj_session=" + "a" * 40 + "; _vercel_sso_nonce=" + "v" * 32,
            )
            self.assertEqual(captured["idempotency-key"], "idem-example-123")
            self.assertEqual(captured["x-vercel-protection-bypass"], "private-protection-token")
            self.assertEqual(ledger.data["admitted_api_calls"], 1)
            self.assertEqual(ledger.data["completed_api_calls"], 1)

    def test_network_failure_writes_sanitized_private_report(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            cohort_path = root / "cohort.json"
            ledger_path = root / "ledger.json"
            report_path = root / "report.json"
            raw_cookie = "dj_session=" + "z" * 40
            data = cohort_data(12)
            data["participants"][0]["cookie"] = raw_cookie
            cohort_path.write_text(json.dumps(data), encoding="utf-8")
            cohort_path.chmod(0o600)
            result = load.main(
                [
                    "--mode",
                    "local",
                    "--base-url",
                    "http://127.0.0.1:9",
                    "--cohort",
                    str(cohort_path),
                    "--ledger",
                    str(ledger_path),
                    "--report",
                    str(report_path),
                    "--timeout",
                    "0.1",
                ]
            )
            self.assertEqual(result, 2)
            report_text = report_path.read_text(encoding="utf-8")
            report = json.loads(report_text)
            self.assertTrue(report["serious_stop"])
            self.assertEqual(report["failure"]["reason"], "Network preflight or request failed")
            self.assertNotIn(raw_cookie, report_text)
            self.assertEqual(stat.S_IMODE(report_path.stat().st_mode), 0o600)

    def test_endpoint_metrics_never_include_opaque_ids(self):
        self.assertEqual(
            load.endpoint_label("POST", "/api/game-sessions/secret-session/finish"),
            "POST /api/game-sessions/{id}/finish",
        )
        self.assertEqual(
            load.endpoint_label("POST", "/api/claims/private-claim/submit"),
            "POST /api/claims/{id}/submit",
        )


if __name__ == "__main__":
    unittest.main()
