import contextlib
import datetime as dt
import hashlib
import json
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
sys.path.insert(0, str(ROOT / "tests"))

import operations
from test_migration_acceptance import (
    ADDITIONS, CLAIM_DRAFT, CLAIM_FIX, FOUNDATION, GAME_V21,
    INTERRUPTED_AND_SHARE, KAKAO_SHARE_WEBHOOK, LOW_SCORE_REFUND, PHASE2,
    PHASE3, RANKING_FINALIZATION, REAL_TOP3_CONTACT, TemporaryAuditDatabase,
)

UTC = dt.timezone.utc
CAMPAIGN_ID = "phase3-ranking-finalization-test"
MIGRATIONS = (
    FOUNDATION, ADDITIONS, CLAIM_FIX, PHASE2, GAME_V21, REAL_TOP3_CONTACT,
    CLAIM_DRAFT, LOW_SCORE_REFUND, KAKAO_SHARE_WEBHOOK, INTERRUPTED_AND_SHARE,
    PHASE3, RANKING_FINALIZATION,
)


@unittest.skipUnless(Path("/private/tmp/dino-phase1-v2-postgres/bin/psql").exists(), "isolated local PostgreSQL fixture is unavailable")
class Phase3RankingFinalizationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.database = TemporaryAuditDatabase()
        try:
            cls.database.create()
        except psycopg.OperationalError as error:
            raise unittest.SkipTest(f"isolated local PostgreSQL fixture is unavailable: {error}") from error
        for migration in MIGRATIONS:
            cls.database.apply(migration)

    @classmethod
    def tearDownClass(cls):
        if hasattr(cls, "database"):
            cls.database.drop()

    def setUp(self):
        self.now = dt.datetime.now(UTC)
        self.closes_at = self.now - dt.timedelta(minutes=2)
        settings = {
            "ranking_finalization_approved": True,
            "ranking_finish_acceptance_cutoff": self.closes_at.isoformat(),
            "claim_submission_cutoff": (self.now + dt.timedelta(days=1)).isoformat(),
        }
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """truncate dino_dev.idempotency_request,dino_dev.admin_audit,dino_dev.ranking_award,
                dino_dev.ranking_snapshot_entry,dino_dev.ranking_snapshot,dino_dev.claim_contact_draft,
                dino_dev.claim_contact,dino_dev.claim,dino_dev.inventory_history,dino_dev.draw_pool_slot,
                dino_dev.draw_credit_ledger,dino_dev.draw,dino_dev.inventory_item,dino_dev.prize,
                dino_dev.ranking_contact_version,dino_dev.ranking_contact,dino_dev.versioned_best_score,
                dino_dev.best_score,dino_dev.game_session,dino_dev.ticket_ledger,dino_dev.participant,
                dino_dev.admin_member,dino_dev.environment_guard,dino_dev.campaign restart identity cascade"""
            )
            conn.execute(
                """insert into dino_dev.campaign
                (id,title,game_version,benefit_url,probability_version,opens_at,closes_at,settings)
                values(%s,'Ranking finalization','1.2.0','https://gemini.google.com/students','rank-v1',
                  %s,%s,%s::jsonb)""",
                (CAMPAIGN_ID, self.closes_at-dt.timedelta(days=1), self.closes_at, json.dumps(settings)),
            )
            conn.execute(
                "insert into dino_dev.environment_guard(environment,project_ref,test_seed,campaign_id) values('test','local',true,%s)",
                (CAMPAIGN_ID,),
            )
            self.admin_id = str(uuid.uuid4())
            conn.execute(
                """insert into dino_dev.admin_member(auth_user_id,display_name,permissions)
                values(%s,'TEST ranking admin',array['ranking:read','ranking:write','claims:write'])""",
                (self.admin_id,),
            )
        self.seed_ranked_players()
        self.seed_ranking_inventory()

    @contextlib.contextmanager
    def app_tx(self):
        with psycopg.connect(self.database.dsn, row_factory=dict_row) as conn:
            with conn.transaction():
                conn.execute("set local role dino_dev_app")
                yield conn

    def admin_ctx(self, **extra):
        return {
            "admin_user_id": self.admin_id,
            "campaign_id": CAMPAIGN_ID,
            "environment": "test",
            "deployment": "ranking-test",
            "event_version": "phase3-v1",
            "game_version": "1.2.0",
            **extra,
        }

    def participant_ctx(self, participant_id, **extra):
        return {
            "participant_token_hash": (participant_id[-1] * 64),
            "campaign_id": CAMPAIGN_ID,
            "environment": "test",
            "deployment": "ranking-test",
            "event_version": "phase3-v1",
            "game_version": "1.2.0",
            "preview_unlimited_play": True,
            **extra,
        }

    def seed_ranked_players(self):
        # Same-score order is achieved_at first, then participant_id.
        players = (
            ("rank_b", 500, 1),
            ("rank_a", 500, 2),
            ("rank_c", 500, 2),
            ("rank_d", 400, 3),
        )
        with psycopg.connect(self.database.dsn) as conn:
            for participant_id, score, offset in players:
                conn.execute(
                    """insert into dino_dev.participant
                    (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                    values(%s,%s,%s,clock_timestamp()+interval '2 days',%s,%s,'test')""",
                    (participant_id, CAMPAIGN_ID, participant_id[-1]*64, participant_id, f"ref_{participant_id}_0000"),
                )
                session_id = f"session_{participant_id}"
                achieved = self.closes_at - dt.timedelta(minutes=10) + dt.timedelta(seconds=offset)
                conn.execute(
                    """insert into dino_dev.game_session
                    (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
                     ticket_refund_status,expires_at,score,valid_ticks,verification_result,finished_at,environment)
                    values(%s,%s,%s,%s,1,'1.2.0','FINISHED','INITIAL','NOT_DUE',%s,%s,60,'VERIFIED',%s,'test')""",
                    (session_id, participant_id, CAMPAIGN_ID, f"key_{participant_id}", achieved+dt.timedelta(minutes=1), score, achieved),
                )
                conn.execute(
                    "insert into dino_dev.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,%s,%s)",
                    (participant_id, session_id, score, achieved),
                )

    def seed_ranking_inventory(self):
        with psycopg.connect(self.database.dsn) as conn:
            for rank in (1, 2, 3):
                prize_id = f"rank_prize_{rank}"
                inventory_id = f"rank_inventory_{rank}"
                conn.execute(
                    """insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability)
                    values(%s,%s,%s,'COUPON','/rank.png',0)""",
                    (prize_id, CAMPAIGN_ID, f"Rank {rank} prize"),
                )
                conn.execute("insert into dino_dev.inventory_item(id,prize_id) values(%s,%s)", (inventory_id, prize_id))
                conn.execute(
                    "insert into dino_dev.ranking_award(campaign_id,rank,prize_id,inventory_item_id) values(%s,%s,%s,%s)",
                    (CAMPAIGN_ID, rank, prize_id, inventory_id),
                )

    def review_top3(self, conn, snapshot, outcome="APPROVED", event_prefix="evt_review"):
        participant_ids = [row["participant_id"] for row in conn.execute(
            "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank<=3 order by rank",
            (snapshot["id"],),
        ).fetchall()]
        for index, participant_id in enumerate(participant_ids, 1):
            operations.review_admin_ranking_candidate(conn, snapshot["id"], {
                "participant_id": participant_id,
                "outcome": outcome,
                "reason": f"TEST gameplay review {index}",
                "evidence_reference": f"TEST_REF_rank_review_{index}",
                "event_id": f"{event_prefix}_{index}",
            }, self.admin_ctx())

    def test_ranking_order_snapshot_finalization_and_manual_payment_are_consistent_and_idempotent(self):
        with self.app_tx() as conn:
            public = operations.leaderboard(conn, {"view": "milestones"}, self.participant_ctx("rank_d"))[1]
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id": "evt_snapshot_final"}, self.admin_ctx())[1]
            entries = conn.execute(
                "select participant_id,score,rank,tied,achieved_at from dino_dev.ranking_snapshot_entry where snapshot_id=%s order by rank",
                (snapshot["id"],),
            ).fetchall()
        self.assertEqual([(r["participant_id"], r["rank"]) for r in entries], [("rank_b",1),("rank_a",2),("rank_c",3),("rank_d",4)])
        self.assertEqual([(r["rank"],r["score"]) for r in public["leaderboard"][:4]], [(1,500),(2,500),(3,500),(4,400)])
        self.assertEqual(public["rank_targets"], [{"rank":1,"score":500},{"rank":2,"score":500},{"rank":3,"score":500}])
        self.assertEqual((public["me"]["rank"], public["top3_gap"]["third_score"]), (4,500))
        self.assertEqual(public["tie_policy"], "EARLIEST_ACHIEVED_AT")

        with self.app_tx() as conn:
            first_candidate = entries[0]["participant_id"]
            review_path = f"/api/admin/ranking-snapshots/{snapshot['id']}/reviews"
            review_body = {"participant_id":first_candidate,"outcome":"APPROVED","reason":"TEST endpoint review",
                           "evidence_reference":"TEST_REF_endpoint_review","event_id":"evt_endpoint_review"}
            review_ctx = self.admin_ctx(idempotency_key="idem-endpoint-review")
            reviewed = operations.dispatch(conn,"POST",review_path,review_body,{},review_ctx)
            replayed_review = operations.dispatch(conn,"POST",review_path,review_body,{},review_ctx)
            endpoint_audits = conn.execute(
                "select count(*)::int n from dino_dev.admin_audit where action='RANKING_GAMEPLAY_REVIEW' and event_id='evt_endpoint_review'"
            ).fetchone()["n"]
            self.assertEqual((reviewed[0], replayed_review, endpoint_audits), (200, reviewed, 1))
            self.review_top3(conn, snapshot)
            status, finalized = operations.finalize_admin_ranking_snapshot(
                conn, snapshot["id"], {"event_id":"evt_finalize_rank","reason":"TEST final ranking"}, self.admin_ctx()
            )
            replay_status, replay = operations.finalize_admin_ranking_snapshot(
                conn, snapshot["id"], {"event_id":"unused_replay"}, self.admin_ctx()
            )
            state = conn.execute(
                """select
                (select count(*) from dino_dev.ranking_award where snapshot_id=%s)::int awards,
                (select count(*) from dino_dev.claim where claim_type='RANKING' and inventory_item_id is not null)::int claims,
                (select count(*) from dino_dev.inventory_item where status='RESERVED')::int reserved,
                (select count(*) from dino_dev.inventory_history where reason='RANKING_FINALIZED')::int history""",
                (snapshot["id"],),
            ).fetchone()
        self.assertEqual((status,replay_status,finalized["status"],replay["id"]),(200,200,"FINAL",snapshot["id"]))
        self.assertEqual(tuple(state.values()), (3,3,3,3))

        winner = finalized["awards"][0]
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.claim_contact
                (claim_id,recipient_name,contact,school,synthetic,consent_at,consent_version)
                values(%s,'TEST winner','01000000000','TEST school',true,clock_timestamp(),'claim-contact-v1')""",
                (winner["claim_id"],),
            )
            conn.execute(
                """update dino_dev.claim set status='CONTACTED',contact_submitted_at=clock_timestamp(),
                contacted_at=clock_timestamp(),verification_status='VERIFIED',verification_reference='TEST_REF_rank_winner'
                where id=%s""",
                (winner["claim_id"],),
            )
        with self.app_tx() as conn:
            paid = operations.admin_claim_patch(conn, winner["claim_id"], {
                "status":"PAID","expected_version":1,"external_delivery":True,
                "reason":"TEST delivered","event_id":"evt_rank_paid",
            }, self.admin_ctx())[1]
        self.assertEqual(paid["status"], "PAID")

    def test_gameplay_reviews_gate_finalization_and_are_separate_from_eligibility(self):
        with self.app_tx() as conn:
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id":"evt_snapshot_review_gate"}, self.admin_ctx())[1]
            listed = operations.admin_ranking_snapshots(conn, self.admin_ctx())[1]["snapshots"][0]
            with self.assertRaises(operations.DomainError) as unreviewed:
                operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_finalize_unreviewed"}, self.admin_ctx())
        self.assertEqual(unreviewed.exception.code, "RANKING_GAMEPLAY_REVIEW_REQUIRED")
        self.assertEqual([(row["rank"], row["score"], row["elapsed_seconds"], row["summary"]) for row in listed["candidates"]],
                         [(1,500,1.0,{}),(2,500,1.0,{}),(3,500,1.0,{})])

        with self.app_tx() as conn:
            self.review_top3(conn, snapshot)
            held_id = conn.execute(
                "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank=2",
                (snapshot["id"],),
            ).fetchone()["participant_id"]
            operations.review_admin_ranking_candidate(conn, snapshot["id"], {
                "participant_id": held_id, "outcome":"HOLD", "reason":"TEST suspicious input pattern",
                "evidence_reference":"TEST_REF_rank_hold", "event_id":"evt_review_hold",
            }, self.admin_ctx())
            with self.assertRaises(operations.DomainError) as held:
                operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_finalize_held"}, self.admin_ctx())
        self.assertEqual(held.exception.code, "RANKING_GAMEPLAY_REVIEW_ON_HOLD")

        with psycopg.connect(self.database.dsn) as conn:
            review_count = conn.execute(
                "select count(*) from dino_dev.admin_audit where action='RANKING_GAMEPLAY_REVIEW' and target_id=%s",
                (f"{snapshot['id']}:{held_id}",),
            ).fetchone()[0]
            claim_verifications = conn.execute("select count(*) from dino_dev.claim where verification_status<>'NOT_REQUESTED'").fetchone()[0]
        self.assertEqual((review_count, claim_verifications), (2, 0))

    def test_review_requires_ranking_write_and_rejects_a_stale_candidate_binding(self):
        with self.app_tx() as conn:
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id":"evt_snapshot_stale_review"}, self.admin_ctx())[1]
            participant_id = conn.execute(
                "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank=1",
                (snapshot["id"],),
            ).fetchone()["participant_id"]
        with psycopg.connect(self.database.dsn) as conn:
            readonly_id = str(uuid.uuid4())
            conn.execute("insert into dino_dev.admin_member(auth_user_id,display_name,permissions) values(%s,'TEST read only',array['ranking:read'])",(readonly_id,))
        review_body = {"participant_id":participant_id,"outcome":"APPROVED","reason":"TEST reviewed gameplay",
                       "evidence_reference":"TEST_REF_rank_stale","event_id":"evt_review_permission"}
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as wrong_campaign:
            operations.review_admin_ranking_candidate(conn, snapshot["id"], review_body, self.admin_ctx(campaign_id="other-campaign"))
        self.assertEqual(wrong_campaign.exception.code, "CAMPAIGN_NOT_CONFIGURED")
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as forbidden:
            operations.review_admin_ranking_candidate(conn, snapshot["id"], review_body, self.admin_ctx(admin_user_id=readonly_id))
        self.assertEqual(forbidden.exception.code, "ADMIN_FORBIDDEN")

        with self.app_tx() as conn:
            self.review_top3(conn, snapshot, event_prefix="evt_stale_approved")
        with psycopg.connect(self.database.dsn) as conn:
            achieved = self.closes_at-dt.timedelta(minutes=1)
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
                 expires_at,score,valid_ticks,verification_result,finished_at,environment)
                values('session_rank_b_new',%s,%s,'key_rank_b_new',2,'1.2.0','FINISHED','INITIAL','NOT_DUE',%s,600,120,'VERIFIED',%s,'test')""",
                (participant_id,CAMPAIGN_ID,achieved+dt.timedelta(minutes=1),achieved),
            )
            conn.execute("update dino_dev.best_score set session_id='session_rank_b_new',score=600,achieved_at=%s where participant_id=%s",(achieved,participant_id))
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as stale:
            operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_finalize_stale_review"}, self.admin_ctx())
        self.assertEqual(stale.exception.code, "RANKING_CANDIDATE_STALE")

    def test_blocked_candidate_cannot_be_finalized_or_auto_replaced(self):
        with self.app_tx() as conn:
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id":"evt_snapshot_blocked"}, self.admin_ctx())[1]
            self.review_top3(conn, snapshot, event_prefix="evt_blocked_approved")
            blocked_id = conn.execute(
                "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank=2",
                (snapshot["id"],),
            ).fetchone()["participant_id"]
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute("update dino_dev.participant set status='BLOCKED' where id=%s",(blocked_id,))
        with self.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as approval:
                operations.review_admin_ranking_candidate(conn, snapshot["id"], {
                    "participant_id":blocked_id,"outcome":"APPROVED","reason":"TEST cannot approve blocked",
                    "evidence_reference":"TEST_REF_blocked_reapproval","event_id":"evt_blocked_reapproval",
                }, self.admin_ctx())
            rank_four = conn.execute(
                "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank=4",
                (snapshot["id"],),
            ).fetchone()["participant_id"]
            with self.assertRaises(operations.DomainError) as blocked:
                operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_finalize_blocked_candidate"}, self.admin_ctx())
        self.assertEqual(approval.exception.code, "RANKING_PARTICIPANT_BLOCKED")
        self.assertEqual(blocked.exception.code, "RANKING_PARTICIPANT_BLOCKED")
        with psycopg.connect(self.database.dsn) as conn:
            auto_award = conn.execute("select count(*) from dino_dev.ranking_award where participant_id=%s",(rank_four,)).fetchone()[0]
        self.assertEqual(auto_award, 0)

    def test_finalization_waits_for_concurrent_participant_status_change(self):
        with self.app_tx() as conn:
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id":"evt_snapshot_concurrent_block"}, self.admin_ctx())[1]
            self.review_top3(conn, snapshot, event_prefix="evt_concurrent_approved")
            blocked_id = conn.execute(
                "select participant_id from dino_dev.ranking_snapshot_entry where snapshot_id=%s and rank=2",
                (snapshot["id"],),
            ).fetchone()["participant_id"]

        result = []
        def finalize():
            try:
                with self.app_tx() as conn:
                    operations.finalize_admin_ranking_snapshot(
                        conn, snapshot["id"], {"event_id":"evt_finalize_concurrent_block"}, self.admin_ctx()
                    )
            except operations.DomainError as error:
                result.append(error.code)

        with psycopg.connect(self.database.dsn) as blocker:
            blocker.execute("select id from dino_dev.participant where id=%s for update",(blocked_id,))
            thread = threading.Thread(target=finalize)
            thread.start()
            time.sleep(0.2)
            self.assertTrue(thread.is_alive(), "finalization should wait for the candidate participant lock")
            blocker.execute("update dino_dev.participant set status='BLOCKED' where id=%s",(blocked_id,))
        thread.join(timeout=5)
        self.assertFalse(thread.is_alive())
        self.assertEqual(result, ["RANKING_PARTICIPANT_BLOCKED"])

    def test_finalization_is_fail_closed_until_approved_cutoff_settled_and_fresh_snapshot_exists(self):
        with self.app_tx() as conn:
            snapshot = operations.create_admin_ranking_snapshot(conn, {"event_id":"evt_snapshot_gate"}, self.admin_ctx())[1]
        with psycopg.connect(self.database.dsn) as conn:
            unauthorized_id=str(uuid.uuid4())
            conn.execute("insert into dino_dev.admin_member(auth_user_id,display_name,permissions) values(%s,'TEST read only',array['ranking:read'])",(unauthorized_id,))
            conn.execute("update dino_dev.campaign set settings=settings||'{\"ranking_finalization_approved\":false}'::jsonb where id=%s", (CAMPAIGN_ID,))
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as forbidden:
            operations.finalize_admin_ranking_snapshot(conn,snapshot["id"],{"event_id":"evt_forbidden"},self.admin_ctx(admin_user_id=unauthorized_id))
        self.assertEqual(forbidden.exception.code,"ADMIN_FORBIDDEN")
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as blocked:
            operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_blocked"}, self.admin_ctx())
        self.assertEqual(blocked.exception.code, "RANKING_FINALIZATION_NOT_READY")
        with psycopg.connect(self.database.dsn) as conn:
            future = dt.datetime.now(UTC)+dt.timedelta(minutes=1)
            conn.execute(
                """update dino_dev.campaign set closes_at=%s,settings=jsonb_build_object(
                'ranking_finalization_approved',true,'ranking_finish_acceptance_cutoff',%s::text,
                'claim_submission_cutoff',%s::text) where id=%s""",
                (future, future.isoformat(), (future+dt.timedelta(days=1)).isoformat(), CAMPAIGN_ID),
            )
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as early:
            operations.finalize_admin_ranking_snapshot(conn, snapshot["id"], {"event_id":"evt_early"}, self.admin_ctx())
        self.assertEqual(early.exception.code, "RANKING_FINALIZATION_TOO_EARLY")
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """update dino_dev.campaign set closes_at=%s,settings=jsonb_build_object(
                'ranking_finalization_approved',true,'ranking_finish_acceptance_cutoff',%s::text,
                'claim_submission_cutoff',%s::text) where id=%s""",
                (self.closes_at,self.closes_at.isoformat(),(self.now+dt.timedelta(days=1)).isoformat(),CAMPAIGN_ID),
            )
            conn.execute("update dino_dev.ranking_snapshot set captured_at=%s where id=%s",(self.closes_at,snapshot["id"]))
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as stale:
            operations.finalize_admin_ranking_snapshot(conn,snapshot["id"],{"event_id":"evt_stale"},self.admin_ctx())
        self.assertEqual(stale.exception.code,"RANKING_SNAPSHOT_STALE")
        with psycopg.connect(self.database.dsn) as conn:
            counts = conn.execute("select count(*) from dino_dev.claim union all select count(*) from dino_dev.inventory_history").fetchall()
        self.assertEqual(counts, [(0,), (0,)])

    def test_same_best_score_retry_keeps_first_server_accepted_timestamp(self):
        participant_id = "rank_equal_retry"
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                values(%s,%s,%s,clock_timestamp()+interval '1 day','equal','ref_equal_retry','test')""",
                (participant_id,CAMPAIGN_ID,participant_id[-1]*64),
            )
            conn.execute("update dino_dev.campaign set opens_at=null,closes_at=null where id=%s",(CAMPAIGN_ID,))
        ctx=self.participant_ctx(participant_id,idempotency_key="equal-first")
        verification={"valid":True,"score":321,"ticks":60,"reason":"VERIFIED","summary":{},"end_reason":"COLLISION"}
        with self.app_tx() as conn:
            _,first=operations.create_session(conn,{},ctx);operations.start_session(conn,first["session_id"],ctx)
            conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '2 seconds' where id=%s",(first["session_id"],))
            operations.finish_session(conn,first["session_id"],{},dict(ctx,verification=verification))
            first_best=conn.execute("select session_id,achieved_at from dino_dev.best_score where participant_id=%s",(participant_id,)).fetchone()
        ctx["idempotency_key"]="equal-second"
        with self.app_tx() as conn:
            _,second=operations.create_session(conn,{},ctx);operations.start_session(conn,second["session_id"],ctx)
            conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '2 seconds' where id=%s",(second["session_id"],))
            operations.finish_session(conn,second["session_id"],{},dict(ctx,verification=verification))
            second_best=conn.execute("select session_id,achieved_at from dino_dev.best_score where participant_id=%s",(participant_id,)).fetchone()
        self.assertEqual(second_best, first_best)

    def test_start_finish_and_claim_submission_use_server_received_cutoffs(self):
        participant_id="rank_window"
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute(
                """insert into dino_dev.participant
                (id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment)
                values(%s,%s,%s,clock_timestamp()+interval '1 day','window','ref_rank_window','test')""",
                (participant_id,CAMPAIGN_ID,participant_id[-1]*64),
            )
            conn.execute(
                """insert into dino_dev.game_session
                (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,expires_at,environment)
                values('window_game',%s,%s,'window-key',1,'1.2.0','RESERVED','INITIAL','NOT_DUE',clock_timestamp()+interval '5 minutes','test')""",
                (participant_id,CAMPAIGN_ID),
            )
        before=self.closes_at-dt.timedelta(seconds=1);after=self.closes_at
        with self.app_tx() as conn:
            operations.start_session(conn,"window_game",self.participant_ctx(participant_id,request_received_at=before))
            conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '2 seconds' where id='window_game'")
            result=operations.finish_session(conn,"window_game",{},self.participant_ctx(participant_id,request_received_at=before,verification={"valid":True,"score":222,"ticks":60,"reason":"VERIFIED","summary":{},"end_reason":"COLLISION"}))[1]
        self.assertEqual(result["status"],"FINISHED")
        with self.app_tx() as conn:
            replay=operations.finish_session(conn,"window_game",{},self.participant_ctx(participant_id,request_received_at=after))[1]
        self.assertEqual(replay["status"],"FINISHED")

        claim_id="claim_window"
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute("insert into dino_dev.claim(id,campaign_id,participant_id,claim_type) values(%s,%s,%s,'RANKING')",(claim_id,CAMPAIGN_ID,participant_id))
            conn.execute("update dino_dev.campaign set settings=jsonb_set(settings,'{claim_submission_cutoff}',to_jsonb(%s::text)) where id=%s",(after.isoformat(),CAMPAIGN_ID))
        body={"name":"TEST user","contact":"01000000000","school":"TEST school","address":"","consent":True,"notice_version":"claim-contact-v1"}
        with self.app_tx() as conn, self.assertRaises(operations.DomainError) as closed:
            operations.claim_draft_post(conn,claim_id,body,self.participant_ctx(participant_id,request_received_at=after))
        self.assertEqual(closed.exception.code,"CLAIM_SUBMISSION_CLOSED")

    def test_post_close_game_rewards_are_zero_while_claim_none_share_remains_available(self):
        participant_id="rank_d";claim_id="claim_post_close"
        callback_token="a"*32;callback_hash=hashlib.sha256(callback_token.encode()).hexdigest()
        claim_token="b"*32;claim_hash=hashlib.sha256(claim_token.encode()).hexdigest()
        with psycopg.connect(self.database.dsn) as conn:
            conn.execute("insert into dino_dev.claim(id,campaign_id,participant_id,claim_type) values(%s,%s,%s,'RANKING')",(claim_id,CAMPAIGN_ID,participant_id))
            conn.execute(
                """insert into dino_dev.kakao_share_intent
                (id,participant_id,campaign_id,kind,reward_type,reward_contract_version,callback_token_hash,environment,expires_at)
                values('share_11111111111111111111111111111111',%s,%s,'retry_invite','GAME',2,%s,'test',clock_timestamp()+interval '30 minutes')""",
                (participant_id,CAMPAIGN_ID,callback_hash),
            )
        share_ctx=self.participant_ctx(
            participant_id,request_received_at=self.now,share_webhook_enabled=True,
            new_share_callback_token=claim_token,new_share_callback_token_hash=claim_hash,
        )
        with self.app_tx() as conn:
            with self.assertRaises(operations.DomainError) as closed:
                operations.create_share_intent(conn,{"kind":"retry_invite"},share_ctx)
            conn.execute("update dino_dev.campaign set status='ENDED',version=version+1,updated_at=clock_timestamp() where id=%s",(CAMPAIGN_ID,))
            _,claim_share=operations.create_share_intent(conn,{"kind":"record_share","claim_id":claim_id},share_ctx)
        self.assertEqual(closed.exception.code,"CAMPAIGN_CLOSED")
        webhook_ctx={
            "kakao_webhook_verified":True,"kakao_resource_id":"resource_game_closed",
            "share_callback_token_hash":callback_hash,"campaign_id":CAMPAIGN_ID,
            "environment":"test","deployment":"ranking-test","event_version":"phase3-v1",
            "request_received_at":self.now,
        }
        with self.app_tx() as conn:
            _,game_result=operations.kakao_share_webhook(conn,{
                "share_id":"share_11111111111111111111111111111111","callback_token":callback_token,
                "CHAT_TYPE":"DirectChat","HASH_CHAT_ID":"friend-hash",
            },webhook_ctx)
            invitation=conn.execute("select invitation_balance from dino_dev.participant where id=%s",(participant_id,)).fetchone()["invitation_balance"]
        self.assertEqual((game_result["reward_status"],invitation),("not_eligible",0))
        claim_webhook={**webhook_ctx,"kakao_resource_id":"resource_claim_none"}
        claim_webhook["share_callback_token_hash"]=claim_hash
        with self.app_tx() as conn:
            _,none_result=operations.kakao_share_webhook(conn,{
                "share_id":claim_share["share_id"],"callback_token":claim_token,
                "CHAT_TYPE":"MemoChat","HASH_CHAT_ID":"self-hash",
            },claim_webhook)
        self.assertEqual((none_result["status"],none_result["reward_status"],none_result["reward_type"]),("confirmed","no_reward","NONE"))


if __name__ == "__main__":
    unittest.main()
