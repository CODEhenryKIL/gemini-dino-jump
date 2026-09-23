"""
Referral and Viral Loop Management Service
"""
import time
import datetime
import sqlite3

def attribute_referral(conn: sqlite3.Connection, invite_code: str, invitee_id: str) -> bool:
    cur = conn.cursor()
    # Find inviter
    cur.execute("SELECT id FROM participant WHERE referral_code = ?", (invite_code,))
    row = cur.fetchone()
    if not row:
        return False
    inviter_id = row['id']
    if inviter_id == invitee_id:
        return False # Self-referral not allowed

    # Check if invitee already attributed
    cur.execute("SELECT COUNT(*) FROM referral WHERE invitee_id = ?", (invitee_id,))
    if cur.fetchone()[0] > 0:
        return False # Already attributed to another inviter

    now = int(time.time())
    ref_id = f"ref_{invitee_id[:8]}_{inviter_id[:8]}"
    cur.execute("""
    INSERT INTO referral (id, inviter_id, invitee_id, status, created_at)
    VALUES (?, ?, ?, 'PENDING', ?)
    """, (ref_id, inviter_id, invitee_id, now))
    return True

def trigger_first_game_reward(conn: sqlite3.Connection, invitee_id: str):
    cur = conn.cursor()
    cur.execute("""
    SELECT id, inviter_id, status FROM referral
    WHERE invitee_id = ? AND status = 'PENDING'
    """, (invitee_id,))
    ref = cur.fetchone()
    if not ref:
        return None

    inviter_id = ref['inviter_id']
    ref_id = ref['id']
    now = int(time.time())

    # Calculate KST date for daily limit
    # KST is UTC + 9
    kst_now = datetime.datetime.fromtimestamp(now, datetime.timezone(datetime.timedelta(hours=9)))
    kst_start_of_day = int(kst_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    # Check daily limit (max 3 per day)
    cur.execute("""
    SELECT COUNT(*) FROM ticket_ledger
    WHERE participant_id = ? AND source_type = 'REFERRAL' AND created_at >= ?
    """, (inviter_id, kst_start_of_day))
    daily_count = cur.fetchone()[0]

    # Check total limit (max 10 overall)
    cur.execute("""
    SELECT COUNT(*) FROM ticket_ledger
    WHERE participant_id = ? AND source_type = 'REFERRAL'
    """, (inviter_id,))
    total_count = cur.fetchone()[0]

    reward_granted = False
    if daily_count < 3 and total_count < 10:
        cur.execute("""
        INSERT INTO ticket_ledger (participant_id, delta, source_type, source_id, created_at)
        VALUES (?, 1, 'REFERRAL', ?, ?)
        """, (inviter_id, ref_id, now))
        reward_granted = True

    cur.execute("""
    UPDATE referral
    SET status = 'QUALIFIED', qualified_at = ?
    WHERE id = ?
    """, (now, ref_id))

    return {
        'inviter_id': inviter_id,
        'reward_granted': reward_granted,
        'daily_count': daily_count + (1 if reward_granted else 0),
        'total_count': total_count + (1 if reward_granted else 0)
    }

def get_referral_summary(conn: sqlite3.Connection, participant_id: str):
    cur = conn.cursor()
    # Total qualified referrals
    cur.execute("SELECT COUNT(*) FROM referral WHERE inviter_id = ? AND status = 'QUALIFIED'", (participant_id,))
    qualified_count = cur.fetchone()[0]

    # Pending referrals
    cur.execute("SELECT COUNT(*) FROM referral WHERE inviter_id = ? AND status = 'PENDING'", (participant_id,))
    pending_count = cur.fetchone()[0]

    # Tickets earned today
    now = int(time.time())
    kst_now = datetime.datetime.fromtimestamp(now, datetime.timezone(datetime.timedelta(hours=9)))
    kst_start_of_day = int(kst_now.replace(hour=0, minute=0, second=0, microsecond=0).timestamp())

    cur.execute("""
    SELECT COUNT(*) FROM ticket_ledger
    WHERE participant_id = ? AND source_type = 'REFERRAL' AND created_at >= ?
    """, (participant_id, kst_start_of_day))
    daily_earned = cur.fetchone()[0]

    cur.execute("""
    SELECT COUNT(*) FROM ticket_ledger
    WHERE participant_id = ? AND source_type = 'REFERRAL'
    """, (participant_id,))
    total_earned = cur.fetchone()[0]

    return {
        'qualified_count': qualified_count,
        'pending_count': pending_count,
        'daily_earned': daily_earned,
        'total_earned': total_earned,
        'daily_limit': 3,
        'total_limit': 10
    }
