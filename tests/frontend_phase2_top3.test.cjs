const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

class Element {
  constructor(tag = 'div') {
    this.tag = tag;
    this.children = [];
    this.className = '';
    this.id = '';
    this.disabled = false;
    this.value = '';
    this.checked = false;
    this.onclick = null;
    this.attrs = {};
    this._text = '';
    this._html = '';
  }
  set innerHTML(value) { this._html = String(value); this._text = ''; this.children = []; }
  get innerHTML() { return this._html; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent || '').join(''); }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  setAttribute(name, value) { this.attrs[name] = String(value); }
  querySelector(selector) {
    if (selector.startsWith('#')) return descendants(this).find((node) => node.id === selector.slice(1)) || null;
    return descendants(this).find((node) => node.tag === selector) || null;
  }
}

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function descendants(node) {
  return (node.children || []).flatMap((child) => [child, ...descendants(child)]);
}

function documentMock() {
  return { createElement: (tag) => new Element(tag) };
}

function loadResult(overrides = {}) {
  const source = fs.readFileSync(path.join(root, 'public/js/views/result_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const ResultView =', 'globalThis.ResultView =');
  const context = {
    console,
    document: documentMock(),
    api: {},
    analytics: { track() {} },
    ui: { text: (node, value) => { node.textContent = String(value); }, showToast() {}, showModal() {} },
    ...overrides,
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: 'result_view.js' });
  return { view: context.ResultView, context };
}

function loadRanking(ResultView, overrides = {}) {
  const source = fs.readFileSync(path.join(root, 'public/js/views/ranking_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const RankingView =', 'globalThis.RankingView =');
  const context = {
    console,
    document: documentMock(),
    ResultView,
    api: { getLeaderboard: async () => ({ leaderboard: [], me: null, top3_gap: { status: 'NO_SCORE' } }) },
    analytics: { track() {} },
    ...overrides,
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: 'ranking_view.js' });
  return context.RankingView;
}

function loadPrize(overrides = {}) {
  const source = fs.readFileSync(path.join(root, 'public/js/views/prize_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const PrizeView =', 'globalThis.PrizeView =');
  const context = {
    console,
    document: documentMock(),
    api: {}, analytics: { track() {} }, ui: {},
    ...overrides,
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: 'prize_view.js' });
  return context.PrizeView;
}

function resultContainer() {
  const selectors = [
    '#result-score', '#result-best', '#result-rank', '#result-top3-gap', '#result-nickname',
    '#top3-request', '#btn-go-pouch', '#btn-share-record', '#btn-edit-nick',
  ];
  const nodes = new Map(selectors.map((selector) => [selector, new Element(selector === '#top3-request' ? 'div' : 'span')]));
  const container = new Element('main');
  container.querySelector = (selector) => nodes.get(selector) || null;
  return { container, nodes };
}

function modalHarness({ submit }) {
  let modal;
  const toasts = [];
  const ui = {
    text: (node, value) => { node.textContent = String(value); },
    formField(labelText, type, name) {
      const label = new Element('label');
      const input = new Element('input');
      input.type = type;
      input.name = name;
      label.append(input);
      return { label, input };
    },
    showModal(options) { modal = options; },
    showToast(message) { toasts.push(message); },
  };
  const analyticsEvents = [];
  const loaded = loadResult({
    api: { submitTop3Profile: submit },
    analytics: { track: (name) => analyticsEvents.push(name) },
    ui,
  });
  return { ...loaded, getModal: () => modal, toasts, analyticsEvents };
}

test('TOP3 request renderer replaces stale content and represents requested, submitted, and hidden states', () => {
  const { view } = loadResult();
  const target = new Element('div');
  target.append(new Element('stale'));
  const router = { renderToken: 7, config: { campaign: { game_version: '2.0.0' } } };

  view.renderTop3Request(target, router, { required: true, status: 'REQUESTED', game_version: '2.0.0' });
  assert.equal(target.children.length, 1);
  assert.match(target.textContent, /잠정 TOP3/);
  assert.equal(descendants(target).find((node) => node.tag === 'button').disabled, false);

  view.renderTop3Request(target, router, { required: false, status: 'SUBMITTED', game_version: '2.0.0' });
  assert.equal(target.children.length, 1, 'submitted state replaces the requested card instead of appending');
  assert.match(target.textContent, /TOP3 정보 접수 완료/);
  assert.match(target.textContent, /최종 수상과 지급 여부는.*운영팀이 확인/);
  assert.equal(descendants(target).find((node) => node.tag === 'button').disabled, true);

  view.renderTop3Request(target, router, { required: false, status: 'NOT_REQUIRED' });
  assert.equal(target.children.length, 0);
});

test('ranking shows prizes without old TOP3 information request cards', async () => {
  const { view: ResultView } = loadResult();
  const RankingView = loadRanking(ResultView);
  const container = new Element('main');
  const router = {
    state: { lastResult: null, top3Profile: { required: false, status: 'SUBMITTED', game_version: '2.0.0' } },
    config: { campaign: { game_version: '2.0.0' } },
    isCurrent: (token) => token === 4,
  };

  await RankingView.render(container, router, 4);
  const holder = container.querySelector('#top3-request');
  assert.equal(holder, null);
  assert.match(container.textContent, /5만원.*3만원.*1만원/);
  assert.doesNotMatch(container.textContent, /이전 게임 규칙|합성 테스트 정보|검증된 최고 점수 랭킹/);
});

test('ranking failure retries in place once and shows recovered results', async () => {
  const { view: ResultView } = loadResult();
  const retryRequest = deferred();
  let calls = 0;
  const RankingView = loadRanking(ResultView, {
    api: {
      getLeaderboard() {
        calls += 1;
        if (calls === 1) return Promise.reject(new Error('랭킹 연결 실패'));
        return retryRequest.promise;
      },
    },
  });
  const container = new Element('main');
  const router = {
    state: { top3Profile: { required: false, status: 'SUBMITTED', game_version: '2.0.0' } },
    config: { campaign: { game_version: '2.0.0' } },
    isCurrent: (token) => token === 3,
  };

  await RankingView.render(container, router, 3);
  assert.match(container.textContent, /랭킹 연결 실패/);
  const retry = descendants(container).find((node) => node.tag === 'button');
  const recovering = retry.onclick();
  assert.equal(retry.onclick(), undefined, 'a double click cannot start a duplicate ranking request');
  assert.equal(calls, 2);
  retryRequest.resolve({
    leaderboard: [{ rank: 1, nickname: '재접속 러너', score: 88, is_me: true }],
    me: { rank: 1, best_score: 88 }, top3_gap: { status: 'IN_TOP3', rank: 1 },
  });
  await recovering;

  assert.match(container.textContent, /재접속 러너/);
  assert.equal(container.querySelector('#top3-request'), null);
  assert.doesNotMatch(container.textContent, /랭킹 연결 실패/);
});

test('ranking ignores reverse-order responses and a retry that finishes after leaving', async () => {
  const { view: ResultView } = loadResult();
  const oldRequest = deferred();
  const newRequest = deferred();
  const leavingRetry = deferred();
  const requests = [
    () => oldRequest.promise,
    () => newRequest.promise,
    () => Promise.reject(new Error('다시 불러와 주세요')),
    () => leavingRetry.promise,
  ];
  const RankingView = loadRanking(ResultView, { api: { getLeaderboard: () => requests.shift()() } });
  const container = new Element('main');
  let current = true;
  const router = { state: { top3Profile: { status: 'NOT_REQUIRED' } }, isCurrent: () => current };

  const oldRender = RankingView.render(container, router, 1);
  const newRender = RankingView.load(container, router, 1);
  newRequest.resolve({ leaderboard: [{ rank: 1, nickname: '새 응답', score: 90 }], me: null, top3_gap: { status: 'NO_SCORE' } });
  await newRender;
  oldRequest.resolve({ leaderboard: [{ rank: 1, nickname: '예전 응답', score: 10 }], me: null, top3_gap: { status: 'NO_SCORE' } });
  await oldRender;
  assert.match(container.textContent, /새 응답/);
  assert.doesNotMatch(container.textContent, /예전 응답/);

  await RankingView.load(container, router, 1);
  const retry = descendants(container).find((node) => node.tag === 'button');
  const late = retry.onclick();
  current = false;
  container.textContent = '다른 화면';
  leavingRetry.resolve({ leaderboard: [{ rank: 1, nickname: '늦은 응답', score: 100 }], me: null, top3_gap: { status: 'NO_SCORE' } });
  await late;
  assert.equal(container.textContent, '다른 화면');
});

test('result keeps the completed game and TOP3 contact CTA while its supplemental ranking request retries', async () => {
  const retryRequest = deferred();
  let calls = 0;
  const { view: ResultView } = loadResult({
    api: {
      getLeaderboard() {
        calls += 1;
        if (calls === 1) return Promise.reject(new Error('temporary'));
        return retryRequest.promise;
      },
    },
  });
  const { container, nodes } = resultContainer();
  const result = { score: 51, bestScore: 81, rank: 5, top3_gap: null };
  const router = {
    state: {
      lastResult: result, draw: { status: 'AVAILABLE' }, participant: { nickname: '완주 러너' },
      top3Profile: { required: true, status: 'REQUESTED', game_version: '2.0.0' },
    },
    config: { campaign: { game_version: '2.0.0' } },
    isCurrent: (token) => token === 6,
    navigate() {},
  };

  ResultView.render(container, router, 6);
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(nodes.get('#result-score').textContent, '51점');
  assert.match(nodes.get('#top3-request').textContent, /잠정 TOP3/);
  assert.match(nodes.get('#result-top3-gap').textContent, /불러오지 못했어요/);
  const retry = descendants(nodes.get('#result-top3-gap')).find((node) => node.tag === 'button');
  const recovering = retry.onclick();
  assert.equal(retry.onclick(), undefined, 'a double click cannot start a duplicate supplemental request');
  assert.equal(calls, 2);
  retryRequest.resolve({ me: { rank: 4 }, top3_gap: { status: 'CHASING', score_needed: 12 } });
  await recovering;

  assert.equal(result.rank, 4);
  assert.equal(nodes.get('#result-rank').textContent, '현재 4위');
  assert.equal(result.top3_gap.score_needed, 12);
  assert.match(nodes.get('#result-top3-gap').textContent, /12점/);
  assert.equal(nodes.get('#result-score').textContent, '51점');
  assert.match(nodes.get('#top3-request').textContent, /잠정 TOP3/);
});

test('result ignores reverse-order supplemental responses and completion after leaving', async () => {
  const oldRequest = deferred();
  const newRequest = deferred();
  const lateRequest = deferred();
  const requests = [oldRequest, newRequest, lateRequest];
  const { view: ResultView } = loadResult({ api: { getLeaderboard: () => requests.shift().promise } });
  const { container, nodes } = resultContainer();
  const result = { score: 20, bestScore: 20, rank: 8, top3_gap: null };
  let current = true;
  const router = { state: { lastResult: result, draw: {}, top3Profile: { status: 'NOT_REQUIRED' } }, isCurrent: () => current, navigate() {} };

  const oldLoad = ResultView.loadTop3Gap(container, router, 4, result);
  const newLoad = ResultView.loadTop3Gap(container, router, 4, result);
  newRequest.resolve({ me: { rank: 4 }, top3_gap: { status: 'CHASING', score_needed: 7 } });
  await newLoad;
  oldRequest.resolve({ me: { rank: 9 }, top3_gap: { status: 'CHASING', score_needed: 99 } });
  await oldLoad;
  assert.equal(result.rank, 4);
  assert.equal(nodes.get('#result-rank').textContent, '현재 4위');
  assert.equal(result.top3_gap.score_needed, 7);
  assert.match(nodes.get('#result-top3-gap').textContent, /7점/);

  result.top3_gap = null;
  const lateLoad = ResultView.loadTop3Gap(container, router, 4, result);
  current = false;
  nodes.get('#result-top3-gap').textContent = '다른 화면 상태';
  lateRequest.resolve({ me: { rank: 1 }, top3_gap: { status: 'IN_TOP3', rank: 1 } });
  await lateLoad;
  assert.equal(result.rank, 4);
  assert.equal(result.top3_gap, null);
  assert.equal(nodes.get('#result-top3-gap').textContent, '다른 화면 상태');
});

test('result passive updates replace TOP3 state and ignore stale render tokens', async () => {
  const { view: ResultView } = loadResult();
  const RankingView = loadRanking(ResultView);
  for (const [name, view] of [['result', ResultView]]) {
    const holder = new Element('div'); holder.id = 'top3-request';
    const container = new Element('main'); container.append(holder);
    let currentToken = 9;
    const router = {
      state: { top3Profile: { required: true, status: 'REQUESTED', game_version: '2.0.0' } },
      config: { campaign: { game_version: '2.0.0' } },
      isCurrent: (token) => token === currentToken,
    };
    await view.updateState(container, router, 9);
    assert.match(holder.textContent, /잠정 TOP3/, `${name} shows a newly requested profile`);
    router.state.top3Profile = { required: false, status: 'SUBMITTED', game_version: '2.0.0' };
    await view.updateState(container, router, 9);
    assert.match(holder.textContent, /TOP3 정보 접수 완료/, `${name} replaces requested with submitted`);
    const submittedText = holder.textContent;
    currentToken = 10;
    router.state.top3Profile = { required: false, status: 'NOT_REQUIRED' };
    await view.updateState(container, router, 9);
    assert.equal(holder.textContent, submittedText, `${name} ignores a stale update`);
    await view.updateState(container, router, 10);
    assert.equal(holder.children.length, 0, `${name} hides a non-required profile`);
  }
});

test('TOP3 submit returns to the screen where the modal opened and broadcasts the submitted state', async (t) => {
  for (const returnView of ['ranking', 'result']) {
    await t.test(returnView, async () => {
      const navigations = [];
      let announcements = 0;
      const harness = modalHarness({ submit: async () => ({ status: 'SUBMITTED', submitted_at: '2026-09-26T00:00:00Z' }) });
      const router = {
        currentView: returnView,
        renderToken: 5,
        state: { top3Profile: { required: true, status: 'REQUESTED', game_version: '2.0.0' }, lastResult: null },
        isCurrent: (token) => token === 5,
        announceStateChange() { announcements += 1; },
        async navigate(viewName, options) { navigations.push([viewName, options]); },
      };
      harness.view.top3Modal(router, 5);
      const modal = harness.getModal();
      descendants(modal.content).find((input) => input.tag === 'input' && !input.name).checked = true;
      assert.equal(await modal.onConfirm(), undefined);
      assert.equal(router.state.top3Profile.required, false);
      assert.equal(router.state.top3Profile.status, 'SUBMITTED');
      assert.equal(announcements, 1);
      assert.deepEqual(JSON.parse(JSON.stringify(navigations)), [[returnView, { replace: true }]]);
      assert.deepEqual(harness.analyticsEvents, ['top3_profile_started', 'top3_profile_submitted']);
    });
  }
});

test('TOP3 submission failure keeps entered values and the modal open for retry', async () => {
  const harness = modalHarness({ submit: async () => { throw new Error('temporary failure'); } });
  const navigations = [];
  const router = {
    currentView: 'ranking', renderToken: 2,
    state: { top3Profile: { required: true, status: 'REQUESTED' } },
    isCurrent: () => true,
    navigate: (...args) => navigations.push(args),
  };
  harness.view.top3Modal(router, 2);
  const modal = harness.getModal();
  const inputs = descendants(modal.content).filter((node) => node.tag === 'input');
  const named = Object.fromEntries(inputs.filter((input) => input.name).map((input) => [input.name, input]));
  named.name.value = 'TEST_재시도';
  named.contact.value = '01000000000';
  named.school.value = 'TEST_학교';
  inputs.find((input) => !input.name).checked = true;

  assert.equal(await modal.onConfirm(), false);
  assert.equal(named.name.value, 'TEST_재시도');
  assert.equal(named.contact.value, '01000000000');
  assert.equal(named.school.value, 'TEST_학교');
  assert.deepEqual(navigations, []);
  assert.deepEqual(harness.toasts, ['temporary failure']);
});

test('ranking claims explain the final cutoff and use record sharing', () => {
  const view = loadPrize();
  const routes = [];
  const router = { navigate: (route) => routes.push(route), shareContext: null };
  const ranking = view.claimCard({
    id: 'ranking-claim', claim_type: 'RANKING', prize_name: null,
    status: 'INFORMATION_RECEIVED', contact_submitted: true,
  }, router, 1);
  assert.match(ranking.textContent, /TOP3 접수 내역/);
  assert.match(ranking.textContent, /최종 수상.*이벤트 종료 시점 기준/);
  const rankingShare = descendants(ranking).find((node) => node.tag === 'a' && /공유/.test(node.textContent));
  assert.match(rankingShare.textContent, /기록 공유/);
  rankingShare.onclick({ preventDefault() {} });
  assert.equal(router.shareContext, 'record_share');
  assert.deepEqual(routes, ['invite']);
});

test('draw claims retain prize-result copy and prize sharing', () => {
  const view = loadPrize();
  const routes = [];
  const router = { navigate: (route) => routes.push(route), shareContext: null };
  const draw = view.claimCard({
    id: 'draw-claim', claim_type: 'DRAW', prize_name: '테스트 커피',
    status: 'INFORMATION_RECEIVED', contact_submitted: true,
  }, router, 1);
  assert.match(draw.textContent, /테스트 커피/);
  assert.match(draw.textContent, /복주머니 경품/);
  const drawShare = descendants(draw).find((node) => node.tag === 'a' && /공유/.test(node.textContent));
  assert.match(drawShare.textContent, /경품 결과 공유/);
  drawShare.onclick({ preventDefault() {} });
  assert.equal(router.shareContext, 'prize_share');
  assert.deepEqual(routes, ['invite']);
});

test('ranking displays actual time gaps, participant count, and safe empty states', async () => {
  const data = { me: { rank: 4, best_score: 450, best_elapsed_seconds: 30 }, top3_gap: { third_score: 600, third_elapsed_seconds: 42.3, participant_count: 1234 }, leaderboard: [] };
  const view = loadRanking(null, { api: { getLeaderboard: async () => data } });
  const container = new Element('main');
  await view.render(container, { isCurrent: () => true }, 1);
  assert.match(container.textContent, /4위/);
  assert.match(container.textContent, /450점/);
  assert.match(container.textContent, /1,234명/);
  assert.match(container.textContent, /12.3초 짧게/);
  data.me.best_elapsed_seconds = 45;
  assert.match(view.timeGapMessage(data), /2.7초 더/);
  data.me.best_elapsed_seconds = 42.3;
  assert.match(view.timeGapMessage(data), /시간이 같아요/);
  data.me.best_elapsed_seconds = null;
  assert.match(view.timeGapMessage(data), /시간 기록을 확인/);
  data.top3_gap.third_score = null;
  assert.match(view.timeGapMessage(data), /아직 3위 기록이 없어요/);
  data.me = null;
  assert.match(view.timeGapMessage(data), /첫 게임/);
});
