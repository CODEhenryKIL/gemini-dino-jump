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

function speedAt(timeSec) {
  const stages = [
    [0, 15, 390, 450], [15, 30, 450, 530], [30, 45, 530, 620],
    [45, 60, 620, 710], [60, 75, 710, 800],
  ];
  for (const [start, end, low, high] of stages) {
    if (timeSec >= start && timeSec < end) return low + ((timeSec - start) / (end - start)) * (high - low);
  }
  return Math.min(800 + Math.max(0, timeSec - 75) * 4, 880);
}

function minGapAt(timeSec) {
  if (timeSec < 15) return 0.95;
  if (timeSec < 30) return 0.88;
  if (timeSec < 45) return 0.80;
  if (timeSec < 60) return 0.74;
  if (timeSec < 75) return 0.68;
  return 0.62;
}

function availableObstacleIndices(timeSec) {
  if (timeSec < 15) return [0, 0, 0, 1, 2];
  if (timeSec < 30) return [0, 1, 2, 0, 1];
  return [0, 1, 2, 3, 4, 0, 3];
}

function intervalTicks(prng, minimum, maximum) {
  return minimum + Math.floor(prng.nextFloat() * (maximum - minimum + 1));
}

function clearedSpawnX(entity, others) {
  let x = entity.x;
  let moved = true;
  while (moved) {
    moved = false;
    for (const other of others) {
      const vertical = entity.y < other.y + other.h && entity.y + entity.h > other.y;
      const horizontal = x < other.x + other.w + V2_RULES.itemObstacleClearancePx &&
        x + entity.w + V2_RULES.itemObstacleClearancePx > other.x;
      if (vertical && horizontal) {
        x = other.x + other.w + V2_RULES.itemObstacleClearancePx;
        moved = true;
      }
    }
  }
  return x;
}

export class V2GameSimulation {
  constructor(seed) { this.reset(seed); }

  reset(seed) {
    if (!Number.isInteger(seed)) throw new TypeError('seed must be an integer');
    this.seed = seed;
    this.obstaclePrng = new V2PRNG(seed);
    this.coinPrng = new V2PRNG((seed ^ 0xC01DC0DE) >>> 0);
    this.heartPrng = new V2PRNG((seed ^ 0x1EA7BEEF) >>> 0);
    this.currentTick = 0;
    this.score = 0;
    this.dinoY = V2_RULES.groundY - V2_RULES.dinoH;
    this.dinoVy = 0;
    this.isGrounded = true;
    this.activeJumpTick = null;
    this.activeJumpHigh = false;
    this.jumpBufferedUntil = -1;
    this.bufferedJumpHigh = false;
    this.obstacles = [];
    this.items = [];
    this.nextObstacleTime = V2_RULES.initialSafeTimeSec;
    this.nextCoinTick = V2_RULES.coinFirstTick;
    this.nextHeartTick = V2_RULES.heartFirstTick;
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
      this.dinoVy = V2_RULES.jumpVelocityLow;
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
    const timeSec = tick / V2_RULES.tickRate;
    const speed = speedAt(timeSec);
    const events = [];

    if (input.jump) this.pressJump(Boolean(input.high));
    if (this.isGrounded && this.jumpBufferedUntil >= tick) {
      this.dinoVy = V2_RULES.jumpVelocityLow;
      this.isGrounded = false;
      this.activeJumpTick = tick;
      this.activeJumpHigh = this.bufferedJumpHigh;
      this.jumpBufferedUntil = -1;
      this.jumpTicks.push({ tick, high: this.activeJumpHigh });
    }
    if (input.holding && !this.isGrounded && !this.activeJumpHigh && tick - this.activeJumpTick === V2_RULES.holdTicks) {
      this.activeJumpHigh = true;
      for (let index = this.jumpTicks.length - 1; index >= 0; index--) {
        if (this.jumpTicks[index].tick === this.activeJumpTick) {
          this.jumpTicks[index].high = true;
          break;
        }
      }
    }
    if (this.activeJumpHigh && !this.isGrounded && tick - this.activeJumpTick === V2_RULES.holdTicks) {
      this.dinoVy = V2_RULES.jumpVelocityHighBoost;
    }
    if (!this.isGrounded) {
      this.dinoVy += V2_RULES.gravity / V2_RULES.tickRate;
      this.dinoY += this.dinoVy / V2_RULES.tickRate;
      if (this.dinoY >= V2_RULES.groundY - V2_RULES.dinoH) {
        this.dinoY = V2_RULES.groundY - V2_RULES.dinoH;
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
        x: V2_RULES.width + 20,
        y: def.altitude === 'ground' ? V2_RULES.groundY - def.h : V2_RULES.groundY - def.offsetFromGround,
        w: def.w, h: def.h, hb: def.hb, type: def.type, altitude: def.altitude,
      };
      obstacle.x = clearedSpawnX(obstacle, this.items);
      this.obstacles.push(obstacle);
      const roll = this.obstaclePrng.nextFloat();
      const extra = this.obstaclePrng.nextFloat();
      const combo = !this.lastWasCombo && roll < 0.35;
      let gap;
      if (combo) gap = (def.type === 'cactus_tall' || def.type === 'cactus_double' ? 0.88 : 0.68) + extra * 0.12;
      else {
        let base = minGapAt(timeSec);
        if (this.lastWasCombo) base = Math.max(base, 1.15);
        gap = base + extra * 0.45;
      }
      this.lastWasCombo = combo;
      this.nextObstacleTime = timeSec + gap;
    }

    if (tick === this.nextCoinTick) {
      const coin = { kind: 'coin', x: V2_RULES.width + 20, y: V2_RULES.groundY - 105, w: 28, h: 28 };
      coin.x = clearedSpawnX(coin, this.obstacles);
      this.items.push(coin);
      this.nextCoinTick += intervalTicks(this.coinPrng, V2_RULES.coinIntervalMinTicks, V2_RULES.coinIntervalMaxTicks);
    }
    if (tick === this.nextHeartTick) {
      const heart = { kind: 'heart', x: V2_RULES.width + 20, y: V2_RULES.groundY - 86, w: 30, h: 30 };
      heart.x = clearedSpawnX(heart, this.obstacles);
      this.items.push(heart);
      this.nextHeartTick += intervalTicks(this.heartPrng, V2_RULES.heartIntervalMinTicks, V2_RULES.heartIntervalMaxTicks);
    }

    const dinoBox = { x: V2_RULES.dinoX + 10, y: this.dinoY + 8, w: 44, h: 58 };
    const remainingItems = [];
    for (const item of this.items) {
      item.x -= speed / V2_RULES.tickRate;
      if (overlaps(dinoBox, item)) {
        if (item.kind === 'coin') {
          this.coins += 1;
          events.push({ type: 'coin', tick });
        } else {
          this.hearts += 1;
          if (this.heart < V2_RULES.maxHearts) this.heart = 1;
          events.push({ type: 'heart', tick, stored: this.heart });
        }
      } else if (item.x + item.w > -60) remainingItems.push(item);
    }
    this.items = remainingItems;

    const remainingObstacles = [];
    let terminalCollision = false;
    for (const obstacle of this.obstacles) {
      obstacle.x -= speed / V2_RULES.tickRate;
      const box = { x: obstacle.x + obstacle.hb.offsetX, y: obstacle.y + obstacle.hb.offsetY, w: obstacle.hb.width, h: obstacle.hb.height };
      if (overlaps(dinoBox, box) && tick >= this.invulnerableUntilTick) {
        if (this.heart === 1) {
          this.heart = 0;
          this.revives += 1;
          this.invulnerableUntilTick = tick + V2_RULES.reviveInvulnerabilityTicks;
          this.overlayUntilTick = tick + V2_RULES.reviveOverlayTicks;
          events.push({ type: 'revive', tick, invulnerableUntilTick: this.invulnerableUntilTick });
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
      if (this.currentTick >= V2_RULES.maxTicks) {
        this.ended = true;
        this.endReason = 'TIME_LIMIT';
        this.endTick = V2_RULES.maxTicks;
        events.push({ type: 'time_limit', tick: V2_RULES.maxTicks });
      }
    }
    this.score = Math.floor(((this.endTick ?? this.currentTick) / V2_RULES.tickRate) * V2_RULES.pointsPerSecond) + this.coins * V2_RULES.coinScore;
    return events;
  }

  result() {
    return {
      version: V2_RULES.version,
      score: this.score,
      ticks: this.endTick ?? this.currentTick,
      jump_ticks: this.jumpTicks.map((jump) => ({ ...jump })),
      end_reason: this.endReason,
      summary: { coins: this.coins, coin_score: this.coins * V2_RULES.coinScore, hearts: this.hearts, revives: this.revives },
    };
  }
}

export function simulateV2(seed, jumps, untilTicks = V2_RULES.maxTicks) {
  const simulation = new V2GameSimulation(seed);
  const jumpMap = new Map(jumps.map((jump) => [typeof jump === 'number' ? jump : jump.tick, typeof jump === 'number' ? true : jump.high]));
  while (!simulation.ended && simulation.currentTick <= untilTicks) {
    const high = jumpMap.get(simulation.currentTick);
    simulation.step({ jump: jumpMap.has(simulation.currentTick), high });
  }
  return simulation.result();
}
