"""Bounded reusable connections to the PostgreSQL transaction pooler."""
import atexit
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic
import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from config import APP_ROLE,ConfigurationError,SCHEMA_NAME,SCHEMA_VERSION
_slots=BoundedSemaphore(8)
_idle=[]
_idle_lock=Lock()

def close_idle_connections():
    with _idle_lock:
        idle=list(_idle)
        _idle.clear()
    for _,conn,_,_ in idle: conn.close()

atexit.register(close_idle_connections)

class DatabaseBusy(RuntimeError): pass
@contextmanager
def connection(settings):
    if not _slots.acquire(timeout=3): raise DatabaseBusy()
    conn=None
    key=(settings.database_url,settings.environment)
    try:
        now=monotonic()
        with _idle_lock:
            while _idle:
                old_key,candidate,created,last_used=_idle.pop()
                if old_key==key and not candidate.closed and now-created<300 and now-last_used<60:
                    conn=candidate
                    break
                candidate.close()
        # A frozen function may retain a socket which the pooler has closed.
        # Check it before handing it to business code; never replay that code.
        if conn is not None and now-last_used>5:
            try: conn.execute("select 1")
            except psycopg.Error:
                conn.close()
                conn=None
        opts={"connect_timeout":5,"autocommit":True,"prepare_threshold":None,"row_factory":dict_row,"application_name":"gemini-dino-jump-phase1"}
        if settings.environment=="preview": opts.update(sslmode="verify-full",sslrootcert=str(Path(__file__).parent/"certs"/"supabase-ca-2021.crt"))
        if conn is None:
            conn=psycopg.connect(settings.database_url,**opts)
            created=monotonic()
        yield conn
        # Only clean autocommit connections can cross request boundaries.
        if not conn.closed and conn.info.transaction_status==TransactionStatus.IDLE:
            with _idle_lock: _idle.append((key,conn,created,monotonic()))
            conn=None
    finally:
        if conn is not None: conn.close()
        _slots.release()
@contextmanager
def transaction(conn):
    with conn.transaction():
        conn.execute("set local statement_timeout='5000ms'; set local lock_timeout='1500ms'; set local idle_in_transaction_session_timeout='8000ms'")
        yield
def check_environment(conn,settings):
    guard=conn.execute("select g.*, current_user as connection_role, exists(select 1 from dino_dev.schema_version where version=%s) as version_present from dino_dev.environment_guard g where singleton",(SCHEMA_VERSION,)).fetchone()
    if not guard or not guard["version_present"]: raise ConfigurationError("DATABASE_NOT_PROVISIONED")
    if guard["environment"]!=settings.environment or guard["project_ref"]!=settings.project_ref or guard["schema_name"]!=SCHEMA_NAME: raise ConfigurationError("DATABASE_GUARD_MISMATCH")
    if not guard["synthetic_only"] or not settings.synthetic_only: raise ConfigurationError("SYNTHETIC_GUARD_REQUIRED")
    if guard["connection_role"]!=APP_ROLE: raise ConfigurationError("DATABASE_ROLE_MISMATCH")
    del guard["connection_role"],guard["version_present"]
    return guard
def rate_limits(conn,buckets,window=60):
    ordered=sorted(buckets)
    rows=conn.execute("select dino_dev.consume_rate_limit(k,n,%s) allowed from unnest(%s::text[],%s::integer[]) b(k,n)",(window,[k for k,_ in ordered],[n for _,n in ordered])).fetchall()
    return all(r["allowed"] for r in rows)
