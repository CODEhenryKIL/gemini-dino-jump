const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');
const read = (file) => fs.readFileSync(path.join(root, file), 'utf8');

function loadApi(fetchImpl) {
  const source = read('public/js/api.js')
    .replace('export class ApiError', 'class ApiError')
    .replace('export const api', 'const api');
  class HeadersMock {
    constructor(initial = {}) { this.values = { ...initial }; }
    set(name, value) { this.values[name] = value; }
    get(name) { return this.values[name]; }
  }
  const context = {
    fetch: fetchImpl,
    Headers: HeadersMock,
    FormData: class {},
    crypto: { randomUUID: () => 'uuid' },
    Math,
    Date,
  };
  vm.runInNewContext(`${source}\nglobalThis.loadedApi = api; globalThis.ApiError = ApiError;`, context);
  return context.loadedApi;
}

function loadView(file, exportName, globals = {}) {
  const source = read(file)
    .replace(/^import .*;\n/gm, '')
    .replace(`export const ${exportName}`, `const ${exportName}`);
  const context = { console, ...globals };
  vm.runInNewContext(`${source}\nglobalThis.loadedView = ${exportName};`, context);
  return context.loadedView;
}

test('participant API uses HttpOnly cookie transport and never browser token storage', async () => {
  const calls = [];
  const api = loadApi(async (url, options) => {
    calls.push({ url, options });
    return { ok: true, status: 201, json: async () => ({ participant: { id: 'p1' }, tickets: { initial: 1 } }) };
  });
  await api.initParticipant({ inviteCode: 'public-code', observationId: 'obs-1', bootstrapToken: 'ephemeral-bootstrap' });
  assert.equal(calls[0].url, '/api/participants/anonymous');
  assert.equal(calls[0].options.credentials, 'same-origin');
  assert.equal(calls[0].options.headers.get('Authorization'), undefined);
  assert.match(calls[0].options.headers.get('Idempotency-Key'), /^idem_/);
  assert.doesNotMatch(read('public/js/api.js'), /localStorage|session_token|Bearer.*participant/i);
  assert.match(calls[0].options.body, /ephemeral-bootstrap/);
});

test('analytics batch transport retries a lost request with the exact generated idempotency key', async () => {
  const calls = [];
  let attempt = 0;
  const api = loadApi(async (url, options) => {
    calls.push({ url, options });
    attempt += 1;
    if (attempt === 1) throw new TypeError('network lost');
    return { ok: true, status: 202, json: async () => ({ accepted: 1, duplicates: 0, rejected: 0 }) };
  });
  const event = { event_id: 'evt_stable_12345678', name: 'entry_viewed' };
  await api.postEvents([event]);
  assert.equal(calls[0].url, '/api/events/batch');
  assert.match(calls[0].options.headers.get('Idempotency-Key'), /^batch_/);
  assert.equal(calls[1].options.headers.get('Idempotency-Key'), calls[0].options.headers.get('Idempotency-Key'));
});

test('rebatching the same first event gets a fresh request key and relies on event IDs for deduplication', async () => {
  const calls = [];
  let uuid = 0;
  const source = read('public/js/api.js')
    .replace('export class ApiError', 'class ApiError')
    .replace('export const api', 'const api');
  class HeadersMock {
    constructor(initial = {}) { this.values = { ...initial }; }
    set(name, value) { this.values[name] = value; }
    get(name) { return this.values[name]; }
  }
  const context = {
    fetch: async (url, options) => { calls.push({ url, options }); return { ok: true, status: 202, json: async () => ({ accepted: 1, duplicates: 0, rejected: 0 }) }; },
    Headers: HeadersMock, FormData: class {}, crypto: { randomUUID: () => `uuid-${++uuid}` }, Math, Date,
  };
  vm.runInNewContext(`${source}\nglobalThis.loadedApi = api;`, context);
  const event = { event_id: 'evt_same_first_12345678', name: 'entry_viewed' };
  await context.loadedApi.postEvents([event]);
  await context.loadedApi.postEvents([event, { ...event, event_id: 'evt_new_second_12345678' }]);
  assert.notEqual(calls[0].options.headers.get('Idempotency-Key'), calls[1].options.headers.get('Idempotency-Key'));
});

test('lost finish retries retain an exact key and a PII-free payload', () => {
  const game = read('public/js/views/game_view.js');
  assert.match(game, /storageSet\(PENDING_RESULT_KEY/);
  assert.match(game, /const sessionId = this\.sessionId;[\s\S]*const key = `finish_\$\{sessionId\}`/);
  assert.match(game, /api\.getSession\(pending\.sessionId\)/);
  assert.doesNotMatch(game, /session_token|contact|recipient|participant_id/i);
  assert.match(game, /checkpointSession/);
  assert.doesNotMatch(game, /checkpointSession\(this\.sessionId, 0\)/);
  assert.match(game, /정상 종료나 자발적 이탈은 환급 대상이 아닙니다/);
  assert.match(game, /같은 게임 이어하기/);
  assert.doesNotMatch(game, /pending\.status !== 'FAULT_REPORTED'\) await api\.reportSessionFault/);
});

test('verified finish clears only its pending reservation and accepts authoritative ticket state', () => {
  const view = loadView('public/js/views/game_view.js', 'GameView');
  const makeRouter = (ticketKind, invitationReserved = 1) => ({
    state: {
      pendingGameSession: { id: 'gs-1', ticket_kind: ticketKind },
      tickets: { initial: 0, invitation: 2, invitation_reserved: invitationReserved, available_total: 2 },
      bestScore: 0, rank: null, draw: { status: 'AVAILABLE' }, top3Profile: { status: 'NOT_REQUIRED' },
    },
    updateCount: 0,
    updateNav() { this.updateCount += 1; },
  });
  const result = { session_id: 'gs-1', score: 32, best_score: 32, rank: 1, verification: 'VERIFIED' };

  const invitation = makeRouter('INVITATION');
  view.ticketKind = 'INITIAL'; // stale view state must not override the matching recovered pending session.
  view.acceptResult(result, invitation);
  assert.equal(invitation.state.pendingGameSession, null);
  assert.equal(invitation.state.tickets.invitation_reserved, 0);
  assert.equal(invitation.updateCount, 1);

  const initial = makeRouter('INITIAL', 2);
  view.ticketKind = 'INVITATION';
  view.acceptResult(result, initial);
  assert.equal(initial.state.pendingGameSession, null);
  assert.equal(initial.state.tickets.invitation_reserved, 2);

  const authoritative = makeRouter('INVITATION');
  const serverTickets = { initial: 0, invitation: 1, invitation_reserved: 7, available_total: 1 };
  view.acceptResult({ ...result, tickets: serverTickets }, authoritative);
  assert.equal(authoritative.state.tickets, serverTickets);
  assert.equal(authoritative.state.tickets.invitation_reserved, 7);
});

test('invite qualification requires both active time and interaction and GET cannot reward', () => {
  const app = read('public/js/app.js');
  assert.match(app, /url\.pathname\.match\(\/\^\\\/invite/);
  assert.match(app, /history\.replaceState\(\{\}, '', '\/'\)/);
  assert.match(app, /!interacted \|\| currentVisible\(\) < requiredMs \|\| document\.hidden/);
  assert.match(app, /api\.qualifyReferral/);
  assert.doesNotMatch(app, /fetch\([^)]*invite[^)]*method:\s*['"]GET/i);
  assert.match(read('public/js/api.js'), /method: 'POST'.*\/api\/referrals\/qualify/s);
  assert.match(app, /requestedLinkKind === 'prize_share' \? 'prize_share' : 'retry_invite'/);
  assert.match(app, /requestedLinkKind === 'initial' \? 'initial' : 'direct'/);
  assert.match(app, /this\.inviteVisit\?\.status === 'PENDING' && this\.inviteVisit\.visit_nonce/);
  assert.match(app, /SELF_INVITE/);
  assert.match(app, /error\.status === 408 \|\| error\.status === 429 \|\| error\.status >= 500/);
  assert.doesNotMatch(app, /link_kind: inviteCode \? 'INVITATION' : 'DIRECT'/);
});

test('draw is participant-scoped, resumes from server, and scratch listeners are cleaned up', () => {
  const draw = read('public/js/views/draw_view.js');
  assert.match(draw, /api\.getDraw\(\)/);
  assert.match(draw, /state\.status === 'DRAWN'/);
  assert.doesNotMatch(draw, /session_id|sessionId/);
  assert.match(draw, /draw\.is_won \? 'won' : 'no_prize'/);
  const scratch = read('public/js/components/scratch_card.js');
  assert.match(scratch, /destroy\(\)/);
  assert.match(scratch, /removeEventListener\('touchmove'/);
});

test('claim UI uses the server claim_type field for DRAW and RANKING records', () => {
  const claims = read('public/js/views/prize_view.js');
  assert.match(claims, /claim\.claim_type \|\| claim\.type \|\| 'DRAW'/);
  assert.match(claims, /claim_type: claimType/);
});

test('admin uses real Supabase Auth and optimistic manual claim transitions', () => {
  const admin = read('public/js/admin.js');
  assert.match(admin, /\/auth\/v1\/token\?grant_type=password/);
  assert.match(admin, /sessionSet\(accessToken\)/);
  assert.match(admin, /expected_version: claim\.version/);
  assert.match(admin, /external_delivery: externalBox\.checked/);
  assert.match(admin, /Array\.isArray\(data\.metrics\)/);
  assert.match(admin, /data\.period\?\.from/);
  assert.match(admin, /T00:00:00\+09:00/);
  assert.match(admin, /nextCalendarDate\(params\.get\('to'\)\)/);
  assert.match(admin, /renderSourceFunnel\(data\.source_funnel/);
  assert.match(admin, /row\.attribution === 'first' \? '첫 유입'/);
  assert.match(admin, /row\.score_from.*row\.score_to/);
  assert.match(admin, /renderTicketLedger\(data\.ticket_ledger/);
  assert.match(admin, /renderClaimSummary\(data\.claims/);
  assert.match(admin, /\/api\/admin\/game-faults\?status=PENDING/);
  assert.match(admin, /expected_version: fault\.fault_review_version/);
  assert.match(admin, /adminPermissions\.has\('faults:write'\)/);
  assert.doesNotMatch(admin, /hardcoded|fake.?otp|service_role/i);
});

test('client event envelope is allowlisted and excludes private arbitrary payloads', () => {
  const analytics = read('public/js/analytics.js');
  assert.match(analytics, /EVENT_ALLOWLIST/);
  assert.match(analytics, /SAFE_DIMENSIONS/);
  assert.match(analytics, /typeof value === 'string' && value\.length/);
  assert.match(analytics, /screen_view_id: this\.screenViewId/);
  assert.match(analytics, /this\.screenViewId = api\.createRequestId\('screen'\)/);
  assert.match(analytics, /: this\.currentActiveMs\(\)/);
  assert.match(read('public/js/api.js'), /\/api\/events\/batch/);
  assert.doesNotMatch(analytics, /contact|phone|address|token|invite_code|full_url/i);
  assert.match(analytics, /this\.queue\.unshift\(\.\.\.events/);
  assert.match(analytics, /error\.status === 408 \|\| error\.status === 429 \|\| error\.status >= 500/);
  assert.match(analytics, /analytics_batch_failed/);
  assert.match(analytics, /setInterval\(\(\) => \{ this\.checkpoint\(\); this\.flush\(\); \}, 2000\)/);
  assert.match(analytics, /event\.persisted/);
  assert.match(analytics, /if \(!this\.observationReady \|\| !this\.queue\.length/);
  assert.match(read('public/js/app.js'), /api\.startObservation\(observation\)\.then[\s\S]*analytics\.setObservationReady\(\)/);
});

test('blocked web storage cannot crash participant or game bootstrap', () => {
  const game = read('public/js/views/game_view.js');
  const analytics = read('public/js/analytics.js');
  assert.match(game, /function storageGet\(key\) \{ try/);
  assert.match(game, /function storageSet\(key, value\) \{ try/);
  assert.match(analytics, /sessionGet\(key\) \{ try/);
  assert.match(read('public/js/app.js'), /navigator\.locks\?\.request/);
});

test('a consumed ticket does not block access to an existing game or fault recovery', () => {
  const home = read('public/js/views/home.js');
  assert.match(home, /start\.disabled = !pendingSession && \(campaignStatus !== 'ACTIVE' \|\| \(!unlimited && available < 1\)\)/);
  assert.match(home, /진행 중 게임 복원/);
  assert.match(home, /장애 복구 상태 확인/);
  assert.match(home, /if \(router\.state\.pendingGameSession\) \{ router\.navigate\('game'\); return; \}/);
});

test('fault recovery persists only non-PII evidence and reconciles rejected checkpoints', () => {
  const game = read('public/js/views/game_view.js');
  assert.match(game, /FAULT_PREFIX = 'dino_fault_'/);
  assert.match(game, /persistFaultMarker\('NETWORK_ERROR', tick\)/);
  assert.match(game, /정상 종료나 자발적 이탈은 환급 대상이 아닙니다/);
  assert.doesNotMatch(game, /recipient_name|contact|address|participant_token/i);
});

test('scratch completion keeps a stable retry key and does not claim completion after failure', () => {
  const draw = read('public/js/views/draw_view.js');
  const client = read('public/js/api.js');
  assert.match(draw, /SCRATCH_KEY_PREFIX/);
  assert.match(draw, /storageGet\(storageKey\) \|\| api\.createRequestId\('scratch'\)/);
  assert.match(draw, /await api\.completeScratch\(draw\.draw_id, eventId\)/);
  assert.match(draw, /analytics\.track\('scratch_completed'/);
  assert.match(draw, /저장 다시 시도/);
  assert.match(client, /completeScratch\(drawId, idempotencyKey = null\)/);
});

test('share attribution uses an opaque approved parameter and records outcomes separately', () => {
  const app = read('public/js/app.js');
  const invite = read('public/js/views/invite_view.js');
  assert.match(app, /url\.searchParams\.get\('share'\)/);
  assert.match(app, /share_id: shareId/);
  assert.match(invite, /url\.searchParams\.set\('share', shareId\)/);
  assert.match(invite, /status: 'copied'/);
  assert.match(invite, /status: 'failed'/);
  assert.match(read('public/js/analytics.js'), /'share_id'/);
});

test('admin isolates contact operations and renders metric definitions and full breakdowns', () => {
  const html = read('public/admin.html');
  const admin = read('public/js/admin.js');
  assert.match(html, /id="claim-operations-section"[^>]*hidden/);
  assert.match(html, /id="ranking-contact-section"[^>]*hidden/);
  assert.match(admin, /adminPermissions\.has\('claims:read'\)/);
  assert.match(admin, /\/api\/admin\/ranking-contacts/);
  assert.match(admin, /claim\.recipient_name/);
  assert.match(admin, /renderOperationalBreakdowns\(data\)/);
  assert.match(admin, /renderDefinitions\(data\.definitions/);
  assert.match(admin, /data\.synthetic_only/);
  assert.match(admin, /data\.filter_attribution/);
  assert.match(admin, /new_participants/);
  assert.match(admin, /returning_participants/);
  assert.match(admin, /claim\.claim_type === 'RANKING' \? '잠정 TOP3 연락 접수'/);
  assert.match(admin, /claim\.assignee_display_name \|\| claim\.assignee_user_id \|\| '미지정'/);
  assert.match(admin, /externalBox\.checked = Boolean\(claim\.external_delivery\)/);
  assert.match(admin, /최종 수상 확정 전이므로 지급 완료로 변경할 수 없습니다/);
  assert.match(admin, /row\.ready/);
  assert.match(admin, /row\.pending/);
  assert.match(admin, /row\.estimated_exits/);
  assert.match(admin, /data\.invitation_performance\?\.period_use_to_grant_ratio/);
  assert.match(admin, /data\.invitation_performance\?\.ratio_definition \|\| 'unknown'/);
  assert.match(admin, /data\.game_progress\?\.by_last_stage/);
  assert.match(admin, /row\.mean_last_observed_active_ms/);
  assert.match(admin, /row\.active_time_unknown/);
  assert.match(admin, /row\.mean_observed_active_ms/);
  assert.match(admin, /row\.active_dwell_unknown/);
  assert.match(admin, /data\.content \|\| \[\]/);
  assert.match(admin, /row\.unlinked_events/);
});

test('hidden views leave the accessibility tree and Gemini exposure requires visibility', () => {
  assert.match(read('public/css/style.css'), /\[hidden\] \{ display: none !important; \}/);
  assert.match(read('public/js/app.js'), /splash\.setAttribute\('aria-hidden', 'true'\); splash\.inert = true/);
  const benefit = read('public/js/views/benefit_view.js');
  assert.match(benefit, /IntersectionObserver/);
  assert.match(benefit, /intersectionRatio >= 0\.5/);
  assert.match(benefit, /cleanup\(\) \{ this\.observer\?\.disconnect/);
});

test('submitted TOP3 state wins over a stale requested result when result screen rerenders', () => {
  const created = [];
  const makeNode = (tag = 'div') => ({
    tag, children: [], disabled: false, textContent: '',
    append(...nodes) { this.children.push(...nodes); },
    appendChild(node) { this.children.push(node); },
    replaceChildren(...nodes) { this.children = nodes; },
  });
  const nodes = new Map([
    ['#result-score', makeNode()], ['#result-best', makeNode()], ['#result-rank', makeNode()],
    ['#result-nickname', makeNode()], ['#btn-go-pouch', makeNode('button')],
    ['#btn-share-record', makeNode('button')], ['#btn-edit-nick', makeNode('button')],
    ['#top3-request', makeNode()],
  ]);
  const documentMock = {
    createElement(tag) { const node = makeNode(tag); created.push(node); return node; },
  };
  const container = { innerHTML: '', querySelector(selector) { return nodes.get(selector); } };
  const router = {
    state: {
      lastResult: { score: 32, bestScore: 32, rank: 1, top3Profile: { required: true, status: 'REQUESTED' } },
      top3Profile: { required: true, status: 'SUBMITTED' }, participant: { nickname: '공룡1234' },
    },
    navigate() {},
  };
  const view = loadView('public/js/views/result_view.js', 'ResultView', {
    document: documentMock,
    ui: { text(node, value) { node.textContent = String(value); } },
  });
  view.render(container, router);
  const button = created.find((node) => node.tag === 'button' && node.textContent === '정보 접수 완료');
  assert.ok(button);
  assert.equal(button.disabled, true);
  assert.equal(created.some((node) => node.textContent === '합성 테스트 정보 입력'), false);
});

test('public metadata uses the deployment site name while retaining Dino Jump', () => {
  const index = read('public/index.html');
  assert.match(index, /<title>구글 코리아 팀 제미나이 \| 공룡 점프<\/title>/);
  assert.match(index, /property="og:site_name" content="구글 코리아 팀 제미나이"/);
});
