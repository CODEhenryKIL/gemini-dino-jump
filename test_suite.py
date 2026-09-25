"""Current Python test runner; remote performance is a separate measured gate."""
import unittest

if __name__ == '__main__':
    suite = unittest.defaultTestLoader.discover('tests', pattern='test_*.py')
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    raise SystemExit(not result.wasSuccessful())
