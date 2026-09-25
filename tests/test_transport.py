"""Actual HTTP boundary tests; business logic uses separate real PG tests."""
import contextlib
import http.client
import io
import json
import os
from pathlib import Path
import sys
import threading
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import app
import auth
import db
from config import Settings, ConfigurationError

LOCAL = {'APP_ENV': 'test', 'DATABASE_URL': 'postgresql://dino_app@127.0.0.1:55432/dino_operations_test',
         'SUPABASE_PROJECT_REF': 'local', 'SESSION_TOKEN_PEPPER': 'unit-test-pepper-' * 3,
         'APP_BASE_URL': 'http://127.0.0.1:3000', 'SUPABASE_PUBLISHABLE_KEY': 'sb_publishable_test'}
REF = 'igfrnexknwtiljdqjrbp'


class ConfigurationTests(unittest.TestCase):
    def settings(self, **extra):
        with patch.dict(os.environ, {**LOCAL, **extra}, clear=True):
            return Settings.from_env()

    def test_public_config_contains_no_server_credentials(self):
        result = self.settings().public()
        self.assertNotIn('database_url', result)
        self.assertNotIn('token_pepper', result)

    def test_remote_identity_and_pooler_required(self):
        valid = dict(APP_ENV='preview', VERCEL_ENV='preview', SUPABASE_PROJECT_REF=REF,
            SUPABASE_PUBLISHABLE_KEY='sb_publishable_' + 'x' * 32,
            SUPABASE_URL=f'https://{REF}.supabase.co', APP_BASE_URL='https://dino-test.vercel.app',
            DATABASE_URL=f'postgresql://dino_app.{REF}:test@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres')
        self.assertTrue(self.settings(**valid).synthetic)
        for key, value in [('VERCEL_ENV','production'), ('DATABASE_URL','postgresql://postgres@127.0.0.1/db'),
                           ('SUPABASE_URL','https://other.supabase.co'),
                           ('SUPABASE_URL',f'https://{REF}.supabase.co/wrong-prefix')]:
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                self.settings(**{**valid,key:value})

    def test_preview_rejects_unapproved_project_and_invalid_public_key(self):
        valid = dict(APP_ENV='preview', SUPABASE_PROJECT_REF=REF,
            SUPABASE_URL=f'https://{REF}.supabase.co', APP_BASE_URL='https://dino-test.vercel.app',
            SUPABASE_PUBLISHABLE_KEY='sb_publishable_' + 'x' * 32,
            DATABASE_URL=f'postgresql://dino_app.{REF}:test@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres')
        for key in ('', 'arbitrary', 'sb_publishable_'):
            with self.subTest(key=key), self.assertRaises(ConfigurationError):
                self.settings(**{**valid, 'SUPABASE_PUBLISHABLE_KEY': key})
        other = 'a' * 20
        with self.assertRaises(ConfigurationError):
            self.settings(**{**valid, 'SUPABASE_PROJECT_REF': other,
                'SUPABASE_URL': f'https://{other}.supabase.co',
                'DATABASE_URL': f'postgresql://dino_app.{other}:test@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres'})

    def test_production_requires_separate_provisioning(self):
        with self.assertRaises(ConfigurationError):
            self.settings(APP_ENV='production', SUPABASE_PROJECT_REF=REF,
                SUPABASE_URL=f'https://{REF}.supabase.co', APP_BASE_URL='https://dino-test.vercel.app',
                SUPABASE_PUBLISHABLE_KEY='sb_publishable_' + 'x' * 32,
                DATABASE_URL=f'postgresql://dino_app.{REF}:test@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres')

    def test_unsafe_configuration_rejected(self):
        for fields in [{'SUPABASE_PUBLISHABLE_KEY':'sb_secret_test'},
                       {'SESSION_TOKEN_PEPPER':'short'}, {'ALLOWED_ORIGINS':'*'},
                       {'DATABASE_URL':'postgresql://postgres@127.0.0.1/db'}]:
            with self.subTest(fields=list(fields)), self.assertRaises(ConfigurationError):
                self.settings(**fields)


class AuthTests(unittest.TestCase):
    def setUp(self):
        with patch.dict(os.environ, LOCAL, clear=True): self.settings = Settings.from_env()

    def test_unconfirmed_or_anonymous_identity_rejected(self):
        for data in [{'id':'00000000-0000-0000-0000-000000000001'},
                     {'id':'00000000-0000-0000-0000-000000000001','is_anonymous':True,'email_confirmed_at':'2026-09-23'}]:
            with patch('auth.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(data).encode())):
                with self.assertRaises(auth.AuthenticationError): auth.verify_admin_identity('test', self.settings)

    def test_confirmed_identity_requires_auth_service_response(self):
        data = {'id':'00000000-0000-0000-0000-000000000001','email_confirmed_at':'2026-09-23',
                'user_metadata':{'admin':True}}
        with patch('auth.urllib.request.urlopen', return_value=io.BytesIO(json.dumps(data).encode())) as request:
            self.assertEqual(auth.verify_admin_identity('test', self.settings), data['id'])
            self.assertTrue(request.call_args.args[0].full_url.endswith('/auth/v1/user'))
        # This proves identity only; PG integration tests deny non-member IDs.

    def test_network_failure_not_success(self):
        with patch('auth.urllib.request.urlopen', side_effect=urllib.error.URLError('offline')):
            with self.assertRaises(auth.AuthenticationUnavailable): auth.verify_admin_identity('test', self.settings)

    def test_token_hash_is_pepper_scoped(self):
        self.assertNotEqual(auth.token_hash('same','pepper1'), auth.token_hash('same','pepper2'))


class HttpBoundaryTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.environment = patch.dict(os.environ, LOCAL, clear=True)
        cls.environment.start()
        cls.server = app.ThreadingHTTPServer(('127.0.0.1',0), app.DinoJumpHandler)
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown(); cls.server.server_close(); cls.thread.join()
        cls.environment.stop()

    def request(self, method, path, body=None, headers=None):
        connection = http.client.HTTPConnection('127.0.0.1',self.server.server_port,timeout=3)
        connection.request(method,path,body=body,headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    def test_config_no_store_and_legacy_redirect(self):
        status, headers, content = self.request('GET','/api/config')
        self.assertEqual(status,200); self.assertEqual(headers['Cache-Control'],'no-store, private')
        self.assertNotIn('unit-test-pepper',content.decode())
        status, headers, _ = self.request('GET','/gate_runner.html')
        self.assertEqual((status,headers['Location']),(302,'/'))

    def test_cross_origin_write_denied_before_database(self):
        with patch('app.db.connection') as database:
            status, _, _ = self.request('POST','/api/draws','{}',
                {'Origin':'https://untrusted.example','Content-Type':'application/json'})
            self.assertEqual(status,403); database.assert_not_called()

    def test_bounded_json_rejects_invalid_body(self):
        for content, expected in [('x'*65537,413), ('[]',400), ('{"value":NaN}',400)]:
            with self.subTest(expected=expected):
                status,_,_ = self.request('POST','/api/draws',content,{'Content-Type':'application/json'})
                self.assertEqual(status,expected)

    def test_admin_has_no_unauthenticated_fallback(self):
        status,_,data = self.request('GET','/api/admin/overview')
        self.assertEqual(status,401); self.assertEqual(json.loads(data)['error'],'ADMIN_AUTH_REQUIRED')

    def test_admin_auth_wait_releases_database_and_keeps_rate_limit_first(self):
        order = []
        @contextlib.contextmanager
        def connection(settings):
            order.append('open')
            try:
                yield object()
            finally:
                order.append('close')
        def limited(conn, buckets):
            order.append('rate')
            return True
        def identity(token, settings):
            self.assertEqual(order, ['open', 'rate', 'close'])
            order.append('auth')
            return '00000000-0000-0000-0000-000000000001'
        with patch('app.db.connection', side_effect=connection), \
             patch('app.db.transaction', side_effect=lambda _: contextlib.nullcontext()), \
             patch('app.db.check_environment'), patch('app.db.rate_limits', side_effect=limited), \
             patch('app.auth.verify_admin_identity', side_effect=identity), \
             patch('app.dispatch', return_value=(200, {'ok': True})):
            status, _, _ = self.request('GET', '/api/admin/overview', headers={'Authorization': 'Bearer test'})
        self.assertEqual(status, 200)
        self.assertEqual(order, ['open', 'rate', 'close', 'auth', 'open', 'close'])

    def test_database_outage_never_returns_success_or_secret(self):
        with patch('app.db.connection',side_effect=app.psycopg.OperationalError('SECRET_HOST')), contextlib.redirect_stderr(io.StringIO()) as logs:
            status, headers, data = self.request('GET','/api/health')
        self.assertEqual(status,503); self.assertEqual(headers['Retry-After'],'5')
        self.assertNotIn('SECRET_HOST',data.decode()+logs.getvalue())
        self.assertEqual(json.loads(data)['error'],'DATABASE_UNAVAILABLE')


if __name__ == '__main__': unittest.main()
