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
sys.path.insert(0, str(ROOT / "tests"))

import phase3_load_harness_correction as correction
from test_phase3_load_remediation import cohort, private_json


class HarnessCorrectionTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory()
        self.directory = Path(self.temporary.name)
        self.first_url = "https://first-preview.vercel.app"
        self.fixed_url = "https://fixed-preview.vercel.app"
        self.first_deployment = "dpl_first"
        self.fixed_deployment = "dpl_fixed"
        self.first_cohort = self.directory / "first-cohort.json"
        self.remediation_cohort = self.directory / "remediation-cohort.json"
        private_json(self.first_cohort, cohort(self.first_url, self.first_deployment))
        private_json(self.remediation_cohort, cohort(self.fixed_url, self.fixed_deployment))
        first_loaded = correction.original.base.load_cohort(
            self.first_cohort, "remote", self.first_url,
            correction.original.base.EXPECTED_PROJECT_REF, self.first_deployment,
        )
        first_fingerprint = correction.original.base.cohort_fingerprint(first_loaded)
        self.first_report = self.directory / "first-report.json"
        private_json(self.first_report, {
            "phase": 3,
            "plan_revision": correction.original.PLAN_REVISION,
            "base_url": self.first_url,
            "deployment_id": self.first_deployment,
            "cohort_fingerprint": first_fingerprint,
            "actual_duration_seconds": 11.52,
            "stages": [],
            "failure": {"type": "SeriousFailure", "reason": "Server 5xx safety stop"},
            "metrics": {"api_calls": 460},
            "budget": {
                "admitted_api_calls": 462, "completed_api_calls": 462,
                "duration_reserved_seconds": 390,
            },
        })
        self.first_ledger = self.directory / "first-ledger.json"
        private_json(self.first_ledger, {
            "version": 2, "phase": 3, "plan_revision": correction.original.PLAN_REVISION,
            "admitted_api_calls": 462, "completed_api_calls": 462,
            "duration_reserved_seconds": 390,
            "runs": [{
                "deployment_id": self.first_deployment,
                "cohort_fingerprint": first_fingerprint,
            }],
            "cohorts": {first_fingerprint: {
                "next_index": 100, "total": 5000,
                "campaign_id": "gemini_dino_phase1_test",
            }},
            "external_cohort_calls": {first_fingerprint: 2},
        })
        first_evidence = correction.remediation.load_prior_evidence(
            self.first_report, self.first_ledger,
        )
        _current, first_binding = correction.remediation.bind_cohorts(
            self.first_cohort, self.remediation_cohort, first_evidence,
            self.fixed_url, self.fixed_deployment,
            correction.original.base.EXPECTED_PROJECT_REF,
        )
        self.fixed_fingerprint = first_binding["new_cohort_fingerprint"]
        self.remediation_report = self.directory / "remediation-report.json"
        private_json(self.remediation_report, {
            "phase": 3,
            "plan_revision": correction.remediation.PLAN_REVISION,
            "deployment_id": self.fixed_deployment,
            "cohort_fingerprint": self.fixed_fingerprint,
            "actual_duration_seconds": 6.31,
            "failure": {
                "type": "SeriousFailure",
                "reason": "Final-load tracking batch was not accepted exactly",
            },
            "metrics": {"api_calls": 356, "flows_completed": 0},
            "budget": {
                "admitted_api_calls": 818, "completed_api_calls": 818,
                "duration_reserved_seconds": 372,
            },
            "prior_evidence": first_binding,
        })
        self.remediation_ledger = self.directory / "remediation-ledger.json"
        private_json(self.remediation_ledger, {
            "version": 2, "phase": 3,
            "plan_revision": correction.remediation.PLAN_REVISION,
            "admitted_api_calls": 818, "completed_api_calls": 818,
            "duration_reserved_seconds": 372,
            "runs": [{
                "deployment_id": self.fixed_deployment,
                "cohort_fingerprint": self.fixed_fingerprint,
            }],
            "cohorts": {self.fixed_fingerprint: {
                "next_index": 200, "total": 5000,
                "campaign_id": "gemini_dino_phase1_test",
            }},
            "external_cohort_calls": {self.fixed_fingerprint: 2},
            "prior_evidence": first_binding,
        })

    def tearDown(self):
        self.temporary.cleanup()

    def chain(self):
        return correction.load_evidence_chain(
            self.first_report, self.first_ledger, self.first_cohort,
            self.remediation_report, self.remediation_ledger, self.remediation_cohort,
            correction.original.base.EXPECTED_PROJECT_REF,
        )

    def test_dry_run_preserves_global_caps(self):
        output = io.StringIO()
        with redirect_stdout(output):
            self.assertEqual(correction.main([]), 0)
        plan = json.loads(output.getvalue())
        self.assertEqual(plan["network_calls"], 0)
        self.assertEqual(plan["cumulative_api_calls_ceiling"], 6320)
        self.assertEqual(plan["cumulative_seconds_ceiling"], 379)
        self.assertEqual(plan["remaining_api_calls"], 680)
        self.assertEqual(plan["remaining_seconds"], 11)

    def test_two_run_chain_starts_at_200_and_allows_only_one_run(self):
        current, binding = self.chain()
        path = self.directory / "correction-ledger.json"
        with correction.CorrectionLedger(path, binding, len(current["participants"])) as ledger:
            self.assertEqual(ledger.claim_participant(binding["cohort_fingerprint"], 5000, binding["campaign_id"]), 200)
            ledger.reserve_run(360, "harness-correction", binding["cohort_fingerprint"], self.fixed_deployment)
            self.assertEqual(ledger.data["duration_reserved_seconds"], 379)
            with self.assertRaises(correction.BudgetExceeded):
                ledger.reserve_run(360, "harness-correction", binding["cohort_fingerprint"], self.fixed_deployment)

    def test_tampered_second_report_is_rejected(self):
        report = json.loads(self.remediation_report.read_text())
        report["metrics"]["api_calls"] = 355
        private_json(self.remediation_report, report)
        with self.assertRaisesRegex(correction.SafetyError, "Two-run evidence chain"):
            self.chain()


if __name__ == "__main__":
    unittest.main()
