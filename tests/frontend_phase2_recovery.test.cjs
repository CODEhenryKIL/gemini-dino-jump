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

test('v2 resume replay restores the actual deterministic score, items, held heart, and revives', () => {
  const directContext = {};
  vm.runInNewContext(`${simulationSource}\nglobalThis.Simulation = V2GameSimulation;`, directContext);
  const simulation = new directContext.Simulation(41);
  while (!simulation.ended && simulation.currentTick < 2200) {
    const jump = simulation.isGrounded && simulation.obstacles.some((obstacle) => obstacle.x < 260 && obstacle.x > 100);
    simulation.step(jump ? { jump: true, high: true } : {});
  }
  assert.equal(simulation.ended, false);
  assert.ok(simulation.coins > 0);
  assert.ok(simulation.hearts > 0);
  assert.ok(simulation.revives > 0);

  const runtime = loadEngine();
  const engine = new runtime.DinoGameEngine({ getContext: () => canvasContext() }, { version: '2.0.0' });
  const snapshot = { version: '2.0.0', seed: 41, tick: simulation.currentTick, jumpTicks: simulation.jumpTicks.map((jump) => ({ ...jump })) };
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

test('missing or stale snapshots never restart an active session at tick zero', async () => {
  let starts = 0;
  const state = { session_id: 'session-1', status: 'ACTIVE', version: '2.0.0', seed: 41, last_checkpoint_tick: 300, expires_at: new Date(Date.now() + 60_000).toISOString() };
  const loaded = loadGameView({ getSession: async () => state, startSession: async () => { starts += 1; } });
  const navigations = [];
  const router = { isCurrent: () => true, state: {}, navigate: (name) => navigations.push(name), refreshState: async () => {} };
  const container = { children: [], replaceChildren() { this.children = []; }, appendChild(child) { this.children.push(child); } };
  loaded.view.renderInterruptedSession(container, router, 1, state);
  const primary = loaded.created.find((element) => element.tag === 'button' && element.className.includes('btn-primary'));
  await primary.onclick();
  assert.equal(starts, 0);
  assert.deepEqual(navigations, []);
  assert.match(loaded.created.find((element) => element.tag === 'p').textContent, /처음부터 다시 시작하지 않습니다/);

  const stale = { sessionId: 'session-1', version: '2.0.0', seed: 41, tick: 299, jumpTicks: [] };
  assert.match(loaded.view.validateResumeSnapshot(stale, state), /서버 체크포인트보다 오래/);
  assert.match(loaded.view.validateResumeSnapshot({ ...stale, tick: 300, version: '1.2.0' }, state), /버전이 일치하지/);
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
