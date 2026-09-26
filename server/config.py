"""Fail-closed Phase 1 environment configuration."""
from dataclasses import dataclass,replace
import base64,json,os,re
from pathlib import Path
from urllib.parse import urlparse

ROOT=Path(__file__).resolve().parent.parent
CONSTANTS=json.loads((ROOT/"shared/game_constants.json").read_text(encoding="utf-8"))
REQUIRED_SCHEMA_VERSIONS=("20260925083548","20260925092759","20260925125939","20260925140902","20260926093414","20260926103809")
SCHEMA_VERSION=REQUIRED_SCHEMA_VERSIONS[-1]; SCHEMA_NAME="dino_dev"; APP_ROLE="dino_dev_app"
APPROVED_PREVIEW_PROJECT_REF="igfrnexknwtiljdqjrbp"
class ConfigurationError(RuntimeError): pass
def _origin(value,local=False):
    p=urlparse(value); http=local and p.scheme=="http" and p.hostname in {"127.0.0.1","localhost","::1"}
    if p.scheme!="https" and not http: raise ConfigurationError("HTTPS_ORIGIN_REQUIRED")
    if not p.hostname or "*" in p.hostname or p.username or p.password or p.query or p.fragment or p.path not in ("","/"): raise ConfigurationError("INVALID_ORIGIN")
    return value.rstrip("/")
@dataclass(frozen=True)
class Settings:
    environment:str; database_url:str; project_ref:str; base_url:str; benefit_url:str; supabase_url:str
    publishable_key:str; token_pepper:str; allowed_origins:frozenset[str]; deployment:str
    synthetic_only:bool=True; schema_name:str=SCHEMA_NAME; game_version:str=CONSTANTS["version"]
    participant_cookie_max_age:int=2592000; invite_active_ms:int=3000; web_analytics_enabled:bool=False
    preview_unlimited_play:bool=False; kakao_javascript_key:str=""
    @classmethod
    def from_env(cls):
        environment=os.getenv("APP_ENV","local")
        if environment not in {"local","test","preview"}: raise ConfigurationError("PRODUCTION_DISABLED")
        if os.getenv("VERCEL_ENV") and os.environ["VERCEL_ENV"]!=environment: raise ConfigurationError("VERCEL_ENV_MISMATCH")
        local=environment in {"local","test"}; project_ref=os.getenv("SUPABASE_PROJECT_REF","local" if local else "")
        if environment=="preview" and project_ref!=APPROVED_PREVIEW_PROJECT_REF: raise ConfigurationError("PREVIEW_PROJECT_NOT_APPROVED")
        database_url=os.getenv("DATABASE_URL",""); d=urlparse(database_url)
        if d.scheme not in {"postgres","postgresql"} or not d.hostname: raise ConfigurationError("POSTGRES_DATABASE_URL_REQUIRED")
        if local!=(d.hostname in {"localhost","127.0.0.1","::1"}): raise ConfigurationError("DATABASE_ENVIRONMENT_MISMATCH")
        if local and d.username!=APP_ROLE: raise ConfigurationError("APPLICATION_DB_ROLE_REQUIRED")
        if not local and (d.port!=6543 or not d.hostname.endswith(".pooler.supabase.com") or d.username!=f"{APP_ROLE}.{project_ref}"): raise ConfigurationError("SCOPED_TRANSACTION_POOLER_REQUIRED")
        base=_origin(os.getenv("APP_BASE_URL",f"https://{os.environ['VERCEL_URL']}" if os.getenv("VERCEL_URL") else "http://127.0.0.1:3000"),local)
        supabase=_origin(os.getenv("SUPABASE_URL","http://127.0.0.1:54321" if local else ""),local)
        if not local and urlparse(supabase).hostname!=f"{project_ref}.supabase.co": raise ConfigurationError("SUPABASE_PROJECT_MISMATCH")
        benefit=os.getenv("GEMINI_BENEFIT_URL","https://gemini.google.com/students"); b=urlparse(benefit)
        allowed_benefit_hosts={x.strip().lower() for x in os.getenv("GEMINI_BENEFIT_ALLOWED_HOSTS","gemini.google.com").split(",") if x.strip()}
        if b.scheme!="https" or b.hostname not in allowed_benefit_hosts or b.username or b.password or b.query or b.fragment or b.path.rstrip("/")!="/students": raise ConfigurationError("BENEFIT_URL_INVALID")
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
        platform_origin=_origin("https://"+os.environ["VERCEL_URL"],False) if environment=="preview" and os.getenv("VERCEL_URL") else None
        allowed=frozenset([base,*([platform_origin] if platform_origin else []),*(_origin(x.strip(),local) for x in os.getenv("ALLOWED_ORIGINS","").split(",") if x.strip())])
        try:cookie_age=int(os.getenv("PARTICIPANT_COOKIE_MAX_AGE_SECONDS","2592000"))
        except ValueError:raise ConfigurationError("COOKIE_MAX_AGE_INVALID") from None
        if not 3600<=cookie_age<=31536000:raise ConfigurationError("COOKIE_MAX_AGE_INVALID")
        analytics=os.getenv("WEB_ANALYTICS_ENABLED","false").lower()
        if analytics not in {"true","false"}:raise ConfigurationError("WEB_ANALYTICS_INVALID")
        unlimited=os.getenv("PREVIEW_UNLIMITED_PLAY","false").lower()
        if unlimited not in {"true","false"}:raise ConfigurationError("PREVIEW_UNLIMITED_PLAY_INVALID")
        kakao_key=os.getenv("KAKAO_JAVASCRIPT_KEY","").strip()
        if kakao_key and not re.fullmatch(r"[0-9a-fA-F]{32}",kakao_key): raise ConfigurationError("KAKAO_JAVASCRIPT_KEY_INVALID")
        return replace(cls(environment,database_url,project_ref,base,benefit,supabase,key,pepper,allowed,os.getenv("VERCEL_DEPLOYMENT_ID",os.getenv("VERCEL_GIT_COMMIT_SHA","local"))),participant_cookie_max_age=cookie_age,web_analytics_enabled=analytics=="true",preview_unlimited_play=unlimited=="true",kakao_javascript_key=kakao_key)
    def public(self):
        return {"environment":self.environment,"synthetic_only":False,"gameplay_synthetic_only":self.synthetic_only,"top3_contact_collection_enabled":True,"deployment":self.deployment,"web_analytics_enabled":self.web_analytics_enabled,"campaign":{"id":os.getenv("CAMPAIGN_ID","gemini_dino_phase1_test"),"game_version":self.game_version},"share":{"kakao_javascript_key":self.kakao_javascript_key},"benefit_url":self.benefit_url,"content_guides":[
            {"id":"study_note","title":"제미나이 노트북","description":"강의 자료 정리와 과제·시험 공부에 활용하는 공개 가이드", "url":"https://app.notion.com/p/3d41ef9d40cd803f9e56da74a08c695f?source=copy_link","available":True},
            {"id":"job_photo","title":"취업사진 프롬프트","description":"정장·배경을 선택해 취업사진을 만드는 프롬프트 안내", "url":"https://app.notion.com/p/3d01ef9d40cd80a798f1c353b8b4311d?source=copy_link","available":True}],"auth":{"supabase_url":self.supabase_url,"publishable_key":self.publishable_key},"limits":{"participant_cookie_max_age_seconds":self.participant_cookie_max_age,"invite_active_ms":self.invite_active_ms}}
