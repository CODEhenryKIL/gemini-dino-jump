const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');
const simulationSource = read('public/js/game/simulation.js').replace(/export\s+(?=(const|class|function)\s)/g, '');

function canvasContext() {
  const gradient = { addColorStop() {} };
  return new Proxy({}, {
    get(_target, key) {
      if (key === 'createLinearGradient' || key === 'createRadialGradient') return () => gradient;
      if (key === 'measureText') return () => ({ width: 10 });
      return () => {};
    },
    set() { return true; },
  });
}

function loadEngine() {
  const source = read('public/js/game/engine.js')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export class DinoGameEngine', 'class DinoGameEngine');
  const runtime = {
    audio: new Proxy({}, { get: () => () => {} }),
    Image: class { set src(_value) {} },
    window: { matchMedia: () => ({ matches: false }), addEventListener() {}, removeEventListener() {} },
    performance: { now: () => 100 },
    requestAnimationFrame: () => 1,
    cancelAnimationFrame() {},
    console,
  };
  vm.runInNewContext(`${simulationSource}\n${source}\nglobalThis.DinoGameEngine = DinoGameEngine;`, runtime);
  return runtime;
}

for (const version of ['2.0.0', '2.1.0']) test(`${version} resume replay restores deterministic score, items, held heart, and revival penalties`, () => {
  const directContext = {};
  vm.runInNewContext(`${simulationSource}\nglobalThis.Simulation = V2GameSimulation;`, directContext);
  const simulation = new directContext.Simulation(41, version);
  while (!simulation.ended && simulation.currentTick < 2200) {
    const jump = simulation.isGrounded && simulation.obstacles.some((obstacle) => obstacle.x < 260 && obstacle.x > 100);
    simulation.step(jump ? { jump: true, high: true } : {});
  }
  assert.equal(simulation.ended, false);
  assert.ok(simulation.coins > 0);
  assert.ok(simulation.hearts > 0);
  assert.ok(simulation.revives > 0);

  const runtime = loadEngine();
  const engine = new runtime.DinoGameEngine({ getContext: () => canvasContext() }, { version });
  const snapshot = { version, seed: 41, tick: simulation.currentTick, jumpTicks: simulation.jumpTicks.map((jump) => ({ ...jump })) };
  const restored = engine.restoreSnapshot(snapshot);
  assert.equal(engine.currentTick, simulation.currentTick);
  assert.equal(engine.score, simulation.score);
  assert.equal(restored.heart, simulation.heart);
  assert.deepEqual(JSON.parse(JSON.stringify(restored.summary)), JSON.parse(JSON.stringify(simulation.result().summary)));
  assert.deepEqual(JSON.parse(JSON.stringify(engine.getResumeSnapshot())), JSON.parse(JSON.stringify(snapshot)));
  engine.resumeRestored();
  assert.equal(engine.isRunning, true);
});

function loadGameView(apiOverrides = {}) {
  const stored = new Map();
  const created = [];
  const document = {
    hidden: false,
    createElement(tag) {
      const element = { tag, className: '', textContent: '', disabled: false, onclick: null, children: [], append(...children) { this.children.push(...children); } };
      created.push(element);
      return element;
    },
    addEventListener() {}, removeEventListener() {},
  };
  const context = {
    api: { createRequestId: () => 'id_12345678', ...apiOverrides },
    analytics: { track() {} }, ui: { showToast() {}, text(node, value) { node.textContent = String(value); } }, audio: {}, DinoGameEngine: class {},
    sessionStorage: { getItem: (key) => stored.get(key) || null, setItem: (key, value) => stored.set(key, value), removeItem: (key) => stored.delete(key) },
    window: { addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false }) }, document,
    setTimeout, clearTimeout, setInterval, clearInterval, Date, console,
  };
  context.globalThis = context;
  const source = read('public/js/views/game_view.js').replace(/^import .*;\s*$/gm, '').replace('export const GameView =', 'globalThis.GameView =');
  vm.runInNewContext(source, context, { filename: 'game_view.js' });
  return { view: context.GameView, stored, created };
}

for (const status of ['ACTIVE', 'RESERVED', 'FAULT_REPORTED']) test(`${status} is automatically invalidated and refunded before a new game`, async () => {
  const order = [];
  const loaded = loadGameView({ abandonSession: async (id) => { order.push(`abandon:${id}`); return { status: 'ABORTED', tickets: { initial: 1 } }; } });
  const state = { session_id: 'session-1', status };
  const router = { isCurrent: () => true, state: { pendingGameSession: state }, updateNav() {}, announceStateChange() {} };
  const container = { replaceChildren() {}, appendChild() {} };
  loaded.stored.set('dino_snapshot_session-1', '{}');
  loaded.view.renderGameShell = () => {};
  loaded.view.startNewSession = async () => { order.push('start'); assert.equal(router.state.tickets.initial, 1); };
  await loaded.view.renderInterruptedSession(container, router, 1, state);
  assert.deepEqual(order, ['abandon:session-1', 'start']);
  assert.equal(router.state.pendingGameSession, null);
  assert.equal(loaded.stored.has('dino_snapshot_session-1'), false);
});

test('a concurrently finished game shows its result instead of being restarted', async () => {
  const result = { session_id: 'session-1', score: 300, best_score: 300, rank: 2 };
  const loaded = loadGameView({ abandonSession: async () => ({ status: 'FINISHED', result }) });
  const routes = [];
  const router = { isCurrent: () => true, state: { tickets: {} }, navigate: (route) => routes.push(route), announceStateChange() {}, updateNav() {} };
  loaded.view.startNewSession = () => assert.fail('finished game must not restart');
  await loaded.view.renderInterruptedSession({ replaceChildren() {}, appendChild() {} }, router, 1, { id: 'session-1' });
  assert.deepEqual(routes, ['result']);
  assert.equal(router.state.lastResult.score, 300);
});

test('failed abandon retains pending session and offers retry without spending another ticket', async () => {
  const loaded = loadGameView({ abandonSession: async () => { throw new Error('offline'); } });
  const pending = { id: 'session-1', status: 'ACTIVE' };
  const router = { isCurrent: () => true, state: { pendingGameSession: pending }, navigate() {} };
  loaded.view.startNewSession = () => assert.fail('do not start before successful refund');
  await loaded.view.renderInterruptedSession({ replaceChildren() {}, appendChild() {} }, router, 1, pending);
  assert.equal(router.state.pendingGameSession, pending);
  assert.equal(loaded.created.find((node) => node.textContent === '다시 시도').hidden, false);
});

test('cleanup persists a PII-free active snapshot for the same session', () => {
  const loaded = loadGameView();
  loaded.view.sessionId = 'session-2';
  loaded.view.engine = { getResumeSnapshot: () => ({ version: '2.0.0', seed: 9, tick: 420, jumpTicks: [{ tick: 120, high: true }] }), stop() {} };
  loaded.view.cleanup();
  const snapshot = JSON.parse(loaded.stored.get('dino_snapshot_session-2'));
  assert.deepEqual(snapshot, { sessionId: 'session-2', version: '2.0.0', seed: 9, tick: 420, jumpTicks: [{ tick: 120, high: true }] });
  assert.doesNotMatch(JSON.stringify(snapshot), /token|contact|participant|phone/i);
});

 test('new game engine shows ten stages and caps the final speed', () => {
  const runtime = loadEngine();
  const engine = new runtime.DinoGameEngine({ getContext: () => canvasContext() }, { version: '2.1.0' });
  assert.equal(engine.stages.length, 10);
  assert.equal(engine.canvas.width, 960);
  assert.equal(engine.canvas.height, 900);
  assert.equal(engine.height, 600);
  assert.equal(engine.groundY, 490);
  assert.equal(engine.getSpeed(105), 940);
  assert.equal(engine.getSpeed(120), 1080);
  assert.equal(engine.getSpeed(135), 1200);
  assert.equal(engine.getSpeed(150), 1320);
  assert.equal(engine.getSpeed(500), 1320);
});
