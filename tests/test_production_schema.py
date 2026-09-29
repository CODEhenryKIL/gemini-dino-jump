import copy,hashlib,json,sys,unittest
import importlib
from pathlib import Path

import psycopg

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/"scripts"))
sys.path.insert(0,str(ROOT/"tests"))

from prepare_production import provision,render_schema
from test_migration_acceptance import (
    ADDITIONS,CLAIM_FIX,FOUNDATION,GAME_V21,INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK,PHASE2,PHASE3,RANKING_FINALIZATION,
    REAL_TOP3_CONTACT,TemporaryAuditDatabase,
)

CLAIM_DRAFT=ROOT/"supabase/migrations/20260926215000_claim_contact_draft.sql"
LOW_SCORE_REFUND=ROOT/"supabase/migrations/20260927090000_low_score_ticket_refund.sql"
SEED=ROOT/"supabase/seed_dino_dev.sql"
GENERATED=ROOT/".local/phase3/production-schema.sql"

def approved_manifest():
    manifest=json.loads((ROOT/"config/phase3-launch.json").read_text(encoding="utf-8"))
    manifest["status"]="APPROVED";manifest["event_enabled"]=False
    manifest["campaign"].update({
      "id":"gemini_dino_2026_test","opens_at":"2026-09-29T21:00:00+09:00",
      "closes_at":"2026-10-03T00:00:00+09:00","claim_closes_at":"2026-10-04T00:00:00+09:00",
      "timezone":"Asia/Seoul",
    })
    manifest["policies"].update({
      "pool_exhaustion":"PAUSE_DRAW_AND_MANUAL_REVIEW","unallocated_inventory_at_close":"MANUAL_REVIEW",
      "beta_data_migration":"PRESERVE_BETA_START_NEW","ranking_ties":"EARLIER_ACHIEVEMENT_FIRST",
      "finish_after_close":"RECEIVED_BEFORE_CLOSE","draw_and_ranking_double_award":"ALLOW_BOTH",
      "eligibility_and_proof":"MANUAL_REVIEW","claim_deadline_and_no_response":"MANUAL_REVIEW_AFTER_DEADLINE",
      "duplicate_person_claims":"MANUAL_REVIEW","privacy_retention_and_deletion":"TEST_FIXTURE_APPROVED",
      "operator_contact":"TEST_FIXTURE_OPERATOR",
    })
    manifest["approvals"]={key:"TEST_FIXTURE_APPROVED" for key in manifest["approvals"]}
    manifest["evidence"]={key:"TEST_FIXTURE_EVIDENCE" for key in manifest["evidence"]}
    manifest["production_flags"]={"unlimited_play":False,"synthetic_inventory":False,"shortened_clock":False}
    return manifest

class ProductionPreparationContractTest(unittest.TestCase):
    @staticmethod
    def encoded(manifest):
        payload=json.dumps(manifest,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()
        return payload,hashlib.sha256(payload).hexdigest()

    def test_provision_accepts_launch_incomplete_paused_preparation(self):
        manifest=approved_manifest()
        manifest["status"]="DRAFT"
        manifest["event_enabled"]=False
        for key in ("privacy","benefit_and_brand","public_launch"):
            manifest["approvals"][key]=None
        for key in ("real_kakao_game_and_draw","physical_device_qa","final_load_test","notion_and_benefit_links","rollback_rehearsal"):
            manifest["evidence"][key]=None
        manifest["campaign"]["id"]="INVALID!"
        payload,digest=self.encoded(manifest)
        with self.assertRaisesRegex(ValueError,"Invalid production campaign ID"):
            provision(None,manifest,digest,payload)

    def test_provision_rejects_active_manifest_missing_launch_evidence_before_db_access(self):
        manifest=approved_manifest()
        manifest["event_enabled"]=True
        manifest["evidence"]["final_load_test"]=None
        payload,digest=self.encoded(manifest)
        with self.assertRaisesRegex(ValueError,"preparation-ready manifest with event_enabled=false"):
            provision(None,manifest,digest,payload)

    def test_provision_rejects_manifest_object_or_digest_drift(self):
        manifest=approved_manifest()
        payload,digest=self.encoded(manifest)
        changed=copy.deepcopy(manifest)
        changed["campaign"]["id"]="changed_after_hash"
        with self.assertRaisesRegex(ValueError,"do not match"):
            provision(None,changed,digest,payload)
        with self.assertRaisesRegex(ValueError,"do not match"):
            provision(None,manifest,"0"*64,payload)

    def test_provision_rejects_bool_int_manifest_drift(self):
        manifest=approved_manifest()
        payload,digest=self.encoded(manifest)
        changed=copy.deepcopy(manifest)
        changed["draw_prizes"][0]["quantity"]=True
        with self.assertRaisesRegex(ValueError,"do not match"):
            provision(None,changed,digest,payload)
        changed=copy.deepcopy(manifest)
        changed["draw_prizes"]=tuple(changed["draw_prizes"])
        with self.assertRaisesRegex(ValueError,"do not match"):
            provision(None,changed,digest,payload)

    def test_prepare_production_imports_as_scripts_package(self):
        module=importlib.import_module("scripts.prepare_production")
        manifest=approved_manifest();manifest["campaign"]["id"]="INVALID!"
        payload,digest=self.encoded(manifest)
        with self.assertRaisesRegex(ValueError,"Invalid production campaign ID"):
            module.provision(None,manifest,digest,payload)

@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(),"isolated local PostgreSQL fixture is unavailable")
class ProductionSchemaIsolationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database=TemporaryAuditDatabase();cls.database.create()
        migrations=(FOUNDATION,ADDITIONS,CLAIM_FIX,PHASE2,GAME_V21,REAL_TOP3_CONTACT,CLAIM_DRAFT,
                    LOW_SCORE_REFUND,KAKAO_SHARE_WEBHOOK,INTERRUPTED_AND_SHARE,PHASE3,RANKING_FINALIZATION)
        for migration in migrations:cls.database.apply(migration)
        with psycopg.connect(cls.database.dsn) as conn:
            conn.execute("""insert into dino_dev.environment_guard(environment,project_ref,test_seed)
              values('test','local',false)""")
        cls.database.apply(SEED)
        with psycopg.connect(cls.database.dsn) as conn:
            cls.beta_before=cls._beta_snapshot(conn)
        rendered=render_schema()
        if GENERATED.exists():
            if GENERATED.read_text(encoding="utf-8")!=rendered:raise AssertionError("generated production schema artifact is stale")
        with psycopg.connect(cls.database.dsn,autocommit=True) as conn:
            conn.execute(rendered,prepare=False)
        cls.manifest=approved_manifest()
        payload=json.dumps(cls.manifest,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()
        cls.digest=hashlib.sha256(payload).hexdigest()
        with psycopg.connect(cls.database.dsn) as conn:
            cls.provisioned=provision(conn,copy.deepcopy(cls.manifest),cls.digest,payload)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls,"database"):cls.database.drop()

    @staticmethod
    def _beta_snapshot(conn):
        rows={}
        for table in ("campaign","participant","prize","inventory_item","draw_pool_slot","environment_guard"):
            rows[table]=conn.execute(f"select count(*) from dino_dev.{table}").fetchone()[0]
        rows["schema_acl"]=conn.execute("select nspacl::text from pg_namespace where nspname='dino_dev'").fetchone()[0]
        rows["grants"]=conn.execute("""select grantee,table_name,privilege_type from information_schema.role_table_grants
          where table_schema='dino_dev' and grantee in ('dino_dev_app','dino_prod_app') order by 1,2,3""").fetchall()
        return rows

    def test_beta_rows_and_permissions_are_unchanged(self):
        with psycopg.connect(self.database.dsn) as conn:after=self._beta_snapshot(conn)
        self.assertEqual(after,self.beta_before)
        self.assertEqual(after["campaign"],1);self.assertEqual(after["inventory_item"],25)

    def test_schemas_and_roles_are_isolated_with_least_privilege(self):
        with psycopg.connect(self.database.dsn) as conn:
            role=conn.execute("""select rolcanlogin,rolsuper,rolcreatedb,rolcreaterole,rolinherit,rolbypassrls
              from pg_roles where rolname='dino_prod_app'""").fetchone()
            self.assertEqual(role,(False,False,False,False,False,False))
            self.assertFalse(conn.execute("select has_schema_privilege('dino_dev_app','dino_prod','usage')").fetchone()[0])
            self.assertFalse(conn.execute("select has_schema_privilege('dino_prod_app','dino_dev','usage')").fetchone()[0])
            self.assertTrue(conn.execute("select has_schema_privilege('dino_prod_app','dino_prod','usage')").fetchone()[0])
            self.assertTrue(conn.execute("select has_table_privilege('dino_prod_app','dino_prod.participant','select,insert,update')").fetchone()[0])
            self.assertFalse(conn.execute("select has_table_privilege('dino_prod_app','dino_prod.participant','delete')").fetchone()[0])
            self.assertTrue(conn.execute("select has_table_privilege('dino_prod_app','dino_prod.environment_guard','select')").fetchone()[0])
            self.assertFalse(conn.execute("select has_table_privilege('dino_prod_app','dino_prod.environment_guard','insert,update,delete')").fetchone()[0])

    def test_production_defaults_and_provisioned_inventory_are_real_and_paused(self):
        with psycopg.connect(self.database.dsn) as conn:
            defaults=dict(conn.execute("""select table_name,column_default from information_schema.columns
              where table_schema='dino_prod' and column_name='synthetic'
              and table_name in ('participant','observation','game_session','analytics_event')""").fetchall())
            self.assertEqual(set(defaults.values()),{"false"})
            campaign=conn.execute("select status,real_prizes_enabled,opens_at,closes_at,settings from dino_prod.campaign").fetchone()
            guard=conn.execute("""select environment,schema_name,synthetic_only,test_seed,event_enabled,launch_manifest_sha256,
              draw_pool_total,draw_prize_quantity,ranking_prize_quantity,claim_closes_at
              from dino_prod.environment_guard""").fetchone()
            slots=conn.execute("""select count(*),count(*) filter(where outcome_kind='PRIZE'),
              count(*) filter(where outcome_kind='BENEFIT') from dino_prod.draw_pool_slot""").fetchone()
            inventory=conn.execute("select count(*) from dino_prod.inventory_item").fetchone()[0]
            awards=conn.execute("select count(*) from dino_prod.ranking_award").fetchone()[0]
        self.assertEqual(campaign[:2],("PAUSED",True));self.assertLess(campaign[2],campaign[3])
        self.assertEqual(campaign[4]["phase3_draw_prize_quantity"],63)
        self.assertEqual(guard[:5],("production","dino_prod",False,False,False))
        self.assertEqual(guard[5:9],(self.digest,5000,63,3));self.assertIsNotNone(guard[9])
        self.assertEqual(slots,(5000,63,4937));self.assertEqual(inventory,66);self.assertEqual(awards,3)
        self.assertEqual(self.provisioned,{"campaign_id":"gemini_dino_2026_test","status":"PAUSED","event_enabled":False,"draw_slots":5000,"draw_prizes":63,"ranking_prizes":3})

    def test_repeated_schema_and_inventory_provisioning_refuse_overwrite(self):
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(self.database.dsn,autocommit=True) as conn:conn.execute(render_schema(),prepare=False)
        with self.assertRaisesRegex(ValueError,"not empty"):
            payload=json.dumps(self.manifest,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()
            with psycopg.connect(self.database.dsn) as conn:provision(conn,copy.deepcopy(self.manifest),self.digest,payload)

    def test_every_mutable_table_must_be_empty_before_provisioning(self):
        inserts=(
          "insert into dino_prod.observation(id,event_id,actor_key,idempotency_key,request_hash,environment) values('existing-observation','existing-event','actor','key','hash','production')",
          "insert into dino_prod.idempotency_request(actor_key,route,idempotency_key,request_hash,response_status,response_body) values('actor','route','key','hash',200,'{}')",
          "insert into dino_prod.admin_audit(admin_user_id,action,target_type,event_id) values('00000000-0000-0000-0000-000000000001','existing','campaign','existing-audit')",
          "insert into dino_prod.rate_limit_bucket(bucket_key,window_started_at,count) values('existing',clock_timestamp(),1)",
          "insert into dino_prod.admin_member(auth_user_id,display_name) values('00000000-0000-0000-0000-000000000001','existing admin')",
        )
        payload=json.dumps(self.manifest,ensure_ascii=False,separators=(",",":"),sort_keys=True).encode()
        with psycopg.connect(self.database.dsn) as conn:
            tables=[row[0] for row in conn.execute("select tablename from pg_tables where schemaname='dino_prod' and tablename<>'schema_version'")]
            truncate=psycopg.sql.SQL("truncate {} restart identity cascade").format(
                psycopg.sql.SQL(",").join(psycopg.sql.Identifier("dino_prod",table) for table in tables)
            )
            for statement in inserts:
                with self.subTest(statement=statement):
                    conn.execute(truncate)
                    conn.execute(statement)
                    with self.assertRaisesRegex(ValueError,"not empty"):
                        provision(conn,copy.deepcopy(self.manifest),self.digest,payload)
                    conn.rollback()

if __name__=="__main__":unittest.main()
