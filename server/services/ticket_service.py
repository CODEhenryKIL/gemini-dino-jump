"""
Ticket Ledger and Concurrency Management Service
"""
import time
import sqlite3

INFINITE_TICKETS = True

def get_ticket_balance(conn: sqlite3.Connection, participant_id: str) -> int:
    if INFINITE_TICKETS:
        return 9999
    cur = conn.cursor()
    cur.execute("SELECT COALESCE(SUM(delta), 0) FROM ticket_ledger WHERE participant_id = ?", (participant_id,))
    row = cur.fetchone()
    return int(row[0]) if row else 0

def grant_initial_ticket_if_needed(conn: sqlite3.Connection, participant_id: str) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT COUNT(*) FROM ticket_ledger WHERE participant_id = ?", (participant_id,))
    if cur.fetchone()[0] == 0:
        now = int(time.time())
        cur.execute("""
        INSERT INTO ticket_ledger (participant_id, delta, source_type, source_id, created_at)
        VALUES (?, 1, 'INITIAL', 'welcome', ?)
        """, (participant_id, now))
        return True
    return False

def check_active_session_exists(conn: sqlite3.Connection, participant_id: str) -> bool:
    now = int(time.time())
    cur = conn.cursor()
    # Reserved within 30s or Active
    cur.execute("""
    SELECT COUNT(*) FROM game_session
    WHERE participant_id = ? AND (
        (status = 'RESERVED' AND reserved_at >= ?) OR
        (status = 'ACTIVE')
    )
    """, (participant_id, now - 30))
    return cur.fetchone()[0] > 0

def consume_ticket_for_play(conn: sqlite3.Connection, participant_id: str, session_id: str) -> bool:
    if INFINITE_TICKETS:
        now = int(time.time())
        cur = conn.cursor()
        cur.execute("""
        INSERT INTO ticket_ledger (participant_id, delta, source_type, source_id, created_at)
        VALUES (?, -1, 'PLAY_CONSUME', ?, ?)
        """, (participant_id, session_id, now))
        return True

    balance = get_ticket_balance(conn, participant_id)
    if balance < 1:
        return False
    now = int(time.time())
    cur = conn.cursor()
    cur.execute("""
    INSERT INTO ticket_ledger (participant_id, delta, source_type, source_id, created_at)
    VALUES (?, -1, 'PLAY_CONSUME', ?, ?)
    """, (participant_id, session_id, now))
    return True
