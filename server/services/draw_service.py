"""
Draw (Lucky Pouch & Scratch Card) & Prize Inventory Service for v1.1
"""
import time
import uuid
import random
import sqlite3

def execute_draw(conn: sqlite3.Connection, session_id: str, participant_id: str, pouch_index: int):
    cur = conn.cursor()

    # 1. Idempotency Check: check if already drawn for this session
    cur.execute("""
    SELECT d.id, d.pouch_index, d.is_won, d.scratch_completed, p.id as prize_id, p.name, p.category, p.image_url, c.id as claim_id, c.status as claim_status
    FROM draw d
    JOIN prize p ON d.prize_id = p.id
    LEFT JOIN claim c ON c.draw_id = d.id
    WHERE d.session_id = ?
    """, (session_id,))
    existing = cur.fetchone()
    if existing:
        return {
            'draw_id': existing['id'],
            'pouch_index': existing['pouch_index'],
            'is_won': bool(existing['is_won']),
            'scratch_completed': bool(existing['scratch_completed']),
            'prize': {
                'id': existing['prize_id'],
                'name': existing['name'],
                'category': existing['category'],
                'image_url': existing['image_url']
            },
            'claim_id': existing['claim_id'],
            'claim_status': existing['claim_status']
        }

    # 2. Check game session qualification
    cur.execute("""
    SELECT status, verification_result, participant_id
    FROM game_session
    WHERE id = ?
    """, (session_id,))
    session = cur.fetchone()
    if not session or session['participant_id'] != participant_id:
        raise ValueError("INVALID_SESSION")
    if session['status'] != 'FINISHED':
        raise ValueError("SESSION_NOT_FINISHED")

    # 3. Fetch active prizes and calculate probabilities
    cur.execute("""
    SELECT id, name, category, image_url, total_stock, reserved_stock, issued_stock, probability
    FROM prize
    WHERE is_active = 1
    """)
    prizes = [dict(r) for r in cur.fetchall()]

    no_prize_item = next((p for p in prizes if p['category'] == 'NO_PRIZE'), None)
    if not no_prize_item:
        raise RuntimeError("No default fallback prize found")

    # Shift probability mass of out-of-stock items to NO_PRIZE
    available_prizes = []
    accumulated_no_prize_prob = no_prize_item['probability']

    for p in prizes:
        if p['category'] == 'NO_PRIZE':
            continue
        remaining_stock = p['total_stock'] - (p['reserved_stock'] + p['issued_stock'])
        if remaining_stock > 0:
            available_prizes.append(p)
        else:
            # Out of stock: shift prob to NO_PRIZE
            accumulated_no_prize_prob += p['probability']

    # Normalize probabilities
    pool = []
    for p in available_prizes:
        pool.append((p, p['probability']))
    pool.append((no_prize_item, accumulated_no_prize_prob))

    # Random selection
    total_weight = sum(w for _, w in pool)
    rnd = random.random() * total_weight
    upto = 0.0
    selected_prize = pool[-1][0]
    for p, weight in pool:
        if upto + weight >= rnd:
            selected_prize = p
            break
        upto += weight

    is_won = (selected_prize['category'] != 'NO_PRIZE')
    now = int(time.time())
    draw_id = f"draw_{uuid.uuid4().hex[:12]}"
    claim_id = None

    # Atomic insertion: insert draw first so claim foreign key succeeds
    cur.execute("""
    INSERT INTO draw (id, session_id, participant_id, pouch_index, prize_id, is_won, scratch_completed, created_at)
    VALUES (?, ?, ?, ?, ?, ?, 0, ?)
    """, (draw_id, session_id, participant_id, pouch_index, selected_prize['id'], 1 if is_won else 0, now))

    if is_won:
        cur.execute("""
        UPDATE prize
        SET reserved_stock = reserved_stock + 1
        WHERE id = ?
        """, (selected_prize['id'],))

        claim_id = f"claim_{uuid.uuid4().hex[:12]}"
        expires_at = now + (72 * 3600) # 72 hours
        cur.execute("""
        INSERT INTO claim (id, draw_id, participant_id, prize_id, status, expires_at, created_at)
        VALUES (?, ?, ?, ?, 'READY', ?, ?)
        """, (claim_id, draw_id, participant_id, selected_prize['id'], expires_at, now))

    return {
        'draw_id': draw_id,
        'pouch_index': pouch_index,
        'is_won': is_won,
        'scratch_completed': False,
        'prize': {
            'id': selected_prize['id'],
            'name': selected_prize['name'],
            'category': selected_prize['category'],
            'image_url': selected_prize['image_url']
        },
        'claim_id': claim_id,
        'claim_status': 'READY' if is_won else None
    }

def mark_scratch_completed(conn: sqlite3.Connection, draw_id: str, participant_id: str):
    cur = conn.cursor()
    cur.execute("""
    UPDATE draw
    SET scratch_completed = 1
    WHERE id = ? AND participant_id = ?
    """, (draw_id, participant_id))
