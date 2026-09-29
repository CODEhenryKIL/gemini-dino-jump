import copy,hashlib,json,sys,unittest
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
      "id":"gemini_dino_2026_test","opens_at":"2026-09-29T19:00:00+09:00",
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
            cls.provisioned=provision(conn,copy.deepcopy(cls.manifest),cls.digest)

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
            campaign=conn.execute("select status,real_prizes_enabled,opens_at,closes_at from dino_prod.campaign").fetchone()
            guard=conn.execute("""select environment,schema_name,synthetic_only,test_seed,event_enabled,launch_manifest_sha256,
              draw_pool_total,draw_prize_quantity,ranking_prize_quantity,claim_closes_at
              from dino_prod.environment_guard""").fetchone()
            slots=conn.execute("""select count(*),count(*) filter(where outcome_kind='PRIZE'),
              count(*) filter(where outcome_kind='BENEFIT') from dino_prod.draw_pool_slot""").fetchone()
            inventory=conn.execute("select count(*) from dino_prod.inventory_item").fetchone()[0]
            awards=conn.execute("select count(*) from dino_prod.ranking_award").fetchone()[0]
        self.assertEqual(campaign[:2],("PAUSED",True));self.assertLess(campaign[2],campaign[3])
        self.assertEqual(guard[:5],("production","dino_prod",False,False,False))
        self.assertEqual(guard[5:9],(self.digest,5000,77,3));self.assertIsNotNone(guard[9])
        self.assertEqual(slots,(5000,77,4923));self.assertEqual(inventory,80);self.assertEqual(awards,3)
        self.assertEqual(self.provisioned,{"campaign_id":"gemini_dino_2026_test","status":"PAUSED","event_enabled":False,"draw_slots":5000,"draw_prizes":77,"ranking_prizes":3})

    def test_repeated_schema_and_inventory_provisioning_refuse_overwrite(self):
        with self.assertRaises(psycopg.Error):
            with psycopg.connect(self.database.dsn,autocommit=True) as conn:conn.execute(render_schema(),prepare=False)
        with self.assertRaisesRegex(ValueError,"not empty"):
            with psycopg.connect(self.database.dsn) as conn:provision(conn,copy.deepcopy(self.manifest),self.digest)

if __name__=="__main__":unittest.main()
