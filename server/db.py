"""
SQLite Database Schema and Access Layer for Team Gemini Dino Jump Event v1.1
"""
import sqlite3
import os
import json
import time
import uuid

def get_db_path():
    env_path = os.environ.get('DB_PATH')
    if env_path:
        return env_path
    if os.environ.get('VERCEL') or os.environ.get('AWS_LAMBDA_FUNCTION_NAME'):
        tmp_db = '/tmp/dino_jump.db'
        orig_db = os.path.join(os.path.dirname(__file__), 'dino_jump.db')
        if not os.path.exists(tmp_db):
            if os.path.exists(orig_db):
                import shutil
                try:
                    shutil.copyfile(orig_db, tmp_db)
                except Exception:
                    pass
        return tmp_db
    return os.path.join(os.path.dirname(__file__), 'dino_jump.db')

DB_PATH = get_db_path()

def get_db_connection():
    db_path = get_db_path()
    need_init = not os.path.exists(db_path)
    conn = sqlite3.connect(db_path, timeout=10.0)
    conn.row_factory = sqlite3.Row
    try:
        conn.execute("PRAGMA journal_mode=WAL")
    except Exception:
        pass
    conn.execute("PRAGMA foreign_keys=ON")
    if need_init:
        init_db_with_conn(conn)
    return conn

def init_db():
    conn = get_db_connection()
    init_db_with_conn(conn)
    conn.close()

def init_db_with_conn(conn):
    with conn:
        conn.executescript("""
        CREATE TABLE IF NOT EXISTS campaign (
            id TEXT PRIMARY KEY,
            title TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE', -- ACTIVE, MAINTENANCE, PAUSED, ENDED
            benefit_url TEXT NOT NULL,
            game_version TEXT NOT NULL DEFAULT '1.1.0',
            announcement_version TEXT NOT NULL DEFAULT '1.0',
            updated_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS participant (
            id TEXT PRIMARY KEY,
            session_token TEXT UNIQUE NOT NULL,
            nickname TEXT NOT NULL,
            is_public INTEGER NOT NULL DEFAULT 1,
            referral_code TEXT UNIQUE NOT NULL,
            created_at INTEGER NOT NULL,
            status TEXT NOT NULL DEFAULT 'ACTIVE'
        );

        CREATE TABLE IF NOT EXISTS game_session (
            id TEXT PRIMARY KEY,
            participant_id TEXT NOT NULL,
            seed INTEGER NOT NULL,
            version TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'RESERVED', -- RESERVED, ACTIVE, FINISHED, ABORTED
            reserved_at INTEGER NOT NULL,
            started_at INTEGER,
            finished_at INTEGER,
            score INTEGER NOT NULL DEFAULT 0,
            valid_ticks INTEGER NOT NULL DEFAULT 0,
            verification_result TEXT, -- VERIFIED, CHEAT_DETECTED, REJECTED
            input_log TEXT,
            FOREIGN KEY (participant_id) REFERENCES participant(id)
        );

        CREATE TABLE IF NOT EXISTS ticket_ledger (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            participant_id TEXT NOT NULL,
            delta INTEGER NOT NULL,
            source_type TEXT NOT NULL, -- INITIAL, REFERRAL, PLAY_CONSUME, ADMIN_ADJUST
            source_id TEXT,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (participant_id) REFERENCES participant(id)
        );

        CREATE TABLE IF NOT EXISTS best_score (
            participant_id TEXT PRIMARY KEY,
            session_id TEXT NOT NULL,
            score INTEGER NOT NULL,
            achieved_at INTEGER NOT NULL,
            FOREIGN KEY (participant_id) REFERENCES participant(id),
            FOREIGN KEY (session_id) REFERENCES game_session(id)
        );

        CREATE TABLE IF NOT EXISTS prize (
            id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            category TEXT NOT NULL, -- COUPON, SHIPPING, DIGITAL, NO_PRIZE
            image_url TEXT NOT NULL,
            total_stock INTEGER NOT NULL,
            reserved_stock INTEGER NOT NULL DEFAULT 0,
            issued_stock INTEGER NOT NULL DEFAULT 0,
            probability REAL NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS draw (
            id TEXT PRIMARY KEY,
            session_id TEXT UNIQUE NOT NULL,
            participant_id TEXT NOT NULL,
            pouch_index INTEGER NOT NULL, -- 0, 1, 2
            prize_id TEXT NOT NULL,
            is_won INTEGER NOT NULL,
            scratch_completed INTEGER NOT NULL DEFAULT 0,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (session_id) REFERENCES game_session(id),
            FOREIGN KEY (participant_id) REFERENCES participant(id),
            FOREIGN KEY (prize_id) REFERENCES prize(id)
        );

        CREATE TABLE IF NOT EXISTS claim (
            id TEXT PRIMARY KEY,
            draw_id TEXT UNIQUE NOT NULL,
            participant_id TEXT NOT NULL,
            prize_id TEXT NOT NULL,
            status TEXT NOT NULL DEFAULT 'READY', -- READY, ELIGIBILITY_PENDING, ISSUING, ISSUED, EXPIRED, REJECTED
            recipient_name TEXT,
            contact_phone TEXT,
            shipping_address TEXT,
            coupon_code TEXT,
            expires_at INTEGER NOT NULL,
            created_at INTEGER NOT NULL,
            FOREIGN KEY (draw_id) REFERENCES draw(id),
            FOREIGN KEY (participant_id) REFERENCES participant(id),
            FOREIGN KEY (prize_id) REFERENCES prize(id)
        );

        CREATE TABLE IF NOT EXISTS referral (
            id TEXT PRIMARY KEY,
            inviter_id TEXT NOT NULL,
            invitee_id TEXT UNIQUE NOT NULL,
            status TEXT NOT NULL DEFAULT 'PENDING', -- PENDING, QUALIFIED, REWARDED
            created_at INTEGER NOT NULL,
            qualified_at INTEGER,
            FOREIGN KEY (inviter_id) REFERENCES participant(id),
            FOREIGN KEY (invitee_id) REFERENCES participant(id)
        );

        CREATE TABLE IF NOT EXISTS benefit_verification (
            participant_id TEXT PRIMARY KEY,
            status TEXT NOT NULL DEFAULT 'NOT_STARTED', -- NOT_STARTED, PENDING, VERIFIED, REJECTED
            note TEXT,
            updated_at INTEGER NOT NULL,
            FOREIGN KEY (participant_id) REFERENCES participant(id)
        );

        CREATE TABLE IF NOT EXISTS analytics_events (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            event_id TEXT UNIQUE,
            participant_id TEXT,
            event_name TEXT NOT NULL,
            payload TEXT,
            created_at INTEGER NOT NULL
        );

        CREATE TABLE IF NOT EXISTS admin_audit (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            admin_user TEXT NOT NULL,
            action TEXT NOT NULL,
            target_type TEXT NOT NULL,
            target_id TEXT,
            details TEXT,
            created_at INTEGER NOT NULL
        );
        """)

        # Initialize default campaign if not exists
        cur = conn.cursor()
        cur.execute("SELECT id FROM campaign WHERE id = 'gemini_dino_2026'")
        if not cur.fetchone():
            now = int(time.time())
            cur.execute("""
            INSERT INTO campaign (id, title, status, benefit_url, game_version, announcement_version, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """, (
                'gemini_dino_2026',
                'Team Gemini 공룡 점프 챌린지 2026',
                'ACTIVE',
                'https://gemini.google.com/students',
                '1.1.0',
                '1.1',
                now
            ))

        # Initialize default prize pool if empty
        cur.execute("SELECT COUNT(*) FROM prize")
        if cur.fetchone()[0] == 0:
            default_prizes = [
                ('prize_coffee', '메가커피 아메리카노', 'COUPON', '/assets/icons/Picture-Light.png', 50, 0, 0, 0.15, 1),
                ('prize_convenience', 'GS25 모바일 상품권 3천원', 'COUPON', '/assets/icons/Picture-Dark.png', 30, 0, 0, 0.08, 1),
                ('prize_merch', 'Team Gemini 한정판 스티커팩 & 굿즈', 'SHIPPING', '/assets/icons/Smile-Light.png', 20, 0, 0, 0.05, 1),
                ('prize_baemin', '배달의민족 1만원권', 'COUPON', '/assets/icons/Heart-Dark.png', 10, 0, 0, 0.02, 1),
                ('prize_gemini_free', '제미나이 1년 무료 이용권', 'NO_PRIZE', '/assets/icons/Rocket-Dark.png', 999999, 0, 0, 0.70, 1)
            ]
            cur.executemany("""
            INSERT INTO prize (id, name, category, image_url, total_stock, reserved_stock, issued_stock, probability, is_active)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """, default_prizes)

if __name__ == '__main__':
    init_db()
    print("Database initialized successfully.")
