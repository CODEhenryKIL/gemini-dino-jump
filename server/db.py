"""Short-lived, transaction-pooler-safe PostgreSQL access."""
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore
import psycopg
from psycopg.rows import dict_row
from config import APP_ROLE,ConfigurationError,SCHEMA_NAME,SCHEMA_VERSION
_slots=BoundedSemaphore(2)
class DatabaseBusy(RuntimeError): pass
@contextmanager
def connection(settings):
    if not _slots.acquire(timeout=3): raise DatabaseBusy()
    try:
        opts={"connect_timeout":5,"autocommit":True,"prepare_threshold":None,"row_factory":dict_row,"application_name":"gemini-dino-jump-phase1"}
        if settings.environment=="preview": opts.update(sslmode="verify-full",sslrootcert=str(Path(__file__).parent/"certs"/"supabase-ca-2021.crt"))
        with psycopg.connect(settings.database_url,**opts) as conn: yield conn
    finally: _slots.release()
@contextmanager
def transaction(conn):
    with conn.transaction():
        conn.execute("set local statement_timeout='5000ms'"); conn.execute("set local lock_timeout='1500ms'"); conn.execute("set local idle_in_transaction_session_timeout='8000ms'")
        yield
def check_environment(conn,settings):
    guard=conn.execute("select * from dino_dev.environment_guard where singleton").fetchone()
    version=conn.execute("select version from dino_dev.schema_version where version=%s",(SCHEMA_VERSION,)).fetchone()
    role=conn.execute("select current_user name").fetchone()
    if not guard or not version: raise ConfigurationError("DATABASE_NOT_PROVISIONED")
    if guard["environment"]!=settings.environment or guard["project_ref"]!=settings.project_ref or guard["schema_name"]!=SCHEMA_NAME: raise ConfigurationError("DATABASE_GUARD_MISMATCH")
    if not guard["synthetic_only"] or not settings.synthetic_only: raise ConfigurationError("SYNTHETIC_GUARD_REQUIRED")
    if role["name"]!=APP_ROLE: raise ConfigurationError("DATABASE_ROLE_MISMATCH")
    return guard
def rate_limits(conn,buckets,window=60):
    ordered=sorted(buckets)
    rows=conn.execute("select dino_dev.consume_rate_limit(k,n,%s) allowed from unnest(%s::text[],%s::integer[]) b(k,n)",(window,[k for k,_ in ordered],[n for _,n in ordered])).fetchall()
    return all(r["allowed"] for r in rows)
