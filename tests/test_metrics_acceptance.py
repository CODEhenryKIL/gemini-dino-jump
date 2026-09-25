"""Phase 1 chapter 6 metric acceptance checks on rollback-only local fixtures."""
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


class MetricsAcceptanceTest(unittest.TestCase):
    def setUp(self):
        url = os.getenv("PHASE1_METRICS_DATABASE_URL", "postgresql://postgres@127.0.0.1:55433/dino_phase1_v2_browser")
        parsed = urlparse(url)
        if parsed.hostname not in {"localhost", "127.0.0.1"} or not parsed.path.startswith("/dino_phase1_v2_"):
            raise RuntimeError("Metrics acceptance fixtures require the isolated local Phase 1 database")
        self.conn = psycopg.connect(url, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.prefix = "dino_phase1_audit_metrics_" + secrets.token_hex(6)
        self.campaign = self.conn.execute("select campaign_id from dino_dev.environment_guard where singleton").fetchone()["campaign_id"]
        self.base = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc)
        self.query = {"from": "2026-01-01T00:00:00Z", "to": "2026-01-02T00:00:00Z"}

    def person(self, suffix, *, first_link="direct", first_channel="audit", public=False, environment="local"):
        pid = self.prefix + suffix
        self.conn.execute("""insert into dino_dev.participant
          (id,campaign_id,token_hash,token_expires_at,nickname,is_public,referral_code,environment,first_link_kind,first_channel,created_at)
          values(%s,%s,%s,clock_timestamp()+interval '1 day',%s,%s,%s,%s,%s,%s,%s)""",
          (pid, self.campaign, secrets.token_hex(32), "TEST_" + suffix, public, secrets.token_urlsafe(16),
           environment, first_link, first_channel, self.base))
        return pid

    def observation(self, suffix, pid=None, *, link="direct", channel="audit", environment="local"):
        oid = self.prefix + "obs_" + suffix
        self.conn.execute("""insert into dino_dev.observation
          (id,event_id,actor_key,idempotency_key,request_hash,participant_id,link_kind,channel_code,environment,created_at)
          values(%s,%s,%s,%s,'hash',%s,%s,%s,%s,%s)""",
          (oid, oid, self.prefix, secrets.token_hex(16), pid, link, channel, environment, self.base))
        return oid

    def event(self, name, pid=None, *, minute=0, observation=None, active=None, screen="home", view=None,
              source="client", dimensions=None, environment="local"):
        self.conn.execute("""insert into dino_dev.analytics_event
          (event_id,campaign_id,participant_id,observation_id,event_name,screen,screen_view_id,visit_session_id,
           active_ms,dimensions,environment,deployment,event_version,source,occurred_at,received_at)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'audit','phase1-v1',%s,%s,%s)""",
          (self.prefix + secrets.token_hex(8), self.campaign, pid, observation, name, screen, view,
           observation, active, json.dumps(dimensions or {}), environment, source,
           self.base + dt.timedelta(minutes=minute), self.base + dt.timedelta(minutes=minute)))

    def report(self, **filters):
        self.conn.execute("set local role dino_dev_app")
        status, data = metrics.build_overview(self.conn, {**self.query, **filters}, {"environment": "local"})
        self.assertEqual(status, 200)
        return data

    def test_first_and_current_visit_server_conversion_are_separate(self):
        pid = self.person("source", first_link="initial", first_channel="school_a")
        oid = self.observation("source", pid, link="retry_invite", channel="school_b")
        self.event("game_start_approved", pid, observation=oid, source="server")
        rows = self.report()["source_funnel"]
        first = next(row for row in rows if row["attribution"] == "first")
        current = next(row for row in rows if row["attribution"] == "session")
        self.assertEqual((first["link_kind"], first["channel"], first["game_starts"]), ("initial", "school_a", 1))
        self.assertEqual((current["link_kind"], current["channel"], current["game_starts"]), ("retry_invite", "school_b", 1))

    def test_loading_ready_next_screen_fallback_exit_rate_and_unlinked(self):
        ready = self.observation("ready", self.person("ready"))
        fallback = self.observation("fallback", self.person("fallback"))
        abandoned = self.observation("abandoned")
        self.event("loading_ready", observation=ready, active=900, screen="loading")
        self.event("screen_entered", observation=fallback, active=0, screen="home")
        self.event("loading_checkpoint", observation=abandoned, active=1500, screen="loading")
        buckets = {row["bucket"]: row for row in self.report()["loading"]["buckets"]}
        self.assertEqual((buckets["0-1s"]["ready"], buckets["0-1s"]["estimated_exits"]), (1, 0))
        self.assertEqual((buckets["unknown"]["ready"], buckets["unknown"]["estimated_exits"]), (1, 0))
        self.assertEqual((buckets["1-2s"]["estimated_exits"], buckets["1-2s"]["estimated_exit_rate"]), (1, 1))

    def test_abandoned_active_dwell_and_gemini_stages_are_observed(self):
        exited = self.person("exit")
        exit_view = self.prefix + "draw_view"
        self.event("draw_entered", exited, active=500, screen="draw", view=exit_view)
        self.event("screen_left", exited, minute=1, active=2500, screen="draw", view=exit_view, dimensions={"reason": "pagehide"})
        unknown = self.person("exit_unknown")
        self.event("draw_entered", unknown, active=300, screen="draw", view=self.prefix + "draw_unknown")
        gemini = self.person("gemini")
        benefit_view = self.prefix + "benefit_view"
        self.event("benefit_viewed", gemini, active=100, screen="benefit", view=benefit_view)
        self.event("gemini_cta_viewed", gemini, minute=1, active=500, screen="benefit", view=benefit_view, dimensions={"position": "benefit_main"})
        self.event("gemini_cta_clicked", gemini, minute=2, active=800, screen="benefit", view=benefit_view, dimensions={"position": "benefit_main"})
        stages = {row["key"]: row for row in self.report()["stages"]}
        self.assertEqual((stages["draw.select"]["estimated_exits"], stages["draw.select"]["mean_abandoned_active_ms"]), (2, 2000))
        self.assertEqual(stages["draw.select"]["abandoned_active_observations"], 1)
        self.assertEqual(stages["draw.select"]["abandoned_active_unknown"], 1)
        self.assertEqual((stages["gemini.exposure"]["progressed"], stages["gemini.exposure"]["mean_observed_active_ms"]), (1, 400))
        self.assertEqual((stages["gemini.click"]["progressed"], stages["gemini.click"]["mean_observed_active_ms"]), (1, 300))

    def test_filters_scope_real_rows_and_leaderboard_masks_private_nickname(self):
        included = self.person("included", first_link="initial", first_channel="school_a", public=False)
        excluded = self.person("excluded", first_link="direct", first_channel="school_b", public=True)
        included_observation = self.observation("included", included, link="initial", channel="school_a")
        excluded_observation = self.observation("excluded", excluded, link="direct", channel="school_b")
        self.event("content_clicked", included, observation=included_observation, dimensions={"content": "study"})
        self.event("content_clicked", excluded, observation=excluded_observation, dimensions={"content": "photo"})
        for pid, score, suffix in ((included, 300, "a"), (excluded, 400, "b")):
            sid = self.prefix + "game_" + suffix
            self.conn.execute("""insert into dino_dev.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,reserved_at,expires_at,score,valid_ticks,verification_result,finished_at,environment)
              values(%s,%s,%s,%s,1,'dino-v1','FINISHED','INITIAL','NOT_DUE',%s,%s,%s,60,'VERIFIED',%s,'local')""",
              (sid, pid, self.campaign, sid, self.base, self.base + dt.timedelta(hours=1), score, self.base))
            self.conn.execute("insert into dino_dev.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,%s,%s)", (pid, sid, score, self.base))
        data = self.report(link_kind="initial", channel="school_a", content="study")
        self.assertEqual(data["totals"]["participants"], 1)
        self.assertEqual(len(data["leaderboard"]), 1)
        self.assertEqual((data["leaderboard"][0]["rank"], data["leaderboard"][0]["nickname"], data["leaderboard"][0]["best_score"]), (2, "익명 참가자", 300))
        self.assertEqual(data["filter_attribution"], "first_participant_cohort")


if __name__ == "__main__":
    unittest.main()
