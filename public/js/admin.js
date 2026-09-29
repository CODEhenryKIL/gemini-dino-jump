import { api } from './api.js';
import { ui } from './ui.js';

const TOKEN_KEY = 'dino_admin_access_token';
function sessionGet() { try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch (_) { return ''; } }
function sessionSet(value) { try { sessionStorage.setItem(TOKEN_KEY, value); } catch (_) {} }
function sessionClear() { try { sessionStorage.removeItem(TOKEN_KEY); } catch (_) {} }
let accessToken = sessionGet();
let sessionRevision = 0;
let loginInFlight = false;
let campaignVersion = 0;
let adminPermissions = new Set();
let adminEnvironment = 'preview';
let recoveryAccessToken = '';
let recoveryInFlight = false;
const loadFailures = new Set();
const sectionRevisions = new Map();
let sessionLoadMessage = '';

function resetAdminSession(message) {
  sessionRevision += 1;
  accessToken = ''; sessionClear(); adminPermissions = new Set(); campaignVersion = 0;
  loadFailures.clear(); sectionRevisions.clear(); sessionLoadMessage = '';
  document.querySelector('#admin-app').hidden = true;
  document.querySelector('#admin-login').hidden = false;
  document.querySelector('#admin-load-status').hidden = true;
  for (const id of ['admin-claims', 'admin-ranking-contacts', 'admin-ranking-snapshots', 'admin-faults', 'admin-name', 'admin-permissions']) {
    document.querySelector(`#${id}`).replaceChildren();
  }
  ui.text(document.querySelector('#admin-login-message'), message);
}

function showLoadError(message) {
  ui.text(document.querySelector('#admin-load-message'), message);
  document.querySelector('#admin-load-status').hidden = false;
}

function updateLoadStatus() {
  if (sessionLoadMessage) showLoadError(sessionLoadMessage);
  else if (loadFailures.size) showLoadError(`불러오지 못한 항목: ${[...loadFailures].join(', ')}. 다시 불러오기를 눌러 주세요.`);
  else document.querySelector('#admin-load-status').hidden = true;
}

async function loadSection(name, path, render) {
  const session = sessionRevision;
  const revision = (sectionRevisions.get(name) || 0) + 1;
  sectionRevisions.set(name, revision);
  const isCurrent = () => session === sessionRevision && sectionRevisions.get(name) === revision;
  try {
    const data = await adminRequest(path);
    if (!isCurrent()) return;
    render(data);
    loadFailures.delete(name);
    updateLoadStatus();
  } catch (error) {
    if (!isCurrent()) return;
    loadFailures.add(name);
    updateLoadStatus();
    throw error;
  }
}

async function adminRequest(path, options = {}) {
  const revision = sessionRevision;
  if (!accessToken) throw new Error('관리자 로그인이 필요합니다.');
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${accessToken}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  const mutation = options.method && options.method !== 'GET';
  if (mutation) headers.set('Idempotency-Key', options.idempotencyKey || api.createRequestId('admin'));
  const fetchOptions = { ...options, headers, credentials: 'same-origin' };
  let response;
  try { response = await fetch(path, fetchOptions); }
  catch (error) { if (!mutation || revision !== sessionRevision) throw error; response = await fetch(path, fetchOptions); }
  const data = await response.json().catch(() => ({}));
  if (revision !== sessionRevision) throw new Error('로그인 상태가 변경되었습니다.');
  if (!response.ok) {
    const error = new Error(data.message || data.error || '관리자 요청에 실패했습니다.');
    error.status = response.status;
    if (response.status === 401) resetAdminSession('로그인이 만료되었거나 유효하지 않습니다. 다시 로그인해 주세요.');
    throw error;
  }
  return data;
}

async function login() {
  if (loginInFlight) return;
  loginInFlight = true;
  document.querySelector('#btn-admin-login').disabled = true;
  const message = document.querySelector('#admin-login-message');
  message.textContent = '';
  try {
    const config = await api.getConfig();
    adminEnvironment = config.environment || 'preview';
    const email = document.querySelector('#admin-email').value.trim();
    const password = document.querySelector('#admin-password').value;
    const response = await fetch(`${config.auth.supabase_url}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: config.auth.publishable_key },
      body: JSON.stringify({ email, password }),
    });
    const auth = await response.json().catch(() => ({}));
    if (!response.ok || !auth.access_token) throw new Error(auth.msg || auth.error_description || '로그인에 실패했습니다.');
    sessionRevision += 1;
    accessToken = auth.access_token;
    sessionSet(accessToken);
    document.querySelector('#admin-password').value = '';
    await showAdmin();
  } catch (error) { message.textContent = error.message; }
  finally { loginInFlight = false; document.querySelector('#btn-admin-login').disabled = false; }
}

function recoveryRedirectUrl() {
  const url = new URL(window.location.href);
  url.hash = '';
  url.search = '';
  return url.toString();
}

function clearRecoveryUrl() {
  window.history?.replaceState?.(null, '', window.location.pathname || '/admin.html');
}

function leaveRecoveryMode() {
  recoveryAccessToken = '';
  clearRecoveryUrl();
  document.querySelector('#admin-password-recovery').hidden = true;
  document.querySelector('#admin-login').hidden = false;
}

async function requestPasswordRecovery() {
  if (recoveryInFlight) return;
  const emailInput = document.querySelector('#admin-email');
  const email = emailInput.value.trim();
  const message = document.querySelector('#admin-password-reset-message');
  if (!email || (emailInput.validity && !emailInput.validity.valid)) {
    message.textContent = '관리자 이메일을 입력해 주세요.';
    emailInput.focus?.();
    return;
  }
  recoveryInFlight = true;
  document.querySelector('#btn-admin-password-reset').disabled = true;
  const genericMessage = '등록된 관리자 이메일이라면 비밀번호 설정 링크를 보냈습니다. 받은편지함과 스팸함을 확인해 주세요.';
  try {
    const config = await api.getConfig();
    await fetch(`${config.auth.supabase_url}/auth/v1/recover?redirect_to=${encodeURIComponent(recoveryRedirectUrl())}`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: config.auth.publishable_key },
      body: JSON.stringify({ email }),
    });
    message.textContent = genericMessage;
  } catch (_) {
    message.textContent = '비밀번호 설정 요청을 보내지 못했습니다. 연결을 확인한 뒤 다시 시도해 주세요.';
  } finally {
    recoveryInFlight = false;
    document.querySelector('#btn-admin-password-reset').disabled = false;
  }
}

async function verifyRecoveryAdministrator(token) {
  const response = await fetch('/api/admin/session', {
    headers: { Authorization: `Bearer ${token}` },
    credentials: 'same-origin',
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok || !data.admin) {
    const error = new Error('이 링크로는 관리자 권한을 확인할 수 없습니다. 새 링크를 요청해 주세요.');
    error.status = response.status;
    throw error;
  }
  return data;
}

async function initializePasswordRecovery() {
  const params = new URLSearchParams((window.location.hash || '').replace(/^#/, ''));
  const recoveryRequested = params.get('type') === 'recovery' || params.has('error_code') || params.has('error_description');
  const token = params.get('access_token') || '';
  if (!recoveryRequested) return false;

  clearRecoveryUrl();
  sessionClear();
  accessToken = '';
  recoveryAccessToken = '';
  document.querySelector('#admin-login').hidden = true;
  document.querySelector('#admin-app').hidden = true;
  document.querySelector('#admin-password-recovery').hidden = false;
  const message = document.querySelector('#admin-password-recovery-message');
  if (!token) {
    message.textContent = '비밀번호 설정 링크가 만료되었거나 올바르지 않습니다. 로그인 화면에서 새 링크를 요청해 주세요.';
    return true;
  }
  message.textContent = '관리자 권한을 확인하고 있습니다.';
  try {
    await verifyRecoveryAdministrator(token);
    recoveryAccessToken = token;
    message.textContent = '';
  } catch (error) {
    recoveryAccessToken = '';
    message.textContent = error.message;
  }
  return true;
}

async function updateRecoveredPassword() {
  if (recoveryInFlight) return;
  const message = document.querySelector('#admin-password-recovery-message');
  if (!recoveryAccessToken) {
    message.textContent = '유효한 비밀번호 설정 링크를 다시 요청해 주세요.';
    return;
  }
  const password = document.querySelector('#admin-new-password').value;
  const confirmation = document.querySelector('#admin-new-password-confirm').value;
  if (password.length < 12) {
    message.textContent = '새 비밀번호는 12자 이상으로 입력해 주세요.';
    return;
  }
  if (password !== confirmation) {
    message.textContent = '새 비밀번호가 서로 일치하지 않습니다.';
    return;
  }
  recoveryInFlight = true;
  document.querySelector('#btn-admin-password-update').disabled = true;
  try {
    const config = await api.getConfig();
    const response = await fetch(`${config.auth.supabase_url}/auth/v1/user`, {
      method: 'PUT',
      headers: {
        'Content-Type': 'application/json',
        apikey: config.auth.publishable_key,
        Authorization: `Bearer ${recoveryAccessToken}`,
      },
      body: JSON.stringify({ password }),
    });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(data.msg || data.message || data.error_description || '새 비밀번호를 저장하지 못했습니다.');
    sessionRevision += 1;
    accessToken = recoveryAccessToken;
    recoveryAccessToken = '';
    sessionSet(accessToken);
    window.history?.replaceState?.(null, '', window.location.pathname || '/admin.html');
    document.querySelector('#admin-new-password').value = '';
    document.querySelector('#admin-new-password-confirm').value = '';
    document.querySelector('#admin-password-recovery').hidden = true;
    await showAdmin();
  } catch (error) {
    message.textContent = error.message;
  } finally {
    recoveryInFlight = false;
    document.querySelector('#btn-admin-password-update').disabled = false;
  }
}

async function showAdmin() {
  const revision = sessionRevision;
  let session;
  try { session = await adminRequest('/api/admin/session'); }
  catch (error) {
    if (revision !== sessionRevision) throw error;
    if (error.status === 403) resetAdminSession('관리자 접근 권한을 확인할 수 없습니다. 권한이 있는 계정으로 다시 로그인해 주세요.');
    else if (accessToken) {
      sessionLoadMessage = '관리자 연결을 확인하지 못했습니다. 다시 불러오기를 눌러 주세요.';
      updateLoadStatus();
    }
    throw error;
  }
  sessionLoadMessage = '';
  try {
    const config = api.config || (api.getConfig ? await api.getConfig() : null);
    if (config?.environment) adminEnvironment = config.environment;
  } catch (_) { /* The authenticated admin sections can still load and the server validates references. */ }
  updateLoadStatus();
  document.querySelector('#admin-login').hidden = true;
  document.querySelector('#admin-app').hidden = false;
  ui.text(document.querySelector('#admin-name'), session.admin.display_name || '관리자');
  adminPermissions = new Set(session.admin.permissions || []);
  ui.text(document.querySelector('#admin-permissions'), `권한: ${[...adminPermissions].join(', ')}`);
  const tasks = [];
  document.querySelector('#admin-analytics-section').hidden = !adminPermissions.has('analytics:read');
  document.querySelector('#claim-operations-section').hidden = !adminPermissions.has('claims:read');
  document.querySelector('#ranking-contact-section').hidden = !adminPermissions.has('claims:read');
  document.querySelector('#ranking-finalization-section').hidden = !adminPermissions.has('ranking:read');
  document.querySelector('#fault-review-section').hidden = !adminPermissions.has('faults:read');
  if (adminPermissions.has('analytics:read')) tasks.push(loadMetrics());
  if (adminPermissions.has('claims:read')) {
    tasks.push(loadClaims(), loadRankingContacts());
  }
  if (adminPermissions.has('faults:read')) {
    tasks.push(loadFaults());
  }
  if (adminPermissions.has('ranking:read')) tasks.push(loadRankingSnapshots());
  document.querySelector('#btn-create-ranking-snapshot').disabled = !adminPermissions.has('ranking:write');
  document.querySelector('#btn-campaign-update').disabled = !adminPermissions.has('campaign:write');
  await Promise.allSettled(tasks);
}

async function loadMetrics() {
  const params = new URLSearchParams(new FormData(document.querySelector('#analytics-filter')));
  for (const [key, value] of [...params]) if (!value) params.delete(key);
  if (params.has('from')) params.set('from', `${params.get('from')}T00:00:00+09:00`);
  if (params.has('to')) params.set('to', `${nextCalendarDate(params.get('to'))}T00:00:00+09:00`);
  return loadSection('통계', `/api/admin/overview?${params}`, renderMetrics);
}

function renderMetrics(data) {
  campaignVersion = data.campaign?.version ?? campaignVersion;
  if (data.campaign?.status) document.querySelector('#campaign-status').value = data.campaign.status;
  ui.text(document.querySelector('#metrics-refreshed'), data.generated_at ? `갱신 ${new Date(data.generated_at).toLocaleString('ko-KR')}` : '갱신 시각 미제공');
  ui.text(document.querySelector('#metrics-window'), formatObservationWindow(data));
  const grid = document.querySelector('#metrics-grid');
  grid.replaceChildren();
  const metrics = Array.isArray(data.metrics) && data.metrics.length ? [...data.metrics] : legacyMetrics(data);
  for (const metric of metrics) {
    const card = document.createElement('article'); card.className = 'metric-card';
    const title = document.createElement('strong'); title.textContent = metric.label || metric.name || metric.key || '지표';
    const value = document.createElement('div'); value.className = 'metric-value';
    value.textContent = metric.denominator === 0 || metric.value === null || (metric.rate === null && metric.value == null) ? '계산 대상 없음' : formatMetricValue(metric);
    const windowSeconds = metric.observation_window_seconds ?? data.observation_window_seconds ?? data.observation_window?.seconds;
    const detail = document.createElement('p');
    detail.textContent = `분자 ${metric.numerator ?? '해당 없음'} / 분모 ${metric.denominator ?? '해당 없음'} · 고유 ${metric.unique_participants ?? '해당 없음'} · 이벤트 ${metric.event_count ?? '해당 없음'} · 관찰 ${windowSeconds == null ? '해당 없음' : `${windowSeconds}초`} · ${metric.estimated ? '추정값' : '원 집계'}`;
    card.append(title, value, detail); grid.appendChild(card);
  }
  renderSourceFunnel(data.source_funnel || []);
  renderScoreDistribution(data.score_distribution || []);
  renderLeaderboard(data.leaderboard || []);
  renderTicketLedger(data.ticket_ledger || []);
  renderDrawSummary(data.draws, data.draw_credit_ledger);
  renderClaimSummary(data.claims || []);
  renderOperationalBreakdowns(data);
  ui.text(document.querySelector('#metrics-scope'), `${data.synthetic_only ? '합성 테스트 데이터만 표시' : '운영 데이터 포함'} · 게임 버전 ${data.campaign?.game_version || data.game?.game_version || '미제공'} · 필터 귀속 ${data.filter_attribution || '미제공'} · 환경 ${data.environment || '현재 환경'}`);
  renderDefinitions(data.definitions || {});
}

function nextCalendarDate(date) {
  const [year, month, day] = date.split('-').map(Number);
  const next = new Date(Date.UTC(year, month - 1, day + 1));
  return next.toISOString().slice(0, 10);
}

function legacyMetrics(data) {
  const metrics = [];
  if (data.totals) {
    metrics.push(
      { label: '전체 이벤트', value: data.totals.events, event_count: data.totals.events, estimated: false },
      { label: '연결된 고유 참가자', value: data.totals.participants, unique_participants: data.totals.participants, estimated: false },
      { label: '미연결 초기 관측', value: data.totals.unlinked_observations, estimated: true },
      { label: '관측 활성 시간(ms)', value: data.totals.active_ms, estimated: true },
    );
  }
  for (const row of data.funnel || []) metrics.push({ label: row.event_name, value: row.events, numerator: row.events, unique_participants: row.participants, event_count: row.events, estimated: false });
  if (data.gemini_ctr) metrics.push({ label: 'Gemini 노출 후 클릭률', rate: data.gemini_ctr.rate, numerator: data.gemini_ctr.numerator, denominator: data.gemini_ctr.denominator, unique_participants: data.gemini_ctr.denominator, estimated: false });
  for (const row of data.loading?.buckets || []) metrics.push({ label: `로딩 마지막 관찰 ${row.bucket}`, value: row.observations, numerator: row.observations, event_count: row.events, estimated: true });
  return metrics;
}

function formatMetricValue(metric) {
  if (metric.rate != null) return `${(Number(metric.rate) * 100).toFixed(1)}%`;
  if (metric.value != null) return String(metric.value);
  return String(metric.numerator ?? 0);
}

function formatObservationWindow(data) {
  const window = data.observation_window || {};
  const start = window.from || window.start || data.period?.from || data.from;
  const end = window.to || window.end || data.period?.to || data.to;
  const seconds = data.observation_window_seconds ?? window.seconds;
  const range = start || end ? `${start ? new Date(start).toLocaleString('ko-KR') : '미지정'} ~ ${end ? new Date(end).toLocaleString('ko-KR') : '현재'}` : '전체 기간 미제공';
  return `관찰 구간 ${range}${seconds == null ? '' : ` · ${seconds}초`}`;
}

function renderTable(target, columns, rows, emptyText) {
  target.replaceChildren();
  if (!rows.length) {
    const empty = document.createElement('p'); empty.className = 'status-note'; empty.textContent = emptyText; target.appendChild(empty); return;
  }
  const table = document.createElement('table'); table.className = 'admin-table';
  const head = document.createElement('thead'); const headerRow = document.createElement('tr');
  for (const column of columns) { const th = document.createElement('th'); th.textContent = column.label; headerRow.appendChild(th); }
  head.appendChild(headerRow); table.appendChild(head);
  const body = document.createElement('tbody');
  for (const row of rows) {
    const tr = document.createElement('tr');
    for (const column of columns) {
      const td = document.createElement('td'); const value = column.value(row);
      td.textContent = value == null || value === '' ? '-' : String(value); tr.appendChild(td);
    }
    body.appendChild(tr);
  }
  table.appendChild(body); target.appendChild(table);
}

function renderTableGroup(target, groups) {
  target.replaceChildren();
  for (const group of groups) {
    const heading = document.createElement('h3'); heading.textContent = group.title;
    const tableTarget = document.createElement('div'); tableTarget.className = 'admin-table-wrap';
    target.append(heading, tableTarget);
    renderTable(tableTarget, group.columns, group.rows || [], group.emptyText);
  }
}

function renderSourceFunnel(rows) {
  renderTable(document.querySelector('#source-funnel'), [
    { label: '귀속', value: (row) => row.attribution === 'first' ? '첫 유입' : row.attribution === 'session' ? '이번 방문' : row.attribution },
    { label: '링크 유형', value: (row) => row.link_kind },
    { label: '채널', value: (row) => row.channel || row.channel_code },
    { label: '진입', value: (row) => row.entries ?? row.observations },
    { label: '참가자', value: (row) => row.participants ?? row.unique_participants },
    { label: '신규', value: (row) => row.new_participants },
    { label: '재방문', value: (row) => row.returning_participants },
    { label: '게임 시작', value: (row) => row.game_starts },
    { label: '게임 시작률', value: (row) => row.game_start_rate == null ? '계산 대상 없음' : `${(Number(row.game_start_rate) * 100).toFixed(1)}%` },
    { label: 'Gemini 클릭', value: (row) => row.gemini_clicks },
    { label: 'Gemini 클릭률', value: (row) => row.gemini_click_rate == null ? '계산 대상 없음' : `${(Number(row.gemini_click_rate) * 100).toFixed(1)}%` },
  ], rows, '조회된 유입 경로 지표가 없습니다.');
}

function renderScoreDistribution(rows) {
  renderTable(document.querySelector('#score-distribution'), [
    { label: '게임 버전', value: (row) => row.game_version || '미제공' },
    { label: '점수 구간', value: (row) => row.score_from != null && row.score_to != null ? `${row.score_from}~${row.score_to}` : (row.bucket || row.range || row.score_bucket) },
    { label: '기록 수', value: (row) => row.games ?? row.count ?? row.sessions ?? row.event_count },
    { label: '고유 참가자', value: (row) => row.participants ?? row.unique_participants },
  ], rows, '조회된 점수 분포가 없습니다.');
}

function renderLeaderboard(rows) {
  renderTable(document.querySelector('#leaderboard-summary'), [
    { label: '게임 버전', value: (row) => row.game_version || '미제공' },
    { label: '현재 순위', value: (row) => row.rank },
    { label: '참가자', value: (row) => row.nickname || '익명 참가자' },
    { label: '최고점', value: (row) => row.best_score },
  ], rows, '조회된 최고점 기록이 없습니다.');
}

function renderTicketLedger(rows) {
  renderTable(document.querySelector('#ticket-ledger'), [
    { label: '원장 사유', value: (row) => row.source_type },
    { label: '게임권 종류', value: (row) => row.ticket_kind },
    { label: '건수', value: (row) => row.events },
    { label: '고유 참가자', value: (row) => row.participants },
  ], rows, '조회된 게임권 원장 집계가 없습니다.');
}

function renderDrawSummary(draws = {}, creditRows = []) {
  const summary = [
    { label: '총 추첨 횟수', value: draws?.total_draws ?? 0 },
    { label: '실제 상품 당첨', value: draws?.actual_prize_draws ?? 0 },
    { label: '실제 상품 당첨자', value: draws?.actual_prize_winners ?? 0 },
    { label: 'Gemini 혜택 결과', value: draws?.benefit_results ?? 0 },
    { label: '실제 지급 완료', value: draws?.paid_prizes ?? 0 },
  ];
  renderTable(document.querySelector('#draw-summary'), [
    { label: '항목', value: (row) => row.label },
    { label: '건수', value: (row) => row.value },
  ], summary, '조회된 경품 뽑기 결과가 없습니다.');
  renderTable(document.querySelector('#draw-credit-ledger'), [
    { label: '뽑기권 원장 사유', value: (row) => row.source_type },
    { label: '건수', value: (row) => row.events },
    { label: '고유 참가자', value: (row) => row.participants },
    { label: '순증감', value: (row) => row.net_credits },
  ], Array.isArray(creditRows) ? creditRows : [], '조회된 뽑기권 원장 집계가 없습니다.');
}

const CLAIM_STATUS_LABELS = {
  AWAITING_INFORMATION: '정보 입력 대기', INFORMATION_RECEIVED: '정보 접수', PENDING_REVIEW: '확인 대기',
  CONTACTED: '연락 완료', PAID: '지급 완료', ON_HOLD: '보류', INELIGIBLE: '대상 아님', NO_RESPONSE: '응답 없음',
};

function renderClaimSummary(rows) {
  renderTable(document.querySelector('#claim-summary'), [
    { label: '수령 유형', value: (row) => row.claim_type },
    { label: '상태', value: (row) => CLAIM_STATUS_LABELS[row.status] || row.status },
    { label: '건수', value: (row) => row.claims },
    { label: '고유 참가자', value: (row) => row.participants },
  ], rows, '조회된 수령 상태 집계가 없습니다.');
}

function objectRows(value) {
  return Object.entries(value || {}).map(([key, count]) => ({ key, count }));
}

function sharingRows(sharing) {
  return [
    { label: '카카오 인증 전송', value: sharing?.server_confirmed_intents },
    { label: '카카오 인증 전송 참가자', value: sharing?.server_confirmed_participants },
    { label: '공유 시도', value: sharing?.attempt_events }, { label: '복사 성공', value: sharing?.copy_success_events },
    { label: '공유창 종료', value: sharing?.share_sheet_closed_events }, { label: '공유 취소', value: sharing?.cancelled_events },
    { label: '공유 실패', value: sharing?.failed_events }, { label: '실제 전송 완료', value: sharing?.actual_delivery || 'unknown' },
    { label: '공유 고유 참가자', value: sharing?.linked_participants }, { label: '공유 미연결 이벤트', value: sharing?.unlinked_events },
  ];
}

function sharingMethodColumns() {
  return [
    { label: '공유 수단', value: (row) => row.share_method || 'unknown' }, { label: '확인 상태', value: (row) => row.status || 'unknown' },
    { label: '이벤트', value: (row) => row.events }, { label: '고유 참가자', value: (row) => row.linked_participants },
    { label: '미연결 이벤트', value: (row) => row.unlinked_events },
  ];
}

function renderOperationalBreakdowns(data) {
  renderTable(document.querySelector('#loading-summary'), [
    { label: '로딩 마지막 구간', value: (row) => row.bucket },
    { label: '관측', value: (row) => row.observations },
    { label: '이벤트', value: (row) => row.events },
    { label: '준비 완료', value: (row) => row.ready },
    { label: '진행 중', value: (row) => row.pending },
    { label: '추정 이탈', value: (row) => row.estimated_exits },
    { label: '추정 이탈률', value: (row) => row.estimated_exit_rate == null ? '계산 대상 없음' : `${(Number(row.estimated_exit_rate) * 100).toFixed(1)}%` },
  ], data.loading?.buckets || [], '조회된 로딩 구간이 없습니다.');
  const loadingTarget = document.querySelector('#loading-summary');
  if (data.loading?.milestones?.length) {
    const milestoneTarget = document.createElement('div'); milestoneTarget.className = 'admin-table-wrap';
    loadingTarget.appendChild(milestoneTarget);
    renderTable(milestoneTarget, [
      { label: '로딩 마일스톤', value: (row) => row.milestone }, { label: '이벤트', value: (row) => row.events },
      { label: '참가자', value: (row) => row.participants }, { label: '관찰', value: (row) => row.observations },
    ], data.loading.milestones, '조회된 로딩 마일스톤이 없습니다.');
  }
  renderTable(document.querySelector('#screen-summary'), [
    { label: '화면', value: (row) => row.screen }, { label: '방문', value: (row) => row.visits },
    { label: '활성 ms', value: (row) => row.active_ms }, { label: '진행 중', value: (row) => row.ongoing },
    { label: '추정 이탈', value: (row) => row.estimated_exits },
  ], data.screens || [], '조회된 화면 체류가 없습니다.');
  renderTable(document.querySelector('#stage-summary'), [
    { label: '단계', value: (row) => row.label || row.key }, { label: '진입', value: (row) => row.entered },
    { label: '진행', value: (row) => row.progressed }, { label: '추정 이탈', value: (row) => row.estimated_exits },
    { label: '진행 중', value: (row) => row.pending }, { label: '평균 관측 경과(초)', value: (row) => row.mean_observed_elapsed_seconds ?? row.mean_active_elapsed_seconds },
    { label: '평균 활성 체류(ms)', value: (row) => row.mean_observed_active_ms },
    { label: '활성 체류 관측', value: (row) => row.active_dwell_observations },
    { label: '활성 체류 알 수 없음', value: (row) => row.active_dwell_unknown },
    { label: '이탈 평균 활성 체류(ms)', value: (row) => row.mean_abandoned_active_ms },
    { label: '이탈 활성 체류 관측', value: (row) => row.abandoned_active_observations },
    { label: '이탈 활성 체류 알 수 없음', value: (row) => row.abandoned_active_unknown },
  ], data.stages || [], '조회된 단계 지표가 없습니다.');
  renderTableGroup(document.querySelector('#game-summary'), [
    {
      title: '게임 상태', rows: objectRows(data.game), emptyText: '조회된 게임 상태가 없습니다.',
      columns: [{ label: '게임 상태', value: (row) => row.key }, { label: '세션', value: (row) => row.count }],
    },
    {
      title: '마지막 관측 단계와 활성 시간', rows: data.game_progress?.by_last_stage || [], emptyText: '연결된 게임 진행 관측이 없습니다.',
      columns: [
        { label: '마지막 단계', value: (row) => row.last_stage || 'unknown' },
        { label: '세션', value: (row) => row.sessions }, { label: '참가자', value: (row) => row.participants },
        { label: '평균 마지막 활성 ms', value: (row) => row.mean_last_observed_active_ms },
        { label: '최대 마지막 활성 ms', value: (row) => row.max_last_observed_active_ms },
        { label: '활성 시간 알 수 없음', value: (row) => row.active_time_unknown },
      ],
    },
    {
      title: '참가자 미연결 게임 관측', rows: [{ count: data.game_progress?.unlinked_checkpoint_events }], emptyText: '미연결 게임 관측 정보가 없습니다.',
      columns: [{ label: '미연결 체크포인트 이벤트', value: (row) => row.count }],
    },
  ]);
  renderTable(document.querySelector('#result-dwell'), [
    { label: '결과 유형', value: (row) => row.result_type }, { label: '화면', value: (row) => row.views ?? row.visits },
    { label: '활성 ms', value: (row) => row.active_ms },
  ], data.result_dwell || [], '조회된 결과 화면 체류가 없습니다.');
  renderTableGroup(document.querySelector('#invitation-summary'), [
    {
      title: '초대 방문 판정', rows: data.invitation || [], emptyText: '조회된 초대 판정이 없습니다.',
      columns: [
        { label: '초대 상태', value: (row) => row.status }, { label: '사유', value: (row) => row.reason || 'unknown' },
        { label: '방문', value: (row) => row.visits }, { label: '방문자', value: (row) => row.visitors },
      ],
    },
    {
      title: '게임 재도전 공유 수단과 확인 가능한 상태', rows: data.sharing?.invitation_sharing?.by_method_status || [], emptyText: '조회된 게임 재도전 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '재도전 초대 공유 수단과 확인 가능한 상태', rows: data.sharing?.retry_invite_sharing?.by_method_status || [], emptyText: '조회된 재도전 초대 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '기록 공유 수단과 확인 가능한 상태', rows: data.sharing?.record_share_sharing?.by_method_status || [], emptyText: '조회된 기록 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '당첨 공유 수단과 확인 가능한 상태', rows: data.sharing?.prize_share_sharing?.by_method_status || [], emptyText: '조회된 당첨 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '수령 정보 자랑 공유 수단과 확인 가능한 상태', rows: data.sharing?.claim_share_sharing?.by_method_status || [], emptyText: '조회된 수령 정보 자랑 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '게임 재도전 공유·전환 요약', rows: [
        ...sharingRows(data.sharing?.invitation_sharing),
        { label: '초대권 지급', value: data.invitation_performance?.grant_events }, { label: '지급 참가자', value: data.invitation_performance?.granted_participants },
        { label: '초대권 사용', value: data.invitation_performance?.use_events }, { label: '사용 참가자', value: data.invitation_performance?.using_participants },
        { label: '기간 내 사용/지급 비율', value: data.invitation_performance?.period_use_to_grant_ratio == null ? '계산 대상 없음' : `${(Number(data.invitation_performance.period_use_to_grant_ratio) * 100).toFixed(1)}%` },
        { label: '비율 정의', value: data.invitation_performance?.ratio_definition || 'unknown' },
        { label: '쿨다운 후 재획득', value: data.invitation_performance?.cooldown_reacquisition_events },
        { label: '쿨다운 후 재획득 참가자', value: data.invitation_performance?.cooldown_reacquisition_participants },
        { label: '쿨다운 후 재참여', value: data.invitation_performance?.cooldown_reparticipation_events },
        { label: '쿨다운 후 재참여 참가자', value: data.invitation_performance?.cooldown_reparticipation_participants },
      ], emptyText: '조회된 공유·초대 전환 요약이 없습니다.',
      columns: [{ label: '항목', value: (row) => row.label }, { label: '값', value: (row) => row.value }],
    },
  ]);
  const gemini = objectRows(data.gemini_conversion).concat([
    { key: '관찰 완료 후 클릭 참가자', count: data.gemini_ctr?.numerator },
    { key: '관찰 완료 노출 참가자 (분모)', count: data.gemini_ctr?.denominator },
    { key: '관찰 완료 후 미클릭 참가자', count: data.gemini_ctr ? data.gemini_ctr.denominator - data.gemini_ctr.numerator : null },
    { key: '관찰 중 참가자 (확정 집계 제외)', count: data.gemini_ctr?.pending_participants },
    { key: '관찰 중 참가자의 노출 이벤트', count: data.gemini_ctr?.pending_exposure_events },
    { key: '관찰 완료 CTR', count: data.gemini_ctr?.rate == null ? '계산 대상 없음' : `${(Number(data.gemini_ctr.rate) * 100).toFixed(1)}%` },
  ]);
  renderTableGroup(document.querySelector('#gemini-summary'), [
    {
      title: 'Gemini 전환', rows: gemini, emptyText: '조회된 Gemini 전환이 없습니다.',
      columns: [{ label: 'Gemini 항목', value: (row) => row.key }, { label: '값', value: (row) => row.count }],
    },
    {
      title: 'Gemini 링크 복사·공유 요약', rows: sharingRows(data.sharing?.gemini_sharing), emptyText: '조회된 Gemini 공유 시도가 없습니다.',
      columns: [{ label: '항목', value: (row) => row.label }, { label: '값', value: (row) => row.value }],
    },
    {
      title: 'Gemini 공유 수단과 확인 가능한 상태', rows: data.sharing?.gemini_sharing?.by_method_status || [], emptyText: '조회된 Gemini 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '목적 미확인 공유 (초대·Gemini 합계 제외)', rows: sharingRows(data.sharing?.unknown_sharing), emptyText: '목적 미확인 공유가 없습니다.',
      columns: [{ label: '항목', value: (row) => row.label }, { label: '값', value: (row) => row.value }],
    },
    {
      title: '콘텐츠별 클릭·경유', rows: data.content || [], emptyText: '조회된 승인 콘텐츠 행동이 없습니다.',
      columns: [
        { label: '콘텐츠', value: (row) => row.content || 'unknown' }, { label: '노출', value: (row) => row.view_events }, { label: '클릭', value: (row) => row.click_events },
        { label: '노출 참가자', value: (row) => row.viewed_participants }, { label: '클릭 참가자', value: (row) => row.clicked_participants },
        { label: '고유 CTR', value: (row) => row.unique_ctr == null ? '계산 대상 없음' : `${(Number(row.unique_ctr) * 100).toFixed(1)}%` },
        { label: '경유 요청', value: (row) => row.outbound_request_events }, { label: '연결 참가자', value: (row) => row.linked_participants },
        { label: '미연결 이벤트', value: (row) => row.unlinked_events },
      ],
    },
  ]);
}

function renderDefinitions(definitions) {
  renderTable(document.querySelector('#metrics-definitions'), [
    { label: '정의', value: (row) => row.key }, { label: '설명', value: (row) => row.value },
  ], Object.entries(definitions).map(([key, value]) => ({ key, value })), '서버가 제공한 지표 정의가 없습니다.');
}

async function loadFaults() {
  return loadSection('장애 심사', '/api/admin/game-faults?status=PENDING', renderFaults);
}

function renderFaults(data) {
  const list = document.querySelector('#admin-faults'); list.replaceChildren();
  if (!data.faults?.length) {
    const empty = document.createElement('p'); empty.textContent = '심사 대기 중인 장애 신고가 없습니다.'; list.appendChild(empty); return;
  }
  for (const fault of data.faults) list.appendChild(faultEditor(fault));
}

function faultEditor(fault) {
  const item = document.createElement('article'); item.className = 'admin-claim-row';
  const info = document.createElement('div');
  const title = document.createElement('strong'); title.textContent = `${fault.ticket_kind} 게임권 · ${fault.fault_reason}`;
  const meta = document.createElement('p'); meta.textContent = `체크포인트 ${fault.last_checkpoint_tick ?? '-'} · 심사 버전 ${fault.fault_review_version}`;
  info.append(title, meta);
  const decision = document.createElement('select');
  for (const value of ['APPROVE', 'DENY']) { const option = document.createElement('option'); option.value = value; option.textContent = value === 'APPROVE' ? '환급 승인' : '환급 거절'; decision.appendChild(option); }
  const reason = document.createElement('input'); reason.placeholder = '심사 사유'; reason.maxLength = 160;
  const save = document.createElement('button'); save.className = 'btn btn-primary btn-sm'; save.textContent = '심사 저장';
  if (!adminPermissions.has('faults:write')) {
    decision.disabled = true; reason.disabled = true; save.disabled = true; save.textContent = '읽기 전용';
  }
  save.onclick = async () => {
    if (reason.value.trim().length < 3) { ui.showToast('심사 사유를 3자 이상 입력해 주세요.'); return; }
    save.disabled = true;
    try {
      await adminRequest(`/api/admin/game-faults/${encodeURIComponent(fault.id)}`, {
        method: 'PATCH',
        body: JSON.stringify({ decision: decision.value, reason: reason.value.trim(), expected_version: fault.fault_review_version, event_id: api.createRequestId('evt') }),
      });
      ui.showToast('장애 심사 결과를 저장했습니다.');
      await Promise.all([loadFaults(), ...(adminPermissions.has('analytics:read') ? [loadMetrics()] : [])]);
    } catch (error) { ui.showToast(error.message); save.disabled = false; }
  };
  item.append(info, decision, reason, save); return item;
}

async function loadClaims() {
  return loadSection('수령 원장', '/api/admin/claims?limit=100', renderClaims);
}

function renderClaims(data) {
  const list = document.querySelector('#admin-claims'); list.replaceChildren();
  if (!data.claims?.length) { const empty = document.createElement('p'); empty.textContent = '처리할 수령 건이 없습니다.'; list.appendChild(empty); return; }
  for (const claim of data.claims) list.appendChild(claimEditor(claim));
}

async function loadRankingContacts() {
  return loadSection('TOP3 접수', '/api/admin/ranking-contacts', renderRankingContacts);
}

function renderRankingContacts(data) {
  const list = document.querySelector('#admin-ranking-contacts'); list.replaceChildren();
  if (!data.ranking_contacts?.length) { const empty = document.createElement('p'); empty.textContent = '잠정 TOP3 연락 접수 건이 없습니다.'; list.appendChild(empty); return; }
  for (const contact of data.ranking_contacts) {
    const item = document.createElement('article'); item.className = 'claim-card';
    const title = document.createElement('strong'); title.textContent = `접수 ${contact.ranking_status} · 수령 ${contact.claim_status || '미생성'}`;
    const meta = document.createElement('p'); meta.textContent = `요청 ${contact.requested_at ? new Date(contact.requested_at).toLocaleString('ko-KR') : '-'} · 제출 ${contact.submitted_at ? new Date(contact.submitted_at).toLocaleString('ko-KR') : '-'}`;
    const privateInfo = document.createElement('p'); privateInfo.className = 'private-contact';
    privateInfo.textContent = `연락 정보: ${contact.recipient_name || '미접수'} · ${contact.contact || '-'} · ${contact.school || '-'}`;
    item.append(title, meta, privateInfo); list.appendChild(item);
  }
}

async function loadRankingSnapshots() {
  return loadSection('최종 랭킹', '/api/admin/ranking-snapshots', renderRankingSnapshots);
}

function renderRankingSnapshots(data) {
  const list = document.querySelector('#admin-ranking-snapshots'); list.replaceChildren();
  const snapshots = Array.isArray(data.snapshots) ? data.snapshots : [];
  if (!snapshots.length) {
    const empty = document.createElement('p'); empty.className = 'status-note'; empty.textContent = '생성된 랭킹 스냅샷이 없습니다.'; list.appendChild(empty); return;
  }
  for (const snapshot of snapshots) list.appendChild(rankingSnapshotEditor(snapshot));
}

function rankingSnapshotEditor(snapshot) {
  const item = document.createElement('article'); item.className = 'claim-card';
  const title = document.createElement('strong');
  title.textContent = snapshot.status === 'FINAL' ? '최종 확정 완료' : '확정 전 스냅샷';
  const meta = document.createElement('p');
  const captured = snapshot.captured_at ? new Date(snapshot.captured_at).toLocaleString('ko-KR') : '-';
  meta.textContent = `생성 ${captured} · 기록 ${Number(snapshot.entry_count || 0).toLocaleString('ko-KR')}명 · 먼저 달성 우선`;
  const status = document.createElement('p'); status.className = 'status-note';
  status.textContent = snapshot.status === 'FINAL'
    ? `확정 ${snapshot.finalized_at ? new Date(snapshot.finalized_at).toLocaleString('ko-KR') : '-'} · TOP3 수령 요청과 경품 예약 생성 완료`
    : '최종 확정 전에 TOP3 플레이 기록을 각각 검토해야 합니다. 재학생 자격 확인은 수령 업무에서 별도로 진행합니다.';
  item.append(title, meta, status);
  const candidates = Array.isArray(snapshot.candidates) ? snapshot.candidates : [];
  for (const candidate of candidates) item.appendChild(rankingCandidateReview(snapshot, candidate));
  if (snapshot.status !== 'FINAL') {
    const controls = document.createElement('div'); controls.className = 'inline-controls';
    const reason = document.createElement('input'); reason.maxLength = 160; reason.placeholder = '최종 확정 사유'; reason.ariaLabel = '최종 랭킹 확정 사유';
    const finalize = document.createElement('button'); finalize.type = 'button'; finalize.className = 'btn btn-primary btn-sm'; finalize.textContent = 'TOP3 최종 확정';
    const ready = candidates.length === 3 && candidates.every((candidate) => candidate.participant_status === 'ACTIVE'
      && candidate.binding_current && candidate.review?.binding_current && candidate.review?.outcome === 'APPROVED');
    if (!ready) { finalize.disabled = true; finalize.textContent = '검토 완료 후 확정'; }
    if (!adminPermissions.has('ranking:write')) { reason.disabled = true; finalize.disabled = true; finalize.textContent = '읽기 전용'; }
    finalize.onclick = async () => {
      const value = reason.value.trim();
      if (!value) { ui.showToast('최종 확정 사유를 입력해 주세요.'); return; }
      finalize.disabled = true;
      try {
        await adminRequest(`/api/admin/ranking-snapshots/${encodeURIComponent(snapshot.id)}/finalize`, {
          method: 'POST', body: JSON.stringify({ reason: value, event_id: api.createRequestId('evt') }),
        });
        ui.showToast('TOP3 최종 순위를 확정했습니다. 실제 지급은 수동으로 처리해 주세요.');
        await Promise.all([loadRankingSnapshots(), ...(adminPermissions.has('claims:read') ? [loadClaims()] : [])]);
      } catch (error) { ui.showToast(error.message); finalize.disabled = false; }
    };
    controls.append(reason, finalize); item.appendChild(controls);
  }
  return item;
}

function rankingCandidateReview(snapshot, candidate) {
  const card = document.createElement('section'); card.className = 'status-note';
  const title = document.createElement('strong');
  title.textContent = `${candidate.rank}위 후보 · ${Number(candidate.score || 0).toLocaleString('ko-KR')}점 · ${Number(candidate.elapsed_seconds || 0).toFixed(1)}초`;
  const session = document.createElement('p');
  session.textContent = `세션 ${candidate.session_id || '-'} · 완료 ${candidate.achieved_at ? new Date(candidate.achieved_at).toLocaleString('ko-KR') : '-'} · ${candidate.end_reason || '-'} · ${candidate.verification || '-'}`;
  const summary = document.createElement('p');
  const summaryText = Object.entries(candidate.summary || {}).map(([key, value]) => `${key} ${value}`).join(' · ');
  summary.textContent = `게임 요약: ${summaryText || '기록 없음'}`;
  const review = document.createElement('p');
  if (candidate.participant_status !== 'ACTIVE') review.textContent = '참가 제한 상태 — 자동으로 차순위를 선정하지 않습니다.';
  else if (!candidate.binding_current || (candidate.review && !candidate.review.binding_current)) review.textContent = '현재 최고 기록과 다름 — 새 스냅샷이 필요합니다.';
  else if (candidate.review?.outcome === 'APPROVED') review.textContent = `플레이 검토 승인 · ${candidate.review.evidence_reference}`;
  else if (candidate.review?.outcome === 'HOLD') review.textContent = `플레이 검토 보류 · ${candidate.review.evidence_reference}`;
  else review.textContent = '플레이 기록 미검토';
  card.append(title, session, summary, review);
  if (snapshot.status === 'FINAL') return card;
  const controls = document.createElement('div'); controls.className = 'inline-controls';
  const evidence = document.createElement('input'); evidence.maxLength = 109; evidence.placeholder = '근거 참조 (TEST_REF_... / REF_...)'; evidence.ariaLabel = `${candidate.rank}위 검토 근거 참조`;
  const reason = document.createElement('input'); reason.maxLength = 500; reason.placeholder = '검토 사유 (개인정보 금지)'; reason.ariaLabel = `${candidate.rank}위 검토 사유`;
  const approve = document.createElement('button'); approve.type = 'button'; approve.className = 'btn btn-primary btn-sm'; approve.textContent = '플레이 승인';
  const hold = document.createElement('button'); hold.type = 'button'; hold.className = 'btn btn-sm'; hold.textContent = '검토 보류';
  const writable = adminPermissions.has('ranking:write') && candidate.participant_status === 'ACTIVE' && candidate.binding_current;
  if (!writable) { evidence.disabled = true; reason.disabled = true; approve.disabled = true; hold.disabled = true; }
  const submit = async (outcome, button) => {
    const evidenceReference = evidence.value.trim(); const reviewReason = reason.value.trim();
    if (!evidenceReference || reviewReason.length < 3) { ui.showToast('비개인 정보 근거 참조와 검토 사유를 입력해 주세요.'); return; }
    approve.disabled = true; hold.disabled = true;
    try {
      await adminRequest(`/api/admin/ranking-snapshots/${encodeURIComponent(snapshot.id)}/reviews`, {
        method: 'POST', body: JSON.stringify({ participant_id: candidate.participant_id, outcome,
          evidence_reference: evidenceReference, reason: reviewReason, event_id: api.createRequestId('evt') }),
      });
      ui.showToast(outcome === 'APPROVED' ? '플레이 기록을 승인했습니다.' : '플레이 기록을 보류했습니다.');
      await loadRankingSnapshots();
    } catch (error) { ui.showToast(error.message); button.disabled = false; approve.disabled = false; hold.disabled = false; }
  };
  approve.onclick = () => submit('APPROVED', approve); hold.onclick = () => submit('HOLD', hold);
  controls.append(evidence, reason, approve, hold); card.appendChild(controls);
  return card;
}

function claimEditor(claim) {
  const item = document.createElement('article'); item.className = 'admin-claim-row admin-payment-editor';
  const info = document.createElement('div');
  const finalizedRanking = claim.claim_type === 'RANKING' && Boolean(claim.prize_id && claim.inventory_item_id);
  const claimTitle = claim.claim_type === 'RANKING'
    ? (finalizedRanking ? (claim.prize_name || 'TOP3 수령 요청') : '잠정 TOP3 연락 접수')
    : (claim.prize_name || '경품 수령 요청');
  const title = document.createElement('strong'); title.textContent = `${claimTitle} · ${CLAIM_STATUS_LABELS[claim.status] || claim.status}`;
  const meta = document.createElement('p'); meta.textContent = `담당 ${claim.assignee_display_name || claim.assignee_user_id || '미지정'} · 버전 ${claim.version}`;
  const privateInfo = document.createElement('p'); privateInfo.className = 'private-contact';
  privateInfo.textContent = `연락 정보: ${claim.recipient_name || '미접수'} · ${claim.contact || '-'} · ${claim.school || '-'} · ${claim.address || '-'}`;
  info.append(title, meta, privateInfo);
  if (claim.claim_type === 'RANKING' && !finalizedRanking) {
    const rankingRestriction = document.createElement('p'); rankingRestriction.className = 'status-note';
    rankingRestriction.textContent = '잠정 TOP3는 최종 수상 확정 전이므로 지급 완료로 변경할 수 없습니다.';
    info.appendChild(rankingRestriction);
  }
  const awaitingInformation = claim.status === 'AWAITING_INFORMATION';
  const needsContact = !claim.contact_submitted_at || !claim.recipient_name || !claim.contact;
  const canCloseNoResponse = awaitingInformation && claim.can_close_no_response === true;
  if (awaitingInformation || needsContact) {
    const note = document.createElement('p'); note.className = 'status-note';
    note.textContent = canCloseNoResponse
      ? '접수 기한이 지났습니다. 사유를 남겨 미응답으로 마감할 수 있습니다. 지급 처리는 할 수 없습니다.'
      : '참가자가 수령 정보를 제출한 뒤 확인·연락·지급 상태로 변경할 수 있습니다.';
    info.appendChild(note);
  }
  const state = document.createElement('select');
  for (const [status, label] of Object.entries(CLAIM_STATUS_LABELS)) {
    const option = document.createElement('option'); option.value = status; option.textContent = label; option.selected = claim.status === status;
    option.disabled = (claim.claim_type === 'RANKING' && !finalizedRanking && status === 'PAID')
      || (awaitingInformation ? status !== 'AWAITING_INFORMATION' && !(canCloseNoResponse && status === 'NO_RESPONSE') : status === 'AWAITING_INFORMATION');
    state.appendChild(option);
  }
  state.value = claim.status;
  state.ariaLabel = '수령 처리 상태';
  const assignee = document.createElement('input'); assignee.placeholder = '담당자 user id'; assignee.value = claim.assignee_user_id || ''; assignee.maxLength = 80;
  const reason = document.createElement('input'); reason.placeholder = '변경 사유'; reason.maxLength = 160;
  const verificationLabel = document.createElement('label');
  const verificationText = document.createElement('span'); verificationText.textContent = '자격 확인';
  const verification = document.createElement('select'); verification.ariaLabel = '자격 확인 상태';
  for (const [value, label] of Object.entries({ NOT_REQUESTED: '확인 전', PENDING: '확인 중', VERIFIED: '확인 완료', REJECTED: '자격 미충족' })) {
    const option = document.createElement('option'); option.value = value; option.textContent = label;
    verification.appendChild(option);
  }
  verification.value = claim.verification_status || 'NOT_REQUESTED';
  verificationLabel.append(verificationText, verification);
  const referencePrefix = adminEnvironment === 'production' ? 'REF_' : 'TEST_REF_';
  const reference = document.createElement('input'); reference.ariaLabel = '자격 확인 참조';
  reference.placeholder = `확인 참조 (${referencePrefix}...)`; reference.maxLength = 109; reference.value = claim.verification_reference || '';
  const external = document.createElement('label'); const externalBox = document.createElement('input'); externalBox.type = 'checkbox'; externalBox.checked = Boolean(claim.external_delivery); externalBox.disabled = awaitingInformation || needsContact; const externalText = document.createElement('span'); externalText.textContent = '외부 전달 완료'; external.append(externalBox, externalText);
  const paymentNote = document.createElement('p'); paymentNote.className = 'status-note';
  paymentNote.textContent = '지급 완료 전 자격 확인과 외부 전달을 확인하고, 전달 확인 사유를 입력해 주세요. 증빙 원본·연락처는 적지 마세요.';
  const updatePaymentNote = () => {
    paymentNote.hidden = state.value !== 'PAID';
    reason.placeholder = state.value === 'PAID' ? '전달 확인 사유 (3자 이상)' : '변경 사유';
  };
  state.onchange = updatePaymentNote; updatePaymentNote();
  if (claim.status === 'PAID') { verification.disabled = true; reference.disabled = true; externalBox.disabled = true; }
  if (canCloseNoResponse) { verification.disabled = true; reference.disabled = true; externalBox.disabled = true; }
  const save = document.createElement('button'); save.className = 'btn btn-primary btn-sm'; save.textContent = '상태 저장';
  if (!adminPermissions.has('claims:write') || ((awaitingInformation || needsContact) && !canCloseNoResponse)) {
    state.disabled = true; assignee.disabled = true; reason.disabled = true; verification.disabled = true; reference.disabled = true; externalBox.disabled = true; save.disabled = true;
    save.textContent = awaitingInformation ? '수령 정보 입력 대기' : needsContact ? '수령 정보 확인 필요' : '읽기 전용';
  }
  save.onclick = async () => {
    if (canCloseNoResponse && (state.value !== 'NO_RESPONSE' || reason.value.trim().length < 3)) {
      ui.showToast('미응답을 선택하고 마감 사유를 3자 이상 입력해 주세요.'); return;
    }
    const verificationReference = reference.value.trim() || null;
    const referencePattern = adminEnvironment === 'production' ? /^REF_[A-Za-z0-9_-]{1,100}$/ : /^TEST_REF_[A-Za-z0-9_-]{1,100}$/;
    if (verificationReference && !referencePattern.test(verificationReference)) {
      ui.showToast(`확인 참조는 ${referencePrefix}로 시작하는 영문·숫자·밑줄·하이픈으로 입력해 주세요.`); return;
    }
    if (verification.value !== 'NOT_REQUESTED' && !verificationReference) { ui.showToast('자격 확인 참조를 입력해 주세요.'); return; }
    if (state.value === 'PAID') {
      if (verification.value !== 'VERIFIED') { ui.showToast('자격 확인을 완료한 뒤 지급 완료로 변경해 주세요.'); return; }
      if (!externalBox.checked) { ui.showToast('실제로 전달한 뒤 외부 전달 완료를 체크해 주세요.'); return; }
      if (claim.status !== 'PAID' && reason.value.trim().length < 3) { ui.showToast('전달 확인 사유를 3자 이상 입력해 주세요.'); return; }
    }
    save.disabled = true;
    try {
      await adminRequest(`/api/admin/claims/${encodeURIComponent(claim.id)}`, { method: 'PATCH', body: JSON.stringify({ status: state.value, assignee_user_id: assignee.value.trim() || null, reason: reason.value.trim(), verification_status: verification.value, verification_reference: verificationReference, external_delivery: externalBox.checked, expected_version: claim.version, event_id: api.createRequestId('evt') }) });
      ui.showToast('수령 상태를 저장했습니다.');
      await Promise.all([loadClaims(), ...(adminPermissions.has('analytics:read') ? [loadMetrics()] : [])]);
    } catch (error) { ui.showToast(error.message); save.disabled = false; }
  };
  item.append(info, state, assignee, verificationLabel, reference, reason, external, paymentNote, save); return item;
}

document.querySelector('#btn-admin-login').onclick = login;
document.querySelector('#admin-password').addEventListener('keydown', (event) => { if (event.key === 'Enter') login(); });
document.querySelector('#btn-admin-password-reset').onclick = requestPasswordRecovery;
document.querySelector('#btn-admin-password-update').onclick = updateRecoveredPassword;
document.querySelector('#btn-admin-password-recovery-cancel').onclick = leaveRecoveryMode;
document.querySelector('#admin-new-password-confirm').addEventListener('keydown', (event) => { if (event.key === 'Enter') updateRecoveredPassword(); });
document.querySelector('#btn-admin-logout').onclick = () => { accessToken = ''; sessionClear(); window.location.reload(); };
document.querySelector('#btn-admin-retry').onclick = async () => {
  const button = document.querySelector('#btn-admin-retry'); button.disabled = true;
  try { await showAdmin(); } catch (_) { /* showAdmin displays the appropriate recovery state. */ }
  finally { button.disabled = false; }
};
document.querySelector('#analytics-filter').onsubmit = (event) => { event.preventDefault(); loadMetrics().catch((error) => ui.showToast(error.message)); };
document.querySelector('#btn-refresh-claims').onclick = () => loadClaims().catch((error) => ui.showToast(error.message));
document.querySelector('#btn-refresh-ranking-contacts').onclick = () => loadRankingContacts().catch((error) => ui.showToast(error.message));
document.querySelector('#btn-refresh-ranking-snapshots').onclick = () => loadRankingSnapshots().catch((error) => ui.showToast(error.message));
document.querySelector('#btn-create-ranking-snapshot').onclick = async () => {
  const button = document.querySelector('#btn-create-ranking-snapshot'); button.disabled = true;
  try {
    await adminRequest('/api/admin/ranking-snapshots', { method: 'POST', body: JSON.stringify({ event_id: api.createRequestId('evt') }) });
    ui.showToast('현재 기록으로 랭킹 스냅샷을 만들었습니다.'); await loadRankingSnapshots();
  } catch (error) { ui.showToast(error.message); }
  finally { button.disabled = !adminPermissions.has('ranking:write'); }
};
document.querySelector('#btn-refresh-faults').onclick = () => loadFaults().catch((error) => ui.showToast(error.message));
document.querySelector('#btn-campaign-update').onclick = async () => {
  try {
    const status = document.querySelector('#campaign-status').value;
    const reason = document.querySelector('#campaign-reason').value.trim();
    if (!reason) return ui.showToast('변경 사유를 입력해 주세요.');
    if (!campaignVersion) return ui.showToast('행사 버전을 불러온 뒤 다시 시도해 주세요.');
    const data = await adminRequest('/api/admin/campaign', { method: 'PATCH', body: JSON.stringify({ status, reason, expected_version: campaignVersion, event_id: api.createRequestId('evt') }) });
    campaignVersion = data.version; ui.showToast('행사 상태를 변경했습니다.'); await loadMetrics();
  } catch (error) { ui.showToast(error.message); }
};

if (typeof window !== 'undefined') {
  const initialAdminAccessToken = accessToken;
  initializePasswordRecovery().then((recoveryMode) => {
    if (!recoveryMode && initialAdminAccessToken && accessToken === initialAdminAccessToken) showAdmin().catch(() => {});
  }).catch(() => {
    leaveRecoveryMode();
    ui.text(document.querySelector('#admin-login-message'), '비밀번호 설정 링크를 확인하지 못했습니다. 새 링크를 요청해 주세요.');
  });
}
