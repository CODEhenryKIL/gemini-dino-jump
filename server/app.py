"""
Full-featured HTTP REST API and Static File Server for Team Gemini Dino Jump Event v1.1
Zero external dependencies, purely standard Python 3.9+ library (http.server, sqlite3, json)
"""
import sys
import os
import json
import time
import uuid
import re
import urllib.parse
from http.server import ThreadingHTTPServer, SimpleHTTPRequestHandler

# Import internal modules
sys.path.insert(0, os.path.dirname(__file__))
import db
import game_verifier
from services import ticket_service, ranking_service, draw_service, referral_service

PORT = int(os.environ.get('PORT', 3000))
PUBLIC_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'public'))
SHARED_DIR = os.path.abspath(os.path.join(os.path.dirname(__file__), '..', 'shared'))

def generate_random_nickname():
    adjectives = ['날렵한', '행운의', '달리는', '귀여운', '용감한', '슈퍼', '빛나는', '초록색', '똑똑한', '스마트']
    nouns = ['공룡이', '제미나이', '러너', '티라노', '트리케라', '점퍼', '앰버서더', '스튜던트', '마스코트', '별똥별']
    import random
    num = random.randint(100, 999)
    return f"{random.choice(adjectives)}{random.choice(nouns)}{num}"

def generate_referral_code():
    return uuid.uuid4().hex[:8]

class DinoJumpHandler(SimpleHTTPRequestHandler):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, directory=PUBLIC_DIR, **kwargs)

    def log_message(self, format, *args):
        # Concise logging
        sys.stderr.write(f"[{time.strftime('%X')}] {format % args}\n")

    def send_json(self, status_code: int, data: dict):
        response_bytes = json.dumps(data, ensure_ascii=False).encode('utf-8')
        self.send_response(status_code)
        self.send_header('Content-Type', 'application/json; charset=utf-8')
        self.send_header('Content-Length', str(len(response_bytes)))
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()
        self.wfile.write(response_bytes)

    def do_OPTIONS(self):
        self.send_response(204)
        self.send_header('Access-Control-Allow-Origin', '*')
        self.send_header('Access-Control-Allow-Methods', 'GET, POST, PATCH, OPTIONS')
        self.send_header('Access-Control-Allow-Headers', 'Content-Type, Authorization')
        self.end_headers()

    def parse_body(self):
        content_length = int(self.headers.get('Content-Length', 0))
        if content_length == 0:
            return {}
        body = self.rfile.read(content_length).decode('utf-8')
        try:
            return json.loads(body)
        except Exception:
            return {}

    def get_authenticated_participant(self, conn):
        auth_header = self.headers.get('Authorization', '')
        token = ''
        if auth_header.startswith('Bearer '):
            token = auth_header[7:].strip()
        if not token:
            return None
        cur = conn.cursor()
        cur.execute("SELECT id, nickname, is_public, referral_code, status FROM participant WHERE session_token = ?", (token,))
        row = cur.fetchone()
        return dict(row) if row else None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        query = urllib.parse.parse_qs(parsed.query)

        # 1. API routes
        if path.startswith('/api/'):
            conn = db.get_db_connection()
            try:
                if path == '/api/campaign':
                    self.handle_get_campaign(conn)
                elif path == '/api/me':
                    self.handle_get_me(conn)
                elif path == '/api/leaderboard':
                    self.handle_get_leaderboard(conn, query)
                elif path.startswith('/api/game-sessions/'):
                    session_id = path.split('/')[-1]
                    self.handle_get_session(conn, session_id)
                elif path == '/api/claims':
                    self.handle_get_claims(conn)
                elif path == '/api/referrals/me':
                    self.handle_get_referrals_me(conn)
                elif path == '/api/admin/overview':
                    self.handle_admin_overview(conn)
                elif path == '/api/admin/scores/suspicious':
                    self.handle_admin_suspicious(conn)
                elif path == '/api/shared/game_constants.json':
                    with open(os.path.join(SHARED_DIR, 'game_constants.json'), 'r', encoding='utf-8') as f:
                        self.send_json(200, json.load(f))
                else:
                    self.send_json(404, {'error': 'NOT_FOUND'})
            finally:
                conn.close()
            return

        # 2. Rewrite /invite/{code} to /index.html with invite query
        if path.startswith('/invite/'):
            code = path.split('/')[-1]
            self.send_response(302)
            self.send_header('Location', f'/?invite={code}')
            self.end_headers()
            return

        # 3. Static files
        return super().do_GET()

    def do_POST(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.parse_body()
        conn = db.get_db_connection()

        try:
            if path == '/api/participants/anonymous':
                self.handle_create_participant(conn, body)
            elif path == '/api/game-sessions':
                self.handle_create_session(conn)
            elif path.endswith('/start') and path.startswith('/api/game-sessions/'):
                session_id = path.split('/')[-2]
                self.handle_start_session(conn, session_id)
            elif path.endswith('/finish') and path.startswith('/api/game-sessions/'):
                session_id = path.split('/')[-2]
                self.handle_finish_session(conn, session_id, body)
            elif path == '/api/draws':
                self.handle_draw(conn, body)
            elif path.startswith('/api/claims/') and path.endswith('/submit'):
                claim_id = path.split('/')[-2]
                self.handle_submit_claim(conn, claim_id, body)
            elif path == '/api/referrals/attribute':
                self.handle_referral_attribute(conn, body)
            elif path == '/api/benefit-verifications':
                self.handle_benefit_verifications(conn, body)
            elif path == '/api/events':
                self.handle_analytics_event(conn, body)
            elif path == '/api/admin/campaign/status':
                self.handle_admin_campaign_status(conn, body)
            elif path == '/api/admin/tickets/adjust':
                self.handle_admin_ticket_adjust(conn, body)
            else:
                self.send_json(404, {'error': 'NOT_FOUND'})
        finally:
            conn.close()

    def do_PATCH(self):
        parsed = urllib.parse.urlparse(self.path)
        path = parsed.path
        body = self.parse_body()
        conn = db.get_db_connection()

        try:
            if path == '/api/me/profile':
                self.handle_patch_profile(conn, body)
            elif path.startswith('/api/draws/') and path.endswith('/scratch-complete'):
                draw_id = path.split('/')[-2]
                self.handle_scratch_complete(conn, draw_id)
            else:
                self.send_json(404, {'error': 'NOT_FOUND'})
        finally:
            conn.close()

    # --- Handlers ---

    def handle_get_campaign(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT id, title, status, benefit_url, game_version, announcement_version FROM campaign WHERE id = 'gemini_dino_2026'")
        campaign = dict(cur.fetchone())

        cur.execute("SELECT id, name, category, image_url, probability FROM prize WHERE is_active = 1")
        prizes = [dict(r) for r in cur.fetchall()]

        self.send_json(200, {
            'campaign': campaign,
            'prizes': prizes
        })

    def handle_create_participant(self, conn, body):
        token = body.get('session_token')
        cur = conn.cursor()
        if token:
            cur.execute("SELECT id, session_token, nickname, is_public, referral_code FROM participant WHERE session_token = ?", (token,))
            existing = cur.fetchone()
            if existing:
                self.send_json(200, dict(existing))
                return

        new_id = f"p_{uuid.uuid4().hex[:12]}"
        new_token = f"tok_{uuid.uuid4().hex}"
        nickname = generate_random_nickname()
        ref_code = generate_referral_code()
        now = int(time.time())

        with conn:
            cur.execute("""
            INSERT INTO participant (id, session_token, nickname, is_public, referral_code, created_at, status)
            VALUES (?, ?, ?, 1, ?, ?, 'ACTIVE')
            """, (new_id, new_token, nickname, ref_code, now))
            # Grant initial ticket
            ticket_service.grant_initial_ticket_if_needed(conn, new_id)

        # Attribute referral if provided in body
        invite_code = body.get('invite_code')
        if invite_code:
            try:
                referral_service.attribute_referral(conn, invite_code, new_id)
            except Exception:
                pass

        self.send_json(201, {
            'id': new_id,
            'session_token': new_token,
            'nickname': nickname,
            'is_public': True,
            'referral_code': ref_code
        })

    def handle_get_me(self, conn):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        balance = ticket_service.get_ticket_balance(conn, p_id)
        cur = conn.cursor()

        # Check best score
        cur.execute("SELECT score, achieved_at FROM best_score WHERE participant_id = ?", (p_id,))
        bs = cur.fetchone()
        best_score = bs['score'] if bs else 0

        # Check unfinished active session or unconsumed draw
        cur.execute("""
        SELECT s.id, s.status, s.score, d.id as draw_id, d.scratch_completed
        FROM game_session s
        LEFT JOIN draw d ON d.session_id = s.id
        WHERE s.participant_id = ? AND s.status = 'FINISHED' AND (d.id IS NULL OR d.scratch_completed = 0)
        ORDER BY s.finished_at DESC LIMIT 1
        """, (p_id,))
        pending_draw_row = cur.fetchone()
        pending_draw = dict(pending_draw_row) if pending_draw_row else None

        # Pending claims count
        cur.execute("SELECT COUNT(*) FROM claim WHERE participant_id = ? AND status = 'READY'", (p_id,))
        ready_claims_count = cur.fetchone()[0]

        # Benefit verification status
        cur.execute("SELECT status FROM benefit_verification WHERE participant_id = ?", (p_id,))
        bv = cur.fetchone()
        benefit_status = bv['status'] if bv else 'NOT_STARTED'

        # Referral stats
        ref_summary = referral_service.get_referral_summary(conn, p_id)

        self.send_json(200, {
            'participant': participant,
            'tickets': balance,
            'best_score': best_score,
            'pending_draw': pending_draw,
            'ready_claims_count': ready_claims_count,
            'benefit_status': benefit_status,
            'referral': ref_summary
        })

    def handle_patch_profile(self, conn, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        nickname = body.get('nickname')
        is_public = body.get('is_public')

        with conn:
            cur = conn.cursor()
            if nickname is not None:
                nickname = str(nickname).strip()
                if not (2 <= len(nickname) <= 12):
                    self.send_json(400, {'error': 'NICKNAME_LENGTH_INVALID', 'message': '2자 이상 12자 이하로 입력해주세요.'})
                    return
                # Check banned patterns (e.g. phone numbers or slurs)
                if re.search(r'\d{3}[-\s]?\d{3,4}[-\s]?\d{4}', nickname):
                    self.send_json(400, {'error': 'NICKNAME_INVALID', 'message': '연락처 형식은 사용할 수 없습니다.'})
                    return
                cur.execute("UPDATE participant SET nickname = ? WHERE id = ?", (nickname, p_id))

            if is_public is not None:
                cur.execute("UPDATE participant SET is_public = ? WHERE id = ?", (1 if is_public else 0, p_id))

        self.send_json(200, {'success': True, 'nickname': nickname, 'is_public': is_public})

    def handle_create_session(self, conn):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        # 1. Check ticket balance
        balance = ticket_service.get_ticket_balance(conn, p_id)
        if balance < 1:
            self.send_json(400, {'error': 'NO_TICKET', 'message': '게임권이 부족합니다.'})
            return

        # 2. Check active session
        if ticket_service.check_active_session_exists(conn, p_id):
            self.send_json(400, {'error': 'SESSION_ACTIVE', 'message': '이미 진행 중인 게임 세션이 있습니다.'})
            return

        import random
        seed = random.randint(100000, 99999999)
        session_id = f"s_{uuid.uuid4().hex[:12]}"
        now = int(time.time())

        with conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO game_session (id, participant_id, seed, version, status, reserved_at)
            VALUES (?, ?, ?, '1.1.0', 'RESERVED', ?)
            """, (session_id, p_id, seed, now))

        self.send_json(201, {
            'session_id': session_id,
            'seed': seed,
            'status': 'RESERVED',
            'version': '1.1.0'
        })

    def handle_start_session(self, conn, session_id):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        cur = conn.cursor()
        cur.execute("SELECT status, participant_id FROM game_session WHERE id = ?", (session_id,))
        session = cur.fetchone()
        if not session or session['participant_id'] != p_id:
            self.send_json(404, {'error': 'SESSION_NOT_FOUND'})
            return

        if session['status'] == 'ACTIVE':
            # Idempotent return
            self.send_json(200, {'status': 'ACTIVE', 'session_id': session_id})
            return

        if session['status'] != 'RESERVED':
            self.send_json(400, {'error': 'INVALID_SESSION_STATE'})
            return

        # Deduct ticket atomically
        with conn:
            consumed = ticket_service.consume_ticket_for_play(conn, p_id, session_id)
            if not consumed:
                self.send_json(400, {'error': 'NO_TICKET'})
                return
            now = int(time.time())
            cur.execute("UPDATE game_session SET status = 'ACTIVE', started_at = ? WHERE id = ?", (now, session_id))

        self.send_json(200, {'status': 'ACTIVE', 'session_id': session_id, 'started_at': now})

    def handle_finish_session(self, conn, session_id, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        cur = conn.cursor()
        cur.execute("SELECT status, participant_id, seed, started_at FROM game_session WHERE id = ?", (session_id,))
        session = cur.fetchone()
        if not session or session['participant_id'] != p_id:
            self.send_json(404, {'error': 'SESSION_NOT_FOUND'})
            return

        if session['status'] == 'FINISHED':
            # Idempotent response
            cur.execute("SELECT score, valid_ticks, verification_result FROM game_session WHERE id = ?", (session_id,))
            s_row = cur.fetchone()
            self.send_json(200, {
                'session_id': session_id,
                'score': s_row['score'],
                'verification_result': s_row['verification_result']
            })
            return

        jump_ticks = body.get('jump_ticks', [])
        submitted_score = int(body.get('score', 0))
        submitted_ticks = int(body.get('ticks', 0))

        # Run deterministic simulation verification
        is_valid, server_score, collision_tick, reason = game_verifier.simulate_and_verify(
            seed=session['seed'],
            jump_ticks=jump_ticks,
            submitted_score=submitted_score,
            submitted_ticks=submitted_ticks
        )

        final_score = server_score if is_valid else min(server_score, submitted_score)
        now = int(time.time())

        with conn:
            cur.execute("""
            UPDATE game_session
            SET status = 'FINISHED',
                finished_at = ?,
                score = ?,
                valid_ticks = ?,
                verification_result = ?,
                input_log = ?
            WHERE id = ?
            """, (now, final_score, collision_tick, reason, json.dumps(jump_ticks), session_id))

            # Update best score
            ranking_service.update_best_score_if_higher(conn, p_id, session_id, final_score, now)

            # Trigger referral reward if this was invitee's first qualified completed game
            reward_res = referral_service.trigger_first_game_reward(conn, p_id)

        # Get my updated rank
        cur.execute("SELECT score, achieved_at FROM best_score WHERE participant_id = ?", (p_id,))
        bs = cur.fetchone()
        best_score = bs['score'] if bs else final_score

        cur.execute("""
        SELECT COUNT(*) + 1 FROM best_score
        WHERE (score > ?) OR (score = ? AND achieved_at < ?)
        """, (best_score, best_score, bs['achieved_at'] if bs else now))
        current_rank = cur.fetchone()[0]

        self.send_json(200, {
            'session_id': session_id,
            'score': final_score,
            'best_score': best_score,
            'rank': current_rank,
            'verification_result': reason,
            'referral_reward_triggered': bool(reward_res and reward_res.get('reward_granted'))
        })

    def handle_get_session(self, conn, session_id):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        cur = conn.cursor()
        cur.execute("""
        SELECT s.id, s.status, s.seed, s.score, s.started_at, s.finished_at, s.verification_result,
               d.id as draw_id, d.pouch_index, d.is_won, d.scratch_completed
        FROM game_session s
        LEFT JOIN draw d ON d.session_id = s.id
        WHERE s.id = ? AND s.participant_id = ?
        """, (session_id, participant['id']))
        row = cur.fetchone()
        if not row:
            self.send_json(404, {'error': 'SESSION_NOT_FOUND'})
            return
        self.send_json(200, dict(row))

    def handle_get_leaderboard(self, conn, query):
        participant = self.get_authenticated_participant(conn)
        p_id = participant['id'] if participant else None
        res = ranking_service.get_leaderboard(conn, current_participant_id=p_id, limit=100)
        self.send_json(200, res)

    def handle_draw(self, conn, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        session_id = body.get('session_id')
        pouch_index = int(body.get('pouch_index', 0)) # 0, 1, 2
        if pouch_index not in (0, 1, 2):
            pouch_index = 0

        with conn:
            try:
                draw_result = draw_service.execute_draw(conn, session_id, participant['id'], pouch_index)
                self.send_json(200, draw_result)
            except ValueError as e:
                self.send_json(400, {'error': str(e)})
            except Exception as e:
                self.send_json(500, {'error': 'DRAW_ERROR', 'message': str(e)})

    def handle_scratch_complete(self, conn, draw_id):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        with conn:
            draw_service.mark_scratch_completed(conn, draw_id, participant['id'])
        self.send_json(200, {'success': True, 'draw_id': draw_id})

    def handle_get_claims(self, conn):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        cur = conn.cursor()
        cur.execute("""
        SELECT c.id, c.status, c.expires_at, c.created_at, c.coupon_code, c.recipient_name, c.contact_phone,
               p.name as prize_name, p.category, p.image_url
        FROM claim c
        JOIN prize p ON c.prize_id = p.id
        WHERE c.participant_id = ?
        ORDER BY c.created_at DESC
        """, (participant['id'],))
        claims = [dict(r) for r in cur.fetchall()]
        self.send_json(200, {'claims': claims})

    def handle_submit_claim(self, conn, claim_id, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        cur = conn.cursor()
        cur.execute("SELECT id, status, prize_id FROM claim WHERE id = ? AND participant_id = ?", (claim_id, participant['id']))
        claim = cur.fetchone()
        if not claim:
            self.send_json(404, {'error': 'CLAIM_NOT_FOUND'})
            return

        recipient_name = body.get('recipient_name', '').strip()
        contact_phone = body.get('contact_phone', '').strip()
        shipping_address = body.get('shipping_address', '').strip()

        # Generate coupon code for digital coupons
        cur.execute("SELECT category FROM prize WHERE id = ?", (claim['prize_id'],))
        cat = cur.fetchone()['category']
        generated_coupon = None
        if cat == 'COUPON':
            generated_coupon = f"GEMINI-{uuid.uuid4().hex[:4].upper()}-{uuid.uuid4().hex[:4].upper()}"

        with conn:
            cur.execute("""
            UPDATE claim
            SET recipient_name = ?,
                contact_phone = ?,
                shipping_address = ?,
                coupon_code = COALESCE(coupon_code, ?),
                status = 'ISSUED'
            WHERE id = ?
            """, (recipient_name, contact_phone, shipping_address, generated_coupon, claim_id))

            # Mark stock issued
            cur.execute("""
            UPDATE prize
            SET reserved_stock = MAX(0, reserved_stock - 1),
                issued_stock = issued_stock + 1
            WHERE id = ?
            """, (claim['prize_id'],))

        self.send_json(200, {
            'success': True,
            'claim_id': claim_id,
            'status': 'ISSUED',
            'coupon_code': generated_coupon
        })

    def handle_referral_attribute(self, conn, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        invite_code = body.get('invite_code')
        with conn:
            success = referral_service.attribute_referral(conn, invite_code, participant['id'])
        self.send_json(200, {'success': success})

    def handle_get_referrals_me(self, conn):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        summary = referral_service.get_referral_summary(conn, participant['id'])
        invite_url = f"/invite/{participant['referral_code']}"
        self.send_json(200, {
            'referral_code': participant['referral_code'],
            'invite_url': invite_url,
            'summary': summary
        })

    def handle_benefit_verifications(self, conn, body):
        participant = self.get_authenticated_participant(conn)
        if not participant:
            self.send_json(401, {'error': 'UNAUTHORIZED'})
            return

        p_id = participant['id']
        now = int(time.time())
        with conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO benefit_verification (participant_id, status, note, updated_at)
            VALUES (?, 'PENDING', '혜택 링크 방문 접수', ?)
            ON CONFLICT(participant_id) DO UPDATE SET
                status = 'PENDING',
                updated_at = ?
            """, (p_id, now, now))

        self.send_json(200, {'status': 'PENDING', 'message': 'Gemini 학생 혜택 등록 확인 진행 중입니다.'})

    def handle_analytics_event(self, conn, body):
        event_name = body.get('event_name', 'unknown')
        event_id = body.get('event_id') or uuid.uuid4().hex
        payload = json.dumps(body.get('payload', {}))
        now = int(time.time())
        try:
            with conn:
                cur = conn.cursor()
                cur.execute("""
                INSERT OR IGNORE INTO analytics_events (event_id, participant_id, event_name, payload, created_at)
                VALUES (?, ?, ?, ?, ?)
                """, (event_id, body.get('participant_id'), event_name, payload, now))
        except Exception:
            pass
        self.send_json(200, {'recorded': True})

    # Admin Handlers
    def handle_admin_overview(self, conn):
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM participant")
        total_participants = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM game_session WHERE status = 'FINISHED'")
        total_games = cur.fetchone()[0]

        cur.execute("SELECT status FROM campaign WHERE id = 'gemini_dino_2026'")
        camp_status = cur.fetchone()['status']

        cur.execute("SELECT id, name, category, total_stock, reserved_stock, issued_stock, probability, is_active FROM prize")
        prizes = [dict(r) for r in cur.fetchall()]

        self.send_json(200, {
            'campaign_status': camp_status,
            'total_participants': total_participants,
            'total_games': total_games,
            'prizes': prizes
        })

    def handle_admin_suspicious(self, conn):
        cur = conn.cursor()
        cur.execute("""
        SELECT s.id as session_id, s.score, s.valid_ticks, s.verification_result, p.nickname, p.id as participant_id, p.is_public
        FROM game_session s
        JOIN participant p ON s.participant_id = p.id
        WHERE s.status = 'FINISHED' AND (s.verification_result LIKE '%MISMATCH%' OR s.score > 1500)
        ORDER BY s.score DESC LIMIT 50
        """)
        suspicious = [dict(r) for r in cur.fetchall()]
        self.send_json(200, {'suspicious_sessions': suspicious})

    def handle_admin_campaign_status(self, conn, body):
        new_status = body.get('status')
        if new_status not in ('ACTIVE', 'MAINTENANCE', 'PAUSED', 'ENDED'):
            self.send_json(400, {'error': 'INVALID_STATUS'})
            return
        now = int(time.time())
        with conn:
            cur = conn.cursor()
            cur.execute("UPDATE campaign SET status = ?, updated_at = ? WHERE id = 'gemini_dino_2026'", (new_status, now))
        self.send_json(200, {'status': new_status})

    def handle_admin_ticket_adjust(self, conn, body):
        p_id = body.get('participant_id')
        delta = int(body.get('delta', 0))
        reason = body.get('reason', 'ADMIN_ADJUST')
        now = int(time.time())
        with conn:
            cur = conn.cursor()
            cur.execute("""
            INSERT INTO ticket_ledger (participant_id, delta, source_type, source_id, created_at)
            VALUES (?, ?, 'ADMIN_ADJUST', ?, ?)
            """, (p_id, delta, reason, now))
            new_balance = ticket_service.get_ticket_balance(conn, p_id)
        self.send_json(200, {'success': True, 'new_balance': new_balance})

def run_server():
    db.init_db()
    server_address = ('0.0.0.0', PORT)
    httpd = ThreadingHTTPServer(server_address, DinoJumpHandler)
    httpd.daemon_threads = True
    print(f"==================================================")
    print(f"🦖 Team Gemini Dino Jump Event v1.1 Server Running!")
    print(f"👉 Local URL: http://localhost:{PORT}")
    print(f"👉 LAN IP URL: http://10.50.13.83:{PORT}")
    print(f"👉 Admin Console: http://localhost:{PORT}/admin.html")
    print(f"==================================================")
    httpd.serve_forever()

if __name__ == '__main__':
    run_server()
