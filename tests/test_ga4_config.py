import os, sys, unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0,str(Path(__file__).resolve().parents[1]/"server"))
from config import ga4_public_config

ORIGIN="https://google-korea-team-gemini.vercel.app"
VALUES={"GA4_ENABLED":"true","GA4_TEST_MEASUREMENT_ID":"G-TEST123456","GA4_PRODUCTION_MEASUREMENT_ID":"G-PROD123456","GA4_ALLOWED_ORIGINS":ORIGIN,"GA4_DEBUG_MODE":"true"}

class GA4ConfigTest(unittest.TestCase):
    def config(self, environment="preview", **changes):
        with patch.dict(os.environ,{**VALUES,**changes},clear=True):
            return ga4_public_config(environment,frozenset({ORIGIN}),ORIGIN)

    def test_property_selected_by_runtime_and_debug_never_production(self):
        preview=self.config();production=self.config("production")
        self.assertEqual(preview["measurement_id"],"G-TEST123456")
        self.assertEqual(preview["property_environment"],"test")
        self.assertTrue(preview["debug_mode"])
        self.assertEqual(production["measurement_id"],"G-PROD123456")
        self.assertFalse(production["debug_mode"])

    def test_local_and_load_test_collection_disabled(self):
        for environment in ("local","test"):
            self.assertFalse(self.config(environment)["enabled"])

    def test_invalid_config_disables_only_analytics(self):
        for overrides in ({"GA4_ENABLED":"false"},{"GA4_TEST_MEASUREMENT_ID":""},{"GA4_TEST_MEASUREMENT_ID":"javascript:secret"},{"GA4_PRODUCTION_MEASUREMENT_ID":"G-TEST123456"},{"GA4_ALLOWED_ORIGINS":""},{"GA4_ALLOWED_ORIGINS":ORIGIN+",https://evil.example"},{"GA4_ALLOWED_ORIGINS":ORIGIN+"?invite=secret"},{"GA4_ALLOWED_ORIGINS":"https://*.vercel.app"}):
            with self.subTest(overrides=overrides):
                value=self.config(**overrides)
                self.assertFalse(value["enabled"])
                self.assertNotIn("measurement_id",value)

    def test_public_config_has_no_other_measurement_id_or_secret(self):
        self.assertNotIn("G-PROD123456",str(self.config()))

    def test_production_requires_separate_test_property(self):
        self.assertFalse(self.config("production",GA4_TEST_MEASUREMENT_ID="")["enabled"])

if __name__=="__main__":unittest.main()
