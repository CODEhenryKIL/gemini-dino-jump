import sys
import unittest
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import game_verifier as verifier


class GameVerifierSafetyTest(unittest.TestCase):
    def test_absent_collision_cannot_be_replaced_by_the_submitted_finish(self):
        with mock.patch.object(verifier, 'check_aabb', return_value=False):
            valid, score, ticks, reason = verifier.simulate_and_verify(1, [], 100, 600)
        self.assertFalse(valid)
        self.assertEqual((score, ticks, reason), (0, 0, 'NO_COLLISION'))

    def test_real_collision_still_verifies(self):
        for seed in (1, 7, 123456, 2147483646):
            _, score, ticks, _ = verifier.simulate_and_verify(seed, [], 0, 600)
            self.assertGreater(ticks, 0)
            self.assertEqual(verifier.simulate_and_verify(seed, [], score, ticks),
                             (True, score, ticks, 'VERIFIED'))

    def test_numeric_fields_require_integers_without_coercion(self):
        for value in (True, False, 32.9, 32.0, '32', None, float('inf'), float('nan')):
            with self.subTest(field='score', value=value), self.assertRaises(ValueError):
                verifier.simulate_and_verify(1, [], value, 194)
            with self.subTest(field='ticks', value=value), self.assertRaises(ValueError):
                verifier.simulate_and_verify(1, [], 32, value)

    def test_high_jump_flag_requires_boolean(self):
        for value in ('false', 0, 1, None, []):
            with self.subTest(value=value), self.assertRaises(ValueError):
                verifier.simulate_and_verify(1, [{'tick': 10, 'high': value}], 32, 194)


if __name__ == '__main__':
    unittest.main()
