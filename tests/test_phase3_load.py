import io
import json
import os
import sys
import tempfile
import threading
import time
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))
import phase3_load
import operations


def health(environment="preview"):
    return {
        "ok": True,
        "database": "ready",
        "service": "gemini-dino-jump",
        "environment": environment,
        "project_ref": phase3_load.base.EXPECTED_PROJECT_REF,
        "schema": phase3_load.base.EXPECTED_SCHEMA,
        "synthetic_only": False,
        "gameplay_synthetic_only": True,
        "test_seed": True,
        "deployment": "dpl_final",
    }


def config(version="2.1.0"):
    project = phase3_load.base.EXPECTED_PROJECT_REF
    return {
        "synthetic_only": False,
        "gameplay_synthetic_only": True,
        "campaign": {"id": "final-test", "status": "ACTIVE", "game_version": version},
        "auth": {"supabase_url": f"https://{project}.supabase.co"},
    }


class FakeFlowClient:
    def __init__(self, rich=False, pending=None):
        self.rich = rich
        self.pending = pending
        self.calls = []
        self.stop = threading.Event()
        self.metrics = phase3_load.base.Metrics()
        self.stage_metrics = None
        self.deadline = time.monotonic() + 60

    def request(
        self, method, path, phase, cookie=None, body=None, idempotency_key=None,
        expected=(200,), expected_negative=False,
    ):
        self.calls.append({
            "method": method, "path": path, "phase": phase, "cookie": cookie,
            "body": body, "idempotency_key": idempotency_key,
            "expected": expected, "expected_negative": expected_negative,
        })
        if (method, path) == ("GET", "/api/me"):
            return 200, {
                "tickets": {"initial": 1, "invitation": 0, "unlimited_play": False},
                "pending_game_session": self.pending,
            }
        if (method, path) == ("POST", "/api/game-sessions"):
            return 201, {"session_id": "gs_final_1", "seed": 4, "version": "2.1.0"}
        if (method, path) == ("POST", "/api/game-sessions/gs_final_1/start"):
            return 200, {"status": "ACTIVE"}
        if (method, path) == ("POST", "/api/game-sessions/gs_final_1/finish"):
            fixture = phase3_load.rich_fixture(4) if self.rich else phase3_load.normal_fixture(4)
            if self.rich:
                refund = {"status": "NOT_DUE", "reason": None}
                consumed = True
            else:
                refund = {"status": "REFUNDED", "reason": "LOW_SCORE"}
                consumed = False
            return 200, {
                "status": "FINISHED", "verification": "VERIFIED",
                "game_version": "2.1.0", "summary": fixture.get("summary", {}),
                "refund": refund, "ticket_consumed": consumed,
            }
        if (method, path) == ("GET", "/api/draws/me"):
            return 200, {"status": "AVAILABLE"}
        if (method, path) == ("POST", "/api/draws"):
            return 201, {
                "draw_id": "draw_final_1", "is_actual_prize": False,
                "claim_id": None, "round_number": 1,
            }
        if (method, path) == ("PATCH", "/api/draws/draw_final_1/scratch-complete"):
            return 200, {"scratch_completed": True, "claim_id": None}
        if method == "GET" and path.startswith("/api/leaderboard"):
            return 200, {"entries": []}
        if (method, path) == ("GET", "/api/referrals/me"):
            return 200, {"invitation_balance": 0}
        if (method, path) == ("GET", "/api/claims"):
            return 200, {"claims": []}
        if (method, path) == ("POST", "/api/events/batch"):
            return 202, {"accepted": 2, "rejected": 0}
        raise AssertionError(f"unexpected request: {method} {path}")


class Phase3LoadSafetyTests(unittest.TestCase):
    def test_default_is_network_free_paused_dry_run(self):
        output = io.StringIO()
        with redirect_stdout(output), mock.patch(
            "urllib.request.urlopen", side_effect=AssertionError("network attempted")
        ), mock.patch("subprocess.run", side_effect=AssertionError("fixture attempted")):
            self.assertEqual(phase3_load.main([]), 0)
        report = json.loads(output.getvalue())
        self.assertEqual((report["phase"], report["game_version"]), (3, "2.1.0"))
        self.assertEqual(report["network_calls"], 0)
        self.assertFalse(report["remote_approval_present"])
        self.assertEqual(report["kakao_callback_calls"], 0)
        self.assertEqual(report["claim_mutation_calls"], 0)

    def test_final_envelope_is_exactly_bounded_and_counts_external_allowance(self):
        estimate = phase3_load.estimate_profile()
        self.assertEqual(
            [(s["virtual_users"], s["seconds"], s["drain_seconds"], s["burst"])
             for s in estimate["stages"]],
            [(100, 180, 90, False), (200, 30, 90, True)],
        )
        self.assertEqual(estimate["flow_attempts_ceiling"], 600)
        self.assertEqual(estimate["runner_api_calls_ceiling"], 6602)
        self.assertEqual(estimate["cohort_preparation_and_check_call_allowance"], 398)
        self.assertEqual(estimate["absolute_api_calls_ceiling"], 7000)
        self.assertEqual(estimate["automatic_retry_calls"], 0)
        self.assertEqual(phase3_load.reserved_duration(), 390)
        self.assertEqual(phase3_load.MAX_DURATION_SECONDS, 390)

    def test_phase1_and_phase2_ledgers_cannot_be_reused(self):
        for phase in (None, 2):
            with self.subTest(phase=phase), tempfile.TemporaryDirectory() as temporary:
                path = Path(temporary) / "old-ledger.json"
                data = {
                    "version": 2,
                    "admitted_api_calls": 0,
                    "completed_api_calls": 0,
                    "duration_reserved_seconds": 0,
                    "runs": [],
                    "cohorts": {},
                    "external_cohort_calls": {},
                }
                if phase is not None:
                    data["phase"] = phase
                path.write_text(json.dumps(data), encoding="utf-8")
                os.chmod(path, 0o600)
                before = path.read_bytes()
                with self.assertRaisesRegex(phase3_load.SafetyError, "non-Phase-3"):
                    phase3_load.Phase3BudgetLedger(path)
                self.assertEqual(path.read_bytes(), before)

    def test_phase3_ledger_includes_preparation_failed_calls_and_is_one_run_only(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "phase3-ledger.json"
            with phase3_load.Phase3BudgetLedger(path) as ledger:
                ledger.register_cohort_preparation("cohort", 398)
                self.assertEqual(ledger.remaining_calls, 6602)
                ledger.admit_call()
                self.assertEqual(ledger.remaining_calls, 6601)
                ledger.reserve_run(390, "full", "cohort", "dpl_final")
                with self.assertRaises(phase3_load.BudgetExceeded):
                    ledger.reserve_run(390, "full", "cohort", "dpl_final")
            saved = json.loads(path.read_text(encoding="utf-8"))
            self.assertEqual(saved["admitted_api_calls"], 399)
            self.assertEqual(saved["completed_api_calls"], 398)
            self.assertEqual(saved["plan_revision"], phase3_load.PLAN_REVISION)

    def test_approval_marker_is_exact_and_old_phase_cannot_authorize(self):
        with tempfile.TemporaryDirectory() as temporary:
            path = Path(temporary) / "approval.json"
            marker = {
                "phase": 3,
                "plan_revision": phase3_load.PLAN_REVISION,
                "approved_remote": True,
                "base_url": "https://final-preview.vercel.app",
                "deployment_id": "dpl_final",
                "campaign_id": "final-test",
                "cohort_fingerprint": "f" * 64,
                "game_version": "2.1.0",
                "max_api_calls": 7000,
                "max_duration_seconds": 390,
                "stages": ["100-stage", "200-burst"],
                "run_id": "final_run_20260929",
            }
            path.write_text(json.dumps(marker), encoding="utf-8")
            os.chmod(path, 0o600)
            loaded = phase3_load.load_approval_marker(
                path, marker["base_url"], marker["deployment_id"],
                marker["campaign_id"], marker["cohort_fingerprint"],
            )
            self.assertEqual(loaded["phase"], 3)
            for mutation in (
                lambda value: value.update(phase=2),
                lambda value: value.update(max_api_calls=10_000),
                lambda value: value.update(extra="forbidden"),
            ):
                changed = dict(marker)
                mutation(changed)
                path.write_text(json.dumps(changed), encoding="utf-8")
                os.chmod(path, 0o600)
                with self.assertRaisesRegex(phase3_load.SafetyError, "does not match"):
                    phase3_load.load_approval_marker(
                        path, marker["base_url"], marker["deployment_id"],
                        marker["campaign_id"], marker["cohort_fingerprint"],
                    )

    def test_remote_execute_without_new_marker_stops_before_network(self):
        with mock.patch("urllib.request.urlopen", side_effect=AssertionError("network attempted")):
            with self.assertRaisesRegex(phase3_load.SafetyError, "new approval marker"):
                phase3_load.main([
                    "--execute", "--mode", "remote",
                    "--base-url", "https://final-preview.vercel.app",
                    "--cohort", "/tmp/never-read-cohort.json",
                    "--ledger", "/tmp/never-created-ledger.json",
                    "--report", "/tmp/never-created-report.json",
                    "--expected-deployment-id", "dpl_final",
                ])

    def test_preflight_requires_current_version_and_preview_guard(self):
        phase3_load.validate_phase3_preflight(
            "remote", health(), config(), phase3_load.base.EXPECTED_PROJECT_REF,
            "dpl_final", "final-test",
        )
        with self.assertRaisesRegex(phase3_load.SafetyError, "2.1.0"):
            phase3_load.validate_phase3_preflight(
                "remote", health(), config("2.0.0"), phase3_load.base.EXPECTED_PROJECT_REF,
                "dpl_final", "final-test",
            )
        with self.assertRaisesRegex(phase3_load.SafetyError, "Production"):
            phase3_load.validate_phase3_preflight(
                "remote", health("production"), config(), phase3_load.base.EXPECTED_PROJECT_REF,
                "dpl_final", "final-test",
            )
        invalid = health()
        invalid["gameplay_synthetic_only"] = False
        with self.assertRaisesRegex(phase3_load.SafetyError, "gameplay_synthetic_only"):
            phase3_load.validate_phase3_preflight(
                "remote", invalid, config(), phase3_load.base.EXPECTED_PROJECT_REF,
                "dpl_final", "final-test",
            )
        invalid_config = config()
        invalid_config["gameplay_synthetic_only"] = False
        with self.assertRaisesRegex(phase3_load.SafetyError, "synthetic Preview gameplay"):
            phase3_load.validate_phase3_preflight(
                "remote", health(), invalid_config, phase3_load.base.EXPECTED_PROJECT_REF,
                "dpl_final", "final-test",
            )

    def test_v21_low_score_flow_refunds_and_never_fakes_share_or_claim_completion(self):
        client = FakeFlowClient(rich=False)
        fixture = phase3_load.normal_fixture(4)
        self.assertLessEqual(fixture["score"], 100)
        with mock.patch.object(phase3_load, "game_fixture", return_value=(fixture, False)), mock.patch.object(
            phase3_load.base, "wait_for_play", return_value=None,
        ):
            phase3_load.phase3_user_flow(client, {"cookie": "dj_session=" + "a" * 40}, 1)
        paths = [(call["method"], call["path"]) for call in client.calls]
        self.assertEqual(len(paths), phase3_load.BASE_FLOW_CALLS)
        self.assertNotIn(("POST", "/api/webhooks/kakao-share"), paths)
        self.assertFalse(any("share-intents" in path for _, path in paths))
        self.assertFalse(any(path.endswith("/submit") or path.endswith("/draft") for _, path in paths))
        draw_call = next(call for call in client.calls if call["path"] == "/api/draws")
        self.assertEqual(draw_call["body"]["expected_round_number"], 1)
        tracking = next(call for call in client.calls if call["path"] == "/api/events/batch")
        self.assertEqual([event["name"] for event in tracking["body"]["events"]], [
            "page_view", "draw_result_viewed",
        ])
        self.assertEqual(tracking["body"]["events"][0]["dimensions"], {
            "source": "home", "channel": "phase3_load", "game_version": "2.1.0",
        })
        self.assertEqual(tracking["body"]["events"][1]["dimensions"], {
            "source": "result", "channel": "phase3_load", "result_type": "benefit",
        })

        event_conn = mock.Mock()
        event_conn.execute.return_value.rowcount = 1
        event_context = {
            "campaign_id": "final-test", "environment": "preview",
            "deployment": "dpl_final", "event_version": "phase3-load-v1",
            "participant_token_hash": "a" * 64,
        }
        with mock.patch.object(operations, "_participant", return_value={"id": "p-final"}), mock.patch.object(
            operations, "_one", return_value={"participant_id": "p-final"},
        ):
            status, accepted = operations.events_batch(event_conn, tracking["body"], event_context)
        self.assertEqual((status, accepted), (202, {
            "accepted": 2, "duplicates": 0, "rejected": 0,
        }))

    def test_v21_rich_flow_checks_consumption_and_penalized_summary(self):
        client = FakeFlowClient(rich=True)
        fixture = phase3_load.rich_fixture(4)
        self.assertGreater(fixture["score"], 100)
        self.assertEqual(fixture["summary"]["revive_penalty"], fixture["summary"]["revives"] * 100)
        with mock.patch.object(phase3_load, "game_fixture", return_value=(fixture, True)), mock.patch.object(
            phase3_load.base, "wait_for_play", return_value=None,
        ):
            phase3_load.phase3_user_flow(client, {"cookie": "dj_session=" + "b" * 40}, 100)
        self.assertEqual(len(client.calls), phase3_load.BASE_FLOW_CALLS)

    def test_unfinished_prepared_session_is_rejected_before_new_session(self):
        client = FakeFlowClient(pending={"session_id": "already-active", "status": "ACTIVE"})
        with self.assertRaisesRegex(phase3_load.SeriousFailure, "unfinished"):
            phase3_load.phase3_user_flow(client, {"cookie": "dj_session=" + "c" * 40}, 1)
        self.assertEqual([(c["method"], c["path"]) for c in client.calls], [("GET", "/api/me")])

    def test_unlimited_play_is_rejected_before_any_game_mutation(self):
        client = FakeFlowClient()
        original = client.request

        def unlimited(method, path, *args, **kwargs):
            status, data = original(method, path, *args, **kwargs)
            if (method, path) == ("GET", "/api/me"):
                data["tickets"]["unlimited_play"] = True
            return status, data

        client.request = unlimited
        with self.assertRaisesRegex(phase3_load.SeriousFailure, "unlimited play"):
            phase3_load.phase3_user_flow(client, {"cookie": "dj_session=" + "d" * 40}, 1)
        self.assertEqual([(c["method"], c["path"]) for c in client.calls], [("GET", "/api/me")])

    def test_first_stage_failure_sets_global_stop_and_prevents_more_admissions(self):
        class Ledger:
            def __init__(self):
                self.claims = 0

            def claim_participant(self, *_args):
                self.claims += 1
                return 0

        class Client:
            def __init__(self):
                self.stop = threading.Event()
                self.metrics = phase3_load.base.Metrics()
                self.stage_metrics = None

        ledger = Ledger()
        client = Client()
        cohort = {"participants": [{"cookie": "cookie"}], "campaign_id": "final-test"}
        with mock.patch.object(
            phase3_load, "phase3_user_flow", side_effect=phase3_load.UnexpectedResponse("fail")
        ):
            with self.assertRaises(phase3_load.UnexpectedResponse):
                phase3_load.run_stage(
                    client, cohort, ledger, "fingerprint", 1, 2, False, "100-stage",
                    [0], threading.Lock(), 10,
                )
        self.assertTrue(client.stop.is_set())
        self.assertEqual(ledger.claims, 1)

    def test_200_vu_burst_admits_one_complete_flow_per_worker(self):
        class Ledger:
            def __init__(self):
                self.next = 0
                self.lock = threading.Lock()

            def claim_participant(self, *_args):
                with self.lock:
                    value = self.next
                    self.next += 1
                    return value

        class Client:
            def __init__(self):
                self.stop = threading.Event()
                self.metrics = phase3_load.base.Metrics()
                self.stage_metrics = None

        participants = [{"cookie": f"cookie-{index}"} for index in range(200)]
        cohort = {"participants": participants, "campaign_id": "final-test"}
        completed = []
        completed_lock = threading.Lock()

        def complete(_client, participant, _sequence):
            with completed_lock:
                completed.append(participant["cookie"])

        with mock.patch.object(phase3_load, "phase3_user_flow", side_effect=complete):
            report = phase3_load.run_stage(
                Client(), cohort, Ledger(), "fingerprint", 200, 30, True, "200-burst",
                [400], threading.Lock(), 45,
            )
        self.assertEqual(len(completed), 200)
        self.assertEqual(len(set(completed)), 200)
        self.assertTrue(report["burst"])


if __name__ == "__main__":
    unittest.main()
