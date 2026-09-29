const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const vm = require('node:vm');
const path = require('node:path');

function harness(value = null, storageBlocked = false) {
  const calls = [];
  const elements = Object.fromEntries(['analytics-consent', 'analytics-settings', 'analytics-accept', 'analytics-decline', 'analytics-consent-title'].map(id => [id, {
    hidden: true, listeners: {}, addEventListener(name, fn) { this.listeners[name] = fn; }, focus() {},
  }]));
  const storage = new Map(value === null ? [] : [['dino_ga4_consent_v1', value]]);
  const context = {
    window: { location: { reload: () => calls.push(['reload']) } },
    ga4Analytics: { configure: c => calls.push(['configure', c]), setConsent: c => calls.push(['consent', c]) },
    document: { getElementById: id => elements[id] },
    localStorage: { getItem: k => { if (storageBlocked) throw Error('blocked'); return storage.get(k); }, setItem: (k,v) => { if (storageBlocked) throw Error('blocked'); storage.set(k,v); } },
  };
  const source = fs.readFileSync(path.join(__dirname, '../public/js/analytics_consent.js'), 'utf8').replace(/^import .*;$/gm, '').replace('export function', 'function');
  vm.runInNewContext(source, context);
  return { calls, elements, storage, configure: context.configureAnalyticsConsent };
}
const config = { ga4: { enabled: true } };

test('new visitor receives no consent grant until choosing allow', () => {
  const h=harness(); h.configure(config);
  assert.equal(h.elements['analytics-consent'].hidden,false);
  assert.equal(h.calls.some(([kind])=>kind==='consent'),false);
  h.elements['analytics-accept'].listeners.click();
  assert.deepEqual(h.calls.at(-1),['consent',true]);
  assert.equal(h.storage.get('dino_ga4_consent_v1'),'granted');
  assert.equal(h.elements['analytics-consent'].hidden,true);
});

test('declined preference persists and can be changed without any game action', () => {
  const h=harness('denied');h.configure(config);
  assert.deepEqual(h.calls.at(-1),['consent',false]);
  h.elements['analytics-settings'].listeners.click();
  assert.equal(h.elements['analytics-consent'].hidden,false);
  h.elements['analytics-accept'].listeners.click();
  h.elements['analytics-settings'].listeners.click();
  h.elements['analytics-decline'].listeners.click();
  assert.deepEqual(h.calls.at(-2),['consent',false]);
  assert.deepEqual(h.calls.at(-1),['reload']);
});

test('disabled setup hides controls and blocked storage does not break the app', () => {
  const h=harness(null,true);h.configure({ga4:{enabled:false}});
  assert.equal(h.elements['analytics-settings'].hidden,true);
  h.configure(config);
  assert.doesNotThrow(()=>h.elements['analytics-decline'].listeners.click());
  assert.deepEqual(h.calls.at(-1),['consent',false]);
});
