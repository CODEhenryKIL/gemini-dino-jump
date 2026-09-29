"""Bounded reusable connections to the PostgreSQL transaction pooler."""
import atexit
from datetime import datetime,timezone
from contextlib import contextmanager
from pathlib import Path
from threading import BoundedSemaphore, Lock
from time import monotonic,sleep
import psycopg
from psycopg.pq import TransactionStatus
from psycopg.rows import dict_row
from config import ConfigurationError,REQUIRED_SCHEMA_VERSIONS,SCHEMA_BINDINGS,database_schema,schema_context
_slots=BoundedSemaphore(8)
_idle=[]
_idle_lock=Lock()
MAX_IDLE_CONNECTIONS=1
_borrowers=0
_EMAXCONN_BACKOFF=(.05,.1,.2)
_EMAXCONN_RETRY_START_WINDOW=.75

def close_idle_connections():
    with _idle_lock:
        idle=list(_idle)
        _idle.clear()
    for _,conn,_,_ in idle: conn.close()

atexit.register(close_idle_connections)

class DatabaseBusy(RuntimeError): pass
def _connect(database_url,opts):
    retry_deadline=monotonic()+_EMAXCONN_RETRY_START_WINDOW
    last_error=None
    for attempt in range(len(_EMAXCONN_BACKOFF)+1):
        if attempt and monotonic()>retry_deadline:raise last_error
        try:return psycopg.connect(database_url,**opts)
        except psycopg.OperationalError as error:
            last_error=error
            message=str(error).lower()
            emaxconn="(emaxconn)" in message or "max client connections reached" in message
            if not emaxconn or attempt==len(_EMAXCONN_BACKOFF):raise
            if monotonic()>retry_deadline:raise
            sleep(_EMAXCONN_BACKOFF[attempt])
            if monotonic()>retry_deadline:raise
@contextmanager
def connection(settings):
    global _borrowers
    with _idle_lock:_borrowers+=1
    acquired=False;conn=None
    try:
        if not _slots.acquire(timeout=3): raise DatabaseBusy()
        acquired=True
        key=(settings.database_url,settings.environment)
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
        if settings.environment in {"preview","production"}: opts.update(sslmode="verify-full",sslrootcert=str(Path(__file__).parent/"certs"/"supabase-ca-2021.crt"))
        if conn is None:
            conn=_connect(settings.database_url,opts)
            created=monotonic()
        with schema_context(settings):yield conn
        # Only clean autocommit connections can cross request boundaries.
        if not conn.closed and conn.info.transaction_status==TransactionStatus.IDLE:
            with _idle_lock:
                if _borrowers>1 and len(_idle)<MAX_IDLE_CONNECTIONS:
                    _idle.append((key,conn,created,monotonic()))
                    conn=None
    finally:
        with _idle_lock:
            _borrowers-=1
            idle=list(_idle) if _borrowers==0 else []
            if idle:_idle.clear()
        for _,idle_conn,_,_ in idle:idle_conn.close()
        if conn is not None: conn.close()
        if acquired:_slots.release()
@contextmanager
def transaction(conn):
    with conn.transaction():
        conn.execute("set local statement_timeout='5000ms'; set local lock_timeout='1500ms'; set local idle_in_transaction_session_timeout='8000ms'")
        yield
def check_environment(conn,settings):
    expected=SCHEMA_BINDINGS.get(settings.environment)
    if not expected or (settings.schema_name,settings.app_role)!=expected: raise ConfigurationError("RUNTIME_SCHEMA_BINDING_INVALID")
    schema=settings.schema_name
    guard=conn.execute(f"""select g.*, current_user as connection_role,
      not exists(
        select 1 from unnest(%s::text[]) required(version)
        where not exists(select 1 from {schema}.schema_version s where s.version=required.version)
      ) as required_versions_present
      from {schema}.environment_guard g where singleton""",(list(REQUIRED_SCHEMA_VERSIONS),)).fetchone()
    if not guard or not guard["required_versions_present"]: raise ConfigurationError("DATABASE_NOT_PROVISIONED")
    if guard["environment"]!=settings.environment or guard["project_ref"]!=settings.project_ref or guard["schema_name"]!=settings.schema_name: raise ConfigurationError("DATABASE_GUARD_MISMATCH")
    if bool(guard["synthetic_only"])!=settings.synthetic_only: raise ConfigurationError("SYNTHETIC_GUARD_MISMATCH")
    if guard["connection_role"]!=settings.app_role: raise ConfigurationError("DATABASE_ROLE_MISMATCH")
    if settings.environment=="production":
        if guard.get("test_seed") is not False:raise ConfigurationError("PRODUCTION_GUARD_MISMATCH")
        def normalized(value,key):
            if key in {"campaign_opens_at","campaign_closes_at","claim_closes_at"}:
                try:
                    moment=value if isinstance(value,datetime) else datetime.fromisoformat(str(value))
                    if moment.tzinfo is None:return None
                    return moment.astimezone(timezone.utc).isoformat()
                except (TypeError,ValueError):return None
            return str(value)
        expected_guard={
          "launch_manifest_sha256":settings.launch_manifest_sha256,
          "campaign_id":settings.campaign_id,
          "event_enabled":settings.event_enabled,
          "campaign_opens_at":settings.campaign_opens_at,
          "campaign_closes_at":settings.campaign_closes_at,
          "claim_closes_at":settings.claim_closes_at,
          "draw_pool_total":settings.draw_pool_total,
          "draw_prize_quantity":settings.draw_prize_quantity,
          "ranking_prize_quantity":settings.ranking_prize_quantity,
          "unlimited_play":False,
          "synthetic_inventory":False,
          "shortened_clock":False,
        }
        if any(normalized(guard.get(key,""),key)!=normalized(value,key) for key,value in expected_guard.items()):
            raise ConfigurationError("PRODUCTION_GUARD_MISMATCH")
    del guard["connection_role"],guard["required_versions_present"]
    return guard
def check_business_environment(conn,settings):
    if settings.environment=="production":
        # The cutover tool takes the exclusive counterpart before changing the
        # guard. Hold this shared lock through dispatch and commit so a request
        # admitted before cutover cannot write afterward using a stale guard.
        conn.execute("select pg_advisory_xact_lock_shared(hashtext('dino-prod-cutover'))")
        return check_environment(conn,settings)
def rate_limits(conn,buckets,window=60):
    ordered=sorted(buckets)
    rows=conn.execute(f"select {database_schema()}.consume_rate_limit(k,n,%s) allowed from unnest(%s::text[],%s::integer[]) b(k,n)",(window,[k for k,_ in ordered],[n for _,n in ordered])).fetchall()
    return all(r["allowed"] for r in rows)
