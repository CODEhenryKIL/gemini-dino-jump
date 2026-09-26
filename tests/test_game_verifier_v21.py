import json
import subprocess
import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import game_verifier
import game_verifier_v2
import operations


class GameVerifierV21Test(unittest.TestCase):
    def _browser_fixture(self, version):
        return json.loads(subprocess.check_output([
            "node", str(ROOT / "tests/js_v2_fixture_runner.cjs"),
            json.dumps({"mode": "bot", "seed": 4, "target_revives": 2, "version": version}),
        ], text=True, cwd=ROOT))

    def test_stage_speed_and_gap_are_driven_by_frozen_version_constants(self):
        v2 = game_verifier.V2_CONSTANTS
        v21 = game_verifier.V21_CONSTANTS
        self.assertEqual(game_verifier_v2._speed_at(v2, 120), 880)
        self.assertEqual(game_verifier_v2._min_gap_at(v2, 120), 0.62)
        self.assertEqual(game_verifier_v2._speed_at(v21, 105), 940)
        self.assertEqual(game_verifier_v2._min_gap_at(v21, 105), 0.50)
        self.assertEqual(game_verifier_v2._speed_at(v21, 135), 1200)
        self.assertEqual(game_verifier_v2._speed_at(v21, 150), 1320)
        self.assertEqual(game_verifier_v2._speed_at(v21, 300), 1320)
        self.assertEqual(game_verifier_v2._min_gap_at(v21, 150), 0.40)
        self.assertEqual(len(game_verifier.LEGACY_CONSTANTS["stages"]), 6)
        self.assertIn("stage_10", operations.ENUM_DIMENSIONS["stage"])

    def test_score_sources_keep_v2_and_v21_leaderboards_separate(self):
        self.assertIn("game_version='2.0.0'", operations._score_source("2.0.0"))
        self.assertIn("game_version='2.1.0'", operations._score_source("2.1.0"))

    def test_v21_browser_replay_matches_server_and_applies_linear_revive_penalty(self):
        play = self._browser_fixture("2.1.0")
        result = game_verifier.verify_game(
            "2.1.0", 4, play["jump_ticks"], play["score"], play["ticks"],
        )
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["summary"], play["summary"])
        self.assertGreaterEqual(result["summary"]["revives"], 2)
        self.assertEqual(
            result["summary"]["revive_penalty"],
            result["summary"]["revives"] * 100,
        )

    def test_frozen_v2_browser_replay_keeps_old_score_and_summary_contract(self):
        play = self._browser_fixture("2.0.0")
        result = game_verifier.verify_game(
            "2.0.0", 4, play["jump_ticks"], play["score"], play["ticks"],
        )
        self.assertTrue(result["valid"], result)
        self.assertEqual(result["summary"], play["summary"])
        self.assertNotIn("revive_penalty", result["summary"])

    def test_version_dispatch_rejects_unknown_version(self):
        with self.assertRaisesRegex(ValueError, "UNSUPPORTED_GAME_VERSION"):
            game_verifier.verify_game("2.2.0", 1, [], 0, 0)


if __name__ == "__main__":
    unittest.main()
