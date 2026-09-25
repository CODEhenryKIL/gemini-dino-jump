"""
Deterministic Server-Side Physics Simulator & Anti-Cheat Verifier (v1.2)
Supports:
- 2-Stage Jump Physics (Low Jump: -680, High Jump: -880)
- Low/Tall Cacti and High/Low Flying Birds (Pterodactyls)
- Fast initial start (390 px/s) & 1.2s first obstacle
"""
import math
import json
import os

import game_verifier_v2

CONSTANTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'shared', 'game_constants.json')
V2_CONSTANTS_PATH = os.path.join(os.path.dirname(__file__), '..', 'shared', 'game_constants_v2.json')
with open(CONSTANTS_PATH, 'r', encoding='utf-8') as f:
    CONSTANTS = json.load(f)
with open(V2_CONSTANTS_PATH, 'r', encoding='utf-8') as f:
    V2_CONSTANTS = json.load(f)

TICK_RATE = CONSTANTS['physics']['tickRate'] # 60
DT = 1.0 / TICK_RATE
GROUND_Y = CONSTANTS['canvas']['groundY'] # 490
GRAVITY = CONSTANTS['physics']['gravity'] # 2200

JUMP_VELOCITY_LOW = CONSTANTS['physics']['jumpVelocityLow'] # -680
JUMP_VELOCITY_HIGH_BOOST = CONSTANTS['physics']['jumpVelocityHighBoost'] # -720
HOLD_TICKS = CONSTANTS['physics'].get('jumpHoldTicks', 6) # 6 ticks (100ms)

DINO_X = CONSTANTS['physics']['dino']['x'] # 120
DINO_W = CONSTANTS['physics']['dino']['width'] # 64
DINO_H = CONSTANTS['physics']['dino']['height'] # 72
DINO_HB = CONSTANTS['physics']['dino']['hitbox']

OBSTACLE_TYPES = CONSTANTS['obstacleTypes']
STAGES = CONSTANTS['stages']
SAFE_TIME_SEC = CONSTANTS['rules']['initialSafeTimeSec'] # 1.2

class PRNG:
    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF

    def next_float(self) -> float:
        self.state = (self.state * 1664525 + 1013904223) & 0xFFFFFFFF
        return (self.state >> 8) / 16777216.0

def get_speed_at_time(elapsed_sec: float) -> float:
    for s in STAGES:
        if s['startTime'] <= elapsed_sec < s['endTime']:
            if s['stage'] <= 5:
                duration = s['endTime'] - s['startTime']
                ratio = min(1.0, max(0.0, (elapsed_sec - s['startTime']) / duration))
                return s['startSpeed'] + ratio * (s['endSpeed'] - s['startSpeed'])
            else:
                spd = s['startSpeed'] + (elapsed_sec - s['startTime']) * s['speedIncreasePerSec']
                return min(spd, s['maxSpeed'])
    return 880.0

def get_min_interval_at_time(elapsed_sec: float) -> float:
    for s in STAGES:
        if s['startTime'] <= elapsed_sec < s['endTime']:
            return s['minIntervalSec']
    return 0.65

def get_available_obstacle_indices(elapsed_sec: float) -> list:
    # Stage 1 (0~15s): mostly small cactus, occasionally tall or double for variety
    if elapsed_sec < 15:
        return [0, 0, 0, 1, 2]
    # Stage 2 (15~30s): small, tall, double cacti
    elif elapsed_sec < 30:
        return [0, 1, 2, 0, 1]
    # Stage 3+ (30s+): all obstacles (small, tall, double, low bird, high bird)
    else:
        return [0, 1, 2, 3, 4, 0, 3]

def check_aabb(box1, box2):
    return not (
        box1['x'] + box1['w'] <= box2['x'] or
        box1['x'] >= box2['x'] + box2['w'] or
        box1['y'] + box1['h'] <= box2['y'] or
        box1['y'] >= box2['y'] + box2['h']
    )

def simulate_and_verify(seed: int, jump_ticks: list, submitted_score: int, submitted_ticks: int):
    """
    Simulates game deterministically. jump_ticks can be either [tick, ...] or [{'tick': t, 'high': bool}, ...]
    """
    if type(seed) is not int or not isinstance(jump_ticks, list):
        raise ValueError('INVALID_GAME_INPUT')
    if type(submitted_score) is not int or type(submitted_ticks) is not int:
        raise ValueError('INVALID_GAME_INPUT')
    if not 0 <= submitted_score <= 6000 or not 0 <= submitted_ticks <= 36000 or len(jump_ticks) > 2048:
        raise ValueError('GAME_INPUT_OUT_OF_BOUNDS')
    prng = PRNG(seed)
    dino_y = GROUND_Y - DINO_H
    dino_vy = 0.0
    is_grounded = True
    jump_buffered_until = -1
    buffered_jump_high = False
    active_jump_tick = -999
    active_jump_high = False

    # Normalize jump map: { tick: is_high }
    jump_map = {}
    for item in jump_ticks:
        if isinstance(item, dict):
            tick = item['tick']
            if isinstance(tick, bool) or not isinstance(tick, int) or not 0 <= tick <= submitted_ticks:
                raise ValueError('INVALID_JUMP_TICK')
            high = item.get('high', False)
            if not isinstance(high, bool):
                raise ValueError('INVALID_JUMP_FLAG')
            jump_map[tick] = high
        elif isinstance(item, int) and not isinstance(item, bool):
            if not 0 <= item <= submitted_ticks:
                raise ValueError('INVALID_JUMP_TICK')
            jump_map[item] = True # default high if unspecified
        else:
            raise ValueError('INVALID_JUMP_TICK')

    obstacles = []
    next_spawn_time = SAFE_TIME_SEC
    last_was_combo = False

    max_sim_ticks = min(36000, max(submitted_ticks + 120, 60 * 10))
    collision_tick = -1

    for tick in range(max_sim_ticks):
        time_sec = tick * DT
        speed = get_speed_at_time(time_sec)

        # 1. Handle jump input
        if tick in jump_map:
            is_high = jump_map[tick]
            if is_grounded:
                dino_vy = JUMP_VELOCITY_LOW
                is_grounded = False
                active_jump_tick = tick
                active_jump_high = is_high
                jump_buffered_until = -1
            else:
                jump_buffered_until = tick + 6
                buffered_jump_high = is_high

        if is_grounded and jump_buffered_until >= tick:
            dino_vy = JUMP_VELOCITY_LOW
            is_grounded = False
            active_jump_tick = tick
            active_jump_high = buffered_jump_high
            jump_buffered_until = -1

        # Check high jump boost at tick + HOLD_TICKS
        if active_jump_high and not is_grounded and (tick - active_jump_tick == HOLD_TICKS):
            dino_vy = JUMP_VELOCITY_HIGH_BOOST

        # 2. Physics update for Dino
        if not is_grounded:
            dino_vy += GRAVITY * DT
            dino_y += dino_vy * DT
            if dino_y >= GROUND_Y - DINO_H:
                dino_y = GROUND_Y - DINO_H
                dino_vy = 0.0
                is_grounded = True
                active_jump_high = False

        # 3. Obstacle Spawning (Synchronized with client PRNG)
        if time_sec >= next_spawn_time:
            allowed_indices = get_available_obstacle_indices(time_sec)
            rand_pick = int(prng.next_float() * len(allowed_indices))
            if rand_pick >= len(allowed_indices):
                rand_pick = len(allowed_indices) - 1
            obs_type = OBSTACLE_TYPES[allowed_indices[rand_pick]]

            obs_x = CONSTANTS['canvas']['logicalWidth'] + 20
            if obs_type.get('altitude') == 'ground':
                obs_y = GROUND_Y - obs_type['height']
            else:
                obs_offset = obs_type.get('offsetFromGround', 85 if obs_type['type'] == 'bird_low' else 140)
                obs_y = GROUND_Y - obs_offset

            obstacles.append({
                'x': obs_x,
                'y': obs_y,
                'w': obs_type['width'],
                'h': obs_type['height'],
                'hb': obs_type['hitbox'],
                'type': obs_type['type']
            })

            # Consecutive Rhythm Combo & Randomness (always consume 2 floats for deterministic sync)
            rand_roll = prng.next_float()
            rand_extra = prng.next_float()

            is_combo = (not last_was_combo) and (rand_roll < 0.35)
            if is_combo:
                # Consecutive jump situation!
                if obs_type['type'] in ['cactus_tall', 'cactus_double']:
                    # Requires landing from high jump
                    gap = 0.88 + rand_extra * 0.12 # 0.88s ~ 1.00s
                else:
                    # Landing from low jump (~0.62s)
                    gap = 0.68 + rand_extra * 0.12 # 0.68s ~ 0.80s
                last_was_combo = True
            else:
                base_interval = get_min_interval_at_time(time_sec)
                if last_was_combo:
                    base_interval = max(base_interval, 1.15)
                gap = base_interval + rand_extra * 0.45
                last_was_combo = False

            next_spawn_time = time_sec + gap

        # 4. Collision check
        dino_box = {
            'x': DINO_X + DINO_HB['offsetX'],
            'y': dino_y + DINO_HB['offsetY'],
            'w': DINO_HB['width'],
            'h': DINO_HB['height']
        }

        collided = False
        remaining = []
        for obs in obstacles:
            obs['x'] -= speed * DT
            obs_box = {
                'x': obs['x'] + obs['hb']['offsetX'],
                'y': obs['y'] + obs['hb']['offsetY'],
                'w': obs['hb']['width'],
                'h': obs['hb']['height']
            }

            if check_aabb(dino_box, obs_box):
                collided = True
                collision_tick = tick
                break

            if obs['x'] + obs['w'] > -50:
                remaining.append(obs)

        obstacles = remaining
        if collided:
            break

    if collision_tick < 0:
        # An unfinished replay cannot prove a game-over or award ranking/draw rights.
        return False, 0, 0, 'NO_COLLISION'

    calculated_score = int(math.floor((collision_tick / TICK_RATE) * CONSTANTS['rules']['pointsPerSecond']))

    tick_diff = abs(collision_tick - submitted_ticks)
    score_diff = abs(calculated_score - submitted_score)

    if tick_diff <= 15 and score_diff <= 5:
        return True, calculated_score, collision_tick, "VERIFIED"
    return False, calculated_score, collision_tick, f"SCORE_MISMATCH: server={calculated_score}, client={submitted_score}"


def verify_game(version: str, seed: int, jumps: list, score: int, ticks: int):
    """Versioned verifier contract. Legacy callers keep using simulate_and_verify()."""
    if version == "2.0.0":
        return game_verifier_v2.verify(V2_CONSTANTS, seed, jumps, score, ticks)
    if version in (None, "", "1.2.0"):
        valid, verified_score, verified_ticks, reason = simulate_and_verify(seed, jumps, score, ticks)
        return {
            "valid": valid,
            "score": verified_score,
            "ticks": verified_ticks,
            "reason": reason,
            "summary": {"coins": 0, "coin_score": 0, "hearts": 0, "revives": 0},
            "end_reason": "COLLISION" if reason != "NO_COLLISION" else None,
        }
    raise ValueError("UNSUPPORTED_GAME_VERSION")
