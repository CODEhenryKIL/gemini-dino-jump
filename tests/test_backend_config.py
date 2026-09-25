import base64,json,os,sys,unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from config import ConfigurationError,Settings
def jwt(role):
    enc=lambda v:base64.urlsafe_b64encode(json.dumps(v).encode()).decode().rstrip("=")
    return enc({"alg":"none"})+"."+enc({"role":role})+".signature"
BASE={"APP_ENV":"test","DATABASE_URL":"postgres://dino_dev_app@127.0.0.1:55433/postgres","SUPABASE_PROJECT_REF":"local","APP_BASE_URL":"http://127.0.0.1:3000","SUPABASE_URL":"http://127.0.0.1:54321","SESSION_TOKEN_PEPPER":"x"*32,"SUPABASE_PUBLISHABLE_KEY":"","GEMINI_BENEFIT_URL":"https://gemini.google.com/students"}
class ConfigTest(unittest.TestCase):
    def test_cookie_period_is_bounded_and_public_config_safe(self):
        with patch.dict(os.environ,{**BASE,"PARTICIPANT_COOKIE_MAX_AGE_SECONDS":"3600","WEB_ANALYTICS_ENABLED":"true"},clear=True):settings=Settings.from_env()
        self.assertEqual(settings.participant_cookie_max_age,3600);self.assertTrue(settings.public()["web_analytics_enabled"]);self.assertNotIn("database_url",settings.public())
        with patch.dict(os.environ,{**BASE,"PARTICIPANT_COOKIE_MAX_AGE_SECONDS":"31536001"},clear=True):
            with self.assertRaises(ConfigurationError):Settings.from_env()
    def test_legacy_service_role_key_and_secret_key_are_rejected(self):
        preview={**BASE,"APP_ENV":"preview","DATABASE_URL":"postgres://dino_dev_app.igfrnexknwtiljdqjrbp:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres","SUPABASE_PROJECT_REF":"igfrnexknwtiljdqjrbp","APP_BASE_URL":"https://preview.example.com","SUPABASE_URL":"https://igfrnexknwtiljdqjrbp.supabase.co"}
        for key in (jwt("service_role"),"sb_secret_"+"x"*32):
            with patch.dict(os.environ,{**preview,"SUPABASE_PUBLISHABLE_KEY":key},clear=True):
                with self.assertRaises(ConfigurationError):Settings.from_env()
    def test_benefit_url_requires_exact_allowlisted_https_destination(self):
        for url in ("http://gemini.google.com/students","https://evil.example/students","https://gemini.google.com/students?token=secret","https://user@gemini.google.com/students"):
            with patch.dict(os.environ,{**BASE,"GEMINI_BENEFIT_URL":url},clear=True):
                with self.assertRaises(ConfigurationError):Settings.from_env()
    def test_preview_allows_exact_friendly_and_immutable_vercel_origins_without_wildcard(self):
        preview={**BASE,"APP_ENV":"preview","VERCEL_ENV":"preview","DATABASE_URL":"postgres://dino_dev_app.igfrnexknwtiljdqjrbp:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres","SUPABASE_PROJECT_REF":"igfrnexknwtiljdqjrbp","APP_BASE_URL":"https://google-korea-team-gemini.vercel.app","VERCEL_URL":"gemini-dino-jump-git-phase1-example.vercel.app","SUPABASE_URL":"https://igfrnexknwtiljdqjrbp.supabase.co","SUPABASE_PUBLISHABLE_KEY":"sb_publishable_"+"x"*32}
        with patch.dict(os.environ,preview,clear=True):settings=Settings.from_env()
        self.assertEqual(settings.allowed_origins,frozenset({"https://google-korea-team-gemini.vercel.app","https://gemini-dino-jump-git-phase1-example.vercel.app"}))
        self.assertFalse(any("*" in origin for origin in settings.allowed_origins))
        with patch.dict(os.environ,{**preview,"VERCEL_URL":"*.vercel.app"},clear=True):
            with self.assertRaises(ConfigurationError):Settings.from_env()
if __name__=="__main__":unittest.main()
