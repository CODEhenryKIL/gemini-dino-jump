import concurrent.futures
import contextlib
import hashlib
import hmac
import os
import secrets
import sys
import threading
import time
import unittest
import uuid
from pathlib import Path

import psycopg
from psycopg.rows import dict_row


ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))

import operations


DSN = os.getenv(
    "PHASE1_CONCURRENCY_DATABASE_URL",
    "postgres://postgres@127.0.0.1:55433/dino_phase1_v2_concurrency",
)
CAMPAIGN_ID = "gemini_dino_phase1_test"
PEPPER = "concurrency-test-pepper-0123456789"


def token_hash(value):
    return hmac.new(PEPPER.encode(), value.encode(), hashlib.sha256).hexdigest()


def context(**extra):
    value = {
        "environment": "test",
        "deployment": "concurrency-test",
        "event_version": "phase1-v1",
        "campaign_id": CAMPAIGN_ID,
        "base_url": "http://127.0.0.1:3000",
        "project_ref": "local",
        "request_id": "concurrency-test",
        "invite_active_ms": 3000,
        "participant_cookie_max_age": 2592000,
        "ip_subject": "concurrency-test-ip",
    }
    value.update(extra)
    return value


@contextlib.contextmanager
def app_tx():
    last_error = None
    for _attempt in range(50):
        try:
            conn = psycopg.connect(DSN, row_factory=dict_row)
            break
        except psycopg.OperationalError as error:
            last_error = error
            time.sleep(0.01)
    else:
        raise last_error
    try:
        with conn.transaction():
            conn.execute("set local role dino_dev_app")
            yield conn
    finally:
        conn.close()


class BackendConcurrencyTest(unittest.TestCase):
    def setUp(self):
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "truncate dino_dev.rate_limit_bucket,dino_dev.idempotency_request,"
                "dino_dev.analytics_event,dino_dev.admin_audit,dino_dev.claim_contact,"
                "dino_dev.claim,dino_dev.inventory_history,dino_dev.draw,"
                "dino_dev.ranking_contact,dino_dev.best_score,dino_dev.game_session,"
                "dino_dev.invitation_reward,dino_dev.invitation_visit,dino_dev.ticket_ledger,"
                "dino_dev.bootstrap,dino_dev.observation,dino_dev.participant restart identity cascade"
            )
            conn.execute(
                "insert into dino_dev.inventory_item(id,prize_id) "
                "select 'test_coffee_'||lpad(n::text,3,'0'),'test_coffee' "
                "from generate_series(1,20)n"
            )
            conn.execute(
                "insert into dino_dev.inventory_item(id,prize_id) "
                "select 'test_shipping_'||lpad(n::text,3,'0'),'test_shipping' "
                "from generate_series(1,5)n"
            )
            conn.execute(
                "update dino_dev.prize set probability=case id "
                "when 'test_coffee' then 0.20 when 'test_shipping' then 0.05 else 0.75 end"
            )

    def participant(self, label, *, initial=1, invitation=0, pending=0, cooldown=None):
        participant_id = f"p_{label}_{uuid.uuid4().hex}"
        raw_token = secrets.token_urlsafe(32)
        referral_code = f"ref_{label}_{secrets.token_urlsafe(12)}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,
                 environment,initial_balance,invitation_balance,invitation_refund_pending,cooldown_until)
                values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,'test',%s,%s,%s,%s)""",
                (
                    participant_id,
                    CAMPAIGN_ID,
                    token_hash(raw_token),
                    f"TEST_{label}"[:24],
                    referral_code,
                    initial,
                    invitation,
                    pending,
                    cooldown,
                ),
            )
        return {
            "id": participant_id,
            "raw_token": raw_token,
            "token_hash": token_hash(raw_token),
            "referral_code": referral_code,
        }

    def invite_visit(self, inviter, visitor, label):
        visit_id = f"iv_{label}_{uuid.uuid4().hex}"
        nonce = secrets.token_urlsafe(32)
        nonce_hash = token_hash(nonce)
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.invitation_visit
                (id,campaign_id,inviter_id,visitor_id,nonce_hash,expires_at,created_at)
                values(%s,%s,%s,%s,%s,clock_timestamp()+interval '10 minutes',
                       clock_timestamp()-interval '4 seconds')""",
                (visit_id, CAMPAIGN_ID, inviter["id"], visitor["id"], nonce_hash),
            )
        return {"id": visit_id, "nonce": nonce, "nonce_hash": nonce_hash}

    def parallel(self, functions):
        barrier = threading.Barrier(len(functions))

        def invoke(function):
            barrier.wait(timeout=10)
            return function()

        with concurrent.futures.ThreadPoolExecutor(max_workers=len(functions)) as executor:
            futures = [executor.submit(invoke, function) for function in functions]
            return [future.result(timeout=30) for future in futures]

    def qualify(self, inviter, visitor, visit):
        with app_tx() as conn:
            _status, result = operations.qualify_referral(
                conn,
                {
                    "code": inviter["referral_code"],
                    "visit_nonce": visit["nonce"],
                    "active_ms": 3000,
                    "interacted": True,
                },
                context(
                    participant_token_hash=visitor["token_hash"],
                    visit_nonce_hash=visit["nonce_hash"],
                ),
            )
            return result

    def test_one_hundred_concurrent_valid_invites_cap_at_three_and_start_one_cooldown(self):
        inviter = self.participant("inviter_100")
        pairs = []
        for index in range(100):
            visitor = self.participant(f"visitor_{index}")
            pairs.append((visitor, self.invite_visit(inviter, visitor, str(index))))

        results = self.parallel(
            [
                lambda visitor=visitor, visit=visit: self.qualify(inviter, visitor, visit)
                for visitor, visit in pairs
            ]
        )
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            participant = conn.execute(
                "select invitation_balance,invitation_refund_pending,cooldown_until "
                "from dino_dev.participant where id=%s",
                (inviter["id"],),
            ).fetchone()
            rewards = conn.execute(
                "select count(*) n from dino_dev.invitation_reward where inviter_id=%s",
                (inviter["id"],),
            ).fetchone()["n"]
            ledger = conn.execute(
                """select count(*) n,count(*) filter(where cooldown_until is not null) cooldown_rows,
                   max(balance_after) max_balance from dino_dev.ticket_ledger
                   where participant_id=%s and source_type='INVITATION_GRANT'""",
                (inviter["id"],),
            ).fetchone()
            pending_visits = conn.execute(
                "select count(*) n from dino_dev.invitation_visit "
                "where inviter_id=%s and status='PENDING'",
                (inviter["id"],),
            ).fetchone()["n"]

        self.assertEqual(sum(result["status"] == "REWARDED" for result in results), 3)
        self.assertTrue(all(result["status"] in {"REWARDED", "COOLDOWN"} for result in results))
        self.assertEqual((participant["invitation_balance"], participant["invitation_refund_pending"]), (3, 0))
        self.assertIsNotNone(participant["cooldown_until"])
        self.assertEqual(rewards, 3)
        self.assertEqual((ledger["n"], ledger["cooldown_rows"], ledger["max_balance"]), (3, 1, 3))
        self.assertEqual(pending_visits, 0)

    def test_same_visitor_can_reward_two_different_inviters_concurrently(self):
        inviter_a = self.participant("inviter_a")
        inviter_b = self.participant("inviter_b")
        visitor = self.participant("shared_visitor")
        visit_a = self.invite_visit(inviter_a, visitor, "a")
        visit_b = self.invite_visit(inviter_b, visitor, "b")

        results = self.parallel(
            [
                lambda: self.qualify(inviter_a, visitor, visit_a),
                lambda: self.qualify(inviter_b, visitor, visit_b),
            ]
        )
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            balances = conn.execute(
                "select id,invitation_balance from dino_dev.participant where id=any(%s)",
                ([inviter_a["id"], inviter_b["id"]],),
            ).fetchall()
            rewards = conn.execute(
                "select count(*) n from dino_dev.invitation_reward where visitor_id=%s",
                (visitor["id"],),
            ).fetchone()["n"]
        self.assertEqual([result["status"] for result in results], ["REWARDED", "REWARDED"])
        self.assertEqual({row["invitation_balance"] for row in balances}, {1})
        self.assertEqual(rewards, 2)

    def test_visits_started_while_full_do_not_credit_after_cooldown(self):
        with psycopg.connect(DSN) as conn:
            future = conn.execute("select clock_timestamp()+interval '10 hours'").fetchone()[0]
        inviter = self.participant("full_inviter", invitation=3, cooldown=future)
        visitors = [self.participant(f"full_visitor_{index}") for index in range(10)]

        def start_visit(visitor):
            nonce = secrets.token_urlsafe(32)
            with app_tx() as conn:
                _status, result = operations.participant_init(
                    conn,
                    {"invite_code": inviter["referral_code"]},
                    context(
                        participant_token_hash=visitor["token_hash"],
                        invite_nonce=nonce,
                        invite_nonce_hash=token_hash(nonce),
                    ),
                )
                return result["invite_visit"]

        started = self.parallel(
            [lambda visitor=visitor: start_visit(visitor) for visitor in visitors]
        )
        self.assertTrue(
            all(visit["status"] == "COOLDOWN" and visit["visit_nonce"] is None for visit in started)
        )

        with psycopg.connect(DSN) as conn:
            conn.execute(
                "update dino_dev.participant set invitation_balance=2,"
                "cooldown_until=clock_timestamp()-interval '1 second' where id=%s",
                (inviter["id"],),
            )
        with app_tx() as conn:
            _status, restored = operations.referral_me(
                conn, context(participant_token_hash=inviter["token_hash"])
            )
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            state = conn.execute(
                "select invitation_balance from dino_dev.participant where id=%s",
                (inviter["id"],),
            ).fetchone()
            rewards = conn.execute(
                "select count(*) n from dino_dev.invitation_reward where inviter_id=%s",
                (inviter["id"],),
            ).fetchone()["n"]
            rejected = conn.execute(
                "select count(*) n from dino_dev.invitation_visit "
                "where inviter_id=%s and status='COOLDOWN'",
                (inviter["id"],),
            ).fetchone()["n"]
        self.assertEqual(restored["invitation_balance"], 2)
        self.assertEqual(state["invitation_balance"], 2)
        self.assertEqual(rewards, 0)
        self.assertEqual(rejected, 10)

    def eligible_participant(self, label):
        participant = self.participant(label, initial=0)
        session_id = f"gs_{label}_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
                 ticket_refund_status,expires_at,score,valid_ticks,verification_result,finished_at,environment)
                values(%s,%s,%s,%s,1,'1.2.0','FINISHED','INITIAL','NOT_DUE',
                       clock_timestamp()+interval '1 hour',10,60,'VERIFIED',clock_timestamp(),'test')""",
                (session_id, participant["id"], CAMPAIGN_ID, f"idem_{session_id}"),
            )
        return participant

    def draw(self, participant):
        last_error = None
        for _attempt in range(20):
            try:
                with app_tx() as conn:
                    return operations.create_draw(
                        conn,
                        {"pouch_index": 0},
                        context(
                            participant_token_hash=participant["token_hash"],
                            idempotency_key=f"draw_{participant['id']}",
                        ),
                    )[1]
            except operations.DomainError as error:
                if error.code != "INVENTORY_BUSY":
                    raise
                last_error = error
                time.sleep(0.01)
        raise last_error

    def test_last_inventory_concurrent_draw_allocates_once_and_lock_is_not_fake_no_prize(self):
        participants = [self.eligible_participant(f"draw_{index}") for index in range(24)]
        with psycopg.connect(DSN) as conn:
            conn.execute(
                "update dino_dev.prize set probability=case when id='test_coffee' then 1 else 0 end"
            )
            conn.execute(
                "update dino_dev.inventory_item set status=case "
                "when id='test_coffee_001' then 'AVAILABLE' else 'VOID' end,"
                "reserved_by_draw_id=null,reserved_at=null,paid_at=null"
            )

        blocker = psycopg.connect(DSN)
        blocker.execute(
            "select id from dino_dev.inventory_item where id='test_coffee_001' for update"
        )
        try:
            locked_results = self.parallel(
                [
                    lambda participant=participant: self._draw_error(participant)
                    for participant in participants[:8]
                ]
            )
        finally:
            blocker.rollback()
            blocker.close()
        self.assertEqual(locked_results, ["INVENTORY_BUSY"] * 8)
        with psycopg.connect(DSN) as conn:
            self.assertEqual(conn.execute("select count(*) from dino_dev.draw").fetchone()[0], 0)

        results = self.parallel(
            [lambda participant=participant: self.draw(participant) for participant in participants]
        )
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            counts = conn.execute(
                """select count(*) n,count(*) filter(where inventory_item_id is not null) allocated,
                   count(*) filter(where prize_id='test_no_prize') no_prize from dino_dev.draw"""
            ).fetchone()
            inventory = conn.execute(
                "select status,reserved_by_draw_id from dino_dev.inventory_item "
                "where id='test_coffee_001'"
            ).fetchone()
        self.assertEqual(sum(result["is_won"] for result in results), 1)
        self.assertEqual((counts["n"], counts["allocated"], counts["no_prize"]), (24, 1, 23))
        self.assertEqual(inventory["status"], "RESERVED")
        self.assertIsNotNone(inventory["reserved_by_draw_id"])

    def _draw_error(self, participant):
        try:
            with app_tx() as conn:
                operations.create_draw(
                    conn,
                    {"pouch_index": 0},
                    context(
                        participant_token_hash=participant["token_hash"],
                        idempotency_key=f"locked_draw_{participant['id']}",
                    ),
                )
        except operations.DomainError as error:
            return error.code
        return "DRAW_CREATED"

    def test_parallel_same_idempotency_key_consumes_one_ticket_once(self):
        participant = self.participant("same_idem")
        idempotency_key = "same-start-key-0123456789"

        def create():
            with app_tx() as conn:
                return operations.create_session(
                    conn,
                    {"event_id": "evt_same_parallel_start"},
                    context(
                        participant_token_hash=participant["token_hash"],
                        idempotency_key=idempotency_key,
                    ),
                )[1]

        results = self.parallel([create for _index in range(40)])
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            state = conn.execute(
                "select initial_balance from dino_dev.participant where id=%s",
                (participant["id"],),
            ).fetchone()
            sessions = conn.execute(
                "select count(*) n,min(id) only_id from dino_dev.game_session where participant_id=%s",
                (participant["id"],),
            ).fetchone()
            consumes = conn.execute(
                "select count(*) n from dino_dev.ticket_ledger "
                "where participant_id=%s and source_type='PLAY_CONSUME'",
                (participant["id"],),
            ).fetchone()["n"]
        self.assertEqual({result["session_id"] for result in results}, {sessions["only_id"]})
        self.assertEqual((state["initial_balance"], sessions["n"], consumes), (0, 1, 1))

    def test_concurrent_grant_and_refund_reservation_never_exceeds_cap(self):
        inviter = self.participant("grant_refund", initial=0, invitation=2, pending=1)
        visitor = self.participant("grant_refund_visitor")
        visit = self.invite_visit(inviter, visitor, "grant_refund")
        session_id = f"gs_grant_refund_{uuid.uuid4().hex}"
        with psycopg.connect(DSN) as conn:
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
                 ticket_refund_status,started_at,expires_at,last_checkpoint_tick,fault_reason,
                 fault_reported_at,fault_review_status,fault_review_version,environment)
                values(%s,%s,%s,%s,1,'1.2.0','FAULT_REPORTED','INVITATION','PENDING',
                       clock_timestamp()-interval '20 seconds',clock_timestamp()+interval '1 hour',
                       120,'NETWORK_ERROR',clock_timestamp()-interval '11 seconds','PENDING',1,'test')""",
                (session_id, inviter["id"], CAMPAIGN_ID, f"idem_{session_id}"),
            )
            conn.execute(
                """insert into dino_dev.ticket_ledger
                (participant_id,ticket_kind,delta,source_type,source_id,balance_after)
                values(%s,'INVITATION',-1,'PLAY_CONSUME',%s,2)""",
                (inviter["id"], session_id),
            )

        def refund():
            with app_tx() as conn:
                return operations.get_session(
                    conn,
                    session_id,
                    context(participant_token_hash=inviter["token_hash"]),
                )[1]

        grant_result, refund_result = self.parallel(
            [lambda: self.qualify(inviter, visitor, visit), refund]
        )
        with psycopg.connect(DSN, row_factory=dict_row) as conn:
            state = conn.execute(
                "select invitation_balance,invitation_refund_pending from dino_dev.participant where id=%s",
                (inviter["id"],),
            ).fetchone()
            counts = conn.execute(
                """select count(*) filter(where source_type='INVITATION_GRANT') grants,
                   count(*) filter(where source_type='FAULT_REFUND') refunds
                   from dino_dev.ticket_ledger where participant_id=%s""",
                (inviter["id"],),
            ).fetchone()
        self.assertIn(grant_result["status"], {"BALANCE_FULL", "COOLDOWN"})
        self.assertEqual(refund_result["refund"]["status"], "REFUNDED")
        self.assertEqual(refund_result["fault_review"]["status"], "AUTO_APPROVED")
        self.assertEqual((state["invitation_balance"], state["invitation_refund_pending"]), (3, 0))
        self.assertLessEqual(state["invitation_balance"] + state["invitation_refund_pending"], 3)
        self.assertEqual((counts["grants"], counts["refunds"]), (0, 1))


if __name__ == "__main__":
    unittest.main()
