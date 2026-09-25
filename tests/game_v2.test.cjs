const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/game/simulation.js'), 'utf8')
  .replace(/export\s+(?=(const|class|function)\s)/g, '');
const context = {};
vm.runInNewContext(`${source}\nglobalThis.V2_RULES = V2_RULES; globalThis.V2GameSimulation = V2GameSimulation; globalThis.OBSTACLE_TYPES = OBSTACLE_TYPES;`, context);

function obstacleAtDino() {
  return {
    x: 124, y: 442, w: 36, h: 48, type: 'cactus_small', altitude: 'ground',
    hb: { offsetX: 6, offsetY: 4, width: 24, height: 42 },
  };
}

test('shared v2 constants match the browser simulation contract', () => {
  const constants = JSON.parse(fs.readFileSync(path.join(root, 'shared/game_constants.json'), 'utf8'));
  const frozen = JSON.parse(fs.readFileSync(path.join(root, 'shared/game_constants_v2.json'), 'utf8'));
  assert.deepEqual(frozen, constants, 'the frozen v2 verifier constants start as an exact copy');
  assert.equal(constants.version, context.V2_RULES.version);
  assert.deepEqual(JSON.parse(JSON.stringify(context.OBSTACLE_TYPES)), constants.obstacleTypes.map((obstacle) => ({
    type: obstacle.type, w: obstacle.width, h: obstacle.height, altitude: obstacle.altitude,
    ...(obstacle.offsetFromGround == null ? {} : { offsetFromGround: obstacle.offsetFromGround }),
    hb: obstacle.hitbox,
  })));
  assert.deepEqual(JSON.parse(JSON.stringify({
    tickRate: context.V2_RULES.tickRate, width: context.V2_RULES.width, groundY: context.V2_RULES.groundY,
    gravity: context.V2_RULES.gravity, jumpVelocityLow: context.V2_RULES.jumpVelocityLow,
    jumpVelocityHighBoost: context.V2_RULES.jumpVelocityHighBoost, holdTicks: context.V2_RULES.holdTicks,
    dinoX: context.V2_RULES.dinoX, dinoW: context.V2_RULES.dinoW, dinoH: context.V2_RULES.dinoH,
    dinoHitbox: context.V2_RULES.dinoHitbox,
  })), {
    tickRate: constants.physics.tickRate, width: constants.canvas.logicalWidth, groundY: constants.canvas.groundY,
    gravity: constants.physics.gravity, jumpVelocityLow: constants.physics.jumpVelocityLow,
    jumpVelocityHighBoost: constants.physics.jumpVelocityHighBoost, holdTicks: constants.physics.jumpHoldTicks,
    dinoX: constants.physics.dino.x, dinoW: constants.physics.dino.width, dinoH: constants.physics.dino.height,
    dinoHitbox: constants.physics.dino.hitbox,
  });
  for (const [jsonKey, jsKey] of [
    ['maxTicks', 'maxTicks'], ['coinScore', 'coinScore'], ['coinFirstTick', 'coinFirstTick'],
    ['coinIntervalMinTicks', 'coinIntervalMinTicks'], ['coinIntervalMaxTicks', 'coinIntervalMaxTicks'],
    ['heartFirstTick', 'heartFirstTick'], ['heartIntervalMinTicks', 'heartIntervalMinTicks'],
    ['heartIntervalMaxTicks', 'heartIntervalMaxTicks'], ['reviveInvulnerabilityTicks', 'reviveInvulnerabilityTicks'],
    ['reviveOverlayTicks', 'reviveOverlayTicks'], ['maxHearts', 'maxHearts'],
    ['itemObstacleClearancePx', 'itemObstacleClearancePx'],
  ]) assert.equal(constants.rules[jsonKey], context.V2_RULES[jsKey], jsonKey);
});

test('seeded live items keep deterministic clearance from present and future obstacles', () => {
  for (const seed of [1, 4, 7, 42, 999]) {
    const sim = new context.V2GameSimulation(seed);
    sim.invulnerableUntilTick = context.V2_RULES.maxTicks + 1;
    for (let tick = 0; tick < 5000; tick++) {
      sim.step();
      for (const item of sim.items) for (const obstacle of sim.obstacles) {
        const vertical = item.y < obstacle.y + obstacle.h && item.y + item.h > obstacle.y;
        if (!vertical) continue;
        const epsilon = 1e-6;
        const separated = item.x + item.w + context.V2_RULES.itemObstacleClearancePx <= obstacle.x + epsilon ||
          obstacle.x + obstacle.w + context.V2_RULES.itemObstacleClearancePx <= item.x + epsilon;
        assert.equal(separated, true, `seed ${seed} tick ${tick} ${item.kind}/${obstacle.type}`);
      }
    }
  }
});

test('seeded item schedules use the draft 3s/2-4s and 20s/25-35s windows', () => {
  const sim = new context.V2GameSimulation(41);
  sim.invulnerableUntilTick = context.V2_RULES.maxTicks + 1;
  while (sim.currentTick <= 1200) sim.step();
  assert.ok(sim.nextCoinTick > 1200 && sim.nextCoinTick <= 1440);
  assert.ok(sim.nextHeartTick >= 2700 && sim.nextHeartTick <= 3300);
});

test('collecting another heart while full stays at one and gives no bonus score', () => {
  const sim = new context.V2GameSimulation(17);
  sim.nextObstacleTime = Infinity;
  sim.nextCoinTick = Infinity;
  sim.nextHeartTick = Infinity;
  sim.heart = 1;
  sim.items.push({ kind: 'heart', x: 130, y: 404, w: 30, h: 30 });
  const events = sim.step();
  assert.equal(sim.heart, 1);
  assert.equal(sim.hearts, 1);
  assert.equal(sim.score, 0);
  assert.equal(sim.items.length, 0, 'the collected heart is consumed even while storage is full');
  assert.deepEqual(JSON.parse(JSON.stringify(events)), [{ type: 'heart', tick: 0, stored: 1 }]);
});

test('revive consumes the heart and collision resumes exactly at the 90 tick boundary', () => {
  const sim = new context.V2GameSimulation(23);
  sim.nextObstacleTime = Infinity;
  sim.nextCoinTick = Infinity;
  sim.nextHeartTick = Infinity;
  sim.heart = 1;
  sim.obstacles.push(obstacleAtDino());
  const revive = sim.step();
  assert.equal(sim.heart, 0);
  assert.equal(sim.revives, 1);
  assert.equal(sim.invulnerableUntilTick, 90);
  assert.equal(revive[0].type, 'revive');
  while (sim.currentTick < 89) sim.step();
  sim.obstacles.push(obstacleAtDino());
  sim.step();
  assert.equal(sim.ended, false, 'tick 89 remains protected');
  sim.step();
  assert.equal(sim.ended, true, 'tick 90 is vulnerable');
  assert.equal(sim.endReason, 'COLLISION');
  assert.equal(sim.endTick, 90);
});

test('time limit is an explicit successful terminal reason', () => {
  const sim = new context.V2GameSimulation(31);
  sim.invulnerableUntilTick = context.V2_RULES.maxTicks + 1;
  while (!sim.ended) sim.step();
  assert.equal(sim.endReason, 'TIME_LIMIT');
  assert.equal(sim.endTick, 36000);
  assert.ok(sim.score >= 6000);
});

test('engine exposes v2 item and repeat-revive callbacks without a revive game-over', () => {
  const engine = fs.readFileSync(path.join(root, 'public/js/game/engine.js'), 'utf8');
  assert.match(engine, /onCoinCollected/);
  assert.match(engine, /onHeartChange/);
  assert.match(engine, /onRevive/);
  assert.match(engine, /if \(this\.simulation\.ended\) this\.handleCrash/);
  assert.match(engine, /removeEventListener\('resize', this\.resizeHandler\)/);
});

test('engine starts and advances the real v2 simulation, then removes its resize listener', () => {
  const engineSource = fs.readFileSync(path.join(root, 'public/js/game/engine.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export class DinoGameEngine', 'class DinoGameEngine');
  const listeners = new Set();
  const runtime = {
    audio: new Proxy({}, { get: () => () => {} }),
    Image: class { set src(_value) {} },
    window: {
      matchMedia: () => ({ matches: false }),
      addEventListener: (_name, handler) => listeners.add(handler),
      removeEventListener: (_name, handler) => listeners.delete(handler),
    },
    performance: { now: () => 0 },
    requestAnimationFrame: () => 1,
    cancelAnimationFrame: () => {},
  };
  vm.runInNewContext(`${source}\n${engineSource}\nglobalThis.DinoGameEngine = DinoGameEngine;`, runtime);
  const engine = new runtime.DinoGameEngine({ getContext: () => ({}) });
  engine.start(4);
  engine.updateSimulationTick();
  assert.equal(engine.currentTick, 1);
  assert.equal(engine.getSummary().coins, 0);
  assert.equal(listeners.size, 1);
  engine.stop();
  assert.equal(listeners.size, 0);
});
