const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function deferred() {
  let resolve;
  let reject;
  const promise = new Promise((ok, fail) => { resolve = ok; reject = fail; });
  return { promise, resolve, reject };
}

function element(tag = 'div') {
  return {
    tag, textContent: '', className: '', children: [], checked: false, required: false,
    hidden: false, inert: false, tabIndex: 0, attrs: {}, dataset: {},
    classList: { add() {}, toggle() {} },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
    getAttribute(name) { return this.attrs[name] ?? null; },
    focus() {},
  };
}

function loadView(file, exportName, globals = {}) {
  const source = fs.readFileSync(path.join(root, file), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace(`export const ${exportName} =`, 'globalThis.__view =');
  const context = { console, ...globals };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: file });
  return context.__view;
}

function claimsHarness(getClaims) {
  const container = element();
  container.replaceChildren = (...children) => { container.children = children; };
  container.querySelector = (selector) => container.children.find((child) => child.className.split(' ').includes(selector.slice(1)));
  const originalAppend = container.appendChild;
  container.appendChild = (child) => {
    child.remove = () => { container.children = container.children.filter((item) => item !== child); };
    originalAppend.call(container, child);
  };
  const view = loadView('public/js/views/prize_view.js', 'PrizeView', {
    api: { getClaims }, analytics: { track() {} }, ui: {},
    document: { createElement: (tag) => element(tag) },
  });
  const router = { isCurrent: () => true };
  const claim = (status) => ({ id: 'claim-1', claim_type: 'DRAW', prize_name: '테스트 경품', status, contact_submitted: true });
  const text = (node = container) => [node.textContent, ...node.children.map((child) => text(child))].join(' ');
  return { view, container, router, claim, text };
}

test('returning to the claims screen reads the current submitted status', async () => {
  let status = 'INFORMATION_RECEIVED';
  const h = claimsHarness(async () => ({ claims: [h.claim(status)] }));
  await h.view.render(h.container, h.router, 7);
  assert.match(h.text(), /정보 접수/);
  status = 'PENDING_REVIEW';
  await h.view.updateState(h.container, h.router, 7);
  assert.match(h.text(), /확인 대기/);
  assert.doesNotMatch(h.text(), /아직 지급 완료 상태는 아니에요/);
  assert.equal(h.container.children.filter((node) => node.tag === 'article').length, 1);
});

test('a claims refresh failure preserves the cards and can be retried in place', async () => {
  let fail = false;
  const h = claimsHarness(async () => {
    if (fail) throw new Error('일시 연결 실패');
    return { claims: [h.claim('INFORMATION_RECEIVED')] };
  });
  await h.view.render(h.container, h.router, 7);
  const savedCard = h.container.children.find((node) => node.tag === 'article');
  fail = true;
  await h.view.updateState(h.container, h.router, 7);
  assert.ok(h.container.children.includes(savedCard));
  assert.match(h.text(), /일시 연결 실패/);
  await h.view.updateState(h.container, h.router, 7);
  assert.equal(h.container.children.filter((node) => node.className.includes('claim-load-error')).length, 1);
  fail = false;
  const retry = h.container.querySelector('.claim-load-error').children.find((node) => node.tag === 'button');
  await retry.onclick();
  assert.doesNotMatch(h.text(), /일시 연결 실패/);
  assert.equal(h.container.children.filter((node) => node.tag === 'article').length, 1);
});

test('an older claims response cannot overwrite a newer refresh in the same screen', async () => {
  const first = deferred();
  let calls = 0;
  const h = claimsHarness(() => ++calls === 1 ? first.promise : Promise.resolve({ claims: [h.claim('PENDING_REVIEW')] }));
  const opening = h.view.render(h.container, h.router, 7);
  await h.view.updateState(h.container, h.router, 7);
  first.resolve({ claims: [h.claim('AWAITING_INFORMATION')] });
  await opening;
  assert.match(h.text(), /확인 대기/);
  assert.doesNotMatch(h.text(), /정보 입력 대기/);
});

for (const scenario of [
  { name: 'ranking', file: 'public/js/views/ranking_view.js', exportName: 'RankingView', method: 'getLeaderboard' },
  { name: 'draw', file: 'public/js/views/draw_view.js', exportName: 'DrawView', method: 'getDraw' },
  { name: 'claims', file: 'public/js/views/prize_view.js', exportName: 'PrizeView', method: 'getClaims' },
]) {
  test(`${scenario.name} load failure cannot replace a newer screen`, async () => {
    const request = deferred();
    let current = true;
    const container = {
      innerHTML: '', marker: 'loading',
      replaceChildren() { this.marker = 'replaced-by-old-view'; },
      appendChild() { this.marker = 'appended-by-old-view'; },
    };
    const view = loadView(scenario.file, scenario.exportName, {
      api: { [scenario.method]: () => request.promise },
      analytics: { track() {} },
      ui: {}, ResultView: {}, ScratchCard: class {},
      document: { createElement: (tag) => element(tag) },
      sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
    });
    const render = view.render(container, { isCurrent: () => current }, 7);
    current = false;
    container.marker = 'new-screen';
    request.reject(new Error('late failure'));
    await render;
    assert.equal(container.marker, 'new-screen');
  });
}

test('TOP3 submission preserves version provenance and does not navigate from a stale result', async () => {
  const request = deferred();
  let current = true;
  let modal;
  const checkboxes = [];
  const navigations = [];
  const document = {
    createElement(tag) {
      const node = element(tag);
      if (tag === 'input') checkboxes.push(node);
      return node;
    },
  };
  const ui = {
    formField(_label, _type, name, options = {}) {
      const input = element('input');
      input.name = name;
      input.required = options.required !== false;
      const label = element('label'); label.appendChild(input);
      return { input, label };
    },
    showModal(options) { modal = options; },
    showToast() {},
  };
  const view = loadView('public/js/views/result_view.js', 'ResultView', {
    api: { submitTop3Profile: () => request.promise },
    analytics: { track() {} }, ui, document,
  });
  const router = {
    renderToken: 4,
    state: { top3Profile: { required: true, status: 'REQUESTED', game_version: '1.2.0' }, lastResult: {} },
    isCurrent: () => current,
    navigate: (viewName) => navigations.push(viewName),
  };
  view.top3Modal(router, 4);
  checkboxes.at(-1).checked = true;
  const submit = modal.onConfirm();
  current = false;
  request.resolve({ status: 'SUBMITTED', submitted_at: '2026-09-26T00:00:00Z' });
  assert.equal(await submit, true);
  assert.equal(router.state.top3Profile.game_version, '1.2.0');
  assert.equal(router.state.top3Profile.status, 'SUBMITTED');
  assert.deepEqual(navigations, []);
});

test('claim submission completion does not navigate away from a newer screen', async () => {
  const request = deferred();
  let current = true;
  let modal;
  let checkbox;
  const navigations = [];
  const document = {
    createElement(tag) {
      const node = element(tag);
      if (tag === 'input') checkbox = node;
      return node;
    },
  };
  const ui = {
    formField(_label, _type, name, options = {}) {
      const input = element('input');
      input.name = name;
      input.required = Boolean(options.required);
      const label = element('label'); label.appendChild(input);
      return { input, label };
    },
    showModal(options) { modal = options; },
    showToast() {},
  };
  const view = loadView('public/js/views/prize_view.js', 'PrizeView', {
    api: { submitClaim: () => request.promise },
    analytics: { track() {} }, ui, document,
  });
  const router = {
    renderToken: 9,
    isCurrent: () => current,
    announceStateChange() {},
    navigate: (viewName) => navigations.push(viewName),
  };
  view.claimModal({ id: 'claim-1', claim_type: 'DRAW' }, router, 9);
  checkbox.checked = true;
  const submit = modal.onConfirm();
  current = false;
  request.resolve({ status: 'INFORMATION_RECEIVED' });
  assert.equal(await submit, true);
  assert.deepEqual(navigations, []);
});

test('an old pouch request cannot pass after leaving and re-entering draw', async () => {
  const request = deferred();
  let currentToken = 1;
  let scratchRenders = 0;
  const open = element('button');
  const pouches = [0, 1, 2].map((index) => {
    const pouch = element('button'); pouch.dataset.index = String(index); return pouch;
  });
  const container = {
    innerHTML: '',
    querySelector: () => open,
    querySelectorAll: () => pouches,
  };
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    api: { drawPouch: () => request.promise },
    analytics: { track() {} }, ui: { showToast() {} }, ScratchCard: class {},
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  view.renderScratch = () => { scratchRenders += 1; };
  view.renderToken = 1;
  let refreshes = 0, broadcasts = 0;
  const router = { isCurrent: (token) => token === currentToken, announceStateChange() { broadcasts += 1; }, async refreshState() { refreshes += 1; } };
  view.renderSelection(container, router, 1);
  pouches[0].onclick();
  const opening = open.onclick();
  currentToken = 2;
  view.renderToken = 2;
  request.resolve({ draw_id: 'old-draw', pouch_index: 0 });
  await opening;
  assert.equal(scratchRenders, 0);
  assert.equal(refreshes, 1, 'the current screen reads the committed draw without rendering the old screen');
  assert.equal(broadcasts, 1);
});

test('a newly committed draw updates current state before rendering scratch', async () => {
  const open = element('button');
  const pouch = element('button'); pouch.dataset.index = '1';
  const container = { innerHTML: '', querySelector: () => open, querySelectorAll: () => [pouch] };
  const draw = { draw_id: 'draw-new', pouch_index: 1, is_won: false };
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    api: { drawPouch: async () => draw }, analytics: { track() {} },
    ui: { showToast(message) { throw new Error(message); } },
  });
  let renders = 0, broadcasts = 0;
  const router = { state: { draw: { status: 'AVAILABLE' } }, isCurrent: () => true, announceStateChange() { broadcasts += 1; } };
  view.renderScratch = (_container, _router, saved) => {
    assert.equal(router.state.draw.status, 'DRAWN');
    assert.equal(router.state.draw.draw_id, draw.draw_id);
    assert.equal(saved, draw);
    renders += 1;
  };
  view.renderSelection(container, router, 1);
  pouch.onclick();
  await open.onclick();
  assert.equal(renders, 1);
  assert.equal(broadcasts, 1);
});

test('an old scratch save cannot complete after draw is re-entered', async () => {
  const request = deferred();
  let currentToken = 3;
  const events = [];
  const selectors = ['#scratch-title', '#scratch-instruction', '#result-prize-img', '#result-prize-title', '#result-prize-sub', '#btn-after-draw', '#btn-instant-reveal', '#restored-pouch', '#post-reveal-actions', '#scratch-save-status', '#scratch-canvas', '#scratch-result-content'];
  const nodes = new Map(selectors.map((selector) => [selector, element()]));
  class ScratchCardMock {
    constructor(_canvas, options) { this.options = options; }
    revealInstantly() { return this.options.onReveal(); }
    destroy() {}
  }
  const view = loadView('public/js/views/draw_view.js', 'DrawView', {
    api: { createRequestId: () => 'scratch-old', completeScratch: () => request.promise },
    analytics: { track: (name) => events.push(name) },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    ScratchCard: ScratchCardMock,
    document: { activeElement: null },
    sessionStorage: { getItem: () => null, setItem() {}, removeItem() {} },
  });
  const router = { isCurrent: (token) => token === currentToken, navigate() {}, announceStateChange() {} };
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  view.renderToken = 3;
  view.renderScratch(container, router, { draw_id: 'draw-old', pouch_index: 0, is_won: false, scratch_completed: false, prize: {} }, 3);
  const saving = view.scratchCard.revealInstantly();
  currentToken = 4;
  view.renderToken = 4;
  request.resolve({ scratch_completed: true });
  await saving;
  assert.equal(events.includes('scratch_completed'), false);
  assert.notEqual(nodes.get('#scratch-save-status').textContent, '결과 확인이 저장됐습니다.');
});
