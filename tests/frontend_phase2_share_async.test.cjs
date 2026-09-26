const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((resolvePromise, rejectPromise) => {
    resolve = resolvePromise;
    reject = rejectPromise;
  });
  return { promise, resolve, reject };
}

function node(tag = 'div', textContent = '') {
  return {
    tag, children: [], textContent, href: '', hidden: false, disabled: false, onclick: null, attrs: {},
    classList: { add() {} },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    removeAttribute(name) { delete this.attrs[name]; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
  };
}

function loadView(file, exportName, globals) {
  const context = { console, URL, ...globals };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, file), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace(`export const ${exportName} =`, 'globalThis.__view =');
  vm.runInNewContext(source, context, { filename: file });
  return context.__view;
}

function inviteNodes() {
  const selectors = [
    '#invite-title', '#invite-description', '#invite-score', '#invite-balance', '#ticket-granted',
    '#ticket-used', '#ticket-refunded', '#valid-visits', '#invite-cooldown', '#btn-invite-draw',
    '#btn-share-native', '#btn-copy-link', '#share-fallback',
  ];
  return new Map(selectors.map((selector) => [selector, node('div', selector === '#share-fallback' ? 'fresh invite help' : '')]));
}

function createInviteHarness(navigatorMock) {
  const events = [];
  const toasts = [];
  let nodes = new Map();
  let requestIndex = 0;
  const analytics = {
    screen: 'invite', screenViewId: 'screen_invite_origin', activeMs: 417,
    currentActiveMs() { return this.activeMs; },
    track(name, dimensions = {}, extra = {}) { events.push({ name, dimensions, extra: { ...extra } }); },
  };
  const container = {
    _html: '',
    set innerHTML(value) { this._html = value; nodes = value.includes('btn-share-native') ? inviteNodes() : new Map(); },
    get innerHTML() { return this._html; },
    querySelector(selector) { return nodes.get(selector); },
    replaceChildren() {}, appendChild() {},
  };
  const api = {
    async getReferralInfo() {
      return { invite_url: 'https://example.test/invite/abcdefghijkl', invitation_balance: 0, ticket_totals: {}, valid_visits: 0 };
    },
    createRequestId() { requestIndex += 1; return `share_${requestIndex}`; },
  };
  const view = loadView('public/js/views/invite_view.js', 'InviteView', {
    api, analytics, navigator: navigatorMock,
    ui: { text(target, value) { target.textContent = String(value); }, showToast(message) { toasts.push(message); } },
    window: { location: { origin: 'https://example.test' } },
    document: { createElement: (tag) => node(tag) },
  });
  const router = {
    state: { bestScore: 321, draw: { status: 'LOCKED' } }, shareContext: 'retry_invite',
    isCurrent: () => true, navigate() {},
  };
  return { analytics, container, events, getNodes: () => nodes, router, toasts, view };
}

function benefitNodes() {
  return new Map([
    ['#btn-go-benefit', node('a')], ['#btn-copy-benefit', node('button')], ['#btn-share-benefit', node('button')],
    ['#benefit-fallback', node('p', 'fresh benefit help')], ['#content-guide-list', node('div')],
  ]);
}

function createBenefitHarness(navigatorMock) {
  const events = [];
  const toasts = [];
  let nodes = new Map();
  const analytics = {
    screen: 'benefit', screenViewId: 'screen_benefit_origin', activeMs: 923,
    currentActiveMs() { return this.activeMs; },
    track(name, dimensions = {}, extra = {}) { events.push({ name, dimensions, extra: { ...extra } }); },
  };
  const container = {
    _html: '',
    set innerHTML(value) { this._html = value; nodes = benefitNodes(); },
    get innerHTML() { return this._html; },
    querySelector(selector) { return nodes.get(selector); },
  };
  const document = { hidden: false, createElement: (tag) => node(tag), addEventListener() {}, removeEventListener() {} };
  const view = loadView('public/js/views/benefit_view.js', 'BenefitView', {
    analytics, document, navigator: navigatorMock, IntersectionObserver: undefined,
    ui: { text(target, value) { target.textContent = String(value); }, showToast(message) { toasts.push(message); } },
  });
  const router = { config: { official_url: 'https://gemini.google.com/students' } };
  return { analytics, container, events, getNodes: () => nodes, router, toasts, view };
}

function shareEvents(events) {
  return events.filter(({ name }) => name === 'share_attempted');
}

test('invite deferred copy keeps its originating context, ignores duplicates, and cannot toast into a rerender', async () => {
  const copy = deferred();
  let copyCalls = 0;
  const harness = createInviteHarness({ clipboard: { writeText() { copyCalls += 1; return copy.promise; } } });
  await harness.view.render(harness.container, harness.router, 'same-token');
  const oldCopyButton = harness.getNodes().get('#btn-copy-link');
  const first = oldCopyButton.onclick();
  const duplicate = oldCopyButton.onclick();
  assert.equal(copyCalls, 1);

  harness.analytics.screen = 'home';
  harness.analytics.screenViewId = 'screen_home_new';
  harness.analytics.activeMs = 12;
  await harness.view.render(harness.container, harness.router, 'same-token');
  const freshFallback = harness.getNodes().get('#share-fallback');
  copy.resolve();
  await Promise.all([first, duplicate]);

  const outcomes = shareEvents(harness.events);
  assert.deepEqual(outcomes.map(({ dimensions }) => dimensions.status), ['attempted', 'copied']);
  assert.deepEqual(outcomes.map(({ dimensions }) => dimensions.share_id), ['share_1', 'share_1']);
  assert.deepEqual(outcomes.map(({ extra }) => extra), [
    { screen: 'invite', screenViewId: 'screen_invite_origin', activeMs: 417 },
    { screen: 'invite', screenViewId: 'screen_invite_origin', activeMs: 417 },
  ]);
  assert.equal(harness.toasts.length, 0);
  assert.equal(freshFallback.textContent, 'fresh invite help');
});

test('invite deferred native cancellation is recorded on the originating attempt without touching the new render', async () => {
  const native = deferred();
  let shareCalls = 0;
  const harness = createInviteHarness({ share(payload) { shareCalls += 1; assert.match(payload.url, /share=share_1/); return native.promise; } });
  await harness.view.render(harness.container, harness.router, 'render-1');
  const oldShareButton = harness.getNodes().get('#btn-share-native');
  const first = oldShareButton.onclick();
  const duplicate = oldShareButton.onclick();
  assert.equal(shareCalls, 1, 'native share must be invoked synchronously from the user click');

  harness.analytics.screen = 'ranking';
  harness.analytics.screenViewId = 'screen_ranking_new';
  harness.analytics.activeMs = 50;
  await harness.view.render(harness.container, harness.router, 'render-2');
  const freshFallback = harness.getNodes().get('#share-fallback');
  native.reject(Object.assign(new Error('closed'), { name: 'AbortError' }));
  await Promise.all([first, duplicate]);

  const outcomes = shareEvents(harness.events);
  assert.deepEqual(outcomes.map(({ dimensions }) => dimensions.status), ['attempted', 'cancelled']);
  assert.ok(outcomes.every(({ extra }) => extra.screenViewId === 'screen_invite_origin' && extra.activeMs === 417));
  assert.equal(harness.toasts.length, 0);
  assert.equal(freshFallback.textContent, 'fresh invite help');
});

test('benefit deferred copy failure keeps its context and cannot rewrite a replacement screen', async () => {
  const copy = deferred();
  let copyCalls = 0;
  const harness = createBenefitHarness({ clipboard: { writeText() { copyCalls += 1; return copy.promise; } } });
  harness.view.render(harness.container, harness.router);
  const oldCopyButton = harness.getNodes().get('#btn-copy-benefit');
  const first = oldCopyButton.onclick();
  const duplicate = oldCopyButton.onclick();
  assert.equal(copyCalls, 1);

  harness.analytics.screen = 'game';
  harness.analytics.screenViewId = 'screen_game_new';
  harness.analytics.activeMs = 31;
  harness.view.render(harness.container, harness.router);
  const freshFallback = harness.getNodes().get('#benefit-fallback');
  copy.reject(new Error('denied'));
  await Promise.all([first, duplicate]);

  const outcomes = shareEvents(harness.events);
  assert.deepEqual(outcomes.map(({ dimensions }) => dimensions.status), ['attempted', 'failed']);
  assert.ok(outcomes.every(({ extra }) => extra.screen === 'benefit' && extra.screenViewId === 'screen_benefit_origin' && extra.activeMs === 923));
  assert.equal(harness.toasts.length, 0);
  assert.equal(freshFallback.textContent, 'fresh benefit help');
});

test('benefit deferred native success invokes once and keeps share_sheet_closed on the original view', async () => {
  const native = deferred();
  let shareCalls = 0;
  const harness = createBenefitHarness({ share(payload) { shareCalls += 1; assert.equal(payload.url, 'https://gemini.google.com/students'); return native.promise; } });
  harness.view.render(harness.container, harness.router);
  const oldShareButton = harness.getNodes().get('#btn-share-benefit');
  const first = oldShareButton.onclick();
  const duplicate = oldShareButton.onclick();
  assert.equal(shareCalls, 1, 'native share must be invoked synchronously from the user click');

  harness.analytics.screen = 'home';
  harness.analytics.screenViewId = 'screen_home_new';
  harness.analytics.activeMs = 7;
  harness.view.render(harness.container, harness.router);
  const freshFallback = harness.getNodes().get('#benefit-fallback');
  native.resolve();
  await Promise.all([first, duplicate]);

  const outcomes = shareEvents(harness.events);
  assert.deepEqual(outcomes.map(({ dimensions }) => dimensions.status), ['attempted', 'share_sheet_closed']);
  assert.ok(outcomes.every(({ extra }) => extra.screenViewId === 'screen_benefit_origin' && extra.activeMs === 923));
  assert.equal(freshFallback.textContent, 'fresh benefit help');
});
