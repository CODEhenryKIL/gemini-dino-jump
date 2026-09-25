"""Transactional business operations for the Phase 1 PostgreSQL backend.

The transport owns the connection and transaction. This module does not commit,
open connections, read environment variables, call external services, or log PII.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import re
import secrets
import uuid


class DomainError(Exception):
    def __init__(self, code: str, message: str, status: int = 400):
        super().__init__(message)
        self.code = code
        self.message = message
        self.status = status


CLIENT_EVENTS = {
    "page_view", "page_engagement", "draw_open", "claim_start",
    "invite_copy", "invite_share_open", "gemini_link_click", "client_error",
}
SCREENS = {"home", "game", "result", "draw", "prize", "claim", "invite", "benefit", "ranking", "admin"}
CHANNELS = {"direct", "referral", "qr", "social", "search", "email", "campus", "unknown"}
ERROR_CODES = {"network", "timeout", "api", "render", "storage", "unknown"}
MUTATING_CAMPAIGN_STATUSES = {"ACTIVE"}


def _id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex}"


def _unix(value):
    return int(value.timestamp()) if value else None


def _one(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()


def _all(conn, sql, params=()):
    return list(conn.execute(sql, params).fetchall())


def _campaign(conn, lock=None):
    suffix = {"share": " for share", "update": " for update"}.get(lock, "")
    row = _one(conn, "select * from dino.campaign order by updated_at desc limit 1" + suffix)
    if not row:
        raise DomainError("CAMPAIGN_NOT_CONFIGURED", "행사 설정이 준비되지 않았습니다.", 503)
    return row


def _campaign_by_id(conn, campaign_id, lock=None):
    suffix = {"share": " for share", "update": " for update"}.get(lock, "")
    row = _one(conn, "select * from dino.campaign where id=%s" + suffix, (campaign_id,))
    if not row:
        raise DomainError("CAMPAIGN_NOT_CONFIGURED", "행사 설정이 준비되지 않았습니다.", 503)
    return row


def _settings(campaign):
    value = campaign.get("settings") or {}
    bounds = {
        "initial_tickets": (0, 100), "referral_reward": (0, 100),
        "referral_daily_limit": (0, 100), "referral_total_limit": (0, 10000),
        "claim_ttl_seconds": (60, 2592000),
    }
    try:
        parsed = {key: int(value[key]) for key in bounds}
    except (KeyError, TypeError, ValueError):
        raise DomainError("CAMPAIGN_CONFIG_INVALID", "행사 설정을 확인하고 있습니다.", 503) from None
    if any(not low <= parsed[key] <= high for key, (low, high) in bounds.items()):
        raise DomainError("CAMPAIGN_CONFIG_INVALID", "행사 설정을 확인하고 있습니다.", 503)
    return parsed


def _safe_enum(value, allowed, fallback="unknown"):
    normalized = str(value or "").strip().lower()
    return normalized if normalized in allowed else fallback


def _ensure_campaign_mutable(campaign):
    if campaign["status"] not in MUTATING_CAMPAIGN_STATUSES:
        raise DomainError("CAMPAIGN_UNAVAILABLE", "현재 행사가 일시 중단되었습니다.", 409)


def _participant(conn, context, *, lock=False, active=False):
    token_hash = context.get("participant_token_hash")
    if not token_hash:
        raise DomainError("UNAUTHORIZED", "참가자 인증이 필요합니다.", 401)
    suffix = " for update" if lock else ""
    row = _one(conn, "select * from dino.participant where token_hash=%s" + suffix, (token_hash,))
    if not row:
        raise DomainError("UNAUTHORIZED", "참가자 인증이 유효하지 않습니다.", 401)
    if active and row["status"] != "ACTIVE":
        raise DomainError("PARTICIPANT_BLOCKED", "현재 참가할 수 없는 계정입니다.", 403)
    return row


def _admin(conn, context, *, claim_metadata=False):
    admin_id = context.get("admin_user_id")
    if not admin_id:
        raise DomainError("ADMIN_UNAUTHORIZED", "관리자 인증이 필요합니다.", 401)
    row = _one(conn, "select * from dino.admin_member where auth_user_id=%s and active=true", (admin_id,))
    if not row:
        raise DomainError("ADMIN_FORBIDDEN", "관리자 권한이 없습니다.", 403)
    if claim_metadata and not row["can_view_claim_metadata"]:
        raise DomainError("ADMIN_FORBIDDEN", "수령 요청 조회 권한이 없습니다.", 403)
    return row


def _ticket_balance(conn, participant_id):
    row = _one(conn, "select coalesce(sum(delta),0)::int as balance from dino.ticket_ledger where participant_id=%s", (participant_id,))
    return row["balance"]


def _emit(conn, event_name, context, participant_id=None, event_id=None, **fields):
    participant_channel = None
    if participant_id:
        participant = _one(conn, "select channel from dino.participant where id=%s", (participant_id,))
        participant_channel = participant["channel"] if participant else None
    conn.execute(
        """insert into dino.analytics_event
           (event_id,participant_id,event_name,screen,active_ms,channel,error_code,environment,synthetic,source)
           values (%s,%s,%s,%s,%s,%s,%s,%s,%s,'server') on conflict(event_id) do nothing""",
        (event_id or _id("evt"), participant_id, event_name, fields.get("screen"),
         fields.get("active_ms"), participant_channel, fields.get("error_code"),
         context["environment"], bool(context.get("synthetic"))),
    )


def _public_participant(row):
    return {"id": row["id"], "nickname": row["nickname"], "is_public": row["is_public"], "referral_code": row["referral_code"]}


def _attribute_referral(conn, invitee, code):
    if not code:
        return False
    inviter = _one(conn, "select id,status,campaign_id,environment from dino.participant where referral_code=%s for share", (code,))
    if (not inviter or inviter["id"] == invitee["id"] or inviter["status"] != "ACTIVE"
            or inviter["campaign_id"] != invitee["campaign_id"] or inviter["environment"] != invitee["environment"]):
        return False
    existing = _one(conn, "select id from dino.referral where invitee_id=%s", (invitee["id"],))
    if existing:
        return False
    conn.execute("insert into dino.referral(id,inviter_id,invitee_id) values (%s,%s,%s)", (_id("ref"), inviter["id"], invitee["id"]))
    return True


def _create_participant(conn, body, context):
    campaign = _campaign(conn, "share")
    _ensure_campaign_mutable(campaign)
    token_hash = context.get("new_token_hash")
    if not token_hash:
        raise DomainError("TOKEN_REQUIRED", "참가자 토큰을 만들 수 없습니다.", 500)
    environment = context["environment"]
    if environment == "production" and context.get("synthetic"):
        raise DomainError("ENVIRONMENT_MISMATCH", "환경 설정이 올바르지 않습니다.", 503)
    participant_id = _id("p")
    participant = _one(
        conn,
        """insert into dino.participant
           (id,campaign_id,token_hash,nickname,referral_code,environment,synthetic,channel)
           values (%s,%s,%s,%s,%s,%s,%s,%s) returning *""",
        (participant_id, campaign["id"], token_hash, f"공룡{secrets.randbelow(9000)+1000}",
         secrets.token_hex(6), environment, bool(context.get("synthetic")), _safe_enum(body.get("channel"), CHANNELS, "direct")),
    )
    settings = _settings(campaign)
    initial = settings["initial_tickets"]
    if initial > 0:
        conn.execute("insert into dino.ticket_ledger(participant_id,delta,source_type,source_id) values (%s,%s,'INITIAL','initial')", (participant_id, initial))
    applied = _attribute_referral(conn, participant, str(body.get("referral_code") or "")[:64])
    return 201, {"participant": _public_participant(participant), "referral_applied": applied}


def _campaign_response(conn):
    campaign = _campaign(conn)
    settings = _settings(campaign)
    prizes = _all(conn, "select id,name,category,image_url,probability,is_test from dino.prize where campaign_id=%s and is_active=true order by id", (campaign["id"],))
    return 200, {
        "id": campaign["id"], "title": campaign["title"], "status": campaign["status"],
        "game_version": campaign["game_version"], "benefit_url": campaign["benefit_url"],
        "settings": settings,
        "prizes": [{**dict(p), "probability": float(p["probability"])} for p in prizes],
        "is_test": campaign["is_test"], "real_prizes_enabled": campaign["real_prizes_enabled"],
    }


def _get_me(conn, context):
    p = _participant(conn, context)
    now = dt.datetime.now(dt.timezone.utc)
    conn.execute("update dino.game_session set status='EXPIRED' where participant_id=%s and status in ('RESERVED','ACTIVE') and expires_at<=%s", (p["id"], now))
    best = _one(conn, "select score from dino.best_score where participant_id=%s", (p["id"],))
    referral = _one(conn, "select count(*)::int invited_count,count(*) filter(where status in ('QUALIFIED','REWARDED'))::int qualified_count,count(*) filter(where status='REWARDED')::int rewarded_count from dino.referral where inviter_id=%s", (p["id"],))
    active = _one(conn, "select id,status,expires_at from dino.game_session where participant_id=%s and status in ('RESERVED','ACTIVE') order by reserved_at desc limit 1", (p["id"],))
    pending = _one(conn, """select s.id,s.score,d.id draw_id,d.scratch_completed from dino.game_session s left join dino.draw d on d.session_id=s.id where s.participant_id=%s and s.status='FINISHED' and (d.id is null or d.scratch_completed=false) order by s.finished_at desc limit 1""", (p["id"],))
    claims = _all(conn, "select id,status,expires_at from dino.claim where participant_id=%s and status in ('READY','SUBMITTED','DELIVERY_PENDING') order by created_at desc", (p["id"],))
    return 200, {
        "participant": _public_participant(p), "tickets": _ticket_balance(conn, p["id"]),
        "best_score": best["score"] if best else 0, "referral": dict(referral),
        "pending_draw": ({"id": pending["id"], "session_id": pending["id"], "score": pending["score"], "draw": pending["draw_id"]} if pending else None),
        "active_session": ({"id": active["id"], "status": active["status"], "expiry": _unix(active["expires_at"])} if active else None),
        "pending_claims": [{"id": c["id"], "status": c["status"], "expires_at": _unix(c["expires_at"])} for c in claims],
    }


def _patch_profile(conn, body, context):
    p = _participant(conn, context, lock=True, active=True)
    nickname = str(body.get("nickname") or "").strip()
    if not 1 <= len(nickname) <= 24:
        raise DomainError("INVALID_NICKNAME", "닉네임은 1~24자로 입력해 주세요.")
    is_public = body.get("is_public")
    if not isinstance(is_public, bool):
        raise DomainError("INVALID_PROFILE", "공개 여부를 확인해 주세요.")
    row = _one(conn, "update dino.participant set nickname=%s,is_public=%s,updated_at=now() where id=%s returning *", (nickname, is_public, p["id"]))
    return 200, {"participant": _public_participant(row)}


def _create_session(conn, body, context):
    p = _participant(conn, context, lock=True, active=True)
    campaign = _campaign_by_id(conn, p["campaign_id"], "share")
    _ensure_campaign_mutable(campaign)
    key = str(body.get("idempotency_key") or "")[:128]
    if not key:
        raise DomainError("IDEMPOTENCY_KEY_REQUIRED", "요청 식별자가 필요합니다.")
    existing = _one(conn, "select * from dino.game_session where participant_id=%s and idempotency_key=%s", (p["id"], key))
    if existing:
        return 200, _session_created(existing)
    now = dt.datetime.now(dt.timezone.utc)
    conn.execute("update dino.game_session set status='EXPIRED' where participant_id=%s and status in ('RESERVED','ACTIVE') and expires_at<=%s", (p["id"], now))
    live = _one(conn, "select * from dino.game_session where participant_id=%s and status in ('RESERVED','ACTIVE') order by reserved_at desc limit 1 for update", (p["id"],))
    if live:
        return 200, _session_created(live)
    row = _one(conn, """insert into dino.game_session(id,participant_id,campaign_id,idempotency_key,seed,version,expires_at,environment,synthetic)
        values(%s,%s,%s,%s,%s,%s,now()+interval '30 seconds',%s,%s) returning *""",
        (_id("gs"), p["id"], campaign["id"], key, secrets.randbelow(2147483646)+1, campaign["game_version"], context["environment"], bool(context.get("synthetic"))))
    return 201, _session_created(row)


def _session_created(row):
    return {"session_id": row["id"], "seed": row["seed"], "status": row["status"], "version": row["version"], "expires_at": _unix(row["expires_at"])}


def _owned_session(conn, session_id, participant_id, lock=False):
    suffix = " for update" if lock else ""
    row = _one(conn, "select * from dino.game_session where id=%s" + suffix, (session_id,))
    if not row:
        raise DomainError("SESSION_NOT_FOUND", "게임 기록을 찾을 수 없습니다.", 404)
    if row["participant_id"] != participant_id:
        raise DomainError("SESSION_NOT_FOUND", "게임 기록을 찾을 수 없습니다.", 404)
    return row


def _start_session(conn, session_id, context):
    p = _participant(conn, context, lock=True, active=True)
    s = _owned_session(conn, session_id, p["id"], lock=True)
    _ensure_campaign_mutable(_campaign_by_id(conn, s["campaign_id"], "share"))
    if s["status"] == "ACTIVE":
        return 200, {**_session_created(s), "tickets": _ticket_balance(conn, p["id"])}
    if s["status"] != "RESERVED" or s["expires_at"] <= dt.datetime.now(dt.timezone.utc):
        raise DomainError("SESSION_NOT_STARTABLE", "게임 시작 시간이 만료되었습니다.", 409)
    if _ticket_balance(conn, p["id"]) < 1:
        raise DomainError("NO_TICKETS", "게임권이 부족합니다.", 409)
    conn.execute("insert into dino.ticket_ledger(participant_id,delta,source_type,source_id) values(%s,-1,'PLAY_CONSUME',%s) on conflict(participant_id,source_type,source_id) do nothing", (p["id"], s["id"]))
    s = _one(conn, "update dino.game_session set status='ACTIVE',started_at=coalesce(started_at,now()),expires_at=now()+interval '24 hours' where id=%s returning *", (s["id"],))
    _emit(conn, "game_start", context, p["id"], f"game_start:{s['id']}")
    return 200, {**_session_created(s), "tickets": _ticket_balance(conn, p["id"])}


def _abort_session(conn, session_id, context):
    p = _participant(conn, context, active=True)
    s = _owned_session(conn, session_id, p["id"], lock=True)
    if s["status"] in ("RESERVED", "ACTIVE"):
        s = _one(conn, "update dino.game_session set status='ABORTED' where id=%s returning *", (s["id"],))
    return 200, {"session_id": s["id"], "status": s["status"]}


def _verification(context, body):
    value = context.get("verification")
    if isinstance(value, dict):
        return (bool(value.get("valid")), int(value.get("score", body.get("score", 0))),
                int(value.get("valid_ticks", body.get("valid_ticks", 0))), str(value.get("reason", "REJECTED"))[:200])
    if isinstance(value, (list, tuple)) and len(value) >= 4:
        return bool(value[0]), int(value[1]), int(value[2]), str(value[3])[:200]
    raise DomainError("VERIFICATION_REQUIRED", "게임 결과 검증이 필요합니다.", 500)


def _finish_response(conn, s):
    best = _one(conn, "select score from dino.best_score where participant_id=%s", (s["participant_id"],))
    rank = None
    if s["status"] == "FINISHED":
        rank = _one(conn, "select 1+count(*)::int as rank from dino.best_score where score>%s", (s["score"],))["rank"]
    return {"session_id": s["id"], "score": s["score"], "best_score": best["score"] if best else 0, "rank": rank, "verification_result": s["verification_result"], "eligible_for_draw": s["status"] == "FINISHED"}


def _qualify_referral(conn, invitee_id, campaign, context):
    ref = _one(conn, "select * from dino.referral where invitee_id=%s for update", (invitee_id,))
    if not ref or ref["status"] != "PENDING":
        return
    settings = _settings(campaign)
    daily_limit, total_limit, reward = (settings["referral_daily_limit"], settings["referral_total_limit"], settings["referral_reward"])
    # Serialize all rewards for one inviter before checking daily/total caps.
    _one(conn, "select id from dino.participant where id=%s for update", (ref["inviter_id"],))
    conn.execute("update dino.referral set status='QUALIFIED',qualified_at=now() where id=%s", (ref["id"],))
    _emit(conn, "referral_qualified", context, invitee_id, f"referral_qualified:{ref['id']}")
    counts = _one(conn, """select count(*) filter(where created_at >= date_trunc('day',now() at time zone 'Asia/Seoul') at time zone 'Asia/Seoul')::int daily,
        count(*)::int total from dino.ticket_ledger where participant_id=%s and source_type='REFERRAL'""", (ref["inviter_id"],))
    if reward > 0 and counts["daily"] < daily_limit and counts["total"] < total_limit:
        conn.execute("insert into dino.ticket_ledger(participant_id,delta,source_type,source_id) values(%s,%s,'REFERRAL',%s) on conflict(participant_id,source_type,source_id) do nothing", (ref["inviter_id"], reward, ref["id"]))
        conn.execute("update dino.referral set status='REWARDED',rewarded_at=now() where id=%s", (ref["id"],))
        _emit(conn, "referral_reward_granted", context, ref["inviter_id"], f"referral_reward:{ref['id']}")


def _finish_session(conn, session_id, body, context):
    # The session lock serializes finish retries. Avoid locking the invitee row
    # first so referral reward locking has a single, deadlock-safe order.
    p = _participant(conn, context, active=True)
    s = _owned_session(conn, session_id, p["id"], lock=True)
    campaign = _campaign_by_id(conn, s["campaign_id"], "share")
    _ensure_campaign_mutable(campaign)
    if s["status"] in ("FINISHED", "REJECTED"):
        return 200, _finish_response(conn, s)
    if s["status"] != "ACTIVE":
        raise DomainError("SESSION_NOT_ACTIVE", "시작된 게임만 종료할 수 있습니다.", 409)
    now = dt.datetime.now(dt.timezone.utc)
    if s["expires_at"] <= now:
        raise DomainError("SESSION_EXPIRED", "게임 세션이 만료되었습니다.", 409)
    if str(body.get("version")) != s["version"]:
        raise DomainError("GAME_VERSION_MISMATCH", "게임 버전이 일치하지 않습니다.", 409)
    verified, score, ticks, result = _verification(context, body)
    elapsed = (now - s["started_at"]).total_seconds() if s["started_at"] else 0
    if ticks < 0 or ticks > 36000 or elapsed + 2.0 < ticks / 60.0:
        verified, result = False, "IMPOSSIBLE_WALLCLOCK_DURATION"
    status = "FINISHED" if verified else "REJECTED"
    s = _one(conn, "update dino.game_session set status=%s,score=%s,valid_ticks=%s,verification_result=%s,finished_at=now() where id=%s returning *", (status, score, ticks, result, s["id"]))
    if verified:
        conn.execute("""insert into dino.best_score(participant_id,session_id,score,achieved_at) values(%s,%s,%s,now())
            on conflict(participant_id) do update set session_id=excluded.session_id,score=excluded.score,achieved_at=excluded.achieved_at
            where excluded.score>dino.best_score.score""", (p["id"], s["id"], score))
        _qualify_referral(conn, p["id"], campaign, context)
        _emit(conn, "game_finish_verified", context, p["id"], f"game_finish:{s['id']}")
    else:
        _emit(conn, "game_finish_rejected", context, p["id"], f"game_finish:{s['id']}", error_code=result[:64])
    return 200, _finish_response(conn, s)


def _draw_response(row):
    return {"draw_id": row["id"], "session_id": row["session_id"], "pouch_index": row["pouch_index"], "is_won": row["is_won"],
            "prize": {"id": row["prize_id"], "name": row["prize_name"], "category": row["prize_category"], "image_url": row["image_url"]},
            "claim_id": row.get("claim_id"), "scratch_completed": row["scratch_completed"], "is_test": row["is_test"]}


DRAW_SELECT = """select d.*,p.name prize_name,p.category prize_category,p.image_url,c.id claim_id
 from dino.draw d join dino.prize p on p.id=d.prize_id left join dino.claim c on c.draw_id=d.id"""


def _draw(conn, body, context):
    p = _participant(conn, context, lock=True, active=True)
    session_id = str(body.get("session_id") or "")
    s = _owned_session(conn, session_id, p["id"], lock=True)
    campaign = _campaign_by_id(conn, s["campaign_id"], "share")
    _ensure_campaign_mutable(campaign)
    if context["environment"] in ("local", "test", "preview") and not campaign["is_test"]:
        raise DomainError("TEST_CAMPAIGN_REQUIRED", "개발 환경의 테스트 행사를 확인해 주세요.", 503)
    existing = _one(conn, DRAW_SELECT + " where d.session_id=%s", (session_id,))
    if existing:
        return 200, _draw_response(existing)
    if s["status"] != "FINISHED" or not str(s["verification_result"] or "").startswith(("VERIFIED", "EARLY_TERMINATION_VERIFIED")):
        raise DomainError("DRAW_NOT_ELIGIBLE", "검증된 게임만 추첨할 수 있습니다.", 409)
    pouch = body.get("pouch_index")
    if not isinstance(pouch, int) or pouch < 0 or pouch > 2:
        raise DomainError("INVALID_POUCH", "주머니를 다시 선택해 주세요.")
    prizes = _all(conn, "select * from dino.prize where campaign_id=%s and is_active=true and is_test=%s order by id", (campaign["id"], campaign["is_test"]))
    fallback = next((x for x in prizes if x["category"] == "NO_PRIZE"), None)
    if not fallback:
        raise DomainError("DRAW_NOT_CONFIGURED", "추첨 설정이 준비되지 않았습니다.", 503)
    roll = secrets.SystemRandom().random()
    selected, upto = fallback, 0.0
    for prize in prizes:
        upto += float(prize["probability"])
        if roll < upto:
            selected = prize
            break
    inventory = None
    if selected["category"] != "NO_PRIZE":
        inventory = _one(conn, "select * from dino.inventory_item where prize_id=%s and status='AVAILABLE' order by created_at,id for update skip locked limit 1", (selected["id"],))
        if not inventory:
            selected = fallback
    draw_id = _id("draw")
    is_won = selected["category"] != "NO_PRIZE" and inventory is not None
    conn.execute("insert into dino.draw(id,session_id,participant_id,pouch_index,prize_id,inventory_item_id,is_won,is_test) values(%s,%s,%s,%s,%s,%s,%s,%s)",
                 (draw_id, s["id"], p["id"], pouch, selected["id"], inventory["id"] if inventory else None, is_won, selected["is_test"]))
    claim_id = None
    if inventory:
        conn.execute("update dino.inventory_item set status='RESERVED',reserved_by_draw_id=%s,reserved_at=now() where id=%s and status='AVAILABLE'", (draw_id, inventory["id"]))
        conn.execute("insert into dino.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id) values(%s,'AVAILABLE','RESERVED','DRAW_WIN','draw',%s)", (inventory["id"], draw_id))
        claim_id = _id("claim")
        ttl = _settings(campaign)["claim_ttl_seconds"]
        conn.execute("insert into dino.claim(id,draw_id,participant_id,prize_id,inventory_item_id,expires_at,is_test) values(%s,%s,%s,%s,%s,now()+(%s * interval '1 second'),%s)",
                     (claim_id, draw_id, p["id"], selected["id"], inventory["id"], ttl, selected["is_test"]))
    _emit(conn, "draw_result", context, p["id"], f"draw_result:{draw_id}")
    row = _one(conn, DRAW_SELECT + " where d.id=%s", (draw_id,))
    return 201, _draw_response(row)


def _scratch(conn, draw_id, context):
    p = _participant(conn, context, active=True)
    locked = _one(conn, "select id,participant_id from dino.draw where id=%s for update", (draw_id,))
    if not locked or locked["participant_id"] != p["id"]:
        raise DomainError("DRAW_NOT_FOUND", "추첨 결과를 찾을 수 없습니다.", 404)
    campaign = _one(conn, "select c.* from dino.draw d join dino.game_session s on s.id=d.session_id join dino.campaign c on c.id=s.campaign_id where d.id=%s for share of c", (draw_id,))
    _ensure_campaign_mutable(campaign)
    row = _one(conn, DRAW_SELECT + " where d.id=%s", (draw_id,))
    if not row["scratch_completed"]:
        conn.execute("update dino.draw set scratch_completed=true where id=%s", (draw_id,))
        row = _one(conn, DRAW_SELECT + " where d.id=%s", (draw_id,))
    return 200, _draw_response(row)


def _get_session(conn, session_id, context):
    p = _participant(conn, context)
    s = _owned_session(conn, session_id, p["id"])
    result = None if s["score"] is None else _finish_response(conn, s)
    draw = _one(conn, DRAW_SELECT + " where d.session_id=%s", (s["id"],))
    return 200, {**_session_created(s), "result": result, "draw": _draw_response(draw) if draw else None}


def _claims(conn, context):
    p = _participant(conn, context)
    _expire_claims(conn, p["id"])
    rows = _all(conn, """select c.*,p.name prize_name,p.category prize_category,
        (select response->>'coupon_code' from dino.delivery_attempt da where da.claim_id=c.id and da.status='SUCCEEDED' order by created_at desc limit 1) coupon_code
        from dino.claim c join dino.prize p on p.id=c.prize_id where c.participant_id=%s order by c.created_at desc""", (p["id"],))
    return 200, {"claims": [{"id": r["id"], "draw_id": r["draw_id"], "prize_id": r["prize_id"], "prize_name": r["prize_name"], "prize_category": r["prize_category"], "status": r["status"], "expires_at": _unix(r["expires_at"]), "created_at": _unix(r["created_at"]), "is_test": r["is_test"], **({"coupon_code": r["coupon_code"]} if r["coupon_code"] else {})} for r in rows]}


def _expire_claims(conn, participant_id=None):
    params = []
    owner_clause = ""
    if participant_id:
        owner_clause, params = " and participant_id=%s", [participant_id]
    rows = _all(conn, "select id,inventory_item_id from dino.claim where status='READY' and expires_at<=now()" + owner_clause + " order by expires_at for update skip locked limit 100", params)
    for row in rows:
        inventory = _one(conn, "select status from dino.inventory_item where id=%s for update", (row["inventory_item_id"],))
        conn.execute("update dino.claim set status='EXPIRED' where id=%s and status='READY'", (row["id"],))
        if inventory and inventory["status"] == "RESERVED":
            conn.execute("update dino.inventory_item set status='EXPIRED' where id=%s", (row["inventory_item_id"],))
            conn.execute("insert into dino.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id) values(%s,'RESERVED','EXPIRED','CLAIM_TTL','claim',%s)", (row["inventory_item_id"], row["id"]))


def _claim_response(conn, claim):
    delivery = _one(conn, "select response from dino.delivery_attempt where claim_id=%s and status='SUCCEEDED' order by created_at desc limit 1", (claim["id"],))
    result = {"claim_id": claim["id"], "status": claim["status"], "is_test": claim["is_test"]}
    if delivery and delivery["response"].get("coupon_code"):
        result["coupon_code"] = delivery["response"]["coupon_code"]
    return result


def _submit_claim(conn, claim_id, body, context):
    p = _participant(conn, context, lock=True, active=True)
    claim = _one(conn, """select c.*,p.category,s.campaign_id from dino.claim c
        join dino.prize p on p.id=c.prize_id join dino.draw d on d.id=c.draw_id
        join dino.game_session s on s.id=d.session_id where c.id=%s for update of c""", (claim_id,))
    if not claim or claim["participant_id"] != p["id"]:
        raise DomainError("CLAIM_NOT_FOUND", "수령 요청을 찾을 수 없습니다.", 404)
    _ensure_campaign_mutable(_campaign_by_id(conn, claim["campaign_id"], "share"))
    if claim["status"] in ("SUBMITTED", "DELIVERY_PENDING", "TEST_ISSUED", "ISSUED"):
        return 200, _claim_response(conn, claim)
    if claim["status"] == "EXPIRED":
        return 409, {"error": "CLAIM_EXPIRED", "message": "수령 기한이 만료되었습니다.", "request_id": context["request_id"]}
    if claim["status"] != "READY":
        raise DomainError("CLAIM_NOT_READY", "수령할 수 없는 상태입니다.", 409)
    if claim["expires_at"] <= dt.datetime.now(dt.timezone.utc):
        inventory = _one(conn, "select status from dino.inventory_item where id=%s for update", (claim["inventory_item_id"],))
        conn.execute("update dino.claim set status='EXPIRED' where id=%s", (claim_id,))
        if inventory and inventory["status"] == "RESERVED":
            conn.execute("update dino.inventory_item set status='EXPIRED' where id=%s", (claim["inventory_item_id"],))
            conn.execute("insert into dino.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id) values(%s,'RESERVED','EXPIRED','CLAIM_TTL','claim',%s)", (claim["inventory_item_id"], claim_id))
        return 409, {"error": "CLAIM_EXPIRED", "message": "수령 기한이 만료되었습니다.", "request_id": context["request_id"]}
    if body.get("consent") is not True:
        raise DomainError("CONSENT_REQUIRED", "개인정보 수집 동의가 필요합니다.")
    name, phone, address = (str(body.get("recipient_name") or "").strip(), str(body.get("contact_phone") or "").strip(), str(body.get("shipping_address") or "").strip())
    if not name or not phone or (claim["category"] == "SHIPPING" and not address):
        raise DomainError("RECIPIENT_REQUIRED", "수령 정보를 모두 입력해 주세요.")
    nonprod = context["environment"] in ("local", "test", "preview")
    if nonprod and (not name.startswith("TEST_") or phone != "01000000000" or (claim["category"] == "SHIPPING" and not address.startswith("TEST_"))):
        raise DomainError("SYNTHETIC_DATA_REQUIRED", "개발 환경에서는 테스트 수령 정보만 사용할 수 있습니다.")
    if context["environment"] == "production":
        raise DomainError("REAL_DELIVERY_DISABLED", "실제 경품 지급은 아직 활성화되지 않았습니다.", 409)
    conn.execute("insert into dino.claim_recipient(claim_id,recipient_name,contact_phone,shipping_address,consented_at,synthetic) values(%s,%s,%s,%s,now(),true)", (claim_id, name[:80], phone[:32], address[:300] or None))
    coupon = f"TEST-{hashlib.sha256(claim_id.encode('utf-8')).hexdigest()[:12].upper()}" if claim["category"] in ("COUPON", "DIGITAL") else None
    response = {"provider": "synthetic", "delivered": True, **({"coupon_code": coupon} if coupon else {})}
    conn.execute("insert into dino.delivery_attempt(id,claim_id,provider,idempotency_key,status,response) values(%s,%s,'synthetic','claim-submit','SUCCEEDED',%s::jsonb)", (_id("delivery"), claim_id, json.dumps(response)))
    claim = _one(conn, "update dino.claim set status='TEST_ISSUED',submitted_at=now() where id=%s returning *", (claim_id,))
    conn.execute("update dino.inventory_item set status='TEST_ISSUED',issued_at=now() where id=%s", (claim["inventory_item_id"],))
    conn.execute("insert into dino.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id) values(%s,'RESERVED','TEST_ISSUED','SYNTHETIC_DELIVERY','claim',%s)", (claim["inventory_item_id"], claim_id))
    _emit(conn, "claim_submit", context, p["id"], f"claim_submit:{claim_id}")
    return 200, _claim_response(conn, claim)


def _referrals(conn, context):
    p = _participant(conn, context)
    campaign = _campaign_by_id(conn, p["campaign_id"])
    row = _one(conn, """select count(*)::int invited_count,count(*) filter(where status in ('QUALIFIED','REWARDED'))::int qualified_count,
        count(*) filter(where status='REWARDED')::int rewarded_count from dino.referral where inviter_id=%s""", (p["id"],))
    earned = _one(conn, "select coalesce(sum(delta),0)::int earned from dino.ticket_ledger where participant_id=%s and source_type='REFERRAL'", (p["id"],))["earned"]
    settings = _settings(campaign)
    return 200, {"invite_url": f"{context['base_url'].rstrip('/')}/invite/{p['referral_code']}", "referral_code": p["referral_code"], "summary": {**dict(row), "earned_tickets": earned}, "policy": {k: settings.get(k) for k in ("referral_reward", "referral_daily_limit", "referral_total_limit")}}


def _attribute(conn, body, context):
    p = _participant(conn, context, active=True)
    _ensure_campaign_mutable(_campaign_by_id(conn, p["campaign_id"], "share"))
    return 200, {"applied": _attribute_referral(conn, p, str(body.get("referral_code") or "")[:64])}


def _benefit(conn, context):
    p = _participant(conn, context, active=True)
    _ensure_campaign_mutable(_campaign_by_id(conn, p["campaign_id"], "share"))
    conn.execute("insert into dino.benefit_verification(participant_id,status) values(%s,'PENDING') on conflict(participant_id) do update set status='PENDING',updated_at=now()", (p["id"],))
    return 200, {"status": "PENDING", "verified": False}


def _leaderboard(conn, query, context):
    p = None
    if context.get("participant_token_hash"):
        p = _participant(conn, context)
    try: limit = max(1, min(100, int(query.get("limit", 50))))
    except (TypeError, ValueError): limit = 50
    rows = _all(conn, """select b.participant_id,p.nickname,b.score,b.achieved_at,
        row_number() over(order by b.score desc,b.achieved_at,b.participant_id)::int rank
        from dino.best_score b join dino.participant p on p.id=b.participant_id where p.is_public=true and p.status='ACTIVE'
        order by b.score desc,b.achieved_at,b.participant_id limit %s""", (limit,))
    mine = _one(conn, """select b.score,(select 1+count(*) from dino.best_score x where x.score>b.score)::int rank from dino.best_score b where participant_id=%s""", (p["id"],)) if p else None
    return 200, {"leaderboard": [{"rank": r["rank"], "nickname": r["nickname"], "score": r["score"], "is_me": bool(p and r["participant_id"] == p["id"])} for r in rows], "my_rank": mine["rank"] if mine else None, "my_score": mine["score"] if mine else None}


def _events(conn, body, context):
    p = _participant(conn, context, active=True)
    events = body.get("events")
    if not isinstance(events, list) or len(events) > 20:
        raise DomainError("INVALID_EVENTS", "이벤트 형식이 올바르지 않습니다.")
    accepted = 0
    for e in events:
        if not isinstance(e, dict) or e.get("event_name") not in CLIENT_EVENTS or not re.fullmatch(r"[A-Za-z0-9:_-]{8,128}", str(e.get("event_id") or "")):
            continue
        result = conn.execute("""insert into dino.analytics_event(event_id,participant_id,event_name,screen,active_ms,channel,error_code,environment,synthetic,source)
            values(%s,%s,%s,%s,%s,%s,%s,%s,%s,'client') on conflict(event_id) do nothing""",
            (e["event_id"], p["id"], e["event_name"], _safe_enum(e.get("screen"), SCREENS),
             min(3600000, max(0, int(e.get("active_ms") or 0))) if e.get("active_ms") is not None else None,
             p["channel"], _safe_enum(e.get("error_code"), ERROR_CODES) if e.get("error_code") else None,
             context["environment"], bool(context.get("synthetic"))))
        accepted += result.rowcount
    return 202, {"accepted": accepted}


def _admin_status(conn, body, context):
    _admin(conn, context)
    status, reason = str(body.get("status") or ""), str(body.get("reason") or "").strip()
    if status not in ("ACTIVE", "MAINTENANCE", "PAUSED", "ENDED") or not 3 <= len(reason) <= 500:
        raise DomainError("INVALID_ADMIN_CHANGE", "상태와 변경 사유를 확인해 주세요.")
    campaign = _campaign(conn, lock="update")
    before = {"status": campaign["status"]}
    row = _one(conn, "update dino.campaign set status=%s,updated_at=now() where id=%s returning *", (status, campaign["id"]))
    conn.execute("insert into dino.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,reason) values(%s,'CAMPAIGN_STATUS','campaign',%s,%s::jsonb,%s::jsonb,%s)", (context["admin_user_id"], campaign["id"], json.dumps(before), json.dumps({"status": status}), reason))
    return 200, {"id": row["id"], "status": row["status"]}


def _admin_tickets(conn, body, context):
    _admin(conn, context)
    participant_id, reason, key = str(body.get("participant_id") or ""), str(body.get("reason") or "").strip(), str(body.get("idempotency_key") or "")[:128]
    try: delta = int(body.get("delta"))
    except (TypeError, ValueError): raise DomainError("INVALID_DELTA", "게임권 변경값을 확인해 주세요.")
    if delta == 0 or abs(delta) > 1000 or not key or not 3 <= len(reason) <= 500:
        raise DomainError("INVALID_ADMIN_CHANGE", "변경값과 사유를 확인해 주세요.")
    request_hash = hashlib.sha256(json.dumps({"actor": str(context["admin_user_id"]), "participant_id": participant_id, "delta": delta, "reason": reason}, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    target = _one(conn, "select id from dino.participant where id=%s for update", (participant_id,))
    if not target:
        raise DomainError("PARTICIPANT_NOT_FOUND", "참가자를 찾을 수 없습니다.", 404)
    existing = _one(conn, "select delta,request_hash from dino.ticket_ledger where participant_id=%s and idempotency_key=%s", (participant_id, key))
    if existing:
        if existing["request_hash"] != request_hash:
            raise DomainError("IDEMPOTENCY_CONFLICT", "같은 요청 식별자에 다른 변경값을 사용할 수 없습니다.", 409)
        return 200, {"participant_id": participant_id, "tickets": _ticket_balance(conn, participant_id)}
    before = _ticket_balance(conn, participant_id)
    if before + delta < 0:
        raise DomainError("NEGATIVE_TICKET_BALANCE", "게임권 잔액은 음수가 될 수 없습니다.", 409)
    conn.execute("insert into dino.ticket_ledger(participant_id,delta,source_type,source_id,idempotency_key,request_hash) values(%s,%s,'ADMIN_ADJUST',%s,%s,%s)", (participant_id, delta, _id("admin"), key, request_hash))
    conn.execute("insert into dino.admin_audit(admin_user_id,action,target_type,target_id,before_value,after_value,reason,idempotency_key) values(%s,'TICKET_ADJUST','participant',%s,%s::jsonb,%s::jsonb,%s,%s)", (context["admin_user_id"], participant_id, json.dumps({"tickets": before}), json.dumps({"tickets": before + delta, "delta": delta}), reason, key))
    return 200, {"participant_id": participant_id, "tickets": before + delta}


def _admin_claims(conn, context):
    _admin(conn, context)
    _expire_claims(conn)
    rows = _all(conn, "select id,draw_id,participant_id,prize_id,status,expires_at,created_at,is_test from dino.claim order by created_at desc limit 500")
    return 200, {"claims": [{**dict(r), "expires_at": _unix(r["expires_at"]), "created_at": _unix(r["created_at"])} for r in rows]}


def _admin_suspicious(conn, context):
    _admin(conn, context)
    rows = _all(conn, "select id,score,verification_result,finished_at created_at from dino.game_session where status='REJECTED' order by finished_at desc limit 200")
    return 200, {"sessions": [{**dict(r), "created_at": _unix(r["created_at"])} for r in rows]}


def _admin_overview(conn, query, context):
    _admin(conn, context)
    environment = str(query.get("environment") or context["environment"])
    if environment not in ("local", "test", "preview", "production"):
        raise DomainError("INVALID_ENVIRONMENT", "조회 환경을 확인해 주세요.")
    try:
        start = dt.date.fromisoformat(str(query.get("from"))) if query.get("from") else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date() - dt.timedelta(days=6)
        end = dt.date.fromisoformat(str(query.get("to"))) if query.get("to") else dt.datetime.now(dt.timezone(dt.timedelta(hours=9))).date()
    except ValueError:
        raise DomainError("INVALID_PERIOD", "조회 기간을 확인해 주세요.")
    if end < start or (end - start).days > 366:
        raise DomainError("INVALID_PERIOD", "조회 기간을 확인해 주세요.")
    start_utc = dt.datetime.combine(start, dt.time.min, tzinfo=dt.timezone(dt.timedelta(hours=9))).astimezone(dt.timezone.utc)
    end_utc = dt.datetime.combine(end + dt.timedelta(days=1), dt.time.min, tzinfo=dt.timezone(dt.timedelta(hours=9))).astimezone(dt.timezone.utc)
    include_synthetic = str(query.get("include_synthetic") or "").lower() == "true" and environment != "production"
    synthetic_clause = "" if include_synthetic else " and synthetic=false"
    events = _all(conn, f"select event_name,count(*)::int total from dino.analytics_event where environment=%s and occurred_at>=%s and occurred_at<%s{synthetic_clause} group by event_name", (environment, start_utc, end_utc))
    by_name = {r["event_name"]: r["total"] for r in events}
    screens = _all(conn, f"""with scoped as (
          select * from dino.analytics_event where environment=%s and occurred_at>=%s and occurred_at<%s{synthetic_clause} and screen is not null
        ), last_views as (
          select participant_id,screen,row_number() over(partition by participant_id order by occurred_at desc,id desc) n
          from scoped where event_name='page_view'
        )
        select s.screen,count(*) filter(where s.event_name='page_view')::int views,
          coalesce(sum(s.active_ms),0)::bigint active_ms,
          (select count(*)::int from last_views l where l.n=1 and l.screen=s.screen) estimated_exits
        from scoped s group by s.screen order by views desc""", (environment, start_utc, end_utc))
    channels = _all(conn, f"""select coalesce(channel,'direct') channel,
          count(*) filter(where event_name='page_view')::int page_views,
          count(distinct participant_id) filter(where event_name='page_view')::int participants,
          count(*) filter(where event_name='game_start')::int game_starts,
          count(*) filter(where event_name='gemini_link_click')::int gemini_clicks
        from dino.analytics_event where environment=%s and occurred_at>=%s and occurred_at<%s{synthetic_clause}
        group by channel order by participants desc,channel""", (environment, start_utc, end_utc))
    inventory = _all(conn, "select p.id prize_id,p.name prize_name,i.status,count(*)::int count from dino.prize p left join dino.inventory_item i on i.prize_id=p.id group by p.id,p.name,i.status order by p.id,i.status")
    refs = _one(conn, """select count(*)::int attributed,count(*) filter(where r.status in ('QUALIFIED','REWARDED'))::int qualified,
        count(*) filter(where r.status='REWARDED')::int rewarded from dino.referral r join dino.participant p on p.id=r.invitee_id
        where p.environment=%s and r.created_at>=%s and r.created_at<%s""" + ("" if include_synthetic else " and p.synthetic=false"), (environment, start_utc, end_utc))
    totals = {"participants": _one(conn, "select count(*)::int n from dino.participant where environment=%s and created_at>=%s and created_at<%s" + ("" if include_synthetic else " and synthetic=false"), (environment, start_utc, end_utc))["n"], "page_views": by_name.get("page_view", 0), "active_ms": sum(r["active_ms"] for r in screens)}
    wins = _one(conn, """select count(*)::int n from dino.draw d join dino.participant p on p.id=d.participant_id
        where p.environment=%s and d.is_won=true and d.created_at>=%s and d.created_at<%s""" + ("" if include_synthetic else " and p.synthetic=false"), (environment, start_utc, end_utc))["n"]
    funnel = {k: by_name.get(k, 0) for k in ("game_start", "game_finish_verified", "draw_result", "claim_submit")}
    funnel["wins"] = wins
    funnel["denominators"] = {"game_finish_verified": "game_start", "draw_result": "game_finish_verified", "wins": "draw_result", "claim_submit": "wins"}
    return 200, {"totals": totals, "inventory": [dict(r) for r in inventory], "screen_metrics": [dict(r) for r in screens], "channels": [dict(r) for r in channels], "funnel": funnel, "referrals": dict(refs), "definitions": {"participants": "기간 내 생성된 익명 참가자 ID 수", "active_ms": "화면이 보이는 동안 수집된 활성 시간 합계", "estimated_exits": "기간 내 참가자별 마지막 page_view 화면 기준 추정", "invite_share_open": "공유창 열림이며 공유 완료가 아님", "gemini_link_click": "외부 링크 클릭이며 가입 완료가 아님", "synthetic": "기본 집계에서 합성 데이터를 제외하며 비운영 환경에서만 include_synthetic=true로 포함", "funnel": "각 단계는 조회 기간 내 발생 건수이며 동일 참가자 코호트 전환율이 아님; 수령 분모는 당첨(wins)"}, "period": {"from": start.isoformat(), "to": end.isoformat(), "timezone": "Asia/Seoul"}, "generated_at": int(dt.datetime.now(dt.timezone.utc).timestamp())}


def dispatch(conn, method: str, path: str, body: dict | None, query: dict | None, context: dict):
    body, query, method = body or {}, query or {}, method.upper()
    if method == "GET" and path == "/api/campaign": return _campaign_response(conn)
    if method == "POST" and path == "/api/participants/anonymous": return _create_participant(conn, body, context)
    if method == "GET" and path == "/api/me": return _get_me(conn, context)
    if method == "PATCH" and path == "/api/me/profile": return _patch_profile(conn, body, context)
    if method == "POST" and path == "/api/game-sessions": return _create_session(conn, body, context)
    m = re.fullmatch(r"/api/game-sessions/([^/]+)/(start|abort|finish)", path)
    if method == "POST" and m:
        return {"start": _start_session, "abort": _abort_session, "finish": lambda c, i, x: _finish_session(c, i, body, x)}[m.group(2)](conn, m.group(1), context)
    m = re.fullmatch(r"/api/game-sessions/([^/]+)", path)
    if method == "GET" and m: return _get_session(conn, m.group(1), context)
    if method == "POST" and path == "/api/draws": return _draw(conn, body, context)
    m = re.fullmatch(r"/api/draws/([^/]+)/scratch-complete", path)
    if method == "PATCH" and m: return _scratch(conn, m.group(1), context)
    if method == "GET" and path == "/api/claims": return _claims(conn, context)
    m = re.fullmatch(r"/api/claims/([^/]+)/submit", path)
    if method == "POST" and m: return _submit_claim(conn, m.group(1), body, context)
    if method == "GET" and path == "/api/referrals/me": return _referrals(conn, context)
    if method == "POST" and path == "/api/referrals/attribute": return _attribute(conn, body, context)
    if method == "POST" and path == "/api/benefit-verifications": return _benefit(conn, context)
    if method == "GET" and path == "/api/leaderboard": return _leaderboard(conn, query, context)
    if method == "POST" and path == "/api/events": return _events(conn, body, context)
    if method == "GET" and path == "/api/admin/overview": return _admin_overview(conn, query, context)
    if method == "GET" and path == "/api/admin/scores/suspicious": return _admin_suspicious(conn, context)
    if method == "POST" and path == "/api/admin/campaign/status": return _admin_status(conn, body, context)
    if method == "POST" and path == "/api/admin/tickets/adjust": return _admin_tickets(conn, body, context)
    if method == "GET" and path == "/api/admin/claims": return _admin_claims(conn, context)
    raise DomainError("NOT_FOUND", "요청한 API를 찾을 수 없습니다.", 404)
