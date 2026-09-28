import concurrent.futures,contextlib,datetime as dt,hashlib,hmac,os,secrets,sys,time,unittest,uuid
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/"server"))
import psycopg
from psycopg.rows import dict_row
import auth,operations

DSN=os.getenv("PHASE1_TEST_DATABASE_URL","postgres://postgres@127.0.0.1:55433/dino_phase1_v2_test")
PEPPER="test-pepper-0123456789-test-pepper"
@contextlib.contextmanager
def app_tx():
    with psycopg.connect(DSN,row_factory=dict_row) as conn:
        with conn.transaction():
            conn.execute("set local role dino_dev_app")
            yield conn
def h(value):return auth.token_hash(value,PEPPER)
def context(**extra):
    value={"environment":"test","deployment":"test","event_version":"phase1-v1","campaign_id":"gemini_dino_phase1_test","base_url":"http://127.0.0.1:3000","project_ref":"local","request_id":"test","invite_active_ms":3000,"participant_cookie_max_age":2592000,"ip_subject":"test-ip"};value.update(extra);return value

class BackendPhase1Test(unittest.TestCase):
    def setUp(self):
        with psycopg.connect(DSN) as conn:
            conn.execute("truncate dino_dev.idempotency_request,dino_dev.analytics_event,dino_dev.admin_audit,dino_dev.ranking_snapshot_entry,dino_dev.ranking_snapshot,dino_dev.claim_contact,dino_dev.claim,dino_dev.inventory_history,dino_dev.draw,dino_dev.ranking_contact,dino_dev.best_score,dino_dev.game_session,dino_dev.invitation_reward,dino_dev.invitation_visit,dino_dev.ticket_ledger,dino_dev.bootstrap,dino_dev.observation,dino_dev.participant restart identity cascade")
            conn.execute("update dino_dev.prize set probability=case id when 'test_coffee' then .20 when 'test_shipping' then .05 else .75 end")
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) select 'test_coffee_'||lpad(n::text,3,'0'),'test_coffee' from generate_series(1,20)n on conflict(id) do update set status='AVAILABLE',reserved_by_draw_id=null,reserved_at=null,paid_at=null")
            conn.execute("insert into dino_dev.inventory_item(id,prize_id) select 'test_shipping_'||lpad(n::text,3,'0'),'test_shipping' from generate_series(1,5)n on conflict(id) do update set status='AVAILABLE',reserved_by_draw_id=null,reserved_at=null,paid_at=null")
    def make_participant(self,invite_code=None):
        eid="event_"+secrets.token_hex(8);oid="obs_"+secrets.token_hex(8);bootstrap=hmac.new(PEPPER.encode(),("bootstrap:"+eid).encode(),hashlib.sha256).hexdigest();raw=auth.deterministic_participant_token(bootstrap,PEPPER);nonce=secrets.token_urlsafe(32)
        ctx=context(idempotency_key=secrets.token_urlsafe(32),bootstrap_token=bootstrap,bootstrap_token_hash=h(bootstrap),new_participant_token=raw,new_participant_token_hash=h(raw),participant_token_hash="",invite_nonce=nonce,invite_nonce_hash=h(nonce))
        with app_tx() as conn:
            operations.create_observation(conn,{"observation_id":oid,"event_id":eid},ctx)
            status,res=operations.participant_init(conn,{"bootstrap_token":bootstrap,"observation_id":oid,"invite_code":invite_code},ctx)
        return raw,status,res
    def qualify(self,visitor,code,nonce):
        with app_tx() as conn:
            conn.execute("update dino_dev.invitation_visit set created_at=clock_timestamp()-interval '4 seconds' where nonce_hash=%s",(h(nonce),))
            return operations.qualify_referral(conn,{"code":code,"visit_nonce":nonce,"active_ms":3000,"interacted":True},context(participant_token_hash=h(visitor),visit_nonce_hash=h(nonce)))[1]
    def create_share_intent(self,conn,raw,kind="retry_invite",claim_id=None):
        token=secrets.token_urlsafe(32);body={"kind":kind}
        if claim_id:body["claim_id"]=claim_id
        _,created=operations.create_share_intent(conn,body,context(participant_token_hash=h(raw),share_webhook_enabled=True,new_share_callback_token=token,new_share_callback_token_hash=h(token),kakao_app_id="123456"))
        return created,token
    def confirm_share(self,conn,created,token,resource_id=None,chat_type="DirectChat",**extra):
        body={"CHAT_TYPE":chat_type,"HASH_CHAT_ID":"chat_"+secrets.token_hex(8),**created["callback_args"],**extra}
        return operations.kakao_share_webhook(conn,body,context(kakao_webhook_verified=True,kakao_resource_id=resource_id or "resource_"+secrets.token_hex(12),share_callback_token_hash=h(token),kakao_app_id="123456"))[1]
    def make_finished_session(self,raw,index):
        ctx=context(participant_token_hash=h(raw),idempotency_key=f"finished-session-{index}-{secrets.token_hex(8)}")
        with app_tx() as conn:
            _,created=operations.create_session(conn,{},ctx)
            conn.execute("update dino_dev.game_session set status='FINISHED',score=10,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(created["session_id"],))
        return ctx
    def finish_verified(self,conn,raw,sid,score,valid=True,preview_unlimited_play=False):
        operations.start_session(conn,sid,context(participant_token_hash=h(raw)))
        conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '3 seconds' where id=%s",(sid,))
        return operations.finish_session(conn,sid,{},context(
            participant_token_hash=h(raw),preview_unlimited_play=preview_unlimited_play,
            verification={"valid":valid,"score":score,"ticks":120,"reason":"VERIFIED" if valid else "INVALID_TEST_RESULT","summary":{},"end_reason":"COLLISION" if valid else None}))
    def make_admin(self,permissions):
        uid=uuid.uuid4()
        with psycopg.connect(DSN) as conn:conn.execute("insert into dino_dev.admin_member(auth_user_id,display_name,permissions) values(%s,'TEST_admin',%s)",(uid,permissions))
        return context(admin_user_id=str(uid),idempotency_key=secrets.token_urlsafe(32))
    def test_anonymous_replay_grants_exactly_one_initial_ticket(self):
        eid="event_"+secrets.token_hex(8);oid="obs_"+secrets.token_hex(8);key=secrets.token_urlsafe(32)
        bootstrap=hmac.new(PEPPER.encode(),("bootstrap:"+eid).encode(),hashlib.sha256).hexdigest();raw=auth.deterministic_participant_token(bootstrap,PEPPER)
        ctx=context(idempotency_key=key,bootstrap_token=bootstrap,bootstrap_token_hash=h(bootstrap),new_participant_token=raw,new_participant_token_hash=h(raw),participant_token_hash="",invite_nonce=secrets.token_urlsafe(32),invite_nonce_hash=h("unused"))
        body={"observation_id":oid,"event_id":eid}
        with app_tx() as conn:
            first_observation=operations.create_observation(conn,body,ctx)
            replay_observation=operations.create_observation(conn,body,ctx)
            status,res=operations.participant_init(conn,{"bootstrap_token":bootstrap,"observation_id":oid},ctx)
            replay_status,replay=operations.participant_init(conn,{"bootstrap_token":bootstrap,"observation_id":oid},ctx)
        self.assertEqual(first_observation,replay_observation);self.assertEqual((status,replay_status),(201,200));self.assertEqual(res["participant"]["id"],replay["participant"]["id"])
        with app_tx() as conn:
            row=conn.execute("select count(*) n,sum(delta) total from dino_dev.ticket_ledger where participant_id=%s",(res["participant"]["id"],)).fetchone()
        self.assertEqual((row["n"],row["total"]),(1,1))
    def test_verified_score_at_or_below_100_refunds_initial_ticket_exactly_once(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32))
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx);sid=session["session_id"]
            status,result=self.finish_verified(conn,raw,sid,100)
            replay_status,replay=operations.finish_session(conn,sid,{},context(participant_token_hash=h(raw)))
            participant=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='LOW_SCORE_REFUND' and source_id=%s",(pid,sid)).fetchone()["n"]
        self.assertEqual((status,replay_status,participant["initial_balance"],refunds),(200,200,1,1))
        self.assertEqual(result["tickets"]["available_total"],1)
        self.assertEqual(result["refund"],{"status":"REFUNDED","ticket_kind":"INITIAL","reason":"LOW_SCORE"})
        self.assertFalse(result["ticket_consumed"]);self.assertEqual(replay["refund"],result["refund"])
    def test_verified_score_above_100_consumes_ticket(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
            _,result=self.finish_verified(conn,raw,session["session_id"],101)
            participant=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='LOW_SCORE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((participant["initial_balance"],refunds),(0,0))
        self.assertEqual(result["refund"],{"status":"NOT_DUE","ticket_kind":"INITIAL","reason":None})
        self.assertTrue(result["ticket_consumed"]);self.assertEqual(result["tickets"]["available_total"],0)
    def test_low_score_invitation_refund_preserves_cap_and_cooldown(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0,invitation_balance=3,cooldown_until=clock_timestamp()+interval '10 hours' where id=%s",(pid,))
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
            reserved=conn.execute("select invitation_balance,invitation_refund_pending,cooldown_until from dino_dev.participant where id=%s",(pid,)).fetchone()
            _,result=self.finish_verified(conn,raw,session["session_id"],0)
            restored=conn.execute("select invitation_balance,invitation_refund_pending,cooldown_until from dino_dev.participant where id=%s",(pid,)).fetchone()
            totals=operations.referral_me(conn,context(participant_token_hash=h(raw)))[1]["ticket_totals"]
        self.assertEqual((reserved["invitation_balance"],reserved["invitation_refund_pending"]),(2,1))
        self.assertEqual((restored["invitation_balance"],restored["invitation_refund_pending"]),(3,0))
        self.assertEqual(restored["cooldown_until"],reserved["cooldown_until"])
        self.assertEqual(result["refund"],{"status":"REFUNDED","ticket_kind":"INVITATION","reason":"LOW_SCORE"})
        self.assertEqual(totals,{"granted":0,"used":1,"refunded":1})
    def test_low_score_unlimited_session_does_not_mint_ticket(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32),preview_unlimited_play=True))
            _,result=self.finish_verified(conn,raw,session["session_id"],50,preview_unlimited_play=True)
            participant=conn.execute("select initial_balance,invitation_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='LOW_SCORE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((participant["initial_balance"],participant["invitation_balance"],refunds),(0,0,0))
        self.assertTrue(result["tickets"]["unlimited_play"]);self.assertFalse(result["ticket_consumed"])
        self.assertEqual(result["refund"]["status"],"NOT_DUE")
    def test_rejected_low_score_does_not_refund_ticket(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
            status,result=self.finish_verified(conn,raw,session["session_id"],50,valid=False)
            participant=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='LOW_SCORE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((status,result["status"],participant["initial_balance"],refunds),(422,"REJECTED",0,0))
    def test_abandon_unfinished_initial_ticket_refunds_once(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32))
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx);sid=session["session_id"]
            operations.start_session(conn,sid,ctx)
            _,first=operations.abandon_session(conn,sid,ctx);_,again=operations.abandon_session(conn,sid,ctx)
            p=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='INCOMPLETE_REFUND' and source_id=%s",(pid,sid)).fetchone()["n"]
        self.assertEqual((first["status"],again["status"],p["initial_balance"],refunds),("ABORTED","ABORTED",1,1))
        self.assertEqual(first["refund"],{"status":"REFUNDED","ticket_kind":"INITIAL","reason":"INCOMPLETE_GAME"})
        self.assertEqual(first["tickets"]["available_total"],1)
    def test_concurrent_abandon_refunds_only_once(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
        def abandon(_index):
            with app_tx() as conn:return operations.abandon_session(conn,session["session_id"],context(participant_token_hash=h(raw)))[1]
        with concurrent.futures.ThreadPoolExecutor(max_workers=2) as pool:results=list(pool.map(abandon,range(2)))
        with app_tx() as conn:
            p=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='INCOMPLETE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((p["initial_balance"],refunds),(1,1));self.assertTrue(all(r["status"]=="ABORTED" for r in results))
    def test_abandon_finished_preserves_result_and_does_not_refund(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
            conn.execute("update dino_dev.game_session set status='FINISHED',score=321,valid_ticks=120,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(session["session_id"],))
            _,result=operations.abandon_session(conn,session["session_id"],context(participant_token_hash=h(raw)))
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='INCOMPLETE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((result["status"],result["result"]["score"],refunds),("FINISHED",321,0))
    def test_abandon_unlimited_session_does_not_mint_ticket(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32),preview_unlimited_play=True)
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            _,session=operations.create_session(conn,{},ctx);_,result=operations.abandon_session(conn,session["session_id"],ctx)
            p=conn.execute("select initial_balance,invitation_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='INCOMPLETE_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((p["initial_balance"],p["invitation_balance"],refunds),(0,0,0))
        self.assertEqual(result["refund"]["status"],"NOT_DUE");self.assertTrue(result["tickets"]["unlimited_play"])
    def test_abandon_fault_reported_invitation_restores_balance_without_review(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        self.make_finished_session(raw,"before-invitation")
        with app_tx() as conn:
            intent,token=self.create_share_intent(conn,raw);self.confirm_share(conn,intent,token)
            _,session=operations.create_session(conn,{},context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32)))
            sid=session["session_id"]
            conn.execute("update dino_dev.game_session set status='FAULT_REPORTED',fault_reason='CLIENT_ERROR',fault_review_status='PENDING',fault_review_version=1 where id=%s",(sid,))
            _,result=operations.abandon_session(conn,sid,context(participant_token_hash=h(raw)))
            state=conn.execute("select invitation_balance,invitation_refund_pending from dino_dev.participant where id=%s",(pid,)).fetchone()
            game=conn.execute("select status,fault_review_status,ticket_refund_status from dino_dev.game_session where id=%s",(sid,)).fetchone()
        self.assertEqual((state["invitation_balance"],state["invitation_refund_pending"]),(1,0))
        self.assertEqual((game["status"],game["fault_review_status"],game["ticket_refund_status"]),("ABORTED","NONE","REFUNDED"))
        self.assertEqual(result["refund"],{"status":"REFUNDED","ticket_kind":"INVITATION","reason":"INCOMPLETE_GAME"})
    def test_expired_active_session_can_be_abandoned_and_refunded(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32))
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx);sid=session["session_id"]
            operations.start_session(conn,sid,ctx)
            conn.execute("update dino_dev.game_session set expires_at=clock_timestamp()-interval '1 second' where id=%s",(sid,))
            pending=operations.get_me(conn,ctx)[1]["pending_game_session"]
            _,result=operations.abandon_session(conn,sid,ctx)
            p=conn.execute("select initial_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
        self.assertEqual(pending["status"],"FAULT_REPORTED")
        self.assertEqual((result["status"],result["refund"]["status"],p["initial_balance"]),("ABORTED","REFUNDED",1))
    def test_each_confirmed_friend_share_grants_until_balance_cap(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            intents=[self.create_share_intent(conn,raw) for _ in range(4)]
            results=[self.confirm_share(conn,intent,token) for intent,token in intents]
            replay=self.confirm_share(conn,*intents[0])
            me=operations.referral_me(conn,context(participant_token_hash=h(raw)))[1]
            grants=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='SHARE_GRANT'",(pid,)).fetchone()["n"]
        self.assertEqual([r["reward_status"] for r in results],["granted","granted","granted","blocked_cooldown"])
        self.assertTrue(replay["duplicate"]);self.assertEqual((grants,me["invitation_balance"],me["confirmed_shares"],me["ticket_totals"]["granted"]),(3,3,4,3))
    def test_legacy_share_reward_is_disabled_and_memo_chat_never_grants(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as legacy:operations.share_reward(conn,{"share_id":"share_old_0001","method":"kakao","status":"attempted"},context(participant_token_hash=h(raw)))
            intent,token=self.create_share_intent(conn,raw);result=self.confirm_share(conn,intent,token,chat_type="MemoChat")
            grants=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='SHARE_GRANT'",(pid,)).fetchone()["n"]
        self.assertEqual(legacy.exception.code,"SHARE_WEBHOOK_REQUIRED");self.assertEqual((result["status"],result["reward_status"],grants),("rejected","not_eligible",0))
    def test_share_intent_proof_is_owned_unforgeable_and_resource_id_is_single_use(self):
        raw,_,created=self.make_participant();other,_,_=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            first,token=self.create_share_intent(conn,raw);second,second_token=self.create_share_intent(conn,raw)
            with self.assertRaises(operations.DomainError) as forged:self.confirm_share(conn,first,"wrong_"+secrets.token_urlsafe(32),resource_id="resource-shared")
            accepted=self.confirm_share(conn,first,token,resource_id="resource-shared")
            duplicate=self.confirm_share(conn,second,second_token,resource_id="resource-shared")
            with self.assertRaises(operations.DomainError) as hidden:operations.get_share_intent(conn,first["share_id"],context(participant_token_hash=h(other)))
            grants=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='SHARE_GRANT'",(pid,)).fetchone()["n"]
        self.assertEqual((forged.exception.code,accepted["reward_status"],duplicate["duplicate"],hidden.exception.code,grants),("INVALID_WEBHOOK","granted",True,"SHARE_INTENT_NOT_FOUND",1))
    def test_claim_submit_requires_confirmed_owned_claim_bound_share(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            conn.execute("insert into dino_dev.claim(id,campaign_id,participant_id,claim_type) values('claim_webhook','gemini_dino_phase1_test',%s,'RANKING')",(pid,))
            conn.execute("""insert into dino_dev.claim_contact_draft
              (claim_id,recipient_name,contact,school,synthetic,consent_at,consent_version)
              values('claim_webhook','TEST_user','01000000000','TEST_school',true,clock_timestamp(),'claim-contact-v1')""")
            intent,token=self.create_share_intent(conn,raw,"record_share","claim_webhook")
            with self.assertRaises(operations.DomainError) as pending:operations.submit_claim(conn,"claim_webhook",{"share_intent_id":intent["share_id"]},context(participant_token_hash=h(raw)))
            self.confirm_share(conn,intent,token);_,submitted=operations.submit_claim(conn,"claim_webhook",{"share_intent_id":intent["share_id"]},context(participant_token_hash=h(raw)))
            _,draft=operations.claim_draft_get(conn,"claim_webhook",context(participant_token_hash=h(raw)))
        self.assertEqual((pending.exception.code,submitted["status"],draft["share_intent_id"]),("SHARE_STEP_REQUIRED","INFORMATION_RECEIVED",intent["share_id"]))
    def test_concurrent_webhooks_grant_at_most_three(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:intents=[self.create_share_intent(conn,raw) for _ in range(10)]
        def reward(pair):
            intent,token=pair
            with app_tx() as conn:return self.confirm_share(conn,intent,token)
        with concurrent.futures.ThreadPoolExecutor(max_workers=10) as pool:results=list(pool.map(reward,intents))
        with app_tx() as conn:
            p=conn.execute("select invitation_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            grants=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='SHARE_GRANT'",(pid,)).fetchone()["n"]
        self.assertEqual((sum(1 for r in results if r["reward_status"]=="granted"),p["invitation_balance"],grants),(3,3,3))
    def test_invalid_cookie_is_not_replaced(self):
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as caught:operations.participant_init(conn,{},context(participant_token_hash=h("invalid"),invite_nonce="x",invite_nonce_hash=h("x")))
        self.assertEqual(caught.exception.code,"SESSION_INVALID")
    def test_old_top3_request_requires_current_rank_before_collection(self):
        entries=[]
        for score in (400,300,200,100):
            raw,_,created=self.make_participant();pid=created['participant']['id']
            ctx=context(participant_token_hash=h(raw),game_version='2.1.0',idempotency_key=secrets.token_urlsafe(24))
            with app_tx() as conn:
                _,session=operations.create_session(conn,{},ctx);sid=session['session_id']
                conn.execute("update dino_dev.game_session set status='FINISHED',score=%s,valid_ticks=%s,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(score,score*6,sid))
                conn.execute("insert into dino_dev.versioned_best_score(participant_id,game_version,session_id,score,achieved_at) values(%s,'2.1.0',%s,%s,clock_timestamp())",(pid,sid,score))
            entries.append((pid,sid,ctx))
        pid,sid,ctx=entries[-1]
        with app_tx() as conn:
            conn.execute("insert into dino_dev.ranking_contact(participant_id,game_version) values(%s,'2.1.0')",(pid,))
            me=operations.get_me(conn,ctx)[1]
            self.assertEqual(me['rank'],4)
            self.assertEqual(me['top3_profile']['status'],'NOT_REQUIRED')
            self.assertFalse(operations.ranking_profile_get(conn,ctx)[1]['required'])
            session=conn.execute('select * from dino_dev.game_session where id=%s',(sid,)).fetchone()
            self.assertFalse(operations.finish_response(conn,session)['top3_profile']['required'])
            with self.assertRaises(operations.DomainError) as caught:operations.ranking_profile_post(conn,{},ctx)
            self.assertEqual(caught.exception.code,'TOP3_PROFILE_NOT_REQUIRED')
            self.assertEqual(conn.execute('select count(*) n from dino_dev.claim_contact').fetchone()['n'],0)
            conn.execute('update dino_dev.game_session set score=500 where id=%s',(sid,))
            conn.execute("update dino_dev.versioned_best_score set score=500 where participant_id=%s",(pid,))
            self.assertTrue(operations.get_me(conn,ctx)[1]['top3_profile']['required'])
            _,submitted=operations.ranking_profile_post(conn,{'name':'TEST_ranker','contact':'01000000000','school':'TEST_school','consent':True,'notice_version':'top3-contact-v1'},ctx)
            self.assertEqual(submitted['status'],'SUBMITTED')
    def test_reset_cookie_recovers_with_fresh_bootstrap_only(self):
        eid="event_"+secrets.token_hex(8);oid="obs_"+secrets.token_hex(8)
        bootstrap=secrets.token_urlsafe(32);raw=auth.deterministic_participant_token(bootstrap,PEPPER)
        ctx=context(idempotency_key=secrets.token_urlsafe(32),bootstrap_token=bootstrap,bootstrap_token_hash=h(bootstrap),new_participant_token=raw,new_participant_token_hash=h(raw),participant_token_hash=h("deleted-participant-cookie"),invite_nonce="unused",invite_nonce_hash=h("unused"))
        body={"bootstrap_token":bootstrap,"observation_id":oid}
        with app_tx() as conn:
            operations.create_observation(conn,{"event_id":eid,"observation_id":oid},ctx)
            status,result=operations.participant_init(conn,body,ctx)
            replay_status,replay=operations.participant_init(conn,body,ctx)
            count=conn.execute("select count(*) n from dino_dev.ticket_ledger").fetchone()["n"]
        self.assertEqual((status,replay_status,count),(201,200,1))
        self.assertEqual(result["_set_cookie_token"],raw)
        self.assertEqual(result["participant"]["id"],replay["participant"]["id"])
    def test_fresh_bootstrap_does_not_replace_blocked_or_expired_account(self):
        raw,_,result=self.make_participant();pid=result["participant"]["id"]
        for expired,expected in ((False,"PARTICIPANT_BLOCKED"),(True,"SESSION_INVALID")):
            with psycopg.connect(DSN) as conn:
                conn.execute("update dino_dev.participant set status='BLOCKED',token_expires_at=clock_timestamp()+make_interval(secs=>%s) where id=%s",(-60 if expired else 3600,pid))
            with app_tx() as conn:
                with self.assertRaises(operations.DomainError) as caught:
                    operations.participant_init(conn,{"bootstrap_token":"fresh"},context(participant_token_hash=h(raw),bootstrap_token_hash=h("fresh")))
            self.assertEqual(caught.exception.code,expected)
    def test_all_participants_can_replay_without_ticket_or_ledger_changes(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
        for index in range(2):
            ctx=context(participant_token_hash=h(raw),idempotency_key=f"unlimited-{index}-{secrets.token_hex(8)}",preview_unlimited_play=True)
            with app_tx() as conn:
                _,me=operations.get_me(conn,ctx);self.assertTrue(me["tickets"]["unlimited_play"]);self.assertEqual(me["tickets"]["available_total"],0)
                status,session=operations.create_session(conn,{},ctx);self.assertEqual(status,201)
                row=conn.execute("select ticket_kind,ticket_refund_status from dino_dev.game_session where id=%s",(session["session_id"],)).fetchone()
                self.assertEqual((row["ticket_kind"],row["ticket_refund_status"]),("INITIAL","NOT_DUE"))
                conn.execute("update dino_dev.game_session set status='FINISHED',score=0,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp() where id=%s",(session["session_id"],))
        with app_tx() as conn:
            participant=conn.execute("select initial_balance,invitation_balance,invitation_refund_pending from dino_dev.participant where id=%s",(pid,)).fetchone()
            charged=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='PLAY_CONSUME'",(pid,)).fetchone()["n"]
        self.assertEqual((participant["initial_balance"],participant["invitation_balance"],participant["invitation_refund_pending"],charged),(0,0,0,0))
    def test_preview_unlimited_applies_to_multiple_unlisted_participants_only_in_test_environments(self):
        for _ in range(2):
            raw,_,created=self.make_participant();pid=created["participant"]["id"]
            ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32),preview_unlimited_play=True)
            with app_tx() as conn:
                conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
                self.assertTrue(operations.get_me(conn,ctx)[1]["tickets"]["unlimited_play"])
                self.assertEqual(operations.create_session(conn,{},ctx)[0],201)
        row={"id":"p_anyone","status":"ACTIVE","synthetic":True}
        self.assertFalse(operations._unlimited_play(row,{"environment":"production","preview_unlimited_play":True}))
        self.assertFalse(operations._unlimited_play(dict(row,synthetic=False),ctx))
        self.assertFalse(operations._unlimited_play(dict(row,status="BLOCKED"),ctx))
        self.assertFalse(operations._unlimited_play(row,dict(ctx,preview_unlimited_play="true")))
    def test_disabled_preview_cannot_spoof_unlimited_play_in_request_body(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32))
            _,me=operations.get_me(conn,ctx);self.assertFalse(me["tickets"]["unlimited_play"])
            with self.assertRaises(operations.DomainError) as caught:operations.create_session(conn,{"unlimited_play":True,"participant_id":pid},ctx)
        self.assertEqual(caught.exception.code,"NO_TICKETS")
    def test_free_session_fault_review_does_not_mint_ticket_or_refund_ledger(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32),preview_unlimited_play=True)
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            _,created_session=operations.create_session(conn,{},ctx);sid=created_session["session_id"]
            operations.start_session(conn,sid,ctx)
            conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '3 seconds' where id=%s",(sid,))
            operations.checkpoint(conn,sid,{"tick":120},ctx);operations.report_fault(conn,sid,{"reason":"NETWORK_ERROR","last_tick":120},ctx)
            conn.execute("update dino_dev.game_session set fault_reported_at=clock_timestamp()-interval '11 seconds' where id=%s",(sid,))
            _,reviewed=operations.get_session(conn,sid,ctx)
            participant=conn.execute("select initial_balance,invitation_balance from dino_dev.participant where id=%s",(pid,)).fetchone()
            refunds=conn.execute("select count(*)::int n from dino_dev.ticket_ledger where participant_id=%s and source_type='FAULT_REFUND'",(pid,)).fetchone()["n"]
        self.assertEqual((reviewed["status"],reviewed["refund"]["status"],reviewed["fault_review"]["status"]),("ABORTED","NOT_DUE","AUTO_APPROVED"))
        self.assertEqual((participant["initial_balance"],participant["invitation_balance"],refunds),(0,0,0))
    def test_disabling_unlimited_keeps_reserved_session_but_blocks_next_free_session(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"];key=secrets.token_urlsafe(32)
        allowed=context(participant_token_hash=h(raw),idempotency_key=key,preview_unlimited_play=True)
        revoked=context(participant_token_hash=h(raw),idempotency_key=key,preview_unlimited_play=False)
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            first_status,first=operations.create_session(conn,{},allowed)
            replay_status,replay=operations.create_session(conn,{},revoked)
            started_status,started=operations.start_session(conn,first["session_id"],revoked)
            conn.execute("update dino_dev.game_session set status='FINISHED',score=0,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp() where id=%s",(first["session_id"],))
            with self.assertRaises(operations.DomainError) as caught:operations.create_session(conn,{},dict(revoked,idempotency_key=secrets.token_urlsafe(32)))
        self.assertEqual((first_status,replay_status,started_status),(201,200,200));self.assertEqual(first["session_id"],replay["session_id"]);self.assertEqual(started["status"],"ACTIVE");self.assertEqual(caught.exception.code,"NO_TICKETS")
    def test_valid_cookie_links_second_tab_only_with_matching_bootstrap_proof(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        event_id="event_second_tab";observation_id="obs_second_tab";bootstrap="bootstrap_second_tab_proof";nonce=secrets.token_urlsafe(32)
        ctx=context(idempotency_key=secrets.token_urlsafe(32),participant_token_hash=h(raw),bootstrap_token=bootstrap,bootstrap_token_hash=h(bootstrap),invite_nonce=nonce,invite_nonce_hash=h(nonce))
        with app_tx() as conn:
            operations.create_observation(conn,{"observation_id":observation_id,"event_id":event_id},ctx)
            operations.participant_init(conn,{"bootstrap_token":bootstrap,"observation_id":observation_id},ctx)
            linked=conn.execute("select participant_id from dino_dev.observation where id=%s",(observation_id,)).fetchone()["participant_id"]
        self.assertEqual(linked,pid)
    def test_qualified_visits_are_tracking_only_and_never_grant_tickets(self):
        inviter,_,inviter_res=self.make_participant();code=inviter_res["participant"]["referral_code"]
        for index in range(3):
            visitor,_,res=self.make_participant(code);nonce=res["invite_visit"]["visit_nonce"]
            with app_tx() as conn:
                conn.execute("update dino_dev.invitation_visit set created_at=clock_timestamp()-interval '4 seconds' where nonce_hash=%s",(h(nonce),))
                _,result=operations.qualify_referral(conn,{"code":code,"visit_nonce":nonce,"active_ms":3000,"interacted":True},context(participant_token_hash=h(visitor),visit_nonce_hash=h(nonce)))
                self.assertEqual((result["status"],result["granted"]),("QUALIFIED",0))
        with app_tx() as conn:
            p=conn.execute("select invitation_balance,cooldown_until from dino_dev.participant where token_hash=%s",(h(inviter),)).fetchone()
        self.assertEqual((p["invitation_balance"],p["cooldown_until"]),(0,None))
        _visitor,_,fourth=self.make_participant(code);self.assertEqual(fourth["invite_visit"]["status"],"PENDING");self.assertIsNotNone(fourth["invite_visit"]["visit_nonce"])
    def test_same_visitor_rewards_two_inviters_but_each_pair_only_once(self):
        inviter_a,_,a=self.make_participant();inviter_b,_,b=self.make_participant();visitor,_,visit_a=self.make_participant(a["participant"]["referral_code"])
        first=self.qualify(visitor,a["participant"]["referral_code"],visit_a["invite_visit"]["visit_nonce"])
        with app_tx() as conn:
            duplicate=operations.qualify_referral(conn,{"code":a["participant"]["referral_code"],"visit_nonce":visit_a["invite_visit"]["visit_nonce"],"active_ms":3000,"interacted":True},context(participant_token_hash=h(visitor),visit_nonce_hash=h(visit_a["invite_visit"]["visit_nonce"])))[1]
            p=conn.execute("select * from dino_dev.participant where token_hash=%s",(h(visitor),)).fetchone()
            raw_b="nonce_b_"+secrets.token_urlsafe(24);visit_b=operations._invite_visit(conn,p,b["participant"]["referral_code"],context(invite_nonce=raw_b,invite_nonce_hash=h(raw_b)))
            row=conn.execute("select nonce_hash from dino_dev.invitation_visit where inviter_id=%s and visitor_id=%s order by created_at desc limit 1",(b["participant"]["id"],p["id"])).fetchone()
            conn.execute("update dino_dev.invitation_visit set created_at=clock_timestamp()-interval '4 seconds' where nonce_hash=%s",(row["nonce_hash"],))
            second=operations.qualify_referral(conn,{"code":b["participant"]["referral_code"],"visit_nonce":"unused","active_ms":3000,"interacted":True},context(participant_token_hash=h(visitor),visit_nonce_hash=row["nonce_hash"]))[1]
        self.assertEqual((first["status"],duplicate["status"],second["status"]),("QUALIFIED","QUALIFIED","QUALIFIED"))
        with app_tx() as conn:
            balances=conn.execute("select invitation_balance from dino_dev.participant where id in (%s,%s) order by id",(a["participant"]["id"],b["participant"]["id"])).fetchall()
        self.assertEqual(sorted(r["invitation_balance"] for r in balances),[0,0])
    def test_invalid_and_self_invites_return_explicit_rejections_and_share_attribution(self):
        raw,_,participant=self.make_participant();pid=participant["participant"]["id"];ctx=context(participant_token_hash=h(raw),invite_nonce="unused",invite_nonce_hash=h("unused"))
        with app_tx() as conn:
            invalid=operations.participant_init(conn,{"invite_code":"missing_invite_code"},ctx)[1]["invite_visit"]
            own=operations.participant_init(conn,{"invite_code":participant["participant"]["referral_code"]},ctx)[1]["invite_visit"]
        self.assertEqual((invalid["status"],own["status"]),("INVALID_CODE","SELF_INVITE"));self.assertIsNone(invalid["visit_nonce"]);self.assertIsNone(own["visit_nonce"])
        inviter,_,data=self.make_participant();share_id="share_"+secrets.token_urlsafe(16);nonce=secrets.token_urlsafe(32)
        with app_tx() as conn:
            visitor=conn.execute("select * from dino_dev.participant where id=%s",(pid,)).fetchone();visit=operations._invite_visit(conn,visitor,data["participant"]["referral_code"],context(invite_nonce=nonce,invite_nonce_hash=h(nonce)),share_id)
            stored=conn.execute("select share_id from dino_dev.invitation_visit where nonce_hash=%s",(h(nonce),)).fetchone()["share_id"]
        self.assertEqual(visit["status"],"PENDING");self.assertEqual(stored,share_id)
    def test_one_hundred_concurrent_visits_never_grant_tickets(self):
        inviter,_,data=self.make_participant();code=data["participant"]["referral_code"];visits=[]
        for _ in range(100):
            visitor,_,created=self.make_participant(code);visits.append((visitor,created["invite_visit"]["visit_nonce"]))
        with psycopg.connect(DSN) as conn:conn.execute("update dino_dev.invitation_visit set created_at=clock_timestamp()-interval '4 seconds'")
        def grant(pair):
            visitor,nonce=pair
            try:return self.qualify(visitor,code,nonce)["status"]
            except operations.DomainError as error:return error.code
        with concurrent.futures.ThreadPoolExecutor(max_workers=20) as pool:statuses=list(pool.map(grant,visits))
        with app_tx() as conn:p=conn.execute("select invitation_balance,invitation_refund_pending,cooldown_until from dino_dev.participant where token_hash=%s",(h(inviter),)).fetchone()
        self.assertEqual(statuses.count("QUALIFIED"),100);self.assertEqual(p["invitation_balance"]+p["invitation_refund_pending"],0);self.assertIsNone(p["cooldown_until"])
    def test_visit_issue_ignores_ticket_cap_and_cooldown_because_it_is_analytics_only(self):
        inviter,_,data=self.make_participant();code=data["participant"]["referral_code"]
        with psycopg.connect(DSN) as conn:conn.execute("update dino_dev.participant set invitation_balance=3,cooldown_until=clock_timestamp()+interval '10 hours' where token_hash=%s",(h(inviter),))
        _visitor,_,created=self.make_participant(code)
        self.assertEqual(created["invite_visit"]["status"],"PENDING");self.assertIsNotNone(created["invite_visit"]["visit_nonce"])
    def test_fault_refunds_original_ticket_once(self):
        raw,_,_=self.make_participant();ctx=context(participant_token_hash=h(raw),idempotency_key="create-session-1")
        with app_tx() as conn:
            _,created=operations.create_session(conn,{"event_id":"evt-create"},ctx);sid=created["session_id"]
            operations.start_session(conn,sid,ctx);conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '3 seconds' where id=%s",(sid,));operations.checkpoint(conn,sid,{"tick":120},ctx)
            _,reported=operations.report_fault(conn,sid,{"reason":"NETWORK_ERROR","last_tick":120},ctx);self.assertEqual(reported["refund"]["status"],"REVIEW_REQUIRED")
            conn.execute("update dino_dev.game_session set fault_reported_at=clock_timestamp()-interval '11 seconds' where id=%s",(sid,))
            _,recovered=operations.get_session(conn,sid,ctx);_,again=operations.get_session(conn,sid,ctx)
        self.assertEqual(recovered["refund"]["status"],"REFUNDED");self.assertEqual(again["refund"]["status"],"REFUNDED")
    def test_second_network_fault_in_24h_remains_pending_for_review(self):
        raw,_,_=self.make_participant()
        def fault(key):
            ctx=context(participant_token_hash=h(raw),idempotency_key=key)
            with app_tx() as conn:
                _,created=operations.create_session(conn,{},ctx);sid=created["session_id"];operations.start_session(conn,sid,ctx)
                conn.execute("update dino_dev.game_session set started_at=clock_timestamp()-interval '3 seconds' where id=%s",(sid,));operations.checkpoint(conn,sid,{"tick":120},ctx);operations.report_fault(conn,sid,{"reason":"NETWORK_ERROR","last_tick":120},ctx)
                conn.execute("update dino_dev.game_session set fault_reported_at=clock_timestamp()-interval '11 seconds' where id=%s",(sid,));return operations.get_session(conn,sid,ctx)[1]
        self.assertEqual(fault("network-fault-one")["fault_review"]["status"],"AUTO_APPROVED")
        second=fault("network-fault-two");self.assertEqual(second["fault_review"]["status"],"PENDING");self.assertEqual(second["refund"]["status"],"REVIEW_REQUIRED")
    def test_expired_reserved_refunds_but_expired_active_requires_review(self):
        raw,_,_=self.make_participant();ctx=context(participant_token_hash=h(raw),idempotency_key="reserved-expiry")
        with app_tx() as conn:
            _,reserved=operations.create_session(conn,{},ctx);conn.execute("update dino_dev.game_session set expires_at=clock_timestamp()-interval '1 second' where id=%s",(reserved["session_id"],));_,me=operations.get_me(conn,ctx)
        self.assertEqual(me["tickets"]["initial"],1)
        ctx["idempotency_key"]="active-expiry"
        with app_tx() as conn:
            _,active=operations.create_session(conn,{},ctx);operations.start_session(conn,active["session_id"],ctx);conn.execute("update dino_dev.game_session set expires_at=clock_timestamp()-interval '1 second' where id=%s",(active["session_id"],));_,me=operations.get_me(conn,ctx)
            row=conn.execute("select status,fault_review_status,ticket_refund_status from dino_dev.game_session where id=%s",(active["session_id"],)).fetchone()
        self.assertEqual((row["status"],row["fault_review_status"],row["ticket_refund_status"]),("FAULT_REPORTED","PENDING","PENDING"));self.assertEqual(me["tickets"]["initial"],0)
    def test_one_draw_per_campaign_participant(self):
        raw,_,res=self.make_participant();ctx=context(participant_token_hash=h(raw),idempotency_key="create-session-2")
        with app_tx() as conn:
            _,created=operations.create_session(conn,{},ctx);sid=created["session_id"]
            conn.execute("update dino_dev.game_session set status='FINISHED',score=10,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(sid,))
            _,first=operations.create_draw(conn,{"pouch_index":0,"expected_round_number":1},ctx)
            _,second=operations.create_draw(conn,{"pouch_index":0,"expected_round_number":1},ctx)
            with self.assertRaises(operations.DomainError) as conflicting_pouch:
                operations.create_draw(conn,{"pouch_index":2,"expected_round_number":1},ctx)
        self.assertEqual(first["draw_id"],second["draw_id"]);self.assertEqual(first["pouch_index"],second["pouch_index"])
        self.assertEqual(conflicting_pouch.exception.code,"DRAW_ROUND_CONFLICT")
        with app_tx() as conn:
            intent,token=self.create_share_intent(conn,raw);self.confirm_share(conn,intent,token);ctx["idempotency_key"]="retry-after-draw"
            _,retry=operations.create_session(conn,{},ctx)
        self.assertEqual(retry["ticket_kind"],"INVITATION")
    def test_other_participant_cannot_read_game_session(self):
        owner,_,_=self.make_participant();other,_,_=self.make_participant();ctx=context(participant_token_hash=h(owner),idempotency_key="owned-session")
        with app_tx() as conn:_,session=operations.create_session(conn,{},ctx)
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as caught:operations.get_session(conn,session["session_id"],context(participant_token_hash=h(other)))
        self.assertEqual((caught.exception.code,caught.exception.status),("SESSION_NOT_FOUND",404))
    def test_top3_contact_persists_after_rank_drop_and_snapshot_never_finalizes_winner(self):
        players=[self.make_participant()[0] for _ in range(4)];scores=[100,400,400,300]
        with psycopg.connect(DSN) as conn:
            for index,(raw,score) in enumerate(zip(players,scores)):
                pid=conn.execute("select id from dino_dev.participant where token_hash=%s",(h(raw),)).fetchone()[0];sid=f"snapshot_session_{index}"
                conn.execute("insert into dino_dev.game_session(id,participant_id,campaign_id,idempotency_key,seed,version,status,ticket_kind,ticket_refund_status,expires_at,score,valid_ticks,verification_result,finished_at,environment) values(%s,%s,'gemini_dino_phase1_test',%s,1,'1.2.0','FINISHED','INITIAL','NOT_DUE',clock_timestamp()+interval '1 minute',%s,60,'VERIFIED',clock_timestamp(),'test')",(sid,pid,"snapshot-key-"+str(index),score))
                conn.execute("insert into dino_dev.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,%s,clock_timestamp())",(pid,sid,score))
            first_pid=conn.execute("select id from dino_dev.participant where token_hash=%s",(h(players[0]),)).fetchone()[0];conn.execute("insert into dino_dev.ranking_contact(participant_id) values(%s)",(first_pid,))
        profile_ctx=context(participant_token_hash=h(players[0]),idempotency_key="top3-profile")
        with app_tx() as conn:
            _,submitted=operations.ranking_profile_post(conn,{"name":"TEST_ranker","contact":"01000000000","school":"TEST_school","consent":True,"notice_version":"top3-contact-v1"},profile_ctx);_,public=operations.ranking_profile_get(conn,profile_ctx)
        self.assertEqual(public["status"],"SUBMITTED");self.assertNotIn("contact",public)
        admin=self.make_admin(["claims:read","claims:write","ranking:read","ranking:write"])
        with app_tx() as conn:
            contacts=operations.admin_ranking_contacts(conn,admin)[1]["ranking_contacts"];claim=conn.execute("select * from dino_dev.claim where id=%s",(submitted["claim_id"],)).fetchone();admin["idempotency_key"]="verify-ranking-claim"
            verified=operations.admin_claim_patch(conn,claim["id"],{"expected_version":claim["version"],"verification_status":"PENDING","verification_reference":"TEST_REF_student_pending","event_id":"evt_verify_rank"},admin)[1]
            pending=operations.admin_claim_patch(conn,claim["id"],{"status":"PENDING_REVIEW","expected_version":verified["version"],"event_id":"evt_rank_pending"},admin)[1]
            contacted=operations.admin_claim_patch(conn,claim["id"],{"status":"CONTACTED","expected_version":pending["version"],"event_id":"evt_rank_contacted"},admin)[1]
            with self.assertRaises(operations.DomainError) as blocked_payment:operations.admin_claim_patch(conn,claim["id"],{"status":"PAID","expected_version":contacted["version"],"event_id":"evt_rank_paid"},admin)
            snapshot=operations.create_admin_ranking_snapshot(conn,{"event_id":"evt_snapshot"},admin)[1]
            tied=conn.execute("select count(*)::int n from dino_dev.ranking_snapshot_entry where snapshot_id=%s and tied",(snapshot["id"],)).fetchone()["n"]
        mine=next(row for row in contacts if row["participant_id"]==first_pid)
        self.assertEqual((mine["ranking_status"],mine["contact"],verified["verification_status"]),("SUBMITTED","01000000000","PENDING"));self.assertEqual((blocked_payment.exception.code,blocked_payment.exception.status),("FINAL_RANKING_UNDECIDED",409));self.assertEqual(tied,2);self.assertEqual((snapshot["status"],snapshot["tie_policy"],snapshot["final_awards_created"]),("DRAFT","UNDECIDED",False))
    def test_admin_can_block_participant_and_revoke_cookie_session(self):
        raw,_,data=self.make_participant();admin=self.make_admin(["participants:write"]);admin["idempotency_key"]="participant-block"
        with app_tx() as conn:_,result=operations.admin_participant_patch(conn,data["participant"]["id"],{"status":"BLOCKED","expected_status":"ACTIVE","revoke_session":True,"reason":"TEST abuse review","event_id":"evt_block"},admin)
        self.assertTrue(result["session_revoked"]);self.assertEqual(result["status"],"BLOCKED")
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as caught:operations.get_me(conn,context(participant_token_hash=h(raw)))
        self.assertEqual(caught.exception.code,"SESSION_INVALID")
    def test_last_inventory_item_is_never_allocated_twice(self):
        participants=[self.make_participant()[0] for _ in range(12)]
        contexts=[self.make_finished_session(raw,index) for index,raw in enumerate(participants)]
        with psycopg.connect(DSN) as conn:
            prize=conn.execute("select id from dino_dev.prize where campaign_id='gemini_dino_phase1_test' and category<>'NO_PRIZE' order by id limit 1").fetchone()[0]
            conn.execute("update dino_dev.prize set probability=case when id=%s then 1 else 0 end",(prize,));conn.execute("update dino_dev.inventory_item set status='VOID',reserved_by_draw_id=null,reserved_at=null where prize_id=%s",(prize,));conn.execute("update dino_dev.inventory_item set status='AVAILABLE' where id=(select id from dino_dev.inventory_item where prize_id=%s order by id limit 1)",(prize,))
        def draw(args):
            raw,ctx=args
            for _ in range(10):
                try:
                    with app_tx() as conn:return operations.create_draw(conn,{"pouch_index":0},ctx)[1]
                except operations.DomainError as error:
                    if error.code!="INVENTORY_BUSY":raise
                    time.sleep(.01)
            raise AssertionError("inventory lock did not clear")
        with concurrent.futures.ThreadPoolExecutor(max_workers=12) as pool:results=list(pool.map(draw,zip(participants,contexts)))
        self.assertEqual(sum(1 for result in results if result["is_won"]),1)
        with app_tx() as conn:
            allocated=conn.execute("select count(*) n,count(distinct inventory_item_id) distinct_n from dino_dev.draw where inventory_item_id is not null").fetchone()
        self.assertEqual((allocated["n"],allocated["distinct_n"]),(1,1))
    def test_analytics_rejects_pii_urls_stale_time_and_foreign_session(self):
        owner,_,_=self.make_participant();other,_,_=self.make_participant();foreign=self.make_finished_session(other,"foreign")
        with app_tx() as conn:sid=conn.execute("select id from dino_dev.game_session where participant_id=(select id from dino_dev.participant where token_hash=%s) limit 1",(h(other),)).fetchone()["id"]
        now=dt.datetime.now(dt.timezone.utc).isoformat().replace("+00:00","Z")
        events=[
            {"event_id":"evt_pii_12345678","name":"page_view","screen":"home","occurred_at":now,"dimensions":{"source":"person@example.com"}},
            {"event_id":"evt_url_12345678","name":"page_view","screen":"home","occurred_at":now,"dimensions":{"source":"https://evil.example/?token=x"}},
            {"event_id":"evt_old_12345678","name":"page_view","screen":"home","occurred_at":"2020-01-01T00:00:00Z","dimensions":{}},
            {"event_id":"evt_foreign_1234","name":"game_checkpoint","screen":"game","occurred_at":now,"game_session_id":sid,"dimensions":{"checkpoint":60}},
        ]
        with app_tx() as conn:_,result=operations.events_batch(conn,{"events":events},context(participant_token_hash=h(owner)))
        self.assertEqual(result,{
            "accepted":0,"duplicates":0,"rejected":4,
            "rejections":[
                {"index":0,"reason":"INVALID_DIMENSIONS"},
                {"index":1,"reason":"INVALID_DIMENSIONS"},
                {"index":2,"reason":"INVALID_TIME"},
                {"index":3,"reason":"CONTEXT_OWNERSHIP"},
            ],
        })
    def test_app_role_cannot_change_guard_membership_or_append_only_ledger(self):
        with app_tx() as conn:
            for sql in ("update dino_dev.environment_guard set project_ref='evil'","insert into dino_dev.admin_member(auth_user_id,display_name) values(gen_random_uuid(),'evil')","update dino_dev.ticket_ledger set delta=-1"):
                with self.assertRaises(psycopg.errors.InsufficientPrivilege):
                    with conn.transaction():conn.execute(sql)

if __name__=="__main__":unittest.main()
