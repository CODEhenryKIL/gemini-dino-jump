import copy
import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import unittest
import uuid

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
from test_migration_acceptance import (
    ADDITIONS, CLAIM_FIX, FOUNDATION, GAME_V21, INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK, PHASE2, PHASE3, RANKING_FINALIZATION,
    REAL_TOP3_CONTACT, TemporaryAuditDatabase,
)

CLAIM_DRAFT = ROOT / "supabase/migrations/20260926215000_claim_contact_draft.sql"
LOW_SCORE_REFUND = ROOT / "supabase/migrations/20260927090000_low_score_ticket_refund.sql"
SPEC = importlib.util.spec_from_file_location("beta_reset", ROOT / "scripts/beta_reset.py")
beta_reset = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(beta_reset)


@unittest.skipUnless(
    Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(),
    "isolated local PostgreSQL fixture is unavailable",
)
class BetaResetTest(unittest.TestCase):
    def setUp(self):
        self.database = TemporaryAuditDatabase()
        self.database.create()
        for migration in (
            FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT,
            CLAIM_DRAFT, LOW_SCORE_REFUND, KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE,
            PHASE3, RANKING_FINALIZATION,
        ):
            self.database.apply(migration)
        self.admin_id = str(uuid.uuid4())
        with self.connection() as conn:
            conn.execute("insert into dino_dev.environment_guard(environment,project_ref,test_seed) values('test','local',false)")
            conn.execute("""insert into dino_dev.campaign
                (id,title,status,game_version,benefit_url,probability_version)
                values(%s,'beta','PAUSED','2.1.0','https://example.test','beta-v1'),
                      ('unrelated_campaign','other','PAUSED','2.1.0','https://example.test','other-v1')""",
                (beta_reset.CAMPAIGN_ID,))
            conn.execute("update dino_dev.environment_guard set campaign_id=%s", (beta_reset.CAMPAIGN_ID,))
            conn.execute("""insert into dino_dev.admin_member(auth_user_id,display_name,permissions)
                values(%s,'keep-admin',array['analytics:read','claims:write'])""", (self.admin_id,))
            self._insert_campaign_rows(conn)
            self._revoke_beta_writes(conn)

    def tearDown(self):
        self.database.drop()

    def connection(self):
        return psycopg.connect(self.database.dsn, row_factory=dict_row)

    def _revoke_beta_writes(self, conn):
        for table in beta_reset.QUARANTINE_TABLES:
            conn.execute(f"revoke insert,update,delete on dino_dev.{table} from dino_dev_app")
        conn.execute("revoke update(status,version,updated_at) on dino_dev.campaign from dino_dev_app")

    def _insert_campaign_rows(self, conn):
        target = "participant_beta"
        other = "participant_other"
        conn.execute("""insert into dino_dev.participant
          (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
          values(%s,%s,repeat('a',64),clock_timestamp()+interval '1 day','beta','BetaReferral01','test'),
                (%s,'unrelated_campaign',repeat('b',64),clock_timestamp()+interval '1 day','other','OtherRefer001','test')""",
          (target, beta_reset.CAMPAIGN_ID, other))
        conn.execute("""insert into dino_dev.ticket_ledger
          (participant_id,ticket_kind,delta,source_type,source_id,balance_after)
          values(%s,'INITIAL',1,'INITIAL_GRANT','initial',1),(%s,'INITIAL',1,'INITIAL_GRANT','initial',1)""",
          (target, other))
        conn.execute("""insert into dino_dev.observation
          (id,event_id,actor_key,idempotency_key,request_hash,participant_id,campaign_code,environment)
          values('obs_beta_001','evt_beta_001',repeat('c',64),'idem_beta_001',repeat('d',64),%s,%s,'test'),
                ('obs_other_01','evt_other_01',repeat('e',64),'idem_other_01',repeat('f',64),%s,'other','test'),
                ('obs_beta_unlinked','evt_beta_unlinked',repeat('g',64),'idem_beta_unlinked',repeat('h',64),null,%s,'test'),
                ('obs_unknown_unlinked','evt_unknown_unlinked',repeat('i',64),'idem_unknown_unlinked',repeat('j',64),null,null,'test')""",
          (target, beta_reset.CAMPAIGN_ID, other, beta_reset.CAMPAIGN_ID))
        conn.execute("""insert into dino_dev.bootstrap(token_hash,observation_id,participant_id,expires_at)
          values(repeat('1',64),'obs_beta_001',%s,clock_timestamp()+interval '1 day'),
                (repeat('2',64),'obs_other_01',%s,clock_timestamp()+interval '1 day'),
                (repeat('3',64),'obs_beta_unlinked',null,clock_timestamp()+interval '1 day'),
                (repeat('4',64),'obs_unknown_unlinked',null,clock_timestamp()+interval '1 day')""", (target, other))
        conn.execute("""insert into dino_dev.game_session
          (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
           expires_at,score,valid_ticks,verification_result,end_reason,finished_at,environment)
          values('session_beta',%s,%s,'game_beta',1,'2.1.0','FINISHED','INITIAL','NOT_DUE',
                 clock_timestamp()+interval '1 day',500,600,'VERIFIED','COLLISION',clock_timestamp(),'test'),
                ('session_other',%s,'unrelated_campaign','game_other',2,'2.1.0','FINISHED','INITIAL','NOT_DUE',
                 clock_timestamp()+interval '1 day',400,600,'VERIFIED','COLLISION',clock_timestamp(),'test')""",
          (target, beta_reset.CAMPAIGN_ID, other))
        conn.execute("""insert into dino_dev.versioned_best_score(participant_id,game_version,session_id,score,achieved_at)
          values(%s,'2.1.0','session_beta',500,clock_timestamp()),
                (%s,'2.1.0','session_other',400,clock_timestamp())""", (target, other))
        conn.execute("""insert into dino_dev.ranking_contact
          (participant_id,status,synthetic,game_version) values(%s,'REQUESTED',true,'2.1.0')""", (target,))
        conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
          values('prize_beta',%s,'beta prize','COUPON','/beta.png',0.5),
                ('prize_other','unrelated_campaign','other prize','COUPON','/other.png',0.5)""",
          (beta_reset.CAMPAIGN_ID,))
        conn.execute("""insert into dino_dev.inventory_item(id,prize_id)
          values('inventory_beta','prize_beta'),('inventory_other','prize_other')""")
        conn.execute("""insert into dino_dev.inventory_history(inventory_item_id,to_status,reason)
          values('inventory_beta','AVAILABLE','seed'),('inventory_other','AVAILABLE','seed')""")
        conn.execute("""insert into dino_dev.draw
          (id,campaign_id,participant_id,eligible_session_id,pouch_index,prize_id,inventory_item_id,is_won,
           probability_version,random_audit_hash,revealed,scratch_completed,round_number,outcome_kind)
          values('draw_beta',%s,%s,'session_beta',0,'prize_beta','inventory_beta',true,'beta-v1',repeat('3',64),true,true,1,'PRIZE'),
                ('draw_other','unrelated_campaign',%s,'session_other',0,'prize_other','inventory_other',true,'other-v1',repeat('4',64),true,true,1,'PRIZE')""",
          (beta_reset.CAMPAIGN_ID, target, other))
        conn.execute("update dino_dev.inventory_item set status='RESERVED',reserved_by_draw_id='draw_beta' where id='inventory_beta'")
        conn.execute("update dino_dev.inventory_item set status='RESERVED',reserved_by_draw_id='draw_other' where id='inventory_other'")
        conn.execute("""insert into dino_dev.claim
          (id,campaign_id,participant_id,draw_id,claim_type,prize_id,inventory_item_id,status)
          values('claim_beta',%s,%s,'draw_beta','DRAW','prize_beta','inventory_beta','PENDING_REVIEW'),
                ('claim_other','unrelated_campaign',%s,'draw_other','DRAW','prize_other','inventory_other','PENDING_REVIEW')""",
          (beta_reset.CAMPAIGN_ID, target, other))
        conn.execute("""insert into dino_dev.claim_contact
          (claim_id,recipient_name,contact,school,synthetic)
          values('claim_beta','beta person','01000000000','school',true),
                ('claim_other','other person','01011111111','school',true)""")
        conn.execute("""insert into dino_dev.analytics_event
          (event_id,campaign_id,participant_id,event_name,environment,deployment,event_version,source,occurred_at)
          values('analytics_beta',%s,%s,'game_complete','test','local','v1','server',clock_timestamp()),
                ('analytics_other','unrelated_campaign',%s,'game_complete','test','local','v1','server',clock_timestamp())""",
          (beta_reset.CAMPAIGN_ID, target, other))
        conn.execute("""insert into dino_dev.kakao_share_intent
          (id,participant_id,campaign_id,kind,callback_token_hash,environment,expires_at,reward_type)
          values('share_beta',%s,%s,'retry_invite',repeat('5',64),'test',clock_timestamp()+interval '1 day','GAME'),
                ('share_other',%s,'unrelated_campaign','retry_invite',repeat('6',64),'test',clock_timestamp()+interval '1 day','GAME')""",
          (target, beta_reset.CAMPAIGN_ID, other))
        conn.execute("""insert into dino_dev.draw_credit_ledger
          (participant_id,campaign_id,delta,source_type,source_id,balance_after)
          values(%s,%s,1,'FIRST_GRANT','first_beta',1),
                (%s,'unrelated_campaign',1,'FIRST_GRANT','first_other',1)""",
          (target, beta_reset.CAMPAIGN_ID, other))
        conn.execute("""insert into dino_dev.draw_pool_slot
          (campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id,allocated_draw_id,allocated_at)
          values(%s,1,'PRIZE','prize_beta','inventory_beta','draw_beta',clock_timestamp()),
                ('unrelated_campaign',1,'PRIZE','prize_other','inventory_other','draw_other',clock_timestamp())""",
          (beta_reset.CAMPAIGN_ID,))
        conn.execute("""insert into dino_dev.ranking_snapshot
          (id,campaign_id,status,tie_policy,created_by,game_version)
          values('snapshot_beta',%s,'DRAFT','EARLIEST_ACHIEVED_AT',%s,'2.1.0'),
                ('snapshot_other','unrelated_campaign','DRAFT','EARLIEST_ACHIEVED_AT',%s,'2.1.0')""",
          (beta_reset.CAMPAIGN_ID, self.admin_id, self.admin_id))
        conn.execute("""insert into dino_dev.ranking_snapshot_entry
          (snapshot_id,participant_id,score,rank,tied,contact_status)
          values('snapshot_beta',%s,500,1,false,'REQUESTED'),
                ('snapshot_other',%s,400,1,false,'NONE')""", (target, other))
        conn.execute("""insert into dino_dev.admin_audit
          (admin_user_id,action,target_type,target_id,event_id)
          values(%s,'CAMPAIGN_STATUS','campaign',%s,'audit_beta'),
                (%s,'CAMPAIGN_STATUS','campaign','unrelated_campaign','audit_other')""",
          (self.admin_id, beta_reset.CAMPAIGN_ID, self.admin_id))
        conn.execute("""insert into dino_dev.idempotency_request
          (actor_key,route,idempotency_key,request_hash,response_status,response_body)
          values(repeat('a',64),'POST /api/game-sessions','idem-beta',repeat('7',64),200,'{}'),
                (repeat('b',64),'POST /api/game-sessions','idem-other',repeat('8',64),200,'{}')""")
        conn.execute("""insert into dino_dev.rate_limit_bucket(bucket_key,window_started_at,count)
          values('route:/api/game-sessions:'||repeat('a',64),clock_timestamp(),1),
                ('route:/api/game-sessions:'||repeat('b',64),clock_timestamp(),1),
                ('ip:'||repeat('9',64),clock_timestamp(),1)""")

    def _counts(self, conn):
        return {
            table: conn.execute(f"select count(*) n from dino_dev.{table}").fetchone()["n"]
            for table in ("campaign", "participant", "claim_contact", "analytics_event", "admin_member",
                          "environment_guard", "schema_version", "idempotency_request", "rate_limit_bucket")
        }

    def test_plan_is_read_only_and_contains_no_raw_identifiers_or_contact_data(self):
        with self.connection() as conn:
            before = self._counts(conn)
            plan = beta_reset.build_plan(conn, "test")
            after = self._counts(conn)
        self.assertEqual(after, before)
        rendered = json.dumps(plan, sort_keys=True)
        self.assertNotIn("participant_beta", rendered)
        self.assertNotIn("beta person", rendered)
        self.assertNotIn("01000000000", rendered)
        self.assertEqual(plan["tables"]["participant"]["count"], 1)
        self.assertEqual(plan["target"]["campaign_id"], beta_reset.CAMPAIGN_ID)

    def test_apply_removes_only_beta_rows_and_preserves_guard_campaign_admin_and_other_campaign(self):
        with self.connection() as conn:
            guard_before = dict(conn.execute("select * from dino_dev.environment_guard").fetchone())
            campaign_before = dict(conn.execute("select * from dino_dev.campaign where id=%s", (beta_reset.CAMPAIGN_ID,)).fetchone())
            versions_before = conn.execute("select count(*) n from dino_dev.schema_version").fetchone()["n"]
            plan = beta_reset.build_plan(conn, "test")
            result = beta_reset.apply_plan(conn, "test", plan, beta_reset.INGRESS_CONFIRMATION)
            self.assertTrue(result["applied"])
            self.assertEqual(conn.execute("select count(*) n from dino_dev.participant where campaign_id=%s", (beta_reset.CAMPAIGN_ID,)).fetchone()["n"], 0)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.prize where campaign_id=%s", (beta_reset.CAMPAIGN_ID,)).fetchone()["n"], 0)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.participant where campaign_id='unrelated_campaign'").fetchone()["n"], 1)
            self.assertEqual(dict(conn.execute("select * from dino_dev.environment_guard").fetchone()), guard_before)
            self.assertEqual(dict(conn.execute("select * from dino_dev.campaign where id=%s", (beta_reset.CAMPAIGN_ID,)).fetchone()), campaign_before)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.admin_member").fetchone()["n"], 1)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.schema_version").fetchone()["n"], versions_before)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.rate_limit_bucket where bucket_key like 'ip:%'").fetchone()["n"], 1)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.observation where id='obs_beta_unlinked'").fetchone()["n"], 0)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.bootstrap where observation_id='obs_beta_unlinked'").fetchone()["n"], 0)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.observation where id='obs_unknown_unlinked'").fetchone()["n"], 1)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.bootstrap where observation_id='obs_unknown_unlinked'").fetchone()["n"], 1)

            repeat_plan = beta_reset.build_plan(conn, "test")
            repeated = beta_reset.apply_plan(conn, "test", repeat_plan, beta_reset.INGRESS_CONFIRMATION)
            self.assertTrue(repeated["applied"])
            self.assertEqual(repeated["deleted"]["participant"], 0)

    def test_stale_plan_and_missing_quarantine_are_rejected(self):
        with self.connection() as conn:
            plan = beta_reset.build_plan(conn, "test")
            conn.execute("""insert into dino_dev.analytics_event
              (event_id,campaign_id,event_name,environment,deployment,event_version,source,occurred_at)
              values('late_beta',%s,'late','test','local','v1','server',clock_timestamp())""", (beta_reset.CAMPAIGN_ID,))
            with self.assertRaisesRegex(beta_reset.BetaResetError, "PLAN_STALE"):
                beta_reset.apply_plan(conn, "test", plan, beta_reset.INGRESS_CONFIRMATION)
            conn.execute("grant insert on dino_dev.analytics_event to dino_dev_app")
            with self.assertRaisesRegex(beta_reset.BetaResetError, "QUARANTINE_REQUIRED"):
                beta_reset.build_plan(conn, "test")

    def test_cross_campaign_reference_is_rejected(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.analytics_event
              (event_id,campaign_id,participant_id,event_name,environment,deployment,event_version,source,occurred_at)
              values('mixed_reference','unrelated_campaign','participant_beta','mixed','test','local','v1','server',clock_timestamp())""")
            with self.assertRaisesRegex(beta_reset.BetaResetError, "CROSS_CAMPAIGN"):
                beta_reset.build_plan(conn, "test")

    def test_cross_campaign_ranking_entry_is_rejected(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.ranking_snapshot_entry
              (snapshot_id,participant_id,score,rank,tied,contact_status)
              values('snapshot_other','participant_beta',300,2,false,'NONE')""")
            with self.assertRaisesRegex(beta_reset.BetaResetError, "CROSS_CAMPAIGN"):
                beta_reset.build_plan(conn, "test")

    def test_foreign_participant_in_beta_snapshot_is_rejected_when_beta_has_no_participants(self):
        with self.connection() as conn:
            plan = beta_reset.build_plan(conn, "test")
            beta_reset.apply_plan(conn, "test", plan, beta_reset.INGRESS_CONFIRMATION)
            conn.execute("""insert into dino_dev.ranking_snapshot
              (id,campaign_id,status,tie_policy,created_by,game_version)
              values('snapshot_beta_empty',%s,'DRAFT','EARLIEST_ACHIEVED_AT',%s,'2.1.0')""",
              (beta_reset.CAMPAIGN_ID, self.admin_id))
            conn.execute("""insert into dino_dev.ranking_snapshot_entry
              (snapshot_id,participant_id,score,rank,tied,contact_status)
              values('snapshot_beta_empty','participant_other',300,1,false,'NONE')""")
            self.assertEqual(conn.execute(
                "select count(*) n from dino_dev.participant where campaign_id=%s",
                (beta_reset.CAMPAIGN_ID,),
            ).fetchone()["n"], 0)
            with self.assertRaisesRegex(beta_reset.BetaResetError, "CROSS_CAMPAIGN"):
                beta_reset.build_plan(conn, "test")

    def test_admin_audit_requires_matching_target_type(self):
        with self.connection() as conn:
            conn.execute("""insert into dino_dev.admin_audit
              (admin_user_id,action,target_type,target_id,event_id)
              values(%s,'COLLISION','claim',%s,'audit_collision')""",
              (self.admin_id, beta_reset.CAMPAIGN_ID))
            plan = beta_reset.build_plan(conn, "test")
            beta_reset.apply_plan(conn, "test", plan, beta_reset.INGRESS_CONFIRMATION)
            self.assertEqual(conn.execute(
                "select count(*) n from dino_dev.admin_audit where event_id='audit_collision'"
            ).fetchone()["n"], 1)

    def test_database_error_rolls_back_every_delete(self):
        with self.connection() as conn:
            plan = beta_reset.build_plan(conn, "test")
            before = self._counts(conn)
            conn.execute("""create function dino_dev.test_stop_beta_delete() returns trigger language plpgsql as $$
              begin raise exception 'stop beta delete'; end $$""")
            conn.execute("""create trigger test_stop_beta_delete before delete on dino_dev.participant
              for each row execute function dino_dev.test_stop_beta_delete()""")
            with self.assertRaises(psycopg.Error):
                beta_reset.apply_plan(conn, "test", plan, beta_reset.INGRESS_CONFIRMATION)
            self.assertEqual(self._counts(conn), before)

    def test_confirmation_and_plan_integrity_are_required(self):
        with self.connection() as conn:
            plan = beta_reset.build_plan(conn, "test")
            with self.assertRaisesRegex(beta_reset.BetaResetError, "INGRESS_CONFIRMATION"):
                beta_reset.apply_plan(conn, "test", plan, "")
            altered = copy.deepcopy(plan)
            altered["target"]["campaign_id"] = "unrelated_campaign"
            altered["sha256"] = beta_reset._plan_digest(altered)
            with self.assertRaisesRegex(beta_reset.BetaResetError, "TARGET_MISMATCH"):
                beta_reset.apply_plan(conn, "test", altered, beta_reset.INGRESS_CONFIRMATION)

    def test_mcp_exported_plan_and_apply_sql_execute_with_same_guards(self):
        with psycopg.connect(self.database.dsn, autocommit=True, row_factory=dict_row) as conn:
            conn.execute("""insert into dino_dev.admin_audit
              (admin_user_id,action,target_type,target_id,event_id)
              values(%s,'CANDIDATE_COLLISION','ranking_snapshot_candidate',
                'snapshot_beta:participant_other','audit_candidate_collision')""", (self.admin_id,))
            direct = beta_reset.build_plan(conn, "test")
            cursor = conn.execute(beta_reset.mcp_plan_sql("test", "local"), prepare=False)
            while cursor.description is None and cursor.nextset():
                pass
            planned = cursor.fetchone()
            self.assertTrue(planned["guard_ok"])
            self.assertTrue(planned["campaign_frozen"])
            self.assertTrue(planned["schema_complete"])
            self.assertTrue(planned["database_quarantined"])
            self.assertRegex(planned["plan_token"], r"^[0-9a-f]{64}$")
            self.assertEqual(planned["counts_and_digests"], direct["tables"])
            self.assertEqual(planned["plan_token"], direct["scope_sha256"])
            sql = beta_reset.mcp_apply_sql(planned["plan_token"], "test", "local")
            conn.execute(sql, prepare=False)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.participant where campaign_id=%s",
                                          (beta_reset.CAMPAIGN_ID,)).fetchone()["n"], 0)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.participant where campaign_id='unrelated_campaign'").fetchone()["n"], 1)
            self.assertEqual(conn.execute("select count(*) n from dino_dev.admin_member").fetchone()["n"], 1)
            self.assertEqual(conn.execute(
                "select count(*) n from dino_dev.admin_audit where event_id='audit_candidate_collision'"
            ).fetchone()["n"], 1)

    def test_quarantine_checks_target_and_drains_preexisting_writer(self):
        sql = beta_reset.quarantine_sql("test", "local")
        self.assertIn("BETA_RESET_GUARD_MISMATCH", sql)
        self.assertIn("BETA_RESET_SCHEMA_INCOMPLETE", sql)
        self.assertGreaterEqual(sql.count("commit;"), 2)
        self.assertIn("in access exclusive mode", sql)
        self.assertIn("and test_seed", beta_reset.quarantine_sql("preview", beta_reset.PROJECT_REF))
        with psycopg.connect(self.database.dsn, autocommit=True) as admin:
            admin.execute("grant update on dino_dev.analytics_event to dino_dev_app")
        writer = psycopg.connect(self.database.dsn)
        try:
            writer.execute("set role dino_dev_app")
            writer.execute("update dino_dev.analytics_event set event_name='held' where event_id='analytics_beta'")
            with psycopg.connect(self.database.dsn, autocommit=True) as admin:
                with self.assertRaises(psycopg.Error):
                    admin.execute(sql, prepare=False)
            writer.rollback()
            with psycopg.connect(self.database.dsn, autocommit=True) as admin:
                admin.execute(sql, prepare=False)
                self.assertFalse(admin.execute(
                    "select has_table_privilege('dino_dev_app','dino_dev.analytics_event','UPDATE')"
                ).fetchone()[0])
        finally:
            writer.close()


if __name__ == "__main__":
    unittest.main()
