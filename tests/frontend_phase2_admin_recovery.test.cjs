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

const privateSelectors = ['#admin-claims', '#admin-ranking-contacts', '#admin-ranking-snapshots', '#admin-faults'];
const selectors = [
  '#admin-login', '#admin-app', '#admin-name', '#admin-permissions', '#admin-login-message',
  '#admin-email', '#admin-password', '#btn-admin-login', '#btn-admin-logout', '#analytics-filter',
  '#btn-admin-password-reset', '#admin-password-reset-message', '#admin-password-recovery',
  '#admin-new-password', '#admin-new-password-confirm', '#btn-admin-password-update', '#btn-admin-password-recovery-cancel', '#admin-password-recovery-message',
  '#claim-operations-section', '#ranking-contact-section', '#ranking-finalization-section', '#fault-review-section',
  '#btn-refresh-claims', '#btn-refresh-ranking-contacts', '#btn-refresh-ranking-snapshots', '#btn-create-ranking-snapshot', '#btn-refresh-faults',
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
  const historyCalls = [];
  const location = {
    href: 'https://candidate.example/admin.html', origin: 'https://candidate.example',
    pathname: '/admin.html', search: '', hash: '', reload() {},
  };
  const context = {
    console, document, sessionStorage, fetch: fetchImpl, Headers, URL, URLSearchParams,
    FormData: FormDataMock, Date, setTimeout, clearTimeout,
    window: { location, history: { replaceState(...args) { historyCalls.push(args); } } },
    api: {
      createRequestId: () => 'admin-request-id',
      getConfig: async () => ({
        environment: 'production',
        auth: { supabase_url: 'https://project.supabase.co', publishable_key: 'public-key' },
      }),
    },
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
        loadMetrics,
        loadRankingSnapshots,
        requestPasswordRecovery,
        initializePasswordRecovery,
        updateRecoveredPassword,
        setAccessToken(value) { accessToken = value; sessionSet(value); },
        getAccessToken() { return accessToken; },
        getRecoveryAccessToken() { return recoveryAccessToken; },
      };
    `);
  vm.runInNewContext(source, context, { filename: 'public/js/admin.js' });
  return { api: context.__adminTest, nodes, stored, location, historyCalls };
}

function pathOf(input) {
  return new URL(String(input), 'https://example.test').pathname;
}

function visibleText(target) {
  return [target.textContent, ...target.children.map(visibleText)].filter(Boolean).join(' ');
}

test('password reset request uses the current admin URL and keeps account existence private', async () => {
  const requests = [];
  const runtime = makeRuntime(async (input, options = {}) => {
    requests.push({ url: String(input), options });
    return response(400, { message: 'User not found' });
  });
  runtime.nodes.get('#admin-email').value = 'operator@example.com';

  await runtime.api.requestPasswordRecovery();

  assert.equal(requests.length, 1);
  const requestUrl = new URL(requests[0].url);
  assert.equal(requestUrl.pathname, '/auth/v1/recover');
  assert.equal(requestUrl.searchParams.get('redirect_to'), 'https://candidate.example/admin.html');
  assert.deepEqual(JSON.parse(requests[0].options.body), { email: 'operator@example.com' });
  assert.match(runtime.nodes.get('#admin-password-reset-message').textContent, /등록된 관리자 이메일이라면/);
  assert.doesNotMatch(runtime.nodes.get('#admin-password-reset-message').textContent, /User not found/);
});

test('recovery callback clears the URL token and requires a server-confirmed administrator', async () => {
  const runtime = makeRuntime(async (input, options = {}) => {
    assert.equal(pathOf(input), '/api/admin/session');
    assert.equal(new Headers(options.headers).get('Authorization'), 'Bearer recovery-secret');
    return response(200, sessionPayload());
  });
  runtime.location.hash = '#access_token=recovery-secret&refresh_token=other-secret&type=recovery';
  runtime.location.href += runtime.location.hash;

  const recoveryMode = await runtime.api.initializePasswordRecovery();

  assert.equal(recoveryMode, true);
  assert.equal(runtime.historyCalls[0][2], '/admin.html');
  assert.equal(runtime.api.getRecoveryAccessToken(), 'recovery-secret');
  assert.equal(runtime.stored.has('dino_admin_access_token'), false);
  assert.equal(runtime.nodes.get('#admin-password-recovery').hidden, false);
  assert.equal(runtime.nodes.get('#admin-login').hidden, true);
  assert.equal(runtime.nodes.get('#admin-password-recovery-message').textContent, '');
});

test('recovery callback rejects a valid auth user who is not an authorized administrator', async () => {
  const runtime = makeRuntime(async () => response(403, { message: '관리자 권한이 없습니다.' }));
  runtime.location.hash = '#access_token=ordinary-user-token&type=recovery';

  await runtime.api.initializePasswordRecovery();

  assert.equal(runtime.api.getRecoveryAccessToken(), '');
  assert.equal(runtime.stored.has('dino_admin_access_token'), false);
  assert.match(runtime.nodes.get('#admin-password-recovery-message').textContent, /관리자 권한/);
});

test('verified recovery updates the password then opens the existing admin session', async () => {
  const calls = [];
  const runtime = makeRuntime(async (input, options = {}) => {
    const requestPath = pathOf(input);
    calls.push({ requestPath, options });
    if (requestPath === '/api/admin/session') return response(200, sessionPayload());
    if (requestPath === '/auth/v1/user') return response(200, { id: 'admin-user' });
    throw new Error(`unexpected request: ${requestPath}`);
  });
  runtime.location.hash = '#access_token=recovery-secret&type=recovery';
  await runtime.api.initializePasswordRecovery();
  runtime.nodes.get('#admin-new-password').value = 'A-strong-admin-password-2026';
  runtime.nodes.get('#admin-new-password-confirm').value = 'A-strong-admin-password-2026';

  await runtime.api.updateRecoveredPassword();

  const update = calls.find((call) => call.requestPath === '/auth/v1/user');
  assert.ok(update);
  assert.equal(new Headers(update.options.headers).get('Authorization'), 'Bearer recovery-secret');
  assert.deepEqual(JSON.parse(update.options.body), { password: 'A-strong-admin-password-2026' });
  assert.equal(runtime.stored.get('dino_admin_access_token'), 'recovery-secret');
  assert.equal(runtime.api.getRecoveryAccessToken(), '');
  assert.equal(runtime.nodes.get('#admin-password-recovery').hidden, true);
  assert.equal(runtime.nodes.get('#admin-app').hidden, false);
  assert.equal(runtime.historyCalls.at(-1)[2], '/admin.html');
});

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

test('a successful filtered metrics query clears only the recovered section failure', async () => {
  let failMetrics = true;
  const runtime = makeRuntime(async (input) => {
    const requestPath = pathOf(input);
    if (requestPath === '/api/admin/session') return response(200, sessionPayload());
    if (requestPath === '/api/admin/overview') return failMetrics ? response(503, {}) : response(200, emptyOverview());
    if (requestPath === '/api/admin/claims') return response(503, {});
    if (requestPath === '/api/admin/ranking-contacts') return response(200, { ranking_contacts: [] });
    if (requestPath === '/api/admin/game-faults') return response(200, { faults: [] });
    throw new Error(`unexpected request: ${requestPath}`);
  });
  runtime.api.setAccessToken('valid-token');
  await runtime.api.showAdmin();
  assert.match(runtime.nodes.get('#admin-load-message').textContent, /통계/);
  assert.match(runtime.nodes.get('#admin-load-message').textContent, /수령 원장/);
  failMetrics = false;
  await runtime.api.loadMetrics();
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, false);
  assert.doesNotMatch(runtime.nodes.get('#admin-load-message').textContent, /통계/);
  assert.match(runtime.nodes.get('#admin-load-message').textContent, /수령 원장/);
});

test('filter retry hides the notice when metrics was the only failed section', async () => {
  let fail = true;
  const runtime = makeRuntime(async (input) => {
    const path = pathOf(input);
    if (path === '/api/admin/session') return response(200, { admin: { permissions: ['analytics:read'] } });
    if (path === '/api/admin/overview') return fail ? response(503, {}) : response(200, emptyOverview());
    throw new Error(`unexpected request: ${path}`);
  });
  runtime.api.setAccessToken('valid-token');
  await runtime.api.showAdmin();
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, false);
  fail = false;
  await runtime.api.loadMetrics();
  assert.equal(runtime.nodes.get('#admin-load-status').hidden, true);
});

test('an older metrics response cannot overwrite the latest filter result or restore its old error', async () => {
  for (const oldStatus of [200, 503]) {
    const old = deferred();
    let attempts = 0;
    const runtime = makeRuntime(async () => ++attempts === 1 ? old.promise : response(200, { ...emptyOverview(), campaign: { version: 9, status: 'PAUSED' } }));
    runtime.api.setAccessToken('valid-token');
    const pending = runtime.api.loadMetrics();
    await runtime.api.loadMetrics();
    assert.equal(runtime.nodes.get('#campaign-status').value, 'PAUSED');
    old.resolve(response(oldStatus, emptyOverview()));
    await pending;
    assert.equal(runtime.nodes.get('#campaign-status').value, 'PAUSED');
    assert.equal(runtime.nodes.get('#admin-load-status').hidden, true);
  }
});

test('ranking writers can finalize a settled snapshot and then process its claims manually', async () => {
  const requests = [];
  let finalized = false;
  const reviews = new Map([
    ['rank-a', null],
    ['rank-b', { outcome: 'APPROVED', evidence_reference: 'TEST_REF_existing_2', binding_current: true }],
    ['rank-c', { outcome: 'APPROVED', evidence_reference: 'TEST_REF_existing_3', binding_current: true }],
  ]);
  const candidates = () => [...reviews.entries()].map(([participant_id, review], index) => ({
    participant_id, rank: index + 1, score: 500 - index * 10, elapsed_seconds: 75.8,
    session_id: `session-${index + 1}`, achieved_at: '2026-10-02T14:50:00Z', end_reason: 'COLLISION',
    verification: 'VERIFIED', summary: { coins: 2, hearts: 1 }, participant_status: 'ACTIVE', binding_current: true, review,
  }));
  const runtime = makeRuntime(async (input, options = {}) => {
    const requestPath = pathOf(input); requests.push({ path: requestPath, options });
    if (requestPath === '/api/admin/session') return response(200, { admin: { display_name: '랭킹 운영자', permissions: ['ranking:read', 'ranking:write', 'claims:read'] } });
    if (requestPath === '/api/admin/claims') return response(200, { claims: [] });
    if (requestPath === '/api/admin/ranking-contacts') return response(200, { ranking_contacts: [] });
    if (requestPath === '/api/admin/ranking-snapshots' && (!options.method || options.method === 'GET')) return response(200, { snapshots: [{
      id: 'snapshot-1', status: finalized ? 'FINAL' : 'DRAFT', tie_policy: 'EARLIEST_ACHIEVED_AT', entry_count: 12,
      captured_at: '2026-10-02T15:00:31Z', finalized_at: finalized ? '2026-10-02T15:01:00Z' : null,
      candidates: candidates(),
    }] });
    if (requestPath === '/api/admin/ranking-snapshots' && options.method === 'POST') return response(201, { id: 'snapshot-1', status: 'DRAFT' });
    if (requestPath === '/api/admin/ranking-snapshots/snapshot-1/reviews') {
      const body = JSON.parse(options.body); reviews.set(body.participant_id, {
        outcome: body.outcome, evidence_reference: body.evidence_reference, binding_current: true,
      });
      return response(200, body);
    }
    if (requestPath === '/api/admin/ranking-snapshots/snapshot-1/finalize') { finalized = true; return response(200, { id: 'snapshot-1', status: 'FINAL', final_awards_created: true }); }
    throw new Error(`unexpected request: ${requestPath}`);
  });
  runtime.api.setAccessToken('ranking-token');
  await runtime.api.showAdmin();
  assert.equal(runtime.nodes.get('#ranking-finalization-section').hidden, false);
  assert.equal(runtime.nodes.get('#btn-create-ranking-snapshot').disabled, false);
  await runtime.nodes.get('#btn-create-ranking-snapshot').onclick();
  const creation = requests.find(({ path, options }) => path === '/api/admin/ranking-snapshots' && options.method === 'POST');
  assert.deepEqual(JSON.parse(creation.options.body), { event_id: 'admin-request-id' });
  let editor = runtime.nodes.get('#admin-ranking-snapshots').children[0];
  assert.match(visibleText(editor), /확정 전 스냅샷/);
  assert.match(visibleText(editor), /먼저 달성 우선/);
  assert.match(visibleText(editor), /플레이 기록 미검토/);
  assert.match(visibleText(editor), /게임 요약: coins 2 · hearts 1/);
  const reviewControls = editor.children[3].children.at(-1);
  const [evidence, reviewReason, approve] = reviewControls.children;
  evidence.value = 'TEST_REF_manual_1'; reviewReason.value = '입력 패턴과 세션 기록 수동 확인';
  await approve.onclick();
  const reviewMutation = requests.find(({ path, options }) => path.endsWith('/reviews') && options.method === 'POST');
  assert.deepEqual(JSON.parse(reviewMutation.options.body), {
    participant_id: 'rank-a', outcome: 'APPROVED', evidence_reference: 'TEST_REF_manual_1',
    reason: '입력 패턴과 세션 기록 수동 확인', event_id: 'admin-request-id',
  });
  editor = runtime.nodes.get('#admin-ranking-snapshots').children[0];
  assert.match(visibleText(editor), /플레이 검토 승인/);
  const controls = editor.children.at(-1);
  const [reason, finalize] = controls.children;
  assert.equal(finalize.disabled, false);
  reason.value = '행사 종료 후 최종 순위 확정';
  await finalize.onclick();
  const mutation = requests.find(({ path, options }) => path.endsWith('/finalize') && options.method === 'POST');
  assert.deepEqual(JSON.parse(mutation.options.body), { reason: '행사 종료 후 최종 순위 확정', event_id: 'admin-request-id' });
  assert.match(visibleText(runtime.nodes.get('#admin-ranking-snapshots')), /최종 확정 완료/);
  assert.match(visibleText(runtime.nodes.get('#admin-ranking-snapshots')), /수령 요청과 경품 예약 생성 완료/);
});
