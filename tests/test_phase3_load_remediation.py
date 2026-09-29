import io
import json
import os
from contextlib import redirect_stdout
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

import phase3_load_remediation as remediation


def private_json(path: Path, value):
    path.write_text(json.dumps(value, separators=(",", ":")), encoding="utf-8")
    os.chmod(path, 0o600)


def cohort(base_url, deployment_id):
    return {
        "schema_version": 1,
        "environment": "preview",
        "project_ref": remediation.original.base.EXPECTED_PROJECT_REF,
        "base_url": base_url,
        "deployment_id": deployment_id,
        "campaign_id": "gemini_dino_phase1_test",
        "preparation_api_calls": 2,
        "participants": [
            {
                "participant_id": f"p_{number:04d}",
                "cookie": "dj_session=" + f"token_{number:04d}_".ljust(40, "x"),
                "referral_code": f"REF{number:09d}",
            }
            for number in range(5000)
        ],
    }


class Phase3RemediationTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.old_url = "https://old-final-preview.vercel.app"
        self.new_url = "https://new-final-preview.vercel.app"
        self.old_deployment = "dpl_old_final"
        self.new_deployment = "dpl_new_final"
        self.old_cohort = self.directory / "old-cohort.json"
        self.new_cohort = self.directory / "new-cohort.json"
        private_json(self.old_cohort, cohort(self.old_url, self.old_deployment))
        private_json(self.new_cohort, cohort(self.new_url, self.new_deployment))
        old_loaded = remediation.original.base.load_cohort(
            self.old_cohort, "remote", self.old_url,
            remediation.original.base.EXPECTED_PROJECT_REF, self.old_deployment,
        )
        self.old_fingerprint = remediation.original.base.cohort_fingerprint(old_loaded)
        self.prior_report = self.directory / "prior-report.json"
        private_json(self.prior_report, {
            "phase": 3,
            "plan_revision": remediation.PRIOR_PLAN_REVISION,
            "base_url": self.old_url,
            "deployment_id": self.old_deployment,
            "cohort_fingerprint": self.old_fingerprint,
            "actual_duration_seconds": 11.52,
            "stages": [],
            "failure": {"type": "SeriousFailure", "reason": "Server 5xx safety stop"},
            "metrics": {"api_calls": 460},
            "budget": {
                "admitted_api_calls": 462,
                "completed_api_calls": 462,
                "duration_reserved_seconds": 390,
            },
        })
        self.prior_ledger = self.directory / "prior-ledger.json"
        private_json(self.prior_ledger, {
            "version": 2,
            "phase": 3,
            "plan_revision": remediation.PRIOR_PLAN_REVISION,
            "admitted_api_calls": 462,
            "completed_api_calls": 462,
            "duration_reserved_seconds": 390,
            "runs": [{
                "profile": "full",
                "deployment_id": self.old_deployment,
                "cohort_fingerprint": self.old_fingerprint,
            }],
            "cohorts": {self.old_fingerprint: {
                "next_index": 100,
                "total": 5000,
                "campaign_id": "gemini_dino_phase1_test",
            }},
            "external_cohort_calls": {self.old_fingerprint: 2},
        })

    def tearDown(self):
        self.temporary.cleanup()

    def binding(self):
        evidence = remediation.load_prior_evidence(self.prior_report, self.prior_ledger)
        current, binding = remediation.bind_cohorts(
            self.old_cohort, self.new_cohort, evidence, self.new_url,
            self.new_deployment, remediation.original.base.EXPECTED_PROJECT_REF,
        )
        return current, binding

    def test_default_plan_is_network_free_and_within_cumulative_limits(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(remediation.main([]), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["network_calls"], 0)
        self.assertEqual(plan["flow_attempts_ceiling"], 500)
        self.assertEqual(plan["new_runner_api_calls_ceiling"], 5502)
        self.assertEqual(plan["cumulative_api_calls_ceiling"], 5964)
        self.assertEqual(plan["cumulative_seconds_ceiling"], 372)
        self.assertEqual(plan["remaining_api_calls"], 1036)
        self.assertEqual(plan["remaining_seconds"], 18)

    def test_evidence_binding_carries_cursor_and_one_run_budget(self):
        current, binding = self.binding()
        ledger_path = self.directory / "remediation-ledger.json"
        fingerprint = binding["new_cohort_fingerprint"]
        with remediation.RemediationLedger(ledger_path, binding, len(current["participants"])) as ledger:
            self.assertEqual(ledger.data["admitted_api_calls"], 462)
            self.assertEqual(ledger.data["duration_reserved_seconds"], 12)
            self.assertEqual(ledger.claim_participant(fingerprint, 5000, current["campaign_id"]), 100)
            ledger.reserve_run(360, "remediation", fingerprint, self.new_deployment)
            self.assertEqual(ledger.data["duration_reserved_seconds"], 372)
            with self.assertRaises(remediation.BudgetExceeded):
                ledger.reserve_run(360, "remediation", fingerprint, self.new_deployment)

    def test_changed_prior_evidence_is_rejected(self):
        report = json.loads(self.prior_report.read_text())
        report["actual_duration_seconds"] = 11.53
        private_json(self.prior_report, report)
        with self.assertRaisesRegex(remediation.SafetyError, "reviewed remediation baseline"):
            remediation.load_prior_evidence(self.prior_report, self.prior_ledger)

    def test_old_or_unbound_marker_cannot_authorize_remediation(self):
        _current, binding = self.binding()
        marker_path = self.directory / "marker.json"
        old_marker = {
            "phase": 3,
            "plan_revision": remediation.PRIOR_PLAN_REVISION,
            "approved_remote": True,
            "run_id": "old_run_20260929",
        }
        private_json(marker_path, old_marker)
        with self.assertRaisesRegex(remediation.SafetyError, "does not match"):
            remediation.load_approval_marker(marker_path, binding)

        exact = {
            "phase": 3,
            "plan_revision": remediation.PLAN_REVISION,
            "approved_remote": True,
            "game_version": remediation.GAME_VERSION,
            "max_cumulative_api_calls": 7000,
            "max_cumulative_seconds": 390,
            "prior_api_calls": 462,
            "prior_charged_seconds": 12,
            "prior_cursor": 100,
            "stages": ["100-remediation", "200-remediation-burst"],
            **binding,
            "run_id": "remediation_run_20260929",
        }
        private_json(marker_path, exact)
        self.assertEqual(remediation.load_approval_marker(marker_path, binding), exact)
        exact["report_sha256"] = "0" * 64
        private_json(marker_path, exact)
        with self.assertRaisesRegex(remediation.SafetyError, "does not match"):
            remediation.load_approval_marker(marker_path, binding)


if __name__ == "__main__":
    unittest.main()
