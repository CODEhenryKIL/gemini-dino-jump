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
  vm.runInNewContext(fs.readFileSync(path.join(root, 'public/js/benefit_retry.js'), 'utf8').replace(/export function /g, 'function '), context);
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
  const again = node();
  const game = node();
  const routes = [];
  const router = { state: { draw: {} }, isCurrent: () => true, navigate(route) { routes.push(route); } };
  const container = { querySelector(selector) { return selector === '#btn-draw-share' ? button : selector === '#draw-share-status' ? status : selector === '#btn-draw-again' ? again : selector === '#btn-draw-game' ? game : null; } };
  return { button, again, game, container, routes, router, status, view: loadDraw(prepare) };
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
    '#scratch-canvas', '#scratch-result-content', '#btn-draw-share', '#draw-share-status', '#btn-draw-again', '#btn-draw-game',
  ];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const scratchContainer = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  view.renderScratch(scratchContainer, router, { draw_id: 'draw-round-4', round_number: 4, pouch_index: 2, outcome_kind: 'BENEFIT', scratch_completed: false, prize: {} }, 2, router.state.draw);
  view.scratchCard.options.onStart();
  assert.equal(tracked.at(-1)[0], 'scratch_started');
  assert.deepEqual(JSON.parse(JSON.stringify(tracked.at(-1)[1])), { round_number: 4 });
});

test('the approved compact B selection keeps the first and repeat prize titles without a lineup image', () => {
  const view = loadDraw(async () => ({}));
  const open = node();
  const pouches = [0, 1, 2].map((index) => ({ ...node(), dataset: { index: String(index) }, classList: { toggle() {} } }));
  const container = {
    innerHTML: '',
    querySelector(selector) { return selector === '#btn-open-pouch' ? open : null; },
    querySelectorAll() { return pouches; },
  };
  const router = { state: { draw: { used_count: 0, max_count: 10, available_credits: 1 } }, isCurrent: () => true };
  view.renderSelection(container, router, 1);
  assert.match(container.innerHTML, /이번 판 경품도 받아가세요/);
  assert.doesNotMatch(container.innerHTML, /prize-lineup|prize-preview/);
  router.state.draw.used_count = 1;
  view.renderSelection(container, router, 1);
  assert.match(container.innerHTML, /경품을 한 번 더 뽑아보세요/);
  const css = fs.readFileSync(path.join(root, 'public/css/phase2-views.css'), 'utf8');
  assert.match(css, /\.view-content:has\(\.draw-action-dock\) \.scratch-ticket \{ height: 180px/);
  assert.match(css, /#btn-open-pouch \{[^}]*background: #188038/);
});

test('a legacy low-score Gemini result remains viewable but cannot expose another draw', () => {
  const view = loadDraw(async () => ({}));
  let rendered;
  view.renderScratch = (_container, _router, draw, _token, state) => { rendered = { draw, state }; };
  const router = { state: {}, isCurrent: () => true };
  const draw = { draw_id: 'legacy-benefit', scratch_completed: true, prize: {} };
  const state = { status: 'LOCKED', score_eligible: false, used_count: 1, available_credits: 1, draw };
  view.renderResolvedState({}, router, 4, state);
  assert.equal(rendered.draw.draw_id, 'legacy-benefit');
  assert.equal(rendered.state.score_eligible, false);

  const retrySource = fs.readFileSync(path.join(root, 'public/js/benefit_retry.js'), 'utf8').replace(/export function /g, 'function ');
  const context = {};
  vm.runInNewContext(`${retrySource}\nglobalThis.available = benefitRetryAvailability;`, context);
  const available = context.available(state, { available_total: 0, invitation: 0, invitation_reserved: 0 }, 'ACTIVE');
  assert.equal(available.drawGrant, false);
  assert.equal(available.drawReady, false);
  assert.equal(available.gameGrant, true);
  assert.match(available.message, /101점/);
});

test('Gemini benefit result prepares combined benefit_retry and confirmed webhook exposes a direct next action', async () => {
  let options;
  const h = shareHarness(async (_router, received) => {
    options = received;
    return { share: async () => ({ method: 'kakao', status: 'pending', shareId: 'share-draw-1' }) };
  });
  await h.view.preparePostDrawShare(h.container, h.router, 4, { round_number: 2, prize: {} }, { used_count: 2, max_count: 10 }, false);
  assert.equal(options.kind, 'benefit_retry');
  assert.equal(h.button.hidden, false);
  assert.equal(h.button.textContent, '공유하고 한 판 더');
  await h.button.onclick();
  assert.match(h.status.textContent, /전송 확인 중/);
  options.onReceipt({ status: 'confirmed', reward_status: 'granted', reward_type: 'BOTH', rewards: { game: { quantity: 1 }, draw: { quantity: 1 } }, tickets: { invitation: 1, available_total: 1 }, draw_state: { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 1 } });
  assert.equal(h.router.state.draw.available_credits, 1);
  assert.equal(h.again.hidden, false);
  assert.equal(h.game.hidden, false);
  assert.equal(h.router.state.tickets.invitation, 1);
  assert.deepEqual(h.routes, [], 'confirmed delivery exposes a direct next action instead of navigating unexpectedly');
});

test('actual prize result prepares an unrewarded two-line prize boast and never opens another draw', async () => {
  let options;
  const h = shareHarness(async (_router, received) => { options = received; return { share: async () => ({ status: 'pending' }) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 5, { round_number: 3, prize: { name: '소니 ULT WEAR 헤드셋' } }, { used_count: 3, max_count: 10, actual_prize_won: true }, true);
  assert.equal(options.kind, 'prize_share');
  assert.equal(options.info.won_prize_name, '소니 ULT WEAR 헤드셋');
  assert.match(h.button.textContent, /당첨 자랑하기/);
  const css = fs.readFileSync(path.join(root, 'public/css/phase2-views.css'), 'utf8');
  assert.match(css, /\.actual-prize-result \.post-reveal-actions #btn-draw-share \{ display: block !important; \}/);
  await h.button.onclick();
  assert.deepEqual(h.routes, []);
});

test('a persisted actual-prize scratch opens direct contact with the authoritative claim', async () => {
  let received; let manual;
  const claim = { id: 'claim-1', claim_type: 'DRAW', prize_name: '소니 헤드셋', category: 'SHIPPING', status: 'AWAITING_INFORMATION' };
  const view = loadDraw(async () => ({}), {
    api: { getClaims: async () => ({ claims: [claim] }) },
    PrizeView: {
      openImmediateClaim: async (...args) => { received = args; return true; },
      directClaimModal: async (...args) => { manual = args; return true; },
    },
  });
  const router = { isCurrent: () => true, navigate() {} };
  const draw = { draw_id: 'draw-1', claim_id: 'claim-1', scratch_completed: true, prize: { name: '소니 헤드셋' } };
  assert.equal(await view.maybeOpenActualPrizeClaim({}, router, 3, draw), true);
  assert.equal(received[0], claim);
  assert.equal(received[2], 3);
  received[3].onSubmitted();
  assert.equal(await view.maybeOpenActualPrizeClaim({}, router, 3, draw, { force: true }), true);
  assert.equal(manual[0], claim, 'manual reopening bypasses the one-shot automatic prompt guard');
});

test('a revisited submitted prize routes its contact CTA to the benefit instead of reopening a dead form', async () => {
  const claim = { id: 'claim-done', claim_type: 'DRAW', prize_name: '헤드셋', status: 'INFORMATION_RECEIVED', contact_submitted: true };
  const after = node();
  const container = { querySelector: (selector) => selector === '#btn-after-draw' ? after : null };
  const routes = [];
  const view = loadDraw(async () => ({}), {
    api: { getClaims: async () => ({ claims: [claim] }) },
    PrizeView: { openImmediateClaim: async () => assert.fail('submitted claim must not reopen') },
  });
  const router = { isCurrent: () => true, navigate: (route) => routes.push(route) };
  const draw = { draw_id: 'draw-done', claim_id: 'claim-done', scratch_completed: true, prize: { name: '헤드셋' } };
  assert.equal(await view.maybeOpenActualPrizeClaim(container, router, 7, draw), true);
  assert.equal(after.textContent, '혜택 보러 가기');
  after.onclick();
  assert.deepEqual(routes, ['benefit']);
});

test('a missing current claim never opens an unrelated pending draw claim', async () => {
  let opened = 0;
  const view = loadDraw(async () => ({}), {
    api: { getClaims: async () => ({ claims: [{ id: 'older-claim', claim_type: 'DRAW', status: 'AWAITING_INFORMATION', contact_submitted: false }] }) },
    PrizeView: { openImmediateClaim: async () => { opened += 1; return true; } },
  });
  const router = { isCurrent: () => true, navigate() {} };
  const draw = { draw_id: 'current-draw', scratch_completed: true, prize: { name: '현재 경품' } };
  assert.equal(await view.maybeOpenActualPrizeClaim({}, router, 10, draw), false);
  assert.equal(opened, 0);
});

test('an authoritative claim id remains usable while the claims list is briefly stale', async () => {
  let received;
  const view = loadDraw(async () => ({}), {
    api: { getClaims: async () => ({ claims: [{ id: 'older-claim', claim_type: 'DRAW', status: 'AWAITING_INFORMATION' }] }) },
    PrizeView: { openImmediateClaim: async (claim) => { received = claim; return true; } },
  });
  const router = { isCurrent: () => true, navigate() {} };
  const draw = { draw_id: 'current-draw', claim_id: 'current-claim', scratch_completed: true, prize: { name: '현재 경품', category: 'COUPON' } };
  assert.equal(await view.maybeOpenActualPrizeClaim({}, router, 11, draw), true);
  assert.equal(received.id, 'current-claim');
  assert.equal(received.prize_name, '현재 경품');
});

test('the fixed draw dock keeps replay primary and prepares a secondary game share before scratching', async () => {
  let preparedKind;
  const view = loadDraw(async (_router, options) => {
    preparedKind = options.kind;
    return { share: async () => ({ status: 'pending' }) };
  }, { showGameGuide() {} });
  const primary = node();
  const secondary = node();
  const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 0, max_count: 10, available_credits: 1 }, tickets: { available_total: 1, invitation: 0, invitation_reserved: 0 } },
    isCurrent: () => true,
    campaignStatus: () => 'ACTIVE',
  };
  await view.updateActionDock(container, router, 8);
  assert.equal(primary.textContent, '한 판 더 하기');
  assert.equal(secondary.hidden, false);
  assert.equal(preparedKind, 'retry_invite');
  assert.match(status.textContent, /게임권 1장/);
});

test('a selection reached with an earlier Gemini result keeps the combined retry hint', async () => {
  let preparedKind;
  const view = loadDraw(async (_router, options) => {
    preparedKind = options.kind;
    return { share: async () => ({ status: 'pending' }) };
  }, { showGameGuide() {} });
  const primary = node(); const secondary = node(); const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1, score_eligible: true }, tickets: { available_total: 1, invitation: 1, invitation_reserved: 0 } },
    isCurrent: () => true, campaignStatus: () => 'ACTIVE',
  };
  await view.updateActionDock(container, router, 15);
  assert.equal(preparedKind, 'benefit_retry');
  assert.equal(primary.textContent, '한 판 더 하기');
  assert.equal(secondary.hidden, false);
  assert.equal(secondary.textContent, '공유하고 한 판 더');
  assert.match(status.textContent, /게임권 1장 \+ 경품 뽑기 1회/);
});

test('a revealed Gemini result upgrades the fixed dock share to the combined retry reward', async () => {
  let preparedKind;
  const view = loadDraw(async (_router, options) => { preparedKind = options.kind; return { share: async () => ({ status: 'pending' }) }; });
  const primary = node(); const secondary = node(); const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const draw = { draw_id: 'benefit-1', scratch_completed: true };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 0 }, tickets: { available_total: 0, invitation: 0, invitation_reserved: 0 } },
    isCurrent: () => true,
    campaignStatus: () => 'ACTIVE',
  };
  view.activeDrawContext = { container, renderToken: 9, draw, drawState: router.state.draw, actualPrize: false, resultRevealed: true };
  await view.updateActionDock(container, router, 9);
  assert.equal(preparedKind, 'benefit_retry');
  assert.equal(primary.textContent, '공유하고 한 판 더');
  assert.match(status.textContent, /게임권 1장 \+ 경품 뽑기 1회/);
});

test('a confirmed combined benefit reward makes the fixed dock open the next draw while retaining replay', async () => {
  let options;
  const routes = [];
  const view = loadDraw(async (_router, received) => {
    options = received;
    return { share: async () => ({ status: 'pending' }) };
  }, { showGameGuide() {} });
  const primary = node(); const secondary = node(); const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const draw = { draw_id: 'benefit-confirmed', scratch_completed: true };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 0 }, tickets: { available_total: 0, invitation: 0, invitation_reserved: 0 } },
    isCurrent: () => true,
    campaignStatus: () => 'ACTIVE',
    navigate: (route) => routes.push(route),
  };
  view.activeDrawContext = { container, renderToken: 13, draw, drawState: router.state.draw, actualPrize: false, resultRevealed: true };
  await view.updateActionDock(container, router, 13);
  options.onReceipt({
    status: 'confirmed', reward_type: 'BOTH', reward_status: 'granted',
    rewards: { game: { quantity: 1 }, draw: { quantity: 1 } },
    tickets: { available_total: 1, invitation: 1, invitation_reserved: 0 },
    draw_state: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1 },
  });
  await new Promise(setImmediate);
  assert.equal(primary.textContent, '한 번 더 뽑기');
  assert.equal(primary.disabled, false);
  assert.equal(secondary.hidden, false);
  assert.equal(secondary.textContent, '한 판 더 하기');
  primary.onclick();
  assert.deepEqual(routes, ['draw']);
});

test('a draw-only benefit reward during the game ticket cooldown still opens the next draw', async () => {
  let options;
  const routes = [];
  const view = loadDraw(async (_router, received) => { options = received; return { share: async () => ({ status: 'pending' }) }; });
  const primary = node(); const secondary = node(); const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const draw = { draw_id: 'benefit-draw-only', scratch_completed: true };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 0 }, tickets: { available_total: 0, invitation: 3, invitation_reserved: 0, cooldown_until: '2999-01-01T00:00:00Z' } },
    isCurrent: () => true, campaignStatus: () => 'ACTIVE', navigate: (route) => routes.push(route),
  };
  view.activeDrawContext = { container, renderToken: 14, draw, drawState: router.state.draw, actualPrize: false, resultRevealed: true };
  await view.updateActionDock(container, router, 14);
  options.onReceipt({
    status: 'confirmed', reward_type: 'DRAW', reward_status: 'granted', rewards: { draw: { quantity: 1 }, game: { quantity: 0 } },
    tickets: { available_total: 0, invitation: 3, invitation_reserved: 0, cooldown_until: '2999-01-01T00:00:00Z' },
    draw_state: { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 1 },
  });
  await new Promise(setImmediate);
  assert.equal(primary.textContent, '한 번 더 뽑기');
  assert.equal(secondary.hidden, true);
  primary.onclick();
  assert.deepEqual(routes, ['draw']);
});

test('a failed dock share preparation exposes a working retry instead of a stuck disabled button', async () => {
  let preparations = 0;
  const view = loadDraw(async () => { preparations += 1; throw new Error('offline'); });
  const primary = node(); const secondary = node(); const status = node();
  const container = { querySelector(selector) {
    return selector === '#draw-dock-primary' ? primary : selector === '#draw-dock-secondary' ? secondary : selector === '#draw-dock-status' ? status : null;
  } };
  const router = {
    state: { draw: { status: 'AVAILABLE', used_count: 0, max_count: 10 }, tickets: { available_total: 0, invitation: 0, invitation_reserved: 0 } },
    isCurrent: () => true,
    campaignStatus: () => 'ACTIVE',
  };
  await view.updateActionDock(container, router, 12);
  assert.equal(primary.disabled, false);
  assert.match(status.textContent, /공유 준비를 불러오지 못했어요/);
  primary.onclick();
  await new Promise(setImmediate);
  assert.equal(preparations, 2);
});

test('an actual-prize draw suppresses automatic TOP3 replacement while keeping manual TOP3 recovery', () => {
  const source = fs.readFileSync(path.join(root, 'public/js/views/draw_view.js'), 'utf8');
  assert.match(source, /!isActualPrizeDraw\(state\.draw\).*openTop3Modal/);
  assert.match(source, /renderTop3Result\(container, router\)/);
});

test('the tenth benefit result permits a game-only retry share', async () => {
  let preparations = 0;
  const h = shareHarness(async () => { preparations += 1; return { share: async () => ({}) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 6, { round_number: 10, prize: {} }, { used_count: 10, max_count: 10 }, false);
  assert.equal(preparations, 1);
  assert.equal(h.button.hidden, false);
  assert.equal(h.again.hidden, true);
  assert.match(h.status.textContent, /공유하면 게임권 1장/);
});

test('callout suppression stays scoped to the game controls and preserves press/release handlers', () => {
  const game = fs.readFileSync(path.join(root, 'public/js/views/game_view.js'), 'utf8');
  const css = fs.readFileSync(path.join(root, 'public/css/game.css'), 'utf8');
  assert.match(game, /for \(const element of \[viewport, jumpButton\]\)/);
  assert.match(game, /\['contextmenu', 'dragstart', 'selectstart', 'dblclick'\]/);
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


test('an existing draw credit offers a separate direct action alongside optional sharing', async () => {
  let preparations = 0;
  const h = shareHarness(async () => { preparations += 1; return { share: async () => ({}) }; });
  await h.view.preparePostDrawShare(h.container, h.router, 4, { round_number: 2, prize: {} }, { used_count: 2, max_count: 10, available_credits: 1 }, false);
  assert.equal(preparations, 1);
  assert.equal(h.button.hidden, false);
  assert.equal(h.again.hidden, false);
  h.again.onclick();
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
  assert.equal(preparations, 0, 'the fixed dock owns retry sharing and direct actions do not create a second intent');
  h.router.state.draw = { status: 'AVAILABLE', used_count: 2, max_count: 10, available_credits: 1 };
  await h.view.updateState(h.container, h.router, 4);
  assert.equal(preparations, 0, 'the granted credit must not create another retry intent');
  assert.equal(h.again.hidden, false);
  h.again.onclick();
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
    '#scratch-canvas', '#scratch-result-content', '#btn-draw-share', '#draw-share-status', '#btn-draw-again', '#btn-draw-game',
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
  assert.equal(preparations, 0, 'the durable reveal exposes its direct draw action without preparing duplicate sharing');
  assert.equal(nodes.get('#btn-draw-again').hidden, false);

  nodes.get('#btn-draw-again').onclick();
  assert.deepEqual(routes, ['draw']);
});
