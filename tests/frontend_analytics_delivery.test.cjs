const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness() {
  const requests = [];
  const warnings = [];
  let nextId = 0;
  let participantReady = false;
  const api = {
    createRequestId: (prefix) => `${prefix}_delivery_${++nextId}`,
    setTrackingContext() { participantReady = true; },
    postEvents(events, options) {
      let resolve, reject;
      const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
      requests.push({ events, options, participantReady, resolve, reject });
      return promise;
    },
  };
  const context = {
    api, performance: { now: () => 100 },
    document: { hidden: false, addEventListener() {} },
    window: { addEventListener() {} },
    sessionStorage: { getItem: () => null, setItem() {} },
    setInterval() {}, console: { warn: (...args) => warnings.push(args) },
  };
  const source = fs.readFileSync(path.join(__dirname, '../public/js/analytics.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const analytics = new Analytics();', 'globalThis.analytics = new Analytics();')
    .replace('export { EVENT_ALLOWLIST, SAFE_DIMENSIONS };', '');
  vm.runInNewContext(source, context);
  return {
    analytics: context.analytics, requests, warnings,
    async respond(index, response) { requests[index].resolve(response); await new Promise(setImmediate); },
  };
}

test('an anonymous event rejected during participant linking waits for the authenticated context and keeps its identity', async () => {
  const h = harness();
  h.analytics.setObservationReady();
  const original = h.requests[0].events[0];
  const before = JSON.stringify(original);
  assert.equal(h.requests[0].participantReady, false);
  await h.respond(0, { accepted: 0, rejected: 1, rejections: [{ index: 0, reason: 'PARTICIPANT_NOT_READY' }] });
  await h.analytics.flush();
  assert.equal(h.requests.length, 1, 'do not replay before the participant cookie is ready');
  assert.equal(h.analytics.queue.length, 1, 'retain the rejected initial event');
  h.analytics.setParticipantReady({ is_new: true });
  assert.equal(h.requests.length, 2);
  assert.equal(h.requests[1].participantReady, true);
  assert.equal(JSON.stringify(h.requests[1].events[0]), before, 'same event ID, time and attribution are retained');
  await h.respond(1, { accepted: h.requests[1].events.length, rejected: 0 });
  assert.equal(h.analytics.queue.length, 0);
  assert.equal(h.warnings.length, 0);
});

test('a late partial rejection retries only the rejected item after participant initialization has already finished', async () => {
  const h = harness();
  h.analytics.recordLoadingCheckpoint(true);
  h.analytics.setObservationReady();
  const [accepted, rejected] = h.requests[0].events;
  h.analytics.setParticipantReady({ is_new: true });
  await h.respond(0, { accepted: 1, rejected: 1, rejections: [{ index: 1, reason: 'PARTICIPANT_NOT_READY' }] });
  assert.equal(h.requests.length, 2, 'resume after the in-flight request settles');
  assert.equal(h.requests[1].events.includes(accepted), false);
  assert.equal(h.requests[1].events.includes(rejected), true);
  await h.respond(1, { accepted: h.requests[1].events.length, rejected: 0 });
  assert.equal(h.warnings.length, 0);
});

test('a repeated participant rejection is reported once and cannot loop forever', async () => {
  const h = harness();
  h.analytics.setParticipantReady({ is_new: true });
  h.analytics.setObservationReady();
  await h.respond(0, { accepted: 2, rejected: 1, rejections: [{ index: 0, reason: 'PARTICIPANT_NOT_READY' }] });
  assert.equal(h.requests.length, 2);
  await h.respond(1, { accepted: 0, rejected: 1, rejections: [{ index: 0, reason: 'PARTICIPANT_NOT_READY' }] });
  await h.analytics.flush();
  assert.equal(h.requests.length, 2);
  assert.equal(h.analytics.queue.length, 0);
  assert.equal(h.warnings.length, 1);
});

test('permanent rejection diagnostics contain only allowed names and reason codes', async () => {
  const h = harness();
  h.analytics.track('content_clicked', { content: 'PRIVATE_VALUE' });
  h.analytics.setObservationReady();
  await h.respond(0, { accepted: 1, rejected: 1, rejections: [{ index: 1, reason: 'INVALID_DIMENSIONS', payload: 'SECRET' }] });
  await h.analytics.flush();
  assert.equal(h.requests.length, 1);
  const diagnostic = JSON.stringify(h.warnings);
  assert.match(diagnostic, /content_clicked/);
  assert.match(diagnostic, /INVALID_DIMENSIONS/);
  assert.doesNotMatch(diagnostic, /PRIVATE_VALUE|SECRET|evt_delivery|obs_delivery/);
});

test('unknown or invalid rejection metadata cannot trigger a retry or leak a response payload', async () => {
  const h = harness();
  h.analytics.setObservationReady();
  await h.respond(0, { accepted: 0, rejected: 1, rejections: [
    { index: -1, reason: 'PARTICIPANT_NOT_READY' },
    { index: 99, reason: 'PARTICIPANT_NOT_READY' },
    { index: 0, reason: 'PRIVATE_REASON' },
  ] });
  await h.analytics.flush();
  assert.equal(h.requests.length, 1);
  assert.equal(h.warnings.length, 1);
  assert.doesNotMatch(JSON.stringify(h.warnings), /PRIVATE_REASON/);
});

test('network failures still retain the same events for a later bounded retry', async () => {
  const h = harness();
  h.analytics.setObservationReady();
  const original = h.requests[0].events[0];
  h.requests[0].reject(new Error('temporary network failure'));
  await new Promise(setImmediate);
  assert.equal(h.analytics.queue[0], original);
  const retry = h.analytics.flush(true);
  assert.equal(h.requests[1].options.keepalive, true);
  await h.respond(1, { accepted: 1, rejected: 0 });
  await retry;
  assert.equal(h.analytics.queue.length, 0);
});

test('partial rejection recovery respects the 40-event queue bound and reports an event it cannot retain', async () => {
  const h = harness();
  h.analytics.setObservationReady();
  for (let i = 0; i < 45; i += 1) h.analytics.track('screen_entered');
  assert.equal(h.analytics.queue.length, 40);
  await h.respond(0, { accepted: 0, rejected: 1, rejections: [{ index: 0, reason: 'PARTICIPANT_NOT_READY' }] });
  assert.equal(h.analytics.queue.length, 40);
  assert.equal(h.requests.length, 1);
  assert.equal(h.warnings.length, 1);
});
