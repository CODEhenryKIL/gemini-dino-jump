"""Dino Jump HTTP transport for local use and Vercel Python Functions."""
from http.cookies import SimpleCookie
from http.server import SimpleHTTPRequestHandler,ThreadingHTTPServer
from urllib.parse import parse_qs,urlencode,urlparse
import datetime as dt
import hashlib,hmac,json,os,re,secrets,sys,time,uuid
sys.path.insert(0,os.path.dirname(__file__))
import auth,db,game_verifier,observability,share_page
from config import CONSTANTS,ROOT,ConfigurationError,Settings,database_schema
from operations import DomainError,dispatch
import psycopg

PUBLIC_DIR=str(ROOT/"public"); MAX_BODY=65536
LEGACY_PATHS={"/gate-runner","/gate-runner/","/gate_runner.html"}
KAKAO_WEBHOOK_PATH="/api/webhooks/kakao-share"
def parse_query(query):
    try:return parse_qs(query,max_num_fields=20)
    except ValueError:raise DomainError("INVALID_QUERY","주소의 요청 항목이 너무 많습니다.") from None
def verify_kakao_webhook_headers(headers,settings):
    if not settings.kakao_admin_key:raise DomainError("SHARE_WEBHOOK_UNAVAILABLE","카카오톡 전송 확인 연결을 준비하고 있습니다.",503,True)
    expected="KakaoAK "+settings.kakao_admin_key;actual=headers.get("Authorization","")
    try:actual_bytes=actual.encode("ascii")
    except UnicodeEncodeError:raise DomainError("WEBHOOK_UNAUTHORIZED","웹훅 인증이 올바르지 않습니다.",401) from None
    expected_bytes=expected.encode("ascii")
    if len(actual_bytes)!=len(expected_bytes) or not hmac.compare_digest(actual_bytes,expected_bytes):raise DomainError("WEBHOOK_UNAUTHORIZED","웹훅 인증이 올바르지 않습니다.",401)
    resource_id=headers.get("X-Kakao-Resource-ID","")
    if not re.fullmatch(r"[\x21-\x7e]{1,128}",resource_id):raise DomainError("INVALID_WEBHOOK","웹훅 요청 식별값이 올바르지 않습니다.")
    if headers.get("User-Agent","")!="KakaoOpenAPI/1.0":raise DomainError("INVALID_WEBHOOK","웹훅 발신 정보가 올바르지 않습니다.")
    return resource_id
def _json_default(value):
    if isinstance(value,(dt.datetime,dt.date)):return value.isoformat()
    if isinstance(value,uuid.UUID):return str(value)
    raise TypeError("not JSON serializable")
class DinoJumpHandler(SimpleHTTPRequestHandler):
    def __init__(self,*args,**kwargs):self.request_id=str(uuid.uuid4());self.cors_origin=None;self.pending_cookie=None;self.response_status=500;super().__init__(*args,directory=PUBLIC_DIR,**kwargs)
    def log_message(self,fmt,*args):pass
    def end_headers(self):
        self.send_header("X-Content-Type-Options","nosniff");self.send_header("Referrer-Policy","strict-origin");self.send_header("X-Frame-Options","DENY");self.send_header("Permissions-Policy","camera=(), microphone=(), geolocation=()")
        super().end_headers()
    def send_json(self,status,data):
        self.response_status=status
        encoded=json.dumps(data,ensure_ascii=False,allow_nan=False,default=_json_default).encode()
        self.send_response(status);self.send_header("Content-Type","application/json; charset=utf-8");self.send_header("Content-Length",str(len(encoded)));self.send_header("Cache-Control","private, no-store");self.send_header("Vary","Origin, Authorization, Cookie");self.send_header("X-Request-ID",self.request_id)
        if self.cors_origin:self.send_header("Access-Control-Allow-Origin",self.cors_origin);self.send_header("Access-Control-Allow-Credentials","true")
        if self.pending_cookie:self.send_header("Set-Cookie",self.pending_cookie)
        if status in (429,503):self.send_header("Retry-After","5")
        self.end_headers()
        if self.command!="HEAD":self.wfile.write(encoded)
    def fail(self,error):self.send_json(error.status,{"error":error.code,"message":error.message,"retryable":error.retryable,"request_id":self.request_id})
    def parse_body(self):
        if self.headers.get("Transfer-Encoding"):raise DomainError("INVALID_BODY","요청 형식을 확인해 주세요.")
        try:length=int(self.headers.get("Content-Length","0"))
        except ValueError:raise DomainError("INVALID_BODY","요청 크기를 확인해 주세요.") from None
        if not 0<=length<=MAX_BODY:raise DomainError("BODY_TOO_LARGE","요청 데이터가 너무 큽니다.",413)
        if not length:return {}
        if self.headers.get_content_type()!="application/json":raise DomainError("JSON_REQUIRED","JSON 요청이 필요합니다.",415)
        try:value=json.loads(self.rfile.read(length),parse_constant=lambda _x:(_ for _ in ()).throw(ValueError()))
        except (ValueError,UnicodeDecodeError):raise DomainError("INVALID_JSON","요청 데이터를 확인해 주세요.") from None
        if not isinstance(value,dict):raise DomainError("INVALID_BODY","요청 데이터는 객체여야 합니다.")
        return value
    def _origin(self,settings):
        origin=self.headers.get("Origin")
        if origin:
            if origin not in settings.allowed_origins:raise DomainError("ORIGIN_DENIED","허용되지 않은 요청 출처입니다.",403)
            self.cors_origin=origin
        if self.command in {"POST","PATCH"} and self.headers.get("Sec-Fetch-Site")=="cross-site":raise DomainError("ORIGIN_DENIED","허용되지 않은 요청 출처입니다.",403)
    def _cookie(self):
        raw=self.headers.get("Cookie","")
        if len(raw)>4096:raise DomainError("SESSION_INVALID","참가자 인증이 올바르지 않습니다.",401)
        jar=SimpleCookie()
        try:jar.load(raw)
        except Exception:raise DomainError("SESSION_INVALID","참가자 인증이 올바르지 않습니다.",401) from None
        name=getattr(self,"participant_cookie_name","dj_session")
        return jar[name].value if name in jar else ""
    def _bearer(self):
        value=self.headers.get("Authorization","")
        if not value:return ""
        if not value.startswith("Bearer ") or len(value)>8200:raise DomainError("ADMIN_AUTH_REQUIRED","관리자 로그인이 필요합니다.",401)
        return value[7:]
    def _ip_subject(self,settings):
        address=self.client_address[0] if self.client_address else "local"
        if os.getenv("VERCEL"):address=self.headers.get("x-vercel-forwarded-for",address).split(",")[0].strip()
        return auth.token_hash(address,settings.token_pepper)
    def _rate(self,conn,settings,path,participant):
        ip=self._ip_subject(settings);limit=240 if path=="/api/participants/anonymous" else 90 if path.startswith("/api/admin/") else 30 if any(x in path for x in ("finish","draws","referrals","claims")) else 180
        subject=participant or ip
        if not db.rate_limits(conn,[("ip:"+ip,12000),("route:"+path+":"+subject,limit)]):raise DomainError("RATE_LIMITED","요청이 많습니다. 잠시 뒤 다시 시도해 주세요.",429,True)
    def _set_participant_cookie(self,token,settings):
        secure="; Secure" if settings.environment in {"preview","production"} else ""
        name="dj_production_session" if settings.environment=="production" else "dj_session"
        self.pending_cookie=f"{name}={token}; Path=/; Max-Age={settings.participant_cookie_max_age}; HttpOnly; SameSite=Lax{secure}"
    def _context(self,settings,body,path):
        self.participant_cookie_name="dj_production_session" if settings.environment=="production" else "dj_session"
        raw_cookie=self._cookie();participant_hash=auth.token_hash(raw_cookie,settings.token_pepper) if raw_cookie else ""
        ctx={"environment":settings.environment,"deployment":settings.deployment,"event_version":"phase2-v1","game_version":settings.game_version,"base_url":settings.base_url,"project_ref":settings.project_ref,"participant_token_hash":participant_hash,"request_id":self.request_id,"invite_active_ms":settings.invite_active_ms,"participant_cookie_max_age":settings.participant_cookie_max_age,"ip_subject":self._ip_subject(settings),"preview_unlimited_play":settings.preview_unlimited_play,"share_webhook_enabled":bool(settings.kakao_javascript_key and settings.kakao_admin_key),"kakao_app_id":settings.kakao_app_id}
        idem=self.headers.get("Idempotency-Key","")
        if idem:
            if not re.fullmatch(r"[\x21-\x7e]{8,128}",idem):raise DomainError("INVALID_IDEMPOTENCY_KEY","요청 식별자를 확인해 주세요.")
            ctx["idempotency_key"]=idem
        if path=="/api/observations":
            event_id=str(body.get("event_id") or "");bootstrap=hmac.new(settings.token_pepper.encode(),("bootstrap:"+event_id+":"+idem).encode(),hashlib.sha256).hexdigest()
            ctx.update(bootstrap_token=bootstrap,bootstrap_token_hash=auth.token_hash(bootstrap,settings.token_pepper))
        if path=="/api/participants/anonymous":
            bootstrap=str(body.get("bootstrap_token") or "")
            if bootstrap:
                raw=auth.deterministic_participant_token(bootstrap,settings.token_pepper)
                ctx.update(bootstrap_token_hash=auth.token_hash(bootstrap,settings.token_pepper),new_participant_token=raw,new_participant_token_hash=auth.token_hash(raw,settings.token_pepper))
            nonce=secrets.token_urlsafe(32);ctx.update(invite_nonce=nonce,invite_nonce_hash=auth.token_hash(nonce,settings.token_pepper))
        if path=="/api/referrals/qualify":
            raw=str(body.get("visit_nonce") or "");ctx["visit_nonce_hash"]=auth.token_hash(raw,settings.token_pepper) if raw else ""
        if path=="/api/referrals/share-intents":
            raw=secrets.token_urlsafe(32);ctx.update(new_share_callback_token=raw,new_share_callback_token_hash=auth.token_hash(raw,settings.token_pepper))
        return ctx
    def _api(self):
        started=time.monotonic();route_template="/api/unknown";error_code=None;deployment="unknown";database_failure=None;environment="unknown";campaign_id="unknown";method=self.command;log_method=self.command;operation_outcome=None
        try:
            parsed=urlparse(self.path)
            if len(self.path)>2048:raise DomainError("URL_TOO_LONG","요청 주소가 너무 깁니다.",414)
            path=parsed.path;route_template=observability.normalize_route(path);method="GET" if self.command=="HEAD" else self.command;query={k:v[-1] for k,v in parse_query(parsed.query).items()};body=self.parse_body() if method in {"POST","PATCH"} else {}
            # Accept a completion only after the full request body has arrived.
            received_at=dt.datetime.now(dt.timezone.utc)
            if method=="GET" and path=="/api/shared/game_constants.json":self.send_json(200,CONSTANTS);return
            settings=Settings.from_env();deployment=settings.deployment;environment=settings.environment;campaign_id=settings.campaign_id
            is_kakao_webhook=path==KAKAO_WEBHOOK_PATH
            if not is_kakao_webhook:self._origin(settings)
            elif method not in {"GET","POST"}:raise DomainError("NOT_FOUND","요청한 API를 찾을 수 없습니다.",404)
            if is_kakao_webhook and method=="GET":body=query
            if method=="OPTIONS":
                self.response_status=204;self.send_response(204);self.send_header("Access-Control-Allow-Methods","GET, POST, PATCH, OPTIONS");self.send_header("Access-Control-Allow-Headers","Content-Type, Authorization, Idempotency-Key");self.send_header("Access-Control-Max-Age","600")
                if self.cors_origin:self.send_header("Access-Control-Allow-Origin",self.cors_origin);self.send_header("Access-Control-Allow-Credentials","true")
                self.end_headers();return
            if is_kakao_webhook:
                resource_id=verify_kakao_webhook_headers(self.headers,settings);callback_token=str(body.get("callback_token") or "")
                ctx={"environment":settings.environment,"deployment":settings.deployment,"event_version":"phase2-v1","game_version":settings.game_version,"base_url":settings.base_url,"project_ref":settings.project_ref,"request_id":self.request_id,"preview_unlimited_play":settings.preview_unlimited_play,"kakao_webhook_verified":True,"kakao_resource_id":resource_id,"share_callback_token_hash":auth.token_hash(callback_token,settings.token_pepper),"kakao_app_id":settings.kakao_app_id}
                token=""
            else:token=self._bearer();ctx=self._context(settings,body,path)
            ctx["request_received_at"]=received_at
            ctx["event_enabled"]=settings.event_enabled
            is_admin=path.startswith("/api/admin/")
            if is_admin:
                if not token:raise DomainError("ADMIN_AUTH_REQUIRED","관리자 로그인이 필요합니다.",401)
                with db.connection(settings) as conn:
                    with db.transaction(conn):db.check_environment(conn,settings);self._rate(conn,settings,path,"")
                ctx["admin_user_id"]=auth.verify_admin_identity(token,settings)
            with db.connection(settings) as conn:
                with db.transaction(conn):guard=db.check_environment(conn,settings)
                ctx["campaign_id"]=guard["campaign_id"];campaign_id=guard["campaign_id"]
                if method=="GET" and path=="/api/health":
                    self.send_json(200,observability.health_snapshot(conn,settings,guard,database_schema()));return
                if method=="GET" and path=="/api/config":
                    config_row=conn.execute(f"select campaign.id,campaign.title,campaign.status,campaign.game_version,campaign.opens_at,campaign.closes_at,clock_timestamp() server_time from (select 1) clock left join {database_schema()}.campaign on campaign.id=%s",(guard["campaign_id"],)).fetchone();data=settings.public();campaign=dict(config_row);data["server_time"]=campaign.pop("server_time");data["campaign"].update(campaign if campaign.get("id") else {});data["campaign"]["game_version"]=settings.game_version;self.send_json(200,data);return
                if not is_admin and not is_kakao_webhook:
                    with db.transaction(conn):self._rate(conn,settings,path,ctx.get("participant_token_hash",""))
                if method=="POST" and re.fullmatch(r"/api/game-sessions/[^/]+/finish",path):
                    sid=path.split("/")[-2];session=conn.execute(f"select seed,version from {database_schema()}.game_session where id=%s and participant_id=(select id from {database_schema()}.participant where token_hash=%s)",(sid,ctx.get("participant_token_hash"))).fetchone()
                    if not session:raise DomainError("SESSION_NOT_FOUND","게임 기록을 찾을 수 없습니다.",404)
                    if body.get("version",session["version"])!=session["version"]:raise DomainError("GAME_VERSION_MISMATCH","게임 버전이 일치하지 않습니다.",409)
                    try:ctx["verification"]=game_verifier.verify_game(session["version"],session["seed"],body.get("jump_ticks",[]),body.get("score"),body.get("ticks",body.get("valid_ticks")))
                    except (TypeError,ValueError,KeyError):raise DomainError("INVALID_GAME_INPUT","게임 기록 형식을 확인해 주세요.") from None
                with db.transaction(conn):
                    if is_kakao_webhook:conn.execute("set local statement_timeout='2500ms'")
                    status,response=dispatch(conn,method,path,body,query,ctx)
            cookie=response.pop("_set_cookie_token",None)
            if cookie:self._set_participant_cookie(cookie,settings)
            if status>=400 and isinstance(response,dict):error_code=response.get("error")
            operation_outcome=observability.operation_outcome(route_template,status,response)
            self.send_json(status,response)
        except DomainError as error:error_code=error.code;self.fail(error)
        except auth.AuthenticationError:error_code="ADMIN_AUTH_REQUIRED";self.fail(DomainError(error_code,"관리자 로그인이 필요합니다.",401))
        except auth.AuthenticationUnavailable:error_code="AUTH_UNAVAILABLE";self.fail(DomainError(error_code,"관리자 인증 연결을 확인해 주세요.",503,True))
        except (ConfigurationError,db.DatabaseBusy,observability.HealthCheckFailed,psycopg.Error) as error:
            database_failure="pool_wait" if isinstance(error,db.DatabaseBusy) else "configuration" if isinstance(error,ConfigurationError) else "health_check" if isinstance(error,observability.HealthCheckFailed) else (error.sqlstate or "connection")
            error_code="SERVICE_UNAVAILABLE";self.fail(DomainError(error_code,"서비스 연결을 확인하고 있습니다.",503,True))
        except (BrokenPipeError,ConnectionResetError):pass
        except Exception:error_code="INTERNAL_ERROR";self.fail(DomainError(error_code,"요청을 처리하지 못했습니다.",500,True))
        finally:
            sys.stderr.write(observability.serialize(observability.request_log(environment=environment,campaign=campaign_id,deployment=deployment,route=route_template,method=log_method,status=self.response_status,duration_ms=(time.monotonic()-started)*1000,request_id=self.request_id,error_code=error_code,database_failure=database_failure,operation=operation_outcome)))
    def _share(self):
        try:
            parsed=urlparse(self.path)
            if len(self.path)>2048:raise ValueError()
            incoming=parse_query(parsed.query)
            code=parsed.path.rsplit("/",1)[-1] if parsed.path.startswith("/invite/") else (incoming.get("code") or [""])[-1]
            target=share_page.share_target(code,incoming)
            settings=Settings.from_env()
            card=share_page.DEFAULT_CARD
            if target["link"] in share_page.KINDS:
                with db.connection(settings) as conn:
                    with db.transaction(conn):
                        guard=db.check_environment(conn,settings)
                        card=share_page.public_card(conn,code,target["link"],settings.game_version,guard["campaign_id"])
            encoded=share_page.render_share_page(card,settings.base_url,code,target)
            self.send_response(200);self.send_header("Content-Type","text/html; charset=utf-8");self.send_header("Content-Length",str(len(encoded)))
            self.send_header("Cache-Control","no-store");self.end_headers()
            if self.command!="HEAD":self.wfile.write(encoded)
        except DomainError as error:self.fail(error)
        except ValueError:self.send_error(404)
        except (ConfigurationError,db.DatabaseBusy,psycopg.Error):self.send_error(503,"Preview unavailable")
    def _static(self):
        path=urlparse(self.path).path
        if path in LEGACY_PATHS:
            self.send_response(302);self.send_header('Location', '/');self.send_header("Cache-Control","no-store");self.end_headers();return
        if path.startswith("/invite/"):return self._share()
        return super().do_HEAD() if self.command=="HEAD" else super().do_GET()
    def do_GET(self):
        path=urlparse(self.path).path
        if path=="/api/index.py":
            try:share_preview=parse_query(urlparse(self.path).query).get("share_preview")==["1"]
            except DomainError as error:return self.fail(error)
            if share_preview:return self._share()
        if path=="/api/share":return self._share()
        return self._api() if path.startswith("/api/") else self._static()
    def do_HEAD(self):return self.do_GET()
    def do_POST(self):return self._api()
    def do_PATCH(self):return self._api()
    def do_OPTIONS(self):return self._api()
def run_server():
    server=ThreadingHTTPServer(("127.0.0.1",int(os.getenv("PORT","3000"))),DinoJumpHandler)
    try:server.serve_forever()
    except KeyboardInterrupt:pass
    finally:server.server_close()
if __name__=="__main__":run_server()
