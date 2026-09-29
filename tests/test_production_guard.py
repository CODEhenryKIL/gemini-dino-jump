import hashlib,json,os,sys,tempfile,unittest
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"server"))
import config,db

PROJECT="igfrnexknwtiljdqjrbp"
PRODUCTION_BASE={
    "APP_ENV":"production","VERCEL_ENV":"production",
    "DATABASE_URL":f"postgres://dino_prod_app.{PROJECT}:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres",
    "SUPABASE_PROJECT_REF":PROJECT,
    "APP_BASE_URL":"https://google-korea-team-gemini.vercel.app",
    "SUPABASE_URL":f"https://{PROJECT}.supabase.co",
    "SESSION_TOKEN_PEPPER":"x"*32,
    "SUPABASE_PUBLISHABLE_KEY":"sb_publishable_"+"x"*32,
    "GEMINI_BENEFIT_URL":"https://gemini.google.com/students",
    "PREVIEW_UNLIMITED_PLAY":"false",
}

def approved_manifest(event_enabled=False):
    manifest={
      "version":"phase3-production-test","status":"APPROVED","event_enabled":event_enabled,
      "campaign":{"id":"gemini_dino_2026","opens_at":"2026-09-29T19:00:00+09:00","closes_at":"2026-10-03T00:00:00+09:00","claim_closes_at":"2026-10-04T00:00:00+09:00"},
      "draw_pool":{"total_slots":5000,"benefit_slots":4923,"max_draws_per_participant":10,"mode":"WITHOUT_REPLACEMENT"},
      "draw_prizes":[{"id":"all-draw-prizes","quantity":77}],
      "ranking_prizes":[{"rank":1,"quantity":1},{"rank":2,"quantity":1},{"rank":3,"quantity":1}],
      "approvals":{"environment":"approved","inventory":"approved","privacy":"approved","benefit_and_brand":"approved","public_launch":"approved"},
      "policies":{key:"approved" for key in config.PRODUCTION_POLICY_KEYS} | {"ranking_ties":"EARLIER_ACHIEVEMENT_FIRST","finish_after_close":"RECEIVED_BEFORE_CLOSE","claim_deadline_and_no_response":"MANUAL_REVIEW_AFTER_DEADLINE"},
      "evidence":{key:"verified" for key in config.PRODUCTION_EVIDENCE_KEYS},
      "production_flags":{"unlimited_play":False,"synthetic_inventory":False,"shortened_clock":False},
    }
    if event_enabled:
        manifest["approvals"]={key:{"status":"APPROVED","detail":"reviewed","reference":"test://approval"} for key in config.PRODUCTION_APPROVAL_KEYS}
        manifest["evidence"]={key:{"status":"VERIFIED","detail":"checked","reference":"test://evidence"} for key in config.PRODUCTION_EVIDENCE_KEYS}
    return manifest

class FakeResult:
    def __init__(self,row):self.row=row
    def fetchone(self):return self.row

class FakeConnection:
    def __init__(self,row):self.row=row;self.query=None;self.params=None
    def execute(self,query,params):
        self.query=query;self.params=params
        row={**self.row,"required_versions_present":set(params[0]).issubset(config.REQUIRED_SCHEMA_VERSIONS)}
        return FakeResult(row)

class ProductionConfigTest(unittest.TestCase):
    def settings(self,manifest=None,env=None):
        payload=json.dumps(manifest or approved_manifest(),ensure_ascii=False,separators=(",",":")).encode()
        temporary=tempfile.NamedTemporaryFile(delete=False)
        self.addCleanup(lambda:Path(temporary.name).unlink(missing_ok=True))
        temporary.write(payload);temporary.close()
        values={**PRODUCTION_BASE,"PRODUCTION_MANIFEST_SHA256":hashlib.sha256(payload).hexdigest(),**(env or {})}
        with patch.object(config,"PRODUCTION_MANIFEST_PATH",Path(temporary.name)),patch.dict(os.environ,values,clear=True):
            return config.Settings.from_env()

    def test_production_uses_separate_schema_role_and_approved_manifest(self):
        settings=self.settings()
        self.assertEqual((settings.schema_name,settings.app_role),("dino_prod","dino_prod_app"))
        self.assertFalse(settings.synthetic_only);self.assertFalse(settings.preview_unlimited_play)
        self.assertEqual((settings.draw_pool_total,settings.draw_prize_quantity,settings.ranking_prize_quantity),(5000,77,3))
        self.assertFalse(settings.event_enabled)

    def test_production_rejects_beta_role_unlimited_mode_and_unapproved_manifest(self):
        cases=(
          ({"DATABASE_URL":f"postgres://dino_dev_app.{PROJECT}:pw@aws-0-ap-northeast-2.pooler.supabase.com:6543/postgres"},approved_manifest(),"SCOPED_TRANSACTION_POOLER_REQUIRED"),
          ({"PREVIEW_UNLIMITED_PLAY":"true"},approved_manifest(),"PRODUCTION_UNLIMITED_PLAY_FORBIDDEN"),
        )
        for env,manifest,error in cases:
            with self.subTest(error=error),self.assertRaisesRegex(config.ConfigurationError,error):self.settings(manifest,env)

    def test_production_requires_vercel_production_and_exact_manifest_hash(self):
        with self.assertRaisesRegex(config.ConfigurationError,"VERCEL_ENV_REQUIRED"):self.settings(env={"VERCEL_ENV":""})
        with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_HASH_MISMATCH"):
            self.settings(env={"PRODUCTION_MANIFEST_SHA256":"0"*64})

    def test_paused_draft_accepts_preparation_gates_but_active_requires_launch_gates(self):
        paused=approved_manifest()
        paused["status"]="DRAFT"
        paused["approvals"]["privacy"]=None
        paused["approvals"]["benefit_and_brand"]=None
        paused["approvals"]["public_launch"]=None
        paused["evidence"]["physical_device_qa"]=None
        self.assertFalse(self.settings(paused).event_enabled)
        paused["event_enabled"]=True
        with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_NOT_APPROVED"):
            self.settings(paused)

    def test_active_manifest_with_all_launch_gates_is_accepted(self):
        settings=self.settings(approved_manifest(event_enabled=True))
        self.assertTrue(settings.event_enabled)

    def test_active_manifest_rejects_free_text_and_failed_structured_gates(self):
        for group,key,value in (
          ("approvals","environment","APPROVED"),
          ("approvals","environment",{"status":"FAILED","detail":"failed","reference":"test://failure"}),
          ("evidence","target_db_and_backup","VERIFIED"),
          ("evidence","target_db_and_backup",{"status":"NOT_RUN","detail":"not run","reference":"test://failure"}),
        ):
            with self.subTest(group=group,key=key,value=value):
                manifest=approved_manifest(event_enabled=True);manifest[group][key]=value
                with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_NOT_APPROVED"):
                    self.settings(manifest)

    def test_active_manifest_allows_only_user_accepted_test_limitations(self):
        manifest=approved_manifest(event_enabled=True)
        limitation={"status":"ACCEPTED_LIMIT","accepted_by":"user","detail":"known test gap","reference":"test://acceptance"}
        manifest["evidence"]["physical_device_qa"]=limitation
        manifest["evidence"]["final_load_test"]=limitation
        self.assertTrue(self.settings(manifest).event_enabled)
        for key,value in (
          ("rollback_rehearsal",limitation),
          ("final_load_test",{**limitation,"accepted_by":"operator"}),
        ):
            with self.subTest(key=key):
                invalid=approved_manifest(event_enabled=True);invalid["evidence"][key]=value
                with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_NOT_APPROVED"):
                    self.settings(invalid)

    def test_paused_manifest_still_requires_exact_preparation_evidence(self):
        for group,key,value in (("approvals","environment",None),("evidence","target_db_and_backup",None),("evidence","inventory_reconciliation","PENDING"),("evidence","runtime_production_guard","check FAILED"),("evidence","runtime_production_guard","미실행")):
            with self.subTest(group=group,key=key):
                manifest=approved_manifest()
                manifest[group][key]=value
                with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_NOT_APPROVED"):
                    self.settings(manifest)

    def test_manifest_quantities_require_positive_json_integers(self):
        for collection,index,value in (("draw_prizes",0,True),("draw_prizes",0,"77"),("ranking_prizes",0,1.0)):
            with self.subTest(collection=collection,value=value):
                manifest=approved_manifest();manifest[collection][index]["quantity"]=value
                with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_INVALID"):
                    self.settings(manifest)
        manifest=approved_manifest();manifest["draw_pool"]["total_slots"]=True
        with self.assertRaisesRegex(config.ConfigurationError,"PRODUCTION_MANIFEST_INVALID"):
            self.settings(manifest)

class ProductionDatabaseGuardTest(unittest.TestCase):
    def settings(self):
        return type("Settings",(),{
          "environment":"production","project_ref":PROJECT,"synthetic_only":False,
          "schema_name":"dino_prod","app_role":"dino_prod_app",
          "launch_manifest_sha256":"a"*64,"campaign_id":"gemini_dino_2026","event_enabled":False,
          "campaign_opens_at":"2026-09-29T19:00:00+09:00","campaign_closes_at":"2026-10-03T00:00:00+09:00",
          "claim_closes_at":"2026-10-04T00:00:00+09:00",
          "draw_pool_total":5000,"draw_prize_quantity":77,"ranking_prize_quantity":3,
        })()

    def guard(self,**overrides):
        return {
          "environment":"production","project_ref":PROJECT,"schema_name":"dino_prod","synthetic_only":False,
          "test_seed":False,"campaign_id":"gemini_dino_2026","connection_role":"dino_prod_app",
          "launch_manifest_sha256":"a"*64,"event_enabled":False,
          "campaign_opens_at":datetime.fromisoformat("2026-09-29T19:00:00+09:00"),
          "campaign_closes_at":datetime.fromisoformat("2026-10-03T00:00:00+09:00"),
          "claim_closes_at":datetime.fromisoformat("2026-10-04T00:00:00+09:00"),
          "draw_pool_total":5000,"draw_prize_quantity":77,"ranking_prize_quantity":3,
          "unlimited_play":False,"synthetic_inventory":False,"shortened_clock":False,
          **overrides,
        }

    def test_exact_production_guard_passes_and_queries_only_production_schema(self):
        conn=FakeConnection(self.guard());guard=db.check_environment(conn,self.settings())
        self.assertIn("from dino_prod.environment_guard",conn.query)
        self.assertIn("from dino_prod.schema_version",conn.query)
        self.assertNotIn("dino_dev",conn.query);self.assertEqual(guard["campaign_id"],"gemini_dino_2026")

    def test_guard_accepts_equivalent_utc_timestamps(self):
        from datetime import timezone
        values=self.guard()
        for key in ("campaign_opens_at","campaign_closes_at","claim_closes_at"):
            values[key]=values[key].astimezone(timezone.utc)
        db.check_environment(FakeConnection(values),self.settings())

    def test_production_guard_rejects_beta_role_synthetic_or_manifest_drift(self):
        for overrides,error in (
          ({"connection_role":"dino_dev_app"},"DATABASE_ROLE_MISMATCH"),
          ({"synthetic_only":True},"SYNTHETIC_GUARD_MISMATCH"),
          ({"launch_manifest_sha256":"b"*64},"PRODUCTION_GUARD_MISMATCH"),
          ({"event_enabled":True},"PRODUCTION_GUARD_MISMATCH"),
          ({"test_seed":True},"PRODUCTION_GUARD_MISMATCH"),
          ({"draw_prize_quantity":76},"PRODUCTION_GUARD_MISMATCH"),
        ):
            with self.subTest(overrides=overrides),self.assertRaisesRegex(config.ConfigurationError,error):
                db.check_environment(FakeConnection(self.guard(**overrides)),self.settings())

if __name__=="__main__":unittest.main()
