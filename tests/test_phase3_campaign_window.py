import datetime as dt
import json
import secrets
import sys
import unittest
from pathlib import Path

import psycopg

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
import operations
import test_backend_phase1 as fixtures


UTC = dt.timezone.utc
CAMPAIGN_ID = "gemini_dino_phase1_test"


class _ClockResult:
    def __init__(self, now):
        self.now = now

    def execute(self, sql, params=()):
        if sql != "select clock_timestamp() as now":
            raise AssertionError(sql)
        return self

    def fetchone(self):
        return {"now": self.now}


class CampaignWindowHelperTest(unittest.TestCase):
    def test_window_helper_uses_inclusive_open_and_exclusive_close(self):
        opens = dt.datetime(2026, 10, 1, tzinfo=UTC)
        closes = opens + dt.timedelta(hours=1)
        campaign = {"opens_at": opens, "closes_at": closes}
        operations._new_entry_allowed(_ClockResult(opens), campaign)
        operations._new_entry_allowed(_ClockResult(closes - dt.timedelta(microseconds=1)), campaign)
        for now, code in ((opens - dt.timedelta(microseconds=1), "CAMPAIGN_NOT_OPEN"), (closes, "CAMPAIGN_CLOSED")):
            with self.subTest(now=now), self.assertRaises(operations.DomainError) as caught:
                operations._new_entry_allowed(_ClockResult(now), campaign)
            self.assertEqual(caught.exception.code, code)
        operations._new_entry_allowed(_ClockResult(None), {"opens_at": None, "closes_at": None})
        for invalid in (
            {"opens_at": opens, "closes_at": None},
            {"opens_at": "invalid", "closes_at": closes},
            {"opens_at": closes, "closes_at": opens},
        ):
            with self.subTest(invalid=invalid), self.assertRaises(operations.DomainError) as caught:
                operations._new_entry_allowed(_ClockResult(opens), invalid)
            self.assertEqual((caught.exception.code, caught.exception.status), ("CAMPAIGN_WINDOW_INVALID", 503))


class Phase3CampaignWindowTest(unittest.TestCase):
    make_participant = fixtures.BackendPhase1Test.make_participant
    make_finished_session = fixtures.BackendPhase1Test.make_finished_session

    def setUp(self):
        with psycopg.connect(fixtures.DSN) as conn:
            self.original = conn.execute(
                "select status,opens_at,closes_at,settings from dino_dev.campaign where id=%s",
                (CAMPAIGN_ID,),
            ).fetchone()
        fixtures.BackendPhase1Test.setUp(self)
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute("truncate dino_dev.draw_pool_slot,dino_dev.draw_credit_ledger restart identity cascade")
            conn.execute(
                "update dino_dev.campaign set status='ACTIVE',opens_at=null,closes_at=null,settings=settings-'phase3_manifest_hash' where id=%s",
                (CAMPAIGN_ID,),
            )

    def tearDown(self):
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute(
                "update dino_dev.campaign set status=%s,opens_at=%s,closes_at=%s,settings=%s::jsonb where id=%s",
                (*self.original[:3], json.dumps(self.original[3]), CAMPAIGN_ID),
            )

    def ctx(self, raw, key=None):
        return fixtures.context(
            participant_token_hash=fixtures.h(raw),
            idempotency_key=key or secrets.token_urlsafe(24),
        )

    def set_window(self, opens_sql, closes_sql):
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute(
                f"update dino_dev.campaign set opens_at={opens_sql},closes_at={closes_sql} where id=%s",
                (CAMPAIGN_ID,),
            )

    def test_closed_window_rejects_new_game_before_ticket_use_but_allows_replay(self):
        raw, _, created = self.make_participant()
        participant_id = created["participant"]["id"]
        key = "campaign-window-game-" + secrets.token_hex(8)
        self.set_window("clock_timestamp()+interval '1 hour'", "clock_timestamp()+interval '2 hours'")
        with fixtures.app_tx() as conn:
            before = conn.execute("select initial_balance from dino_dev.participant where id=%s", (participant_id,)).fetchone()["initial_balance"]
            with self.assertRaises(operations.DomainError) as caught:
                operations.create_session(conn, {}, self.ctx(raw, key))
            after = conn.execute("select initial_balance from dino_dev.participant where id=%s", (participant_id,)).fetchone()["initial_balance"]
            ledgers = conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s", (participant_id,)).fetchone()["n"]
            sessions = conn.execute("select count(*)::int n from dino_dev.game_session where participant_id=%s", (participant_id,)).fetchone()["n"]
        self.assertEqual((caught.exception.code, before, after, ledgers, sessions), ("CAMPAIGN_NOT_OPEN", 1, 1, 1, 0))

        self.set_window("clock_timestamp()-interval '1 hour'", "clock_timestamp()+interval '1 hour'")
        with fixtures.app_tx() as conn:
            status, created_session = operations.create_session(conn, {}, self.ctx(raw, key))
        self.set_window("clock_timestamp()-interval '2 hours'", "clock_timestamp()-interval '1 hour'")
        with fixtures.app_tx() as conn:
            replay_status, replay = operations.create_session(conn, {}, self.ctx(raw, key))
            ledgers = conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='PLAY_CONSUME'", (participant_id,)).fetchone()["n"]
        self.assertEqual((status, replay_status, replay["session_id"], ledgers), (201, 200, created_session["session_id"], 1))

    def test_closed_window_rejects_new_draw_without_credit_pool_or_inventory_mutation_and_allows_replay(self):
        raw, _, created = self.make_participant()
        participant_id = created["participant"]["id"]
        self.make_finished_session(raw, "campaign-window-closed")
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute(
                """insert into dino_dev.draw_pool_slot
                (campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id)
                values(%s,1,'PRIZE','test_coffee','test_coffee_001')""",
                (CAMPAIGN_ID,),
            )
        self.set_window("clock_timestamp()-interval '2 hours'", "clock_timestamp()-interval '1 hour'")
        with fixtures.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as caught:
                operations.create_draw(conn, {"pouch_index": 0, "expected_round_number": 1}, self.ctx(raw))
            counts = conn.execute(
                """select
                (select count(*) from dino_dev.draw where participant_id=%s)::int draws,
                (select count(*) from dino_dev.draw_credit_ledger where participant_id=%s)::int credits,
                (select count(*) from dino_dev.draw_pool_slot where campaign_id=%s and allocated_draw_id is not null)::int allocated,
                (select count(*) from dino_dev.inventory_item where id='test_coffee_001' and status='AVAILABLE')::int available""",
                (participant_id, participant_id, CAMPAIGN_ID),
            ).fetchone()
        self.assertEqual(caught.exception.code, "CAMPAIGN_CLOSED")
        self.assertEqual(tuple(counts.values()), (0, 0, 0, 1))

        self.set_window("clock_timestamp()-interval '1 hour'", "clock_timestamp()+interval '1 hour'")
        with fixtures.app_tx() as conn:
            status, draw = operations.create_draw(conn, {"pouch_index": 0, "expected_round_number": 1}, self.ctx(raw))
        self.set_window("clock_timestamp()-interval '2 hours'", "clock_timestamp()-interval '1 hour'")
        with fixtures.app_tx() as conn:
            replay_status, replay = operations.create_draw(conn, {"pouch_index": 0, "expected_round_number": 1}, self.ctx(raw))
            counts = conn.execute(
                """select
                (select count(*) from dino_dev.draw where participant_id=%s)::int draws,
                (select count(*) from dino_dev.draw_credit_ledger where participant_id=%s)::int credits,
                (select count(*) from dino_dev.draw_pool_slot where campaign_id=%s and allocated_draw_id is not null)::int allocated""",
                (participant_id, participant_id, CAMPAIGN_ID),
            ).fetchone()
        self.assertEqual((status, replay_status, replay["draw_id"], replay["replayed"]), (201, 200, draw["draw_id"], True))
        self.assertEqual(tuple(counts.values()), (1, 2, 1))


if __name__ == "__main__":
    unittest.main()
