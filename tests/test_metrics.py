"""Metrics correctness against real PostgreSQL, using rollback-only fixtures."""
import datetime as dt
import json
import os
from pathlib import Path
import secrets
import sys
import unittest
import unicodedata
from urllib.parse import urlparse

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'server'))
import metrics
import psycopg
from psycopg.rows import dict_row


class MetricsTest(unittest.TestCase):
    def setUp(self):
        url = os.getenv('PHASE1_METRICS_DATABASE_URL', 'postgresql://postgres@127.0.0.1:55433/dino_phase1_v2_browser')
        parsed = urlparse(url)
        if parsed.hostname not in {'localhost', '127.0.0.1'} or not parsed.path.startswith('/dino_phase1_v2_'):
            raise RuntimeError('Metrics fixtures require the isolated local Phase 1 database')
        self.conn = psycopg.connect(url, row_factory=dict_row)
        self.addCleanup(self.conn.close)
        self.addCleanup(self.conn.rollback)
        self.prefix = 'metrics_' + secrets.token_hex(8)
        self.campaign = self.conn.execute('select campaign_id from dino_dev.environment_guard where singleton').fetchone()['campaign_id']
        self.base = dt.datetime(2026, 1, 1, 12, tzinfo=dt.timezone.utc)
        self.query = {'from': '2026-01-01T00:00:00Z', 'to': '2026-01-02T00:00:00Z'}

    def person(self, suffix):
        pid = self.prefix + suffix
        self.conn.execute('''insert into dino_dev.participant(id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,first_link_kind,first_channel,created_at)
          values(%s,%s,%s,clock_timestamp()+interval '1 day','TEST_metrics',%s,'local','direct','metrics_test',%s)''',
          (pid,self.campaign,secrets.token_hex(32),secrets.token_urlsafe(16),self.base))
        return pid

    def observation(self, pid=None):
        oid = self.prefix + secrets.token_hex(4)
        self.conn.execute('''insert into dino_dev.observation(id,event_id,actor_key,idempotency_key,request_hash,participant_id,link_kind,channel_code,environment,created_at)
          values(%s,%s,%s,%s,%s,%s,'direct','metrics_test','local',%s)''',
          (oid,oid,self.prefix,secrets.token_hex(16),'hash',pid,self.base))
        return oid

    def event(self, name, pid=None, minute=0, dimensions=None, observation=None, active=None, screen='benefit', environment='local', source='client', screen_view=None, game_session=None):
        self.conn.execute('''insert into dino_dev.analytics_event(event_id,campaign_id,participant_id,observation_id,event_name,screen,screen_view_id,visit_session_id,game_session_id,active_ms,dimensions,environment,deployment,event_version,source,occurred_at,received_at)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,'test','1',%s,%s,%s)''',
          (self.prefix+secrets.token_hex(8),self.campaign,pid,observation,name,screen,screen_view,pid or observation,game_session,active,json.dumps(dimensions or {}),environment,source,self.base+dt.timedelta(minutes=minute),self.base+dt.timedelta(minutes=minute)))

    def game_session(self, pid, suffix='game'):
        session_id = self.prefix + suffix
        self.conn.execute('''insert into dino_dev.game_session(id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,reserved_at,expires_at,environment)
          values(%s,%s,%s,%s,1,'dino-v1','ACTIVE','INITIAL','PENDING',%s,%s,'local')''',
          (session_id,pid,self.campaign,self.prefix+suffix,self.base,self.base+dt.timedelta(hours=1)))
        return session_id

    def report(self, **query):
        self.conn.execute('set local role dino_dev_app')
        status, data = metrics.build_overview(self.conn,{**self.query,**query},{'environment':'local'})
        self.assertEqual(status,200)
        return data

    def test_ordered_same_position_window_and_environment_ctr(self):
        p1,p2,p3,p4 = [self.person(str(i)) for i in range(4)]
        for p in [p1,p2,p3,p4]:self.event('gemini_cta_viewed',p,10,{'position':'primary'})
        self.event('gemini_cta_clicked',p1,11,{'position':'primary'})
        self.event('gemini_cta_clicked',p1,12,{'position':'primary'})
        self.event('gemini_cta_clicked',p2,9,{'position':'primary'})
        self.event('gemini_cta_clicked',p3,11,{'position':'footer'})
        self.event('gemini_cta_clicked',p3,11,{'position':'primary'},environment='test')
        self.event('gemini_cta_clicked',p4,41,{'position':'primary'})
        data=self.report()
        self.assertEqual((data['gemini_ctr']['numerator'],data['gemini_ctr']['denominator'],data['gemini_ctr']['rate']),(1,4,0.25))
        self.assertEqual((data['gemini_ctr']['exposure_events'],data['gemini_ctr']['pending_participants']),(4,0))
        self.assertEqual(data['gemini_conversion']['direct'],4)
        self.assertEqual(data['gemini_conversion']['union_participants'],4)

    def test_ctr_closes_windows_deduplicates_and_keeps_pending_separate(self):
        recent,old_success,wrong_position,before,duplicate,cutoff,exact_window = [
            self.person(name) for name in ('recent','oldsuccess','wrongposition','before','duplicate','cutoff','exactwindow')
        ]
        self.event('gemini_cta_viewed',recent,691,{'position':'primary'})
        self.event('gemini_cta_viewed',recent,692,{'position':'primary'})

        self.event('gemini_cta_viewed',old_success,100,{'position':'primary'})
        self.event('gemini_cta_clicked',old_success,130,{'position':'primary'})
        self.event('gemini_cta_viewed',old_success,691,{'position':'primary'})

        self.event('gemini_cta_viewed',wrong_position,200,{'position':'primary'})
        self.event('gemini_cta_clicked',wrong_position,201,{'position':'footer'})
        self.event('gemini_cta_clicked',before,299,{'position':'primary'})
        self.event('gemini_cta_viewed',before,300,{'position':'primary'})

        self.event('gemini_cta_viewed',duplicate,400,{'position':'primary'})
        self.event('gemini_cta_viewed',duplicate,401,{'position':'primary'})
        self.event('gemini_cta_clicked',duplicate,402,{'position':'primary'})

        self.event('gemini_cta_viewed',cutoff,690,{'position':'primary'})
        self.event('gemini_cta_clicked',cutoff,719,{'position':'primary'})
        self.event('gemini_cta_viewed',exact_window,500,{'position':'footer'})
        self.event('gemini_cta_clicked',exact_window,530,{'position':'footer'})

        ctr = self.report()['gemini_ctr']
        self.assertEqual((ctr['numerator'],ctr['denominator'],ctr['rate']),(3,5,3/5))
        self.assertEqual((ctr['exposure_events'],ctr['pending_participants'],ctr['pending_exposure_events']),(6,2,3))
        by_position={row['position']:row for row in ctr['by_position']}
        self.assertEqual((by_position['primary']['numerator'],by_position['primary']['denominator'],
                          by_position['primary']['pending_participants'],by_position['primary']['exposure_events']),
                         (2,4,2,5))
        self.assertEqual((by_position['footer']['numerator'],by_position['footer']['denominator']), (1,1))
        pending_metric=next(row for row in self.report()['metrics'] if row['key']=='gemini.pending')
        self.assertEqual((pending_metric['value'],pending_metric['event_count']),(2,3))

    def test_ctr_window_ending_at_report_end_stays_pending_until_next_report(self):
        participant=self.person('reportend')
        self.event('gemini_cta_viewed',participant,690,{'position':'primary'})
        self.event('gemini_cta_clicked',participant,720,{'position':'primary'})

        at_boundary=self.report()['gemini_ctr']
        self.assertEqual((at_boundary['numerator'],at_boundary['denominator'],at_boundary['rate']),(0,0,None))
        self.assertEqual((at_boundary['pending_participants'],at_boundary['pending_exposure_events']),(1,1))

        after_boundary=self.report(to='2026-01-02T00:01:00Z')['gemini_ctr']
        self.assertEqual((after_boundary['numerator'],after_boundary['denominator'],after_boundary['rate']),(1,1,1))
        self.assertEqual((after_boundary['pending_participants'],after_boundary['pending_exposure_events']),(0,0))

    def test_loading_last_active_no_checkpoint_double_count_and_unknown(self):
        p=self.person('loading');o=self.observation(p);self.observation()
        for active in [500,1000,1500]:self.event('loading_checkpoint',p,observation=o,active=active,screen='loading')
        data=self.report()
        buckets={r['bucket']:r for r in data['loading']['buckets']}
        self.assertEqual(buckets['1-2s']['observations'],1)
        self.assertEqual(buckets['1-2s']['estimated_exits'],1)
        self.assertEqual(buckets['unknown']['observations'],1)
        self.assertEqual(data['totals']['active_ms'],1500)
        self.assertEqual(data['totals']['unlinked_observations'],1)

    def test_zero_exposure_null_rate_and_guide_not_a_conversion(self):
        p=self.person('guide');self.event('content_clicked',p,dimensions={'content':'study'})
        data=self.report()
        self.assertIsNone(data['gemini_ctr']['rate'])
        self.assertEqual(data['gemini_conversion']['union_participants'],0)

    def test_reentered_screen_active_time_is_added_without_checkpoint_overlap(self):
        p=self.person('repeat')
        self.event('screen_entered',p,active=500,screen='draw')
        self.conn.execute("update dino_dev.analytics_event set screen_view_id=%s where participant_id=%s",(self.prefix+'view1',p))
        self.event('screen_left',p,active=1000,screen='draw')
        self.conn.execute("update dino_dev.analytics_event set screen_view_id=%s where participant_id=%s and screen_view_id is null",(self.prefix+'view1',p))
        self.event('screen_left',p,active=2000,screen='draw')
        self.conn.execute("update dino_dev.analytics_event set screen_view_id=%s where participant_id=%s and screen_view_id is null",(self.prefix+'view2',p))
        data=self.report()
        self.assertEqual(data['totals']['active_ms'],3000)
        self.assertEqual(next(x for x in data['screens'] if x['screen']=='draw')['visits'],2)

    def test_stage_replays_do_not_count_completed_person_as_an_exit(self):
        p=self.person('stages')
        self.event('draw_entered',p,0,screen='draw')
        self.event('pouch_selected',p,1,screen='draw')
        self.event('draw_entered',p,2,screen='draw')
        data=self.report();stage=next(x for x in data['stages'] if x['key']=='draw.select')
        self.assertEqual((stage['entered'],stage['progressed'],stage['estimated_exits']),(1,1,0))
        self.assertEqual((stage['mean_observed_active_ms'],stage['active_dwell_unknown']),(None,1))

    def test_scratch_start_progresses_to_both_visible_result_and_saved_completion(self):
        participant = self.person('scratchdone')
        view = self.prefix + 'scratch-completed-view'
        self.event('scratch_started', participant, 1, active=100, screen='draw', screen_view=view)
        self.event('draw_result_viewed', participant, 2, {'result_type':'no_prize'}, active=200, screen='draw', screen_view=view)
        self.event('client_scratch_completed', participant, 3, active=300, screen='draw', screen_view=view)

        stages = {row['key']:row for row in self.report()['stages']}
        visible = stages['scratch.visible']
        complete = stages['scratch.complete']
        self.assertEqual(unicodedata.normalize('NFC', visible['label']), '긁기 시작→결과 실제 노출')
        self.assertEqual((visible['entered'],visible['progressed'],visible['estimated_exits']), (1,1,0))
        self.assertEqual(unicodedata.normalize('NFC', complete['label']), '긁기 시작→완료 저장')
        self.assertEqual((complete['entered'],complete['progressed'],complete['estimated_exits']), (1,1,0))

    def test_visible_scratch_with_failed_save_is_not_a_visibility_exit(self):
        participant = self.person('scratchfailed')
        view = self.prefix + 'scratch-failed-view'
        self.event('scratch_started', participant, 1, active=100, screen='draw', screen_view=view)
        self.event('draw_result_viewed', participant, 2, {'result_type':'no_prize'}, active=200, screen='draw', screen_view=view)

        stages = {row['key']:row for row in self.report()['stages']}
        visible = stages['scratch.visible']
        complete = stages['scratch.complete']
        self.assertEqual((visible['entered'],visible['progressed'],visible['estimated_exits']), (1,1,0))
        self.assertEqual((complete['entered'],complete['progressed'],complete['estimated_exits']), (1,0,1))

    def test_restored_visible_result_adds_dwell_without_a_new_scratch_stage(self):
        participant = self.person('scratchrestored')
        view = self.prefix + 'scratch-restored-view'
        self.event('draw_result_viewed', participant, 1, {'result_type':'no_prize'}, active=100, screen='draw', screen_view=view)
        self.event('screen_left', participant, 2, active=900, screen='draw', screen_view=view)

        data = self.report()
        stages = {row['key']:row for row in data['stages']}
        self.assertNotIn('scratch.visible', stages)
        self.assertNotIn('scratch.complete', stages)
        dwell = next(row for row in data['result_dwell'] if row['result_type']=='no_prize')
        self.assertEqual((dwell['visits'],dwell['active_ms']), (1,800))

    def test_open_observation_window_is_not_abandonment(self):
        p=self.person('pending')
        self.event('draw_entered',p,719,screen='draw')
        data=self.report();stage=next(x for x in data['stages'] if x['key']=='draw.select')
        self.assertEqual((stage['entered'],stage['pending'],stage['estimated_exits']),(1,1,0))

    def test_future_report_and_naive_times_are_rejected(self):
        from operations import DomainError
        for query in [{'from':'2026-01-01','to':'2026-01-02'}, {'from':'2999-01-01T00:00:00Z','to':'2999-01-02T00:00:00Z'}]:
            with self.assertRaises(DomainError):metrics.build_overview(self.conn,query,{'environment':'local'})

    def test_completed_recent_screen_remains_in_exit_denominator(self):
        done,pending,exited=[self.person(x) for x in ('done','open','exited')]
        self.event('pouch_selected',done,719,screen='draw')
        self.event('draw_entered',pending,719,screen='draw')
        self.event('draw_entered',exited,0,screen='draw')
        data=self.report()
        row=next(x for x in data['screens'] if x['screen']=='draw')
        self.assertEqual((row['visits'],row['ongoing'],row['estimated_exits']),(3,1,1))
        metric=next(x for x in data['metrics'] if x['key']=='screen.exit.draw')
        self.assertEqual((metric['numerator'],metric['denominator'],metric['rate']),(1,2,0.5))

    def test_source_cohort_new_return_and_conversion_are_unique(self):
        fresh,returning=self.person('new'),self.person('returning')
        self.conn.execute('update dino_dev.participant set created_at=%s where id=%s',
                          (self.base-dt.timedelta(days=2),returning))
        for person in (fresh,returning):
            observation=self.observation(person)
            for minute in (1,2):
                self.event('gemini_cta_clicked',person,minute,observation=observation)
        data=self.report()
        for row in data['source_funnel']:
            self.assertEqual((row['new_participants'],row['returning_participants'],row['participants']),(1,1,2))
            self.assertEqual(row['gemini_click_rate'],1)
            self.assertEqual(row['game_start_rate'],0)

    def test_sharing_and_content_report_observed_actions_without_delivery_inference(self):
        linked = self.person('sharing')
        unlinked_observation = self.observation()
        self.event('share_attempted',linked,1,{'source':'gemini','share_method':'native','status':'attempted'},screen='invite')
        self.event('share_attempted',linked,2,{'source':'gemini','share_method':'copy','status':'copied'})
        self.event('share_attempted',linked,3,{'share_method':'native','status':'attempted'},screen='invite')
        self.event('share_attempted',linked,4,{'share_method':'native','status':'share_sheet_closed'},screen='invite')
        self.event('share_attempted',linked,5,{'source':'home','share_method':'native','status':'cancelled'})
        self.event('share_attempted',None,6,{'share_method':'copy','status':'copied','share_id':'safe_share'},observation=unlinked_observation,screen='invite')
        self.event('content_clicked',linked,5,{'content':'study'})
        self.event('content_clicked',linked,6,{'content':'study'})
        self.event('notion_redirect_requested',linked,7,{'content':'study'})
        self.event('content_clicked',None,8,{'content':'photo'},observation=unlinked_observation)
        data = self.report()
        self.assertEqual(data['sharing']['actual_delivery'],'unknown')
        self.assertEqual((data['sharing']['attempt_events'],data['sharing']['copy_success_events'],
                          data['sharing']['share_sheet_closed_events'],data['sharing']['cancelled_events']),
                         (2,2,1,1))
        self.assertEqual((data['sharing']['linked_participants'],data['sharing']['unlinked_events']), (1,1))
        self.assertEqual((data['sharing']['gemini_sharing']['linked_participants'],
                          data['sharing']['gemini_sharing']['copy_success_events']), (1,1))
        self.assertEqual((data['sharing']['invitation_sharing']['linked_participants'],
                          data['sharing']['invitation_sharing']['unlinked_events'],
                          data['sharing']['invitation_sharing']['copy_success_events']), (1,1,1))
        self.assertEqual((data['sharing']['unknown_sharing']['linked_participants'],
                          data['sharing']['unknown_sharing']['cancelled_events']), (1,1))
        self.assertEqual({row['purpose'] for row in data['sharing']['by_purpose']},
                         {'gemini','retry_invite','unknown'})
        study = next(row for row in data['content'] if row['content']=='study')
        photo = next(row for row in data['content'] if row['content']=='photo')
        self.assertEqual((study['click_events'],study['outbound_request_events'],study['linked_participants']), (2,1,1))
        self.assertEqual((photo['linked_participants'],photo['unlinked_events']), (0,1))

    def test_invitation_ledger_reports_period_ratio_and_post_cooldown_reparticipation(self):
        participant = self.person('inviteledger')
        rows = [
          ('INVITATION_GRANT','old',1,self.base-dt.timedelta(hours=13),self.base-dt.timedelta(hours=2)),
          ('PLAY_CONSUME','oldplay',0,self.base-dt.timedelta(hours=12,minutes=30),None),
          ('INVITATION_GRANT','new',1,self.base+dt.timedelta(minutes=10),self.base+dt.timedelta(hours=10,minutes=10)),
          ('PLAY_CONSUME','newplay',0,self.base+dt.timedelta(minutes=20),None),
        ]
        for source,source_id,balance,created,cooldown in rows:
            self.conn.execute('''insert into dino_dev.ticket_ledger(participant_id,ticket_kind,delta,source_type,source_id,balance_after,cooldown_until,created_at)
              values(%s,'INVITATION',%s,%s,%s,%s,%s,%s)''',
              (participant,1 if source=='INVITATION_GRANT' else -1,source,self.prefix+source_id,balance,cooldown,created))
        result = self.report()['invitation_performance']
        self.assertEqual((result['grant_events'],result['use_events'],result['period_use_to_grant_ratio']), (1,1,1))
        self.assertEqual((result['cooldown_reacquisition_events'],result['cooldown_reacquisition_participants']), (1,1))
        self.assertEqual((result['cooldown_reparticipation_events'],result['cooldown_reparticipation_participants']), (1,1))

    def test_game_last_checkpoint_and_stage_active_dwell_keep_unknown_explicit(self):
        observed,unknown = self.person('observed'),self.person('unknown')
        game = self.game_session(observed,'observedgame')
        self.game_session(unknown,'unknowngame')
        view = self.prefix+'drawview'
        self.event('game_checkpoint',observed,1,{'stage':'RUNNING'},active=1000,screen='game',game_session=game)
        self.event('game_checkpoint',observed,2,{'stage':'FAST'},active=4200,screen='game',game_session=game)
        self.event('draw_entered',observed,3,active=500,screen='draw',screen_view=view)
        self.event('pouch_selected',observed,4,active=1700,screen='draw',screen_view=view)
        data = self.report()
        fast = next(row for row in data['game_progress']['by_last_stage'] if row['last_stage']=='FAST')
        missing = next(row for row in data['game_progress']['by_last_stage'] if row['last_stage']=='unknown')
        self.assertEqual((fast['sessions'],fast['mean_last_observed_active_ms'],fast['active_time_unknown']), (1,4200,0))
        self.assertEqual((missing['sessions'],missing['active_time_unknown']), (1,1))
        stage = next(row for row in data['stages'] if row['key']=='draw.select')
        self.assertEqual((stage['mean_observed_active_ms'],stage['active_dwell_observations'],stage['active_dwell_unknown']), (1200,1,0))


if __name__=='__main__':unittest.main()
