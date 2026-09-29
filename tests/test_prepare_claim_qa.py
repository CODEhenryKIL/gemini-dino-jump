import datetime as dt
import importlib.util
import json
from pathlib import Path
import sys
import unittest

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "tests"))
sys.path.insert(0, str(ROOT / "server"))
import operations
from test_migration_acceptance import (
    ADDITIONS, CLAIM_FIX, FOUNDATION, GAME_V21, INTERRUPTED_AND_SHARE, KAKAO_SHARE_WEBHOOK,
    PHASE2, PHASE3, RANKING_FINALIZATION, REAL_TOP3_CONTACT, TemporaryAuditDatabase,
)

CLAIM_DRAFT = ROOT / "supabase/migrations/20260926215000_claim_contact_draft.sql"
LOW_SCORE_REFUND = ROOT / "supabase/migrations/20260927090000_low_score_ticket_refund.sql"
SPEC = importlib.util.spec_from_file_location("prepare_claim_qa", ROOT / "scripts/prepare_claim_qa.py")
qa = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(qa)


@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(), "isolated PostgreSQL unavailable")
class PrepareClaimQaTest(unittest.TestCase):
    def setUp(self):
        self.database = TemporaryAuditDatabase(); self.database.create()
        for migration in (FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT,
                          CLAIM_DRAFT, LOW_SCORE_REFUND, KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE,
                          PHASE3, RANKING_FINALIZATION):
            self.database.apply(migration)
        with self.connect() as conn:
            conn.execute("insert into dino_dev.environment_guard(environment,project_ref,test_seed) values('test','local',true)")
            conn.execute("""insert into dino_dev.campaign(id,title,status,game_version,benefit_url,probability_version)
              values('qa_campaign','QA','ACTIVE','1.2.0','https://example.test','qa-v1')""")
            conn.execute("update dino_dev.environment_guard set campaign_id='qa_campaign'")
            conn.execute("""insert into dino_dev.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
              values
              ('p_rank_first','qa_campaign',repeat('a',64),clock_timestamp()+interval '1 day','first','RankFirst001','test'),
              ('p_claim_qa_user','qa_campaign',repeat('b',64),clock_timestamp()+interval '1 day','target','RankTarget01','test'),
              ('p_rank_third','qa_campaign',repeat('c',64),clock_timestamp()+interval '1 day','third','RankThird001','test'),
              ('p_rank_fourth','qa_campaign',repeat('e',64),clock_timestamp()+interval '1 day','fourth','RankFourth01','test')""")
            for participant, score, tick, letter in (
                ('p_rank_first', 500, 300, 'a'), ('p_claim_qa_user', 400, 360, 'b'),
                ('p_rank_third', 300, 420, 'c'), ('p_rank_fourth', 200, 480, 'e')):
                session = 'gs_' + participant[2:]
                conn.execute("""insert into dino_dev.game_session
                  (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
                   finished_at,expires_at,score,valid_ticks,verification_result,environment)
                  values(%s,%s,'qa_campaign',%s,1,'2.1.0','FINISHED','INITIAL','NOT_DUE',
                    clock_timestamp(),clock_timestamp()+interval '1 day',%s,%s,'VERIFIED','test')""",
                    (session, participant, 'idem-' + letter, score, tick))
                conn.execute("""insert into dino_dev.versioned_best_score
                  (participant_id,game_version,session_id,score,achieved_at)
                  values(%s,'2.1.0',%s,%s,clock_timestamp())""", (participant, session, score))
            conn.execute("""insert into dino_dev.ranking_contact(participant_id,status,game_version)
              values('p_claim_qa_user','REQUESTED','2.1.0')""")
            conn.execute("""insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
              values('qa_prize','qa_campaign','TEST coffee','COUPON','/qa.png',0.1)""")
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) values('qa_inventory','qa_prize')")
            conn.execute("""insert into dino_dev.draw
              (id,campaign_id,participant_id,eligible_session_id,round_number,pouch_index,prize_id,inventory_item_id,
               is_won,outcome_kind,probability_version,random_audit_hash,revealed,scratch_completed)
              values('qa_draw','qa_campaign','p_claim_qa_user','gs_claim_qa_user',1,0,'qa_prize','qa_inventory',
                true,'PRIZE','qa-v1',repeat('d',64),true,true)""")
            conn.execute("""update dino_dev.inventory_item set status='RESERVED',reserved_by_draw_id='qa_draw',
              reserved_at=clock_timestamp() where id='qa_inventory'""")
            conn.execute("""insert into dino_dev.claim
              (id,campaign_id,participant_id,draw_id,claim_type,prize_id,inventory_item_id,status,contact_submitted_at)
              values('existing_draw','qa_campaign','p_claim_qa_user','qa_draw','DRAW','qa_prize','qa_inventory',
                'INFORMATION_RECEIVED',clock_timestamp())""")
            conn.execute("""update dino_dev.claim set hold_reason='SENSITIVE_HOLD_SENTINEL',
              verification_reference='SENSITIVE_VERIFY_SENTINEL' where id='existing_draw'""")
            conn.execute("""insert into dino_dev.claim_contact
              (claim_id,recipient_name,contact,school,synthetic)
              values('existing_draw','TEST_EXISTING','01000000000','TEST_SCHOOL',true)""")

    def tearDown(self): self.database.drop()
    def connect(self): return psycopg.connect(self.database.dsn, row_factory=dict_row)

    def state(self, conn):
        return {
            "draw": conn.execute("select to_jsonb(c) row from dino_dev.claim c where id='existing_draw'").fetchone()["row"],
            "contact": conn.execute("select to_jsonb(c) row from dino_dev.claim_contact c where claim_id='existing_draw'").fetchone()["row"],
            "ranking": conn.execute("select to_jsonb(r) row from dino_dev.ranking_contact r where participant_id='p_claim_qa_user'").fetchone()["row"],
            "inventory": conn.execute("select to_jsonb(i) row from dino_dev.inventory_item i where id='qa_inventory'").fetchone()["row"],
            "score": conn.execute("select to_jsonb(b) row from dino_dev.versioned_best_score b where participant_id='p_claim_qa_user'").fetchone()["row"],
        }

    def test_connector_snapshot_plan_apply_cleanup_preserves_existing_state(self):
        with self.connect() as conn:
            before = self.state(conn)
            raw = conn.execute(qa.render_state_sql('test', 'p_claim_qa_user')).fetchone()
        plan = qa.plan_from_snapshot(json.loads(json.dumps(raw, default=str)), 'test', 'p_claim_qa_user')
        self.assertEqual((plan['database_state']['campaign']['game_version'], plan['database_state']['runtime_game_version'],
                          plan['database_state']['ranking']['rank']), ('1.2.0', '2.1.0', 2))
        serialized = json.dumps(plan, ensure_ascii=False)
        for secret in ('TEST_EXISTING', '01000000000', 'TEST_SCHOOL', 'SENSITIVE_HOLD_SENTINEL', 'SENSITIVE_VERIFY_SENTINEL'):
            self.assertNotIn(secret, serialized)
        with self.connect() as conn:
            conn.execute(qa.render_apply_sql(plan, qa.APPLY_CONFIRMATION))
            claim = conn.execute("select * from dino_dev.claim where id=%s", (plan['fixture']['claim_id'],)).fetchone()
            after_apply = self.state(conn)
            status, payload = operations.claims(conn, {"participant_token_hash": "b" * 64})
        self.assertEqual(before, after_apply)
        self.assertEqual((claim['claim_type'], claim['status'], claim['prize_id'], claim['inventory_item_id'], claim['draw_id']),
                         ('RANKING', 'AWAITING_INFORMATION', None, None, None))
        listed = next(item for item in payload['claims'] if item['id'] == plan['fixture']['claim_id'])
        self.assertEqual((status, listed['claim_type'], listed['contact_submitted']), (200, 'RANKING', False))
        with self.connect() as conn:
            conn.execute(qa.render_cleanup_sql(plan, qa.CLEANUP_CONFIRMATION))
            self.assertIsNone(conn.execute("select 1 from dino_dev.claim where id=%s", (plan['fixture']['claim_id'],)).fetchone())
            self.assertEqual(before, self.state(conn))

    def test_cleanup_refuses_after_draft_or_share_touches_claim(self):
        with self.connect() as conn: plan = qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
        with self.connect() as conn:
            qa.apply_fixture(conn, plan, qa.APPLY_CONFIRMATION)
            conn.execute("""insert into dino_dev.claim_contact_draft
              (claim_id,recipient_name,contact,school,synthetic,consent_at,consent_version)
              values(%s,'TEST_QA','01000000000','TEST_SCHOOL',true,clock_timestamp(),'claim-contact-v1')""",
              (plan['fixture']['claim_id'],))
        with self.connect() as conn:
            with self.assertRaisesRegex(Exception, 'CLAIM_QA_FIXTURE_TOUCHED'):
                qa.cleanup_fixture(conn, plan, qa.CLEANUP_CONFIRMATION)
        with self.connect() as conn:
            self.assertIsNotNone(conn.execute("select 1 from dino_dev.claim where id=%s", (plan['fixture']['claim_id'],)).fetchone())

    def test_guards_reject_existing_ranking_non_top3_and_bad_contact(self):
        with self.connect() as conn:
            conn.execute("""insert into dino_dev.claim(id,campaign_id,participant_id,claim_type,status)
              values('already_rank','qa_campaign','p_claim_qa_user','RANKING','AWAITING_INFORMATION')""")
            with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_RANKING_CLAIM_EXISTS'):
                qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
            conn.execute("delete from dino_dev.claim where id='already_rank'")
            conn.execute("update dino_dev.ranking_contact set status='SUBMITTED',submitted_at=clock_timestamp() where participant_id='p_claim_qa_user'")
            with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_RANKING_CONTACT_INVALID'):
                qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
            conn.execute("update dino_dev.ranking_contact set status='REQUESTED',submitted_at=null where participant_id='p_claim_qa_user'")
            conn.execute("update dino_dev.ranking_contact set game_version='2.0.0' where participant_id='p_claim_qa_user'")
            with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_RANKING_CONTACT_INVALID'):
                qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
            conn.execute("update dino_dev.ranking_contact set game_version='2.1.0' where participant_id='p_claim_qa_user'")
            conn.execute("update dino_dev.versioned_best_score set score=100 where participant_id='p_claim_qa_user'")
            with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_TOP3_REQUIRED'):
                qa.plan_fixture(conn, 'test', 'p_claim_qa_user')

    def test_expired_and_stale_plans_are_rejected(self):
        with self.connect() as conn: plan = qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
        plan['created_at'] = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(hours=1)).isoformat()
        plan['sha256'] = qa._digest({key: value for key, value in plan.items() if key != 'sha256'})
        with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_PLAN_EXPIRED'):
            qa.render_apply_sql(plan, qa.APPLY_CONFIRMATION)
        self.assertIn('CLAIM_QA_FIXTURE_TOUCHED', qa.render_cleanup_sql(plan, qa.CLEANUP_CONFIRMATION))
        with self.connect() as conn: plan = qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
        with self.connect() as conn: conn.execute("update dino_dev.participant set nickname='changed' where id='p_claim_qa_user'")
        # Nickname is intentionally outside the frozen state; score is a material stale change.
        with self.connect() as conn: conn.execute("update dino_dev.versioned_best_score set score=401 where participant_id='p_claim_qa_user'")
        with self.connect() as conn:
            with self.assertRaisesRegex(Exception, 'CLAIM_QA_PLAN_STALE'):
                qa.apply_fixture(conn, plan, qa.APPLY_CONFIRMATION)

    def test_confirmation_and_scope_are_fail_closed(self):
        with self.connect() as conn: plan = qa.plan_fixture(conn, 'test', 'p_claim_qa_user')
        with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_CONFIRMATION_REQUIRED'):
            qa.render_apply_sql(plan, '')
        with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_CLEANUP_CONFIRMATION_REQUIRED'):
            qa.render_cleanup_sql(plan, '')
        with self.assertRaisesRegex(qa.ClaimQaError, 'CLAIM_QA_SCOPE_INVALID'):
            qa.render_state_sql('production', 'p_claim_qa_user')


if __name__ == '__main__': unittest.main()
