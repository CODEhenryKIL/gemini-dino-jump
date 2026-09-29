"""Fail-closed Phase 1 environment configuration."""
from dataclasses import dataclass,replace,field
from contextlib import contextmanager
from contextvars import ContextVar
import base64,hashlib,hmac,json,os,re
from datetime import datetime
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent.parent
CONSTANTS=json.loads((ROOT/"shared/game_constants.json").read_text(encoding="utf-8"))
REQUIRED_SCHEMA_VERSIONS=("20260925083548","20260925092759","20260925125939","20260925140902","20260926093414","20260926103809","20260926215000","20260927090000","20260927091037","20260927140000","20260928151903","20260929021923")
SCHEMA_VERSION=REQUIRED_SCHEMA_VERSIONS[-1]
SCHEMA_BINDINGS={
    "local":("dino_dev","dino_dev_app"),
    "test":("dino_dev","dino_dev_app"),
    "preview":("dino_dev","dino_dev_app"),
    "production":("dino_prod","dino_prod_app"),
}
# Compatibility aliases for migration tests and development tooling. Runtime code
# must use the binding stored on Settings instead of these development defaults.
SCHEMA_NAME,APP_ROLE=SCHEMA_BINDINGS["preview"]
_DATABASE_SCHEMA=ContextVar("dino_database_schema",default=SCHEMA_NAME)
def database_schema():
    return _DATABASE_SCHEMA.get()
@contextmanager
def schema_context(settings):
    expected=SCHEMA_BINDINGS.get(settings.environment)
    if expected!=(settings.schema_name,settings.app_role):raise ConfigurationError("RUNTIME_SCHEMA_BINDING_INVALID")
    token=_DATABASE_SCHEMA.set(settings.schema_name)
    try:yield
    finally:_DATABASE_SCHEMA.reset(token)
APPROVED_PREVIEW_PROJECT_REF="igfrnexknwtiljdqjrbp"
APPROVED_PRODUCTION_PROJECT_REF=APPROVED_PREVIEW_PROJECT_REF
PRODUCTION_MANIFEST_PATH=ROOT/"server"/"production-launch-manifest.json"
PRODUCTION_FLAGS={"unlimited_play":False,"synthetic_inventory":False,"shortened_clock":False}
PRODUCTION_POLICY_KEYS=("pool_exhaustion","unallocated_inventory_at_close","beta_data_migration","ranking_ties","finish_after_close","draw_and_ranking_double_award","eligibility_and_proof","claim_deadline_and_no_response","duplicate_person_claims","privacy_retention_and_deletion","operator_contact")
PRODUCTION_APPROVAL_KEYS=("environment","inventory","privacy","benefit_and_brand","public_launch")
PRODUCTION_EVIDENCE_KEYS=("target_db_and_backup","runtime_production_guard","inventory_reconciliation","real_kakao_game_and_draw","physical_device_qa","final_load_test","notion_and_benefit_links","rollback_rehearsal")
PRODUCTION_PREPARATION_APPROVAL_KEYS=("environment","inventory")
PRODUCTION_PREPARATION_EVIDENCE_KEYS=("target_db_and_backup","runtime_production_guard","inventory_reconciliation")
PRODUCTION_FAILURE_MARKERS=("FAILED","NOT_RUN","REJECTED","BLOCKED","SKIPPED","보류","미실행","실패")
PRODUCTION_LIMITATION_EVIDENCE_KEYS=frozenset(("physical_device_qa","final_load_test"))
class ConfigurationError(RuntimeError): pass

def ga4_public_config(environment, allowed_origins, base_url):
    """Optional telemetry fails closed without taking the game offline."""
    disabled={"enabled":False}
    if os.getenv("GA4_ENABLED","false").lower()!="true":return disabled
    if environment not in {"preview","production"}:return {**disabled,"disabled_reason":"ENVIRONMENT_NOT_ALLOWED"}
    production_id=os.getenv("GA4_PRODUCTION_MEASUREMENT_ID","").strip()
    test_id=os.getenv("GA4_TEST_MEASUREMENT_ID","").strip()
    measurement_id=production_id if environment=="production" else test_id
    if not re.fullmatch(r"G-[A-Z0-9]{6,20}",measurement_id):return {**disabled,"disabled_reason":"MEASUREMENT_ID_REQUIRED"}
    if not re.fullmatch(r"G-[A-Z0-9]{6,20}",production_id) or not re.fullmatch(r"G-[A-Z0-9]{6,20}",test_id) or production_id==test_id:
        return {**disabled,"disabled_reason":"SEPARATE_PROPERTIES_REQUIRED"}
    try:
        origins=sorted({_origin(value.strip()) for value in os.getenv("GA4_ALLOWED_ORIGINS","").split(",") if value.strip()})
    except (ConfigurationError,ValueError):return {**disabled,"disabled_reason":"ORIGIN_INVALID"}
    if not origins or base_url not in origins or not set(origins).issubset(allowed_origins):
        return {**disabled,"disabled_reason":"ORIGIN_NOT_APPROVED"}
    return {"enabled":True,"measurement_id":measurement_id,"property_environment":"production" if environment=="production" else "test","allowed_origins":origins,"debug_mode":environment=="preview" and os.getenv("GA4_DEBUG_MODE","false").lower()=="true"}
def _origin(value,local=False):
    p=urlparse(value); http=local and p.scheme=="http" and p.hostname in {"127.0.0.1","localhost","::1"}
    if p.scheme!="https" and not http: raise ConfigurationError("HTTPS_ORIGIN_REQUIRED")
    if not p.hostname or "*" in p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("","/"): raise ConfigurationError("INVALID_ORIGIN")
    return value.rstrip("/")

def _manifest_time(value):
    try:return datetime.fromisoformat(str(value))
    except (TypeError,ValueError):raise ConfigurationError("PRODUCTION_MANIFEST_INVALID") from None

def _manifest_entry_present(value):
    if not isinstance(value,str) or not value.strip():return False
    normalized=value.strip().upper()
    return normalized not in {"TODO","TBD","PENDING","UNDECIDED"} and not any(marker in normalized for marker in PRODUCTION_FAILURE_MARKERS)

def _structured_manifest_record(value,status,accepted_limit=False):
    if not isinstance(value,dict):return False
    details=all(isinstance(value.get(key),str) and value[key].strip() for key in ("detail","reference"))
    return details and (value.get("status")==status or (accepted_limit and value.get("status")=="ACCEPTED_LIMIT" and value.get("accepted_by")=="user"))

def _load_production_manifest():
    try:raw=PRODUCTION_MANIFEST_PATH.read_bytes(); manifest=json.loads(raw)
    except (OSError,json.JSONDecodeError):raise ConfigurationError("PRODUCTION_MANIFEST_REQUIRED") from None
    expected=os.getenv("PRODUCTION_MANIFEST_SHA256","").strip().lower()
    actual=hashlib.sha256(raw).hexdigest()
    if not re.fullmatch(r"[0-9a-f]{64}",expected) or not hmac.compare_digest(actual,expected):
        raise ConfigurationError("PRODUCTION_MANIFEST_HASH_MISMATCH")
    if manifest.get("status") not in {"DRAFT","APPROVED"} or not isinstance(manifest.get("event_enabled"),bool):
        raise ConfigurationError("PRODUCTION_MANIFEST_NOT_APPROVED")
    approvals=manifest.get("approvals") or {}; evidence=manifest.get("evidence") or {}
    policies=manifest.get("policies") or {}
    preparation_complete=(
        all(_manifest_entry_present(policies.get(key)) for key in PRODUCTION_POLICY_KEYS)
        and all(_manifest_entry_present(approvals.get(key)) or _structured_manifest_record(approvals.get(key),"APPROVED") for key in PRODUCTION_PREPARATION_APPROVAL_KEYS)
        and all(_manifest_entry_present(evidence.get(key)) or _structured_manifest_record(evidence.get(key),"VERIFIED") for key in PRODUCTION_PREPARATION_EVIDENCE_KEYS)
    )
    launch_complete=(
        manifest.get("status")=="APPROVED"
        and all(_structured_manifest_record(approvals.get(key),"APPROVED") for key in PRODUCTION_APPROVAL_KEYS)
        and all(_structured_manifest_record(evidence.get(key),"VERIFIED",key in PRODUCTION_LIMITATION_EVIDENCE_KEYS) for key in PRODUCTION_EVIDENCE_KEYS)
    )
    if not preparation_complete or (manifest["event_enabled"] and not launch_complete):
        raise ConfigurationError("PRODUCTION_MANIFEST_NOT_APPROVED")
    campaign=manifest.get("campaign") or {}; campaign_id=campaign.get("id")
    if not isinstance(campaign_id,str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9_-]{2,63}",campaign_id):
        raise ConfigurationError("PRODUCTION_MANIFEST_INVALID")
    opens_at=_manifest_time(campaign.get("opens_at")); closes_at=_manifest_time(campaign.get("closes_at")); claim_closes_at=_manifest_time(campaign.get("claim_closes_at"))
    if opens_at.tzinfo is None or closes_at.tzinfo is None or claim_closes_at.tzinfo is None or opens_at>=closes_at or closes_at>=claim_closes_at:
        raise ConfigurationError("PRODUCTION_MANIFEST_INVALID")
    if policies.get("finish_after_close")!="RECEIVED_BEFORE_CLOSE" or policies.get("claim_deadline_and_no_response")!="MANUAL_REVIEW_AFTER_DEADLINE" or policies.get("ranking_ties")!="EARLIER_ACHIEVEMENT_FIRST":
        raise ConfigurationError("PRODUCTION_MANIFEST_INVALID")
    draw_pool=manifest.get("draw_pool") or {}; draw_prizes=manifest.get("draw_prizes"); ranking_prizes=manifest.get("ranking_prizes")
    try:
        quantities=[item["quantity"] for item in [*draw_prizes,*ranking_prizes]]
        if not quantities or any(type(quantity) is not int or quantity<=0 for quantity in quantities):raise ValueError()
        draw_quantity=sum(item["quantity"] for item in draw_prizes)
        ranking_quantity=sum(item["quantity"] for item in ranking_prizes)
    except (TypeError,KeyError,ValueError):raise ConfigurationError("PRODUCTION_MANIFEST_INVALID") from None
    pool_values=(draw_pool.get("total_slots"),draw_pool.get("benefit_slots"),draw_pool.get("max_draws_per_participant"))
    if any(type(value) is not int for value in pool_values) or pool_values!=(5000,4937,10):
        raise ConfigurationError("PRODUCTION_MANIFEST_INVALID")
    if draw_quantity!=63 or ranking_quantity!=3 or manifest.get("production_flags")!=PRODUCTION_FLAGS:
        raise ConfigurationError("PRODUCTION_MANIFEST_INVALID")
    return manifest,actual,draw_quantity,ranking_quantity

@dataclass(frozen=True)
class Settings:
    environment:str; database_url:str; project_ref:str; base_url:str; benefit_url:str; supabase_url:str
    publishable_key:str; token_pepper:str; allowed_origins:frozenset[str]; deployment:str
    synthetic_only:bool=True; schema_name:str=SCHEMA_NAME; app_role:str=APP_ROLE; game_version:str=CONSTANTS["version"]
    campaign_id:str="gemini_dino_phase1_test"; event_enabled:bool=False; launch_manifest_sha256:str=""
    campaign_opens_at:str=""; campaign_closes_at:str=""; claim_closes_at:str=""; draw_pool_total:int=0; draw_prize_quantity:int=0; ranking_prize_quantity:int=0
    participant_cookie_max_age:int=2592000; invite_active_ms:int=3000; web_analytics_enabled:bool=False
    preview_unlimited_play:bool=False; kakao_javascript_key:str=""; kakao_admin_key:str=""; kakao_app_id:str=""
    ga4:dict=field(default_factory=lambda:{"enabled":False})
    @classmethod
    def from_env(cls):
        environment=os.getenv("APP_ENV","local")
        if environment not in SCHEMA_BINDINGS: raise ConfigurationError("ENVIRONMENT_INVALID")
        if os.getenv("VERCEL_ENV") and os.environ["VERCEL_ENV"]!=environment: raise ConfigurationError("VERCEL_ENV_MISMATCH")
        if environment=="production" and os.getenv("VERCEL_ENV")!="production": raise ConfigurationError("VERCEL_ENV_REQUIRED")
        local=environment in {"local","test"}; project_ref=os.getenv("SUPABASE_PROJECT_REF","local" if local else "")
        if environment=="preview" and project_ref!=APPROVED_PREVIEW_PROJECT_REF: raise ConfigurationError("PREVIEW_PROJECT_NOT_APPROVED")
        if environment=="production" and project_ref!=APPROVED_PRODUCTION_PROJECT_REF: raise ConfigurationError("PRODUCTION_PROJECT_NOT_APPROVED")
        schema_name,app_role=SCHEMA_BINDINGS[environment]
        database_url=os.getenv("DATABASE_URL",""); d=urlparse(database_url)
        if d.scheme not in {"postgres","postgresql"} or not d.hostname: raise ConfigurationError("POSTGRES_DATABASE_URL_REQUIRED")
        if local!=(d.hostname in {"localhost","127.0.0.1","::1"}): raise ConfigurationError("DATABASE_ENVIRONMENT_MISMATCH")
        if local and d.username!=app_role: raise ConfigurationError("APPLICATION_DB_ROLE_REQUIRED")
        if not local and (d.port!=6543 or not d.hostname.endswith(".pooler.supabase.com") or d.username!=f"{app_role}.{project_ref}"): raise ConfigurationError("SCOPED_TRANSACTION_POOLER_REQUIRED")
        base=_origin(os.getenv("APP_BASE_URL",f"https://{os.environ['VERCEL_URL']}" if os.getenv("VERCEL_URL") else "http://127.0.0.1:3000"),local)
        supabase=_origin(os.getenv("SUPABASE_URL","http://127.0.0.1:54321" if local else ""),local)
        if not local and urlparse(supabase).hostname!=f"{project_ref}.supabase.co": raise ConfigurationError("SUPABASE_PROJECT_MISMATCH")
        benefit=os.getenv("GEMINI_BENEFIT_URL","https://VQyu3J.s.gy/Game"); b=urlparse(benefit)
        allowed_benefit_hosts={x.strip().lower() for x in os.getenv("GEMINI_BENEFIT_ALLOWED_HOSTS","gemini.google.com").split(",") if x.strip()}
        valid_benefit_path=(b.hostname in allowed_benefit_hosts and b.path.rstrip("/")=="/students") or (b.hostname=="vqyu3j.s.gy" and b.path=="/Game")
        if b.scheme!="https" or not valid_benefit_path or b.port not in (None,443) or b.username or b.password or b.query or b.fragment: raise ConfigurationError("BENEFIT_URL_INVALID")
        key=os.getenv("SUPABASE_PUBLISHABLE_KEY","")
        if not local and not (re.fullmatch(r"sb_publishable_[A-Za-z0-9_-]{20,}",key) or key.count(".")==2): raise ConfigurationError("PUBLISHABLE_KEY_REQUIRED")
        if key.startswith("sb_secret_"): raise ConfigurationError("SECRET_KEY_PUBLIC")
        if key.count(".")==2:
            try:
                payload=json.loads(base64.urlsafe_b64decode(key.split(".")[1]+"="*(-len(key.split(".")[1])%4)))
                if payload.get("role")!="anon": raise ValueError()
            except (ValueError,TypeError,KeyError,json.JSONDecodeError): raise ConfigurationError("PUBLIC_KEY_ROLE_INVALID") from None
        pepper=os.getenv("SESSION_TOKEN_PEPPER","")
        if len(pepper)<32: raise ConfigurationError("TOKEN_PEPPER_REQUIRED")
        platform_origin=_origin("https://"+os.environ["VERCEL_URL"],False) if not local and os.getenv("VERCEL_URL") else None
        allowed=frozenset([base,*([platform_origin] if platform_origin else []),*(_origin(x.strip(),local) for x in os.getenv("ALLOWED_ORIGINS","").split(",") if x.strip())])
        try:cookie_age=int(os.getenv("PARTICIPANT_COOKIE_MAX_AGE_SECONDS","2592000"))
        except ValueError:raise ConfigurationError("COOKIE_MAX_AGE_INVALID") from None
        if not 3600<=cookie_age<=31536000:raise ConfigurationError("COOKIE_MAX_AGE_INVALID")
        analytics=os.getenv("WEB_ANALYTICS_ENABLED","false").lower()
        if analytics not in {"true","false"}:raise ConfigurationError("WEB_ANALYTICS_INVALID")
        unlimited=os.getenv("PREVIEW_UNLIMITED_PLAY","false").lower()
        if unlimited not in {"true","false"}:raise ConfigurationError("PREVIEW_UNLIMITED_PLAY_INVALID")
        if environment=="production" and unlimited!="false":raise ConfigurationError("PRODUCTION_UNLIMITED_PLAY_FORBIDDEN")
        kakao_key=os.getenv("KAKAO_JAVASCRIPT_KEY","").strip()
        if kakao_key and not re.fullmatch(r"[0-9a-fA-F]{32}",kakao_key): raise ConfigurationError("KAKAO_JAVASCRIPT_KEY_INVALID")
        kakao_admin_key=os.getenv("KAKAO_ADMIN_KEY","").strip()
        if kakao_admin_key and not re.fullmatch(r"[0-9a-fA-F]{32}",kakao_admin_key): raise ConfigurationError("KAKAO_ADMIN_KEY_INVALID")
        kakao_app_id=os.getenv("KAKAO_APP_ID","").strip()
        if kakao_app_id and not re.fullmatch(r"[1-9][0-9]{0,19}",kakao_app_id): raise ConfigurationError("KAKAO_APP_ID_INVALID")
        manifest={};manifest_hash="";draw_quantity=0;ranking_quantity=0
        if environment=="production":manifest,manifest_hash,draw_quantity,ranking_quantity=_load_production_manifest()
        campaign=manifest.get("campaign") or {}
        campaign_id=campaign.get("id") or os.getenv("CAMPAIGN_ID","gemini_dino_phase1_test")
        if environment=="production" and os.getenv("CAMPAIGN_ID",campaign_id)!=campaign_id:raise ConfigurationError("PRODUCTION_CAMPAIGN_MISMATCH")
        draw_pool=manifest.get("draw_pool") or {}
        return replace(cls(environment,database_url,project_ref,base,benefit,supabase,key,pepper,allowed,os.getenv("VERCEL_DEPLOYMENT_ID",os.getenv("VERCEL_GIT_COMMIT_SHA","local"))),synthetic_only=environment!="production",schema_name=schema_name,app_role=app_role,campaign_id=campaign_id,event_enabled=bool(manifest.get("event_enabled",False)),launch_manifest_sha256=manifest_hash,campaign_opens_at=str(campaign.get("opens_at") or ""),campaign_closes_at=str(campaign.get("closes_at") or ""),claim_closes_at=str(campaign.get("claim_closes_at") or ""),draw_pool_total=int(draw_pool.get("total_slots") or 0),draw_prize_quantity=draw_quantity,ranking_prize_quantity=ranking_quantity,participant_cookie_max_age=cookie_age,web_analytics_enabled=analytics=="true",preview_unlimited_play=unlimited=="true",kakao_javascript_key=kakao_key,kakao_admin_key=kakao_admin_key,kakao_app_id=kakao_app_id,ga4=ga4_public_config(environment,allowed,base))
    def public(self):
        return {"environment":self.environment,"synthetic_only":False,"gameplay_synthetic_only":self.synthetic_only,"top3_contact_collection_enabled":True,"deployment":self.deployment,"web_analytics_enabled":self.web_analytics_enabled,"ga4":self.ga4,"campaign":{"id":self.campaign_id,"game_version":self.game_version,"event_enabled":self.event_enabled},"share":{"kakao_javascript_key":self.kakao_javascript_key,"webhook_enabled":bool(self.kakao_javascript_key and self.kakao_admin_key)},"benefit_url":self.benefit_url,"content_guides":[
            {"id":"study_note","title":"4년 평점 4.26의 제미나이 공부법","description":"강의 자료 정리와 과제·시험 공부에 활용하는 공개 가이드", "url":"https://app.notion.com/p/3d41ef9d40cd803f9e56da74a08c695f?source=copy_link","available":True},
            {"id":"job_photo","title":"취업 사진 제미나이로 만드는 비법","description":"정장·배경을 선택해 취업사진을 만드는 프롬프트 안내", "url":"https://app.notion.com/p/3d01ef9d40cd80a798f1c353b8b4311d?source=copy_link","available":True}],"auth":{"supabase_url":self.supabase_url,"publishable_key":self.publishable_key},"limits":{"participant_cookie_max_age_seconds":self.participant_cookie_max_age,"invite_active_ms":self.invite_active_ms}}
