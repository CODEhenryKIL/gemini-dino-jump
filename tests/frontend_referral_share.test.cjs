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

function loadShare({ key = '', Kakao, navigatorMock = {}, documentMock = null } = {}) {
  const events = [];
  const toasts = [];
  let requestIndex = 0;
  const api = {
    config: { share: { kakao_javascript_key: key } },
    async getReferralInfo() { return { invite_url: '/invite/referralcode123' }; },
    createRequestId() { requestIndex += 1; return `share_${requestIndex}`; },
  };
  const analytics = {
    screen: 'result', screenViewId: 'result_screen_1', activeMs: 724,
    currentActiveMs() { return this.activeMs; },
    track(name, dimensions, extra) { events.push({ name, dimensions, extra }); },
  };
  const context = {
    console, URL, api, analytics, navigator: navigatorMock, Kakao,
    ui: { showToast(message) { toasts.push(message); } },
    window: { location: { origin: 'https://game.example' }, prompt() {} },
    document: documentMock || { createElement() { throw new Error('unexpected SDK load'); }, head: { appendChild() {} } },
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/referral_share.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export async function prepareResultReferralShare', 'globalThis.prepareResultReferralShare = async function');
  vm.runInNewContext(source, context, { filename: 'public/js/referral_share.js' });
  const router = { config: { share: { kakao_javascript_key: key } }, state: { bestScore: 4321 } };
  return { analytics, api, context, events, prepare: context.prepareResultReferralShare, router, toasts };
}

function shareEvents(events) {
  return events.filter(({ name }) => name === 'share_attempted');
}

test('configured Kakao share initializes once and opens sendDefault with an attributed invite URL', async () => {
  const sent = [];
  const initKeys = [];
  let initialized = false;
  const Kakao = {
    init(key) { initKeys.push(key); initialized = true; },
    isInitialized() { return initialized; },
    Share: { sendDefault(payload) { sent.push(payload); } },
  };
  const key = '0123456789abcdef0123456789abcdef';
  const harness = loadShare({ key, Kakao });
  const prepared = await harness.prepare(harness.router);
  assert.equal(prepared.mode, 'kakao');
  const result = await prepared.share();

  assert.deepEqual(initKeys, [key]);
  assert.equal(result.method, 'kakao');
  assert.equal(sent.length, 1);
  assert.equal(sent[0].objectType, 'text');
  assert.match(sent[0].text, /4321/);
  assert.equal(sent[0].link.mobileWebUrl, sent[0].link.webUrl);
  assert.match(sent[0].link.webUrl, /^https:\/\/game\.example\/invite\/referralcode123\?/);
  assert.match(sent[0].link.webUrl, /(?:\?|&)link=record_share(?:&|$)/);
  assert.match(sent[0].link.webUrl, /(?:\?|&)share=share_1(?:&|$)/);
  assert.deepEqual(shareEvents(harness.events).map(({ dimensions }) => [dimensions.share_method, dimensions.status]), [['kakao', 'attempted']]);
});

test('unconfigured Kakao opens native share directly and blocks duplicate clicks while pending', async () => {
  const native = deferred();
  const payloads = [];
  const harness = loadShare({ navigatorMock: { share(payload) { payloads.push(payload); return native.promise; } } });
  const prepared = await harness.prepare(harness.router);
  assert.equal(prepared.mode, 'native');
  const first = prepared.share();
  const duplicate = await prepared.share();

  assert.equal(payloads.length, 1, 'native share must be invoked synchronously from the click');
  assert.equal(duplicate.status, 'pending');
  native.resolve();
  assert.equal((await first).status, 'share_sheet_closed');
  assert.deepEqual(shareEvents(harness.events).map(({ dimensions }) => dimensions.status), ['attempted', 'share_sheet_closed']);
  assert.ok(shareEvents(harness.events).every(({ extra }) => extra.screenViewId === 'result_screen_1' && extra.activeMs === 724));
});

test('Kakao invocation failure falls through to native share without claiming message delivery', async () => {
  const payloads = [];
  const Kakao = {
    init() {}, isInitialized() { return true; },
    Share: { sendDefault() { throw new Error('domain not registered'); } },
  };
  const harness = loadShare({
    key: '0123456789abcdef0123456789abcdef', Kakao,
    navigatorMock: { async share(payload) { payloads.push(payload); } },
  });
  const prepared = await harness.prepare(harness.router);
  const result = await prepared.share();

  assert.equal(result.method, 'native');
  assert.equal(payloads.length, 1);
  assert.deepEqual(shareEvents(harness.events).map(({ dimensions }) => [dimensions.share_method, dimensions.status]), [
    ['kakao', 'attempted'], ['kakao', 'failed'], ['native', 'attempted'], ['native', 'share_sheet_closed'],
  ]);
});

test('no sharing API copies the attributed invite URL without navigating away', async () => {
  const copied = [];
  const harness = loadShare({ navigatorMock: { clipboard: { async writeText(value) { copied.push(value); } } } });
  const prepared = await harness.prepare(harness.router);
  assert.equal(prepared.mode, 'copy');
  const result = await prepared.share();

  assert.equal(result.status, 'copied');
  assert.equal(copied.length, 1);
  assert.match(copied[0], /link=record_share/);
  assert.deepEqual(shareEvents(harness.events).map(({ dimensions }) => dimensions.status), ['attempted', 'copied']);
  assert.deepEqual(harness.toasts, ['초대 링크를 복사했어요. 카카오톡에 붙여 넣어 주세요.']);
});
