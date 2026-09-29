const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const source = fs.readFileSync(path.join(root, 'public/js/ga4_analytics.js'), 'utf8');

async function loadModule() {
  return import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}#${Math.random()}`);
}

function memoryStorage() {
  const values = new Map();
  return {
    get length() { return values.size; },
    key(index) { return [...values.keys()][index] ?? null; },
    getItem(key) { return values.get(key) ?? null; },
    setItem(key, value) { values.set(key, String(value)); },
    removeItem(key) { values.delete(key); },
    dump() { return JSON.stringify([...values.entries()]); },
  };
}

function runtime(href = 'https://preview.example.test/?utm_source=kakao&utm_medium=referral&utm_campaign=dino_jump_2026&utm_content=friend_invite&share=private-code&name=Kim', localStorage = memoryStorage()) {
  const url = new URL(href);
  const scripts = [];
  const cookieWrites = [];
  let cookies = '_ga=client-secret; _ga_TEST=session-secret; ordinary=keep';
  const document = {
    head: { appendChild(script) { scripts.push(script); } },
    createElement(name) { assert.equal(name, 'script'); return {}; },
    get cookie() { return cookies; },
    set cookie(value) { cookieWrites.push(value); },
  };
  return {
    location: { href: url.href, origin: url.origin, hostname: url.hostname },
    document,
    localStorage,
    scripts,
    cookieWrites,
  };
}

const previewConfig = (overrides = {}) => ({
  environment: 'preview',
  ga4: {
    enabled: true,
    measurement_id: 'G-ABCDEF1234',
    property_environment: 'test',
    allowed_origins: ['https://preview.example.test'],
    debug_mode: true,
    ...overrides,
  },
});

function gtagCalls(fake) {
  return (fake.dataLayer || []).map((args) => Array.from(args));
}

test('GA4 stays network-silent without consent and rejects environment/property mismatches', async () => {
  const { Ga4Analytics } = await loadModule();
  const noConsentRuntime = runtime();
  const noConsent = new Ga4Analytics(noConsentRuntime);
  assert.equal(noConsent.configure(previewConfig()), true);
  noConsent.track('loading_ready', {}, { screen: 'loading' });
  assert.equal(noConsentRuntime.scripts.length, 0);
  assert.equal(noConsentRuntime.dataLayer, undefined);
  noConsent.setConsent(false);
  assert.equal(noConsentRuntime.scripts.length, 0);

  const mismatchRuntime = runtime();
  const mismatch = new Ga4Analytics(mismatchRuntime);
  mismatch.setConsent(true);
  assert.equal(mismatch.configure(previewConfig({ property_environment: 'production' })), false);
  assert.equal(mismatchRuntime.scripts.length, 0);
  assert.equal(mismatchRuntime.dataLayer, undefined);
});

test('manual page views disable automatic tracking, use fixed virtual URLs, and deduplicate only consecutive screens', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime();
  const analytics = new Ga4Analytics(fake);
  analytics.configure(previewConfig());
  analytics.setConsent(true);
  analytics.track('screen_entered', {}, { screen: 'home' });
  analytics.track('screen_entered', {}, { screen: 'home' });
  analytics.track('screen_entered', {}, { screen: 'game' });
  analytics.track('screen_entered', {}, { screen: 'home' });

  const calls = gtagCalls(fake);
  const config = calls.find((call) => call[0] === 'config');
  assert.equal(config[2].send_page_view, false);
  assert.equal(config[2].cookie_expires, 60 * 86400);
  assert.equal(config[2].cookie_update, false);
  assert.equal(config[2].allow_google_signals, false);
  assert.equal(config[2].allow_ad_personalization_signals, false);
  assert.equal(config[2].ads_data_redaction, true);
  const regionalDefault = calls.find((call) => call[0] === 'consent' && call[1] === 'default' && Array.isArray(call[2].region));
  assert.ok(regionalDefault[2].region.includes('GB'));
  assert.ok(regionalDefault[2].region.includes('CH'));
  assert.equal(regionalDefault[2].analytics_storage, 'denied');
  const pages = calls.filter((call) => call[0] === 'event' && call[1] === 'page_view');
  assert.equal(pages.length, 3);
  assert.equal(pages[0][2].page_location, 'https://preview.example.test/virtual/home');
  assert.equal(pages[0][2].page_referrer, 'https://preview.example.test/virtual/entry');
  assert.equal(pages[1][2].page_referrer, 'https://preview.example.test/virtual/home');
  assert.equal(pages[2][2].page_referrer, 'https://preview.example.test/virtual/game');
  assert.doesNotMatch(JSON.stringify(pages), /share=|private-code|name=|Kim/);
  assert.equal(pages[0][2].campaign_source, 'kakao');
  assert.equal(pages[0][2].campaign_medium, 'referral');
});

test('event parameters are allowlisted and server success events deduplicate without emitting application IDs', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime('https://preview.example.test/');
  const analytics = new Ga4Analytics(fake);
  analytics.configure(previewConfig());
  analytics.setConsent(true);
  const dimensions = {
    game_version: '1.2.0', score: 321, rank: 7, end_reason: 'COLLISION', status: 'VERIFIED',
    duration_seconds: 12.34,
    name: 'PRIVATE NAME', phone: '01012345678', token: 'secret-token', share_id: 'share-secret', raw_url: 'https://private.test/?code=secret',
  };
  assert.equal(analytics.track('game_completed', dimensions, { screen: 'game', gameSessionId: 'session-private-1' }), true);
  assert.equal(analytics.track('game_completed', dimensions, { screen: 'game', gameSessionId: 'session-private-1' }), false);
  analytics.track('game_completed', dimensions, { screen: 'game', gameSessionId: 'session-private-2' });
  analytics.track('game_checkpoint', { score: 999 }, { screen: 'game' });

  const events = gtagCalls(fake).filter((call) => call[0] === 'event' && call[1] === 'game_complete');
  assert.equal(events.length, 2);
  assert.deepEqual(Object.keys(events[0][2]).sort(), ['duration_seconds', 'end_reason', 'game_version', 'rank', 'score', 'screen_name', 'verification_status']);
  assert.equal(events[0][2].duration_seconds, 12.3);
  assert.doesNotMatch(JSON.stringify(events), /PRIVATE|010123|secret|session-private|raw_url|share_id/);
  assert.equal(gtagCalls(fake).some((call) => call[1] === 'game_checkpoint'), false);
});

test('draw interaction events include only their bounded round and pouch dimensions', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime('https://preview.example.test/');
  const analytics = new Ga4Analytics(fake);
  analytics.configure(previewConfig());
  analytics.setConsent(true);
  analytics.track('pouch_selected', { action: 'pouch_2', round_number: 4, draw_id: 'private-draw' }, { screen: 'draw' });
  analytics.track('scratch_started', { round_number: 4, name: 'Private Name' }, { screen: 'draw' });
  const events = gtagCalls(fake).filter((call) => call[0] === 'event').slice(-2);
  assert.deepEqual(events.map((call) => [call[1], call[2].round_number]), [['pouch_selected', 4], ['scratch_started', 4]]);
  assert.equal(events[0][2].pouch, 'pouch_2');
  assert.doesNotMatch(JSON.stringify(events), /private-draw|Private Name/);
});

test('consented success dedup survives reload with hashed bounded property-scoped storage', async () => {
  const { Ga4Analytics } = await loadModule();
  const storage = memoryStorage();
  const firstRuntime = runtime('https://preview.example.test/', storage);
  const first = new Ga4Analytics(firstRuntime);
  first.configure(previewConfig());
  first.setConsent(true);
  assert.equal(first.track('draw_result_viewed', { result_type: 'benefit', round_number: 2 }, { screen: 'draw', dedupKey: 'draw-result:private-draw-id' }), true);
  assert.doesNotMatch(storage.dump(), /private-draw-id|draw-result/);

  const secondRuntime = runtime('https://preview.example.test/', storage);
  const second = new Ga4Analytics(secondRuntime);
  second.configure(previewConfig());
  second.setConsent(true);
  assert.equal(second.track('draw_result_viewed', { result_type: 'benefit', round_number: 2 }, { screen: 'draw', dedupKey: 'draw-result:private-draw-id' }), false);
  assert.equal(gtagCalls(secondRuntime).some((call) => call[1] === 'draw_result_view'), false);

  const otherPropertyRuntime = runtime('https://preview.example.test/', storage);
  const otherProperty = new Ga4Analytics(otherPropertyRuntime);
  otherProperty.configure(previewConfig({ measurement_id: 'G-ZYXWVU9876' }));
  otherProperty.setConsent(true);
  assert.equal(otherProperty.track('draw_result_viewed', { result_type: 'benefit', round_number: 2 }, { screen: 'draw', dedupKey: 'draw-result:private-draw-id' }), true);
});

test('dedup storage is consent-only, cleared on denial, and bounded in memory when storage is blocked', async () => {
  const { Ga4Analytics, DEDUP_LIMIT } = await loadModule();
  const storage = memoryStorage();
  const undecided = new Ga4Analytics(runtime('https://preview.example.test/', storage));
  undecided.configure(previewConfig());
  undecided.track('draw_result_viewed', {}, { dedupKey: 'private-before-consent' });
  assert.equal(storage.length, 0);

  undecided.setConsent(true);
  undecided.track('draw_result_viewed', { result_type: 'benefit', round_number: 1 }, { dedupKey: 'private-after-consent' });
  assert.equal(storage.length, 1);
  undecided.setConsent(false);
  assert.equal(storage.length, 0);

  const blockedStorage = {
    get length() { throw new Error('blocked'); }, key() { throw new Error('blocked'); },
    getItem() { throw new Error('blocked'); }, setItem() { throw new Error('blocked'); }, removeItem() { throw new Error('blocked'); },
  };
  const fallback = new Ga4Analytics(runtime('https://preview.example.test/', blockedStorage));
  fallback.configure(previewConfig());
  fallback.setConsent(true);
  for (let index = 0; index < DEDUP_LIMIT + 10; index += 1) {
    fallback.track('draw_result_viewed', { result_type: 'benefit', round_number: 1 }, { dedupKey: `draw-${index}` });
  }
  assert.equal(fallback.dedup.size, DEDUP_LIMIT);
});

test('persisted dedup expires after its bounded TTL', async () => {
  const { Ga4Analytics, DEDUP_TTL_MS } = await loadModule();
  const storage = memoryStorage();
  let clock = 10_000;
  const firstRuntime = runtime('https://preview.example.test/', storage);
  firstRuntime.Date = { now: () => clock };
  const first = new Ga4Analytics(firstRuntime);
  first.configure(previewConfig());
  first.setConsent(true);
  assert.equal(first.track('claim_form_submitted', { claim_type: 'DRAW' }, { dedupKey: 'claim-private' }), true);

  clock += DEDUP_TTL_MS + 1;
  const laterRuntime = runtime('https://preview.example.test/', storage);
  laterRuntime.Date = { now: () => clock };
  const later = new Ga4Analytics(laterRuntime);
  later.configure(previewConfig());
  later.setConsent(true);
  assert.equal(later.track('claim_form_submitted', { claim_type: 'DRAW' }, { dedupKey: 'claim-private' }), true);
});

test('a tiny sanitized pre-config buffer is available only to consent already granted before config', async () => {
  const { Ga4Analytics, BUFFER_LIMIT } = await loadModule();
  const fake = runtime('https://preview.example.test/?utm_source=evil&utm_campaign=private-campaign');
  const analytics = new Ga4Analytics(fake);
  analytics.setConsent(true);
  for (let index = 0; index < BUFFER_LIMIT + 5; index += 1) {
    analytics.track('content_clicked', { content: 'study_note', position: 'benefit_guides', name: `person-${index}` }, { screen: 'benefit' });
  }
  assert.equal(analytics.buffer.length, BUFFER_LIMIT);
  analytics.configure(previewConfig());
  assert.equal(fake.scripts.length, 1);
  assert.equal(gtagCalls(fake).filter((call) => call[0] === 'event').length, BUFFER_LIMIT);
  assert.doesNotMatch(JSON.stringify(gtagCalls(fake)), /person-|private-campaign|evil/);

  fake.scripts[0].onerror();
  assert.doesNotThrow(() => analytics.track('gemini_cta_clicked', { position: 'benefit_main' }, { screen: 'benefit' }));
  assert.equal(analytics.blocked, true);
  assert.equal(analytics.buffer.length, 0);
});

test('undecided consent drops past actions and first allow sends only the current virtual page', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime();
  const analytics = new Ga4Analytics(fake);
  analytics.track('entry_viewed', { name: 'PRIVATE NAME' }, { screen: 'loading' });
  analytics.track('game_cta_clicked', { source: 'home' }, { screen: 'home' });
  analytics.track('screen_entered', {}, { screen: 'home' });
  assert.equal(analytics.buffer.length, 0);
  assert.equal(analytics.currentScreen, 'home');
  analytics.configure(previewConfig());
  assert.equal(fake.scripts.length, 0);
  analytics.setConsent(true);
  const events = gtagCalls(fake).filter((call) => call[0] === 'event');
  assert.deepEqual(events.map((call) => call[1]), ['page_view']);
  assert.equal(events[0][2].page_location, 'https://preview.example.test/virtual/home');
  assert.doesNotMatch(JSON.stringify(events), /PRIVATE|game_cta/);
});

test('revoking consent stops collection and expires only GA cookies', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime();
  const analytics = new Ga4Analytics(fake);
  analytics.configure(previewConfig());
  analytics.setConsent(true);
  const before = gtagCalls(fake).length;
  analytics.setConsent(false);
  analytics.track('loading_ready', {}, { screen: 'loading' });
  const calls = gtagCalls(fake);
  assert.equal(calls.length, before + 1);
  assert.deepEqual(calls.at(-1).slice(0, 2), ['consent', 'update']);
  assert.deepEqual(calls.at(-1)[2], {
    analytics_storage: 'denied', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
  });
  assert.equal(fake['ga-disable-G-ABCDEF1234'], true);
  assert.ok(fake.cookieWrites.some((value) => value.startsWith('_ga=')));
  assert.ok(fake.cookieWrites.some((value) => value.startsWith('_ga_TEST=')));
  assert.equal(fake.cookieWrites.some((value) => value.startsWith('ordinary=')), false);
});

test('grant after revoke reenables the loaded tag with ads consent still denied', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime();
  const analytics = new Ga4Analytics(fake);
  analytics.configure(previewConfig());
  analytics.setConsent(true);
  analytics.setCurrentScreen('home');
  analytics.setConsent(false);
  const before = gtagCalls(fake).length;
  analytics.setConsent(true);
  const calls = gtagCalls(fake).slice(before);
  assert.equal(fake.scripts.length, 1, 'the loaded SDK is reused');
  assert.equal(fake['ga-disable-G-ABCDEF1234'], false);
  assert.deepEqual(calls[0], ['consent', 'update', {
    analytics_storage: 'granted', ad_storage: 'denied', ad_user_data: 'denied', ad_personalization: 'denied',
  }]);
  assert.equal(calls[1][0], 'event');
  assert.equal(calls[1][1], 'page_view');
});

test('automatic collection is not recorded as affirmative consent and repeated config does not override regional defaults', async () => {
  const { Ga4Analytics } = await loadModule();
  const storage = memoryStorage();
  const fake = runtime('https://preview.example.test/', storage);
  const analytics = new Ga4Analytics(fake);
  analytics.setConsent(true, 'automatic');
  analytics.configure(previewConfig());
  const callsBeforeRepeat = gtagCalls(fake).length;
  analytics.track('draw_result_viewed', { result_type: 'benefit', round_number: 1 }, { screen: 'draw', dedupKey: 'automatic-dedup' });
  assert.equal(storage.length, 0, 'automatic policy uses only in-memory dedup');
  analytics.setConsent(true, 'automatic');
  analytics.configure(previewConfig());
  const repeated = gtagCalls(fake).slice(callsBeforeRepeat);
  assert.equal(repeated.some((call) => call[0] === 'consent' && call[1] === 'update' && call[2].analytics_storage === 'granted'), false);
  assert.equal(analytics.consentSource, 'automatic');
});

test('automatic mode never sends a global granted update after a prior in-page denial', async () => {
  const { Ga4Analytics } = await loadModule();
  const fake = runtime();
  const analytics = new Ga4Analytics(fake);
  analytics.setConsent(true, 'automatic');
  analytics.configure(previewConfig());
  analytics.setConsent(false, 'browser_signal');
  const before = gtagCalls(fake).length;
  analytics.setConsent(true, 'automatic');
  const calls = gtagCalls(fake).slice(before);
  assert.equal(calls.some((call) => call[0] === 'consent' && call[1] === 'update' && call[2].analytics_storage === 'granted'), false);
});

test('the internal analytics hook forwards before its bounded delivery queue rejects an event', () => {
  const forwarded = [];
  const api = {
    createRequestId: (prefix) => `${prefix}_ga4_test`,
    setTrackingContext() {},
    postEvents: async () => ({ accepted: 0, rejected: 0 }),
  };
  const context = {
    api,
    ga4Analytics: { track: (...args) => forwarded.push(args), setAttribution() {} },
    performance: { now: () => 100 },
    document: { hidden: false, addEventListener() {} },
    window: { addEventListener() {} },
    sessionStorage: { getItem: () => null, setItem() {} },
    setInterval() {}, console,
  };
  const analyticsSource = fs.readFileSync(path.join(root, 'public/js/analytics.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const analytics = new Analytics();', 'globalThis.analytics = new Analytics();')
    .replace('export { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', '');
  vm.runInNewContext(analyticsSource, context);
  for (let index = 0; index < 45; index += 1) context.analytics.track('screen_entered');
  assert.equal(context.analytics.queue.length, 40);
  assert.equal(forwarded.length, 46, 'constructor entry plus every attempted event reaches the independent adapter');
});

test('adapter failures cannot block the internal event queue or direct GA4 callers', () => {
  const api = {
    createRequestId: (prefix) => `${prefix}_ga4_failure_test`,
    setTrackingContext() {}, postEvents: async () => ({ accepted: 0, rejected: 0 }),
  };
  const context = {
    api,
    ga4Analytics: { track() { throw new Error('adapter unavailable'); }, setAttribution() { throw new Error('adapter unavailable'); } },
    performance: { now: () => 100 }, document: { hidden: false, addEventListener() {} },
    window: { addEventListener() {} }, sessionStorage: { getItem: () => null, setItem() {} },
    setInterval() {}, console,
  };
  const analyticsSource = fs.readFileSync(path.join(root, 'public/js/analytics.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const analytics = new Analytics();', 'globalThis.analytics = new Analytics();')
    .replace('export { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', '');
  vm.runInNewContext(analyticsSource, context);
  const before = context.analytics.queue.length;
  assert.doesNotThrow(() => context.analytics.track('content_clicked', { content: 'study_note' }));
  assert.equal(context.analytics.queue.length, before + 1);
  assert.equal(context.analytics.trackGa4('tutorial_viewed', { tutorial_step: 1 }), false);
  assert.doesNotThrow(() => context.analytics.setEntryAttribution({ channel: 'kakao' }));
});
