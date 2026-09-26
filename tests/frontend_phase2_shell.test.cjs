const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

function loadRouter(href) {
  const historyCalls = [];
  const windowListeners = {};
  const analyticsCalls = [];
  const container = {
    childElementCount: 0,
    replaceChildren() { this.childElementCount = 0; },
  };
  const elements = {
    'view-container': container,
    'header-ticket-pill': { textContent: '', title: '' },
    'splash-screen': { classList: { toggle() {}, add() {} }, dataset: {}, setAttribute() {} },
    'splash-status-text': { textContent: '' },
    'splash-retry': { hidden: true, onclick: null },
  };
  const blankView = { render(target) { target.childElementCount = 1; }, cleanup() {} };
  const context = {
    api: { createRequestId: (prefix) => `${prefix}_12345678` },
    analytics: {
      observationId: 'obs_12345678',
      setEntryAttribution: (value) => analyticsCalls.push(value),
      enterScreen() {},
    },
    startVercelAnalytics() {},
    ui: { hideModal() {} },
    HomeView: blankView, GameView: blankView, ResultView: blankView, DrawView: blankView,
    PrizeView: blankView, RankingView: blankView, InviteView: blankView, BenefitView: blankView,
    document: {
      hidden: false,
      fonts: { ready: Promise.resolve() },
      getElementById: (id) => elements[id] || null,
      querySelectorAll: () => [],
      addEventListener() {},
    },
    window: {
      location: { href },
      addEventListener: (name, listener) => { windowListeners[name] = listener; },
      scrollTo() {},
      matchMedia: () => ({ matches: false }),
    },
    history: {
      replaceState: (state, _unused, url) => historyCalls.push({ method: 'replace', state, url }),
      pushState: (state, _unused, url) => historyCalls.push({ method: 'push', state, url }),
    },
    navigator: {},
    BroadcastChannel: undefined,
    URL,
    setTimeout,
    clearTimeout,
    setInterval,
    clearInterval,
    Date,
    console,
  };
  context.globalThis = context;
  const source = read('public/js/app.js')
    .replace(/^import .*;\s*$/gm, '')
    .replace(/document\.addEventListener\('DOMContentLoaded',[\s\S]*$/, '')
    .concat('\nglobalThis.AppRouter = AppRouter;');
  vm.runInNewContext(source, context, { filename: 'app.js' });
  return { router: new context.AppRouter(), historyCalls, analyticsCalls, windowListeners, context };
}

test('entry parsing accepts record_share once and removes invite and attribution values from browser history', () => {
  const loaded = loadRouter('https://example.test/invite/InviteCode_123?invite=InviteCode_123&link=record_share&share=share_12345678&channel=campus&campaign=fall&view=ranking');
  const request = loaded.router.parseInitialRequest();
  assert.equal(request.observation.link_kind, 'record_share');
  assert.equal(request.inviteCode, 'InviteCode_123');
  assert.deepEqual(JSON.parse(JSON.stringify(loaded.analyticsCalls[0])), { link_kind: 'record_share', channel: 'campus', campaign_code: 'fall', share_id: 'share_12345678' });
  assert.deepEqual(JSON.parse(JSON.stringify(loaded.historyCalls.at(-1))), { method: 'replace', state: { view: 'ranking' }, url: '/?view=ranking' });
  assert.doesNotMatch(loaded.historyCalls.at(-1).url, /invite|share|channel|campaign|InviteCode/);
});

test('initial brand flow has the required copy and a static reduced-motion presentation', () => {
  const html = read('public/index.html');
  const css = read('public/css/style.css');
  const app = read('public/js/app.js');
  assert.match(html, /Google Student Ambassador/);
  assert.match(html, /Google AI로 만든/);
  assert.match(html, /한 판 즐기고,[\s\S]*경품에 도전하세요\./);
  assert.match(html, /공룡 게임 한 판![\s\S]*복주머니를 고르고[\s\S]*복권을 긁어 결과 확인![\s\S]*삼텐바이미부터 상품권까지/);
  assert.doesNotMatch(html, /프리뷰|시안|게임은 누구나 참여 가능 · 경품은 대학생 대상/);
  assert.match(app, /prefers-reduced-motion: reduce/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)[\s\S]*animation: none !important/);
  assert.match(app, /Dino-Dark\.png[\s\S]*Heart-Light\.png/);
});

test('five-second intro completion stays separate from data readiness, including reduced motion', async () => {
  for (const reduced of [false, true]) {
    const { router, context } = loadRouter('https://example.test/');
    const timers = [];
    const milestones = [];
    context.window.matchMedia = () => ({ matches: reduced });
    context.setTimeout = (callback, delay) => { timers.push({ callback, delay }); };
    context.analytics.setLoadingIntroCompleted = (data) => milestones.push(data);
    const intro = router.playInitialIntro();
    assert.equal(timers.length, 1);
    assert.equal(timers[0].delay, 5000);
    assert.equal(router.loadingState.intro, false);
    assert.equal(milestones.length, 0);
    timers[0].callback();
    await intro;
    assert.equal(router.loadingState.intro, true);
    assert.equal(router.loadingState.data, false);
    assert.equal(milestones.length, 1);
    assert.equal(milestones[0].reduced_motion, reduced);
    assert.equal(context.document.getElementById('splash-screen').dataset.state, 'intro-complete');
  }
});

test('router writes public screen-only history and popstate renders without creating a duplicate entry', () => {
  const loaded = loadRouter('https://example.test/');
  loaded.router.initialized = true;
  loaded.router.bindNavigation();
  loaded.router.navigate('ranking');
  assert.deepEqual(JSON.parse(JSON.stringify(loaded.historyCalls.at(-1))), { method: 'push', state: { view: 'ranking' }, url: '/?view=ranking' });
  const count = loaded.historyCalls.length;
  loaded.windowListeners.popstate({ state: { view: 'benefit' } });
  assert.equal(loaded.router.currentView, 'benefit');
  assert.equal(loaded.historyCalls.length, count);
});

test('a synchronous result redirect keeps the destination URL and render promise', async () => {
  const loaded = loadRouter('https://example.test/?view=result');
  loaded.router.views.result = {
    render(_container, router) { router.navigate('home', { replace: true }); },
  };
  const outer = loaded.router.navigate('result');
  const destination = loaded.router.activeRenderPromise;
  assert.equal((await outer).current, false);
  assert.equal((await destination).current, true);
  assert.equal(loaded.router.currentView, 'home');
  assert.deepEqual(JSON.parse(JSON.stringify(loaded.historyCalls)), [
    { method: 'replace', state: { view: 'home' }, url: '/' },
  ]);
});

test('navigation exposes the current page and preserves modified link clicks', async () => {
  const loaded = loadRouter('https://example.test/');
  const links = ['home', 'ranking', 'claims', 'invite', 'benefit'].map((view) => ({
    dataset: { view }, attributes: {}, active: false,
    classList: { toggle(_name, value) { links.find((link) => link.dataset.view === view).active = value; } },
    setAttribute(name, value) { this.attributes[name] = value; },
    removeAttribute(name) { delete this.attributes[name]; },
    addEventListener(_name, callback) { this.click = callback; },
  }));
  loaded.context.document.querySelectorAll = () => links;
  loaded.router.initialized = true;
  loaded.router.bindNavigation();
  await loaded.router.navigate('home');
  const historyCount = loaded.historyCalls.length;
  let prevented = 0;
  for (const modifier of ['metaKey', 'ctrlKey', 'shiftKey', 'altKey']) {
    links[1].click({ [modifier]: true, preventDefault() { prevented += 1; } });
  }
  assert.equal(prevented, 0);
  assert.equal(loaded.historyCalls.length, historyCount);
  links[1].click({ button: 0, preventDefault() { prevented += 1; } });
  assert.equal(prevented, 1);
  assert.equal(loaded.router.currentView, 'ranking');
  assert.deepEqual(links.filter((link) => link.attributes['aria-current'] === 'page').map((link) => link.dataset.view), ['ranking']);
  loaded.windowListeners.popstate({ state: { view: 'home' } });
  assert.deepEqual(links.filter((link) => link.attributes['aria-current'] === 'page').map((link) => link.dataset.view), ['home']);
});

test('initial loading_ready and splash dismissal wait for the actual initial view render', async () => {
  const loaded = loadRouter('https://example.test/?view=ranking');
  const events = [];
  let releaseRender;
  loaded.router.initialRequest = { requestedView: 'ranking', inviteCode: null };
  loaded.router.introPromise = Promise.resolve();
  loaded.router.loadInitialData = async () => ({ participant: {} });
  loaded.router.installInviteState = () => {};
  loaded.router.hideSplash = () => events.push('splash_hidden');
  loaded.context.analytics.setLoadingReady = () => events.push('loading_ready');
  loaded.router.views.ranking = {
    render: () => new Promise((resolve) => { releaseRender = () => { events.push('ranking_rendered'); resolve(); }; }),
    cleanup() {},
  };

  const initializing = loaded.router.init();
  await new Promise((resolve) => setImmediate(resolve));
  assert.deepEqual(events, []);
  assert.equal(loaded.router.initialized, false);
  releaseRender();
  await initializing;
  assert.deepEqual(events, ['ranking_rendered', 'loading_ready', 'splash_hidden']);
  assert.equal(loaded.router.initialized, true);
});

test('retry keeps focus on the loading status, then the page or the retry button', async () => {
  for (const fails of [false, true]) {
    const { router, context } = loadRouter('https://example.test/');
    const focused = [];
    const status = context.document.getElementById('splash-status-text');
    const retry = context.document.getElementById('splash-retry');
    status.focus = () => focused.push('status');
    retry.focus = () => focused.push('retry');
    router.container.focus = () => focused.push('page');
    router.initialRequest = { requestedView: 'home', inviteCode: null };
    router.introPromise = Promise.resolve();
    router.loadInitialData = async () => {
      if (fails) throw new Error('connection failed');
      return { participant: {} };
    };
    router.installInviteState = () => {};
    context.analytics.setLoadingReady = () => {};
    router.renderInitError(new Error('initial connection failed'));
    await retry.onclick();
    assert.deepEqual(focused, ['status', fails ? 'retry' : 'page']);
    assert.equal(status.tabIndex, -1);
    assert.equal(retry.hidden, !fails);
    assert.equal(router.initialized, !fails);
    if (!fails) assert.equal(router.container.tabIndex, -1);
  }
});

test('render promises are race guarded and an older route cannot become current after a newer route', async () => {
  const loaded = loadRouter('https://example.test/');
  let releaseRanking;
  let releaseBenefit;
  loaded.router.views.ranking = { render: () => new Promise((resolve) => { releaseRanking = resolve; }), cleanup() {} };
  loaded.router.views.benefit = { render: () => new Promise((resolve) => { releaseBenefit = resolve; }), cleanup() {} };

  const ranking = loaded.router.navigate('ranking');
  const benefit = loaded.router.navigate('benefit');
  releaseRanking();
  const stale = await ranking;
  assert.equal(stale.current, false);
  assert.equal(loaded.router.currentView, 'benefit');
  releaseBenefit();
  const latest = await benefit;
  assert.equal(latest.ok, true);
  assert.equal(latest.current, true);
  assert.equal(latest.error, null);
  assert.equal(loaded.router.currentView, 'benefit');
});

test('ticket header shows unlimited only for an explicit server flag and resets after revocation', () => {
  const { router, context } = loadRouter('https://example.test/');
  router.state.tickets = { initial: 0, invitation: 0, available_total: 0, unlimited_play: true };
  router.updateNav();
  assert.equal(context.document.getElementById('header-ticket-pill').textContent, '🎟️ 무제한');
  router.state.tickets = { initial: 0, invitation: 0, available_total: 0 };
  router.updateNav();
  assert.equal(context.document.getElementById('header-ticket-pill').textContent, '🎟️ 0장');
});

test('overlapping resume refreshes share one server read', async () => {
  const loaded = loadRouter('https://example.test/');
  let reads = 0;
  let release;
  loaded.context.api.getMe = () => {
    reads += 1;
    return new Promise((resolve) => { release = resolve; });
  };
  const first = loaded.router.refreshState({ quiet: true });
  const second = loaded.router.refreshState({ quiet: true });
  assert.equal(reads, 1);
  release({ tickets: { available_total: 1 }, participant: {} });
  await Promise.all([first, second]);
  assert.equal(reads, 1);
});

test('a server refresh updates the visible view without navigation or replacing its controls', async () => {
  const loaded = loadRouter('https://example.test/');
  loaded.router.initialized = true;
  loaded.router.currentView = 'home';
  let updates = 0;
  loaded.router.views.home = {
    updateState(container, router) {
      assert.equal(container, router.container);
      assert.equal(router.state.tickets.invitation, 1);
      updates += 1;
    },
    render() { assert.fail('refresh must not rebuild the screen'); },
  };
  loaded.context.api.getMe = async () => ({ tickets: { initial: 0, invitation: 1 } });
  await loaded.router.refreshState({ quiet: true });
  assert.equal(updates, 1);
  assert.equal(loaded.historyCalls.length, 0);
});

test('a newly reached cooldown is announced once on a safe screen and never interrupts a game or form', async () => {
  const loaded = loadRouter('https://example.test/');
  const notices = [];
  loaded.context.ui.showModal = (notice) => notices.push(notice);
  loaded.context.api.acknowledgeCooldown = async () => ({});
  loaded.router.state.tickets = { cooldown_until: new Date(Date.now() + 3600000).toISOString(), cooldown_notice_pending: true };
  loaded.router.currentView = 'game';
  loaded.router.showCooldownNotice();
  assert.equal(notices.length, 0);
  loaded.router.currentView = 'home';
  const originalGet = loaded.context.document.getElementById;
  loaded.context.document.getElementById = (id) => id === 'common-modal-overlay' ? {} : originalGet(id);
  loaded.router.showCooldownNotice();
  assert.equal(notices.length, 0);
  loaded.context.document.getElementById = originalGet;
  loaded.router.showCooldownNotice();
  loaded.router.showCooldownNotice();
  assert.equal(notices.length, 1);
  await notices[0].onConfirm();
  assert.equal(loaded.router.state.tickets.cooldown_notice_pending, false);
  loaded.router.state.tickets = { cooldown_until: new Date(Date.now() + 7200000).toISOString(), cooldown_notice_pending: true };
  loaded.router.showCooldownNotice();
  assert.equal(notices.length, 2);
  loaded.router.state.tickets = { cooldown_until: '2000-01-01T00:00:00Z', cooldown_notice_pending: true };
  loaded.router.showCooldownNotice();
  assert.equal(notices.length, 2);
});

test('loading milestones are independently deduplicated and remain attributed to loading', () => {
  let now = 0;
  const api = { createRequestId: (prefix) => `${prefix}_${++now}`, setTrackingContext() {}, postEvents: async () => ({}) };
  const context = {
    __api: api,
    performance: { now: () => now * 100 },
    document: { hidden: false, addEventListener() {} },
    window: { addEventListener() {} },
    sessionStorage: { getItem: () => null, setItem() {} },
    setInterval: () => 1,
    console,
  };
  context.globalThis = context;
  const source = read('public/js/analytics.js')
    .replace("import { api } from './api.js';", 'const api = globalThis.__api;')
    .replace('export const analytics = new Analytics();\nexport { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', 'globalThis.analytics = new Analytics();');
  vm.runInNewContext(source, context, { filename: 'analytics.js' });
  context.analytics.setLoadingDataReady();
  context.analytics.setLoadingDataReady();
  context.analytics.setLoadingIntroCompleted({ reduced_motion: true });
  const milestones = context.analytics.queue.filter(({ name }) => name.startsWith('loading_') && name !== 'loading_checkpoint');
  assert.deepEqual([...milestones.map(({ name }) => name)], ['loading_data_ready', 'loading_intro_completed']);
  assert.ok(milestones.every(({ screen }) => screen === 'loading'));
  assert.equal(milestones[1].dimensions.reduced_motion, true);
});

test('view exposure, draw CTA, and scratch accessibility events survive client filtering and match the server contract', () => {
  const api = { createRequestId: (prefix) => `${prefix}_phase2_contract`, setTrackingContext() {}, postEvents: async () => ({}) };
  const context = {
    __api: api,
    performance: { now: () => 100 },
    document: { hidden: false, addEventListener() {} },
    window: { addEventListener() {} },
    sessionStorage: { getItem: () => null, setItem() {} },
    setInterval: () => 1,
    console,
  };
  context.globalThis = context;
  const source = read('public/js/analytics.js')
    .replace("import { api } from './api.js';", 'const api = globalThis.__api;')
    .replace('export const analytics = new Analytics();\nexport { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', 'globalThis.analytics = new Analytics();');
  vm.runInNewContext(source, context, { filename: 'analytics.js' });
  context.analytics.track('content_viewed', { content: 'study_note', position: 'benefit_guides' });
  context.analytics.track('scratch_reveal_requested', { action: 'accessibility_button' });
  context.analytics.track('draw_cta_clicked', { source: 'invite', draw_status: 'AVAILABLE' });
  const queued = context.analytics.queue.filter(({ name }) => ['content_viewed', 'scratch_reveal_requested', 'draw_cta_clicked'].includes(name));
  assert.deepEqual([...queued.map(({ name }) => name)], ['content_viewed', 'scratch_reveal_requested', 'draw_cta_clicked']);
  assert.equal(queued[0].dimensions.content, 'study_note');
  assert.equal(queued[0].dimensions.position, 'benefit_guides');
  assert.equal(queued[1].dimensions.action, 'accessibility_button');
  assert.equal(queued[2].dimensions.source, 'invite');
  assert.equal(queued[2].dimensions.draw_status, 'AVAILABLE');

  const server = read('server/operations.py');
  for (const eventName of ['content_viewed', 'scratch_reveal_requested', 'draw_cta_clicked']) assert.match(server, new RegExp(`CLIENT_EVENTS=.*${eventName}`));
  for (const dimension of ['content', 'position', 'action']) assert.match(server, new RegExp(`DIMENSIONS=.*[\"']${dimension}[\"']`));
});

test('game completion forwards verifier version, terminal reason, and item summary', async () => {
  const finishCalls = [];
  const navigations = [];
  const sessionStorage = new Map();
  const context = {
    api: {
      finishSession: async (...args) => { finishCalls.push(args); return { score: 130, best_score: 130, rank: 4, verification: 'VERIFIED' }; },
      createRequestId: () => 'evt_12345678',
    },
    analytics: { track() {} },
    ui: { showToast() {} },
    audio: {},
    DinoGameEngine: class {},
    sessionStorage: { getItem: (key) => sessionStorage.get(key) || null, setItem: (key, value) => sessionStorage.set(key, value), removeItem: (key) => sessionStorage.delete(key) },
    window: {}, document: {}, setTimeout, clearTimeout, setInterval, clearInterval, console,
  };
  context.globalThis = context;
  const source = read('public/js/views/game_view.js')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const GameView =', 'globalThis.GameView =');
  vm.runInNewContext(source, context, { filename: 'game_view.js' });
  const view = context.GameView;
  view.sessionId = 'session-1';
  view.gameVersion = '2.0.0';
  view.engine = { stop() {} };
  const router = {
    state: { tickets: {}, bestScore: 0, rank: null },
    isCurrent: () => true,
    announceStateChange() {}, updateNav() {}, navigate: (viewName) => navigations.push(viewName),
  };
  await view.handleGameOver({ version: '2.0.0', end_reason: 'TIME_LIMIT', score: 130, ticks: 36000, jump_ticks: [], summary: { coins: 3, coin_score: 30, hearts: 2, revives: 2 } }, router, {});
  assert.equal(finishCalls.length, 1);
  assert.deepEqual(JSON.parse(JSON.stringify(finishCalls[0][1])), {
    version: '2.0.0', end_reason: 'TIME_LIMIT', score: 130, ticks: 36000, jump_ticks: [], checkpoints: [],
    summary: { coins: 3, coin_score: 30, hearts: 2, revives: 2 },
  });
  assert.deepEqual(navigations, ['result']);
});

test('leaving during countdown resolves the pending start and clears timers', async () => {
  const context = {
    api: {}, analytics: {}, ui: {}, audio: {}, DinoGameEngine: class {},
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    window: {}, document: {}, setTimeout, clearTimeout, setInterval, clearInterval, console,
  };
  context.globalThis = context;
  const source = read('public/js/views/game_view.js')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const GameView =', 'globalThis.GameView =');
  vm.runInNewContext(source, context, { filename: 'game_view.js' });
  const overlay = { isConnected: true, classList: { add() {}, remove() {} } };
  const number = { textContent: '' };
  const container = { querySelector: (selector) => selector === '#countdown-overlay' ? overlay : number };
  const pending = context.GameView.runCountdown(container, 3);
  context.GameView.cleanup();
  assert.equal(await pending, false);
});
