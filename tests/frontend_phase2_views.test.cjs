const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function loadView(file, exportName, globals = {}) {
  const source = fs.readFileSync(path.join(root, file), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace(`export const ${exportName} =`, 'globalThis.__view =');
  const context = { console, URL, ...globals };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: file });
  return context.__view;
}

function node() {
  return {
    textContent: '', hidden: false, disabled: false, inert: false, tabIndex: 0, onclick: null, children: [], attrs: {},
    classList: { add() {}, toggle() {} },
    append(...items) { this.children.push(...items); },
    appendChild(item) { this.children.push(item); },
    replaceChildren(...items) { this.children = items; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
    getAttribute(name) { return this.attrs[name] ?? null; },
  };
}

test('home enables a newly earned ticket and uses the latest pending game after a passive refresh', () => {
  const nodes = new Map();
  const container = { innerHTML: '', querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); } };
  const routes = [];
  const view = loadView('public/js/views/home.js', 'HomeView', {
    ui: { showModal() {} }, analytics: { track() {} },
    showGameGuide: () => routes.push('guide'),
  });
  const router = { state: { tickets: { initial: 0, invitation: 0 }, bestScore: 32 }, navigate: (route) => routes.push(route) };
  view.render(container, router);
  const start = nodes.get('#btn-start-jump');
  assert.equal(start.disabled, false);
  assert.match(start.textContent, /친구에게 공유하고 게임권 받기/);
  router.state.tickets = { initial: 0, invitation: 1 };
  view.updateState(container, router);
  assert.equal(start.disabled, false);
  assert.equal(start.textContent, '게임 시작');
  assert.equal(nodes.get('#home-ticket-note').hidden, true);
  assert.equal(nodes.get('#home-invite-ticket').textContent, '1장');
  start.onclick();
  assert.deepEqual(routes, ['guide']);
  router.state.tickets = { initial: 0, invitation: 0 };
  router.state.pendingGameSession = { status: 'ACTIVE' };
  view.updateState(container, router);
  assert.equal(start.disabled, false);
  assert.equal(start.textContent, '진행 중 게임 복원');
  start.onclick();
  assert.deepEqual(routes, ['guide', 'game']);
});

test('home distinguishes expired cooldown from current waiting and explains an ended campaign accurately', () => {
  const nodes = new Map();
  const container = { innerHTML: '', querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); } };
  const view = loadView('public/js/views/home.js', 'HomeView');
  const router = { state: { tickets: { initial: 0, invitation: 2, cooldown_until: '2000-01-01T00:00:00Z' } } };
  view.render(container, router);
  assert.doesNotMatch(nodes.get('#home-ticket-note').textContent, /적립 대기/);
  assert.equal(nodes.get('#home-ticket-note').hidden, true);
  router.config = { campaign: { status: 'ENDED' } };
  view.updateState(container, router);
  assert.equal(nodes.get('#home-ticket-note').hidden, false);
  assert.match(nodes.get('#home-ticket-note').textContent, /종료/);
  assert.doesNotMatch(nodes.get('#home-ticket-note').textContent, /다시 시작/);
});

test('home restores a draw route without requiring another ticket or another game', () => {
  const nodes = new Map();
  const container = { innerHTML: '', querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); } };
  const routes = [], events = [];
  const view = loadView('public/js/views/home.js', 'HomeView', {
    analytics: { track: (name, dimensions) => events.push({ name, ...dimensions }) },
  });
  const router = { state: { tickets: { initial: 0, invitation: 0 }, draw: { status: 'LOCKED' } }, navigate: (route) => routes.push(route) };
  view.render(container, router);
  const draw = nodes.get('#btn-home-draw');
  assert.equal(draw.hidden, true);
  draw.onclick();
  assert.deepEqual(routes, []);
  router.state.draw.status = 'AVAILABLE';
  view.updateState(container, router);
  assert.equal(nodes.get('#btn-start-jump').disabled, false);
  assert.match(nodes.get('#btn-start-jump').textContent, /친구에게 공유하고 게임권 받기/);
  assert.equal(draw.hidden, false);
  assert.equal(draw.textContent, '복주머니 열기');
  draw.onclick();
  router.state.draw.status = 'DRAWN';
  view.updateState(container, router);
  assert.equal(draw.textContent, '내 복주머니 결과 보기');
  draw.onclick();
  assert.deepEqual(routes, ['draw', 'draw']);
  assert.deepEqual(events, [
    { name: 'draw_cta_clicked', source: 'home', draw_status: 'AVAILABLE' },
    { name: 'draw_cta_clicked', source: 'home', draw_status: 'DRAWN' },
  ]);
});

test('result and empty claims draw buttons track their own source before entering the draw screen', () => {
  const events = [], routes = [];
  const globals = {
    analytics: { track: (name, dimensions) => events.push({ name, ...dimensions }) },
    ui: { text: (target, value) => { target.textContent = String(value); } },
    document: { createElement: () => node() },
  };
  const result = loadView('public/js/views/result_view.js', 'ResultView', globals);
  const nodes = new Map();
  const container = { innerHTML: '', querySelector(selector) { if (!nodes.has(selector)) nodes.set(selector, node()); return nodes.get(selector); } };
  const router = { state: { lastResult: { score: 32, bestScore: 32, top3_gap: { status: 'TOO_FEW' } }, draw: { status: 'AVAILABLE' } }, navigate: (route) => routes.push(route) };
  result.render(container, router, 1);
  nodes.get('#btn-go-pouch').onclick();
  const prize = loadView('public/js/views/prize_view.js', 'PrizeView', globals);
  const claims = node();
  router.state.draw.status = 'DRAWN';
  prize.renderEmpty(claims, router);
  claims.children[0].children[1].onclick();
  assert.deepEqual(routes, ['draw', 'draw']);
  assert.deepEqual(events, [
    { name: 'draw_cta_clicked', source: 'result', draw_status: 'AVAILABLE' },
    { name: 'draw_cta_clicked', source: 'claims', draw_status: 'DRAWN' },
  ]);
});

test('prize claim preserves the form and rejects an empty school before sending the request', async () => {
  const fields = new Map();
  let modal;
  let consent;
  let submitted = 0;
  const view = loadView('public/js/views/prize_view.js', 'PrizeView', {
    document: { createElement(tag) { const item = node(); if (tag === 'input') consent = item; return item; } },
    analytics: { track() {} },
    api: { submitClaim: async () => { submitted += 1; } },
    ui: {
      formField(_label, _type, name, options) {
        const input = { name, required: options.required, value: '' };
        fields.set(name, input);
        return { label: node(), input };
      },
      showModal(value) { modal = value; }, showToast() {},
    },
  });
  view.claimModal({ id: 'claim-1', claim_type: 'DRAW' }, { announceStateChange() {}, navigate() {} });
  consent.checked = true;
  fields.get('school').value = '   ';
  assert.equal(await modal.onConfirm(), false);
  assert.equal(submitted, 0);
  assert.equal(fields.get('name').value, 'TEST_사용자');
  fields.get('school').value = 'TEST_학교';
  fields.get('address').value = '';
  await modal.onConfirm();
  assert.equal(submitted, 1);
});

test('TOP3 gap copy handles server states without promising a prize', () => {
  const view = loadView('public/js/views/result_view.js', 'ResultView');
  assert.match(view.top3GapMessage({ rank: 2, top3_gap: { status: 'IN_TOP3', rank: 2, tied: false, participant_count: 8 } }), /현재 2위로 TOP3/);
  assert.match(view.top3GapMessage({ rank: 3, top3_gap: { status: 'IN_TOP3', rank: 3, tied: true, participant_count: 8 } }), /같은 순위의 동점 기록/);
  assert.match(view.top3GapMessage({ rank: null, top3_gap: { status: 'TOO_FEW', participant_count: 2 } }), /현재 참가자는 2명/);
  assert.match(view.top3GapMessage({ rank: null, top3_gap: { status: 'NO_SCORE' } }), /검증된 점수/);
  assert.equal(view.top3GapMessage({ rank: 6, top3_gap: { status: 'CHASING', third_score: 100, score_needed: 42, tied: false, participant_count: 8 } }), '현재 3위까지 42점이 더 필요해요.');
  assert.match(view.top3GapMessage({ rank: 4, top3_gap: { status: 'CHASING', third_score: 100, score_needed: 0, tied: true, participant_count: 8 } }), /3위 점수와 동점/);
});

test('an old-version TOP3 contact request stays actionable without implying current TOP3 status', () => {
  const view = loadView('public/js/views/result_view.js', 'ResultView');
  const old = view.top3RequestCopy({ status: 'REQUESTED', game_version: '1.2.0' }, { campaign: { game_version: '2.0.0' } });
  assert.match(old.title, /이전 게임 규칙/);
  assert.match(old.description, /접수 요청은 유지/);
  assert.match(old.description, /현재 2.0.0 규칙의 TOP3라는 뜻은 아니며/);
  const current = view.top3RequestCopy({ status: 'REQUESTED', game_version: '2.0.0' }, { campaign: { game_version: '2.0.0' } });
  assert.match(current.title, /잠정 TOP3/);
});

test('record sharing emits a public URL with explicit context and authoritative ticket totals', async () => {
  const selectors = ['#invite-title', '#invite-description', '#invite-score', '#invite-balance', '#ticket-granted', '#ticket-used', '#ticket-refunded', '#valid-visits', '#invite-cooldown', '#share-fallback', '#btn-share-native', '#btn-copy-link', '#btn-invite-draw'];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const copied = [];
  const events = [];
  let referral = { invite_url: '/invite/publiccode123', invitation_balance: 2, valid_visits: 7, ticket_totals: { granted: 5, used: 2, refunded: 1 } };
  const view = loadView('public/js/views/invite_view.js', 'InviteView', {
    api: {
      getReferralInfo: async () => referral,
      createRequestId: () => 'share_phase2_1234',
    },
    analytics: { track: (name, dimensions = {}) => events.push({ name, dimensions }) },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    navigator: { clipboard: { writeText: async (value) => copied.push(value) } },
    window: { location: { origin: 'https://example.test' } },
    document: { createElement: () => node() },
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector), replaceChildren() { throw new Error('unexpected error state'); } };
  const routes = [];
  const router = { state: { bestScore: 812, draw: { status: 'AVAILABLE' } }, shareContext: 'record_share', isCurrent: () => true, navigate: (route) => routes.push(route) };
  await view.render(container, router, 1);
  const draw = nodes.get('#btn-invite-draw');
  assert.equal(draw.hidden, false);
  draw.onclick();
  assert.deepEqual(routes, ['draw'], 'the draw can open before sharing or waiting for a friend');
  assert.deepEqual(JSON.parse(JSON.stringify(events.filter(({ name }) => name === 'draw_cta_clicked'))), [
    { name: 'draw_cta_clicked', dimensions: { source: 'invite', draw_status: 'AVAILABLE' } },
  ]);
  await nodes.get('#btn-copy-link').onclick();
  assert.equal(nodes.get('#ticket-granted').textContent, '5장');
  assert.equal(nodes.get('#ticket-used').textContent, '사용 2장');
  assert.equal(nodes.get('#ticket-refunded').textContent, '환급 1장');
  assert.equal(copied[0], 'https://example.test/invite/publiccode123?link=record_share&share=share_phase2_1234');
  assert.deepEqual(JSON.parse(JSON.stringify(events.filter((event) => event.name === 'share_attempted').map((event) => event.dimensions))), [
    { share_method: 'copy', share_id: 'share_phase2_1234', link_kind: 'record_share', status: 'attempted' },
    { share_method: 'copy', share_id: 'share_phase2_1234', link_kind: 'record_share', status: 'copied' },
  ]);
  referral = { ...referral, invitation_balance: 3, valid_visits: 8, cooldown_until: '2000-01-01T00:00:00Z', ticket_totals: { granted: 6, used: 2, refunded: 1 } };
  router.state.draw.status = 'DRAWN';
  await view.updateState(container, router, 1);
  assert.equal(draw.textContent, '내 복주머니 결과 보기');
  assert.equal(nodes.get('#invite-balance').textContent, '3장');
  assert.equal(nodes.get('#valid-visits').textContent, '8회');
  assert.equal(nodes.get('#ticket-granted').textContent, '6장');
  assert.doesNotMatch(nodes.get('#invite-cooldown').textContent, /적립 대기 중/);
  await nodes.get('#btn-copy-link').onclick();
  assert.equal(copied[1], copied[0], 'passive refresh preserves record_share context');
  assert.equal(events.filter(({ name }) => name === 'invite_cta_viewed').length, 1);
  referral = { ...referral, invitation_balance: 1 };
  await view.updateState(container, { isCurrent: () => false }, 1);
  assert.equal(nodes.get('#invite-balance').textContent, '3장', 'an older response must not change the current screen');
  assert.equal(draw.hidden, false, 'an older refresh must not hide the current draw action');
  router.state.draw.status = 'LOCKED';
  await view.updateState(container, router, 1);
  assert.equal(draw.hidden, true);
  draw.onclick();
  assert.deepEqual(routes, ['draw'], 'a now-locked draw action does not navigate');
});

test('restored scratched draw reveals the same server result without another draw or completion request', async () => {
  const selectors = ['#scratch-title', '#scratch-instruction', '#result-prize-img', '#result-prize-title', '#result-prize-sub', '#btn-after-draw', '#btn-instant-reveal', '#restored-pouch', '#post-reveal-actions', '#scratch-save-status', '#scratch-canvas', '#scratch-result-content'];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  let completeCalls = 0;
  let restored = false;
  class ScratchCardMock {
    constructor(_canvas, options) { this.options = options; }
    revealInstantly(options) { restored = options?.restored === true; this.options.onReveal(); }
    destroy() {}
  }
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    api: { completeScratch: async () => { completeCalls += 1; } },
    analytics: { track() {} },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    ScratchCard: ScratchCardMock,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  const router = { isCurrent: () => true, navigate() {}, announceStateChange() {} };
  view.renderToken = 1;
  view.renderScratch(container, router, { draw_id: 'draw-1', pouch_index: 2, is_won: false, scratch_completed: true, prize: {} });
  await Promise.resolve();
  assert.equal(completeCalls, 0);
  assert.equal(restored, true, 'restoring a server result must not count as a new scratch');
  assert.match(nodes.get('#restored-pouch').textContent, /3번 주머니/);
  assert.equal(nodes.get('#post-reveal-actions').hidden, false);
  assert.equal(nodes.get('#scratch-title').textContent, '복주머니 결과를 확인하세요');
  assert.equal(nodes.get('#scratch-instruction').textContent, '이미 정해진 결과예요. 게임 기록과 Gemini 혜택은 계속 확인할 수 있어요.');
  assert.doesNotMatch(nodes.get('#scratch-instruction').textContent, /긁/);
  assert.equal(nodes.get('#btn-after-draw').textContent, '혜택 안내 보기');
});

test('scratch result enters the accessibility tree only when revealed and canvas leaves keyboard order', async () => {
  const selectors = ['#scratch-title', '#scratch-instruction', '#result-prize-img', '#result-prize-title', '#result-prize-sub', '#btn-after-draw', '#btn-instant-reveal', '#restored-pouch', '#post-reveal-actions', '#scratch-save-status', '#scratch-canvas', '#scratch-result-content'];
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  const exposureStates = [];
  class ScratchCardMock {
    constructor(_canvas, options) { this.options = options; }
    revealInstantly() { this.revealPromise = this.options.onReveal(); return this.revealPromise; }
    destroy() {}
  }
  const resultContent = nodes.get('#scratch-result-content');
  const canvas = nodes.get('#scratch-canvas');
  const document = { activeElement: canvas };
  nodes.get('#btn-after-draw').focus = () => { document.activeElement = nodes.get('#btn-after-draw'); };
  const setAttribute = canvas.setAttribute.bind(canvas);
  canvas.setAttribute = (name, value) => {
    if (name === 'aria-hidden' && value === 'true') assert.notEqual(document.activeElement, canvas, 'move focus before hiding the scratch control');
    setAttribute(name, value);
  };
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    document,
    api: { createRequestId: () => 'scratch-event-1', completeScratch: async () => { throw new Error('save unavailable'); } },
    analytics: { track(name) { if (name === 'draw_result_viewed') exposureStates.push({ hidden: resultContent.getAttribute('aria-hidden'), inert: resultContent.inert, tabIndex: canvas.tabIndex }); } },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    ScratchCard: ScratchCardMock,
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  const routes = [];
  const router = { isCurrent: () => true, navigate: (route) => routes.push(route), announceStateChange() {} };
  view.renderToken = 1;
  view.renderScratch(container, router, { draw_id: 'draw-2', pouch_index: 0, is_won: true, scratch_completed: false, prize: { name: '테스트 경품' } });
  assert.match(container.innerHTML, /복권을 긁어 결과를 확인하세요/);
  assert.match(container.innerHTML, /화면을 긁거나 아래 버튼/);
  assert.equal(resultContent.getAttribute('aria-hidden'), 'true');
  assert.equal(resultContent.inert, true);
  assert.equal(canvas.tabIndex, 0);
  nodes.get('#btn-instant-reveal').onclick();
  await view.scratchCard.revealPromise;
  assert.equal(resultContent.getAttribute('aria-hidden'), 'false');
  assert.equal(resultContent.inert, false);
  assert.equal(canvas.tabIndex, -1);
  assert.equal(canvas.getAttribute('aria-hidden'), 'true');
  assert.equal(document.activeElement, nodes.get('#btn-after-draw'));
  assert.equal(nodes.get('#scratch-title').textContent, '복주머니 결과를 확인하세요');
  assert.equal(nodes.get('#scratch-instruction').textContent, '이미 정해진 결과예요. 수령함에서 접수·진행 상태를 확인할 수 있어요.');
  assert.doesNotMatch(nodes.get('#scratch-instruction').textContent, /긁/);
  assert.equal(nodes.get('#btn-after-draw').textContent, '수령함에서 확인하기');
  assert.equal(nodes.get('#scratch-save-status').textContent, '결과는 그대로 유지됩니다. 저장 연결을 다시 시도해 주세요.');
  assert.equal(nodes.get('#btn-instant-reveal').textContent, '저장 다시 시도');
  nodes.get('#btn-after-draw').onclick();
  assert.deepEqual(routes, ['claims']);
  assert.deepEqual(JSON.parse(JSON.stringify(exposureStates)), [{ hidden: 'false', inert: false, tabIndex: -1 }]);
});

test('guide card exposure and outbound click use distinct events and stop after cleanup', () => {
  const events = [];
  const observers = [];
  class ObserverMock {
    constructor(callback) { this.callback = callback; this.targets = new Set(); this.disconnected = false; observers.push(this); }
    observe(target) { this.targets.add(target); }
    unobserve(target) { this.targets.delete(target); }
    disconnect() { this.disconnected = true; this.targets.clear(); }
    trigger(target, ratio = 1) {
      if (!this.disconnected && this.targets.has(target)) this.callback([{ target, isIntersecting: ratio > 0, intersectionRatio: ratio }]);
    }
  }
  const link = node();
  const guideList = node();
  const nodes = new Map([
    ['#btn-go-benefit', link], ['#btn-copy-benefit', node()], ['#btn-share-benefit', node()],
    ['#benefit-fallback', node()], ['#content-guide-list', guideList],
  ]);
  const documentMock = { hidden: false, createElement: () => node() };
  const view = loadView('public/js/views/benefit_view.js', 'BenefitView', {
    analytics: { track: (name, dimensions = {}) => events.push({ name, dimensions }) },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    document: documentMock,
    navigator: { clipboard: { writeText: async () => {} } },
    IntersectionObserver: ObserverMock,
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  view.render(container, { config: {
    benefit_url: 'https://gemini.google.com/students',
    content_guides: [{ id: 'study_note', title: '제미나이 노트북', description: '학습 루틴', url: 'https://example.test/study', available: true }],
  } });
  const card = guideList.children[0];
  const action = card.children[2];
  const contentObserver = observers.find((observer) => observer.targets.has(card));
  contentObserver.trigger(card, 0.49);
  contentObserver.trigger(card, 0.5);
  contentObserver.trigger(card, 1);
  action.onclick();
  assert.deepEqual(JSON.parse(JSON.stringify(events.filter(({ name }) => name.startsWith('content_')))), [
    { name: 'content_viewed', dimensions: { content: 'study_note', position: 'benefit_guides' } },
    { name: 'content_clicked', dimensions: { content: 'study_note', position: 'benefit_guides' } },
  ]);
  view.cleanup();
  contentObserver.trigger(card, 1);
  assert.equal(events.filter(({ name }) => name === 'content_viewed').length, 1);
  assert.equal(contentObserver.disconnected, true);
});
