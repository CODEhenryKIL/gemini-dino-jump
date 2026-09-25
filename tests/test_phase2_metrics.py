import datetime as dt
import json
import os
from pathlib import Path
import secrets
import sys
import unittest
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "server"))
import metrics
import psycopg
from psycopg.rows import dict_row


class Phase2MetricsTest(unittest.TestCase):
    def setUp(self):
        url = os.getenv("PHASE1_METRICS_DATABASE_URL", "postgresql://postgres@127.0.0.1:55433/dino_phase1_v2_browser")
        parsed = urlparse(url)
        if parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.path.startswith("/dino_phase1_v2_"):
            raise RuntimeError("Phase 2 metrics fixtures require an isolated local database")
        self.conn = psycopg.connect(url, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.prefix = "phase2_metrics_" + secrets.token_hex(6)
        self.campaign = self.conn.execute("select campaign_id from dino_dev.environment_guard where singleton").fetchone()["campaign_id"]
        self.base = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc)
        self.query = {"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z", "channel": "phase2_metrics"}

    def person(self, suffix, public=False, environment="local"):
        pid = self.prefix + suffix
        self.conn.execute("""insert into dino_dev.participant
          (id,campaign_id,token_hash,token_expires_at,nickname,is_public,referral_code,environment,first_link_kind,first_channel,created_at)
          values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,%s,%s,'record_share','phase2_metrics',%s)""",
          (pid, self.campaign, secrets.token_hex(32), "TEST_" + suffix, public, secrets.token_urlsafe(16), environment, self.base))
        return pid

    def observation(self, suffix, pid):
        oid = self.prefix + "obs_" + suffix
        self.conn.execute("""insert into dino_dev.observation
          (id,event_id,actor_key,idempotency_key,request_hash,participant_id,link_kind,channel_code,environment,created_at)
          values(%s,%s,%s,%s,'hash',%s,'record_share','phase2_metrics','local',%s)""",
          (oid, oid, self.prefix, secrets.token_hex(16), pid, self.base))
        return oid

    def event(self, name, pid, observation, minute, dimensions=None, screen="loading"):
        self.conn.execute("""insert into dino_dev.analytics_event
          (event_id,campaign_id,participant_id,observation_id,event_name,screen,visit_session_id,
           dimensions,environment,deployment,event_version,source,occurred_at,received_at)
          values(%s,%s,%s,%s,%s,%s,%s,%s::jsonb,'local','phase2-metrics','phase2-v1','client',%s,%s)""",
          (self.prefix + secrets.token_hex(8), self.campaign, pid, observation, name, screen, observation,
           json.dumps(dimensions or {}), self.base + dt.timedelta(minutes=minute), self.base + dt.timedelta(minutes=minute)))

    def report(self):
        self.conn.execute("set local role dino_dev_app")
        status, data = metrics.build_overview(self.conn, self.query, {"environment": "local", "game_version": "2.0.0"})
        self.assertEqual(status, 200)
        return data

    def test_v2_score_and_server_game_summary_are_version_scoped(self):
        pid = self.person("game", public=True)
        sid = self.prefix + "game"
        self.conn.execute("""insert into dino_dev.game_session
          (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
           reserved_at,expires_at,score,valid_ticks,verification_result,game_summary,end_reason,finished_at,environment)
          values(%s,%s,%s,%s,4,'2.0.0','FINISHED','INITIAL','NOT_DUE',%s,%s,828,4128,'VERIFIED',%s::jsonb,'COLLISION',%s,'local')""",
          (sid, pid, self.campaign, sid, self.base, self.base + dt.timedelta(hours=1),
           json.dumps({"coins": 14, "coin_score": 140, "hearts": 2, "revives": 2}), self.base))
        self.conn.execute("""insert into dino_dev.versioned_best_score
          (participant_id,game_version,session_id,score,achieved_at) values(%s,'2.0.0',%s,828,%s)""", (pid, sid, self.base))
        outsider = self.person("outsider", public=True, environment="test")
        outsider_sid = self.prefix + "outsider_game"
        self.conn.execute("""insert into dino_dev.game_session
          (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,
           reserved_at,expires_at,score,valid_ticks,verification_result,game_summary,end_reason,finished_at,environment)
          values(%s,%s,%s,%s,4,'2.0.0','FINISHED','INITIAL','NOT_DUE',%s,%s,8999,36000,'VERIFIED',
            '{"coins":299,"coin_score":2990,"hearts":0,"revives":0}'::jsonb,'TIME_LIMIT',%s,'test')""",
          (outsider_sid, outsider, self.campaign, outsider_sid, self.base, self.base + dt.timedelta(hours=1), self.base))
        self.conn.execute("""insert into dino_dev.versioned_best_score
          (participant_id,game_version,session_id,score,achieved_at) values(%s,'2.0.0',%s,8999,%s)""",
          (outsider, outsider_sid, self.base))
        data = self.report()
        self.assertEqual(data["campaign"]["game_version"], "2.0.0")
        self.assertEqual((data["game"]["coins_collected"], data["game"]["coin_score"],
                          data["game"]["hearts_collected"], data["game"]["revives"]), (14, 140, 2, 2))
        self.assertEqual(data["game"]["collision_finished"], 1)
        self.assertEqual((data["leaderboard"][0]["game_version"], data["leaderboard"][0]["best_score"]), ("2.0.0", 828))
        self.assertEqual(data["leaderboard"][0]["rank"], 1, "rank is computed after the environment cohort is scoped")
        self.assertEqual((data["score_distribution"][0]["game_version"], data["score_distribution"][0]["games"]), ("2.0.0", 1))

    def test_loading_content_ordered_ctr_and_record_share_are_separate(self):
        converted = self.person("converted")
        converted_obs = self.observation("converted", converted)
        for index, name in enumerate(("loading_data_ready", "loading_intro_completed", "loading_ready")):
            self.event(name, converted, converted_obs, index)
        self.event("content_viewed", converted, converted_obs, 4, {"content": "study_note"}, "benefit")
        self.event("content_clicked", converted, converted_obs, 5, {"content": "study_note"}, "benefit")
        self.event("share_attempted", converted, converted_obs, 6,
                   {"link_kind": "record_share", "share_method": "copy", "status": "copied", "share_id": "share_phase2_metrics"}, "invite")
        self.event("share_attempted", converted, converted_obs, 7,
                   {"link_kind": "retry_invite", "share_method": "native", "status": "attempted", "share_id": "retry_phase2_metrics"}, "invite")
        self.event("share_attempted", converted, converted_obs, 8,
                   {"link_kind": "prize_share", "share_method": "native", "status": "share_sheet_closed", "share_id": "prize_phase2_metrics"}, "prize")

        reversed_pid = self.person("reversed")
        reversed_obs = self.observation("reversed", reversed_pid)
        self.event("content_clicked", reversed_pid, reversed_obs, 3, {"content": "study_note"}, "benefit")
        self.event("content_viewed", reversed_pid, reversed_obs, 4, {"content": "study_note"}, "benefit")

        data = self.report()
        milestones = {row["milestone"]: row for row in data["loading"]["milestones"]}
        self.assertEqual({name: milestones[name]["events"] for name in milestones}, {
            "loading_data_ready": 1, "loading_intro_completed": 1, "loading_ready": 1,
        })
        content = next(row for row in data["content"] if row["content"] == "study_note")
        self.assertEqual((content["viewed_participants"], content["clicked_participants"],
                          content["converted_participants"], content["unique_ctr"]), (2, 2, 1, 0.5))
        record = data["sharing"]["record_share_sharing"]
        self.assertEqual((record["copy_success_events"], record["linked_participants"]), (1, 1))
        retry = data["sharing"]["retry_invite_sharing"]
        prize = data["sharing"]["prize_share_sharing"]
        invitation = data["sharing"]["invitation_sharing"]
        self.assertEqual((retry["attempt_events"], prize["share_sheet_closed_events"]), (1, 1))
        self.assertEqual((invitation["event_count"], invitation["linked_participants"]), (3, 1))
        self.assertEqual({"record_share", "retry_invite", "prize_share"},
                         {row["purpose"] for row in data["sharing"]["by_purpose"]})

    def test_ranking_contact_counts_are_game_version_scoped(self):
        legacy = self.person("legacy_contact")
        current = self.person("current_contact")
        self.conn.execute("""insert into dino_dev.ranking_contact
          (participant_id,status,game_version,requested_at) values
          (%s,'SUBMITTED','1.2.0',%s),(%s,'REQUESTED','2.0.0',%s)""",
          (legacy, self.base, current, self.base))
        data = self.report()
        self.assertEqual(data["ranking"], {"requested": 1, "submitted": 0})


if __name__ == "__main__":
    unittest.main()
