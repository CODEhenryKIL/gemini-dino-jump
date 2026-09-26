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

function loadShare({ key = '', Kakao, navigatorMock = {}, documentMock = null, referral = null } = {}) {
  const events = [];
  const toasts = [];
  let requestIndex = 0;
  const api = {
    config: { share: { kakao_javascript_key: key } },
    async getReferralInfo() { return referral || { invite_url: '/invite/referralcode123' }; },
    createRequestId() { requestIndex += 1; return `share_${requestIndex}`; },
  };
  const analytics = {
    screen: 'result', screenViewId: 'result_screen_1', activeMs: 724,
    currentActiveMs() { return this.activeMs; },
    track(name, dimensions, extra) { events.push({ name, dimensions, extra }); },
  };
  const context = {
    console, URL, setTimeout, clearTimeout, api, analytics, navigator: navigatorMock, Kakao,
    ui: { showToast(message) { toasts.push(message); } },
    window: { location: { origin: 'https://game.example' }, prompt() {} },
    document: documentMock || { createElement() { throw new Error('unexpected SDK load'); }, head: { appendChild() {} } },
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/referral_share.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export function loadKakaoSdk', 'function loadKakaoSdk')
    .replace('export function buildReferralShareText', 'globalThis.buildReferralShareText = function')
    .replace('export async function prepareResultReferralShare', 'globalThis.prepareResultReferralShare = async function');
  vm.runInNewContext(source, context, { filename: 'public/js/referral_share.js' });
  const router = { config: { share: { kakao_javascript_key: key } }, state: { bestScore: 4321 } };
  return { analytics, api, buildText: context.buildReferralShareText, context, events, prepare: context.prepareResultReferralShare, router, toasts };
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
  assert.equal(sent[0].text, '행사 종료 시 1위 달성하면 5만원\n\n참여하면 삼텐바이미 받을 수도 있대!\n너도 한 판 해봐!');
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
  assert.match(copied[0], /^행사 종료 시 1위 달성하면 5만원/);
  assert.match(copied[0], /link=record_share/);
  assert.deepEqual(shareEvents(harness.events).map(({ dimensions }) => dimensions.status), ['attempted', 'copied']);
  assert.deepEqual(harness.toasts, ['초대 링크를 복사했어요. 카카오톡에 붙여 넣어 주세요.']);
});

test('ranking share copy includes participant count when the server provides it', () => {
  const harness = loadShare();
  assert.equal(harness.buildText('retry_invite', { participant_count: 37 }),
    '행사 종료 시 1위 달성하면 5만원\n현재 참여 인원 37명, 도전해 볼 만하다!\n\n참여하면 삼텐바이미 받을 수도 있대!\n너도 한 판 해봐!');
  assert.equal(harness.buildText('record_share', {}),
    '행사 종료 시 1위 달성하면 5만원\n\n참여하면 삼텐바이미 받을 수도 있대!\n너도 한 판 해봐!');
  assert.equal(harness.buildText('record_share', { participant_count: null }),
    '행사 종료 시 1위 달성하면 5만원\n\n참여하면 삼텐바이미 받을 수도 있대!\n너도 한 판 해봐!');
});

test('general and non-winning prize shares never imply that the participant won', () => {
  const harness = loadShare();
  const expected = '나 게임 한 판 하고\n복주머니 열어봄!\n\n삼텐바이미 받을 수도 있다던데,\n너도 한번 해봐';
  assert.equal(harness.buildText('general_share'), expected);
  assert.equal(harness.buildText('prize_share', { won_prize_name: null }), expected);
});

test('winning prize share names the prize and always uses the requested Samtanbimi line', () => {
  const harness = loadShare();
  const expected = '나 소니 헤드셋 이거 받음\n아직 삼텐바이미 남았다는데\n\n너도 게임 한 판 하고\n상품 뽑아봐!';
  assert.equal(harness.buildText('prize_share', { won_prize_name: '소니 헤드셋' }), expected);
  assert.equal(harness.buildText('prize_share', { won_prize_name: '소니 헤드셋', samtan_available: false }), expected);
});

test('general share attributes analytics and URL as prize_share', async () => {
  const copied = [];
  const harness = loadShare({ navigatorMock: { clipboard: { async writeText(value) { copied.push(value); } } } });
  const prepared = await harness.prepare(harness.router, { kind: 'general_share' });
  await prepared.share();
  assert.match(copied[0], /link=prize_share/);
  assert.ok(shareEvents(harness.events).every(({ dimensions }) => dimensions.link_kind === 'prize_share'));
});


test('fresh SDK exposes Share only after init and still prepares Kakao sharing', async () => {
  let script;
  const harness = loadShare({ key: '0123456789abcdef0123456789abcdef', documentMock: { createElement: () => ({ remove() {} }), head: { appendChild(value) { script = value; } } } });
  const preparing = harness.prepare(harness.router);
  await new Promise(setImmediate);
  let initialized = false;
  harness.context.Kakao = { isInitialized: () => initialized, init() { initialized = true; this.Share = { sendDefault() {} }; } };
  script.onload();
  const prepared = await preparing;
  assert.equal(initialized, true);
  assert.equal(prepared.mode, 'kakao');
});
