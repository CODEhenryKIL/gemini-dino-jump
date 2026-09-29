const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

const root = path.resolve(__dirname, '..');
const consentSource = fs.readFileSync(path.join(root, 'public/js/analytics_consent.js'), 'utf8')
  .replace(/^import .*;$/gm, '')
  .replace('export function', 'function')
  .replace(/^export \{.*\};$/gm, '');
const config = {
  environment: 'preview',
  ga4: {
    enabled: true,
    measurement_id: 'G-TEST123456',
    property_environment: 'test',
    allowed_origins: ['https://preview.example.test'],
  },
};

function harness({ preference = null, cookie = '', gpc = false, dnt = null, gaDisable = false, storageBlocked = false } = {}) {
  const calls = [];
  const listeners = {};
  const storage = new Map(preference === null ? [] : [['dino_ga4_consent_v1', preference]]);
  const window = {
    doNotTrack: dnt,
    addEventListener(name, listener) { listeners[name] = listener; },
    location: {},
  };
  if (gaDisable) window['ga-disable-G-TEST123456'] = true;
  const context = {
    ga4Analytics: {
      setConsent: (...args) => calls.push(['consent', ...args]),
      configure: (value) => calls.push(['configure', value]),
    },
    document: { cookie },
    navigator: { globalPrivacyControl: gpc, doNotTrack: dnt, msDoNotTrack: null },
    localStorage: {
      getItem(key) { if (storageBlocked) throw Error('blocked'); return storage.get(key) ?? null; },
    },
    window,
  };
  vm.runInNewContext(consentSource, context);
  return { calls, configure: context.configureAnalyticsConsent, listeners };
}

test('a new visitor uses automatic GA4 without storing a false affirmative choice', () => {
  const h = harness();
  h.configure(config);
  assert.deepEqual(h.calls[0], ['consent', true, 'automatic']);
  assert.equal(h.calls[1][0], 'configure');
  assert.equal(h.calls[1][1], config);
});

test('stored and cookie opt-outs remain off while an old affirmative choice remains distinguishable', () => {
  const denied = harness({ preference: 'denied' });
  denied.configure(config);
  assert.deepEqual(denied.calls[0], ['consent', false, 'stored_optout']);

  const cookieWins = harness({ preference: 'granted', cookie: 'dino_ga4_optout=1' });
  cookieWins.configure(config);
  assert.deepEqual(cookieWins.calls[0], ['consent', false, 'stored_optout']);

  const granted = harness({ preference: 'granted' });
  granted.configure(config);
  assert.deepEqual(granted.calls[0], ['consent', true, 'stored_choice']);
});

test('GPC, DNT and an external ga-disable flag override automatic or previously granted collection', () => {
  for (const options of [
    { preference: 'granted', gpc: true },
    { preference: 'granted', dnt: '1' },
    { gaDisable: true },
  ]) {
    const h = harness(options);
    h.configure(config);
    assert.deepEqual(h.calls[0], ['consent', false, 'browser_signal']);
    assert.equal(h.calls[1][0], 'configure');
  }
});

test('blocked preference storage fails closed and never blocks the game', () => {
  const h = harness({ storageBlocked: true });
  assert.doesNotThrow(() => h.configure(config));
  assert.deepEqual(h.calls[0], ['consent', false, 'storage_unavailable']);

  const context = {
    ga4Analytics: { setConsent() { throw Error('adapter unavailable'); }, configure() {} },
    document: { cookie: '' }, navigator: {}, localStorage: { getItem: () => null }, window: {},
  };
  vm.runInNewContext(consentSource, context);
  assert.doesNotThrow(() => context.configureAnalyticsConsent(config));
});

test('an opt-out saved in another tab immediately stops analytics without interrupting the game', () => {
  const h = harness();
  h.configure(config);
  h.listeners.storage({ key: 'dino_ga4_consent_v1', newValue: 'denied' });
  assert.deepEqual(h.calls.at(-1), ['consent', false, 'stored_optout']);
});

test('removed popup stays absent and a standalone opt-out page discloses automatic analytics', () => {
  const appHtml = fs.readFileSync(path.join(root, 'public/index.html'), 'utf8');
  const privacyHtml = fs.readFileSync(path.join(root, 'public/privacy.html'), 'utf8');
  assert.doesNotMatch(appHtml, /id="analytics-(?:settings|consent|accept|decline)"/);
  assert.doesNotMatch(appHtml, /분석 설정|분석을 허용할까요/);
  assert.match(privacyHtml, /별도 팝업 없이/);
  assert.match(privacyHtml, /이름·연락처·학교/);
  assert.match(privacyHtml, /2개월/);
  assert.match(privacyHtml, /60일/);
  assert.match(privacyHtml, /analytics-optout/);
  assert.doesNotMatch(privacyHtml, /ga4_analytics|app\.js/);
});

test('the standalone control persists opt-out, clears GA data, and can restore automatic mode', () => {
  const listeners = {};
  const elements = {
    'analytics-optout': { addEventListener: (name, fn) => { listeners[`out:${name}`] = fn; } },
    'analytics-reenable': { addEventListener: (name, fn) => { listeners[`in:${name}`] = fn; } },
    'privacy-status': { textContent: '' },
    'privacy-storage-help': { hidden: true },
  };
  const values = new Map([['dino_ga4_dedup_v1:preview:test:key', 'private-dedup']]);
  const cookies = new Map([['_ga', 'client'], ['_ga_TEST', 'session'], ['ordinary', 'keep']]);
  const document = {
    getElementById: (id) => elements[id] || null,
    get cookie() { return [...cookies].map(([key, value]) => `${key}=${value}`).join('; '); },
    set cookie(value) {
      const [pair] = value.split(';');
      const separator = pair.indexOf('=');
      const key = pair.slice(0, separator);
      const item = pair.slice(separator + 1);
      if (/Max-Age=0/.test(value)) cookies.delete(key); else cookies.set(key, item);
    },
  };
  const context = {
    document,
    location: { hostname: 'preview.example.test' },
    localStorage: {
      get length() { return values.size; },
      key: (index) => [...values.keys()][index] ?? null,
      getItem: (key) => values.get(key) ?? null,
      setItem: (key, value) => values.set(key, String(value)),
      removeItem: (key) => values.delete(key),
    },
  };
  vm.runInNewContext(fs.readFileSync(path.join(root, 'public/js/privacy.js'), 'utf8'), context);
  listeners['out:click']();
  assert.equal(values.get('dino_ga4_consent_v1'), 'denied');
  assert.equal([...values.keys()].some((key) => key.startsWith('dino_ga4_dedup_v1:')), false);
  assert.equal(cookies.has('_ga'), false);
  assert.equal(cookies.has('_ga_TEST'), false);
  assert.equal(cookies.get('ordinary'), 'keep');
  assert.match(elements['privacy-status'].textContent, /중지했습니다/);

  listeners['in:click']();
  assert.equal(values.has('dino_ga4_consent_v1'), false);
  assert.equal(cookies.has('dino_ga4_optout'), false);
  assert.match(elements['privacy-status'].textContent, /자동 분석을 다시 사용/);
});
