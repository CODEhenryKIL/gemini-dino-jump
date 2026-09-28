import copy
import importlib.util
import json
from pathlib import Path
import unittest

ROOT = Path(__file__).resolve().parents[1]
SPEC = importlib.util.spec_from_file_location("phase3_preflight", ROOT / "scripts/phase3_preflight.py")
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class Phase3PreflightTest(unittest.TestCase):
    def setUp(self):
        self.manifest = json.loads((ROOT / "config/phase3-launch.json").read_text())

    def test_confirmed_inventory_and_pending_policies_are_distinct(self):
        result = MODULE.validate(self.manifest)
        self.assertEqual(result["errors"], [])
        self.assertIn("campaign.opens_at", result["pending"])
        self.assertEqual(result["totals"]["total_budget_krw"], 1599000)
        self.assertEqual(result["totals"]["initial_actual_prize_probability"], .0154)

    def test_launch_with_missing_decisions_is_rejected(self):
        self.manifest["event_enabled"] = True
        self.assertTrue(MODULE.validate(self.manifest)["errors"])

    def test_ranking_stock_cannot_be_accidentally_added_to_draws(self):
        self.manifest["draw_prizes"][4]["quantity"] += 1
        self.assertTrue(MODULE.validate(self.manifest)["errors"])

    def test_equal_total_cannot_hide_wrong_prize_distribution(self):
        self.manifest["draw_prizes"][8]["quantity"] -= 1
        self.manifest["draw_prizes"][9]["quantity"] += 1
        self.assertTrue(MODULE.validate(self.manifest)["errors"])

    def test_invalid_event_window_and_naive_time_are_rejected(self):
        for start, end in (("2026-10-02T12:00:00+09:00", "2026-10-01T12:00:00+09:00"), ("2026-10-01T12:00:00", "2026-10-02T12:00:00+09:00")):
            with self.subTest(start=start):
                m = copy.deepcopy(self.manifest)
                m["campaign"].update(opens_at=start, closes_at=end)
                self.assertTrue(MODULE.validate(m)["errors"])

    def test_deleted_checks_or_placeholder_cannot_pass_readiness(self):
        self.manifest["policies"] = {}
        self.manifest["approvals"]["public_launch"] = "TBD"
        result = MODULE.validate(self.manifest)
        self.assertIn("policies.ranking_ties", result["pending"])
        self.assertIn("approvals.public_launch", result["pending"])

    def test_test_flags_cannot_be_marked_production_ready(self):
        self.manifest["production_flags"]["unlimited_play"] = True
        self.assertTrue(MODULE.validate(self.manifest)["errors"])


if __name__ == "__main__":
    unittest.main()
