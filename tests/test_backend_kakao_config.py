import os,sys,unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from config import ConfigurationError,Settings

BASE={"APP_ENV":"test","DATABASE_URL":"postgres://dino_dev_app@127.0.0.1:55433/postgres","SUPABASE_PROJECT_REF":"local","APP_BASE_URL":"http://127.0.0.1:3000","SUPABASE_URL":"http://127.0.0.1:54321","SESSION_TOKEN_PEPPER":"x"*32,"SUPABASE_PUBLISHABLE_KEY":"","GEMINI_BENEFIT_URL":"https://gemini.google.com/students"}

class KakaoConfigTest(unittest.TestCase):
    def test_optional_public_javascript_key(self):
        key="0123456789abcdef0123456789abcdef"
        with patch.dict(os.environ,{**BASE,"KAKAO_JAVASCRIPT_KEY":key},clear=True):settings=Settings.from_env()
        self.assertEqual(settings.kakao_javascript_key,key)
        self.assertEqual(settings.public()["share"],{"kakao_javascript_key":key,"webhook_enabled":False})
        with patch.dict(os.environ,BASE,clear=True):settings=Settings.from_env()
        self.assertEqual(settings.public()["share"],{"kakao_javascript_key":"","webhook_enabled":False})

    def test_webhook_is_publicly_enabled_only_with_both_keys_and_secrets_stay_private(self):
        key="0123456789abcdef0123456789abcdef";admin="abcdef0123456789abcdef0123456789"
        with patch.dict(os.environ,{**BASE,"KAKAO_JAVASCRIPT_KEY":key,"KAKAO_ADMIN_KEY":admin,"KAKAO_APP_ID":"123456"},clear=True):settings=Settings.from_env()
        self.assertEqual(settings.public()["share"],{"kakao_javascript_key":key,"webhook_enabled":True})
        self.assertNotIn(admin,str(settings.public()));self.assertNotIn("kakao_app_id",settings.public()["share"])

    def test_rejects_non_javascript_key_shapes(self):
        for key in ("short","sb_secret_"+"x"*32,"g"*32,"0"*31,"0"*33):
            with self.subTest(key=key),patch.dict(os.environ,{**BASE,"KAKAO_JAVASCRIPT_KEY":key},clear=True):
                with self.assertRaisesRegex(ConfigurationError,"KAKAO_JAVASCRIPT_KEY_INVALID"):Settings.from_env()

    def test_rejects_invalid_private_webhook_configuration(self):
        for name,value,error in (("KAKAO_ADMIN_KEY","short","KAKAO_ADMIN_KEY_INVALID"),("KAKAO_APP_ID","app-1","KAKAO_APP_ID_INVALID")):
            with self.subTest(name=name),patch.dict(os.environ,{**BASE,name:value},clear=True):
                with self.assertRaisesRegex(ConfigurationError,error):Settings.from_env()

if __name__=="__main__":unittest.main()
