import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import operations


class MissingParticipantConnection:
    def execute(self, sql, params):
        return self

    def fetchone(self):
        return None


class AuthenticationReloadNoticeTest(unittest.TestCase):
    def test_missing_cookie_requests_reload_without_changing_error_contract(self):
        with self.assertRaises(operations.DomainError) as caught:
            operations._participant(MissingParticipantConnection(), {})

        error = caught.exception
        self.assertEqual((error.code, error.status), ("UNAUTHORIZED", 401))
        self.assertIn("새로고침", error.message)

    def test_stale_beta_cookie_requests_reload_when_production_has_no_session(self):
        with self.assertRaises(operations.DomainError) as caught:
            operations._participant(
                MissingParticipantConnection(),
                {"participant_token_hash": "stale-beta-cookie-hash"},
            )

        error = caught.exception
        self.assertEqual((error.code, error.status), ("SESSION_INVALID", 401))
        self.assertIn("새로고침", error.message)


if __name__ == "__main__":
    unittest.main()
