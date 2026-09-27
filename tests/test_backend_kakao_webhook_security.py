import sys,unittest
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
import app
from operations import DomainError

class KakaoWebhookHeaderSecurityTest(unittest.TestCase):
    def setUp(self):
        self.settings=SimpleNamespace(kakao_admin_key="a"*32)
        self.valid={"Authorization":"KakaoAK "+"a"*32,"X-Kakao-Resource-ID":"resource-1","User-Agent":"KakaoOpenAPI/1.0"}

    def test_exact_headers_are_accepted(self):
        self.assertEqual(app.verify_kakao_webhook_headers(self.valid,self.settings),"resource-1")

    def test_missing_wrong_and_non_ascii_authorization_fail_closed(self):
        for authorization in ("","KakaoAK "+"b"*32,"KakaoAK "+"가"*16):
            with self.subTest(authorization=authorization),self.assertRaises(DomainError) as caught:
                app.verify_kakao_webhook_headers({**self.valid,"Authorization":authorization},self.settings)
            self.assertEqual((caught.exception.code,caught.exception.status),("WEBHOOK_UNAUTHORIZED",401))

    def test_absent_server_secret_disables_webhook(self):
        with self.assertRaises(DomainError) as caught:
            app.verify_kakao_webhook_headers(self.valid,SimpleNamespace(kakao_admin_key=""))
        self.assertEqual((caught.exception.code,caught.exception.status),("SHARE_WEBHOOK_UNAVAILABLE",503))

if __name__=="__main__":unittest.main()
