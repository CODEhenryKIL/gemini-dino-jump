"""Transactional Phase 1 business operations. No connection or network ownership."""
from __future__ import annotations
import datetime as dt
import hashlib, json, re, secrets, uuid
from urllib.parse import urlparse
import metrics

UTC=dt.timezone.utc
class DomainError(RuntimeError):
    def __init__(self,code,message,status=400,retryable=False):
        super().__init__(message); self.code=code; self.message=message; self.status=status; self.retryable=retryable
def _id(prefix): return f"{prefix}_{uuid.uuid4().hex}"
def _iso(value): return value.astimezone(UTC).isoformat().replace("+00:00","Z") if value else None
def _one(conn,sql,params=()): return conn.execute(sql,params).fetchone()
def _all(conn,sql,params=()): return list(conn.execute(sql,params).fetchall())
def _campaign(conn,lock=False):
    row=_one(conn,"select * from dino_dev.campaign where id=(select campaign_id from dino_dev.environment_guard where singleton)"+(" for update" if lock else ""))
    if not row: raise DomainError("CAMPAIGN_NOT_CONFIGURED","행사 설정이 준비되지 않았습니다.",503,True)
    return row
def _mutable(campaign):
    if campaign["status"]!="ACTIVE": raise DomainError("CAMPAIGN_UNAVAILABLE","현재 행사가 일시 중단되었습니다.",409)
def _participant(conn,ctx,lock=False,active=False):
    token_hash=ctx.get("participant_token_hash")
    if not token_hash: raise DomainError("UNAUTHORIZED","참가자 인증이 필요합니다.",401)
    row=_one(conn,"select * from dino_dev.participant where token_hash=%s and token_expires_at>clock_timestamp()"+(" for update" if lock else ""),(token_hash,))
    if not row: raise DomainError("SESSION_INVALID","참가자 인증이 만료되었거나 유효하지 않습니다.",401)
    if active and row["status"]!="ACTIVE": raise DomainError("PARTICIPANT_BLOCKED","현재 참여할 수 없습니다.",403)
    return row
def _public(row): return {"id":row["id"],"nickname":row["nickname"],"is_public":row["is_public"],"referral_code":row["referral_code"]}
def _tickets(row):
    return {"initial":row["initial_balance"],"invitation":row["invitation_balance"],"invitation_reserved":row["invitation_refund_pending"],"available_total":row["initial_balance"]+row["invitation_balance"],"cooldown_until":_iso(row["cooldown_until"]),"cooldown_notice_pending":row["cooldown_notice_pending"]}
def _event(conn,name,ctx,participant_id=None,event_id=None,screen=None,game_session_id=None,dimensions=None,observation_id=None,visit_session_id=None):
    conn.execute("""insert into dino_dev.analytics_event(event_id,campaign_id,participant_id,observation_id,event_name,screen,visit_session_id,game_session_id,dimensions,environment,deployment,event_version,synthetic,source,occurred_at)
      values(%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,true,'server',clock_timestamp()) on conflict(event_id) do nothing""",
      (event_id or _id("evt"),ctx["campaign_id"],participant_id,observation_id,name,screen,visit_session_id,game_session_id,json.dumps(dimensions or {}),ctx["environment"],ctx["deployment"],ctx["event_version"]))
def _admin(conn,ctx,permission=None):
    uid=ctx.get("admin_user_id")
    row=_one(conn,"select * from dino_dev.admin_member where auth_user_id=%s and active",(uid,)) if uid else None
    if not row: raise DomainError("ADMIN_FORBIDDEN","관리자 권한이 없습니다.",403)
    if permission and permission not in row["permissions"]: raise DomainError("ADMIN_FORBIDDEN","해당 관리자 권한이 없습니다.",403)
    return row
def _request_hash(body): return hashlib.sha256(json.dumps(body,sort_keys=True,separators=(",",":"),ensure_ascii=False,default=str).encode()).hexdigest()
def _revalidate_idempotent_replay(conn,method,path,ctx):
    if ctx.get("admin_user_id"):
        permission=None
        if method=="PATCH" and re.fullmatch(r"/api/admin/claims/[^/]+",path):permission="claims:write"
        elif method=="PATCH" and re.fullmatch(r"/api/admin/game-faults/[^/]+",path):permission="faults:write"
        elif method=="POST" and path=="/api/admin/ranking-snapshots":permission="ranking:write"
        elif method=="PATCH" and re.fullmatch(r"/api/admin/participants/[^/]+",path):permission="participants:write"
        elif method=="PATCH" and path=="/api/admin/campaign":permission="campaign:write"
        _admin(conn,ctx,permission)
        return
    if not ctx.get("participant_token_hash"):
        return
    active=(method,path) in {
      ("PATCH","/api/me/profile"),("POST","/api/referrals/qualify"),("POST","/api/referrals/cooldown-notice/ack"),
      ("POST","/api/game-sessions"),("POST","/api/ranking/profile"),("POST","/api/draws"),
    } or bool(re.fullmatch(r"/api/game-sessions/[^/]+/(?:start|checkpoint|finish|fault)",path)) or bool(re.fullmatch(r"/api/claims/[^/]+/submit",path))
    _participant(conn,ctx,active=active)
def _idempotent(conn,method,path,body,ctx,fn):
    key=ctx.get("idempotency_key")
    if not key: raise DomainError("IDEMPOTENCY_KEY_REQUIRED","요청 식별자가 필요합니다.",400)
    actor=ctx.get("admin_user_id") or ctx.get("participant_token_hash") or ctx.get("ip_subject")
    route=method+" "+path; digest=_request_hash(body)
    conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",(str(actor)+"|"+route+"|"+key,))
    old=_one(conn,"select * from dino_dev.idempotency_request where actor_key=%s and route=%s and idempotency_key=%s",(actor,route,key))
    if old:
        if old["request_hash"]!=digest: raise DomainError("IDEMPOTENCY_CONFLICT","같은 요청 식별자에 다른 값을 사용할 수 없습니다.",409)
        _revalidate_idempotent_replay(conn,method,path,ctx)
        return old["response_status"],old["response_body"]
    status,response=fn()
    conn.execute("insert into dino_dev.idempotency_request(actor_key,route,idempotency_key,request_hash,response_status,response_body) values(%s,%s,%s,%s,%s,%s::jsonb)",(actor,route,key,digest,status,json.dumps(response,default=str)))
    return status,response

def create_observation(conn,body,ctx):
    oid=str(body.get("observation_id") or ""); eid=str(body.get("event_id") or "")
    if not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",oid) or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",eid): raise DomainError("VALIDATION_ERROR","관측 식별자를 확인해 주세요.")
    link=str(body.get("link_kind") or "unknown");channel=str(body.get("channel_code") or "unknown");campaign_code=str(body.get("campaign_code") or "");share_id=str(body.get("share_id") or "")
    code_pattern=r"(?:unknown|[A-Za-z][A-Za-z0-9_-]{0,31})"
    if link not in {"initial","retry_invite","prize_share","direct","unknown"} or not re.fullmatch(code_pattern,channel) or (campaign_code and not re.fullmatch(code_pattern,campaign_code)) or (share_id and not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",share_id)): raise DomainError("VALIDATION_ERROR","유입 값을 확인해 주세요.")
    referrer=str(body.get("referrer_origin") or "");parsed=urlparse(referrer) if referrer else None
    if parsed and (parsed.scheme not in {"http","https"} or not parsed.hostname or parsed.path not in {"","/"} or parsed.query or parsed.fragment or parsed.username): raise DomainError("VALIDATION_ERROR","유입 출처는 origin만 허용합니다.")
    key=ctx.get("idempotency_key")
    if not key:raise DomainError("IDEMPOTENCY_KEY_REQUIRED","요청 식별자가 필요합니다.")
    if not re.fullmatch(r"[A-Za-z0-9_-]{32,128}",key):raise DomainError("INVALID_IDEMPOTENCY_KEY","초기 접속 식별자는 충분히 긴 무작위 값이어야 합니다.")
    digest=_request_hash(body);actor=ctx["ip_subject"]
    conn.execute("select pg_advisory_xact_lock(hashtextextended(%s,0))",(actor+"|observation|"+key,))
    old=_one(conn,"select id,event_id,request_hash from dino_dev.observation where actor_key=%s and idempotency_key=%s",(actor,key))
    if old and old["request_hash"]!=digest:raise DomainError("IDEMPOTENCY_CONFLICT","같은 요청 식별자에 다른 값을 사용할 수 없습니다.",409)
    if not old:
        replay=_one(conn,"select actor_key,idempotency_key from dino_dev.observation where event_id=%s or id=%s",(eid,oid))
        if replay:raise DomainError("OBSERVATION_REPLAY_DENIED","이미 사용된 초기 관측 정보입니다.",409)
        conn.execute("""insert into dino_dev.observation(id,event_id,actor_key,idempotency_key,request_hash,link_kind,channel_code,campaign_code,share_id,referrer_origin,environment)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(oid,eid,actor,key,digest,link,channel,campaign_code or None,share_id or None,referrer or None,ctx["environment"]))
    bootstrap=ctx["bootstrap_token"]; bh=ctx["bootstrap_token_hash"]
    conn.execute("insert into dino_dev.bootstrap(token_hash,observation_id,expires_at) values(%s,%s,clock_timestamp()+interval '10 minutes') on conflict(token_hash) do nothing",(bh,oid))
    return 201,{"observation_id":oid,"accepted":True,"bootstrap_token":bootstrap}

def _invite_visit(conn,p,invite_code,ctx,share_id=None):
    if not invite_code: return None
    inviter=_one(conn,"select * from dino_dev.participant where referral_code=%s and campaign_id=%s and status='ACTIVE' for update",(invite_code,p["campaign_id"]))
    if not inviter:return {"visit_nonce":None,"status":"INVALID_CODE","reason":"INVITE_CODE_NOT_FOUND","expires_at":None}
    if inviter["id"]==p["id"]:return {"visit_nonce":None,"status":"SELF_INVITE","reason":"SELF_INVITE_NOT_ALLOWED","expires_at":None}
    raw=ctx["invite_nonce"]; hashed=ctx["invite_nonce_hash"]
    existing=_one(conn,"select * from dino_dev.invitation_visit where inviter_id=%s and visitor_id=%s and status='PENDING' and expires_at>clock_timestamp() order by created_at desc limit 1",(inviter["id"],p["id"]))
    now=dt.datetime.now(UTC); issue_status="PENDING"; issue_reason=None
    if inviter["cooldown_until"] and inviter["cooldown_until"]>now:issue_status="COOLDOWN";issue_reason="INVITER_COOLDOWN_AT_ISSUE"
    elif inviter["invitation_balance"]+inviter["invitation_refund_pending"]>=3:issue_status="BALANCE_FULL";issue_reason="INVITER_BALANCE_FULL_AT_ISSUE"
    if existing:
        existing=_one(conn,"update dino_dev.invitation_visit set nonce_hash=%s,share_id=%s,expires_at=clock_timestamp()+interval '15 minutes' where id=%s returning *",(hashed,share_id,existing["id"]))
    else:
        existing=_one(conn,"""insert into dino_dev.invitation_visit(id,campaign_id,inviter_id,visitor_id,nonce_hash,share_id,expires_at)
          values(%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '15 minutes') returning *""",(_id("iv"),p["campaign_id"],inviter["id"],p["id"],hashed,share_id))
    if issue_status!="PENDING":
        existing=_one(conn,"update dino_dev.invitation_visit set status=%s,reason=%s where id=%s returning *",(issue_status,issue_reason,existing["id"]))
    return {"visit_nonce":raw if issue_status=="PENDING" else None,"status":issue_status,"reason":issue_reason,"expires_at":_iso(existing["expires_at"])}

def participant_init(conn,body,ctx):
    share_id=str(body.get("share_id") or "")
    if share_id and not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",share_id):raise DomainError("VALIDATION_ERROR","공유 식별자를 확인해 주세요.")
    if ctx.get("participant_token_hash"):
        p=_participant(conn,ctx,active=True)
        bootstrap=str(body.get("bootstrap_token") or "");oid=str(body.get("observation_id") or "")
        if bootstrap and oid and ctx.get("bootstrap_token_hash"):
            proof=_one(conn,"select observation_id from dino_dev.bootstrap where token_hash=%s and expires_at>clock_timestamp()",(ctx["bootstrap_token_hash"],))
            if proof and proof["observation_id"]==oid:conn.execute("update dino_dev.observation set participant_id=%s,linked_at=coalesce(linked_at,clock_timestamp()) where id=%s and participant_id is null",(p["id"],oid))
        visit=_invite_visit(conn,p,str(body.get("invite_code") or "")[:64],ctx,share_id or None)
        return 200,{"participant":_public(p),"tickets":_tickets(p),"invite_visit":visit}
    bootstrap=str(body.get("bootstrap_token") or "")
    if not bootstrap or ctx.get("bootstrap_token_hash") is None: raise DomainError("BOOTSTRAP_REQUIRED","초기 접속을 다시 시도해 주세요.",401)
    proof=_one(conn,"select * from dino_dev.bootstrap where token_hash=%s and expires_at>clock_timestamp() for update",(ctx["bootstrap_token_hash"],))
    if not proof: raise DomainError("BOOTSTRAP_INVALID","초기 접속을 다시 시도해 주세요.",401)
    p=_one(conn,"select * from dino_dev.participant where id=%s for update",(proof["participant_id"],)) if proof["participant_id"] else None
    created=False
    if not p:
        campaign=_campaign(conn,True); _mutable(campaign); pid=_id("p")
        p=_one(conn,"""insert into dino_dev.participant(id,campaign_id,token_hash,token_expires_at,nickname,referral_code,environment,first_link_kind,first_channel)
          values(%s,%s,%s,clock_timestamp()+make_interval(secs=>%s),%s,%s,%s,%s,%s) returning *""",(pid,campaign["id"],ctx["new_participant_token_hash"],ctx["participant_cookie_max_age"],f"공룡{secrets.randbelow(9000)+1000}",secrets.token_urlsafe(12),ctx["environment"],str(body.get("link_kind") or "unknown")[:32],str(body.get("channel") or "unknown")[:64]))
        conn.execute("insert into dino_dev.ticket_ledger(participant_id,ticket_kind,delta,source_type,source_id,balance_after) values(%s,'INITIAL',1,'INITIAL_GRANT','initial',1)",(pid,))
        conn.execute("update dino_dev.bootstrap set participant_id=%s,consumed_at=clock_timestamp() where token_hash=%s",(pid,ctx["bootstrap_token_hash"]))
        created=True
    oid=str(body.get("observation_id") or "")
    if oid and oid==proof["observation_id"]: conn.execute("update dino_dev.observation set participant_id=%s,linked_at=coalesce(linked_at,clock_timestamp()) where id=%s and participant_id is null",(p["id"],oid))
    visit=_invite_visit(conn,p,str(body.get("invite_code") or "")[:64],ctx,share_id or None)
    return (201 if created else 200),{"participant":_public(p),"tickets":_tickets(p),"invite_visit":visit,"_set_cookie_token":ctx["new_participant_token"]}

def get_me(conn,ctx):
    p=_participant(conn,ctx,True);_reconcile_expired(conn,p["id"]);p=_one(conn,"select * from dino_dev.participant where id=%s",(p["id"],));best=_one(conn,"select score from dino_dev.best_score where participant_id=%s",(p["id"],))
    rank=_one(conn,"select 1+count(*)::int rank from dino_dev.best_score where score>(select score from dino_dev.best_score where participant_id=%s)",(p["id"],)) if best else None
    live=_one(conn,"select id,status,ticket_kind,expires_at,last_checkpoint_tick from dino_dev.game_session where participant_id=%s and status in ('RESERVED','ACTIVE','FAULT_REPORTED') order by reserved_at desc limit 1",(p["id"],))
    draw=_one(conn,"select id from dino_dev.draw where campaign_id=%s and participant_id=%s",(p["campaign_id"],p["id"]))
    eligible=_one(conn,"select id from dino_dev.game_session where participant_id=%s and status='FINISHED' order by finished_at limit 1",(p["id"],))
    contact=_one(conn,"select status from dino_dev.ranking_contact where participant_id=%s",(p["id"],))
    claims=_one(conn,"select count(*)::int n from dino_dev.claim where participant_id=%s",(p["id"],))["n"]
    return 200,{"participant":_public(p),"tickets":_tickets(p),"best_score":best["score"] if best else 0,"rank":rank["rank"] if rank else None,"pending_game_session":dict(live) if live else None,"draw":{"status":"DRAWN" if draw else "AVAILABLE" if eligible else "LOCKED","draw_id":draw["id"] if draw else None},"top3_profile":{"status":contact["status"] if contact else "NOT_REQUIRED"},"claim_count":claims}

def patch_profile(conn,body,ctx):
    p=_participant(conn,ctx,True,True); nickname=str(body.get("nickname") or "").strip(); public=body.get("is_public")
    if not 1<=len(nickname)<=24 or not isinstance(public,bool): raise DomainError("VALIDATION_ERROR","프로필 값을 확인해 주세요.")
    p=_one(conn,"update dino_dev.participant set nickname=%s,is_public=%s,updated_at=clock_timestamp() where id=%s returning *",(nickname,public,p["id"]))
    return 200,{"participant":_public(p)}

def referral_me(conn,ctx):
    p=_participant(conn,ctx); counts=_one(conn,"""select count(*)::int valid_visits,count(*) filter(where status='REWARDED')::int rewarded_visits,
      count(*) filter(where status not in ('PENDING','REWARDED'))::int rejected_visits from dino_dev.invitation_visit where inviter_id=%s""",(p["id"],))
    pairs=_one(conn,"select count(*)::int n from dino_dev.invitation_reward where inviter_id=%s",(p["id"],))["n"]
    return 200,{"invite_url":ctx["base_url"]+"/invite/"+p["referral_code"],"referral_code":p["referral_code"],"invitation_balance":p["invitation_balance"],"invitation_reserved":p["invitation_refund_pending"],"cooldown_until":_iso(p["cooldown_until"]),"cooldown_notice_pending":p["cooldown_notice_pending"],"rewarded_pairs":pairs,**dict(counts)}

def qualify_referral(conn,body,ctx):
    visitor=_participant(conn,ctx,active=True); raw=str(body.get("visit_nonce") or "")
    try: active_ms=int(body.get("active_ms"))
    except (TypeError,ValueError): active_ms=0
    visit=_one(conn,"select * from dino_dev.invitation_visit where nonce_hash=%s for update",(ctx["visit_nonce_hash"] if raw else "",))
    if not visit or visit["visitor_id"]!=visitor["id"] or visit["expires_at"]<=dt.datetime.now(UTC):
        raise DomainError("INVALID_NONCE","초대 방문을 다시 시작해 주세요.",409)
    if visit["status"]!="PENDING": return 200,{"status":visit["status"],"reason":visit["reason"],"granted":1 if visit["status"]=="REWARDED" else 0}
    campaign=_campaign(conn);_mutable(campaign)
    inviter=_one(conn,"select * from dino_dev.participant where id=%s and status='ACTIVE' for update",(visit["inviter_id"],))
    if not inviter or inviter["campaign_id"]!=visitor["campaign_id"] or str(body.get("code") or "")!=inviter["referral_code"]: raise DomainError("INVALID_NONCE","초대 방문을 다시 시작해 주세요.",409)
    existing=_one(conn,"select id from dino_dev.invitation_reward where campaign_id=%s and inviter_id=%s and visitor_id=%s",(visit["campaign_id"],visit["inviter_id"],visitor["id"]))
    now=dt.datetime.now(UTC); status="REWARDED"; reason="QUALIFIED"; granted=1
    if existing: status="ALREADY_REWARDED"; reason="PAIR_ALREADY_REWARDED"; granted=0
    elif active_ms<ctx["invite_active_ms"] or body.get("interacted") is not True or visit["created_at"]>now-dt.timedelta(milliseconds=ctx["invite_active_ms"]): status="NOT_QUALIFIED"; reason="ACTIVE_TIME_OR_INTERACTION_REQUIRED"; granted=0
    elif inviter["cooldown_until"] and inviter["cooldown_until"]>now: status="COOLDOWN"; reason="INVITER_COOLDOWN"; granted=0
    elif inviter["invitation_balance"]+inviter["invitation_refund_pending"]>=3: status="BALANCE_FULL"; reason="INVITER_BALANCE_FULL"; granted=0
    if status=="REWARDED":
        rid=_id("ir"); new_balance=inviter["invitation_balance"]+1; cooldown=now+dt.timedelta(hours=10) if new_balance==3 else inviter["cooldown_until"]
        conn.execute("insert into dino_dev.invitation_reward(id,campaign_id,inviter_id,visitor_id,visit_id) values(%s,%s,%s,%s,%s)",(rid,visit["campaign_id"],inviter["id"],visitor["id"],visit["id"]))
        conn.execute("update dino_dev.participant set invitation_balance=%s,cooldown_until=%s,cooldown_notice_pending=case when %s=3 then true else cooldown_notice_pending end,updated_at=clock_timestamp() where id=%s",(new_balance,cooldown,new_balance,inviter["id"]))
        conn.execute("insert into dino_dev.ticket_ledger(participant_id,ticket_kind,delta,source_type,source_id,balance_after,cooldown_until) values(%s,'INVITATION',1,'INVITATION_GRANT',%s,%s,%s)",(inviter["id"],rid,new_balance,cooldown))
        _event(conn,"invitation_granted",ctx,inviter["id"],"invitation_granted:"+rid,dimensions={"balance":new_balance})
    conn.execute("update dino_dev.invitation_visit set status=%s,reason=%s,qualified_at=clock_timestamp(),active_ms=%s,interacted=%s where id=%s",(status,reason,active_ms,bool(body.get("interacted")),visit["id"]))
    inviter=_one(conn,"select * from dino_dev.participant where id=%s",(inviter["id"],))
    return 200,{"status":status,"reason":reason,"granted":granted,"inviter_balance":inviter["invitation_balance"],"cooldown_until":_iso(inviter["cooldown_until"])}

def cooldown_ack(conn,body,ctx):
    p=_participant(conn,ctx,True,True)
    if str(body.get("cooldown_until") or "")!=_iso(p["cooldown_until"]): raise DomainError("COOLDOWN_CHANGED","대기 상태가 변경되었습니다.",409)
    conn.execute("update dino_dev.participant set cooldown_notice_pending=false where id=%s",(p["id"],))
    return 200,{"acknowledged":True}

def _owned_session(conn,sid,pid,lock=False):
    row=_one(conn,"select * from dino_dev.game_session where id=%s"+(" for update" if lock else ""),(sid,))
    if not row or row["participant_id"]!=pid: raise DomainError("SESSION_NOT_FOUND","게임 기록을 찾을 수 없습니다.",404)
    return row
def _session(row):
    refund_status="REVIEW_REQUIRED" if row["fault_review_status"]=="PENDING" else row["ticket_refund_status"]
    return {"session_id":row["id"],"seed":row["seed"],"version":row["version"],"status":row["status"],"ticket_kind":row["ticket_kind"],"last_checkpoint_tick":row["last_checkpoint_tick"],"expires_at":_iso(row["expires_at"]),"refund":{"status":refund_status,"ticket_kind":row["ticket_kind"]},"fault_review":{"status":row["fault_review_status"],"version":row["fault_review_version"]}}
def create_session(conn,body,ctx):
    p=_participant(conn,ctx,True,True); campaign=_campaign(conn); _mutable(campaign)
    observation_id=body.get("observation_id");visit_session_id=body.get("visit_session_id")
    if observation_id is not None:
        observation_id=str(observation_id)
        if not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",observation_id):raise DomainError("VALIDATION_ERROR","게임 유입 관측값을 확인해 주세요.")
        observed=_one(conn,"select participant_id from dino_dev.observation where id=%s",(observation_id,))
        if not observed or observed["participant_id"]!=p["id"]:raise DomainError("INVALID_OBSERVATION_ATTRIBUTION","현재 참가자의 유입 관측만 연결할 수 있습니다.",409)
    if visit_session_id is not None:
        visit_session_id=str(visit_session_id)
        if not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",visit_session_id):raise DomainError("VALIDATION_ERROR","방문 세션 식별자를 확인해 주세요.")
    _reconcile_expired(conn,p["id"]);p=_one(conn,"select * from dino_dev.participant where id=%s for update",(p["id"],))
    old=_one(conn,"select * from dino_dev.game_session where participant_id=%s and idempotency_key=%s",(p["id"],ctx["idempotency_key"]))
    if old:return 200,_session(old)
    live=_one(conn,"select * from dino_dev.game_session where participant_id=%s and status in ('RESERVED','ACTIVE','FAULT_REPORTED') order by reserved_at desc limit 1 for update",(p["id"],))
    if live:return 200,_session(live)
    kind="INITIAL" if p["initial_balance"]>0 else "INVITATION" if p["invitation_balance"]>0 else None
    if not kind: raise DomainError("NO_TICKETS","게임권이 부족합니다.",409)
    if kind=="INITIAL":
        conn.execute("update dino_dev.participant set initial_balance=initial_balance-1,updated_at=clock_timestamp() where id=%s",(p["id"],)); after=p["initial_balance"]-1
    else:
        conn.execute("update dino_dev.participant set invitation_balance=invitation_balance-1,invitation_refund_pending=invitation_refund_pending+1,updated_at=clock_timestamp() where id=%s",(p["id"],)); after=p["invitation_balance"]-1
    sid=_id("gs"); conn.execute("insert into dino_dev.ticket_ledger(participant_id,ticket_kind,delta,source_type,source_id,balance_after) values(%s,%s,-1,'PLAY_CONSUME',%s,%s)",(p["id"],kind,sid,after))
    row=_one(conn,"""insert into dino_dev.game_session(id,participant_id,campaign_id,idempotency_key,seed,version,ticket_kind,expires_at,environment)
      values(%s,%s,%s,%s,%s,%s,%s,clock_timestamp()+interval '2 minutes',%s) returning *""",(sid,p["id"],campaign["id"],ctx["idempotency_key"],secrets.randbelow(2147483646)+1,campaign["game_version"],kind,ctx["environment"]))
    _event(conn,"game_start_approved",ctx,p["id"],"game_reserved:"+sid,game_session_id=sid,observation_id=observation_id,visit_session_id=visit_session_id)
    return 201,_session(row)
def start_session(conn,sid,ctx):
    p=_participant(conn,ctx,True,True); s=_owned_session(conn,sid,p["id"],True)
    if s["status"]=="ACTIVE": return 200,_session(s)
    if s["status"]!="RESERVED" or s["expires_at"]<=dt.datetime.now(UTC): raise DomainError("SESSION_NOT_STARTABLE","게임 시작 시간이 만료되었습니다.",409)
    s=_one(conn,"update dino_dev.game_session set status='ACTIVE',started_at=clock_timestamp(),expires_at=clock_timestamp()+interval '10 minutes' where id=%s returning *",(sid,))
    return 200,{**_session(s),"started_at":_iso(s["started_at"])}
def checkpoint(conn,sid,body,ctx):
    p=_participant(conn,ctx,active=True); s=_owned_session(conn,sid,p["id"],True)
    try: tick=int(body.get("tick"))
    except (TypeError,ValueError): raise DomainError("VALIDATION_ERROR","체크포인트를 확인해 주세요.")
    elapsed=(dt.datetime.now(UTC)-s["started_at"]).total_seconds() if s["started_at"] else 0
    if s["status"]!="ACTIVE" or not 60<=tick<=36000 or tick/60.0>elapsed+1.0 or (s["last_checkpoint_tick"] is not None and tick<s["last_checkpoint_tick"]): raise DomainError("CHECKPOINT_REJECTED","체크포인트 상태가 올바르지 않습니다.",409)
    conn.execute("update dino_dev.game_session set last_checkpoint_tick=%s where id=%s",(tick,sid)); return 202,{"session_id":sid,"tick":tick}
def _settle_invitation_pending(conn,s):
    if s["ticket_kind"]=="INVITATION" and s["ticket_refund_status"]=="PENDING":
        conn.execute("update dino_dev.participant set invitation_refund_pending=invitation_refund_pending-1 where id=%s",(s["participant_id"],))
def finish_session(conn,sid,body,ctx):
    p=_participant(conn,ctx,active=True); s=_owned_session(conn,sid,p["id"],True)
    if s["status"] in ("FINISHED","REJECTED"):
        return 200,finish_response(conn,s)
    if s["status"]!="ACTIVE": raise DomainError("SESSION_NOT_ACTIVE","진행 중인 게임만 종료할 수 있습니다.",409)
    v=ctx.get("verification")
    if not v: raise DomainError("VERIFICATION_REQUIRED","게임 검증 결과가 없습니다.",500)
    valid,score,ticks,reason=v; status="FINISHED" if valid else "REJECTED"
    elapsed=(dt.datetime.now(UTC)-s["started_at"]).total_seconds() if s["started_at"] else 0
    if ticks<60 or ticks/60.0>elapsed+1.0:valid=False;status="REJECTED";reason="IMPOSSIBLE_WALLCLOCK_DURATION"
    _settle_invitation_pending(conn,s)
    s=_one(conn,"update dino_dev.game_session set status=%s,score=%s,valid_ticks=%s,verification_result=%s,finished_at=clock_timestamp(),ticket_refund_status='NOT_DUE' where id=%s returning *",(status,score,ticks,reason,sid))
    if not valid:
        _event(conn,"game_verification_rejected",ctx,p["id"],"game_rejected:"+sid,game_session_id=sid,dimensions={"reason":reason})
        return 422,{"error":"GAME_VERIFICATION_FAILED","message":"게임 결과를 검증하지 못했습니다.","retryable":False,"session_id":sid,"status":"REJECTED","verification":reason}
    conn.execute("""insert into dino_dev.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,%s,clock_timestamp())
      on conflict(participant_id) do update set session_id=excluded.session_id,score=excluded.score,achieved_at=excluded.achieved_at where excluded.score>dino_dev.best_score.score""",(p["id"],sid,score))
    rank=_one(conn,"select 1+count(*)::int rank from dino_dev.best_score where score>%s",(score,))["rank"]
    if rank<=3: conn.execute("insert into dino_dev.ranking_contact(participant_id) values(%s) on conflict(participant_id) do nothing",(p["id"],))
    _event(conn,"game_finish_verified",ctx,p["id"],"game_finished:"+sid,game_session_id=sid,dimensions={"score":score,"rank":rank})
    return 200,finish_response(conn,s)
def finish_response(conn,s):
    best=_one(conn,"select score from dino_dev.best_score where participant_id=%s",(s["participant_id"],)); rank=_one(conn,"select 1+count(*)::int rank from dino_dev.best_score where score>%s",(s["score"],))["rank"] if s["status"]=="FINISHED" else None
    draw=_one(conn,"select id from dino_dev.draw where campaign_id=%s and participant_id=%s",(s["campaign_id"],s["participant_id"]))
    contact=_one(conn,"select status from dino_dev.ranking_contact where participant_id=%s",(s["participant_id"],))
    return {"session_id":s["id"],"status":s["status"],"verification":s["verification_result"],"score":s["score"],"best_score":best["score"] if best else 0,"rank":rank,"draw":{"status":"DRAWN" if draw else "AVAILABLE","draw_id":draw["id"] if draw else None},"top3_profile":{"required":bool(contact and contact["status"]=="REQUESTED"),"status":contact["status"] if contact else "NOT_REQUIRED"}}

def report_fault(conn,sid,body,ctx):
    p=_participant(conn,ctx,active=True); s=_owned_session(conn,sid,p["id"],True)
    if s["status"] in ("FINISHED","REJECTED"): return 200,finish_response(conn,s)
    if s["status"]=="ABORTED": return 200,_session(s)
    if s["status"]=="FAULT_REPORTED": return 200,{**_session(s),"refund":{"status":"REVIEW_REQUIRED","ticket_kind":s["ticket_kind"]}}
    reason=str(body.get("reason") or "")
    elapsed=(dt.datetime.now(UTC)-s["started_at"]).total_seconds() if s["started_at"] else 0
    if s["status"]!="ACTIVE" or reason not in {"NETWORK_ERROR","CLIENT_ERROR","SERVER_ERROR"} or s["last_checkpoint_tick"] is None or s["last_checkpoint_tick"]<60 or elapsed<1: raise DomainError("FAULT_NOT_REPORTABLE","장애 보고 조건을 확인할 수 없습니다.",409)
    try: last_tick=int(body.get("last_tick"))
    except (TypeError,ValueError): last_tick=-1
    if last_tick<s["last_checkpoint_tick"] or last_tick>36000: raise DomainError("FAULT_NOT_REFUNDABLE","장애 증거가 올바르지 않습니다.",409)
    s=_one(conn,"update dino_dev.game_session set status='FAULT_REPORTED',fault_reason=%s,fault_reported_at=clock_timestamp(),fault_review_status='PENDING',fault_review_version=1 where id=%s returning *",(reason,sid))
    _event(conn,"game_fault_reported",ctx,p["id"],"fault:"+sid,game_session_id=sid,dimensions={"reason":reason})
    return 202,_session(s)
def _refund_fault(conn,s,review_status,reviewed_by=None,reason=None):
    p=_one(conn,"select * from dino_dev.participant where id=%s for update",(s["participant_id"],))
    if s["ticket_refund_status"]=="REFUNDED":return s
    if s["ticket_kind"]=="INITIAL":
        conn.execute("update dino_dev.participant set initial_balance=least(1,initial_balance+1) where id=%s",(p["id"],)); after=min(1,p["initial_balance"]+1)
    else:
        conn.execute("update dino_dev.participant set invitation_refund_pending=invitation_refund_pending-1,invitation_balance=invitation_balance+1 where id=%s",(p["id"],)); after=p["invitation_balance"]+1
    conn.execute("insert into dino_dev.ticket_ledger(participant_id,ticket_kind,delta,source_type,source_id,balance_after,cooldown_until) values(%s,%s,1,'FAULT_REFUND',%s,%s,%s) on conflict do nothing",(p["id"],s["ticket_kind"],s["id"],after,p["cooldown_until"]))
    return _one(conn,"""update dino_dev.game_session set status='ABORTED',ticket_refund_status='REFUNDED',finished_at=clock_timestamp(),fault_review_status=%s,
      fault_review_version=fault_review_version+1,fault_reviewed_by=%s,fault_reviewed_at=clock_timestamp(),fault_review_reason=%s where id=%s returning *""",(review_status,reviewed_by,reason,s["id"]))
def _reconcile_expired(conn,participant_id):
    expired=_all(conn,"select * from dino_dev.game_session where participant_id=%s and status in ('RESERVED','ACTIVE') and expires_at<=clock_timestamp() order by reserved_at for update",(participant_id,))
    for session in expired:
        if session["status"]=="RESERVED":
            session=dict(session);session["fault_reason"]="SERVER_RESERVATION_EXPIRED"
            conn.execute("update dino_dev.game_session set fault_reason='SERVER_RESERVATION_EXPIRED',fault_reported_at=clock_timestamp(),fault_review_status='PENDING',fault_review_version=1 where id=%s",(session["id"],))
            _refund_fault(conn,session,"AUTO_APPROVED",reason="RESERVATION_NEVER_STARTED")
        else:
            conn.execute("""update dino_dev.game_session set status='FAULT_REPORTED',fault_reason='SERVER_TIMEOUT',fault_reported_at=clock_timestamp(),
              fault_review_status='PENDING',fault_review_version=1 where id=%s""",(session["id"],))
def _reconcile_fault(conn,s):
    if s["status"]!="FAULT_REPORTED" or s["fault_reason"]!="NETWORK_ERROR" or s["fault_reported_at"]>dt.datetime.now(UTC)-dt.timedelta(seconds=10): return s
    prior=_one(conn,"""select count(*)::int n from dino_dev.game_session where participant_id=%s and id<>%s and fault_review_status='AUTO_APPROVED' and fault_reason='NETWORK_ERROR'
      and fault_reviewed_at>=clock_timestamp()-interval '24 hours'""",(s["participant_id"],s["id"]))["n"]
    return _refund_fault(conn,s,"AUTO_APPROVED",reason="FIRST_NETWORK_FAULT_24H") if prior==0 else s
def get_session(conn,sid,ctx):
    p=_participant(conn,ctx);_reconcile_expired(conn,p["id"]);s=_owned_session(conn,sid,p["id"],True);s=_reconcile_fault(conn,s)
    response=_session(s)
    if s["status"] in ("FINISHED","REJECTED"): response["result"]=finish_response(conn,s)
    return 200,response

def leaderboard(conn,query,ctx):
    p=None
    if ctx.get("participant_token_hash"):
        try:p=_participant(conn,ctx)
        except DomainError: pass
    try:limit=max(1,min(100,int(query.get("limit",100))))
    except (TypeError,ValueError):limit=100
    rows=_all(conn,"""select b.participant_id,p.nickname,b.score,dense_rank() over(order by b.score desc)::int rank,
      count(*) over(partition by b.score)>1 tied from dino_dev.best_score b join dino_dev.participant p on p.id=b.participant_id
      where p.is_public and p.status='ACTIVE' order by b.score desc,b.achieved_at limit %s""",(limit,))
    mine=_one(conn,"select b.score,1+(select count(distinct score) from dino_dev.best_score x where x.score>b.score)::int rank from dino_dev.best_score b where participant_id=%s",(p["id"],)) if p else None
    return 200,{"leaderboard":[{"rank":r["rank"],"nickname":r["nickname"],"score":r["score"],"tied":r["tied"],"is_me":bool(p and r["participant_id"]==p["id"])} for r in rows],"me":{"rank":mine["rank"],"best_score":mine["score"]} if mine else None,"tie_policy":"UNDECIDED"}
def ranking_profile_get(conn,ctx):
    p=_participant(conn,ctx); row=_one(conn,"select status,submitted_at from dino_dev.ranking_contact where participant_id=%s",(p["id"],))
    return 200,{"required":bool(row and row["status"]=="REQUESTED"),"status":row["status"] if row else "NOT_REQUIRED","submitted_at":_iso(row["submitted_at"]) if row else None}
def ranking_profile_post(conn,body,ctx):
    p=_participant(conn,ctx,active=True); row=_one(conn,"select * from dino_dev.ranking_contact where participant_id=%s for update",(p["id"],))
    if not row: raise DomainError("TOP3_PROFILE_NOT_REQUIRED","현재 잠정 TOP3 정보 등록 대상이 아닙니다.",409)
    existing=_one(conn,"select id from dino_dev.claim where campaign_id=%s and participant_id=%s and claim_type='RANKING'",(p["campaign_id"],p["id"]))
    if row["status"]=="SUBMITTED" and existing:return 200,{"status":"SUBMITTED","submitted_at":_iso(row["submitted_at"]),"claim_id":existing["id"]}
    name,contact,school=(str(body.get(k) or "").strip() for k in ("name","contact","school"))
    if row["status"]=="SUBMITTED" and row["recipient_name"]:name,contact,school=row["recipient_name"],row["contact"],row["school"]
    if not name or not contact or not school or not (name.startswith("TEST_") and contact=="01000000000" and school.startswith("TEST_")): raise DomainError("SYNTHETIC_DATA_REQUIRED","개발 환경에서는 합성 정보만 입력할 수 있습니다.")
    claim_id=existing["id"] if existing else _id("claim")
    if not existing:conn.execute("insert into dino_dev.claim(id,campaign_id,participant_id,claim_type) values(%s,%s,%s,'RANKING')",(claim_id,p["campaign_id"],p["id"]))
    conn.execute("insert into dino_dev.claim_contact(claim_id,recipient_name,contact,school) values(%s,%s,%s,%s) on conflict(claim_id) do nothing",(claim_id,name[:80],contact[:32],school[:120]))
    conn.execute("""update dino_dev.claim set
      status=case when status='AWAITING_INFORMATION' then 'INFORMATION_RECEIVED' else status end,
      contact_submitted_at=coalesce(contact_submitted_at,clock_timestamp()),updated_at=clock_timestamp()
      where id=%s""",(claim_id,))
    row=_one(conn,"update dino_dev.ranking_contact set status='SUBMITTED',recipient_name=null,contact=null,school=null,submitted_at=coalesce(submitted_at,clock_timestamp()),updated_at=clock_timestamp() where participant_id=%s returning *",(p["id"],))
    return 200,{"status":"SUBMITTED","submitted_at":_iso(row["submitted_at"]),"claim_id":claim_id}

DRAW_SELECT="""select d.*,p.name prize_name,p.category prize_category,p.image_url,c.id claim_id from dino_dev.draw d join dino_dev.prize p on p.id=d.prize_id left join dino_dev.claim c on c.draw_id=d.id"""
def _draw_response(row):
    return {"draw_id":row["id"],"pouch_index":row["pouch_index"],"is_won":row["is_won"],"prize":{"id":row["prize_id"],"name":row["prize_name"],"category":row["prize_category"],"image_url":row["image_url"]},"revealed":row["revealed"],"scratch_completed":row["scratch_completed"],"claim_id":row["claim_id"]}
def draw_me(conn,ctx):
    p=_participant(conn,ctx); row=_one(conn,DRAW_SELECT+" where d.campaign_id=%s and d.participant_id=%s",(p["campaign_id"],p["id"]))
    if row:return 200,{"status":"DRAWN","draw":_draw_response(row)}
    eligible=_one(conn,"select id from dino_dev.game_session where participant_id=%s and status='FINISHED' order by finished_at limit 1",(p["id"],))
    return 200,{"status":"AVAILABLE" if eligible else "LOCKED","eligible_session_id":eligible["id"] if eligible else None,"draw":None}
def create_draw(conn,body,ctx):
    p=_participant(conn,ctx,True,True); old=_one(conn,DRAW_SELECT+" where d.campaign_id=%s and d.participant_id=%s for update of d",(p["campaign_id"],p["id"]))
    if old:return 200,_draw_response(old)
    try:pouch=int(body.get("pouch_index"))
    except (TypeError,ValueError):pouch=-1
    if pouch not in (0,1,2):raise DomainError("VALIDATION_ERROR","복주머니를 확인해 주세요.")
    session=_one(conn,"select * from dino_dev.game_session where participant_id=%s and status='FINISHED' order by finished_at limit 1 for update",(p["id"],))
    if not session:raise DomainError("DRAW_NOT_AVAILABLE","정상 게임 완료 후 열 수 있습니다.",409)
    campaign=_campaign(conn); prizes=_all(conn,"select * from dino_dev.prize where campaign_id=%s and is_active order by id",(campaign["id"],))
    roll=secrets.randbelow(10_000_000)/10_000_000; acc=0; prize=None
    for item in prizes:
        acc+=float(item["probability"])
        if roll<acc:prize=item;break
    prize=prize or next((x for x in prizes if x["category"]=="NO_PRIZE"),None)
    if not prize:raise DomainError("DRAW_CONFIG_INVALID","추첨 설정을 확인하고 있습니다.",503)
    inventory=None
    if prize["category"]!="NO_PRIZE":
        inventory=_one(conn,"select * from dino_dev.inventory_item where prize_id=%s and status='AVAILABLE' order by created_at,id for update skip locked limit 1",(prize["id"],))
        if not inventory:
            remaining=_one(conn,"select count(*)::int n from dino_dev.inventory_item where prize_id=%s and status='AVAILABLE'",(prize["id"],))["n"]
            if remaining:raise DomainError("INVENTORY_BUSY","경품 재고 확인이 지연되고 있습니다.",503,True)
            prize=next((x for x in prizes if x["category"]=="NO_PRIZE"),None)
            if not prize:raise DomainError("INVENTORY_EXHAUSTED","경품 재고가 소진되었습니다.",409)
    did=_id("draw"); audit=hashlib.sha256(f"{did}:{roll}:{campaign['probability_version']}".encode()).hexdigest()
    conn.execute("""insert into dino_dev.draw(id,campaign_id,participant_id,eligible_session_id,pouch_index,prize_id,inventory_item_id,is_won,probability_version,random_audit_hash)
      values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",(did,campaign["id"],p["id"],session["id"],pouch,prize["id"],inventory["id"] if inventory else None,prize["category"]!="NO_PRIZE",campaign["probability_version"],audit))
    claim_id=None
    if inventory:
        conn.execute("update dino_dev.inventory_item set status='RESERVED',reserved_by_draw_id=%s,reserved_at=clock_timestamp() where id=%s",(did,inventory["id"])); conn.execute("insert into dino_dev.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id) values(%s,'AVAILABLE','RESERVED','DRAW','draw',%s)",(inventory["id"],did))
        claim_id=_id("claim"); conn.execute("insert into dino_dev.claim(id,campaign_id,participant_id,draw_id,claim_type,prize_id,inventory_item_id) values(%s,%s,%s,%s,'DRAW',%s,%s)",(claim_id,campaign["id"],p["id"],did,prize["id"],inventory["id"]))
    row=_one(conn,DRAW_SELECT+" where d.id=%s",(did,)); _event(conn,"draw_fixed",ctx,p["id"],"draw:"+did,dimensions={"result_type":"won" if inventory else "no_prize"})
    return 201,_draw_response(row)
def scratch_complete(conn,did,ctx):
    p=_participant(conn,ctx); row=_one(conn,"update dino_dev.draw set revealed=true,scratch_completed=true where id=%s and participant_id=%s returning *",(did,p["id"]))
    if not row:raise DomainError("DRAW_NOT_FOUND","추첨 결과를 찾을 수 없습니다.",404)
    claim=_one(conn,"select id from dino_dev.claim where draw_id=%s",(did,)); return 200,{"draw_id":did,"scratch_completed":True,"claim_id":claim["id"] if claim else None}

def claims(conn,ctx):
    p=_participant(conn,ctx); rows=_all(conn,"""select c.id,c.claim_type,c.status,c.created_at,c.contact_submitted_at,p.name prize_name,p.category
      from dino_dev.claim c left join dino_dev.prize p on p.id=c.prize_id where c.participant_id=%s order by c.created_at desc""",(p["id"],))
    return 200,{"claims":[{"id":r["id"],"type":r["claim_type"],"claim_type":r["claim_type"],"prize_name":r["prize_name"],"category":r["category"],"status":r["status"],"created_at":_iso(r["created_at"]),"contact_submitted":bool(r["contact_submitted_at"])} for r in rows]}
def submit_claim(conn,cid,body,ctx):
    p=_participant(conn,ctx,active=True); claim=_one(conn,"select * from dino_dev.claim where id=%s and participant_id=%s for update",(cid,p["id"]))
    if not claim:raise DomainError("CLAIM_NOT_FOUND","수령 요청을 찾을 수 없습니다.",404)
    existing=_one(conn,"select claim_id from dino_dev.claim_contact where claim_id=%s",(cid,))
    if existing:return 200,{"id":cid,"status":claim["status"],"submitted_at":_iso(claim["contact_submitted_at"])}
    name,contact,school,address=(str(body.get(k) or "").strip() for k in ("name","contact","school","address"))
    if not name.startswith("TEST_") or contact!="01000000000" or (school and not school.startswith("TEST_")) or (address and not address.startswith("TEST_")): raise DomainError("SYNTHETIC_DATA_REQUIRED","개발 환경에서는 합성 정보만 입력할 수 있습니다.")
    conn.execute("insert into dino_dev.claim_contact(claim_id,recipient_name,contact,school,address) values(%s,%s,%s,%s,%s)",(cid,name[:80],contact[:32],school[:120] or None,address[:300] or None))
    claim=_one(conn,"""update dino_dev.claim set
      status=case when status='AWAITING_INFORMATION' then 'INFORMATION_RECEIVED' else status end,
      contact_submitted_at=coalesce(contact_submitted_at,clock_timestamp()),updated_at=clock_timestamp()
      where id=%s returning *""",(cid,))
    _event(conn,"claim_information_received",ctx,p["id"],"claim_submit:"+cid,dimensions={"claim_type":claim["claim_type"]})
    return 200,{"id":cid,"status":claim["status"],"submitted_at":_iso(claim["contact_submitted_at"])}

CLIENT_EVENTS={"entry_viewed","participant_ready","loading_ready","loading_checkpoint","screen_entered","screen_left","game_cta_clicked","game_start_approved","game_checkpoint","game_completed","game_fault_reported","game_recovered","ranking_viewed","top3_profile_started","top3_profile_submitted","invite_cta_viewed","share_attempted","invite_visit_interacted","invite_visit_qualified","invite_visit_rejected","draw_entered","pouch_selected","scratch_started","scratch_completed","draw_result_viewed","claim_form_started","claim_form_submitted","benefit_viewed","gemini_cta_viewed","gemini_cta_clicked","content_clicked","notion_redirect_requested","page_view"}
SCREENS={"loading","home","game","result","draw","claim","claims","invite","benefit","ranking","content","admin"}
DIMENSIONS={"previous_screen","source","link_kind","channel","campaign_code","content","position","action","status","reason","stage","bucket","result_type","prize_kind","share_method","share_id","checkpoint","is_new","is_synthetic","connected","observed","score","rank","game_version","draw_status","claim_type"}
SERVER_EVENT_NAMES={"game_start_approved","game_fault_reported","game_completed","invite_visit_qualified","scratch_completed","claim_form_submitted","top3_profile_submitted"}
BOOLEAN_DIMENSIONS={"is_new","is_synthetic","connected","observed"};INTEGER_DIMENSIONS={"score","rank","checkpoint"};OPAQUE_DIMENSIONS={"share_id"}
INTEGER_DIMENSION_RANGES={"score":(0,6000),"rank":(0,100000),"checkpoint":(0,36000)}
ENUM_DIMENSIONS={
  "previous_screen":SCREENS|{"unknown"},
  "source":{"home","gemini","phase1_load","unknown"},
  "link_kind":{"initial","retry_invite","prize_share","direct","unknown"},
  "content":{"study","photo","other","unknown"},
  "position":{"benefit_main","unknown"},
  "action":{"pouch_0","pouch_1","pouch_2"},
  "status":{"attempted","share_sheet_closed","cancelled","failed","copied","VERIFIED",
    "INVALID_CODE","SELF_INVITE","PENDING","COOLDOWN","BALANCE_FULL","REWARDED","ALREADY_REWARDED","NOT_QUALIFIED","REJECTED",
    "INVALID_NONCE","CAMPAIGN_UNAVAILABLE","RATE_LIMITED","RESERVED","ACTIVE","FAULT_REPORTED","FINISHED","ABORTED","EXPIRED"},
  "reason":{"navigation","pagehide","INVITE_CODE_NOT_FOUND","SELF_INVITE_NOT_ALLOWED","INVITER_COOLDOWN_AT_ISSUE",
    "INVITER_BALANCE_FULL_AT_ISSUE","QUALIFIED","PAIR_ALREADY_REWARDED","ACTIVE_TIME_OR_INTERACTION_REQUIRED",
    "INVITER_COOLDOWN","INVITER_BALANCE_FULL","INVALID_NONCE","NOT_ELIGIBLE","QUALIFICATION_REJECTED",
    "NETWORK_ERROR","CLIENT_ERROR","SERVER_ERROR","CAMPAIGN_UNAVAILABLE","RATE_LIMITED"},
  "stage":{"stage_1","stage_2","stage_3","stage_4","stage_5","stage_6"},
  "bucket":{"0-1s","1-2s","2-3s","3s+","unknown"},
  "result_type":{"won","no_prize","unknown"},
  "prize_kind":{"COUPON","DIGITAL","SHIPPING","NO_PRIZE","NONE"},
  "share_method":{"kakao","copy","native","unknown"},
  "claim_type":{"DRAW","RANKING"},
  "draw_status":{"LOCKED","AVAILABLE","DRAWN"},
}
CODE_DIMENSIONS={"channel","campaign_code"}
CODE_DIMENSION_VALUE=re.compile(r"(?:unknown|[A-Za-z][A-Za-z0-9_-]{0,31})")
GAME_VERSION_VALUE=re.compile(r"[0-9]+\.[0-9]+\.[0-9]+")
def events_batch(conn,body,ctx):
    p=None
    if ctx.get("participant_token_hash"):p=_participant(conn,ctx)
    events=body.get("events")
    if not isinstance(events,list) or not 1<=len(events)<=32:raise DomainError("VALIDATION_ERROR","이벤트 묶음을 확인해 주세요.")
    accepted=duplicates=rejected=0
    for event in events:
        if not isinstance(event,dict) or event.get("name") not in CLIENT_EVENTS or event.get("screen") not in SCREENS or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",str(event.get("event_id") or "")): rejected+=1;continue
        dims=event.get("dimensions") or {}
        if not isinstance(dims,dict) or set(dims)-DIMENSIONS:rejected+=1;continue
        valid_dims=True
        for key,value in dims.items():
            if key in BOOLEAN_DIMENSIONS:valid_dims=valid_dims and isinstance(value,bool)
            elif key in INTEGER_DIMENSIONS:
                low,high=INTEGER_DIMENSION_RANGES[key]
                valid_dims=valid_dims and isinstance(value,int) and not isinstance(value,bool) and low<=value<=high
            elif key in OPAQUE_DIMENSIONS:valid_dims=valid_dims and isinstance(value,str) and bool(re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",value))
            elif key in ENUM_DIMENSIONS:valid_dims=valid_dims and isinstance(value,str) and value in ENUM_DIMENSIONS[key]
            elif key in CODE_DIMENSIONS:valid_dims=valid_dims and isinstance(value,str) and bool(CODE_DIMENSION_VALUE.fullmatch(value))
            elif key=="game_version":valid_dims=valid_dims and isinstance(value,str) and bool(GAME_VERSION_VALUE.fullmatch(value))
            else:valid_dims=False
        if not valid_dims:rejected+=1;continue
        if dims.get("source")=="phase1_load" and ctx["environment"]=="production":rejected+=1;continue
        try:occurred=dt.datetime.fromisoformat(str(event.get("occurred_at") or "").replace("Z","+00:00")); active=int(event.get("active_ms")) if event.get("active_ms") is not None else None
        except (TypeError,ValueError):rejected+=1;continue
        now=dt.datetime.now(UTC)
        if occurred.tzinfo is None or occurred.astimezone(UTC)<now-dt.timedelta(hours=24) or occurred.astimezone(UTC)>now+dt.timedelta(minutes=5) or (active is not None and not 0<=active<=3600000):rejected+=1;continue
        observation_id=event.get("observation_id");game_session_id=event.get("game_session_id");screen_view_id=event.get("screen_view_id")
        if screen_view_id is not None and not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}",str(screen_view_id)):rejected+=1;continue
        if observation_id:
            observed=_one(conn,"select participant_id from dino_dev.observation where id=%s",(observation_id,))
            if not observed or (p and observed["participant_id"] not in (None,p["id"])) or (not p and observed["participant_id"] is not None):rejected+=1;continue
        if game_session_id:
            game=_one(conn,"select participant_id from dino_dev.game_session where id=%s",(game_session_id,))
            if not p or not game or game["participant_id"]!=p["id"]:rejected+=1;continue
        stored_name="client_"+event["name"] if event["name"] in SERVER_EVENT_NAMES else event["name"]
        result=conn.execute("""insert into dino_dev.analytics_event(event_id,campaign_id,participant_id,observation_id,event_name,screen,screen_view_id,visit_session_id,game_session_id,active_ms,dimensions,environment,deployment,event_version,synthetic,source,occurred_at)
          values(%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s::jsonb,%s,%s,%s,true,'client',%s) on conflict(event_id) do nothing""",(event["event_id"],ctx["campaign_id"],p["id"] if p else None,observation_id,stored_name,event["screen"],screen_view_id,str(event.get("visit_session_id") or "")[:128] or None,game_session_id,active,json.dumps(dims),ctx["environment"],ctx["deployment"],ctx["event_version"],occurred))
        if result.rowcount:accepted+=1
        else:duplicates+=1
    return 202,{"accepted":accepted,"duplicates":duplicates,"rejected":rejected}

def admin_session(conn,ctx):
    row=_admin(conn,ctx); return 200,{"authenticated":True,"admin":{"user_id":str(row["auth_user_id"]),"display_name":row["display_name"],"permissions":row["permissions"]}}
def admin_overview(conn,query,ctx):
    _admin(conn,ctx,"analytics:read")
    return metrics.build_overview(conn,query,ctx)
def admin_claims(conn,query,ctx):
    _admin(conn,ctx,"claims:read");conditions=[];params=[]
    for key,column in (("status","c.status"),("type","c.claim_type"),("assignee","c.assignee_user_id::text")):
        if query.get(key):conditions.append(column+"=%s");params.append(str(query[key]))
    where=(" where "+" and ".join(conditions)) if conditions else ""
    rows=_all(conn,"""select c.*,p.name prize_name,cc.recipient_name,cc.contact,cc.school,cc.address from dino_dev.claim c left join dino_dev.prize p on p.id=c.prize_id left join dino_dev.claim_contact cc on cc.claim_id=c.id"""+where+" order by c.updated_at desc limit 200",params)
    return 200,{"claims":[{**dict(r),"created_at":_iso(r["created_at"]),"updated_at":_iso(r["updated_at"]),"contact_submitted_at":_iso(r["contact_submitted_at"]),"contacted_at":_iso(r["contacted_at"]),"paid_at":_iso(r["paid_at"])} for r in rows]}
def admin_claim_patch(conn,cid,body,ctx):
    admin=_admin(conn,ctx,"claims:write"); claim=_one(conn,"select * from dino_dev.claim where id=%s for update",(cid,))
    if not claim:raise DomainError("CLAIM_NOT_FOUND","수령 요청을 찾을 수 없습니다.",404)
    try:expected=int(body.get("expected_version"))
    except (TypeError,ValueError):expected=-1
    if expected!=claim["version"]:raise DomainError("VERSION_CONFLICT","다른 관리자가 먼저 변경했습니다.",409)
    contact=_one(conn,"select claim_id from dino_dev.claim_contact where claim_id=%s",(cid,))
    if not claim["contact_submitted_at"] or not contact:raise DomainError("CLAIM_INFORMATION_REQUIRED","당첨자가 수령 정보를 입력한 뒤에 처리할 수 있습니다.",409)
    status=str(body.get("status") or claim["status"]); changing_status=status!=claim["status"]
    transitions={"AWAITING_INFORMATION":set(),"INFORMATION_RECEIVED":{"PENDING_REVIEW","ON_HOLD","INELIGIBLE","NO_RESPONSE"},"PENDING_REVIEW":{"CONTACTED","ON_HOLD","INELIGIBLE","NO_RESPONSE"},"CONTACTED":{"PAID","ON_HOLD","NO_RESPONSE"},"ON_HOLD":{"PENDING_REVIEW","INELIGIBLE","NO_RESPONSE"},"NO_RESPONSE":{"PENDING_REVIEW","INELIGIBLE"},"PAID":set(),"INELIGIBLE":set()}
    if changing_status and status not in transitions.get(claim["status"],set()):raise DomainError("INVALID_CLAIM_TRANSITION","현재 상태에서 해당 처리로 변경할 수 없습니다.",409)
    if changing_status and claim["claim_type"]=="RANKING" and status=="PAID":raise DomainError("FINAL_RANKING_UNDECIDED","최종 순위·동점 정책 확정 전에는 랭킹 선물을 지급 완료로 처리할 수 없습니다.",409)
    reason=str(body.get("reason") or "").strip()
    if changing_status and status in {"ON_HOLD","INELIGIBLE","NO_RESPONSE"} and len(reason)<3:raise DomainError("VALIDATION_ERROR","처리 사유를 입력해 주세요.")
    verification=str(body.get("verification_status") or claim["verification_status"]);reference=body.get("verification_reference",claim["verification_reference"])
    if verification not in {"NOT_REQUESTED","PENDING","VERIFIED","REJECTED"} or (reference is not None and not re.fullmatch(r"TEST_REF_[A-Za-z0-9_-]{1,100}",str(reference))):raise DomainError("VALIDATION_ERROR","합성 검증 상태와 참조를 확인해 주세요.")
    if verification!="NOT_REQUESTED" and reference is None:raise DomainError("VALIDATION_ERROR","검증 참조를 입력해 주세요.")
    assignee=body.get("assignee_user_id") or (str(claim["assignee_user_id"]) if claim["assignee_user_id"] else str(admin["auth_user_id"]))
    assigned=_one(conn,"select auth_user_id from dino_dev.admin_member where auth_user_id=%s and active and 'claims:write'=any(permissions)",(assignee,))
    if not assigned:raise DomainError("INVALID_ASSIGNEE","활성 수령 업무 담당자를 지정해 주세요.",409)
    if changing_status and status=="PAID" and claim["inventory_item_id"]:
        inventory=_one(conn,"select status from dino_dev.inventory_item where id=%s for update",(claim["inventory_item_id"],))
        if not inventory or inventory["status"]!="RESERVED":raise DomainError("INVENTORY_STATE_CONFLICT","경품 재고 상태가 일치하지 않습니다.",409)
    updated=_one(conn,"""update dino_dev.claim set status=%s,assignee_user_id=%s,hold_reason=%s,external_delivery=%s,verification_status=%s,verification_reference=%s,version=version+1,
      contacted_at=case when %s='CONTACTED' then coalesce(contacted_at,clock_timestamp()) else contacted_at end,
      paid_at=case when %s='PAID' then coalesce(paid_at,clock_timestamp()) else paid_at end,updated_at=clock_timestamp() where id=%s returning *""",(status,assignee,reason or claim["hold_reason"],body.get("external_delivery",claim["external_delivery"]),verification,reference,status,status,cid))
    if changing_status and status=="PAID" and claim["inventory_item_id"]:
        result=conn.execute("update dino_dev.inventory_item set status='PAID',paid_at=clock_timestamp() where id=%s and status='RESERVED'",(claim["inventory_item_id"],))
        if result.rowcount!=1:raise DomainError("INVENTORY_STATE_CONFLICT","경품 재고 상태가 일치하지 않습니다.",409)
    conn.execute("insert into dino_dev.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,reason,event_id) values(%s,'CLAIM_UPDATE','claim',%s,%s::jsonb,%s::jsonb,%s,%s)",(admin["auth_user_id"],cid,json.dumps({"status":claim["status"],"verification_status":claim["verification_status"],"version":claim["version"]}),json.dumps({"status":status,"verification_status":verification,"version":updated["version"]}),reason or None,str(body.get("event_id"))))
    return 200,{"id":cid,"status":status,"verification_status":verification,"version":updated["version"],"assignee_user_id":str(updated["assignee_user_id"])}
def admin_events(conn,query,ctx):
    _admin(conn,ctx,"analytics:read"); rows=_all(conn,"select event_id,event_name,screen,active_ms,dimensions,source,occurred_at,participant_id is not null connected from dino_dev.analytics_event order by received_at desc limit 200")
    return 200,{"events":[{**dict(r),"occurred_at":_iso(r["occurred_at"])} for r in rows]}
def admin_faults(conn,query,ctx):
    _admin(conn,ctx,"faults:read");status=str(query.get("status") or "PENDING")
    if status not in {"PENDING","AUTO_APPROVED","APPROVED","DENIED"}:raise DomainError("VALIDATION_ERROR","장애 심사 상태를 확인해 주세요.")
    rows=_all(conn,"""select id,participant_id,fault_reason,fault_reported_at,last_checkpoint_tick,fault_review_status,fault_review_version,
      ticket_kind,ticket_refund_status,fault_reviewed_by,fault_reviewed_at,fault_review_reason from dino_dev.game_session
      where fault_review_status=%s order by fault_reported_at desc limit 200""",(status,))
    return 200,{"faults":[{**dict(r),"fault_reported_at":_iso(r["fault_reported_at"]),"fault_reviewed_at":_iso(r["fault_reviewed_at"])} for r in rows]}
def admin_fault_patch(conn,sid,body,ctx):
    admin=_admin(conn,ctx,"faults:write");s=_one(conn,"select * from dino_dev.game_session where id=%s for update",(sid,))
    if not s:raise DomainError("SESSION_NOT_FOUND","게임 기록을 찾을 수 없습니다.",404)
    try:expected=int(body.get("expected_version"))
    except (TypeError,ValueError):expected=-1
    if s["fault_review_status"]!="PENDING" or s["fault_review_version"]!=expected:raise DomainError("VERSION_CONFLICT","장애 심사 상태가 변경되었습니다.",409)
    decision=str(body.get("decision") or "");reason=str(body.get("reason") or "").strip()
    if decision not in {"APPROVE","DENY"} or len(reason)<3:raise DomainError("VALIDATION_ERROR","심사 결과와 사유를 입력해 주세요.")
    before={"status":s["fault_review_status"],"version":s["fault_review_version"]}
    if decision=="APPROVE":s=_refund_fault(conn,s,"APPROVED",admin["auth_user_id"],reason)
    else:s=_one(conn,"""update dino_dev.game_session set status='ABORTED',ticket_refund_status='NOT_DUE',finished_at=clock_timestamp(),fault_review_status='DENIED',
      fault_review_version=fault_review_version+1,fault_reviewed_by=%s,fault_reviewed_at=clock_timestamp(),fault_review_reason=%s where id=%s returning *""",(admin["auth_user_id"],reason,sid))
    conn.execute("insert into dino_dev.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,reason,event_id) values(%s,'FAULT_REVIEW','game_session',%s,%s::jsonb,%s::jsonb,%s,%s)",(admin["auth_user_id"],sid,json.dumps(before),json.dumps({"status":s["fault_review_status"],"version":s["fault_review_version"]}),reason,str(body.get("event_id"))))
    return 200,{"session_id":sid,"status":s["status"],"refund":{"status":s["ticket_refund_status"],"ticket_kind":s["ticket_kind"]},"fault_review":{"status":s["fault_review_status"],"version":s["fault_review_version"]}}
def admin_campaign(conn,body,ctx):
    admin=_admin(conn,ctx,"campaign:write"); campaign=_campaign(conn,True); status=str(body.get("status") or "")
    if status not in {"ACTIVE","PAUSED","ENDED"} or int(body.get("expected_version") or -1)!=campaign["version"]:raise DomainError("VERSION_CONFLICT","행사 상태가 변경되었습니다.",409)
    row=_one(conn,"update dino_dev.campaign set status=%s,version=version+1,updated_at=clock_timestamp() where id=%s returning *",(status,campaign["id"]))
    conn.execute("insert into dino_dev.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,event_id) values(%s,'CAMPAIGN_STATUS','campaign',%s,%s::jsonb,%s::jsonb,%s)",(admin["auth_user_id"],campaign["id"],json.dumps({"status":campaign["status"]}),json.dumps({"status":status}),str(body.get("event_id"))))
    return 200,{"id":row["id"],"status":row["status"],"version":row["version"]}

def admin_participant_patch(conn,pid,body,ctx):
    admin=_admin(conn,ctx,"participants:write");participant=_one(conn,"select * from dino_dev.participant where id=%s for update",(pid,))
    if not participant:raise DomainError("PARTICIPANT_NOT_FOUND","참가자를 찾을 수 없습니다.",404)
    status=str(body.get("status") or participant["status"]);expected=str(body.get("expected_status") or "");revoke=body.get("revoke_session",False);reason=str(body.get("reason") or "").strip()
    if status not in {"ACTIVE","BLOCKED"} or expected!=participant["status"] or not isinstance(revoke,bool):raise DomainError("VERSION_CONFLICT","참가자 상태가 변경되었습니다.",409)
    if (status!=participant["status"] or revoke) and len(reason)<3:raise DomainError("VALIDATION_ERROR","제한 또는 세션 폐기 사유를 입력해 주세요.")
    updated=_one(conn,"""update dino_dev.participant set status=%s,token_expires_at=case when %s then least(token_expires_at,clock_timestamp()) else token_expires_at end,
      updated_at=clock_timestamp() where id=%s returning *""",(status,revoke,pid))
    conn.execute("insert into dino_dev.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,reason,event_id) values(%s,'PARTICIPANT_ACCESS','participant',%s,%s::jsonb,%s::jsonb,%s,%s)",(admin["auth_user_id"],pid,json.dumps({"status":participant["status"]}),json.dumps({"status":status,"session_revoked":revoke}),reason or None,str(body.get("event_id"))))
    return 200,{"participant_id":pid,"status":updated["status"],"session_revoked":revoke}

def admin_ranking_snapshots(conn,ctx):
    _admin(conn,ctx,"ranking:read");rows=_all(conn,"""select s.id,s.status,s.tie_policy,s.campaign_closes_at,s.captured_at,count(e.participant_id)::int entry_count
      from dino_dev.ranking_snapshot s left join dino_dev.ranking_snapshot_entry e on e.snapshot_id=s.id group by s.id order by s.captured_at desc limit 50""")
    return 200,{"snapshots":[{**dict(row),"campaign_closes_at":_iso(row["campaign_closes_at"]),"captured_at":_iso(row["captured_at"])} for row in rows]}

def admin_ranking_contacts(conn,ctx):
    _admin(conn,ctx,"claims:read");rows=_all(conn,"""select r.participant_id,r.status ranking_status,r.requested_at,r.submitted_at,c.id claim_id,c.status claim_status,
      c.verification_status,c.assignee_user_id,c.version,cc.recipient_name,cc.contact,cc.school
      from dino_dev.ranking_contact r left join dino_dev.claim c on c.participant_id=r.participant_id and c.claim_type='RANKING'
      left join dino_dev.claim_contact cc on cc.claim_id=c.id order by r.requested_at desc limit 200""")
    return 200,{"ranking_contacts":[{**dict(row),"requested_at":_iso(row["requested_at"]),"submitted_at":_iso(row["submitted_at"])} for row in rows]}

def create_admin_ranking_snapshot(conn,body,ctx):
    admin=_admin(conn,ctx,"ranking:write");campaign=_campaign(conn,True);sid=_id("rank_snapshot")
    snapshot=_one(conn,"""insert into dino_dev.ranking_snapshot(id,campaign_id,campaign_closes_at,created_by)
      values(%s,%s,%s,%s) returning *""",(sid,campaign["id"],campaign["closes_at"],admin["auth_user_id"]))
    conn.execute("""insert into dino_dev.ranking_snapshot_entry(snapshot_id,participant_id,score,rank,tied,contact_status)
      select %s,b.participant_id,b.score,dense_rank() over(order by b.score desc),count(*) over(partition by b.score)>1,coalesce(r.status,'NOT_REQUESTED')
      from dino_dev.best_score b join dino_dev.participant p on p.id=b.participant_id left join dino_dev.ranking_contact r on r.participant_id=b.participant_id
      where p.campaign_id=%s and p.status='ACTIVE'""",(sid,campaign["id"]))
    count=_one(conn,"select count(*)::int n from dino_dev.ranking_snapshot_entry where snapshot_id=%s",(sid,))["n"]
    conn.execute("insert into dino_dev.admin_audit(admin_user_id,action,target_type,target_id,after_value,event_id) values(%s,'RANKING_SNAPSHOT','ranking_snapshot',%s,%s::jsonb,%s)",(admin["auth_user_id"],sid,json.dumps({"status":"DRAFT","tie_policy":"UNDECIDED","entry_count":count}),str(body.get("event_id"))))
    return 201,{"id":sid,"status":snapshot["status"],"tie_policy":snapshot["tie_policy"],"campaign_closes_at":_iso(snapshot["campaign_closes_at"]),"captured_at":_iso(snapshot["captured_at"]),"entry_count":count,"final_awards_created":False}

def dispatch(conn,method,path,body,query,ctx):
    def call():
        if method=="POST" and path=="/api/observations":return create_observation(conn,body,ctx)
        if method=="POST" and path=="/api/participants/anonymous":return participant_init(conn,body,ctx)
        if method=="GET" and path=="/api/me":return get_me(conn,ctx)
        if method=="PATCH" and path=="/api/me/profile":return patch_profile(conn,body,ctx)
        if method=="GET" and path=="/api/referrals/me":return referral_me(conn,ctx)
        if method=="POST" and path=="/api/referrals/qualify":return qualify_referral(conn,body,ctx)
        if method=="POST" and path=="/api/referrals/cooldown-notice/ack":return cooldown_ack(conn,body,ctx)
        if method=="POST" and path=="/api/game-sessions":return create_session(conn,body,ctx)
        m=re.fullmatch(r"/api/game-sessions/([^/]+)/(start|checkpoint|finish|fault)",path)
        if method=="POST" and m:return {"start":lambda:start_session(conn,m.group(1),ctx),"checkpoint":lambda:checkpoint(conn,m.group(1),body,ctx),"finish":lambda:finish_session(conn,m.group(1),body,ctx),"fault":lambda:report_fault(conn,m.group(1),body,ctx)}[m.group(2)]()
        m=re.fullmatch(r"/api/game-sessions/([^/]+)",path)
        if method=="GET" and m:return get_session(conn,m.group(1),ctx)
        if method=="GET" and path=="/api/leaderboard":return leaderboard(conn,query,ctx)
        if method=="GET" and path=="/api/ranking/profile":return ranking_profile_get(conn,ctx)
        if method=="POST" and path=="/api/ranking/profile":return ranking_profile_post(conn,body,ctx)
        if method=="GET" and path=="/api/draws/me":return draw_me(conn,ctx)
        if method=="POST" and path=="/api/draws":return create_draw(conn,body,ctx)
        m=re.fullmatch(r"/api/draws/([^/]+)/scratch-complete",path)
        if method=="PATCH" and m:return scratch_complete(conn,m.group(1),ctx)
        if method=="GET" and path=="/api/claims":return claims(conn,ctx)
        m=re.fullmatch(r"/api/claims/([^/]+)/submit",path)
        if method=="POST" and m:return submit_claim(conn,m.group(1),body,ctx)
        if method=="POST" and path=="/api/events/batch":return events_batch(conn,body,ctx)
        if method=="GET" and path=="/api/admin/session":return admin_session(conn,ctx)
        if method=="GET" and path=="/api/admin/overview":return admin_overview(conn,query,ctx)
        if method=="GET" and path=="/api/admin/claims":return admin_claims(conn,query,ctx)
        m=re.fullmatch(r"/api/admin/claims/([^/]+)",path)
        if method=="PATCH" and m:return admin_claim_patch(conn,m.group(1),body,ctx)
        if method=="GET" and path=="/api/admin/analytics/events":return admin_events(conn,query,ctx)
        if method=="GET" and path=="/api/admin/game-faults":return admin_faults(conn,query,ctx)
        m=re.fullmatch(r"/api/admin/game-faults/([^/]+)",path)
        if method=="PATCH" and m:return admin_fault_patch(conn,m.group(1),body,ctx)
        if method=="GET" and path=="/api/admin/ranking-snapshots":return admin_ranking_snapshots(conn,ctx)
        if method=="POST" and path=="/api/admin/ranking-snapshots":return create_admin_ranking_snapshot(conn,body,ctx)
        if method=="GET" and path=="/api/admin/ranking-contacts":return admin_ranking_contacts(conn,ctx)
        m=re.fullmatch(r"/api/admin/participants/([^/]+)",path)
        if method=="PATCH" and m:return admin_participant_patch(conn,m.group(1),body,ctx)
        if method=="PATCH" and path=="/api/admin/campaign":return admin_campaign(conn,body,ctx)
        raise DomainError("NOT_FOUND","요청한 API를 찾을 수 없습니다.",404)
    mutation=method in {"POST","PATCH"} and path not in {"/api/participants/anonymous","/api/observations"}
    return _idempotent(conn,method,path,body,ctx,call) if mutation else call()
