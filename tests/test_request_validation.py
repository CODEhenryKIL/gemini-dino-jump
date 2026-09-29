"""Transport boundaries and guide event contracts; no real database writes."""
import datetime as dt
import http.client
import json
import re
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'server'))
import app
import operations


class QueryBoundaryTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.DinoJumpHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)

    def request(self, path):
        with mock.patch.object(app.Settings, 'from_env', return_value=SimpleNamespace(deployment='boundary-test')):
            connection = http.client.HTTPConnection(*self.server.server_address, timeout=5)
            try:
                connection.request('GET', path)
                response = connection.getresponse()
                return response.status, json.loads(response.read())
            finally:
                connection.close()

    def test_twenty_query_fields_are_allowed(self):
        status, body = self.request('/api/shared/game_constants.json?' + '&'.join(f'q{i}=x' for i in range(20)))
        self.assertEqual(status, 200)
        self.assertIn('version', body)

    def test_twenty_one_fields_return_400_without_database_access(self):
        query = '&'.join(f'q{i}=x' for i in range(21))
        with mock.patch.object(app.db, 'connection') as database:
            for path in ('/api/health', '/api/index.py', '/api/share', '/invite/abcdefghijklm'):
                with self.subTest(path=path):
                    status, body = self.request(path + '?' + query)
                    self.assertEqual((status, body['error']), (400, 'INVALID_QUERY'))
                    self.assertFalse(body['retryable'])
            database.assert_not_called()


class ProfileBoundaryTest(unittest.TestCase):
    def test_line_breaks_controls_and_invisible_formatting_are_rejected(self):
        conn = mock.Mock()
        participant = {'id': 'p1', 'is_public': False}
        for name in ('a\nb', 'a\rb', 'a\tb', 'a\0b', 'a\u2028b', 'a\u2029b', 'a\u200bb', 'a\u202eb', '\nname', 123):
            with self.subTest(name=repr(name)), mock.patch.object(operations, '_participant', return_value=participant):
                with self.assertRaises(operations.DomainError) as error:
                    operations.patch_profile(conn, {'nickname': name}, {})
                self.assertEqual((error.exception.status, error.exception.code), (400, 'VALIDATION_ERROR'))
        conn.execute.assert_not_called()

    def test_normal_korean_nickname_and_existing_privacy_are_preserved(self):
        participant = {'id': 'p1', 'is_public': False}
        result = {**participant, 'nickname': '공룡 🦖', 'referral_code': 'sample-code'}
        with mock.patch.object(operations, '_participant', return_value=participant), mock.patch.object(operations, '_one', return_value=result) as update:
            status, body = operations.patch_profile(mock.Mock(), {'nickname': '  공룡 🦖  '}, {})
        self.assertEqual((status, body['participant']['nickname'], body['participant']['is_public']), (200, '공룡 🦖', False))
        self.assertEqual(update.call_args.args[2], ('공룡 🦖', False, 'p1'))


class GuideAnalyticsContractTest(unittest.TestCase):
    def test_actual_guide_source_is_accepted_by_server_with_content_dimensions(self):
        source = (ROOT / 'public/js/views/benefit_view.js').read_text()
        match = re.search(r"analytics\.track\('share_attempted', \{ source: '([^']+)', content, position: 'benefit_guides'", source)
        self.assertIsNotNone(match)
        conn = mock.Mock()
        conn.execute.return_value.rowcount = 1
        events = []
        for content in ('study_note', 'job_photo'):
            for method, status in (('copy', 'copied'), ('native', 'share_sheet_closed'), ('native', 'cancelled')):
                events.append({'event_id': f'guide-{content}-{method}-{status}', 'name': 'share_attempted', 'screen': 'benefit',
                               'occurred_at': dt.datetime.now(dt.timezone.utc).isoformat(),
                               'dimensions': {'source': match.group(1), 'content': content, 'position': 'benefit_guides', 'share_method': method, 'status': status}})
        status, response = operations.events_batch(conn, {'events': events}, {'campaign_id': 'test', 'environment': 'local', 'deployment': 'contract-test', 'event_version': 'phase2-v1'})
        self.assertEqual((status, response['accepted'], response['rejected']), (202, 6, 0))
        self.assertEqual(conn.execute.call_count, 6)


if __name__ == '__main__':
    unittest.main()
