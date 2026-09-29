const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const deferred = () => {
  let resolve;
  const promise = new Promise((done) => { resolve = done; });
  return { promise, resolve };
};

function node(tag = 'div') {
  return {
    tag, textContent: '', innerHTML: '', hidden: false, disabled: false, onclick: null, children: [], attrs: {}, dataset: {},
    classList: { add() {}, toggle() {} },
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); return item; },
    replaceChildren(...items) { this.children = items; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
  };
}

function loadView(file, exportName, globals = {}) {
  const source = fs.readFileSync(path.join(root, file), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace(`export const ${exportName} =`, 'globalThis.__view =');
  const context = { console, Date, Math, JSON, Number, Promise, setTimeout, clearTimeout, ...globals };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: file });
  return context.__view;
}

test('ranking GAME share stays disabled when preparation or sharing crosses campaign end', async () => {
  let status = 'ACTIVE';
  let shares = 0;
  const preparing = deferred();
  const sharing = deferred();
  const view = loadView('public/js/views/ranking_view.js', 'RankingView', {
    prepareResultReferralShare: () => preparing.promise,
    api: {}, analytics: { track() {} }, document: { createElement: () => node() },
  });
  const router = { campaignStatus: () => status };
  const button = node('button'); const feedback = node('p');
  const pending = view.prepareSharing(button, feedback, router, () => true);
  status = 'ENDED';
  preparing.resolve({ share: async () => { shares += 1; return sharing.promise; } });
  await pending;
  assert.equal(button.disabled, true);
  await button.onclick?.();
  assert.equal(shares, 0);

  status = 'ACTIVE';
  const ready = deferred();
  const view2 = loadView('public/js/views/ranking_view.js', 'RankingView', {
    prepareResultReferralShare: async () => ({ share: async () => { shares += 1; return ready.promise; } }),
    api: {}, analytics: { track() {} }, document: { createElement: () => node() },
  });
  const button2 = node('button'); const prepared = view2.prepareSharing(button2, node('p'), router, () => true);
  await prepared;
  const click = button2.onclick();
  status = 'PAUSED'; ready.resolve({ status: 'cancelled' }); await click;
  assert.equal(button2.disabled, true, 'share finally must not re-enable a reward action after pause');
});

test('invite blocks GAME rewards at boundaries but preserves NONE prize sharing and saved draw results', async () => {
  let status = 'ENDED';
  const preparedKinds = [];
  const selectors = ['#invite-gap', '#invite-balance', '#ticket-granted', '#ticket-used', '#ticket-refunded', '#valid-visits', '#invite-cooldown', '#share-fallback', '#btn-share-native', '#btn-invite-draw'];
  const makeContainer = () => {
    const nodes = new Map(selectors.map((selector) => [selector, node()]));
    return { nodes, container: { innerHTML: '', querySelector: (selector) => nodes.get(selector), replaceChildren() {} } };
  };
  const view = loadView('public/js/views/invite_view.js', 'InviteView', {
    api: { getReferralInfo: async () => ({ invite_url: '/invite/test', ticket_totals: {} }), getLeaderboard: async () => ({}) },
    analytics: { track() {} }, ui: { text: (target, value) => { if (target) target.textContent = String(value); }, showToast() {} },
    prepareResultReferralShare: async (_router, options) => { preparedKinds.push(options.kind); return { share: async () => ({ status: 'cancelled' }) }; },
    document: { createElement: () => node() },
  });
  const game = makeContainer();
  const routes = [];
  const router = { state: { draw: { status: 'AVAILABLE' } }, shareContext: 'record_share', campaignStatus: () => status,
    isCurrent: () => true, navigate: (route) => routes.push(route) };
  await view.render(game.container, router, 1);
  assert.deepEqual(preparedKinds, []);
  assert.equal(game.nodes.get('#btn-share-native').disabled, true);
  assert.equal(game.nodes.get('#btn-invite-draw').disabled, true);

  router.state.draw = { status: 'DRAWN', draw: { scratch_completed: true } };
  view.updateDrawAction(game.container, router);
  assert.equal(game.nodes.get('#btn-invite-draw').disabled, false);
  game.nodes.get('#btn-invite-draw').onclick();
  assert.deepEqual(routes, ['draw']);

  const prize = makeContainer(); router.shareContext = 'prize_share';
  await view.render(prize.container, router, 2);
  assert.deepEqual(preparedKinds, ['prize_share']);
  assert.equal(prize.nodes.get('#btn-share-native').disabled, false);
});

test('invite preparation resolving after campaign end cannot enable GAME sharing', async () => {
  let status = 'ACTIVE';
  const preparing = deferred();
  const selectors = ['#invite-gap', '#invite-balance', '#ticket-granted', '#ticket-used', '#ticket-refunded', '#valid-visits', '#invite-cooldown', '#share-fallback', '#btn-share-native', '#btn-invite-draw'];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const view = loadView('public/js/views/invite_view.js', 'InviteView', {
    api: { getReferralInfo: async () => ({ invite_url: '/invite/test', ticket_totals: {} }), getLeaderboard: async () => ({}) },
    analytics: { track() {} }, ui: { text: (target, value) => { if (target) target.textContent = String(value); }, showToast() {} },
    prepareResultReferralShare: () => preparing.promise, document: { createElement: () => node() },
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector), replaceChildren() {} };
  const router = { state: { draw: { status: 'LOCKED' } }, shareContext: 'retry_invite', campaignStatus: () => status, isCurrent: () => true, navigate() {} };
  const rendering = view.render(container, router, 1);
  await Promise.resolve();
  status = 'ENDED';
  preparing.resolve({ share: async () => ({ status: 'cancelled' }) });
  await rendering;
  assert.equal(nodes.get('#btn-share-native').disabled, true);
});

function drawHarness({ status = 'ENDED', pending = null, prepare } = {}) {
  const values = new Map();
  if (pending) values.set('dino_pending_draw_v1', JSON.stringify(pending));
  const sessionStorage = {
    getItem: (key) => values.get(key) || null,
    setItem: (key, value) => values.set(key, String(value)),
    removeItem: (key) => values.delete(key),
  };
  let campaign = status;
  const calls = [];
  const api = {
    createRequestId: () => 'new-draw-key',
    getDraw: async () => ({ status: 'AVAILABLE', used_count: 0, available_credits: 1, draw: null }),
    drawPouch: async (...args) => { calls.push(args); return { draw: { draw_id: 'draw-1', scratch_completed: false }, draw_state: { status: 'DRAWN' } }; },
  };
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    api, analytics: { track() {} }, ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    ScratchCard: class {}, prepareResultReferralShare: prepare || (async () => ({ share: async () => ({}) })), sessionStorage,
    document: { createElement: () => node() },
  });
  const open = node('button'); const description = node('p');
  const pouches = [0, 1, 2].map((index) => ({ ...node('button'), dataset: { index: String(index) }, classList: { toggle() {} } }));
  const container = { innerHTML: '', querySelector: (selector) => selector === '#btn-open-pouch' ? open : selector === '.pouch-selection-description' ? description : null,
    querySelectorAll: () => pouches };
  const router = { state: { draw: { status: 'AVAILABLE', used_count: 0, available_credits: 1 } }, campaignStatus: () => campaign,
    isCurrent: () => true, announceStateChange() {}, refreshState: async () => {}, navigate() {} };
  return { api, calls, container, description, open, pouches, router, setStatus: (value) => { campaign = value; }, values, view };
}

test('draw blocks new selection after end while retaining an existing idempotent pending draw', async () => {
  const blocked = drawHarness();
  blocked.view.renderSelection(blocked.container, blocked.router, 1);
  assert.ok(blocked.pouches.every((pouch) => pouch.disabled));
  await blocked.open.onclick();
  assert.deepEqual(blocked.calls, []);
  blocked.setStatus('ACTIVE'); await blocked.view.updateState(blocked.container, blocked.router, 1);
  assert.ok(blocked.pouches.every((pouch) => !pouch.disabled));
  blocked.setStatus('PAUSED'); await blocked.view.updateState(blocked.container, blocked.router, 1);
  assert.match(blocked.description.textContent, /잠시 중단/);

  const request = { event_id: 'durable-key', pouch_index: 2, expected_round_number: 1 };
  const pending = drawHarness({ pending: request });
  pending.view.renderSelection(pending.container, pending.router, 2);
  assert.equal(pending.open.disabled, false);
  await pending.open.onclick();
  assert.deepEqual(pending.calls, [[2, 'durable-key', 1]]);
});

test('draw post actions block DRAW rewards after end while preserving actual-prize NONE sharing', async () => {
  let preparations = 0;
  const h = drawHarness({ prepare: async () => { preparations += 1; return { share: async () => ({ status: 'cancelled' }) }; } });
  const button = node('button'); const message = node('p');
  const container = { querySelector: (selector) => selector === '#btn-draw-share' ? button : selector === '#draw-share-status' ? message : null };
  h.router.state.draw = { status: 'DRAWN' };
  await h.view.preparePostDrawShare(container, h.router, 3, { round_number: 1, prize: {} }, { used_count: 1, max_count: 10 }, false);
  assert.equal(preparations, 0);
  assert.equal(button.disabled, true);
  await h.view.preparePostDrawShare(container, h.router, 4, { round_number: 1, prize: { name: '경품' } }, { used_count: 1, max_count: 10 }, true);
  assert.equal(preparations, 1);
  assert.equal(button.disabled, false);

  const late = deferred();
  const crossing = drawHarness({ status: 'ACTIVE', prepare: () => late.promise });
  const lateButton = node('button'); const lateMessage = node('p');
  const lateContainer = { querySelector: (selector) => selector === '#btn-draw-share' ? lateButton : selector === '#draw-share-status' ? lateMessage : null };
  const pending = crossing.view.preparePostDrawShare(lateContainer, crossing.router, 5, { round_number: 2, prize: {} }, { used_count: 2, max_count: 10 }, false);
  crossing.setStatus('PAUSED');
  late.resolve({ share: async () => ({ status: 'cancelled' }) });
  await pending;
  assert.equal(lateButton.disabled, true);
});

test('claims benefit card does not prepare or reopen DRAW actions after campaign end', async () => {
  let status = 'ENDED'; let preparations = 0;
  const view = loadView('public/js/views/prize_view.js', 'PrizeView', {
    api: {}, analytics: { track() {} }, ui: { showToast() {} },
    prepareResultReferralShare: async () => { preparations += 1; return { share: async () => ({}) }; },
    document: { createElement: (tag) => node(tag) },
  });
  const router = { state: {}, campaignStatus: () => status, isCurrent: () => true, navigate() {} };
  const direct = view.benefitCard({ available_credits: 1, used_count: 1, max_count: 10 }, router, 1);
  assert.equal(direct.children.at(-1).children[1].disabled, true);
  const share = view.benefitCard({ available_credits: 0, used_count: 1, max_count: 10 }, router, 1);
  await Promise.resolve();
  assert.equal(preparations, 0);
  assert.equal(share.children.at(-1).children[1].disabled, true);

  status = 'PAUSED';
  const paused = view.benefitCard({ available_credits: 1, used_count: 1, max_count: 10 }, router, 1);
  assert.match(paused.children.at(-1).children[1].textContent, /잠시 중단/);

  status = 'ACTIVE';
  const late = deferred();
  const crossingView = loadView('public/js/views/prize_view.js', 'PrizeView', {
    api: {}, analytics: { track() {} }, ui: { showToast() {} }, prepareResultReferralShare: () => late.promise,
    document: { createElement: (tag) => node(tag) },
  });
  const crossing = crossingView.benefitCard({ available_credits: 0, used_count: 1, max_count: 10 }, router, 2);
  status = 'ENDED'; late.resolve({ share: async () => ({}) });
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(crossing.children.at(-1).children[1].disabled, true);
});
