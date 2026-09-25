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
    this._text = '';
  }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent || '').join(''); }
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
  replaceChildren(...children) { this._text = ''; this.children = children; }
  querySelector(selector) {
    if (selector.startsWith('#')) return descendants(this).find((node) => node.id === selector.slice(1)) || null;
    return descendants(this).find((node) => node.tag === selector) || null;
  }
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

test('ranking reconnect renders a submitted TOP3 card without relying on lastResult', async () => {
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
  assert.ok(holder, 'ranking always renders the persistent TOP3 state holder');
  assert.match(holder.textContent, /TOP3 정보 접수 완료/);
  assert.equal(descendants(holder).find((node) => node.tag === 'button').disabled, true);
});

test('result and ranking passive updates replace TOP3 state and ignore stale render tokens', async () => {
  const { view: ResultView } = loadResult();
  const RankingView = loadRanking(ResultView);
  for (const [name, view] of [['result', ResultView], ['ranking', RankingView]]) {
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
