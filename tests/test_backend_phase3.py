import concurrent.futures
import secrets
import sys
import unittest
from pathlib import Path

import psycopg
from psycopg.rows import dict_row

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "server"))
sys.path.insert(0, str(ROOT / "tests"))
import test_backend_phase1 as fixtures
import operations


class BackendPhase3Test(unittest.TestCase):
    make_participant = fixtures.BackendPhase1Test.make_participant
    make_finished_session = fixtures.BackendPhase1Test.make_finished_session
    create_share_intent = fixtures.BackendPhase1Test.create_share_intent
    confirm_share = fixtures.BackendPhase1Test.confirm_share

    def setUp(self):
        fixtures.BackendPhase1Test.setUp(self)
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute("truncate dino_dev.draw_pool_slot,dino_dev.draw_credit_ledger restart identity cascade")
            conn.execute("""update dino_dev.prize set is_active=true
              where campaign_id='gemini_dino_phase1_test' and category='NO_PRIZE'""")

    def ctx(self, raw, **extra):
        return fixtures.context(participant_token_hash=fixtures.h(raw), **extra)

    def seed_benefits(self, count, start=1):
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute(
                """insert into dino_dev.draw_pool_slot(campaign_id,slot_number,outcome_kind)
                select 'gemini_dino_phase1_test',n,'BENEFIT'
                from generate_series(%s::integer,%s::integer)n""",
                (start, start + count - 1),
            )

    def seed_prize(self, slot_number=1, inventory_id="test_coffee_001"):
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute(
                """insert into dino_dev.draw_pool_slot
                (campaign_id,slot_number,outcome_kind,prize_id,inventory_item_id)
                values('gemini_dino_phase1_test',%s,'PRIZE','test_coffee',%s)""",
                (slot_number, inventory_id),
            )

    def draw(self, raw, pouch=0, expected_round_number=None):
        if expected_round_number is None:
            with fixtures.app_tx() as conn:
                expected_round_number = operations.draw_me(conn, self.ctx(raw))[1]["used_count"] + 1
        with fixtures.app_tx() as conn:
            return operations.create_draw(
                conn,
                {"pouch_index": pouch, "expected_round_number": expected_round_number},
                self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)),
            )[1]

    def share(self, raw, kind):
        with fixtures.app_tx() as conn:
            intent, token = self.create_share_intent(conn, raw, kind=kind)
            result = self.confirm_share(conn, intent, token)
        return intent, result

    def test_reward_purpose_is_server_fixed_and_draw_credit_is_separate(self):
        self.seed_benefits(3)
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-purpose")

        first = self.draw(raw)
        self.assertEqual((first["round_number"], first["outcome_kind"]), (1, "BENEFIT"))
        self.assertEqual(first["draw_state"]["available_credits"], 0)

        intent, confirmed = self.share(raw, "draw_retry")
        self.assertEqual((intent["reward_type"], confirmed["reward_type"], confirmed["reward_status"]), ("DRAW", "DRAW", "granted"))
        self.assertEqual(confirmed["draw_state"]["available_credits"], 1)
        second = self.draw(raw, 1)
        self.assertEqual((second["round_number"], second["draw_state"]["used_count"]), (2, 2))

        _game_intent, game = self.share(raw, "record_share")
        _none_intent, none = self.share(raw, "general_share")
        with fixtures.app_tx() as conn:
            person = conn.execute("select invitation_balance from dino_dev.participant where id=%s", (participant["participant"]["id"],)).fetchone()
            state = operations.draw_me(conn, self.ctx(raw))[1]
        self.assertEqual((game["reward_type"], game["reward_status"], person["invitation_balance"]), ("GAME", "granted", 1))
        self.assertEqual((none["reward_type"], none["reward_status"]), ("NONE", "no_reward"))
        self.assertEqual(state["available_credits"], 0)

    def test_benefit_retry_grants_both_once_and_replays_durable_outcomes(self):
        self.seed_benefits(2)
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined")
        self.draw(raw)

        with fixtures.app_tx() as conn:
            intent, token = self.create_share_intent(conn, raw, kind="benefit_retry")
            self.assertEqual((intent["reward_type"], intent["reward_contract_version"], intent["reward_status"]), ("BOTH", 3, "pending"))
            self.assertEqual(intent["rewards"], {
                "game": {"status": "pending", "quantity": 0},
                "draw": {"status": "pending", "quantity": 0},
            })
            stored = conn.execute(
                "select reward_contract_version from dino_dev.kakao_share_intent where id=%s",
                (intent["share_id"],),
            ).fetchone()
            first = self.confirm_share(conn, intent, token, resource_id="resource_combined_once")
            duplicate = self.confirm_share(conn, intent, token, resource_id="resource_combined_replay")
            polled = operations.get_share_intent(conn, intent["share_id"], self.ctx(raw))[1]
            ledgers = conn.execute("""select
              (select count(*)::int from dino_dev.ticket_ledger
               where participant_id=%s and source_type='SHARE_GRANT' and source_id=%s) game_grants,
              (select count(*)::int from dino_dev.draw_credit_ledger
               where participant_id=%s and source_type='SHARE_GRANT' and source_id=%s) draw_grants""",
              (participant["participant"]["id"], intent["share_id"], participant["participant"]["id"], intent["share_id"])).fetchone()

        expected = {
            "game": {"status": "granted", "quantity": 1},
            "draw": {"status": "granted", "quantity": 1},
        }
        self.assertEqual(stored["reward_contract_version"], 3)
        self.assertEqual((first["reward_status"], first["rewards"]), ("granted", expected))
        self.assertEqual((duplicate["duplicate"], duplicate["rewards"]), (True, expected))
        self.assertEqual(polled["rewards"], expected)
        self.assertEqual((first["tickets"]["invitation"], first["draw_state"]["available_credits"]), (1, 1))
        self.assertEqual(tuple(ledgers.values()), (1, 1))

    def test_benefit_retry_at_draw_limit_still_grants_game_only(self):
        self.seed_benefits(10)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-limit")
        self.draw(raw)
        for _index in range(9):
            self.share(raw, "draw_retry")
            self.draw(raw)

        intent, confirmed = self.share(raw, "benefit_retry")
        self.assertEqual(intent["draw_state"]["status"], "EXHAUSTED")
        self.assertEqual(confirmed["reward_status"], "granted")
        self.assertEqual(confirmed["rewards"], {
            "game": {"status": "granted", "quantity": 1},
            "draw": {"status": "blocked_draw_limit", "quantity": 0},
        })
        self.assertEqual((confirmed["tickets"]["invitation"], confirmed["draw_state"]["available_credits"]), (1, 0))

    def test_benefit_retry_grants_draw_when_game_cap_includes_pending_refund(self):
        self.seed_benefits(2)
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-cap")
        self.draw(raw)
        with fixtures.app_tx() as conn:
            conn.execute("""update dino_dev.participant set initial_balance=0,
              invitation_balance=2,invitation_refund_pending=1,cooldown_until=null where id=%s""",
              (participant["participant"]["id"],))
            intent, token = self.create_share_intent(conn, raw, kind="benefit_retry")
            confirmed = self.confirm_share(conn, intent, token)
        self.assertEqual(confirmed["rewards"], {
            "game": {"status": "blocked_cap", "quantity": 0},
            "draw": {"status": "granted", "quantity": 1},
        })
        self.assertEqual((confirmed["reward_status"], confirmed["tickets"]["invitation"],
                          confirmed["draw_state"]["available_credits"]), ("granted", 2, 1))

    def test_benefit_retry_grants_draw_when_game_is_on_cooldown(self):
        self.seed_benefits(2)
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-cooldown")
        self.draw(raw)
        with fixtures.app_tx() as conn:
            conn.execute("""update dino_dev.participant set initial_balance=0,
              invitation_balance=1,invitation_refund_pending=0,
              cooldown_until=clock_timestamp()+interval '1 hour' where id=%s""",
              (participant["participant"]["id"],))
            intent, token = self.create_share_intent(conn, raw, kind="benefit_retry")
            confirmed = self.confirm_share(conn, intent, token)
        self.assertEqual(confirmed["rewards"], {
            "game": {"status": "blocked_cooldown", "quantity": 0},
            "draw": {"status": "granted", "quantity": 1},
        })
        self.assertEqual((confirmed["reward_status"], confirmed["tickets"]["invitation"],
                          confirmed["draw_state"]["available_credits"]), ("granted", 1, 1))

    def test_benefit_retry_blocks_both_after_prize_or_campaign_becomes_ineligible(self):
        self.seed_benefits(1)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-prize")
        self.draw(raw)
        with fixtures.app_tx() as conn:
            draw_intent, draw_token = self.create_share_intent(conn, raw, kind="draw_retry")
            self.confirm_share(conn, draw_intent, draw_token)
            combined, combined_token = self.create_share_intent(conn, raw, kind="benefit_retry")
        self.seed_prize(slot_number=2)
        self.draw(raw)
        with fixtures.app_tx() as conn:
            blocked = self.confirm_share(conn, combined, combined_token)
            with self.assertRaises(operations.DomainError) as unavailable:
                self.create_share_intent(conn, raw, kind="benefit_retry")
        expected_prize = {
            "game": {"status": "blocked_prize_won", "quantity": 0},
            "draw": {"status": "blocked_prize_won", "quantity": 0},
        }
        self.assertEqual((blocked["reward_status"], blocked["rewards"]), ("blocked_prize_won", expected_prize))
        self.assertEqual(unavailable.exception.code, "DRAW_SHARE_NOT_AVAILABLE")

        self.seed_benefits(1, start=3)
        other_raw, _, _participant = self.make_participant()
        self.make_finished_session(other_raw, "phase3-combined-paused")
        self.draw(other_raw)
        with fixtures.app_tx() as conn:
            paused, paused_token = self.create_share_intent(conn, other_raw, kind="benefit_retry")
        try:
            with psycopg.connect(fixtures.DSN) as conn:
                conn.execute("update dino_dev.campaign set status='PAUSED' where id='gemini_dino_phase1_test'")
            with fixtures.app_tx() as conn:
                paused_result = self.confirm_share(conn, paused, paused_token)
        finally:
            with psycopg.connect(fixtures.DSN) as conn:
                conn.execute("update dino_dev.campaign set status='ACTIVE' where id='gemini_dino_phase1_test'")
        self.assertEqual(paused_result["rewards"], {
            "game": {"status": "not_eligible", "quantity": 0},
            "draw": {"status": "not_eligible", "quantity": 0},
        })

    def test_concurrent_duplicate_benefit_retry_webhooks_grant_each_reward_once(self):
        self.seed_benefits(2)
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-race")
        self.draw(raw)
        with fixtures.app_tx() as conn:
            intent, token = self.create_share_intent(conn, raw, kind="benefit_retry")

        def confirm(index):
            with fixtures.app_tx() as conn:
                return self.confirm_share(conn, intent, token, resource_id=f"resource_combined_race_{index}")

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(confirm, range(2)))
        with fixtures.app_tx() as conn:
            counts = conn.execute("""select
              (select count(*)::int from dino_dev.ticket_ledger
               where participant_id=%s and source_type='SHARE_GRANT' and source_id=%s) game_grants,
              (select count(*)::int from dino_dev.draw_credit_ledger
               where participant_id=%s and source_type='SHARE_GRANT' and source_id=%s) draw_grants""",
              (participant["participant"]["id"], intent["share_id"], participant["participant"]["id"], intent["share_id"])).fetchone()
        self.assertEqual(sorted(result["duplicate"] for result in results), [False, True])
        self.assertEqual({str(result["rewards"]) for result in results}, {str(results[0]["rewards"])})
        self.assertEqual(tuple(counts.values()), (1, 1))

    def test_benefit_retry_rejection_and_expiry_persist_not_eligible_components(self):
        self.seed_benefits(1)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-combined-terminal-outcomes")
        self.draw(raw)
        with fixtures.app_tx() as conn:
            rejected_intent, rejected_token = self.create_share_intent(conn, raw, kind="benefit_retry")
            expired_intent, expired_token = self.create_share_intent(conn, raw, kind="benefit_retry")
            rejected = self.confirm_share(
                conn, rejected_intent, rejected_token,
                chat_type="MemoChat", IS_SINGLE_CHATROOM=True,
            )
            conn.execute(
                "update dino_dev.kakao_share_intent set expires_at=clock_timestamp()-interval '1 second' where id=%s",
                (expired_intent["share_id"],),
            )
            expired = self.confirm_share(conn, expired_intent, expired_token)
            stored = conn.execute("""select status,reward_status,game_reward_status,
              game_reward_quantity,draw_reward_status,draw_reward_quantity
              from dino_dev.kakao_share_intent where id=any(%s) order by status""",
              ([rejected_intent["share_id"], expired_intent["share_id"]],)).fetchall()
        expected = {
            "game": {"status": "not_eligible", "quantity": 0},
            "draw": {"status": "not_eligible", "quantity": 0},
        }
        self.assertEqual((rejected["status"], rejected["reward_status"], rejected["rewards"]),
                         ("rejected", "not_eligible", expected))
        self.assertEqual((expired["status"], expired["reward_status"], expired["rewards"]),
                         ("expired", "not_eligible", expected))
        self.assertEqual([tuple(row.values()) for row in stored], [
            ("EXPIRED", "NOT_ELIGIBLE", "NOT_ELIGIBLE", 0, "NOT_ELIGIBLE", 0),
            ("REJECTED", "NOT_ELIGIBLE", "NOT_ELIGIBLE", 0, "NOT_ELIGIBLE", 0),
        ])

    def test_actual_prize_is_terminal_and_late_draw_share_is_not_replayed(self):
        self.seed_benefits(1)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-terminal")
        self.assertEqual(self.draw(raw)["outcome_kind"], "BENEFIT")

        with fixtures.app_tx() as conn:
            granted, granted_token = self.create_share_intent(conn, raw, kind="draw_retry")
            self.confirm_share(conn, granted, granted_token)
            late, late_token = self.create_share_intent(conn, raw, kind="draw_retry")
        self.seed_prize(slot_number=2)
        prize = self.draw(raw)
        self.assertEqual((prize["outcome_kind"], prize["is_actual_prize"], prize["draw_state"]["status"]), ("PRIZE", True, "WON"))

        with fixtures.app_tx() as conn:
            claim_share, _token = self.create_share_intent(conn, raw, kind="prize_share", claim_id=prize["claim_id"])
            self.assertEqual(claim_share["reward_type"], "NONE")
            contract = conn.execute("select reward_contract_version from dino_dev.kakao_share_intent where id=%s", (claim_share["share_id"],)).fetchone()["reward_contract_version"]
            self.assertEqual(contract, 2)
            with self.assertRaises(operations.DomainError) as wrong_kind:
                self.create_share_intent(conn, raw, kind="draw_retry", claim_id=prize["claim_id"])
            blocked = self.confirm_share(conn, late, late_token)
            with self.assertRaises(operations.DomainError) as stopped:
                operations.create_draw(conn, {"pouch_index": 0, "expected_round_number": 3}, self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)))
            conn.execute("""insert into dino_dev.claim(id,campaign_id,participant_id,claim_type)
              select %s,campaign_id,id,'RANKING' from dino_dev.participant where token_hash=%s""",
              ("claim_ranking_alongside_draw", fixtures.h(raw)))
            claims = conn.execute("select count(*)::int n from dino_dev.claim where participant_id=(select id from dino_dev.participant where token_hash=%s)", (fixtures.h(raw),)).fetchone()["n"]
        self.assertEqual(blocked["reward_status"], "blocked_prize_won")
        self.assertEqual(wrong_kind.exception.code, "CLAIM_SHARE_KIND_INVALID")
        self.assertEqual(stopped.exception.code, "DRAW_PRIZE_ALREADY_WON")
        self.assertEqual(claims, 2)

    def test_first_draw_plus_nine_verified_shares_caps_at_ten(self):
        self.seed_benefits(10)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-limit")
        rounds = [self.draw(raw)["round_number"]]
        for _index in range(9):
            _intent, confirmed = self.share(raw, "draw_retry")
            self.assertEqual(confirmed["reward_status"], "granted")
            rounds.append(self.draw(raw)["round_number"])
        self.assertEqual(rounds, list(range(1, 11)))
        with fixtures.app_tx() as conn:
            state = operations.draw_me(conn, self.ctx(raw))[1]
            with self.assertRaises(operations.DomainError) as limited:
                self.create_share_intent(conn, raw, kind="draw_retry")
            ledger = conn.execute("""select count(*) filter(where source_type='FIRST_GRANT') first_grants,
              count(*) filter(where source_type='SHARE_GRANT') share_grants,
              count(*) filter(where source_type='DRAW_CONSUME') consumes,coalesce(sum(delta),0)::int balance
              from dino_dev.draw_credit_ledger where participant_id=(select id from dino_dev.participant where token_hash=%s)""", (fixtures.h(raw),)).fetchone()
        self.assertEqual((state["status"], state["used_count"], state["available_credits"]), ("EXHAUSTED", 10, 0))
        self.assertEqual(limited.exception.code, "DRAW_SHARE_NOT_AVAILABLE")
        self.assertEqual(tuple(ledger.values()), (1, 9, 10, 0))

    def test_concurrent_last_credit_webhooks_and_draw_requests_stop_at_ten(self):
        self.seed_benefits(10)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-last-credit-race")
        self.draw(raw)
        for _index in range(8):
            self.share(raw, "draw_retry")
            self.draw(raw)

        with fixtures.app_tx() as conn:
            first_intent, first_token = self.create_share_intent(conn, raw, kind="draw_retry")
            second_intent, second_token = self.create_share_intent(conn, raw, kind="draw_retry")

        def confirm(intent, token):
            with fixtures.app_tx() as conn:
                return self.confirm_share(conn, intent, token)["reward_status"]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            reward_statuses = list(executor.map(
                lambda pair: confirm(*pair),
                ((first_intent, first_token), (second_intent, second_token)),
            ))
        self.assertEqual(sorted(reward_statuses), ["blocked_draw_limit", "granted"])

        def final_draw():
            with fixtures.app_tx() as conn:
                return operations.create_draw(
                    conn,
                    {"pouch_index": 2, "expected_round_number": 10},
                    self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)),
                )[1]

        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
            results = list(executor.map(lambda _unused: final_draw(), range(2)))
        with fixtures.app_tx() as conn:
            state = operations.draw_me(conn, self.ctx(raw))[1]
            ledger = conn.execute("""select
              count(*) filter(where source_type='SHARE_GRANT')::int share_grants,
              count(*) filter(where source_type='DRAW_CONSUME')::int consumes,
              coalesce(sum(delta),0)::int balance
              from dino_dev.draw_credit_ledger
              where participant_id=(select id from dino_dev.participant where token_hash=%s)""",
              (fixtures.h(raw),)).fetchone()
            draw_count = conn.execute("""select count(*)::int n from dino_dev.draw
              where participant_id=(select id from dino_dev.participant where token_hash=%s)""",
              (fixtures.h(raw),)).fetchone()["n"]
        self.assertEqual({result["draw_id"] for result in results}, {results[0]["draw_id"]})
        self.assertEqual(sorted(result.get("replayed", False) for result in results), [False, True])
        self.assertEqual((state["status"], state["used_count"], state["available_credits"]), ("EXHAUSTED", 10, 0))
        self.assertEqual(tuple(ledger.values()), (9, 10, 0))
        self.assertEqual(draw_count, 10)

    def test_one_pool_slot_is_allocated_once_under_concurrency(self):
        self.seed_prize()
        participants = []
        for index in range(8):
            raw, _, _participant = self.make_participant()
            self.make_finished_session(raw, f"phase3-race-{index}")
            participants.append(raw)

        def invoke(raw):
            try:
                return self.draw(raw)["outcome_kind"]
            except operations.DomainError as error:
                return error.code

        with concurrent.futures.ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(invoke, participants))
        with psycopg.connect(fixtures.DSN) as conn:
            allocated = conn.execute("select count(*) from dino_dev.draw_pool_slot where allocated_draw_id is not null").fetchone()[0]
            reserved = conn.execute("select count(*) from dino_dev.inventory_item where id='test_coffee_001' and status='RESERVED'").fetchone()[0]
            draws = conn.execute("select count(*) from dino_dev.draw where participant_id in (select id from dino_dev.participant where token_hash=any(%s))",( [fixtures.h(raw) for raw in participants],)).fetchone()[0]
            claims = conn.execute("select count(*) from dino_dev.claim where participant_id in (select id from dino_dev.participant where token_hash=any(%s))",( [fixtures.h(raw) for raw in participants],)).fetchone()[0]
        self.assertEqual(results.count("PRIZE"), 1)
        self.assertEqual(results.count("BENEFIT"), 7)
        self.assertEqual((allocated, reserved, draws, claims), (1, 1, 8, 1))

    def test_exhausted_pool_requires_active_benefit_configuration(self):
        self.seed_benefits(1)
        first_raw, _, _participant = self.make_participant()
        second_raw, _, _participant = self.make_participant()
        self.make_finished_session(first_raw, "phase3-benefit-exhaust-first")
        self.make_finished_session(second_raw, "phase3-benefit-exhaust-second")
        self.assertEqual(self.draw(first_raw)["outcome_kind"], "BENEFIT")
        with psycopg.connect(fixtures.DSN) as conn:
            conn.execute("""update dino_dev.prize set is_active=false
              where campaign_id='gemini_dino_phase1_test' and category='NO_PRIZE'""")
        with self.assertRaises(operations.DomainError) as invalid:
            self.draw(second_raw)
        self.assertEqual(invalid.exception.code, "DRAW_CONFIG_INVALID")

    def test_expected_round_replays_same_result_without_spending_next_credit(self):
        self.seed_benefits(2)
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-round-replay")
        first = self.draw(raw, pouch=2, expected_round_number=1)
        self.share(raw, "draw_retry")

        replay = self.draw(raw, pouch=2, expected_round_number=1)
        self.assertEqual((replay["draw_id"], replay["replayed"]), (first["draw_id"], True))
        self.assertEqual((replay["draw_state"]["used_count"], replay["draw_state"]["available_credits"]), (1, 1))
        with fixtures.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as conflict:
                operations.create_draw(
                    conn,
                    {"pouch_index": 1, "expected_round_number": 1},
                    self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)),
                )
            with self.assertRaises(operations.DomainError) as stale:
                operations.create_draw(
                    conn,
                    {"pouch_index": 0, "expected_round_number": 3},
                    self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)),
                )
        self.assertEqual(conflict.exception.code, "DRAW_ROUND_CONFLICT")
        self.assertEqual(stale.exception.code, "DRAW_ROUND_MISMATCH")

    def test_rolling_old_app_draw_is_reconciled_as_consumed_first_credit(self):
        raw, _, participant = self.make_participant()
        self.make_finished_session(raw, "phase3-rolling-old-app")
        with psycopg.connect(fixtures.DSN, row_factory=dict_row) as conn:
            session = conn.execute("""select id from dino_dev.game_session
              where participant_id=%s and status='FINISHED' order by finished_at desc limit 1""",
              (participant["participant"]["id"],)).fetchone()["id"]
            benefit = conn.execute("""select id from dino_dev.prize
              where campaign_id='gemini_dino_phase1_test' and category='NO_PRIZE' limit 1""").fetchone()["id"]
            conn.execute("""insert into dino_dev.draw
              (id,campaign_id,participant_id,eligible_session_id,pouch_index,prize_id,is_won,
               probability_version,random_audit_hash)
              values(%s,'gemini_dino_phase1_test',%s,%s,0,%s,false,'legacy-cutover',%s)""",
              ("draw_legacy_cutover",participant["participant"]["id"],session,benefit,"0"*64))
        with fixtures.app_tx() as conn:
            before = operations.draw_me(conn,self.ctx(raw))[1]
            with self.assertRaises(operations.DomainError) as blocked:
                operations.create_draw(
                    conn,{"pouch_index":1,"expected_round_number":2},
                    self.ctx(raw,idempotency_key=secrets.token_urlsafe(24)),
                )
            ledger = conn.execute("""select source_type,delta,balance_after from dino_dev.draw_credit_ledger
              where participant_id=%s order by id""",(participant["participant"]["id"],)).fetchall()
        self.assertEqual((before["used_count"],before["available_credits"],before["status"]),(1,0,"DRAWN"))
        self.assertEqual(blocked.exception.code,"DRAW_CREDIT_REQUIRED")
        self.assertEqual([tuple(row.values()) for row in ledger],
                         [("FIRST_GRANT",1,1),("DRAW_CONSUME",-1,0)])

    def test_marked_finite_pool_never_falls_back_to_legacy_probability(self):
        raw, _, _participant = self.make_participant()
        self.make_finished_session(raw, "phase3-failclosed")
        with psycopg.connect(fixtures.DSN, row_factory=dict_row) as conn:
            conn.execute("update dino_dev.campaign set settings=jsonb_set(settings,'{phase3_manifest_hash}','\"test-hash\"') where id='gemini_dino_phase1_test'")
            conn.execute("set local role dino_dev_app")
            with self.assertRaises(operations.DomainError) as invalid:
                operations.create_draw(
                    conn,
                    {"pouch_index": 0, "expected_round_number": 1},
                    self.ctx(raw, idempotency_key=secrets.token_urlsafe(24)),
                )
            conn.rollback()
        self.assertEqual(invalid.exception.code, "DRAW_CONFIG_INVALID")


if __name__ == "__main__":
    unittest.main()
