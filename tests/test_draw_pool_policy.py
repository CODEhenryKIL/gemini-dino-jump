import hashlib
import json
import secrets
import sys
import unittest
from pathlib import Path
from unittest import mock

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))

import operations
from test_migration_acceptance import (
    ADDITIONS,
    BENEFIT_RETRY,
    CLAIM_FIX,
    FOUNDATION,
    GAME_V21,
    INTERRUPTED_AND_SHARE,
    KAKAO_SHARE_WEBHOOK,
    PHASE2,
    PHASE3,
    RANKING_FINALIZATION,
    REAL_TOP3_CONTACT,
    TemporaryAuditDatabase,
)


CLAIM_DRAFT = ROOT / "supabase/migrations/20260926215000_claim_contact_draft.sql"
LOW_SCORE_REFUND = ROOT / "supabase/migrations/20260927090000_low_score_ticket_refund.sql"
SEED = ROOT / "supabase/seed_dino_dev.sql"
ACTIVE_POLICY_MIGRATIONS = sorted((ROOT / "supabase/migrations").glob("*draw_pool_active_policy*.sql"))
VARIABLE_POLICY_MIGRATIONS = sorted((ROOT / "supabase/migrations").glob("*draw_pool_variable_window*.sql"))
CAMPAIGN_ID = "gemini_dino_phase1_test"
POLICY_VERSION = "remaining-3000-test-v1"


@unittest.skipUnless(
    Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(),
    "isolated local PostgreSQL fixture is unavailable",
)
class DrawPoolPolicyTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        if len(ACTIVE_POLICY_MIGRATIONS) != 1 or len(VARIABLE_POLICY_MIGRATIONS) != 1:
            raise AssertionError(
                "expected one active policy and one variable window migration, got "
                f"{ACTIVE_POLICY_MIGRATIONS}, {VARIABLE_POLICY_MIGRATIONS}"
            )
        cls.database = TemporaryAuditDatabase()
        cls.database.create()
        migrations = (
            FOUNDATION,
            ADDITIONS,
            CLAIM_FIX,
            PHASE2,
            GAME_V21,
            REAL_TOP3_CONTACT,
            CLAIM_DRAFT,
            LOW_SCORE_REFUND,
            KAKAO_SHARE_WEBHOOK,
            INTERRUPTED_AND_SHARE,
            PHASE3,
            RANKING_FINALIZATION,
            BENEFIT_RETRY,
            ACTIVE_POLICY_MIGRATIONS[0],
            VARIABLE_POLICY_MIGRATIONS[0],
        )
        for migration in migrations:
            cls.database.apply(migration)
        with psycopg.connect(cls.database.dsn) as conn:
            conn.execute(
                "insert into dino_dev.environment_guard(environment,project_ref,test_seed) "
                "values('test','local',false)"
            )
        cls.database.apply(SEED)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    def setUp(self):
        self.conn = psycopg.connect(self.database.dsn, row_factory=dict_row)
        self.tx = self.conn.transaction()
        self.tx.__enter__()

    def tearDown(self):
        self.tx.__exit__(Exception, Exception("rollback test"), None)
        self.conn.close()

    @staticmethod
    def context(token_hash):
        return {
            "environment": "test",
            "deployment": "draw-pool-policy-test",
            "event_version": "phase3-v1",
            "game_version": "1.2.0",
            "campaign_id": CAMPAIGN_ID,
            "base_url": "http://127.0.0.1:3000",
            "project_ref": "local",
            "request_id": "draw-pool-policy-test",
            "participant_token_hash": token_hash,
            "idempotency_key": secrets.token_urlsafe(24),
        }

    def participant(self, number, *, score=101):
        token_hash = f"{number:064x}"
        participant_id = f"policy_participant_{number}"
        session_id = f"policy_session_{number}"
        self.conn.execute(
            """insert into dino_dev.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,
               initial_balance)
              values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,'test',0)""",
            (participant_id, CAMPAIGN_ID, token_hash, f"공룡{number}", f"Policy{number:06d}"),
        )
        self.conn.execute(
            """insert into dino_dev.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
               ticket_refund_status,expires_at,score,valid_ticks,verification_result,end_reason,
               finished_at,environment)
              values(%s,%s,%s,%s,%s,'1.2.0','FINISHED','INITIAL','NOT_DUE',
                clock_timestamp()+interval '1 hour',%s,60,'VERIFIED','COLLISION',clock_timestamp(),'test')""",
            (session_id, participant_id, CAMPAIGN_ID, f"policy-session-{number}", number, score),
        )
        return participant_id, session_id, token_hash

    def set_policy(self, *, ceiling=3000, version=POLICY_VERSION, initial_remaining=3000):
        policy = {
            "version": version,
            "active_slot_max": ceiling,
            "initial_remaining": initial_remaining,
            "activated_at": "2026-09-30T13:49:26+09:00",
        }
        self.conn.execute(
            """update dino_dev.campaign
              set probability_version=%s,
                  settings=settings||jsonb_build_object('draw_pool_policy',%s::jsonb)
              where id=%s""",
            (version, json.dumps(policy), CAMPAIGN_ID),
        )
        return policy

    def add_benefit_slots(self, first, last):
        self.conn.execute(
            """insert into dino_dev.draw_pool_slot(campaign_id,slot_number,outcome_kind)
              select %s,n,'BENEFIT' from generate_series(%s::integer,%s::integer)n""",
            (CAMPAIGN_ID, first, last),
        )

    def test_no_policy_keeps_legacy_pool_compatible(self):
        _participant_id, _session_id, token_hash = self.participant(1)
        self.add_benefit_slots(1, 1)
        self.conn.execute("set local role dino_dev_app")
        status, result = operations.create_draw(
            self.conn, {"pouch_index": 0, "expected_round_number": 1}, self.context(token_hash)
        )
        marker = self.conn.execute(
            "select current_setting('dino.draw_policy_version',true) marker"
        ).fetchone()["marker"]
        self.assertEqual((status, result["outcome_kind"], marker), (201, "BENEFIT", None))

    def test_invalid_policy_windows_fail_closed_without_minting_or_allocating_rights(self):
        self.add_benefit_slots(1, 1)
        for index, invalid in enumerate((0, -1, 5001, 1.5, True, "1500"), start=20):
            with self.subTest(initial_remaining=invalid):
                participant_id, _session_id, token_hash = self.participant(index)
                self.set_policy(ceiling=1, initial_remaining=invalid)
                self.conn.execute("set local role dino_dev_app")
                with self.assertRaises(operations.DomainError) as caught, self.conn.transaction():
                    operations.create_draw(
                        self.conn, {"pouch_index": 0, "expected_round_number": 1},
                        self.context(token_hash),
                    )
                self.conn.execute("reset role")
                proof = self.conn.execute(
                    """select
                      (select count(*) from dino_dev.draw where participant_id=%s)::int draws,
                      (select count(*) from dino_dev.draw_credit_ledger where participant_id=%s)::int credits,
                      (select count(*) from dino_dev.draw_pool_slot where allocated_draw_id is not null)::int allocated""",
                    (participant_id, participant_id),
                ).fetchone()
                self.assertEqual(caught.exception.code, "DRAW_CONFIG_INVALID")
                self.assertEqual(tuple(proof.values()), (0, 0, 0))

    def test_policy_window_1500_is_accepted(self):
        _participant_id, _session_id, token_hash = self.participant(2)
        self.add_benefit_slots(1, 1500)
        self.set_policy(ceiling=1500, version="remaining-1500-accepted", initial_remaining=1500)
        self.conn.execute("set local role dino_dev_app")
        status, result = operations.create_draw(
            self.conn, {"pouch_index": 0, "expected_round_number": 1}, self.context(token_hash)
        )
        self.assertEqual((status, result["outcome_kind"]), (201, "BENEFIT"))

    def test_pool_lock_refreshes_stale_campaign_before_selecting(self):
        self.add_benefit_slots(1, 2)
        stale = self.conn.execute(
            "select * from dino_dev.campaign where id=%s", (CAMPAIGN_ID,)
        ).fetchone()
        self.set_policy(ceiling=1)
        self.conn.execute("set local role dino_dev_app")
        with mock.patch.object(operations.secrets, "randbelow", side_effect=lambda count: count - 1):
            prize, inventory, _roll, slot = operations._pool_prize(self.conn, dict(stale))
        self.assertEqual((slot["slot_number"], inventory, prize["category"]), (1, None, "NO_PRIZE"))

    def test_old_runtime_insert_rolls_back_without_consuming_existing_rights(self):
        participant_id, session_id, _token_hash = self.participant(3)
        self.add_benefit_slots(1, 1)
        self.set_policy(ceiling=1)
        self.conn.execute(
            """insert into dino_dev.draw_credit_ledger
              (participant_id,campaign_id,delta,source_type,source_id,balance_after)
              values(%s,%s,1,'FIRST_GRANT',%s,1)""",
            (participant_id, CAMPAIGN_ID, session_id),
        )
        self.conn.execute("set local role dino_dev_app")
        with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
            self.conn.execute(
                """insert into dino_dev.draw
                  (id,campaign_id,participant_id,eligible_session_id,round_number,pouch_index,
                   prize_id,is_won,outcome_kind,probability_version,random_audit_hash)
                  values('policy_old_runtime_draw',%s,%s,%s,1,0,'test_no_prize',false,
                    'BENEFIT',%s,repeat('a',64))""",
                (CAMPAIGN_ID, participant_id, session_id, POLICY_VERSION),
            )
        self.conn.execute("select set_config('dino.draw_policy_version',%s,true)", (POLICY_VERSION,))
        with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
            self.conn.execute(
                """insert into dino_dev.draw
                  (id,campaign_id,participant_id,eligible_session_id,round_number,pouch_index,
                   prize_id,is_won,outcome_kind,probability_version,random_audit_hash)
                  values('policy_wrong_version_draw',%s,%s,%s,1,0,'test_no_prize',false,
                    'BENEFIT','stale-policy-version',repeat('d',64))""",
                (CAMPAIGN_ID, participant_id, session_id),
            )
        proof = self.conn.execute(
            """select
              (select count(*) from dino_dev.draw where participant_id=%s)::int draws,
              (select coalesce(sum(delta),0) from dino_dev.draw_credit_ledger where participant_id=%s)::int balance,
              (select count(*) from dino_dev.draw_pool_slot where allocated_draw_id is not null)::int allocated""",
            (participant_id, participant_id),
        ).fetchone()
        self.assertEqual(tuple(proof.values()), (0, 1, 0))

    def test_database_guard_rejects_allocation_above_ceiling(self):
        participant_id, session_id, _token_hash = self.participant(4)
        self.add_benefit_slots(1, 2)
        self.set_policy(ceiling=1)
        self.conn.execute("set local role dino_dev_app")
        self.conn.execute("select set_config('dino.draw_policy_version',%s,true)", (POLICY_VERSION,))
        self.conn.execute(
            """insert into dino_dev.draw
              (id,campaign_id,participant_id,eligible_session_id,round_number,pouch_index,
               prize_id,is_won,outcome_kind,probability_version,random_audit_hash)
              values('policy_guard_draw',%s,%s,%s,1,0,'test_no_prize',false,
                'BENEFIT',%s,repeat('b',64))""",
            (CAMPAIGN_ID, participant_id, session_id, POLICY_VERSION),
        )
        with self.assertRaises(psycopg.errors.CheckViolation), self.conn.transaction():
            self.conn.execute(
                """update dino_dev.draw_pool_slot
                  set allocated_draw_id='policy_guard_draw',allocated_at=clock_timestamp()
                  where campaign_id=%s and slot_number=2""",
                (CAMPAIGN_ID,),
            )
        allocated = self.conn.execute(
            "select allocated_draw_id from dino_dev.draw_pool_slot where campaign_id=%s and slot_number=2",
            (CAMPAIGN_ID,),
        ).fetchone()["allocated_draw_id"]
        self.assertIsNone(allocated)

    def test_historical_draw_replay_does_not_require_current_policy_marker(self):
        participant_id, session_id, token_hash = self.participant(5)
        self.conn.execute(
            """insert into dino_dev.draw
              (id,campaign_id,participant_id,eligible_session_id,round_number,pouch_index,
               prize_id,is_won,outcome_kind,probability_version,random_audit_hash)
              values('policy_historical_draw',%s,%s,%s,1,2,'test_no_prize',false,
                'BENEFIT','phase1-test-v1',repeat('c',64))""",
            (CAMPAIGN_ID, participant_id, session_id),
        )
        self.set_policy(ceiling=1)
        self.conn.execute("set local role dino_dev_app")
        status, replay = operations.create_draw(
            self.conn, {"pouch_index": 2, "expected_round_number": 1}, self.context(token_hash)
        )
        self.assertEqual(
            (status, replay["draw_id"], replay["replayed"], replay["outcome_kind"]),
            (200, "policy_historical_draw", True, "BENEFIT"),
        )

    def assert_window_depletes_once_then_falls_back_to_benefit(self, window):
        participant_count = window + 1
        version = f"remaining-{window}-depletion-v1"
        self.conn.execute(
            """insert into dino_dev.inventory_item(id,prize_id)
              select 'policy_coffee_'||lpad(n::text,3,'0'),'test_coffee'
              from generate_series(1,56)n"""
        )
        self.conn.execute(
            """insert into dino_dev.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,
               initial_balance)
              select 'policy_bulk_p_'||n,%s,lpad(to_hex(n+10000),64,'0'),
                clock_timestamp()+interval '1 day','공룡'||n,'PolicyBulk'||lpad(n::text,5,'0'),
                'test',0 from generate_series(1,%s::integer)n""",
            (CAMPAIGN_ID, participant_count),
        )
        self.conn.execute(
            """insert into dino_dev.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
               ticket_refund_status,expires_at,score,valid_ticks,verification_result,end_reason,
               finished_at,environment)
              select 'policy_bulk_s_'||n,'policy_bulk_p_'||n,%s,'policy-bulk-'||n,n,
                '1.2.0','FINISHED','INITIAL','NOT_DUE',clock_timestamp()+interval '1 hour',
                101,60,'VERIFIED','COLLISION',clock_timestamp(),'test'
              from generate_series(1,%s::integer)n""",
            (CAMPAIGN_ID, participant_count),
        )
        self.conn.execute(
            """insert into dino_dev.draw_pool_slot
              (campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id)
              select %s,n,case when n<=56 then 'PRIZE' else 'BENEFIT' end,
                case when n<=56 then 'test_coffee' end,
                case when n<=56 then 'policy_coffee_'||lpad(n::text,3,'0') end
              from generate_series(1,5000)n""",
            (CAMPAIGN_ID,),
        )
        self.conn.execute(
            """update dino_dev.campaign set settings=settings||
              '{"phase3_manifest_hash":"policy-test","phase3_draw_prize_quantity":56}'::jsonb
              where id=%s""",
            (CAMPAIGN_ID,),
        )
        self.set_policy(ceiling=window, version=version, initial_remaining=window)
        self.conn.execute("set local role dino_dev_app")
        outcomes = {"PRIZE": 0, "BENEFIT": 0}
        for number in range(1, participant_count + 1):
            token_hash = f"{number + 10000:064x}"
            status, result = operations.create_draw(
                self.conn,
                {"pouch_index": number % 3, "expected_round_number": 1},
                self.context(token_hash),
            )
            self.assertEqual(status, 201)
            outcomes[result["outcome_kind"]] += 1
        proof = self.conn.execute(
            """select
              count(*) filter(where slot_number<=%s and allocated_draw_id is not null)::int active_allocated,
              count(*) filter(where slot_number>%s and allocated_draw_id is not null)::int inactive_allocated,
              count(*) filter(where slot_number>%s and allocated_draw_id is null)::int inactive_remaining,
              count(*) filter(where outcome_kind='PRIZE' and allocated_draw_id is not null)::int prizes_allocated
              from dino_dev.draw_pool_slot where campaign_id=%s""",
            (window, window, window, CAMPAIGN_ID),
        ).fetchone()
        last = self.conn.execute(
            "select outcome_kind,probability_version from dino_dev.draw where participant_id=%s",
            (f"policy_bulk_p_{participant_count}",),
        ).fetchone()
        self.assertEqual(outcomes, {"PRIZE": 56, "BENEFIT": window - 55})
        self.assertEqual(tuple(proof.values()), (window, 0, 5000 - window, 56))
        self.assertEqual(tuple(last.values()), ("BENEFIT", version))

    def test_active_1500_slots_deplete_once_then_fallback_to_benefit(self):
        self.assert_window_depletes_once_then_falls_back_to_benefit(1500)

    def test_active_3000_slots_deplete_once_then_fallback_to_benefit(self):
        self.assert_window_depletes_once_then_falls_back_to_benefit(3000)


if __name__ == "__main__":
    unittest.main()
