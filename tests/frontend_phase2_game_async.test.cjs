const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function loadGameView(apiOverrides = {}) {
  const stored = new Map();
  const events = [];
  const toasts = [];
  const created = [];
  const document = {
    hidden: false,
    createElement(tag) {
      const node = {
        tag, className: '', textContent: '', disabled: false, children: [],
        append(...children) { this.children.push(...children); },
        appendChild(child) { this.children.push(child); },
      };
      created.push(node);
      return node;
    },
    addEventListener() {}, removeEventListener() {},
  };
  const context = {
    api: { createRequestId: () => 'request-id', ...apiOverrides },
    analytics: { track: (...args) => events.push(args) },
    ui: { showToast: (message) => toasts.push(message), text(node, value) { node.textContent = String(value); } },
    audio: {}, DinoGameEngine: class {}, document,
    sessionStorage: {
      getItem: (key) => stored.get(key) ?? null,
      setItem: (key, value) => stored.set(key, value),
      removeItem: (key) => stored.delete(key),
    },
    window: { addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false }) },
    setTimeout, clearTimeout, setInterval, clearInterval, Date, console,
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/views/game_view.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const GameView =', 'globalThis.GameView =');
  vm.runInNewContext(source, context, { filename: 'game_view.js' });
  return { view: context.GameView, stored, events, toasts, created };
}

function router(current = () => true) {
  const navigations = [];
  return {
    state: { tickets: {}, pendingGameSession: null }, renderToken: 1,
    isCurrent: (token) => current(token),
    navigate: (name) => navigations.push(name),
    announceStateChange() {}, updateNav() {}, refreshState: async () => {},
    navigations,
  };
}

const finishResult = { session_id: 'old', score: 10, best_score: 10, rank: 1, verification: 'VERIFIED' };
const gameResult = { version: '2.0.0', end_reason: 'COLLISION', score: 10, ticks: 100, jump_ticks: [], checkpoints: [], summary: {} };

test('current game completion clears its durable pending finish and navigates', async () => {
  const loaded = loadGameView({ finishSession: async () => finishResult });
  const appRouter = router();
  loaded.view.sessionId = 'old';
  loaded.view.engine = { stop() {} };
  await loaded.view.handleGameOver(gameResult, appRouter, {}, 1);
  assert.equal(loaded.stored.has('dino_pending_result'), false);
  assert.deepEqual(appRouter.navigations, ['result']);
  assert.equal(appRouter.state.lastResult.sessionId, 'old');
});

test('late game completion cannot clear or navigate over a newer session', async () => {
  const finish = deferred();
  const loaded = loadGameView({ finishSession: () => finish.promise });
  let token = 1;
  const appRouter = router((candidate) => candidate === token);
  loaded.view.sessionId = 'old';
  loaded.view.engine = { stop() {} };
  const completing = loaded.view.handleGameOver(gameResult, appRouter, {}, 1);
  token = 2;
  loaded.view.resetRuntime();
  loaded.view.sessionId = 'new';
  loaded.stored.set('dino_pending_result', JSON.stringify({ sessionId: 'new', key: 'finish_new', payload: {} }));
  finish.resolve(finishResult);
  await completing;
  assert.equal(JSON.parse(loaded.stored.get('dino_pending_result')).sessionId, 'new');
  assert.deepEqual(appRouter.navigations, []);
  assert.equal(appRouter.state.lastResult, undefined);
});

test('late pending-result recovery keeps durable data for the next current render', async () => {
  const finish = deferred();
  const invoked = deferred();
  const loaded = loadGameView({
    getSession: async () => ({ status: 'ACTIVE' }),
    finishSession: () => { invoked.resolve(); return finish.promise; },
  });
  loaded.stored.set('dino_pending_result', JSON.stringify({ sessionId: 'old', key: 'finish_old', payload: { score: 10 } }));
  let current = true;
  const appRouter = router(() => current);
  const recovery = loaded.view.recoverPendingResult(appRouter, 1);
  await invoked.promise;
  current = false;
  finish.resolve(finishResult);
  assert.equal(await recovery, true);
  assert.equal(JSON.parse(loaded.stored.get('dino_pending_result')).sessionId, 'old');
  assert.deepEqual(appRouter.navigations, []);
});

test('late pending-result failure cannot delete durable recovery data', async () => {
  const finish = deferred();
  const invoked = deferred();
  const loaded = loadGameView({
    getSession: async () => ({ status: 'ACTIVE' }),
    finishSession: () => { invoked.resolve(); return finish.promise; },
  });
  loaded.stored.set('dino_pending_result', JSON.stringify({ sessionId: 'old', key: 'finish_old', payload: { score: 10 } }));
  let current = true;
  const recovery = loaded.view.recoverPendingResult(router(() => current), 1);
  await invoked.promise;
  current = false;
  const error = Object.assign(new Error('invalid finish'), { status: 409 });
  finish.reject(error);
  await assert.rejects(recovery, /invalid finish/);
  assert.equal(JSON.parse(loaded.stored.get('dino_pending_result')).key, 'finish_old');
});

test('checkpoint completions cannot regress storage or resurrect an old session', async () => {
  const first = deferred();
  const second = deferred();
  const third = deferred();
  let calls = 0;
  const loaded = loadGameView({ checkpointSession: () => [first.promise, second.promise, third.promise][calls++] });
  const engine = { isRunning: true, currentTick: 100, stop() {}, getResumeSnapshot: () => ({ version: '2.0.0', seed: 1, tick: engine.currentTick, jumpTicks: [] }) };
  loaded.view.sessionId = 'same';
  loaded.view.engine = engine;
  const older = loaded.view.sendCheckpoint();
  engine.currentTick = 200;
  const newer = loaded.view.sendCheckpoint();
  second.resolve({});
  await newer;
  first.resolve({});
  await older;
  assert.equal(loaded.stored.get('dino_checkpoint_same'), '200');

  loaded.view.engine.currentTick = 300;
  const late = loaded.view.sendCheckpoint();
  loaded.view.cleanup();
  loaded.view.sessionId = 'new';
  loaded.stored.delete('dino_checkpoint_same');
  third.resolve({});
  await late;
  assert.equal(loaded.stored.has('dino_checkpoint_same'), false);
});

test('late fault completion preserves a newer session marker and emits no old analytics', async () => {
  const report = deferred();
  const loaded = loadGameView({ reportSessionFault: () => report.promise });
  loaded.view.sessionId = 'old';
  const reporting = loaded.view.reportFault('CLIENT_ERROR', 0);
  loaded.view.cleanup();
  loaded.view.sessionId = 'new';
  loaded.stored.set('dino_fault_new', JSON.stringify({ sessionId: 'new', reason: 'NETWORK_ERROR', tick: 50, key: 'new-key' }));
  report.resolve({});
  assert.equal(await reporting, false);
  assert.equal(JSON.parse(loaded.stored.get('dino_fault_new')).key, 'new-key');
  assert.equal(loaded.events.some(([name]) => name === 'game_fault_reported'), false);
});

test('current fault recovery reconciles a 409 checkpoint before reporting the fault', async () => {
  const calls = [];
  const conflict = Object.assign(new Error('checkpoint already advanced'), { status: 409 });
  const loaded = loadGameView({
    checkpointSession: async (...args) => { calls.push(['checkpoint', ...args]); throw conflict; },
    getSession: async (...args) => { calls.push(['session', ...args]); return { last_checkpoint_tick: 90 }; },
    reportSessionFault: async (...args) => { calls.push(['fault', ...args]); return {}; },
  });
  loaded.view.sessionId = 'fault-session';
  loaded.view.currentStage = 'stage_2';
  loaded.stored.set('dino_checkpoint_fault-session', '80');
  const reported = await loaded.view.reportFault('CLIENT_ERROR', 80);
  assert.equal(reported, true);
  assert.deepEqual(JSON.parse(JSON.stringify(calls)), [
    ['checkpoint', 'fault-session', 80, 'stage_2'],
    ['session', 'fault-session'],
    ['fault', 'fault-session', { reason: 'CLIENT_ERROR', last_tick: 90 }, 'request-id'],
  ]);
  assert.equal(loaded.stored.has('dino_fault_fault-session'), false);
  assert.equal(loaded.events.some(([name]) => name === 'game_fault_reported'), true);
});

test('interrupted FAULT_REPORTED refresh cannot navigate after the screen becomes stale', async () => {
  const refresh = deferred();
  const loaded = loadGameView({ getSession: async () => ({ status: 'ABORTED' }) });
  let current = true;
  const appRouter = router(() => current);
  appRouter.refreshState = () => refresh.promise;
  const container = { children: [], replaceChildren() { this.children = []; }, appendChild(child) { this.children.push(child); } };
  loaded.view.renderInterruptedSession(container, appRouter, 1, { id: 'old', status: 'FAULT_REPORTED' });
  const primary = loaded.created.find((node) => node.tag === 'button' && node.className.includes('btn-primary'));
  const checking = primary.onclick();
  await Promise.resolve();
  current = false;
  refresh.resolve({});
  await checking;
  assert.deepEqual(appRouter.navigations, []);
  assert.equal(loaded.events.some(([name]) => name === 'game_recovered'), false);
});
