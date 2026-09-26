const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

test('game session creation carries the exact observation and visit context', async () => {
  const requests = [];
  const original = { fetch: global.fetch, crypto: global.crypto };
  global.crypto = { randomUUID: () => '12345678-1234-1234-1234-123456789abc' };
  global.fetch = async (url, options) => {
    requests.push({ url, options });
    return { ok: true, json: async () => ({ session_id: 'session-1' }) };
  };
  try {
    const moduleUrl = `data:text/javascript;base64,${Buffer.from(read('public/js/api.js')).toString('base64')}`;
    const { api } = await import(moduleUrl);
    api.setTrackingContext('obs_context_12345678', 'visit_context_12345678');
    await api.createSession();
    const body = JSON.parse(requests[0].options.body);
    assert.equal(requests[0].url, '/api/game-sessions');
    assert.equal(body.observation_id, 'obs_context_12345678');
    assert.equal(body.visit_session_id, 'visit_context_12345678');
    assert.match(body.event_id, /^evt_/);
  } finally {
    global.fetch = original.fetch;
    global.crypto = original.crypto;
  }
});

test('loading ready remains attached to the loading view after the first screen renders', () => {
  let now = 100;
  const trackingContexts = [];
  const api = {
    createRequestId: (() => { let index = 0; return (prefix) => `${prefix}_acceptance_${++index}`; })(),
    setTrackingContext: (...args) => trackingContexts.push(args),
    postEvents: async () => ({ accepted: 0 }),
  };
  const listeners = {};
  const context = {
    __api: api,
    performance: { now: () => now },
    document: { hidden: false, addEventListener: (name, fn) => { listeners[name] = fn; } },
    window: { addEventListener: (name, fn) => { listeners[name] = fn; } },
    sessionStorage: { getItem: () => null, setItem: () => {} },
    setInterval: () => 1,
    console,
  };
  context.globalThis = context;
  let source = read('public/js/analytics.js')
    .replace("import { api } from './api.js';", 'const api = globalThis.__api;')
    .replace('export const analytics = new Analytics();\nexport { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', 'globalThis.__analytics = new Analytics();');
  vm.runInNewContext(source, context, { filename: 'analytics.js' });
  const analytics = context.__analytics;
  const loadingViewId = analytics.screenViewId;
  assert.equal(trackingContexts.length, 0);
  analytics.setParticipantReady({ is_new: true });
  now = 600;
  analytics.enterScreen('home');
  now = 650;
  analytics.setLoadingReady();
  const participantReady = analytics.queue.find((event) => event.name === 'participant_ready');
  const loadingReady = analytics.queue.find((event) => event.name === 'loading_ready');
  assert.deepEqual(trackingContexts[0], [analytics.observationId, analytics.visitSessionId]);
  assert.equal(participantReady.screen, 'loading');
  assert.equal(loadingReady.screen, 'loading');
  assert.equal(loadingReady.screen_view_id, loadingViewId);
  assert.ok(loadingReady.active_ms >= participantReady.active_ms);
  assert.ok(analytics.queue.findIndex((event) => event.name === 'screen_entered') < analytics.queue.findIndex((event) => event.name === 'loading_ready'));
});

test('Gemini benefit copy and native share record observable outcomes only', async () => {
  const events = [];
  const toasts = [];
  const nodes = new Map();
  const node = () => ({ onclick: null, href: '', disabled: false, hidden: false, textContent: '', children: [], classList: { add() {} }, append(...children) { this.children.push(...children); }, appendChild(child) { this.children.push(child); }, removeAttribute() {}, setAttribute() {} });
  for (const selector of ['#btn-go-benefit', '#btn-copy-benefit', '#btn-share-benefit', '#btn-kakao-benefit', '#benefit-official-url', '#benefit-fallback', '#content-guide-list']) nodes.set(selector, node());
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  const context = {
    __analytics: { track: (name, dimensions = {}) => events.push({ name, dimensions }) },
    __ui: { text: (target, value) => { target.textContent = String(value); }, showToast: (message) => toasts.push(message) },
    document: { hidden: false, createElement: () => node(), addEventListener() {}, removeEventListener() {} },
    navigator: {
      clipboard: { writeText: async (value) => { assert.equal(value, 'https://gemini.google.com/students'); } },
      share: async ({ url }) => { assert.equal(url, 'https://gemini.google.com/students'); },
    },
    IntersectionObserver: undefined,
    console,
  };
  context.globalThis = context;
  const source = read('public/js/views/benefit_view.js')
    .replace("import { analytics } from '../analytics.js';", 'const analytics = globalThis.__analytics;')
    .replace("import { ui } from '../ui.js';", 'const ui = globalThis.__ui;')
    .replace("import { loadKakaoSdk } from '../referral_share.js';", 'const loadKakaoSdk = async () => null;')
    .replace('export const BenefitView =', 'globalThis.__BenefitView =');
  vm.runInNewContext(source, context, { filename: 'benefit_view.js' });
  context.__BenefitView.render(container, { config: { benefit_url: 'https://gemini.google.com/students' } });
  await nodes.get('#btn-copy-benefit').onclick();
  await nodes.get('#btn-share-benefit').onclick();
  const outcomes = events.filter((event) => event.name === 'share_attempted').map((event) => event.dimensions);
  assert.deepEqual(JSON.parse(JSON.stringify(outcomes)), [
    { source: 'gemini', position: 'benefit_main', share_method: 'copy', status: 'attempted' },
    { source: 'gemini', position: 'benefit_main', share_method: 'copy', status: 'copied' },
    { source: 'gemini', position: 'benefit_main', share_method: 'native', status: 'attempted' },
    { source: 'gemini', position: 'benefit_main', share_method: 'native', status: 'share_sheet_closed' },
  ]);
  assert.equal(outcomes.some((item) => item.status === 'delivered'), false);
  assert.equal(toasts.length, 1);
});
