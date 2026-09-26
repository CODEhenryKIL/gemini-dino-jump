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
    def make_finished_session(self,raw,index):
        ctx=context(participant_token_hash=h(raw),idempotency_key=f"finished-session-{index}-{secrets.token_hex(8)}")
        with app_tx() as conn:
            _,created=operations.create_session(conn,{},ctx)
            conn.execute("update dino_dev.game_session set status='FINISHED',score=10,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(created["session_id"],))
        return ctx
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
    def test_invalid_cookie_is_not_replaced(self):
        with app_tx() as conn:
            with self.assertRaises(operations.DomainError) as caught:operations.participant_init(conn,{},context(participant_token_hash=h("invalid"),invite_nonce="x",invite_nonce_hash=h("x")))
        self.assertEqual(caught.exception.code,"SESSION_INVALID")
    def test_allowlisted_participant_can_replay_without_ticket_or_ledger_changes(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
        allowlist=frozenset({pid})
        for index in range(2):
            ctx=context(participant_token_hash=h(raw),idempotency_key=f"unlimited-{index}-{secrets.token_hex(8)}",preview_unlimited_participant_ids=allowlist)
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
    def test_unlisted_participant_cannot_spoof_unlimited_play_in_request_body(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        with app_tx() as conn:
            conn.execute("update dino_dev.participant set initial_balance=0 where id=%s",(pid,))
            ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32))
            _,me=operations.get_me(conn,ctx);self.assertFalse(me["tickets"]["unlimited_play"])
            with self.assertRaises(operations.DomainError) as caught:operations.create_session(conn,{"unlimited_play":True,"participant_id":pid},ctx)
        self.assertEqual(caught.exception.code,"NO_TICKETS")
    def test_free_session_fault_review_does_not_mint_ticket_or_refund_ledger(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"]
        ctx=context(participant_token_hash=h(raw),idempotency_key=secrets.token_urlsafe(32),preview_unlimited_participant_ids=frozenset({pid}))
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
    def test_allowlist_revocation_keeps_reserved_session_but_blocks_next_free_session(self):
        raw,_,created=self.make_participant();pid=created["participant"]["id"];key=secrets.token_urlsafe(32)
        allowed=context(participant_token_hash=h(raw),idempotency_key=key,preview_unlimited_participant_ids=frozenset({pid}))
        revoked=context(participant_token_hash=h(raw),idempotency_key=key,preview_unlimited_participant_ids=frozenset())
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
    def test_invitation_cap_and_cooldown_start_at_balance_three(self):
        inviter,_,inviter_res=self.make_participant();code=inviter_res["participant"]["referral_code"]
        for index in range(3):
            visitor,_,res=self.make_participant(code);nonce=res["invite_visit"]["visit_nonce"]
            with app_tx() as conn:
                conn.execute("update dino_dev.invitation_visit set created_at=clock_timestamp()-interval '4 seconds' where nonce_hash=%s",(h(nonce),))
                _,result=operations.qualify_referral(conn,{"code":code,"visit_nonce":nonce,"active_ms":3000,"interacted":True},context(participant_token_hash=h(visitor),visit_nonce_hash=h(nonce)))
                self.assertEqual(result["status"],"REWARDED")
        with app_tx() as conn:
            p=conn.execute("select invitation_balance,cooldown_until from dino_dev.participant where token_hash=%s",(h(inviter),)).fetchone()
        self.assertEqual(p["invitation_balance"],3);self.assertIsNotNone(p["cooldown_until"])
        _visitor,_,fourth=self.make_participant(code);self.assertEqual(fourth["invite_visit"]["status"],"COOLDOWN");self.assertIsNone(fourth["invite_visit"]["visit_nonce"])
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
        self.assertEqual((first["status"],duplicate["status"],second["status"]),("REWARDED","REWARDED","REWARDED"))
        with app_tx() as conn:
            balances=conn.execute("select invitation_balance from dino_dev.participant where id in (%s,%s) order by id",(a["participant"]["id"],b["participant"]["id"])).fetchall()
        self.assertEqual(sorted(r["invitation_balance"] for r in balances),[1,1])
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
    def test_one_hundred_concurrent_visits_never_exceed_three_tickets(self):
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
        self.assertEqual(statuses.count("REWARDED"),3);self.assertEqual(p["invitation_balance"]+p["invitation_refund_pending"],3);self.assertIsNotNone(p["cooldown_until"])
    def test_cooldown_allows_use_and_restarts_only_on_new_grant_to_three(self):
        inviter,_,data=self.make_participant();code=data["participant"]["referral_code"]
        for _ in range(3):
            visitor,_,created=self.make_participant(code);self.qualify(visitor,code,created["invite_visit"]["visit_nonce"])
        ctx=context(participant_token_hash=h(inviter),idempotency_key="cooldown-use-ticket")
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx)
            self.assertEqual(session["ticket_kind"],"INITIAL")
            conn.execute("update dino_dev.game_session set status='FINISHED',score=1,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(session["session_id"],))
        ctx["idempotency_key"]="cooldown-use-invite"
        with app_tx() as conn:
            _,session=operations.create_session(conn,{},ctx);self.assertEqual(session["ticket_kind"],"INVITATION")
            row=conn.execute("select * from dino_dev.game_session where id=%s",(session["session_id"],)).fetchone();operations._settle_invitation_pending(conn,row);conn.execute("update dino_dev.game_session set status='FINISHED',score=1,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(session["session_id"],))
        blocked_raw,_,blocked=self.make_participant(code);self.assertEqual(blocked["invite_visit"]["status"],"COOLDOWN")
        with psycopg.connect(DSN) as conn:conn.execute("update dino_dev.participant set cooldown_until=clock_timestamp()-interval '1 second' where token_hash=%s",(h(inviter),))
        nonce=secrets.token_urlsafe(32)
        with app_tx() as conn:
            blocked_participant=conn.execute("select * from dino_dev.participant where token_hash=%s",(h(blocked_raw),)).fetchone();fresh=operations._invite_visit(conn,blocked_participant,code,context(invite_nonce=nonce,invite_nonce_hash=h(nonce)))
        result=self.qualify(blocked_raw,code,fresh["visit_nonce"])
        self.assertEqual(result["status"],"REWARDED")
        until=dt.datetime.fromisoformat(result["cooldown_until"].replace("Z","+00:00"));self.assertGreater(until,dt.datetime.now(dt.timezone.utc)+dt.timedelta(hours=9,minutes=59))
    def test_cumulative_invitation_grants_do_not_block_while_balance_stays_below_three(self):
        inviter,_,data=self.make_participant();code=data["participant"]["referral_code"];self.make_finished_session(inviter,"consume-initial")
        for index in range(4):
            visitor,_,created=self.make_participant(code);self.assertEqual(self.qualify(visitor,code,created["invite_visit"]["visit_nonce"])["status"],"REWARDED")
            ctx=context(participant_token_hash=h(inviter),idempotency_key=f"consume-invite-{index}")
            with app_tx() as conn:
                _,session=operations.create_session(conn,{},ctx);self.assertEqual(session["ticket_kind"],"INVITATION")
                row=conn.execute("select * from dino_dev.game_session where id=%s",(session["session_id"],)).fetchone();operations._settle_invitation_pending(conn,row);conn.execute("update dino_dev.game_session set status='FINISHED',score=1,valid_ticks=60,verification_result='VERIFIED',finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s",(session["session_id"],))
        with app_tx() as conn:
            p=conn.execute("select invitation_balance,cooldown_until from dino_dev.participant where token_hash=%s",(h(inviter),)).fetchone();rewards=conn.execute("select count(*)::int n from dino_dev.invitation_reward where inviter_id=(select id from dino_dev.participant where token_hash=%s)",(h(inviter),)).fetchone()["n"]
        self.assertEqual((rewards,p["invitation_balance"],p["cooldown_until"]),(4,0,None))
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
            _,first=operations.create_draw(conn,{"pouch_index":0},ctx);_,second=operations.create_draw(conn,{"pouch_index":2},ctx)
        self.assertEqual(first["draw_id"],second["draw_id"]);self.assertEqual(first["pouch_index"],second["pouch_index"])
        visitor,_,visit=self.make_participant(res["participant"]["referral_code"]);self.qualify(visitor,res["participant"]["referral_code"],visit["invite_visit"]["visit_nonce"]);ctx["idempotency_key"]="retry-after-draw"
        with app_tx() as conn:_,retry=operations.create_session(conn,{},ctx)
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
            _,submitted=operations.ranking_profile_post(conn,{"name":"TEST_ranker","contact":"01000000000","school":"TEST_school"},profile_ctx);_,public=operations.ranking_profile_get(conn,profile_ctx)
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
            prize=conn.execute("select id from dino_dev.prize where category<>'NO_PRIZE' order by id limit 1").fetchone()[0]
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
