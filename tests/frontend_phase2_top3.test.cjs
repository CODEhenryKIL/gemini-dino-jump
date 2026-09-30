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
    prepareResultReferralShare: async () => ({ share() {} }),
    ui: { text: (node, value) => { node.textContent = String(value); }, showToast() {}, showModal() {}, formField(labelText, type, name) { const label = new Element('label'); label.textContent = labelText; const input = new Element('input'); input.type = type; input.name = name; label.append(input); return { label, input }; } },
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
    prepareResultReferralShare: async () => ({ share: async () => ({ status: 'cancelled' }) }),
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
    setTimeout,
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
    hideModal() {},
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
  const router = { renderToken: 7, state: { lastResult: { rank: 1 } }, config: { campaign: { game_version: '2.0.0' } } };

  view.renderTop3Request(target, router, { required: true, status: 'REQUESTED', game_version: '2.0.0' });
  assert.equal(target.children.length, 1);
  assert.match(target.textContent, /수령 정보를 등록/);
  assert.equal(descendants(target).find((node) => node.tag === 'button').disabled, false);

  view.renderTop3Request(target, router, { required: false, status: 'SUBMITTED', game_version: '2.0.0' });
  assert.equal(target.children.length, 1, 'submitted state replaces the requested card instead of appending');
  assert.match(target.textContent, /TOP3 정보 접수 완료/);
  assert.match(target.textContent, /수령함에서 접수 상태/);
  assert.equal(descendants(target).find((node) => node.tag === 'form'), undefined);

  view.renderTop3Request(target, router, { required: false, status: 'NOT_REQUIRED' });
  assert.equal(target.children.length, 0);
});

test('leaving TOP3 hides a historical contact request and reentry restores it', () => {
  const { view } = loadResult();
  const target = new Element();
  const router = { state: { lastResult: { rank: 2 } } };
  const profile = { status: 'REQUESTED', game_version: '2.1.0', eligible: true };
  view.renderTop3Request(target, router, profile);
  assert.equal(target.hidden, false);
  router.state.lastResult.rank = 4;
  view.renderTop3Request(target, router, profile);
  assert.equal(target.hidden, true);
  assert.equal(target.children.length, 0);
  router.state.lastResult.rank = 2;
  view.renderTop3Request(target, router, { ...profile, eligible: false });
  assert.equal(target.hidden, true);
  view.renderTop3Request(target, router, profile);
  assert.equal(target.hidden, false);
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
  assert.match(container.textContent, /🥇5만원.*🥈2만원.*🥉1만원/);
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

test('result keeps the completed game but hides an old TOP3 request while ranking retries', async () => {
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
  assert.equal(nodes.get('#top3-request').hidden, true);
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
  assert.match(nodes.get('#result-top3-gap').textContent, /약 2초/);
  assert.equal(nodes.get('#result-score').textContent, '51점');
  assert.equal(nodes.get('#top3-request').hidden, true);
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
  assert.match(nodes.get('#result-top3-gap').textContent, /약 1초/);

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
      state: { lastResult: { rank: 1 }, top3Profile: { required: true, status: 'REQUESTED', game_version: '2.0.0' } },
      config: { campaign: { game_version: '2.0.0' } },
      isCurrent: (token) => token === currentToken,
    };
    await view.updateState(container, router, 9);
    assert.match(holder.textContent, /수령 정보를 등록/, `${name} shows a newly requested profile`);
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

function fillContact(form) {
  const inputs = descendants(form).filter(node => node.tag === 'input');
  const values = { name: '홍길동', contact: '010-1234-5678', school: '테스트대학교' };
  for (const input of inputs) { if (input.name) input.value = values[input.name]; else input.checked = true; }
}

test('TOP3 direct form starts blank, accepts ordinary values, broadcasts and blocks double submission', async () => {
  const request = deferred(); let calls = 0, announcements = 0, payload;
  const harness = modalHarness({ submit: async data => { calls++; payload = data; return request.promise; } });
  const router = { renderToken: 5, state: { top3Profile: { status: 'REQUESTED' }, lastResult: {} }, isCurrent: () => true, announceStateChange() { announcements++; } };
  const form = harness.view.top3Form(router, 5);
  assert.ok(descendants(form).filter(node => node.name).every(node => node.value === ''));
  assert.doesNotMatch(form.textContent, /합성|테스트 정보|현재 순위가 내려가더라도/);
  fillContact(form);
  const submit = form.onsubmit({ preventDefault() {} });
  await form.onsubmit({ preventDefault() {} });
  assert.equal(calls, 1);
  assert.equal(payload.name, '홍길동');
  request.resolve({ status: 'SUBMITTED', submitted_at: '2026-09-26T00:00:00Z' });
  await submit;
  assert.equal(router.state.top3Profile.status, 'SUBMITTED');
  assert.equal(announcements, 1);
  assert.match(form.textContent, /정보 접수 완료/);
  assert.deepEqual(harness.analyticsEvents, ['top3_profile_started', 'top3_profile_submitted']);
});

test('TOP3 auto prompt congratulates the current rank and submits directly to the draw flow', async () => {
  const harness = modalHarness({ submit: async () => ({ status: 'SUBMITTED', submitted_at: '2026-09-30T00:00:00Z' }) });
  const router = {
    renderToken: 8,
    state: { top3Profile: { status: 'REQUESTED', eligible: true }, lastResult: { rank: 2, top3_gap: { status: 'IN_TOP3', rank: 2 } } },
    isCurrent: () => true,
    announceStateChange() {},
  };
  assert.equal(harness.view.openTop3Modal(router, 8), true);
  const modal = harness.getModal();
  assert.equal(modal.confirmText, '저장하고 경품 뽑기');
  assert.match(modal.content.textContent, /현재 2위로 TOP3/);
  const form = descendants(modal.content).find((node) => node.tag === 'form');
  fillContact(form);
  assert.equal(await modal.onConfirm(), true);
  assert.equal(router.state.top3Profile.status, 'SUBMITTED');
  assert.equal(harness.view.openTop3Modal(router, 8), false, 'submitted contact never reopens');
});

test('TOP3 inline failure preserves entered values and allows retry', async () => {
  let calls = 0;
  const harness = modalHarness({ submit: async () => { calls++; if (calls === 1) throw new Error('temporary failure'); return { status: 'SUBMITTED' }; } });
  const router = { renderToken: 2, state: { top3Profile: { status: 'REQUESTED' } }, isCurrent: () => true };
  const form = harness.view.top3Form(router, 2);
  await form.onsubmit({ preventDefault() {} });
  assert.equal(calls, 0);
  fillContact(form);
  await form.onsubmit({ preventDefault() {} });
  assert.match(form.textContent, /temporary failure/);
  assert.equal(descendants(form).find(node => node.name === 'name').value, '홍길동');
  assert.equal(descendants(form).find(node => node.tag === 'button').disabled, false);
  await form.onsubmit({ preventDefault() {} });
  assert.equal(router.state.top3Profile.status, 'SUBMITTED');
});

test('passive TOP3 refresh preserves the compact popup entry without replacing it', () => {
  const { view } = loadResult();
  const target = new Element();
  const router = { renderToken: 3, state: { lastResult: { rank: 1 } } };
  const profile = { status: 'REQUESTED', game_version: '2.1.0' };
  view.renderTop3Request(target, router, profile);
  const button = descendants(target).find(node => node.tag === 'button');
  assert.match(button.textContent, /수령 정보 입력/);
  view.renderTop3Request(target, router, { ...profile });
  assert.equal(descendants(target).find(node => node.tag === 'button'), button);
});

test('result prioritizes the pouch before replay and sharing while sharing opens in place', async () => {
  let shares = 0;
  const { view } = loadResult({ prepareResultReferralShare: async () => ({ share() { shares++; } }) });
  const { container, nodes } = resultContainer();
  const routes = [];
  view.render(container, { state: { lastResult: { score: 40, bestScore: 50, rank: 4, top3_gap: { status: 'CHASING', score_needed: 42 } } }, navigate: name => routes.push(name) }, 1);
  await new Promise(resolve => setImmediate(resolve));
  nodes.get('#btn-share-record').onclick();
  assert.equal(shares, 1);
  assert.deepEqual(routes, []);
  assert.ok(container.innerHTML.indexOf('id="btn-play-again"') < container.innerHTML.indexOf('id="btn-share-record"'));
  assert.ok(container.innerHTML.indexOf('id="btn-go-pouch"') < container.innerHTML.indexOf('id="btn-play-again"'));
  assert.ok(container.innerHTML.indexOf('id="top3-request"') > container.innerHTML.indexOf('id="btn-go-pouch"'));
  assert.doesNotMatch(container.innerHTML, /기록 검증 완료/);
  assert.doesNotMatch(container.innerHTML, /#TeamGemini|2026 캠퍼스 챌린지|랭킹 닉네임|이번 판/);
  assert.match(nodes.get('#result-top3-gap').textContent, /TOP3까지 약 5초만 더!/);
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
  assert.doesNotMatch(draw.textContent, /복주머니 기록|복주머니.*회차/);
  const drawShare = descendants(draw).find((node) => node.tag === 'a' && /공유/.test(node.textContent));
  assert.match(drawShare.textContent, /경품 결과 공유/);
  drawShare.onclick({ preventDefault() {} });
  assert.equal(router.shareContext, 'prize_share');
  assert.deepEqual(routes, ['invite']);
});

test('ranking uses score-equivalent seconds consistently despite longer elapsed play', async () => {
  const data = { me: { rank: 4, best_score: 749, best_elapsed_seconds: 90.9 }, top3_gap: { status: 'CHASING', score_needed: 51, third_score: 800, third_elapsed_seconds: 80, participant_count: 1234 }, leaderboard: [] };
  const view = loadRanking(null, { api: { getLeaderboard: async () => data } });
  const container = new Element('main');
  await view.render(container, { isCurrent: () => true }, 1);
  assert.match(container.textContent, /4위/);
  assert.match(container.textContent, /749점/);
  assert.match(container.textContent, /1,234명/);
  assert.equal(view.timeGapMessage(data), '3위까지 약 6초 더!');
  data.me.best_elapsed_seconds = 30;
  assert.equal(view.timeGapMessage(data), '3위까지 약 6초 더!');
  data.top3_gap.score_needed = 50;
  assert.equal(view.timeGapMessage(data), '3위까지 약 5초 더!');
  data.top3_gap.score_needed = null;
  assert.match(view.timeGapMessage(data), /점수를 확인/);
  data.top3_gap.third_score = null;
  assert.match(view.timeGapMessage(data), /아직 3위 기록이 없어요/);
  data.me.rank = 2;
  assert.equal(view.timeGapMessage(data), '현재 2위로 TOP3예요!');
  data.me = null;
  assert.match(view.timeGapMessage(data), /첫 게임을 마치면\n/);
});

test('claim draft resumes, cancelled share stays pending, and only a confirmed Kakao intent finalizes', async () => {
  let modal;
  let submitted = 0;
  let shared = 0;
  let outcome = { method: 'native', status: 'cancelled' };
  let failSubmit = true;
  let intentStatus = 'confirmed';
  const drafts = [];
  const routes = [];
  const view = loadPrize({
    api: {
      getClaimDraft: async () => ({ draft: { name: '테스트', contact: '01000000000', school: '테스트학교', address: '테스트주소', consent: true } }),
      saveClaimDraft: async (_id, payload) => drafts.push(payload),
      getReferralShareIntent: async (shareId) => { assert.equal(shareId, 'share-1'); return { status: intentStatus, tickets: { invitation: 1, available_total: 1 } }; },
      submitClaim: async (_id, payload) => { submitted++; assert.equal(payload.share_intent_id, 'share-1'); if (failSubmit) throw new Error('다시 시도'); },
    },
    prepareResultReferralShare: async () => ({ share: async () => { shared++; return outcome; } }),
    ui: {
      showModal: (options) => { modal = options; }, showToast() {},
      formField(labelText, type, name, opts) { const label = new Element('label'); const input = new Element('input'); input.name = name; input.required = opts.required; label.append(input); return { label, input }; },
    },
  });
  const router = { state: { tickets: { invitation: 0, available_total: 0 } }, isCurrent: () => true, announceStateChange() {}, navigate: (route) => routes.push(route) };
  await view.claimModal({ id: 'claim-1', claim_type: 'DRAW', category: 'SHIPPING' }, router, 1);
  assert.equal(modal.confirmText, '다음');
  assert.equal(descendants(modal.content).find((node) => node.name === 'name').value, '테스트');
  await modal.onConfirm();
  assert.equal(shared, 0, 'step 1 saves the draft without opening Kakao');
  assert.equal(drafts.length, 1);
  assert.equal(drafts[0].consent, true);
  assert.equal(drafts[0].notice_version, 'claim-contact-v1');
  assert.equal(submitted, 0);
  assert.equal(modal.title, '2 / 3 · 카카오톡 공유');
  await new Promise(setImmediate);
  const button = descendants(modal.content).find((node) => node.tag === 'button');
  assert.match(modal.content.textContent, /나에게 보내기/);
  await button.onclick();
  assert.equal(shared, 1);
  assert.equal(submitted, 0);
  assert.match(modal.content.textContent, /공유를 취소/);
  outcome = { method: 'kakao', status: 'pending', shareId: 'share-1' };
  await button.onclick();
  assert.equal(submitted, 1);
  assert.equal(shared, 2);
  assert.equal(router.state.tickets.invitation, 1);
  failSubmit = false;
  await button.onclick();
  assert.equal(submitted, 2);
  assert.equal(shared, 2);
  assert.equal(modal.title, '3 / 3 · 접수 완료');
  modal.onConfirm();
  assert.deepEqual(routes, ['claims']);
});

test('claim step 1 saves first and step 2 accepts a confirmed Kakao self-send webhook', async () => {
  let modal; let opened = 0; let finalized = 0;
  const saving = deferred();
  const view = loadPrize({
    api: {
      getClaimDraft: async () => ({ draft: { name: 'TEST_사용자', contact: '01000000000', school: 'TEST_학교', consent: true } }),
      saveClaimDraft: () => saving.promise,
      getReferralShareIntent: async (shareId) => { assert.equal(shareId, 'share-direct'); return { status: 'confirmed', chat_type: 'MemoChat' }; },
      submitClaim: async (_id, payload) => { assert.equal(payload.share_intent_id, 'share-direct'); finalized++; },
    },
    prepareResultReferralShare: async (_router, options) => {
      assert.equal(options.claimId, 'claim-direct');
      return { share: async () => { opened++; return { method: 'kakao', status: 'pending', shareId: 'share-direct' }; } };
    },
    ui: { showModal: (value) => { modal = value; }, showToast() {}, formField(_label, _type, name, opts) { const label = new Element('label'); const input = new Element('input'); input.name = name; input.required = opts.required; label.append(input); return { label, input }; } },
  });
  await view.claimModal({ id: 'claim-direct', category: 'COUPON' }, { isCurrent: () => true, navigate() {}, announceStateChange() {} }, 1);
  const clicked = modal.onConfirm();
  assert.equal(opened, 0);
  assert.equal(finalized, 0);
  saving.resolve({ draft_saved: true });
  await clicked;
  await new Promise(setImmediate);
  assert.equal(modal.title, '2 / 3 · 카카오톡 공유');
  assert.equal(opened, 0);
  const button = descendants(modal.content).find((node) => node.tag === 'button');
  await button.onclick();
  assert.equal(finalized, 1);
  assert.equal(opened, 1);
  assert.equal(modal.title, '3 / 3 · 접수 완료');
});

test('a late webhook check cannot submit a claim after the share step is closed', async () => {
  let modal; let submitted = 0;
  const checking = deferred();
  const routes = [];
  const view = loadPrize({
    api: {
      getReferralShareIntent: () => checking.promise,
      submitClaim: async () => { submitted++; },
    },
    prepareResultReferralShare: async () => ({ share: async () => ({ method: 'kakao', status: 'pending', shareId: 'unused' }) }),
    ui: { showModal: (value) => { modal = value; } },
  });
  view.claimShareModal(
    { id: 'claim-late', claim_type: 'DRAW' },
    { isCurrent: () => true, navigate: (route) => routes.push(route), state: {} },
    1,
    { method: 'kakao', status: 'pending', shareId: 'share-late' },
  );
  await Promise.resolve();
  modal.onConfirm();
  checking.resolve({ status: 'confirmed' });
  await new Promise(setImmediate);
  assert.equal(submitted, 0);
  assert.deepEqual(routes, ['claims']);
});


test('ranking bottom share button uses retry copy and opens sharing in place', async () => {
  let kind; let opened = 0;
  const view = loadRanking(null, { prepareResultReferralShare: async (_router, options) => { kind = options.kind; return { share: async () => { opened++; return { method: 'kakao', status: 'attempted' }; } }; } });
  const container = new Element('main');
  await view.render(container, { isCurrent: () => true, navigate() { throw new Error('must share in place'); } }, 1);
  await new Promise(setImmediate);
  const button = container.querySelector('#btn-ranking-share');
  assert.equal(kind, 'retry_invite');
  assert.match(button.innerHTML, /공유하고 한 판 더/);
  const dock = container.children.find((node) => node.className === 'ranking-share-dock');
  assert.ok(dock.children.includes(button));
  assert.ok(container.children.indexOf(dock) > container.children.findIndex((node) => node.className === 'card ranking-list'));
  assert.equal(button.disabled, false);
  await button.onclick();
  assert.equal(opened, 1);
});


test('replay visibility respects 100-point boundary, balances, unlimited mode and campaign pause', () => {
  const { view } = loadResult();
  const replay = new Element('button');
  const container = { querySelector: selector => selector === '#btn-play-again' ? replay : null };
  const router = { state: { lastResult: { score: 100, rank: 4 }, tickets: { available_total: 0 } }, config: { campaign: { status: 'ACTIVE' } } };
  view.updateState(container, router); assert.equal(replay.hidden, false);
  router.state.lastResult.score = 101;
  view.updateState(container, router); assert.equal(replay.hidden, true);
  router.state.tickets.available_total = 1;
  view.updateState(container, router); assert.equal(replay.hidden, false);
  router.state.tickets = { available_total: 0, unlimited_play: true };
  view.updateState(container, router); assert.equal(replay.hidden, false);
  router.config.campaign.status = 'PAUSED';
  view.updateState(container, router); assert.equal(replay.disabled, true);
});

test('TOP3 celebration runs once per result and respects reduced motion and rank', () => {
  const { view, context } = loadResult();
  const host = new Element();
  context.document.createElement = () => ({ style: {} });
  const container = { querySelector: () => host };
  const result = { rank: 3 };
  view.celebrateTop3(container, result); assert.equal(host.children.length, 32);
  view.celebrateTop3(container, result); assert.equal(host.children.length, 32);
  view.celebrateTop3(container, { rank: 4 }); assert.equal(host.children.length, 32);
  context.matchMedia = () => ({ matches: true });
  view.celebrateTop3(container, { rank: 1 }); assert.equal(host.children.length, 32);
});

test('replay opens the game guide and ignores stale clicks', () => {
  let guides = 0;
  const { view } = loadResult({ showGameGuide: () => { guides++; } });
  const { container } = resultContainer();
  const originalQuery = container.querySelector;
  const replay = new Element('button');
  container.querySelector = selector => selector === '#btn-play-again' ? replay : originalQuery(selector);
  let current = true;
  const router = { state: { lastResult: { score: 100, rank: 4, top3_gap: {} }, tickets: { available_total: 1 } }, isCurrent: () => current };
  view.render(container, router, 1);
  replay.onclick(); assert.equal(guides, 1);
  current = false; replay.onclick(); assert.equal(guides, 1);
});
