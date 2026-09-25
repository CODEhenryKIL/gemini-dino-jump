"""Short-lived PostgreSQL connections; schema and seed are explicit setup steps."""
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore
import psycopg
from psycopg.rows import dict_row
from config import ConfigurationError, SCHEMA_VERSION

_slots = BoundedSemaphore(2)


class DatabaseBusy(Exception):
    pass


@contextmanager
def connection(settings):
    if not _slots.acquire(timeout=3):
        raise DatabaseBusy()
    try:
        options = {'connect_timeout': 5, 'autocommit': True,
                   'prepare_threshold': None, 'row_factory': dict_row,
                   'application_name': 'gemini-dino-jump'}
        if settings.environment in ('preview', 'production'):
            options.update(sslmode='verify-full',
                           sslrootcert=str(Path(__file__).resolve().parent / 'certs/supabase-ca-2021.crt'))
        with psycopg.connect(settings.database_url, **options) as conn:
            yield conn
    finally:
        _slots.release()


@contextmanager
def transaction(conn):
    with conn.transaction():
        conn.execute("SET LOCAL statement_timeout = '5000ms'")
        conn.execute("SET LOCAL lock_timeout = '2000ms'")
        conn.execute("SET LOCAL idle_in_transaction_session_timeout = '10000ms'")
        yield


def check_environment(conn, settings):
    guard = conn.execute('SELECT environment, project_ref, synthetic_only FROM dino.environment_guard WHERE singleton').fetchone()
    version = conn.execute('SELECT version FROM dino.schema_version WHERE version = %s', (SCHEMA_VERSION,)).fetchone()
    if not guard or not version:
        raise ConfigurationError('DATABASE_NOT_PROVISIONED')
    if guard['environment'] != settings.environment or guard['project_ref'] != settings.project_ref:
        raise ConfigurationError('DATABASE_ENVIRONMENT_MISMATCH')
    if bool(guard['synthetic_only']) != settings.synthetic:
        raise ConfigurationError('DATABASE_SYNTHETIC_MODE_MISMATCH')


def rate_limit(conn, bucket_key, limit, window=60):
    return rate_limits(conn, [(bucket_key, limit)], window)


def rate_limits(conn, buckets, window=60):
    # Stable lock order and a single round-trip for the IP and token limits.
    ordered = sorted(buckets)
    with transaction(conn):
        rows = conn.execute('SELECT dino.consume_rate_limit(k, n, %s) AS allowed '
                            'FROM unnest(%s::text[], %s::integer[]) AS b(k,n)',
                            (window, [k for k, _ in ordered], [n for _, n in ordered])).fetchall()
    return all(row['allowed'] for row in rows)
