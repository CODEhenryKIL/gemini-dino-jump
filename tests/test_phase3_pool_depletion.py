"""Opt-in full depletion proof for the isolated 5,000-slot Phase 3 pool."""
import hashlib
import os
import sys
import unittest
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
import operations

DSN = os.getenv("PHASE3_POOL_DATABASE_URL")
CAMPAIGN_ID = os.getenv("PHASE3_POOL_CAMPAIGN_ID", "phase3_inventory_test")


@unittest.skipUnless(DSN, "set PHASE3_POOL_DATABASE_URL for the isolated full-pool proof")
class Phase3PoolDepletionTest(unittest.TestCase):
    def test_all_5000_slots_are_consumed_once_with_exact_inventory_mix(self):
        conn = psycopg.connect(DSN, row_factory=dict_row)
        try:
            counts = conn.execute("""select count(*)::int total,
              count(*) filter(where outcome_kind='PRIZE')::int prizes,
              count(*) filter(where outcome_kind='BENEFIT')::int benefits,
              count(*) filter(where allocated_draw_id is not null)::int allocated
              from dino_dev.draw_pool_slot where campaign_id=%s""", (CAMPAIGN_ID,)).fetchone()
            self.assertEqual(dict(counts), {"total": 5000, "prizes": 77, "benefits": 4923, "allocated": 0})
            conn.execute("update dino_dev.campaign set status='ACTIVE' where id=%s", (CAMPAIGN_ID,))
            conn.execute("update dino_dev.environment_guard set campaign_id=%s where singleton", (CAMPAIGN_ID,))
            conn.execute("""insert into dino_dev.participant
              (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
              select 'p_phase3_full_'||lpad(n::text,5,'0'),%s,
                lpad(to_hex(n),64,'0'),clock_timestamp()+interval '1 day',
                '공룡'||n,'phase3full'||lpad(n::text,6,'0'),'test'
              from generate_series(1,5001)n""", (CAMPAIGN_ID,))
            conn.execute("""insert into dino_dev.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
               ticket_refund_status,expires_at,score,valid_ticks,verification_result,end_reason,finished_at,environment)
              select 'gs_phase3_full_'||lpad(n::text,5,'0'),
                'p_phase3_full_'||lpad(n::text,5,'0'),%s,
                'phase3-full-'||n,n,'2.1.0','FINISHED','INITIAL','NOT_DUE',
                clock_timestamp()+interval '1 hour',101,60,'VERIFIED','COLLISION',clock_timestamp(),'test'
              from generate_series(1,5001)n""", (CAMPAIGN_ID,))
            conn.execute("set local role dino_dev_app")
            base = {"environment": "test", "deployment": "phase3-pool-proof",
                    "event_version": "phase3-v1", "game_version": "2.1.0",
                    "campaign_id": CAMPAIGN_ID, "base_url": "http://127.0.0.1:3000",
                    "project_ref": "local", "request_id": "phase3-pool-proof"}
            outcomes = {"PRIZE": 0, "BENEFIT": 0}
            for number in range(1, 5001):
                token_hash = f"{number:064x}"
                status, result = operations.create_draw(
                    conn,
                    {"pouch_index": number % 3, "expected_round_number": 1},
                    {**base, "participant_token_hash": token_hash,
                     "idempotency_key": hashlib.sha256(f"draw:{number}".encode()).hexdigest()},
                )
                self.assertEqual(status, 201)
                outcomes[result["outcome_kind"]] += 1
            with self.assertRaises(operations.DomainError) as exhausted:
                operations.create_draw(
                    conn, {"pouch_index": 0, "expected_round_number": 1},
                    {**base, "participant_token_hash": f"{5001:064x}",
                     "idempotency_key": hashlib.sha256(b"draw:5001").hexdigest()},
                )
            self.assertEqual(exhausted.exception.code, "DRAW_POOL_EXHAUSTED")
            proof = conn.execute("""select
              count(*)::int allocated,
              count(distinct allocated_draw_id)::int distinct_draws,
              count(*) filter(where outcome_kind='PRIZE')::int prize_slots,
              count(*) filter(where outcome_kind='BENEFIT')::int benefit_slots,
              (select count(*)::int from dino_dev.claim where campaign_id=%s and claim_type='DRAW') claims,
              (select count(*)::int from dino_dev.inventory_item i join dino_dev.prize p on p.id=i.prize_id
                where p.campaign_id=%s and i.status='RESERVED') reserved
              from dino_dev.draw_pool_slot where campaign_id=%s and allocated_draw_id is not null""",
              (CAMPAIGN_ID, CAMPAIGN_ID, CAMPAIGN_ID)).fetchone()
            self.assertEqual(outcomes, {"PRIZE": 77, "BENEFIT": 4923})
            self.assertEqual(tuple(proof.values()), (5000, 5000, 77, 4923, 77, 77))
        finally:
            conn.rollback()
            conn.close()


if __name__ == "__main__":
    unittest.main()
