"""Validated environment configuration. No credentials in public config."""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
from urllib.parse import urlparse

ROOT = Path(__file__).resolve().parent.parent
CONSTANTS = json.loads((ROOT / 'shared/game_constants.json').read_text())
SCHEMA_VERSION = '20260923033611'
APPROVED_PREVIEW_PROJECT_REF = 'igfrnexknwtiljdqjrbp'


class ConfigurationError(Exception):
    pass


def _url(value, *, local=False):
    parsed = urlparse(value)
    if parsed.scheme != 'https' and not (local and parsed.scheme == 'http' and parsed.hostname in ('localhost', '127.0.0.1', '::1')):
        raise ConfigurationError('HTTPS_URL_REQUIRED')
    if not parsed.hostname or parsed.username or parsed.password or parsed.query or parsed.fragment:
        raise ConfigurationError('INVALID_URL')
    return value.rstrip('/')


@dataclass(frozen=True)
class Settings:
    environment: str
    database_url: str
    project_ref: str
    base_url: str
    benefit_url: str
    supabase_url: str
    publishable_key: str
    token_pepper: str
    web_analytics_enabled: bool
    allowed_origins: frozenset
    game_version: str = CONSTANTS['version']

    @classmethod
    def from_env(cls):
        environment = os.environ.get('APP_ENV', 'local')
        if environment not in ('local', 'test', 'preview', 'production'):
            raise ConfigurationError('INVALID_APP_ENV')
        if environment == 'production':
            raise ConfigurationError('PRODUCTION_NOT_PROVISIONED')
        if os.environ.get('VERCEL_ENV') and os.environ['VERCEL_ENV'] != environment:
            raise ConfigurationError('VERCEL_ENV_MISMATCH')
        local = environment in ('local', 'test')
        project_ref = os.environ.get('SUPABASE_PROJECT_REF', 'local' if local else '')
        if not project_ref or (not local and (len(project_ref) != 20 or not project_ref.isalpha())):
            raise ConfigurationError('PROJECT_REF_REQUIRED')
        if environment == 'preview' and project_ref != APPROVED_PREVIEW_PROJECT_REF:
            raise ConfigurationError('PREVIEW_PROJECT_NOT_APPROVED')
        database_url = os.environ.get('DATABASE_URL', '')
        parsed_db = urlparse(database_url)
        if parsed_db.scheme not in ('postgres', 'postgresql') or not parsed_db.hostname:
            raise ConfigurationError('POSTGRES_DATABASE_URL_REQUIRED')
        if local != (parsed_db.hostname in ('localhost', '127.0.0.1', '::1')):
            raise ConfigurationError('DATABASE_ENVIRONMENT_MISMATCH')
        if not local and (parsed_db.port != 6543 or not parsed_db.hostname.endswith('.pooler.supabase.com') or parsed_db.username != f'dino_app.{project_ref}'):
            raise ConfigurationError('SCOPED_TRANSACTION_POOLER_REQUIRED')
        if local and parsed_db.username != 'dino_app':
            raise ConfigurationError('APPLICATION_DB_ROLE_REQUIRED')
        base_default = ('https://' + os.environ['VERCEL_URL']) if os.environ.get('VERCEL_URL') else 'http://127.0.0.1:3000'
        base_url = _url(os.environ.get('APP_BASE_URL', base_default), local=local)
        benefit_url = _url(os.environ.get('GEMINI_BENEFIT_URL', 'https://gemini.google.com/students'))
        supabase_url = _url(os.environ.get('SUPABASE_URL', 'http://127.0.0.1:54321' if local else ''), local=local)
        if urlparse(supabase_url).path not in ('', '/'):
            raise ConfigurationError('SUPABASE_URL_MUST_BE_ORIGIN')
        if not local and urlparse(supabase_url).hostname != f'{project_ref}.supabase.co':
            raise ConfigurationError('SUPABASE_PROJECT_MISMATCH')
        pepper = os.environ.get('SESSION_TOKEN_PEPPER', '')
        if len(pepper) < 32:
            raise ConfigurationError('SESSION_TOKEN_PEPPER_REQUIRED')
        publishable_key = os.environ.get('SUPABASE_PUBLISHABLE_KEY', '')
        if publishable_key.startswith('sb_secret_'):
            raise ConfigurationError('SERVER_KEY_IN_PUBLIC_CONFIG')
        if not local and publishable_key.count('.') != 2 and not re.fullmatch(r'sb_publishable_[A-Za-z0-9_-]{20,}', publishable_key):
            raise ConfigurationError('VALID_PUBLIC_KEY_REQUIRED')
        if publishable_key.count('.') == 2:
            import base64
            try:
                part = publishable_key.split('.')[1]
                payload = json.loads(base64.urlsafe_b64decode(part + '=' * (-len(part) % 4)))
                if payload.get('role') != 'anon':
                    raise ValueError()
            except (ValueError, KeyError):
                raise ConfigurationError('INVALID_PUBLIC_KEY') from None
        extra = [s.strip() for s in os.environ.get('ALLOWED_ORIGINS', '').split(',') if s.strip()]
        origins = frozenset([base_url] + [_url(x, local=local) for x in extra])
        if any(urlparse(x).path not in ('', '/') for x in origins):
            raise ConfigurationError('ORIGIN_MUST_NOT_INCLUDE_PATH')
        return cls(environment, database_url, project_ref, base_url, benefit_url,
                   supabase_url, publishable_key, pepper,
                   os.environ.get('WEB_ANALYTICS_ENABLED', 'false').lower() == 'true', origins)

    @property
    def synthetic(self):
        return self.environment != 'production'

    def public(self):
        return {'environment': self.environment, 'base_url': self.base_url,
                'benefit_url': self.benefit_url, 'supabase_url': self.supabase_url,
                'supabase_publishable_key': self.publishable_key,
                'web_analytics_enabled': self.web_analytics_enabled,
                'game_version': self.game_version}
