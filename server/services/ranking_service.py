"""
Ranking & Leaderboard Service
"""
import sqlite3

def get_leaderboard(conn: sqlite3.Connection, current_participant_id: str = None, limit: int = 100):
    cur = conn.cursor()
    # Fetch public best scores
    cur.execute("""
    SELECT 
        b.score,
        b.achieved_at,
        p.nickname,
        p.id as participant_id
    FROM best_score b
    JOIN participant p ON b.participant_id = p.id
    WHERE p.is_public = 1
    ORDER BY b.score DESC, b.achieved_at ASC, p.id ASC
    LIMIT ?
    """, (limit,))
    
    rows = cur.fetchall()
    leaderboard = []
    for idx, r in enumerate(rows):
        leaderboard.append({
            'rank': idx + 1,
            'nickname': r['nickname'],
            'score': r['score'],
            'achieved_at': r['achieved_at'],
            'is_me': (r['participant_id'] == current_participant_id)
        })

    # My personal rank and best score
    my_card = None
    if current_participant_id:
        cur.execute("""
        SELECT b.score, b.achieved_at, p.nickname, p.is_public
        FROM best_score b
        JOIN participant p ON b.participant_id = p.id
        WHERE p.id = ?
        """, (current_participant_id,))
        my_row = cur.fetchone()
        if my_row:
            my_score = my_row['score']
            my_time = my_row['achieved_at']
            # Calculate rank among all valid scores
            cur.execute("""
            SELECT COUNT(*) + 1 FROM best_score
            WHERE (score > ?) OR (score = ? AND achieved_at < ?)
            """, (my_score, my_score, my_time))
            my_rank = cur.fetchone()[0]
            my_card = {
                'rank': my_rank,
                'score': my_score,
                'nickname': my_row['nickname'],
                'is_public': bool(my_row['is_public'])
            }

    return {
        'leaderboard': leaderboard,
        'my_card': my_card
    }

def update_best_score_if_higher(conn: sqlite3.Connection, participant_id: str, session_id: str, score: int, achieved_at: int) -> bool:
    cur = conn.cursor()
    cur.execute("SELECT score FROM best_score WHERE participant_id = ?", (participant_id,))
    row = cur.fetchone()
    if not row:
        cur.execute("""
        INSERT INTO best_score (participant_id, session_id, score, achieved_at)
        VALUES (?, ?, ?, ?)
        """, (participant_id, session_id, score, achieved_at))
        return True
    elif score > row['score']:
        cur.execute("""
        UPDATE best_score
        SET session_id = ?, score = ?, achieved_at = ?
        WHERE participant_id = ?
        """, (session_id, score, achieved_at, participant_id))
        return True
    return False
