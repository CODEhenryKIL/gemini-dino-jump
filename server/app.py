"""Dino Jump HTTP transport for local use and Vercel Python Functions."""
import json
import os
import re
import secrets
import sys
import time
import uuid
from datetime import datetime
from decimal import Decimal
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, quote, urlparse

sys.path.insert(0, os.path.dirname(__file__))
import auth
import db
import game_verifier
import psycopg
from config import CONSTANTS, ROOT, ConfigurationError, Settings
from services.operations import DomainError, dispatch

PUBLIC_DIR = str(ROOT / 'public')
MAX_BODY = 65536
LEGACY_PATHS = ('/gate-runner', '/gate-runner/', '/gate_runner.html')


def _json_default(value):
    if isinstance(value, uuid.UUID):
        return str(value)
    if isinstance(value, datetime):
        return int(value.timestamp())
    if isinstance(value, Decimal):
        return float(value)
    raise TypeError('Non-JSON response')


class DinoJumpHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        self.request_id = str(uuid.uuid4())
        self.cors_origin = None
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Default access logs include query strings and referral codes; omit them.
        pass

    def _log(self, event, status, started):
        sys.stderr.write(json.dumps({'event': event, 'status': status,
            'request_id': self.request_id, 'duration_ms': round((time.monotonic()-started)*1000)}) + '\n')

    def end_headers(self):
        self.send_header('X-Content-Type-Options', 'nosniff')
        self.send_header('Referrer-Policy', 'no-referrer')
        self.send_header('X-Frame-Options', 'DENY')
        self.send_header('Permissions-Policy', 'camera=(), microphone=(), geolocation=()')
        super().end_headers()

    def send_json(self, status, data):
        encoded = json.dumps(data, ensure_ascii=False, allow_nan=False, default=_json_default).encode()
        self.send_response(status)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(encoded)))
        self.send_header('Cache-Control', 'no-store, private')
        self.send_header('Vary', 'Origin, Authorization')
        self.send_header('X-Request-ID', self.request_id)
        if self.cors_origin:
            self.send_header('Access-Control-Allow-Origin', self.cors_origin)
        if status in (429, 503):
            self.send_header('Retry-After', '5')
        self.end_headers()
        if self.command != 'HEAD':
            self.wfile.write(encoded)

    def fail(self, code, message, status=400):
        self.send_json(status, {'error': code, 'message': message, 'request_id': self.request_id})

    def parse_body(self):
        if self.headers.get('Transfer-Encoding'):
            raise DomainError('INVALID_BODY', '요청 형식을 확인해 주세요.', 400)
        try:
            length = int(self.headers.get('Content-Length', '0'))
        except ValueError:
            raise DomainError('INVALID_BODY', '요청 크기를 확인해 주세요.', 400) from None
        if not 0 <= length <= MAX_BODY:
            raise DomainError('BODY_TOO_LARGE', '요청 데이터가 너무 큽니다.', 413)
        if not length:
            return {}
        if self.headers.get_content_type() != 'application/json':
            raise DomainError('JSON_REQUIRED', 'JSON 요청이 필요합니다.', 415)
        try:
            self.connection.settimeout(10)
            body = json.loads(self.rfile.read(length), parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
        except (ValueError, UnicodeDecodeError, TimeoutError):
            raise DomainError('INVALID_JSON', '요청 데이터를 확인해 주세요.', 400) from None
        if not isinstance(body, dict):
            raise DomainError('INVALID_BODY', '요청 데이터는 객체여야 합니다.', 400)
        return body

    def _origin(self, settings):
        origin = self.headers.get('Origin')
        if origin:
            if origin not in settings.allowed_origins:
                raise DomainError('ORIGIN_DENIED', '허용되지 않은 요청 출처입니다.', 403)
            self.cors_origin = origin
        if self.command in ('POST', 'PATCH') and self.headers.get('Sec-Fetch-Site') == 'cross-site':
            raise DomainError('ORIGIN_DENIED', '허용되지 않은 요청 출처입니다.', 403)

    def _token(self):
        value = self.headers.get('Authorization', '')
        if not value:
            return ''
        if not value.startswith('Bearer ') or len(value) > 8200:
            raise DomainError('AUTH_REQUIRED', '다시 로그인해 주세요.', 401)
        return value[7:]

    def _ip_subject(self, settings):
        # Vercel overwrites x-vercel-forwarded-for at its trusted proxy boundary.
        address = self.client_address[0] if self.client_address else 'local'
        if os.environ.get('VERCEL'):
            address = self.headers.get('x-vercel-forwarded-for', address).split(',')[0].strip()
        return auth.token_hash(address, settings.token_pepper)

    def _bucket(self, settings, path, token):
        subject = self._ip_subject(settings)
        if token and not path.startswith('/api/admin/'):
            subject = auth.token_hash(token, settings.token_pepper)
        if path == '/api/participants/anonymous':
            # A campus or event may have 200 visitors behind one NAT address.
            return 'anonymous:' + subject, 240
        if path.endswith('/finish'):
            return 'finish:' + subject, 20
        if path.endswith('/start') or path == '/api/game-sessions':
            return 'start:' + subject, 20
        if path == '/api/draws' or path.endswith('/submit') or path.startswith('/api/referrals/'):
            return 'reward:' + subject, 30
        if path.startswith('/api/admin/'):
            return 'admin:' + subject, 90
        return 'api:' + subject, 180

    def _rate_limit(self, conn, settings, path, token):
        bucket, limit = self._bucket(settings, path, token)
        buckets = [('ip:' + self._ip_subject(settings), 12000), (bucket, limit)]
        if path.endswith('/finish'):
            buckets.append(('ip-finish:' + self._ip_subject(settings), 1200))
        if not db.rate_limits(conn, buckets):
            raise DomainError('RATE_LIMITED', '요청이 많습니다. 잠시 뒤 다시 시도해 주세요.', 429)

    def _api(self):
        started = time.monotonic()
        status = 500
        try:
            settings = Settings.from_env()
            self._origin(settings)
            parsed = urlparse(self.path)
            path = parsed.path
            if len(self.path) > 2048:
                raise DomainError('URL_TOO_LONG', '요청 주소가 너무 깁니다.', 414)
            query = parse_qs(parsed.query, max_num_fields=20)
            query = {key: values[-1] for key, values in query.items()}
            if self.command == 'OPTIONS':
                self.send_response(204)
                if self.cors_origin:
                    self.send_header('Access-Control-Allow-Origin', self.cors_origin)
                self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
                self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization, Idempotency-Key')
                self.send_header('Cache-Control', 'no-store')
                self.end_headers()
                status = 204
                return
            method = 'GET' if self.command == 'HEAD' else self.command
            if method == 'GET' and path == '/api/config':
                status = 200
                self.send_json(status, settings.public())
                return
            if method == 'GET' and path == '/api/shared/game_constants.json':
                status = 200
                self.send_json(status, CONSTANTS)
                return
            token = self._token()
            body = self.parse_body() if method in ('POST', 'PATCH') else {}
            if self.headers.get('Idempotency-Key'):
                key = self.headers['Idempotency-Key']
                if not re.fullmatch(r'[A-Za-z0-9_-]{8,100}', key):
                    raise DomainError('INVALID_IDEMPOTENCY_KEY', '요청 식별자를 확인해 주세요.', 400)
                body['idempotency_key'] = key
            context = {'environment': settings.environment, 'base_url': settings.base_url,
                'benefit_url': settings.benefit_url, 'game_version': settings.game_version,
                'participant_token_hash': auth.token_hash(token, settings.token_pepper) if token else '',
                'admin_user_id': None, 'request_id': self.request_id, 'synthetic': settings.synthetic}
            new_token = None
            if method == 'POST' and path == '/api/participants/anonymous':
                new_token = secrets.token_urlsafe(32)
                context['new_token_hash'] = auth.token_hash(new_token, settings.token_pepper)
            is_admin = path.startswith('/api/admin/')
            if is_admin:
                if not token:
                    raise auth.AuthenticationError()
                # Limit Auth traffic, then release scarce DB slots before HTTP I/O.
                with db.connection(settings) as conn:
                    with db.transaction(conn):
                        db.check_environment(conn, settings)
                    self._rate_limit(conn, settings, path, token)
                context['admin_user_id'] = auth.verify_admin_identity(token, settings)
            with db.connection(settings) as conn:
                with db.transaction(conn):
                    db.check_environment(conn, settings)
                if path == '/api/health' and method == 'GET':
                    status, response = 200, {'status': 'ok', 'environment': settings.environment,
                        'game_version': settings.game_version, 'database': 'ok',
                        'project_ref': settings.project_ref, 'synthetic_only': settings.synthetic}
                else:
                    if not is_admin:
                        self._rate_limit(conn, settings, path, token)
                    if method == 'POST' and re.fullmatch(r'/api/game-sessions/[^/]+/finish', path):
                        session_path = path.rsplit('/', 1)[0]
                        with db.transaction(conn):
                            _, session = dispatch(conn, 'GET', session_path, {}, {}, context)
                        if session.get('result') is None:
                            if body.get('version') != session.get('version') or body.get('version') != settings.game_version:
                                raise DomainError('GAME_VERSION_MISMATCH', '새로고침 후 다시 시작해 주세요.', 409)
                            try:
                                valid, score, ticks, reason = game_verifier.simulate_and_verify(
                                    session['seed'], body.get('jump_ticks'), body.get('score'), body.get('valid_ticks'))
                            except (ValueError, TypeError, KeyError):
                                raise DomainError('INVALID_GAME_INPUT', '게임 기록 형식을 확인해 주세요.', 400) from None
                            context['verification'] = {'valid': valid, 'score': score,
                                'valid_ticks': ticks, 'reason': reason}
                    with db.transaction(conn):
                        status, response = dispatch(conn, method, path, body, query, context)
                    if new_token:
                        response['session_token'] = new_token
                # Both business transaction and connection finish before sending success.
            self.send_json(status, response)
        except DomainError as error:
            status = error.status
            self.fail(error.code, error.message, status)
        except auth.AuthenticationError:
            status = 401
            self.fail('ADMIN_AUTH_REQUIRED', '관리자 계정으로 로그인해 주세요.', status)
        except auth.AuthenticationUnavailable:
            status = 503
            self.fail('AUTH_UNAVAILABLE', '로그인 연결을 확인한 뒤 다시 시도해 주세요.', status)
        except ConfigurationError:
            status = 503
            self.fail('CONFIGURATION_UNAVAILABLE', '서비스 연결 설정을 확인하고 있습니다.', status)
        except (psycopg.Error, db.DatabaseBusy):
            status = 503
            self.fail('DATABASE_UNAVAILABLE', '저장소에 연결하지 못했습니다. 같은 요청을 다시 시도해 주세요.', status)
        except (ValueError, TypeError):
            status = 400
            self.fail('INVALID_REQUEST', '요청 값을 확인해 주세요.', status)
        except (BrokenPipeError, ConnectionResetError):
            status = 499
        except Exception:
            status = 500
            self.fail('INTERNAL_ERROR', '요청을 처리하지 못했습니다. 같은 요청으로 재시도해 주세요.', status)
        finally:
            self._log('api_request', status, started)

    def redirect_legacy_gate(self, path):
        if path not in LEGACY_PATHS:
            return False
        self.send_response(302)
        self.send_header('Location', '/')
        self.send_header('Cache-Control', 'no-store')
        self.end_headers()
        return True

    def _static(self):
        path = urlparse(self.path).path
        if self.redirect_legacy_gate(path):
            return
        if path.startswith('/invite/'):
            code = path.rsplit('/', 1)[-1]
            if not re.fullmatch(r'[A-Za-z0-9_-]{1,64}', code):
                self.send_error(404)
                return
            self.send_response(302)
            self.send_header('Location', '/?invite=' + quote(code))
            self.end_headers()
            return
        if self.command == 'HEAD':
            return super().do_HEAD()
        return super().do_GET()

    def do_GET(self):
        return self._api() if urlparse(self.path).path.startswith('/api/') else self._static()

    def do_HEAD(self):
        return self.do_GET()

    def do_POST(self):
        return self._api()

    def do_PATCH(self):
        return self._api()

    def do_OPTIONS(self):
        return self._api()


def run_server():
    port = int(os.environ.get('PORT', '3000'))
    server = ThreadingHTTPServer(('127.0.0.1', port), DinoJumpHandler)
    print(f'Dino Jump local server: http://127.0.0.1:{port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()


if __name__ == '__main__':
    run_server()
