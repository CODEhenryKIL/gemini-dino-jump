"""Deterministic v2 replay for coins, hearts, repeat revives, and time-limit finishes."""
import math


UINT32_MASK = 0xFFFFFFFF
COIN_SEED_MASK = 0xC01DC0DE
HEART_SEED_MASK = 0x1EA7BEEF


class PRNG:
    def __init__(self, seed):
        self.state = seed & UINT32_MASK

    def next_float(self):
        self.state = (self.state * 1664525 + 1013904223) & UINT32_MASK
        return (self.state >> 8) / 16777216.0


def _overlaps(a, b):
    return not (
        a["x"] + a["w"] <= b["x"] or a["x"] >= b["x"] + b["w"] or
        a["y"] + a["h"] <= b["y"] or a["y"] >= b["y"] + b["h"]
    )


def _speed_at(constants, time_sec):
    for stage in constants["stages"]:
        if stage["startTime"] <= time_sec < stage["endTime"]:
            if "endSpeed" in stage:
                duration = stage["endTime"] - stage["startTime"]
                ratio = min(1.0, max(0.0, (time_sec - stage["startTime"]) / duration))
                return stage["startSpeed"] + ratio * (stage["endSpeed"] - stage["startSpeed"])
            speed = stage["startSpeed"] + (time_sec - stage["startTime"]) * stage.get("speedIncreasePerSec", 0)
            return min(speed, stage.get("maxSpeed", speed))
    last = constants["stages"][-1]
    return last.get("maxSpeed", last.get("endSpeed", last["startSpeed"]))


def _min_gap_at(constants, time_sec):
    for stage in constants["stages"]:
        if stage["startTime"] <= time_sec < stage["endTime"]:
            return stage["minIntervalSec"]
    return constants["stages"][-1]["minIntervalSec"]


def _available_indices(time_sec):
    if time_sec < 15:
        return (0, 0, 0, 1, 2)
    if time_sec < 30:
        return (0, 1, 2, 0, 1)
    return (0, 1, 2, 3, 4, 0, 3)


def _interval_ticks(prng, minimum, maximum):
    return minimum + math.floor(prng.next_float() * (maximum - minimum + 1))


def _cleared_spawn_x(entity, others, clearance):
    x = entity["x"]
    moved = True
    while moved:
        moved = False
        for other in others:
            vertical = entity["y"] < other["y"] + other["h"] and entity["y"] + entity["h"] > other["y"]
            horizontal = x < other["x"] + other["w"] + clearance and x + entity["w"] + clearance > other["x"]
            if vertical and horizontal:
                x = other["x"] + other["w"] + clearance
                moved = True
    return x


def _normalize_jumps(jumps, submitted_ticks, max_ticks):
    if not isinstance(jumps, list) or len(jumps) > 4096:
        raise ValueError("INVALID_GAME_INPUT")
    jump_map = {}
    for item in jumps:
        if isinstance(item, bool):
            raise ValueError("INVALID_JUMP_TICK")
        if isinstance(item, int):
            tick, high = item, True
        elif isinstance(item, dict):
            tick = item.get("tick")
            high = item.get("high", False)
            if isinstance(tick, bool) or not isinstance(tick, int):
                raise ValueError("INVALID_JUMP_TICK")
            if not isinstance(high, bool):
                raise ValueError("INVALID_JUMP_FLAG")
        else:
            raise ValueError("INVALID_JUMP_TICK")
        if not 0 <= tick <= min(submitted_ticks, max_ticks):
            raise ValueError("INVALID_JUMP_TICK")
        jump_map[tick] = high
    return jump_map


def simulate(constants, seed, jumps, submitted_ticks):
    rules = constants["rules"]
    physics = constants["physics"]
    canvas = constants["canvas"]
    max_ticks = rules["maxTicks"]
    jump_map = _normalize_jumps(jumps, submitted_ticks, max_ticks)

    tick_rate = physics["tickRate"]
    ground_y = canvas["groundY"]
    dino = physics["dino"]
    dino_hb = dino["hitbox"]
    obstacle_types = constants["obstacleTypes"]

    obstacle_prng = PRNG(seed)
    coin_prng = PRNG(seed ^ COIN_SEED_MASK)
    heart_prng = PRNG(seed ^ HEART_SEED_MASK)
    tick = 0
    dino_y = ground_y - dino["height"]
    dino_vy = 0.0
    grounded = True
    active_jump_tick = None
    active_jump_high = False
    jump_buffered_until = -1
    buffered_jump_high = False
    obstacles = []
    items = []
    next_obstacle_time = rules["initialSafeTimeSec"]
    next_coin_tick = rules["coinFirstTick"]
    next_heart_tick = rules["heartFirstTick"]
    last_was_combo = False
    heart = coins = hearts = revives = 0
    invulnerable_until_tick = 0
    end_reason = None
    end_tick = None

    while tick < max_ticks and end_reason is None:
        time_sec = tick / tick_rate
        speed = _speed_at(constants, time_sec)

        if tick in jump_map:
            high = jump_map[tick]
            if grounded:
                dino_vy = physics["jumpVelocityLow"]
                grounded = False
                active_jump_tick = tick
                active_jump_high = high
                jump_buffered_until = -1
            else:
                jump_buffered_until = tick + 6
                buffered_jump_high = high
        if grounded and jump_buffered_until >= tick:
            dino_vy = physics["jumpVelocityLow"]
            grounded = False
            active_jump_tick = tick
            active_jump_high = buffered_jump_high
            jump_buffered_until = -1
        if active_jump_high and not grounded and tick - active_jump_tick == physics["jumpHoldTicks"]:
            dino_vy = physics["jumpVelocityHighBoost"]
        if not grounded:
            dino_vy += physics["gravity"] / tick_rate
            dino_y += dino_vy / tick_rate
            if dino_y >= ground_y - dino["height"]:
                dino_y = ground_y - dino["height"]
                dino_vy = 0.0
                grounded = True
                active_jump_tick = None
                active_jump_high = False

        if time_sec >= next_obstacle_time:
            allowed = _available_indices(time_sec)
            index = min(len(allowed) - 1, math.floor(obstacle_prng.next_float() * len(allowed)))
            definition = obstacle_types[allowed[index]]
            obstacle = {
                "x": canvas["logicalWidth"] + 20,
                "y": ground_y - definition["height"] if definition["altitude"] == "ground" else ground_y - definition["offsetFromGround"],
                "w": definition["width"], "h": definition["height"],
                "hb": definition["hitbox"], "type": definition["type"],
            }
            obstacle["x"] = _cleared_spawn_x(obstacle, items, rules["itemObstacleClearancePx"])
            obstacles.append(obstacle)
            roll = obstacle_prng.next_float()
            extra = obstacle_prng.next_float()
            combo = not last_was_combo and roll < 0.35
            if combo:
                gap = (0.88 if definition["type"] in ("cactus_tall", "cactus_double") else 0.68) + extra * 0.12
            else:
                base = _min_gap_at(constants, time_sec)
                if last_was_combo:
                    base = max(base, 1.15)
                gap = base + extra * 0.45
            last_was_combo = combo
            next_obstacle_time = time_sec + gap

        if tick == next_coin_tick:
            coin = {"kind": "coin", "x": canvas["logicalWidth"] + 20, "y": ground_y - 105, "w": 28, "h": 28}
            coin["x"] = _cleared_spawn_x(coin, obstacles, rules["itemObstacleClearancePx"])
            items.append(coin)
            next_coin_tick += _interval_ticks(coin_prng, rules["coinIntervalMinTicks"], rules["coinIntervalMaxTicks"])
        if tick == next_heart_tick:
            heart_item = {"kind": "heart", "x": canvas["logicalWidth"] + 20, "y": ground_y - 86, "w": 30, "h": 30}
            heart_item["x"] = _cleared_spawn_x(heart_item, obstacles, rules["itemObstacleClearancePx"])
            items.append(heart_item)
            next_heart_tick += _interval_ticks(heart_prng, rules["heartIntervalMinTicks"], rules["heartIntervalMaxTicks"])

        dino_box = {"x": dino["x"] + dino_hb["offsetX"], "y": dino_y + dino_hb["offsetY"], "w": dino_hb["width"], "h": dino_hb["height"]}
        remaining_items = []
        for item in items:
            item["x"] -= speed / tick_rate
            if _overlaps(dino_box, item):
                if item["kind"] == "coin":
                    coins += 1
                else:
                    hearts += 1
                    heart = min(rules["maxHearts"], heart + 1)
            elif item["x"] + item["w"] > -60:
                remaining_items.append(item)
        items = remaining_items

        remaining_obstacles = []
        for obstacle in obstacles:
            obstacle["x"] -= speed / tick_rate
            hb = obstacle["hb"]
            box = {"x": obstacle["x"] + hb["offsetX"], "y": obstacle["y"] + hb["offsetY"], "w": hb["width"], "h": hb["height"]}
            if _overlaps(dino_box, box) and tick >= invulnerable_until_tick:
                if heart == 1:
                    heart = 0
                    revives += 1
                    invulnerable_until_tick = tick + rules["reviveInvulnerabilityTicks"]
                    continue
                end_reason = "COLLISION"
                end_tick = tick
                break
            if obstacle["x"] + obstacle["w"] > -60:
                remaining_obstacles.append(obstacle)
        obstacles = remaining_obstacles
        if end_reason is None:
            tick += 1

    if end_reason is None and tick >= max_ticks:
        end_reason = "TIME_LIMIT"
        end_tick = max_ticks
    revive_penalty = revives * rules.get("revivePenaltyPoints", 0)
    score = max(0, math.floor((end_tick / tick_rate) * rules["pointsPerSecond"]) + coins * rules["coinScore"] - revive_penalty)
    return {
        "score": score,
        "ticks": end_tick,
        "summary": {"coins": coins, "coin_score": coins * rules["coinScore"], "hearts": hearts, "revives": revives,
                    **({"revive_penalty": revive_penalty} if rules.get("revivePenaltyPoints") else {})},
        "end_reason": end_reason,
    }


def verify(constants, seed, jumps, submitted_score, submitted_ticks):
    if isinstance(seed, bool) or not isinstance(seed, int):
        raise ValueError("INVALID_GAME_INPUT")
    if isinstance(submitted_score, bool) or not isinstance(submitted_score, int):
        raise ValueError("INVALID_GAME_INPUT")
    if isinstance(submitted_ticks, bool) or not isinstance(submitted_ticks, int):
        raise ValueError("INVALID_GAME_INPUT")
    if not 0 <= submitted_ticks <= constants["rules"]["maxTicks"] or not 0 <= submitted_score <= 9000:
        raise ValueError("GAME_INPUT_OUT_OF_BOUNDS")

    result = simulate(constants, seed, jumps, submitted_ticks)
    valid = result["ticks"] == submitted_ticks and result["score"] == submitted_score
    if valid:
        reason = "VERIFIED"
    elif result["ticks"] != submitted_ticks:
        reason = f"TICK_MISMATCH: server={result['ticks']}, client={submitted_ticks}"
    else:
        reason = f"SCORE_MISMATCH: server={result['score']}, client={submitted_score}"
    return {
        "valid": valid,
        "score": result["score"],
        "ticks": result["ticks"],
        "reason": reason,
        "summary": result["summary"],
        "end_reason": result["end_reason"],
    }
