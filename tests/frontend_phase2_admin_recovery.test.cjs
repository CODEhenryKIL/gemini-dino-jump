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

function node(tag = 'div') {
  return {
    tag, textContent: '', className: '', value: '', checked: false, disabled: false,
    hidden: false, children: [], attrs: {}, dataset: {}, onclick: null, onsubmit: null,
    classList: { add() {}, remove() {}, toggle() {} },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); return child; },
    replaceChildren(...children) { this.children = [...children]; },
    addEventListener() {},
    setAttribute(name, value) { this.attrs[name] = String(value); },
    removeAttribute(name) { delete this.attrs[name]; },
  };
}

function response(status, data) {
  return {
    ok: status >= 200 && status < 300,
    status,
    async json() { return data; },
  };
}

const privateSelectors = ['#admin-claims', '#admin-ranking-contacts', '#admin-faults'];
const selectors = [
  '#admin-login', '#admin-app', '#admin-name', '#admin-permissions', '#admin-login-message',
  '#admin-email', '#admin-password', '#btn-admin-login', '#btn-admin-logout', '#analytics-filter',
  '#claim-operations-section', '#ranking-contact-section', '#fault-review-section',
  '#btn-refresh-claims', '#btn-refresh-ranking-contacts', '#btn-refresh-faults',
  '#btn-campaign-update', '#campaign-status', '#campaign-reason',
  '#admin-load-status', '#admin-load-message', '#btn-admin-retry',
  '#metrics-refreshed', '#metrics-window', '#metrics-grid', '#metrics-scope', '#metrics-definitions',
  '#source-funnel', '#loading-summary', '#screen-summary', '#stage-summary', '#game-summary',
  '#score-distribution', '#leaderboard-summary', '#ticket-ledger', '#claim-summary',
  '#result-dwell', '#invitation-summary', '#gemini-summary', ...privateSelectors,
];

function emptyOverview() {
  return {
    generated_at: '2026-09-26T00:00:00Z', metrics: [], source_funnel: [], score_distribution: [],
    leaderboard: [], ticket_ledger: [], claims: [], loading: { buckets: [], milestones: [] },
    screens: [], stages: [], game: {}, game_progress: {}, result_dwell: [], invitation: [],
    sharing: {}, invitation_performance: {}, gemini_conversion: {}, content: [], definitions: {},
    campaign: { version: 3, status: 'ACTIVE', game_version: '2.0.0' }, environment: 'preview',
  };
}

function sessionPayload() {
  return {
    admin: {
      display_name: '테스트 관리자',
      permissions: ['analytics:read', 'claims:read', 'faults:read'],
    },
  };
}

function makeRuntime(fetchImpl) {
  const nodes = new Map(selectors.map((selector) => [selector, node()]));
  nodes.get('#admin-app').hidden = true;
  nodes.get('#admin-load-status').hidden = true;
  const stored = new Map();
  const sessionStorage = {
    getItem: (key) => stored.get(key) || null,
    setItem: (key, value) => stored.set(key, String(value)),
    removeItem: (key) => stored.delete(key),
  };
  const document = {
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, node());
      return nodes.get(selector);
    },
    createElement: (tag) => node(tag),
  };
  class FormDataMock {
    constructor() {}
    *[Symbol.iterator]() {}
  }
  const context = {
    console, document, sessionStorage, fetch: fetchImpl, Headers, URLSearchParams,
    FormData: FormDataMock, Date, setTimeout, clearTimeout,
    window: { location: { reload() {} } },
    api: { createRequestId: () => 'admin-request-id' },
    ui: {
      text(target, value) { target.textContent = String(value); },
      showToast() {},
    },
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/admin.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace(/if \(accessToken\) showAdmin\(\)\.catch\([\s\S]*?\);\s*$/, '')
    .concat(`
      globalThis.__adminTest = {
        showAdmin,
        adminRequest,
        setAccessToken(value) { accessToken = value; sessionSet(value); },
        getAccessToken() { return accessToken; },
      };
    `);
  vm.runInNewContext(source, context, { filename: 'public/js/admin.js' });
  return { api: context.__adminTest, nodes, stored };
}

function pathOf(input) {
  return new URL(String(input), 'https://example.test').pathname;
}

function visibleText(target) {
  return [target.textContent, ...target.children.map(visibleText)].filter(Boolean).join(' ');
}

test('a metrics failure keeps the authenticated operations available and retry clears the notice', async () => {
  let overviewAttempts = 0;
  const calls = [];
  const runtime = makeRuntime(async (input) => {
    const requestPath = pathOf(input); calls.push(requestPath);
    if (requestPath === '/api/admin/session') return response(200, sessionPayload());
    if (requestPath === '/api/admin/overview') {
      overviewAttempts += 1;
      return overviewAttempts === 1
        ? response(503, { message: '통계 서비스를 잠시 사용할 수 없습니다.' })
        : response(200, emptyOverview());
    }
    if (requestPath === '/api/admin/claims') return response(200, { claims: [] });
    if (requestPath === '/api/admin/ranking-contacts') return response(200, { ranking_contacts: [] });
    if (requestPath === '/api/admin/game-faults') return response(200, { faults: [] });
    throw new Error(`unexpected request: ${requestPath}`);
  });
  runtime.api.setAccessToken('kept-token');

  await runtime.api.showAdmin();

  assert.equal(runtime.api.getAccessToken(), 'kept-token');
  assert.equal(runtime.stored.get('dino_admin_access_token'), 'kept-token');
  assert.equal(runtime.nodes.get('#admin-app').hidden, false);
  assert.equal(runtime.nodes.get('#admin-login').hidden, true);
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, false);
  assert.match(runtime.nodes.get('#admin-load-message').textContent, /통계|지표/);
  assert.equal(runtime.nodes.get('#btn-admin-retry').hidden, false);
  assert.match(visibleText(runtime.nodes.get('#admin-claims')), /처리할 수령 건이 없습니다/);
  assert.match(visibleText(runtime.nodes.get('#admin-ranking-contacts')), /TOP3 연락 접수 건이 없습니다/);
  assert.match(visibleText(runtime.nodes.get('#admin-faults')), /장애 신고가 없습니다/);
  assert.ok(calls.includes('/api/admin/overview'));

  await runtime.nodes.get('#btn-admin-retry').onclick();
  assert.equal(overviewAttempts, 2);
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, true);
  assert.equal(runtime.nodes.get('#btn-admin-retry').disabled, false);
});

test('a 401 response expires the admin session, removes private data, and returns to login', async () => {
  const runtime = makeRuntime(async () => response(401, { message: '로그인이 만료되었습니다.' }));
  runtime.api.setAccessToken('expired-token');
  for (const selector of privateSelectors) runtime.nodes.get(selector).appendChild(node('private-row'));
  runtime.nodes.get('#admin-login').hidden = true;
  runtime.nodes.get('#admin-app').hidden = false;

  await assert.rejects(runtime.api.adminRequest('/api/admin/claims'), /로그인|만료/);

  assert.equal(runtime.api.getAccessToken(), '');
  assert.equal(runtime.stored.has('dino_admin_access_token'), false);
  assert.equal(runtime.nodes.get('#admin-app').hidden, true);
  assert.equal(runtime.nodes.get('#admin-login').hidden, false);
  for (const selector of privateSelectors) assert.equal(runtime.nodes.get(selector).children.length, 0);
});

test('a late successful private response cannot repopulate the DOM after expiry', async () => {
  const claims = deferred();
  let overviewRequested = false;
  const runtime = makeRuntime(async (input) => {
    const requestPath = pathOf(input);
    if (requestPath === '/api/admin/session') return response(200, sessionPayload());
    if (requestPath === '/api/admin/overview') {
      overviewRequested = true;
      return response(401, { message: '로그인이 만료되었습니다.' });
    }
    if (requestPath === '/api/admin/claims') return claims.promise;
    if (requestPath === '/api/admin/ranking-contacts') return response(200, { ranking_contacts: [] });
    if (requestPath === '/api/admin/game-faults') return response(200, { faults: [] });
    throw new Error(`unexpected request: ${requestPath}`);
  });
  runtime.api.setAccessToken('soon-expired-token');

  const loading = runtime.api.showAdmin();
  while (!overviewRequested) await Promise.resolve();
  await new Promise((resolve) => setImmediate(resolve));
  assert.equal(runtime.api.getAccessToken(), '');
  claims.resolve(response(200, {
    claims: [{
      id: 'private-claim', claim_type: 'DRAW', prize_name: '비공개 경품', status: 'INFORMATION_RECEIVED',
      recipient_name: '개인정보 이름', contact: '010-0000-0000', school: '비공개 학교',
      contact_submitted_at: '2026-09-26T00:00:00Z', version: 1,
    }],
  }));
  await loading;

  assert.equal(runtime.nodes.get('#admin-login').hidden, false);
  assert.equal(runtime.nodes.get('#admin-app').hidden, true);
  assert.equal(runtime.nodes.get('#admin-claims').children.length, 0);
  assert.doesNotMatch(visibleText(runtime.nodes.get('#admin-claims')), /개인정보 이름|010-0000-0000/);
});

test('a forbidden admin session is recovered as an expired login', async () => {
  const runtime = makeRuntime(async () => response(403, { message: '관리자 권한이 없습니다.' }));
  runtime.api.setAccessToken('forbidden-token');
  runtime.nodes.get('#admin-login').hidden = true;
  runtime.nodes.get('#admin-app').hidden = false;

  await assert.rejects(runtime.api.showAdmin(), /관리자 권한/);

  assert.equal(runtime.api.getAccessToken(), '');
  assert.equal(runtime.stored.has('dino_admin_access_token'), false);
  assert.equal(runtime.nodes.get('#admin-login').hidden, false);
  assert.equal(runtime.nodes.get('#admin-app').hidden, true);
});

test('a temporary session outage keeps the token and offers retry instead of treating it as expiry', async () => {
  const runtime = makeRuntime(async () => response(503, { message: '관리자 서버가 잠시 응답하지 않습니다.' }));
  runtime.api.setAccessToken('recoverable-token');

  await assert.rejects(runtime.api.showAdmin(), /잠시 응답하지 않습니다/);

  assert.equal(runtime.api.getAccessToken(), 'recoverable-token');
  assert.equal(runtime.stored.get('dino_admin_access_token'), 'recoverable-token');
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, false);
  assert.equal(runtime.nodes.get('#btn-admin-retry').hidden, false);
  assert.match(runtime.nodes.get('#admin-load-message').textContent, /잠시|다시|재시도/);
});
