export const V2_RULES = Object.freeze({
  version: '2.0.0', tickRate: 60, maxTicks: 36000,
  width: 960, groundY: 490, gravity: 2200,
  jumpVelocityLow: -680, jumpVelocityHighBoost: -720, holdTicks: 6,
  dinoX: 120, dinoW: 64, dinoH: 72,
  dinoHitbox: Object.freeze({ offsetX: 10, offsetY: 8, width: 44, height: 58 }),
  pointsPerSecond: 10, initialSafeTimeSec: 1.2,
  coinScore: 10, coinFirstTick: 180, coinIntervalMinTicks: 120, coinIntervalMaxTicks: 240,
  heartFirstTick: 1200, heartIntervalMinTicks: 1500, heartIntervalMaxTicks: 2100,
  reviveInvulnerabilityTicks: 90, reviveOverlayTicks: 24, maxHearts: 1,
  itemObstacleClearancePx: 24,
});

export const V21_RULES = Object.freeze({
  ...V2_RULES,
  version: '2.1.0',
  revivePenaltyPoints: 100,
});

const V2_STAGES = Object.freeze([
  Object.freeze({ stage: 1, startTime: 0, endTime: 15, startSpeed: 390, endSpeed: 450, minIntervalSec: 0.95, title: 'STAGE 1', subtitle: '상쾌한 낮, 가볍게 출발!' }),
  Object.freeze({ stage: 2, startTime: 15, endTime: 30, startSpeed: 450, endSpeed: 530, minIntervalSec: 0.88, title: 'STAGE 2', subtitle: '기울어지는 오후 햇살' }),
  Object.freeze({ stage: 3, startTime: 30, endTime: 45, startSpeed: 530, endSpeed: 620, minIntervalSec: 0.80, title: 'STAGE 3', subtitle: '황금빛 노을 & 새 출현!' }),
  Object.freeze({ stage: 4, startTime: 45, endTime: 60, startSpeed: 620, endSpeed: 710, minIntervalSec: 0.74, title: 'STAGE 4', subtitle: '보랏빛 황혼 매직아워' }),
  Object.freeze({ stage: 5, startTime: 60, endTime: 75, startSpeed: 710, endSpeed: 800, minIntervalSec: 0.68, title: 'STAGE 5', subtitle: '별빛과 달빛의 밤하늘' }),
  Object.freeze({ stage: 6, startTime: 75, endTime: 999999, startSpeed: 800, speedIncreasePerSec: 4, maxSpeed: 880, maxSpeedTime: 95, minIntervalSec: 0.62, title: 'STAGE 6', subtitle: '신비로운 제미나이 은하수' }),
]);

export const V21_STAGES = Object.freeze([
  ...V2_STAGES.slice(0, 5),
  Object.freeze({ stage: 6, startTime: 75, endTime: 90, startSpeed: 800, endSpeed: 880, minIntervalSec: 0.62, title: 'STAGE 6', subtitle: '신비로운 제미나이 은하수' }),
  Object.freeze({ stage: 7, startTime: 90, endTime: 105, startSpeed: 880, endSpeed: 940, minIntervalSec: 0.58, title: 'STAGE 7', subtitle: '빨라지는 은하 질주' }),
  Object.freeze({ stage: 8, startTime: 105, endTime: 120, startSpeed: 940, endSpeed: 1080, minIntervalSec: 0.50, title: 'STAGE 8', subtitle: '초고속 별빛 구간' }),
  Object.freeze({ stage: 9, startTime: 120, endTime: 135, startSpeed: 1080, endSpeed: 1200, minIntervalSec: 0.44, title: 'STAGE 9', subtitle: '한계에 가까운 질주' }),
  Object.freeze({ stage: 10, startTime: 135, endTime: 999999, startSpeed: 1200, speedIncreasePerSec: 8, maxSpeed: 1320, maxSpeedTime: 150, minIntervalSec: 0.40, title: 'STAGE 10', subtitle: '최종 극한 구간' }),
]);

const OBSTACLE_TYPES = Object.freeze([
  { type: 'cactus_small', w: 36, h: 48, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 24, height: 42 } },
  { type: 'cactus_tall', w: 44, h: 84, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 32, height: 76 } },
  { type: 'cactus_double', w: 68, h: 64, altitude: 'ground', hb: { offsetX: 6, offsetY: 4, width: 56, height: 56 } },
  { type: 'bird_low', w: 52, h: 40, altitude: 'air_low', offsetFromGround: 85, hb: { offsetX: 4, offsetY: 4, width: 44, height: 32 } },
  { type: 'bird_high', w: 52, h: 40, altitude: 'air_high', offsetFromGround: 140, hb: { offsetX: 4, offsetY: 4, width: 44, height: 32 } },
]);

export class V2PRNG {
  constructor(seed) { this.state = seed >>> 0; }
  nextFloat() {
    this.state = (Math.imul(this.state, 1664525) + 1013904223) >>> 0;
    return (this.state >>> 8) / 16777216.0;
  }
}

function overlaps(a, b) {
  return !(a.x + a.w <= b.x || a.x >= b.x + b.w || a.y + a.h <= b.y || a.y >= b.y + b.h);
}

function speedAt(timeSec, stages) {
  const stage = stages.find(({ startTime, endTime }) => timeSec >= startTime && timeSec < endTime) || stages.at(-1);
  if (stage.endSpeed != null) {
    return stage.startSpeed + ((timeSec - stage.startTime) / (stage.endTime - stage.startTime)) * (stage.endSpeed - stage.startSpeed);
  }
  return Math.min(stage.startSpeed + Math.max(0, timeSec - stage.startTime) * stage.speedIncreasePerSec, stage.maxSpeed);
}

function minGapAt(timeSec, stages) {
  return (stages.find(({ startTime, endTime }) => timeSec >= startTime && timeSec < endTime) || stages.at(-1)).minIntervalSec;
}

function availableObstacleIndices(timeSec) {
  if (timeSec < 15) return [0, 0, 0, 1, 2];
  if (timeSec < 30) return [0, 1, 2, 0, 1];
  return [0, 1, 2, 3, 4, 0, 3];
}

function intervalTicks(prng, minimum, maximum) {
  return minimum + Math.floor(prng.nextFloat() * (maximum - minimum + 1));
}

function clearedSpawnX(entity, others, clearancePx) {
  let x = entity.x;
  let moved = true;
  while (moved) {
    moved = false;
    for (const other of others) {
      const vertical = entity.y < other.y + other.h && entity.y + entity.h > other.y;
      const horizontal = x < other.x + other.w + clearancePx &&
        x + entity.w + clearancePx > other.x;
      if (vertical && horizontal) {
        x = other.x + other.w + clearancePx;
        moved = true;
      }
    }
  }
  return x;
}

export class V2GameSimulation {
  constructor(seed, version = V2_RULES.version) {
    if (version !== V2_RULES.version && version !== V21_RULES.version) throw new RangeError(`unsupported game version: ${version}`);
    this.rules = version === V21_RULES.version ? V21_RULES : V2_RULES;
    this.stages = version === V21_RULES.version ? V21_STAGES : V2_STAGES;
    this.reset(seed);
  }

  reset(seed) {
    if (!Number.isInteger(seed)) throw new TypeError('seed must be an integer');
    this.seed = seed;
    this.obstaclePrng = new V2PRNG(seed);
    this.coinPrng = new V2PRNG((seed ^ 0xC01DC0DE) >>> 0);
    this.heartPrng = new V2PRNG((seed ^ 0x1EA7BEEF) >>> 0);
    this.currentTick = 0;
    this.score = 0;
    this.dinoY = this.rules.groundY - this.rules.dinoH;
    this.dinoVy = 0;
    this.isGrounded = true;
    this.activeJumpTick = null;
    this.activeJumpHigh = false;
    this.jumpBufferedUntil = -1;
    this.bufferedJumpHigh = false;
    this.obstacles = [];
    this.items = [];
    this.nextObstacleTime = this.rules.initialSafeTimeSec;
    this.nextCoinTick = this.rules.coinFirstTick;
    this.nextHeartTick = this.rules.heartFirstTick;
    this.lastWasCombo = false;
    this.heart = 0;
    this.coins = 0;
    this.hearts = 0;
    this.revives = 0;
    this.invulnerableUntilTick = 0;
    this.overlayUntilTick = 0;
    this.ended = false;
    this.endReason = null;
    this.endTick = null;
    this.jumpTicks = [];
  }

  pressJump(high = false) {
    if (this.ended) return false;
    if (this.isGrounded) {
      this.dinoVy = this.rules.jumpVelocityLow;
      this.isGrounded = false;
      this.activeJumpTick = this.currentTick;
      this.activeJumpHigh = Boolean(high);
      this.jumpBufferedUntil = -1;
      const jump = { tick: this.currentTick, high: Boolean(high) };
      this.jumpTicks.push(jump);
      return true;
    }
    this.jumpBufferedUntil = this.currentTick + 6;
    this.bufferedJumpHigh = Boolean(high);
    return false;
  }

  step(input = {}) {
    if (this.ended) return [];
    const tick = this.currentTick;
    const timeSec = tick / this.rules.tickRate;
    const speed = speedAt(timeSec, this.stages);
    const events = [];

    if (input.jump) this.pressJump(Boolean(input.high));
    if (this.isGrounded && this.jumpBufferedUntil >= tick) {
      this.dinoVy = this.rules.jumpVelocityLow;
      this.isGrounded = false;
      this.activeJumpTick = tick;
      this.activeJumpHigh = this.bufferedJumpHigh;
      this.jumpBufferedUntil = -1;
      this.jumpTicks.push({ tick, high: this.activeJumpHigh });
    }
    if (input.holding && !this.isGrounded && !this.activeJumpHigh && tick - this.activeJumpTick === this.rules.holdTicks) {
      this.activeJumpHigh = true;
      for (let index = this.jumpTicks.length - 1; index >= 0; index--) {
        if (this.jumpTicks[index].tick === this.activeJumpTick) {
          this.jumpTicks[index].high = true;
          break;
        }
      }
    }
    if (this.activeJumpHigh && !this.isGrounded && tick - this.activeJumpTick === this.rules.holdTicks) {
      this.dinoVy = this.rules.jumpVelocityHighBoost;
    }
    if (!this.isGrounded) {
      this.dinoVy += this.rules.gravity / this.rules.tickRate;
      this.dinoY += this.dinoVy / this.rules.tickRate;
      if (this.dinoY >= this.rules.groundY - this.rules.dinoH) {
        this.dinoY = this.rules.groundY - this.rules.dinoH;
        this.dinoVy = 0;
        this.isGrounded = true;
        this.activeJumpTick = null;
        this.activeJumpHigh = false;
      }
    }

    if (timeSec >= this.nextObstacleTime) {
      const allowed = availableObstacleIndices(timeSec);
      const index = Math.min(allowed.length - 1, Math.floor(this.obstaclePrng.nextFloat() * allowed.length));
      const def = OBSTACLE_TYPES[allowed[index]];
      const obstacle = {
        x: this.rules.width + 20,
        y: def.altitude === 'ground' ? this.rules.groundY - def.h : this.rules.groundY - def.offsetFromGround,
        w: def.w, h: def.h, hb: def.hb, type: def.type, altitude: def.altitude,
      };
      obstacle.x = clearedSpawnX(obstacle, this.items, this.rules.itemObstacleClearancePx);
      this.obstacles.push(obstacle);
      const roll = this.obstaclePrng.nextFloat();
      const extra = this.obstaclePrng.nextFloat();
      const combo = !this.lastWasCombo && roll < 0.35;
      let gap;
      if (combo) gap = (def.type === 'cactus_tall' || def.type === 'cactus_double' ? 0.88 : 0.68) + extra * 0.12;
      else {
        let base = minGapAt(timeSec, this.stages);
        if (this.lastWasCombo) base = Math.max(base, 1.15);
        gap = base + extra * 0.45;
      }
      this.lastWasCombo = combo;
      this.nextObstacleTime = timeSec + gap;
    }

    if (tick === this.nextCoinTick) {
      const coin = { kind: 'coin', x: this.rules.width + 20, y: this.rules.groundY - 105, w: 28, h: 28 };
      coin.x = clearedSpawnX(coin, this.obstacles, this.rules.itemObstacleClearancePx);
      this.items.push(coin);
      this.nextCoinTick += intervalTicks(this.coinPrng, this.rules.coinIntervalMinTicks, this.rules.coinIntervalMaxTicks);
    }
    if (tick === this.nextHeartTick) {
      const heart = { kind: 'heart', x: this.rules.width + 20, y: this.rules.groundY - 86, w: 30, h: 30 };
      heart.x = clearedSpawnX(heart, this.obstacles, this.rules.itemObstacleClearancePx);
      this.items.push(heart);
      this.nextHeartTick += intervalTicks(this.heartPrng, this.rules.heartIntervalMinTicks, this.rules.heartIntervalMaxTicks);
    }

    const dinoBox = { x: this.rules.dinoX + 10, y: this.dinoY + 8, w: 44, h: 58 };
    const remainingItems = [];
    for (const item of this.items) {
      item.x -= speed / this.rules.tickRate;
      if (overlaps(dinoBox, item)) {
        if (item.kind === 'coin') {
          this.coins += 1;
          events.push({ type: 'coin', tick });
        } else {
          this.hearts += 1;
          if (this.heart < this.rules.maxHearts) this.heart = 1;
          events.push({ type: 'heart', tick, stored: this.heart });
        }
      } else if (item.x + item.w > -60) remainingItems.push(item);
    }
    this.items = remainingItems;

    const remainingObstacles = [];
    let terminalCollision = false;
    for (const obstacle of this.obstacles) {
      obstacle.x -= speed / this.rules.tickRate;
      const box = { x: obstacle.x + obstacle.hb.offsetX, y: obstacle.y + obstacle.hb.offsetY, w: obstacle.hb.width, h: obstacle.hb.height };
      if (overlaps(dinoBox, box) && tick >= this.invulnerableUntilTick) {
        if (this.heart === 1) {
          this.heart = 0;
          this.revives += 1;
          this.invulnerableUntilTick = tick + this.rules.reviveInvulnerabilityTicks;
          this.overlayUntilTick = tick + this.rules.reviveOverlayTicks;
          const reviveEvent = { type: 'revive', tick, invulnerableUntilTick: this.invulnerableUntilTick };
          if (this.rules.version === V21_RULES.version) {
            reviveEvent.penalty = this.rules.revivePenaltyPoints;
            reviveEvent.totalPenalty = this.revives * this.rules.revivePenaltyPoints;
          }
          events.push(reviveEvent);
          continue;
        }
        terminalCollision = true;
        events.push({ type: 'collision', tick });
        break;
      }
      if (obstacle.x + obstacle.w > -60) remainingObstacles.push(obstacle);
    }
    this.obstacles = remainingObstacles;

    if (terminalCollision) {
      this.ended = true;
      this.endReason = 'COLLISION';
      this.endTick = tick;
    } else {
      this.currentTick += 1;
      if (this.currentTick >= this.rules.maxTicks) {
        this.ended = true;
        this.endReason = 'TIME_LIMIT';
        this.endTick = this.rules.maxTicks;
        events.push({ type: 'time_limit', tick: this.rules.maxTicks });
      }
    }
    const rawScore = Math.floor(((this.endTick ?? this.currentTick) / this.rules.tickRate) * this.rules.pointsPerSecond) + this.coins * this.rules.coinScore;
    const revivePenalty = this.rules.version === V21_RULES.version ? this.revives * this.rules.revivePenaltyPoints : 0;
    this.score = Math.max(0, rawScore - revivePenalty);
    return events;
  }

  result() {
    return {
      version: this.rules.version,
      score: this.score,
      ticks: this.endTick ?? this.currentTick,
      jump_ticks: this.jumpTicks.map((jump) => ({ ...jump })),
      end_reason: this.endReason,
      summary: {
        coins: this.coins,
        coin_score: this.coins * this.rules.coinScore,
        hearts: this.hearts,
        revives: this.revives,
        ...(this.rules.version === V21_RULES.version ? { revive_penalty: this.revives * this.rules.revivePenaltyPoints } : {}),
      },
    };
  }
}

export function simulateV2(seed, jumps, untilTicks = V2_RULES.maxTicks, version = V2_RULES.version) {
  const simulation = new V2GameSimulation(seed, version);
  const jumpMap = new Map(jumps.map((jump) => [typeof jump === 'number' ? jump : jump.tick, typeof jump === 'number' ? true : jump.high]));
  while (!simulation.ended && simulation.currentTick <= untilTicks) {
    const high = jumpMap.get(simulation.currentTick);
    simulation.step({ jump: jumpMap.has(simulation.currentTick), high });
  }
  return simulation.result();
}
