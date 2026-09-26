import json
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import game_verifier
import game_verifier_v2


class GameVerifierV2Test(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        output = subprocess.check_output([
            "node", str(ROOT / "tests/js_v2_fixture_runner.cjs"),
            json.dumps({"mode": "bot", "seed": 4, "target_revives": 2}),
        ], cwd=ROOT, text=True)
        cls.fixture = json.loads(output)

    def test_javascript_and_python_match_with_two_revives(self):
        result = game_verifier.verify_game(
            "2.0.0", 4, self.fixture["jump_ticks"], self.fixture["score"], self.fixture["ticks"]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["score"], self.fixture["score"])
        self.assertEqual(result["ticks"], self.fixture["ticks"])
        self.assertEqual(result["summary"], self.fixture["summary"])
        self.assertEqual(result["summary"]["revives"], 2)
        self.assertEqual(result["end_reason"], "COLLISION")

    def test_javascript_and_python_match_after_clearance_for_multiple_seeds(self):
        for seed in (1, 7, 42):
            with self.subTest(seed=seed):
                output = subprocess.check_output([
                    "node", str(ROOT / "tests/js_v2_fixture_runner.cjs"),
                    json.dumps({"mode": "bot", "seed": seed, "target_revives": 0}),
                ], cwd=ROOT, text=True)
                fixture = json.loads(output)
                result = game_verifier.verify_game(
                    "2.0.0", seed, fixture["jump_ticks"], fixture["score"], fixture["ticks"]
                )
                self.assertTrue(result["valid"], result)
                self.assertEqual(result["summary"], fixture["summary"])
                self.assertEqual(result["end_reason"], fixture["end_reason"])

    def test_v2_dispatch_uses_frozen_constants_even_if_current_constants_change(self):
        current = json.loads((ROOT / "shared/game_constants.json").read_text())
        frozen = json.loads((ROOT / "shared/game_constants_v2.json").read_text())
        self.assertEqual((current["version"], frozen["version"]), ("2.1.0", "2.0.0"))
        self.assertNotEqual(current, frozen)
        replacement = {**current, "rules": {**current["rules"], "coinScore": 999}}
        with mock.patch.object(game_verifier, "CONSTANTS", replacement):
            result = game_verifier.verify_game(
                "2.0.0", 4, self.fixture["jump_ticks"], self.fixture["score"], self.fixture["ticks"]
            )
        self.assertTrue(result["valid"], result)

    def test_submitted_score_and_ticks_cannot_claim_items_or_revives(self):
        score_tamper = game_verifier.verify_game(
            "2.0.0", 4, self.fixture["jump_ticks"], self.fixture["score"] + 10, self.fixture["ticks"]
        )
        tick_tamper = game_verifier.verify_game(
            "2.0.0", 4, self.fixture["jump_ticks"], self.fixture["score"], self.fixture["ticks"] - 1
        )
        self.assertFalse(score_tamper["valid"])
        self.assertTrue(score_tamper["reason"].startswith("SCORE_MISMATCH"))
        self.assertEqual(score_tamper["summary"], self.fixture["summary"])
        self.assertFalse(tick_tamper["valid"])
        self.assertTrue(tick_tamper["reason"].startswith("TICK_MISMATCH"))

    def test_client_item_and_revive_flags_have_no_authority(self):
        forged = [dict(jump, heart=True, coin=True, revived=True) for jump in self.fixture["jump_ticks"]]
        result = game_verifier.verify_game(
            "2.0.0", 4, forged, self.fixture["score"], self.fixture["ticks"]
        )
        self.assertTrue(result["valid"])
        self.assertEqual(result["summary"], self.fixture["summary"])

    def test_time_limit_is_legitimate_but_other_unfinished_ticks_are_rejected(self):
        with mock.patch.object(game_verifier_v2, "_overlaps", return_value=False):
            complete = game_verifier.verify_game("2.0.0", 9, [], 6000, 36000)
            unfinished = game_verifier.verify_game("2.0.0", 9, [], 100, 600)
        self.assertEqual((complete["valid"], complete["end_reason"]), (True, "TIME_LIMIT"))
        self.assertFalse(unfinished["valid"])
        self.assertTrue(unfinished["reason"].startswith("TICK_MISMATCH"))

    def test_legacy_dispatch_preserves_v1_no_collision_rejection(self):
        with mock.patch.object(game_verifier, "check_aabb", return_value=False):
            result = game_verifier.verify_game("1.2.0", 1, [], 100, 600)
        self.assertFalse(result["valid"])
        self.assertEqual(result["reason"], "NO_COLLISION")
        self.assertIsNone(result["end_reason"])

    def test_unknown_versions_and_non_integer_fields_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_GAME_VERSION"):
            game_verifier.verify_game("3.0.0", 1, [], 0, 0)
        for value in (True, 1.5, "1", None):
            with self.subTest(value=value), self.assertRaises(ValueError):
                game_verifier.verify_game("2.0.0", 1, [], value, 100)


if __name__ == "__main__":
    unittest.main()
