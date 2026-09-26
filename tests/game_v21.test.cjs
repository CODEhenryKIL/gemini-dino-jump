const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/game/simulation.js'), 'utf8')
  .replace(/export\s+(?=(const|class|function)\s)/g, '');
const context = {};
vm.runInNewContext(`${source}
globalThis.V2_RULES = V2_RULES;
globalThis.V21_RULES = V21_RULES;
globalThis.V21_STAGES = V21_STAGES;
globalThis.V2GameSimulation = V2GameSimulation;
globalThis.simulateV2 = simulateV2;`, context);

function obstacleAtDino() {
  return {
    x: 124, y: 442, w: 36, h: 48, type: 'cactus_small', altitude: 'ground',
    hb: { offsetX: 6, offsetY: 4, width: 24, height: 42 },
  };
}

function simulateRevives(reviveCount) {
  const sim = new context.V2GameSimulation(211, '2.1.0');
  sim.nextObstacleTime = Infinity;
  sim.nextCoinTick = Infinity;
  sim.nextHeartTick = Infinity;
  const reviveEvents = [];
  for (let index = 0; index < reviveCount; index++) {
    while (sim.currentTick < sim.invulnerableUntilTick) sim.step();
    sim.heart = 1;
    sim.obstacles.push(obstacleAtDino());
    reviveEvents.push(sim.step()[0]);
  }
  sim.coins = 30;
  while (sim.currentTick < 1200) sim.step();
  return { sim, reviveEvents };
}

function movementAndGapAt(timeSec) {
  const sim = new context.V2GameSimulation(17, '2.1.0');
  sim.currentTick = timeSec * sim.rules.tickRate;
  sim.nextCoinTick = Infinity;
  sim.nextHeartTick = Infinity;
  sim.nextObstacleTime = timeSec;
  sim.obstaclePrng.nextFloat = (() => {
    const values = [0, 1, 0];
    return () => values.shift() ?? 0;
  })();
  const xBefore = sim.rules.width + 20;
  sim.step();
  return {
    speed: (xBefore - sim.obstacles[0].x) * sim.rules.tickRate,
    gap: sim.nextObstacleTime - timeSec,
  };
}

test('current and frozen v2.1 constants exactly match the exported browser contract', () => {
  const current = JSON.parse(fs.readFileSync(path.join(root, 'shared/game_constants.json'), 'utf8'));
  const frozen = JSON.parse(fs.readFileSync(path.join(root, 'shared/game_constants_v21.json'), 'utf8'));
  assert.deepEqual(current, frozen);
  assert.equal(current.version, context.V21_RULES.version);
  assert.equal(current.rules.revivePenaltyPoints, context.V21_RULES.revivePenaltyPoints);
  assert.deepEqual(JSON.parse(JSON.stringify(context.V21_STAGES)), current.stages);
});

test('v2.1 stages 8 through 10 apply the specified speed ramps and obstacle gaps', () => {
  for (const [timeSec, expectedSpeed, expectedGap] of [
    [105, 940, 0.50],
    [112.5, 1010, 0.50],
    [120, 1080, 0.44],
    [127.5, 1140, 0.44],
    [135, 1200, 0.40],
    [142.5, 1260, 0.40],
    [150, 1320, 0.40],
    [160, 1320, 0.40],
  ]) {
    const actual = movementAndGapAt(timeSec);
    assert.ok(Math.abs(actual.speed - expectedSpeed) < 1e-8, `speed at ${timeSec}s`);
    assert.ok(Math.abs(actual.gap - expectedGap) < 1e-8, `gap at ${timeSec}s`);
  }
});

test('v2.1 collision revives deduct 100 points each and report the cumulative penalty', () => {
  for (const reviveCount of [0, 1, 2, 3]) {
    const { sim, reviveEvents } = simulateRevives(reviveCount);
    const result = sim.result();
    assert.equal(result.summary.revives, reviveCount);
    assert.equal(result.summary.revive_penalty, reviveCount * 100);
    assert.equal(result.score, 500 - reviveCount * 100);
    reviveEvents.forEach((event, index) => {
      assert.equal(event.type, 'revive');
      assert.equal(event.penalty, 100);
      assert.equal(event.totalPenalty, (index + 1) * 100);
    });
  }
});

test('v2.1 score never falls below zero after repeated revives', () => {
  const { sim } = simulateRevives(3);
  sim.coins = 0;
  sim.currentTick = 1;
  sim.step();
  assert.equal(sim.score, 0);
});

test('the frozen v2.0 contract and default replay remain penalty-free', () => {
  const frozen = JSON.parse(fs.readFileSync(path.join(root, 'shared/game_constants_v2.json'), 'utf8'));
  assert.equal(frozen.version, '2.0.0');
  assert.equal(frozen.stages.length, 6);
  assert.equal(frozen.stages[5].startSpeed, 800);
  assert.equal(frozen.stages[5].maxSpeed, 880);
  assert.equal(frozen.rules.revivePenaltyPoints, undefined);

  const defaultSim = new context.V2GameSimulation(19);
  const explicitSim = new context.V2GameSimulation(19, '2.0.0');
  for (const sim of [defaultSim, explicitSim]) {
    sim.nextObstacleTime = Infinity;
    sim.nextCoinTick = Infinity;
    sim.nextHeartTick = Infinity;
    sim.heart = 1;
    sim.obstacles.push(obstacleAtDino());
    const event = sim.step()[0];
    assert.equal(event.penalty, undefined);
    assert.equal(event.totalPenalty, undefined);
    assert.equal(sim.result().summary.revive_penalty, undefined);
    assert.equal(sim.result().version, '2.0.0');
  }
  assert.deepEqual(JSON.parse(JSON.stringify(defaultSim.result())), JSON.parse(JSON.stringify(explicitSim.result())));
});

test('simulateV2 accepts v2.1 as its optional fourth version argument', () => {
  const result = context.simulateV2(7, [], 60, '2.1.0');
  assert.equal(result.version, '2.1.0');
  assert.equal(result.summary.revive_penalty, 0);
});
