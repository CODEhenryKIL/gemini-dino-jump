"""Phase 2 transactions exercised through the restricted local application role."""
import datetime as dt
import json
import secrets
import subprocess
import unittest
from pathlib import Path

import test_backend_phase1 as fixtures
import game_verifier
import operations
import metrics
import share_page

ROOT = Path(__file__).resolve().parents[1]


class BackendPhase2Test(unittest.TestCase):
    setUp = fixtures.BackendPhase1Test.setUp
    make_participant = fixtures.BackendPhase1Test.make_participant
    make_admin = fixtures.BackendPhase1Test.make_admin
    qualify = fixtures.BackendPhase1Test.qualify

    @classmethod
    def setUpClass(cls):
        cls.play = json.loads(subprocess.check_output(['node', str(ROOT/'tests/js_v2_fixture_runner.cjs'), json.dumps({'mode':'bot','seed':4,'target_revives':2})],text=True,cwd=ROOT))
        cls.verification = game_verifier.verify_game('2.0.0',4,cls.play['jump_ticks'],cls.play['score'],cls.play['ticks'])
        assert cls.verification['valid']

    def ctx(self, raw, **extra):
        return fixtures.context(participant_token_hash=fixtures.h(raw),game_version='2.0.0',**extra)

    def started(self, raw):
        ctx=self.ctx(raw,idempotency_key=secrets.token_urlsafe(24))
        with fixtures.app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx)
            _,started=operations.start_session(conn,session['session_id'],ctx)
            conn.execute("update dino_dev.game_session set seed=4,started_at=clock_timestamp()-make_interval(secs=>%s) where id=%s",(self.play['ticks']/60+1,session['session_id']))
        return ctx,started

    def attributed_visit(self, visitor, code, kind):
        event_id='evt_'+secrets.token_hex(10);observation_id='obs_'+secrets.token_hex(10)
        idempotency_key=secrets.token_urlsafe(32);bootstrap=secrets.token_urlsafe(32)
        share_id='share_'+secrets.token_hex(8);nonce=secrets.token_urlsafe(32)
        ctx=self.ctx(visitor,idempotency_key=idempotency_key,bootstrap_token=bootstrap,
                     bootstrap_token_hash=fixtures.h(bootstrap),invite_nonce=nonce,
                     invite_nonce_hash=fixtures.h(nonce))
        observation={'observation_id':observation_id,'event_id':event_id,'link_kind':kind,
                     'channel_code':'unknown','share_id':share_id}
        with fixtures.app_tx() as conn:
            status,created=operations.create_observation(conn,observation,ctx)
            self.assertEqual((status,created['accepted']),(201,True))
            status,initialized=operations.participant_init(conn,{
                'invite_code':code,'bootstrap_token':bootstrap,'observation_id':observation_id,
                'link_kind':kind,'channel':'unknown','share_id':share_id,
            },ctx)
            self.assertEqual(status,200)
            linked=conn.execute('select link_kind,share_id,participant_id from dino_dev.observation where id=%s',(observation_id,)).fetchone()
            self.assertEqual((linked['link_kind'],linked['share_id'],linked['participant_id']),
                             (kind,share_id,initialized['participant']['id']))
        self.assertEqual(initialized['invite_visit']['status'],'PENDING')
        return initialized['invite_visit']['visit_nonce']

    def test_verified_summary_versioned_rank_and_draw_are_atomic(self):
        raw,_,p=self.make_participant();ctx,s=self.started(raw)
        with fixtures.app_tx() as conn:
            self.assertEqual(s['version'],'2.0.0')
            status,result=operations.finish_session(conn,s['session_id'],{'summary':{'revives':999}},dict(ctx,verification=self.verification))
            self.assertEqual(status,200)
            self.assertEqual(result['summary'],self.play['summary'])
            self.assertEqual(result['rank'],1)
            self.assertEqual(result['draw']['status'],'AVAILABLE')
            self.assertEqual(result['top3_gap']['status'],'IN_TOP3')
            self.assertEqual(conn.execute('select count(*) n from dino_dev.best_score').fetchone()['n'],0)
            self.assertEqual(conn.execute('select count(*) n from dino_dev.versioned_best_score').fetchone()['n'],1)
            self.assertEqual(operations.get_me(conn,ctx)[1]['best_score'],self.play['score'])
            self.assertEqual(operations.get_me(conn,dict(ctx,game_version='1.2.0'))[1]['best_score'],0)
            again=operations.finish_session(conn,s['session_id'],{},dict(ctx,verification=self.verification))[1]
            self.assertEqual(result,again)

    def test_expired_active_game_cannot_submit_or_rank(self):
        raw,_,_=self.make_participant();ctx,s=self.started(raw)
        with fixtures.app_tx() as conn:
            conn.execute("update dino_dev.game_session set expires_at=clock_timestamp()-interval '1 second' where id=%s",(s['session_id'],))
            status,result=operations.finish_session(conn,s['session_id'],{},dict(ctx,verification=self.verification))
            self.assertEqual((status,result['error']),(409,'SESSION_EXPIRED'))
            self.assertEqual(conn.execute('select count(*) n from dino_dev.versioned_best_score').fetchone()['n'],0)
            self.assertEqual(operations.get_me(conn,ctx)[1]['draw']['status'],'LOCKED')
            state=conn.execute('select status,fault_reason from dino_dev.game_session where id=%s',(s['session_id'],)).fetchone()
            self.assertEqual(dict(state),{'status':'FAULT_REPORTED','fault_reason':'SERVER_TIMEOUT'})

    def test_submitted_top3_contact_survives_rank_drop_and_verified_reentry(self):
        # Exercise the real finish/upsert twice; competing scores are local rank fixtures.
        short = json.loads(subprocess.check_output([
            'node', str(ROOT/'tests/js_v2_fixture_runner.cjs'),
            json.dumps({'seed': 4, 'jumps': []}),
        ], text=True, cwd=ROOT))
        verified_short = game_verifier.verify_game('2.0.0', 4, [], short['score'], short['ticks'])
        self.assertTrue(verified_short['valid'])
        self.assertGreater(self.play['score'], short['score'] + 3)
        raw, _, person = self.make_participant()
        pid = person['participant']['id']
        ctx, first = self.started(raw)
        with fixtures.app_tx() as conn:
            result = operations.finish_session(conn, first['session_id'], {}, dict(ctx, verification=verified_short))[1]
            self.assertEqual((result['rank'], result['top3_profile']['status']), (1, 'REQUESTED'))
            submitted = operations.ranking_profile_post(conn, {
                'name': 'TEST_REENTRY', 'contact': '01000000000', 'school': 'TEST_SCHOOL',
            }, ctx)[1]

        with fixtures.psycopg.connect(fixtures.DSN) as conn:
            for index in range(1, 4):
                _, _, data = self.make_participant()
                rival_id = data['participant']['id']
                session_id = 'rank_reentry_rival_' + str(index)
                score = short['score'] + index
                conn.execute("""insert into dino_dev.game_session
                    (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,
                     ticket_refund_status,expires_at,score,valid_ticks,verification_result,finished_at,environment)
                    values(%s,%s,'gemini_dino_phase1_test',%s,4,'2.0.0','FINISHED','INITIAL',
                    'NOT_DUE',clock_timestamp()+interval '1 minute',%s,60,'VERIFIED',clock_timestamp(),'test')""",
                    (session_id, rival_id, session_id, score))
                conn.execute("""insert into dino_dev.versioned_best_score
                    (participant_id,game_version,session_id,score,achieved_at)
                    values(%s,'2.0.0',%s,%s,clock_timestamp())""", (rival_id, session_id, score))

        with fixtures.app_tx() as conn:
            self.assertEqual(operations.get_me(conn, ctx)[1]['rank'], 4)
            profile = operations.ranking_profile_get(conn, ctx)[1]
            self.assertEqual((profile['status'], profile['required']), ('SUBMITTED', False))

        visitor, _, visit = self.make_participant(person['participant']['referral_code'])
        self.qualify(visitor, person['participant']['referral_code'], visit['invite_visit']['visit_nonce'])
        retry_ctx, retry = self.started(raw)
        with fixtures.app_tx() as conn:
            reentry = operations.finish_session(conn, retry['session_id'], {}, dict(retry_ctx, verification=self.verification))[1]
            self.assertEqual((reentry['rank'], reentry['top3_gap']['status']), (1, 'IN_TOP3'))
            self.assertEqual((reentry['top3_profile']['status'], reentry['top3_profile']['required']), ('SUBMITTED', False))
            replay = operations.ranking_profile_post(conn, {
                'name': 'TEST_OTHER', 'contact': '01000000001', 'school': 'TEST_OTHER',
            }, retry_ctx)[1]
            self.assertEqual(replay['claim_id'], submitted['claim_id'])
            contact = conn.execute('select count(*) n from dino_dev.ranking_contact where participant_id=%s', (pid,)).fetchone()
            claims = conn.execute("select count(*) n from dino_dev.claim where participant_id=%s and claim_type='RANKING'", (pid,)).fetchone()
            saved = conn.execute('select recipient_name,school from dino_dev.claim_contact where claim_id=%s', (submitted['claim_id'],)).fetchone()
            self.assertEqual((contact['n'], claims['n']), (1, 1))
            self.assertEqual((saved['recipient_name'], saved['school']), ('TEST_REENTRY', 'TEST_SCHOOL'))
            self.assertEqual(reentry['draw']['status'], 'AVAILABLE')

    def test_dense_rank_ties_private_name_and_gap_use_same_rules(self):
        participants=[]
        scores=(500,500,400,300,300,200)
        elapsed_ticks=(600,540,480,720,180,360)
        for index,(score,ticks) in enumerate(zip(scores,elapsed_ticks)):
            raw,_,p=self.make_participant();pid=p['participant']['id'];ctx,s=self.started(raw)
            with fixtures.app_tx() as conn:
                conn.execute("update dino_dev.game_session set status='FINISHED',score=%s,valid_ticks=%s,finished_at=clock_timestamp() where id=%s",(score,ticks,s['session_id']))
                conn.execute("insert into dino_dev.versioned_best_score values(%s,%s,%s,%s,timestamptz '2026-01-01 00:00:00+00'+make_interval(secs=>%s))",(pid,'2.0.0',s['session_id'],score,index))
            participants.append((raw,pid))
        with fixtures.app_tx() as conn:
            conn.execute('update dino_dev.participant set is_public=false where id=%s',(participants[0][1],))
            ctx=self.ctx(participants[-1][0]);data=operations.leaderboard(conn,{},ctx)[1]
            self.assertEqual(data['me']['rank'],4)
            self.assertEqual(data['me']['best_elapsed_seconds'],6.0)
            self.assertEqual(data['top3_gap']['third_score'],300)
            self.assertEqual(data['top3_gap']['third_elapsed_seconds'],12.0)
            self.assertEqual(data['top3_gap']['score_needed'],100)
            self.assertEqual(data['top3_gap']['status'],'CHASING')
            conn.execute("update dino_dev.versioned_best_score set achieved_at=timestamptz '2026-01-01 00:00:03+00' where score=300")
            tied_third=operations.leaderboard(conn,{},ctx)[1]['top3_gap']
            expected_tied_seconds=12.0 if participants[3][1]<participants[4][1] else 3.0
            self.assertEqual(tied_third['third_elapsed_seconds'],expected_tied_seconds)
            top=operations.get_me(conn,self.ctx(participants[1][0]))[1]
            self.assertEqual(top['rank'],1);self.assertTrue(top['top3_gap']['tied'])
            self.assertEqual(len(data['leaderboard']),5)
            self.assertEqual(sum(x['score']==500 for x in data['leaderboard']),1)
        admin=self.make_admin(['ranking:write']);admin['game_version']='2.0.0'
        with fixtures.app_tx() as conn:
            _,snapshot=operations.create_admin_ranking_snapshot(conn,{'event_id':'evt_snapshot_v2'},admin)
            self.assertEqual(snapshot['game_version'],'2.0.0');self.assertEqual(snapshot['entry_count'],6)

    def test_old_top3_request_provenance_preserved_and_upgraded_without_reset(self):
        raw,_,p=self.make_participant();pid=p['participant']['id'];ctx,s=self.started(raw)
        admin=self.make_admin(['ranking:write'])
        with fixtures.app_tx() as conn:
            conn.execute("insert into dino_dev.ranking_contact(participant_id,status,game_version,submitted_at) values(%s,'SUBMITTED','1.2.0',clock_timestamp())",(pid,))
            before=operations.get_me(conn,ctx)[1]['top3_profile']
            self.assertEqual(before,{'status':'SUBMITTED','game_version':'1.2.0'})
            _,finished=operations.finish_session(conn,s['session_id'],{},dict(ctx,verification=self.verification))
            self.assertEqual(finished['top3_profile']['status'],'SUBMITTED')
            self.assertEqual(finished['top3_profile']['game_version'],'2.0.0')
            self.assertFalse(finished['top3_profile']['required'])
            versions=conn.execute('select game_version from dino_dev.ranking_contact_version where participant_id=%s order by game_version',(pid,)).fetchall()
            self.assertEqual([row['game_version'] for row in versions],['1.2.0','2.0.0'])
            # A historical score remains visible to the old Preview's snapshot.
            conn.execute("""insert into dino_dev.game_session
              (id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,reserved_at,expires_at,score,valid_ticks,verification_result,finished_at,environment)
              select id||'_legacy',participant_id,campaign_id,idempotency_key||'_legacy',seed,'1.2.0',status,ticket_kind,ticket_refund_status,reserved_at,expires_at,10,60,'VERIFIED',finished_at,environment
              from dino_dev.game_session where id=%s""",(s['session_id'],))
            conn.execute('insert into dino_dev.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,10,clock_timestamp())',(pid,s['session_id']+'_legacy'))
            now=dt.datetime.now(dt.timezone.utc)
            query={'from':(now-dt.timedelta(hours=1)).isoformat(),'to':(now+dt.timedelta(minutes=1)).isoformat()}
            for version in ('1.2.0','2.0.0'):
                _,report=metrics.build_overview(conn,query,dict(ctx,game_version=version))
                self.assertEqual(report['ranking'],{'requested':1,'submitted':1})
                _,snapshot=operations.create_admin_ranking_snapshot(conn,{'event_id':'evt_snapshot_'+version},dict(admin,game_version=version))
                entry=conn.execute('select contact_status from dino_dev.ranking_snapshot_entry where snapshot_id=%s and participant_id=%s',(snapshot['id'],pid)).fetchone()
                self.assertEqual(entry['contact_status'],'SUBMITTED')

    def test_legacy_preview_conflict_still_records_its_contact_version(self):
        raw,_,p=self.make_participant();pid=p['participant']['id'];ctx,s=self.started(raw)
        with fixtures.app_tx() as conn:
            operations.finish_session(conn,s['session_id'],{},dict(ctx,verification=self.verification))
            conn.execute("insert into dino_dev.ranking_contact(participant_id) values(%s) on conflict(participant_id) do nothing",(pid,))
            versions=conn.execute('select game_version from dino_dev.ranking_contact_version where participant_id=%s order by game_version',(pid,)).fetchall()
            self.assertEqual([row['game_version'] for row in versions],['1.2.0','2.0.0'])

    def test_share_preview_is_read_only_and_escapes_public_text(self):
        raw,_,p=self.make_participant();ctx,s=self.started(raw);code=p['participant']['referral_code']
        with fixtures.app_tx() as conn:
            operations.finish_session(conn,s['session_id'],{},dict(ctx,verification=self.verification))
            conn.execute('update dino_dev.participant set nickname=%s where id=%s',('<b>public</b>',p['participant']['id']))
            before=conn.execute('select (select count(*) from dino_dev.invitation_visit) visits,(select count(*) from dino_dev.ticket_ledger) ledger').fetchone()
            card=share_page.public_card(conn,code,'record_share','2.0.0',ctx['campaign_id'])
            target=share_page.share_target(code,{'link':['record_share'],'share':['share_safe_123'],'contact':['01000000000'],'channel':['x</script>']})
            html=share_page.render_share_page(card,'https://example.test',code,target).decode()
            self.assertIn(str(self.play['score']),html);self.assertIn('&lt;b&gt;public&lt;/b&gt;',html)
            self.assertNotIn('<script>alert',html);self.assertNotIn('01000000000',html)
            self.assertNotIn('channel',target)
            conn.execute('update dino_dev.participant set is_public=false where id=%s',(p['participant']['id'],))
            private=share_page.public_card(conn,code,'record_share','2.0.0',ctx['campaign_id'])
            self.assertEqual(private['title'],'공룡 점프 챌린지')
            after=conn.execute('select (select count(*) from dino_dev.invitation_visit) visits,(select count(*) from dino_dev.ticket_ledger) ledger').fetchone()
            self.assertEqual(before,after)

    def test_new_events_accept_safe_dimensions_and_reject_personal_text(self):
        raw,_,_=self.make_participant();ctx=self.ctx(raw)
        contracts=[('loading_data_ready',{'connected':True}),('loading_intro_completed',{'reduced_motion':True}),('game_coin_collected',{'coin_count':2,'coin_score':20,'score':6200,'tick':200}),('game_heart_collected',{'hearts':1}),('game_revived',{'revive_count':2}),('content_viewed',{'content':'study_note','position':'benefit_guides'}),('content_clicked',{'content':'job_photo','position':'benefit_guides'}),('scratch_reveal_requested',{'action':'keyboard'}),('share_attempted',{'link_kind':'record_share','status':'attempted'}),('game_completed',{'end_reason':'TIME_LIMIT','game_version':'2.0.0'})]
        events=[{'event_id':'evt_'+secrets.token_hex(10),'name':name,'screen':'home','occurred_at':dt.datetime.now(dt.timezone.utc).isoformat(),'dimensions':dims} for name,dims in contracts]
        draw_ctas=[('home','LOCKED'),('result','AVAILABLE'),('invite','DRAWN'),('claims','AVAILABLE')]
        events.extend({'event_id':'evt_'+secrets.token_hex(10),'name':'draw_cta_clicked','screen':source,
                       'occurred_at':dt.datetime.now(dt.timezone.utc).isoformat(),
                       'dimensions':{'source':source,'draw_status':draw_status}}
                      for source,draw_status in draw_ctas)
        events.append(dict(events[-1],event_id='evt_'+secrets.token_hex(10),dimensions={'content':'my-phone-01000000000'}))
        with fixtures.app_tx() as conn:
            _,result=operations.events_batch(conn,{'events':events},ctx)
            self.assertEqual(result,{
                'accepted':14,'duplicates':0,'rejected':1,
                'rejections':[{'index':14,'reason':'INVALID_DIMENSIONS'}],
            })
            stored=conn.execute("select screen,dimensions->>'source' source,dimensions->>'draw_status' draw_status from dino_dev.analytics_event where event_name='draw_cta_clicked' order by screen").fetchall()
            self.assertEqual({(row['screen'],row['source'],row['draw_status']) for row in stored},
                             {(source,source,draw_status) for source,draw_status in draw_ctas})

    def test_event_batch_rejections_distinguish_retryable_participant_linking(self):
        owner,_,owner_data=self.make_participant();other,_,_=self.make_participant()
        owner_id=owner_data['participant']['id']
        now=dt.datetime.now(dt.timezone.utc).isoformat()
        with fixtures.app_tx() as conn:
            observation=conn.execute(
                'select id from dino_dev.observation where participant_id=%s order by created_at desc limit 1',
                (owner_id,),
            ).fetchone()['id']
            session=operations.create_session(
                conn,{},self.ctx(owner,idempotency_key=secrets.token_urlsafe(24)),
            )[1]['session_id']

        linked_event={
            'event_id':'evt_linked_'+secrets.token_hex(8),'name':'page_view','screen':'home',
            'occurred_at':now,'observation_id':observation,'dimensions':{},
        }
        malformed_events=[
            {'event_id':'bad','name':'page_view','screen':'home','occurred_at':now,'dimensions':{}},
            {'event_id':'evt_dims_'+secrets.token_hex(8),'name':'page_view','screen':'home',
             'occurred_at':now,'dimensions':{'source':'person@example.com'}},
            {'event_id':'evt_time_'+secrets.token_hex(8),'name':'page_view','screen':'home',
             'occurred_at':'2020-01-01T00:00:00Z','dimensions':{}},
            {'event_id':'evt_context_'+secrets.token_hex(8),'name':'page_view','screen':'home',
             'occurred_at':now,'screen_view_id':'bad','dimensions':{}},
            {'event_id':'evt_shape_'+secrets.token_hex(8),'name':'page_view','screen':'home',
             'occurred_at':now,'dimensions':[]},
        ]

        with fixtures.app_tx() as conn:
            _,waiting=operations.events_batch(conn,{'events':[linked_event]},fixtures.context())
            _,accepted=operations.events_batch(conn,{'events':[linked_event]},self.ctx(owner))
            _,duplicate=operations.events_batch(conn,{'events':[linked_event]},self.ctx(owner))
            _,foreign=operations.events_batch(conn,{'events':[
                dict(linked_event,event_id='evt_foreign_obs_'+secrets.token_hex(8)),
                dict(linked_event,event_id='evt_foreign_game_'+secrets.token_hex(8),
                     observation_id=None,game_session_id=session),
            ]},self.ctx(other))
            _,malformed=operations.events_batch(conn,{'events':malformed_events},self.ctx(owner))
            _,missing_observation=operations.events_batch(conn,{'events':[
                dict(linked_event,event_id='evt_missing_obs_'+secrets.token_hex(8),
                     observation_id='obs_missing_12345678'),
            ]},self.ctx(owner))

        self.assertEqual(waiting,{
            'accepted':0,'duplicates':0,'rejected':1,
            'rejections':[{'index':0,'reason':'PARTICIPANT_NOT_READY'}],
        })
        self.assertEqual(accepted,{'accepted':1,'duplicates':0,'rejected':0})
        self.assertEqual(duplicate,{'accepted':0,'duplicates':1,'rejected':0})
        self.assertEqual(foreign,{
            'accepted':0,'duplicates':0,'rejected':2,
            'rejections':[
                {'index':0,'reason':'CONTEXT_OWNERSHIP'},
                {'index':1,'reason':'CONTEXT_OWNERSHIP'},
            ],
        })
        self.assertEqual(malformed,{
            'accepted':0,'duplicates':0,'rejected':5,
            'rejections':[
                {'index':0,'reason':'INVALID_EVENT'},
                {'index':1,'reason':'INVALID_DIMENSIONS'},
                {'index':2,'reason':'INVALID_TIME'},
                {'index':3,'reason':'INVALID_CONTEXT'},
                {'index':4,'reason':'INVALID_DIMENSIONS'},
            ],
        })
        self.assertEqual(missing_observation,{
            'accepted':0,'duplicates':0,'rejected':1,
            'rejections':[{'index':0,'reason':'CONTEXT_OWNERSHIP'}],
        })
        for result in (waiting,foreign,malformed,missing_observation):
            serialized=json.dumps(result)
            self.assertNotIn(linked_event['event_id'],serialized)
            self.assertNotIn(observation,serialized)
            self.assertNotIn(owner,serialized)

    def test_share_kinds_do_not_bypass_pair_deduplication(self):
        inviter,_,p=self.make_participant();code=p['participant']['referral_code'];visitor,_,_=self.make_participant()
        first=self.qualify(visitor,code,self.attributed_visit(visitor,code,'retry_invite'))
        self.assertEqual((first['status'],first['granted']),('REWARDED',1))
        for kind in ('record_share','prize_share','retry_invite'):
            again=self.qualify(visitor,code,self.attributed_visit(visitor,code,kind))
            self.assertEqual((again['status'],again['reason'],again['granted']),
                             ('ALREADY_REWARDED','PAIR_ALREADY_REWARDED',0))
        with fixtures.app_tx() as conn:
            info=operations.referral_me(conn,self.ctx(inviter))[1]
            self.assertEqual(info['ticket_totals'],{'granted':1,'used':0,'refunded':0})
            self.assertEqual(info['valid_visits'],1)

    def test_each_share_kind_rewards_a_distinct_visitor_and_third_starts_cooldown(self):
        inviter,_,p=self.make_participant();code=p['participant']['referral_code']
        for expected_balance,kind in enumerate(('retry_invite','record_share','prize_share'),start=1):
            visitor,_,_=self.make_participant()
            result=self.qualify(visitor,code,self.attributed_visit(visitor,code,kind))
            self.assertEqual((result['status'],result['granted'],result['inviter_balance']),
                             ('REWARDED',1,expected_balance))
            self.assertEqual(result['cooldown_until'] is not None,expected_balance==3)
        with fixtures.app_tx() as conn:
            info=operations.referral_me(conn,self.ctx(inviter))[1]
            self.assertEqual(info['ticket_totals'],{'granted':3,'used':0,'refunded':0})
            self.assertEqual((info['valid_visits'],info['rewarded_pairs'],info['invitation_balance']),(3,3,3))
            self.assertIsNotNone(info['cooldown_until'])
