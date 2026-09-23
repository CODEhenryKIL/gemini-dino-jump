import json
from pathlib import Path
import sys
import unittest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / 'server'))
from game_verifier import simulate_and_verify


class PhysicsRegression(unittest.TestCase):
    def test_existing_collision_vectors_preserve_physics(self):
        vectors = json.loads((ROOT / 'tests/fixtures/physics-v1.2.0.json').read_text())
        for vector in vectors:
            with self.subTest(vector=vector):
                self.assertEqual(simulate_and_verify(vector['seed'], vector['jump_ticks'],
                    vector['score'], vector['valid_ticks']),
                    (True, vector['score'], vector['valid_ticks'], 'VERIFIED'))

    def test_early_finish_cannot_fabricate_verified_game(self):
        self.assertFalse(simulate_and_verify(42, [], 0, 1)[0])

    def test_invalid_or_unbounded_inputs_rejected(self):
        for jumps, score, ticks in [([], 1, 10**9), ([], True, 30),
                ([1, 1], 1, 30), ([{'tick': 1, 'high': 'yes'}], 1, 30),
                ([False], 1, 30), ([31], 1, 30), ([], 1, -1)]:
            with self.subTest(jumps=jumps, score=score, ticks=ticks):
                with self.assertRaises(ValueError):
                    simulate_and_verify(42, jumps, score, ticks)


if __name__ == '__main__':
    unittest.main()
