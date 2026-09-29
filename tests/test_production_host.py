import contextlib
import email.message
import http.client
import json
import sys
import threading
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app
import db

BASE = 'https://google-korea-team-gemini.vercel.app'
HOST = 'google-korea-team-gemini.vercel.app'
CANDIDATE = 'dino-candidate.vercel.app'


class ProductionHostTest(unittest.TestCase):
    def handler(self, host=HOST, origin=None, extra=()):
        handler = object.__new__(app.DinoJumpHandler)
        handler.headers = email.message.Message()
        if host is not None:
            handler.headers.add_header('Host', host)
        if origin is not None:
            handler.headers.add_header('Origin', origin)
        for name, value in extra:
            handler.headers.add_header(name, value)
        return handler

    def settings(self, **changes):
        return SimpleNamespace(environment='production', event_enabled=True, base_url=BASE, **changes)

    def test_public_routes_require_canonical_host_including_get_and_callback(self):
        for path in ('/api/participants/me', '/api/participants/anonymous', '/api/game-sessions',
                     '/api/claims', '/api/referrals/share-intents', '/api/draws',
                     '/api/observations', '/api/analytics/events', app.KAKAO_WEBHOOK_PATH):
            with self.subTest(path=path):
                with self.assertRaisesRegex(app.DomainError, '공식 행사 주소'):
                    self.handler(CANDIDATE)._production_host(self.settings(), path)
                self.handler()._production_host(self.settings(), path)

    def test_host_cannot_be_replaced_by_forwarded_headers_or_duplicates(self):
        for handler in (self.handler(None), self.handler(HOST + ':443'),
                        self.handler(HOST + '.attacker.test'), self.handler(HOST + ', ' + CANDIDATE),
                        self.handler(HOST, extra=(('Host', HOST),)),
                        self.handler(CANDIDATE, extra=(('X-Forwarded-Host', HOST), ('X-Vercel-Forwarded-Host', HOST)))):
            with self.assertRaises(app.DomainError):
                handler._production_host(self.settings(), '/api/draws')

    def test_public_origin_must_match_canonical_origin(self):
        self.handler(origin=BASE)._production_host(self.settings(), '/api/draws')
        self.handler(HOST.upper())._production_host(self.settings(), '/api/draws')
        self.handler(extra=(('X-Forwarded-Host', CANDIDATE),))._production_host(self.settings(), '/api/draws')
        with self.assertRaises(app.DomainError):
            self.handler(origin='https://' + CANDIDATE)._production_host(self.settings(), '/api/draws')

    def test_candidate_operator_checks_and_disabled_preparation_remain_accessible(self):
        for path in ('/api/health', '/api/config', '/api/admin/claims', '/api/admin/session'):
            self.handler(CANDIDATE)._production_host(self.settings(), path)
        for environment, enabled in (('production', False), ('preview', True), ('test', True)):
            settings = SimpleNamespace(environment=environment, event_enabled=enabled, base_url=BASE)
            self.handler(CANDIDATE)._production_host(settings, '/api/participants/anonymous')

    def test_http_candidate_is_denied_before_database_access(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.DinoJumpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        settings = self.settings(deployment='host-boundary-test', campaign_id='test')
        try:
            with mock.patch.object(app.Settings, 'from_env', return_value=settings), \
                 mock.patch.object(app.db, 'connection') as connect, \
                 mock.patch.object(app.sys.stderr, 'write'):
                for method, path in (('POST', '/api/participants/anonymous'), ('GET', '/api/me'),
                                     ('GET', app.KAKAO_WEBHOOK_PATH), ('POST', app.KAKAO_WEBHOOK_PATH),
                                     ('OPTIONS', '/api/draws'), ('GET', '/api/adminish')):
                    conn = http.client.HTTPConnection(*server.server_address, timeout=5)
                    conn.request(method, path, headers={'Host': CANDIDATE})
                    response = conn.getresponse()
                    self.assertEqual(response.status, 403)
                    self.assertEqual(json.loads(response.read())['error'], 'PUBLIC_HOST_REQUIRED')
                    conn.close()
                connect.assert_not_called()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

    def test_guard_is_checked_only_after_shared_cutover_lock(self):
        calls = []
        conn = mock.Mock()
        conn.execute.side_effect = lambda sql: calls.append('lock')
        with mock.patch.object(db, 'check_environment', side_effect=lambda *_: calls.append('guard')):
            db.check_business_environment(conn, self.settings())
        self.assertEqual(calls, ['lock', 'guard'])
        conn.execute.assert_called_once_with("select pg_advisory_xact_lock_shared(hashtext('dino-prod-cutover'))")
        conn.reset_mock()
        db.check_business_environment(conn, SimpleNamespace(environment='preview'))
        conn.execute.assert_not_called()

    def test_changed_guard_between_admission_and_dispatch_cannot_write(self):
        server = app.ThreadingHTTPServer(('127.0.0.1', 0), app.DinoJumpHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        settings = self.settings(deployment='host-boundary-test', campaign_id='test')
        try:
            with mock.patch.object(app.Settings, 'from_env', return_value=settings), \
                 mock.patch.object(app.DinoJumpHandler, '_origin'), \
                 mock.patch.object(app.DinoJumpHandler, '_context', return_value={}), \
                 mock.patch.object(app.DinoJumpHandler, '_rate'), \
                 mock.patch.object(db, 'connection', side_effect=lambda _: contextlib.nullcontext(mock.Mock())), \
                 mock.patch.object(db, 'transaction', side_effect=lambda _: contextlib.nullcontext()), \
                 mock.patch.object(db, 'check_environment', return_value={'campaign_id': 'test'}), \
                 mock.patch.object(db, 'check_business_environment', side_effect=app.ConfigurationError('PRODUCTION_GUARD_MISMATCH')), \
                 mock.patch.object(app, 'dispatch') as dispatch, \
                 mock.patch.object(app.sys.stderr, 'write'):
                conn = http.client.HTTPConnection(*server.server_address, timeout=5)
                conn.request('POST', '/api/draws', headers={'Host': HOST})
                response = conn.getresponse()
                self.assertEqual(response.status, 503)
                self.assertEqual(json.loads(response.read())['error'], 'SERVICE_UNAVAILABLE')
                dispatch.assert_not_called()
                conn.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)


if __name__ == '__main__':
    unittest.main()
