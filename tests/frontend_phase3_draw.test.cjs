const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function loadDraw(prepareResultReferralShare, overrides = {}) {
  const context = {
    console,
    api: {},
    analytics: { track() {} },
    ui: { text(node, value) { node.textContent = String(value); }, showToast() {} },
    ScratchCard: class {},
    prepareResultReferralShare,
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    ...overrides,
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/views/draw_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const DrawView =', 'globalThis.DrawView =');
  vm.runInNewContext(source, context, { filename: 'draw_view.js' });
  return context.DrawView;
}

function node() {
  return {
    hidden: true, disabled: false, textContent: '', onclick: null, inert: false, tabIndex: 0, attrs: {},
    classList: { add() {}, toggle() {} },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
    getAttribute(name) { return this.attrs[name] ?? null; },
    focus() {},
  };
}

function shareHarness(prepare) {
  const button = node();
  const status = node();
  const routes = [];
  const router = { state: { draw: {} }, isCurrent: () => true, navigate(route) { routes.push(route); } };
  const container = { querySelector(selector) { return selector === '#btn-draw-share' ? button : selector === '#draw-share-status' ? status : null; } };
  return { button, container, routes, router, status, view: loadDraw(prepare) };
}

test('pouch and scratch hooks report the server round being acted on', () => {
  const tracked = [];
  class ScratchCardMock {
    constructor(_canvas, options) { this.options = options; }
    destroy() {}
  }
  const pouches = [0, 1, 2].map((index) => ({
    ...node(), dataset: { index: String(index) }, classList: { toggle() {} },
  }));
  const open = node();
  const description = node();
  const selectionContainer = {
    innerHTML: '',
    querySelector(selector) { return selector === '#btn-open-pouch' ? open : description; },
    querySelectorAll() { return pouches; },
  };
  const view = loadDraw(async () => ({}), {
    analytics: { track: (...args) => tracked.push(args) },
    ScratchCard: ScratchCardMock,
    document: { activeElement: null },
  });
  const router = { state: { draw: { used_count: 3, max_count: 10, available_credits: 1 } }, isCurrent: () => true, announceStateChange() {}, navigate() {} };
  view.renderSelection(selectionContainer, router, 1);
  pouches[2].onclick();
  assert.equal(tracked.at(-1)[0], 'pouch_selected');
  assert.deepEqual(JSON.parse(JSON.stringify(tracked.at(-1)[1])), { action: 'pouch_2', round_number: 4 });

  const selectors = [
    '#scratch-title', '#scratch-instruction', '#result-prize-img', '#result-prize-title', '#result-prize-sub',
    '#btn-after-draw', '#btn-instant-reveal', '#restored-pouch', '#post-reveal-actions', '#scratch-save-status',
    '#scratch-canvas', '#scratch-result-content', '#btn-draw-share', '#draw-share-status',
  ];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const scratchContainer = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  view.renderScratch(scratchContainer, router, { draw_id: 'draw-round-4', round_number: 4, pouch_index: 2, outcome_kind: 'BENEFIT', scratch_completed: false, prize: {} }, 2, router.state.draw);
  view.scratchCard.options.onStart();
  assert.equal(tracked.at(-1)[0], 'scratch_started');
  assert.deepEqual(JSON.parse(JSON.stringify(tracked.at(-1)[1])), { round_number: 4 });
});

test('Gemini benefit result prepares draw_retry and confirmed webhook exposes a direct next action', async () => {
  let options;
  const h = shareHarness(async (_router, received) => {
    options = received;
    return { share: async () => ({ method: 'kakao', status: 'pending', shareId: 'share-draw-1' }) };
  });
  await h.view.preparePostDrawShare(h.container, h.router, 4, { round_number: 2, prize: {} }, { used_count: 2, max_count: 10 }, false);
  assert.equal(options.kind, 'draw_retry');
  assert.equal(h.button.hidden, false);
  assert.match(h.button.textContent, /공유하고 한 번 더 뽑기/);
  await h.button.onclick();
  assert.match(h.status.textContent, /전송 확인 후/);
  options.onReceipt({ status: 'confirmed', reward_status: 'granted', reward_type: 'DRAW', draw_state: { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 1 } });
  assert.equal(h.router.state.draw.available_credits, 1);
  assert.deepEqual(h.routes, [], 'confirmed delivery exposes a direct next action instead of navigating unexpectedly');
});

test('actual prize result prepares an unrewarded two-line prize boast and never opens another draw', async () => {
  let options;
  const h = shareHarness(async (_router, received) => { options = received; return { share: async () => ({ status: 'pending' }) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 5, { round_number: 3, prize: { name: '소니 ULT WEAR 헤드셋' } }, { used_count: 3, max_count: 10, actual_prize_won: true }, true);
  assert.equal(options.kind, 'prize_share');
  assert.equal(options.info.won_prize_name, '소니 ULT WEAR 헤드셋');
  assert.match(h.button.textContent, /당첨 자랑하기/);
  await h.button.onclick();
  assert.deepEqual(h.routes, []);
});

test('the tenth benefit result ends repeat draws without preparing a new share intent', async () => {
  let preparations = 0;
  const h = shareHarness(async () => { preparations += 1; return { share: async () => ({}) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 6, { round_number: 10, prize: {} }, { used_count: 10, max_count: 10 }, false);
  assert.equal(preparations, 0);
  assert.equal(h.button.hidden, true);
  assert.equal(h.status.textContent, '10회 복주머니를 모두 확인했어요.');
});

test('jump callout suppression stays scoped to the jump button and preserves press/release handlers', () => {
  const game = fs.readFileSync(path.join(root, 'public/js/views/game_view.js'), 'utf8');
  const css = fs.readFileSync(path.join(root, 'public/css/game.css'), 'utf8');
  assert.match(game, /jumpButton\.addEventListener\('contextmenu'/);
  assert.match(game, /jumpButton\.addEventListener\('dragstart'/);
  assert.match(game, /for \(const element of \[canvas, jumpButton\]\)/);
  assert.match(game, /element\.addEventListener\('pointerdown', press\)/);
  assert.match(game, /element\.addEventListener\('pointerup', release\)/);
  assert.match(css, /\.big-jump-btn \{[\s\S]*-webkit-touch-callout: none/);
  assert.doesNotMatch(css, /(?:^|\n)(?:html|body|\*)[^\{]*\{[^}]*-webkit-touch-callout:\s*none/);
});


test('an AVAILABLE credit does not hide its latest unrevealed result', async () => {
  const state = {
    status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1,
    draw: { draw_id: 'draw-1', round_number: 1, scratch_completed: false },
  };
  const view = loadDraw(async () => ({}), { api: { getDraw: async () => state } });
  let scratch = null;
  let selections = 0;
  view.renderScratch = (_container, _router, draw, _token, drawState) => { scratch = { draw, drawState }; };
  view.renderSelection = () => { selections += 1; };
  const router = { state: {}, isCurrent: () => true };
  await view.render({ innerHTML: '' }, router, 7);
  assert.equal(selections, 0);
  assert.equal(scratch.draw.draw_id, 'draw-1');
  assert.equal(scratch.drawState.available_credits, 1);
});

test('a lost draw response keeps one durable key and reconciles before manual retry', async () => {
  const values = new Map();
  const sessionStorage = {
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, value); },
    removeItem(key) { values.delete(key); },
  };
  const calls = [];
  let attempt = 0;
  const api = {
    createRequestId: () => 'draw-stable-key',
    getDraw: async () => ({ status: 'AVAILABLE', used_count: 0, max_count: 10, available_credits: 1, draw: null }),
    drawPouch: async (...args) => {
      calls.push(args);
      attempt += 1;
      if (attempt === 1) throw new Error('response lost');
      return {
        draw: { draw_id: 'draw-1', round_number: 1, pouch_index: 2, scratch_completed: false },
        draw_state: { status: 'DRAWN', used_count: 1, max_count: 10, available_credits: 0 },
      };
    },
  };
  const open = node();
  const pouches = [0, 1, 2].map((index) => ({ ...node(), dataset: { index: String(index) }, classList: { toggle() {} } }));
  const container = {
    innerHTML: '',
    querySelector(selector) { return selector === '#btn-open-pouch' ? open : null; },
    querySelectorAll() { return pouches; },
  };
  const view = loadDraw(async () => ({}), { api, sessionStorage });
  let resolved = null;
  view.renderResolvedState = (_container, _router, _token, state) => { resolved = state; };
  const router = { state: { draw: { status: 'AVAILABLE', used_count: 0, max_count: 10, available_credits: 1 } }, isCurrent: () => true, announceStateChange() {} };
  view.renderSelection(container, router, 4);
  pouches[2].onclick();
  await open.onclick();
  assert.match(open.textContent, /다시 확인/);
  assert.ok(values.has('dino_pending_draw_v1'));
  await open.onclick();
  assert.deepEqual(calls, [
    [2, 'draw-stable-key', 1],
    [2, 'draw-stable-key', 1],
  ]);
  assert.equal(values.has('dino_pending_draw_v1'), false);
  assert.equal(resolved.draw.draw_id, 'draw-1');
});

test('draw API carries an explicit reusable idempotency key and expected round guard', () => {
  const apiSource = fs.readFileSync(path.join(root, 'public/js/api.js'), 'utf8');
  assert.match(apiSource, /drawPouch\(pouchIndex, idempotencyKey = null, expectedRoundNumber = null\)/);
  assert.match(apiSource, /idempotencyKey: eventId/);
  assert.match(apiSource, /expected_round_number: expectedRoundNumber/);
});


test('an existing draw credit renders a direct next draw action without preparing another share', async () => {
  let preparations = 0;
  const h = shareHarness(async () => { preparations += 1; return { share: async () => ({}) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 4, { round_number: 2, prize: {} }, { used_count: 2, max_count: 10, available_credits: 1 }, false);
  assert.equal(preparations, 0);
  assert.equal(h.button.hidden, false);
  assert.equal(h.button.textContent, '한 번 더 뽑기');
  h.button.onclick();
  assert.deepEqual(h.routes, ['draw']);
});

test('a passive state refresh replaces the share action with a direct draw action without reload', async () => {
  let preparations = 0;
  const h = shareHarness(async () => { preparations += 1; return { share: async () => ({}) }; });
  const draw = { draw_id: 'draw-2', round_number: 2, scratch_completed: true, prize: {} };
  h.router.state.draw = { status: 'DRAWN', used_count: 2, max_count: 10, available_credits: 0 };
  h.view.activeDrawContext = {
    container: h.container, router: h.router, renderToken: 4, draw,
    drawState: h.router.state.draw, actualPrize: false, resultRevealed: true,
  };
  await h.view.updateState(h.container, h.router, 4);
  assert.equal(preparations, 1);
  h.router.state.draw = { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 1 };
  await h.view.updateState(h.container, h.router, 4);
  assert.equal(preparations, 1, 'the granted credit must not create another draw_retry intent');
  assert.equal(h.button.textContent, '한 번 더 뽑기');
  h.button.onclick();
  assert.deepEqual(h.routes, ['draw']);
});

test('an unrevealed benefit waits for scratch persistence before exposing the next draw action', async () => {
  let resolveSave;
  const save = new Promise((resolve) => { resolveSave = resolve; });
  let preparations = 0;
  class ScratchCardMock {
    constructor(_canvas, options) { this.options = options; }
    revealInstantly() { this.promise = this.options.onReveal(); return this.promise; }
    destroy() {}
  }
  const selectors = [
    '#scratch-title', '#scratch-instruction', '#result-prize-img', '#result-prize-title', '#result-prize-sub',
    '#btn-after-draw', '#btn-instant-reveal', '#restored-pouch', '#post-reveal-actions', '#scratch-save-status',
    '#scratch-canvas', '#scratch-result-content', '#btn-draw-share', '#draw-share-status',
  ];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  const view = loadDraw(async () => { preparations += 1; return { share: async () => ({}) }; }, {
    api: { createRequestId: () => 'scratch-save-1', completeScratch: () => save },
    ScratchCard: ScratchCardMock,
    document: { activeElement: null },
  });
  const routes = [];
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1 } },
    isCurrent: () => true, announceStateChange() {}, navigate(route) { routes.push(route); },
  };
  view.renderScratch(container, router, { draw_id: 'draw-1', round_number: 1, pouch_index: 0, outcome_kind: 'BENEFIT', scratch_completed: false, prize: {} }, 5, router.state.draw);
  nodes.get('#btn-instant-reveal').onclick();
  await Promise.resolve();
  assert.equal(nodes.get('#post-reveal-actions').hidden, false);
  assert.equal(nodes.get('#btn-draw-share').hidden, true, 'do not advance before the revealed result is durably saved');
  resolveSave({ scratch_completed: true });
  await view.scratchCard.promise;
  assert.equal(preparations, 0);
  assert.equal(nodes.get('#btn-draw-share').hidden, false);
  assert.equal(nodes.get('#btn-draw-share').textContent, '한 번 더 뽑기');
  nodes.get('#btn-draw-share').onclick();
  assert.deepEqual(routes, ['draw']);
});
