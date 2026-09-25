import { api } from './api.js';
import { ui } from './ui.js';

const TOKEN_KEY = 'dino_admin_access_token';
function sessionGet() { try { return sessionStorage.getItem(TOKEN_KEY) || ''; } catch (_) { return ''; } }
function sessionSet(value) { try { sessionStorage.setItem(TOKEN_KEY, value); } catch (_) {} }
function sessionClear() { try { sessionStorage.removeItem(TOKEN_KEY); } catch (_) {} }
let accessToken = sessionGet();
let campaignVersion = 0;
let adminPermissions = new Set();

async function adminRequest(path, options = {}) {
  const headers = new Headers(options.headers || {});
  headers.set('Authorization', `Bearer ${accessToken}`);
  if (options.body) headers.set('Content-Type', 'application/json');
  const mutation = options.method && options.method !== 'GET';
  if (mutation) headers.set('Idempotency-Key', options.idempotencyKey || api.createRequestId('admin'));
  const fetchOptions = { ...options, headers, credentials: 'same-origin' };
  let response;
  try { response = await fetch(path, fetchOptions); }
  catch (error) { if (!mutation) throw error; response = await fetch(path, fetchOptions); }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(data.message || data.error || '관리자 요청에 실패했습니다.');
  return data;
}

async function login() {
  const message = document.querySelector('#admin-login-message');
  message.textContent = '';
  try {
    const config = await api.getConfig();
    const email = document.querySelector('#admin-email').value.trim();
    const password = document.querySelector('#admin-password').value;
    const response = await fetch(`${config.auth.supabase_url}/auth/v1/token?grant_type=password`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json', apikey: config.auth.publishable_key },
      body: JSON.stringify({ email, password }),
    });
    const auth = await response.json().catch(() => ({}));
    if (!response.ok || !auth.access_token) throw new Error(auth.msg || auth.error_description || '로그인에 실패했습니다.');
    accessToken = auth.access_token;
    sessionSet(accessToken);
    document.querySelector('#admin-password').value = '';
    await showAdmin();
  } catch (error) { message.textContent = error.message; }
}

async function showAdmin() {
  const session = await adminRequest('/api/admin/session');
  document.querySelector('#admin-login').hidden = true;
  document.querySelector('#admin-app').hidden = false;
  ui.text(document.querySelector('#admin-name'), session.admin.display_name || '관리자');
  adminPermissions = new Set(session.admin.permissions || []);
  ui.text(document.querySelector('#admin-permissions'), `권한: ${[...adminPermissions].join(', ')}`);
  const tasks = [];
  if (adminPermissions.has('analytics:read')) tasks.push(loadMetrics());
  if (adminPermissions.has('claims:read')) {
    document.querySelector('#claim-operations-section').hidden = false;
    document.querySelector('#ranking-contact-section').hidden = false;
    tasks.push(loadClaims(), loadRankingContacts());
  }
  if (adminPermissions.has('faults:read')) {
    document.querySelector('#fault-review-section').hidden = false;
    tasks.push(loadFaults());
  }
  document.querySelector('#btn-campaign-update').disabled = !adminPermissions.has('campaign:write');
  await Promise.all(tasks);
}

async function loadMetrics() {
  const params = new URLSearchParams(new FormData(document.querySelector('#analytics-filter')));
  for (const [key, value] of [...params]) if (!value) params.delete(key);
  if (params.has('from')) params.set('from', `${params.get('from')}T00:00:00+09:00`);
  if (params.has('to')) params.set('to', `${nextCalendarDate(params.get('to'))}T00:00:00+09:00`);
  const data = await adminRequest(`/api/admin/overview?${params}`);
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
  renderClaimSummary(data.claims || []);
  renderOperationalBreakdowns(data);
  ui.text(document.querySelector('#metrics-scope'), `${data.synthetic_only ? '합성 테스트 데이터만 표시' : '운영 데이터 포함'} · 필터 귀속 ${data.filter_attribution || '미제공'} · 환경 ${data.environment || '현재 환경'}`);
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
    { label: '점수 구간', value: (row) => row.score_from != null && row.score_to != null ? `${row.score_from}~${row.score_to}` : (row.bucket || row.range || row.score_bucket) },
    { label: '기록 수', value: (row) => row.games ?? row.count ?? row.sessions ?? row.event_count },
    { label: '고유 참가자', value: (row) => row.participants ?? row.unique_participants },
  ], rows, '조회된 점수 분포가 없습니다.');
}

function renderLeaderboard(rows) {
  renderTable(document.querySelector('#leaderboard-summary'), [
    { label: '현재 순위', value: (row) => row.rank },
    { label: '참가자', value: (row) => row.nickname || '익명 참가자' },
    { label: '최고점', value: (row) => row.best_score },
    { label: '동점', value: (row) => row.tied ? '예' : '아니오' },
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
      title: '초대 공유 수단과 확인 가능한 상태', rows: data.sharing?.invitation_sharing?.by_method_status || [], emptyText: '조회된 초대 공유 시도가 없습니다.',
      columns: sharingMethodColumns(),
    },
    {
      title: '초대 공유·전환 요약', rows: [
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
        { label: '콘텐츠', value: (row) => row.content || 'unknown' }, { label: '클릭', value: (row) => row.click_events },
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
  const data = await adminRequest('/api/admin/game-faults?status=PENDING');
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
  const data = await adminRequest('/api/admin/claims?limit=100');
  const list = document.querySelector('#admin-claims'); list.replaceChildren();
  if (!data.claims?.length) { const empty = document.createElement('p'); empty.textContent = '처리할 수령 건이 없습니다.'; list.appendChild(empty); return; }
  for (const claim of data.claims) list.appendChild(claimEditor(claim));
}

async function loadRankingContacts() {
  const data = await adminRequest('/api/admin/ranking-contacts');
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

function claimEditor(claim) {
  const item = document.createElement('article'); item.className = 'admin-claim-row';
  const info = document.createElement('div');
  const claimTitle = claim.claim_type === 'RANKING' ? '잠정 TOP3 연락 접수' : (claim.prize_name || '경품 수령 요청');
  const title = document.createElement('strong'); title.textContent = `${claimTitle} · ${CLAIM_STATUS_LABELS[claim.status] || claim.status}`;
  const meta = document.createElement('p'); meta.textContent = `담당 ${claim.assignee_display_name || claim.assignee_user_id || '미지정'} · 버전 ${claim.version}`;
  const privateInfo = document.createElement('p'); privateInfo.className = 'private-contact';
  privateInfo.textContent = `연락 정보: ${claim.recipient_name || '미접수'} · ${claim.contact || '-'} · ${claim.school || '-'} · ${claim.address || '-'}`;
  info.append(title, meta, privateInfo);
  if (claim.claim_type === 'RANKING') {
    const rankingRestriction = document.createElement('p'); rankingRestriction.className = 'status-note';
    rankingRestriction.textContent = '잠정 TOP3는 최종 수상 확정 전이므로 지급 완료로 변경할 수 없습니다.';
    info.appendChild(rankingRestriction);
  }
  const awaitingInformation = claim.status === 'AWAITING_INFORMATION';
  const needsContact = !claim.contact_submitted_at || !claim.recipient_name || !claim.contact;
  if (awaitingInformation || needsContact) {
    const note = document.createElement('p'); note.className = 'status-note';
    note.textContent = '참가자가 수령 정보를 제출한 뒤 확인·연락·지급 상태로 변경할 수 있습니다.';
    info.appendChild(note);
  }
  const state = document.createElement('select');
  for (const [status, label] of Object.entries(CLAIM_STATUS_LABELS)) {
    const option = document.createElement('option'); option.value = status; option.textContent = label; option.selected = claim.status === status;
    option.disabled = (claim.claim_type === 'RANKING' && status === 'PAID')
      || (awaitingInformation ? status !== 'AWAITING_INFORMATION' : status === 'AWAITING_INFORMATION');
    state.appendChild(option);
  }
  const assignee = document.createElement('input'); assignee.placeholder = '담당자 user id'; assignee.value = claim.assignee_user_id || ''; assignee.maxLength = 80;
  const reason = document.createElement('input'); reason.placeholder = '변경 사유'; reason.maxLength = 160;
  const external = document.createElement('label'); const externalBox = document.createElement('input'); externalBox.type = 'checkbox'; externalBox.checked = Boolean(claim.external_delivery); externalBox.disabled = awaitingInformation || needsContact; const externalText = document.createElement('span'); externalText.textContent = '외부 전달 완료'; external.append(externalBox, externalText);
  const save = document.createElement('button'); save.className = 'btn btn-primary btn-sm'; save.textContent = '상태 저장';
  if (!adminPermissions.has('claims:write') || awaitingInformation || needsContact) {
    state.disabled = true; assignee.disabled = true; reason.disabled = true; externalBox.disabled = true; save.disabled = true;
    save.textContent = awaitingInformation ? '수령 정보 입력 대기' : needsContact ? '수령 정보 확인 필요' : '읽기 전용';
  }
  save.onclick = async () => {
    save.disabled = true;
    try {
      await adminRequest(`/api/admin/claims/${encodeURIComponent(claim.id)}`, { method: 'PATCH', body: JSON.stringify({ status: state.value, assignee_user_id: assignee.value.trim() || null, reason: reason.value.trim(), external_delivery: externalBox.checked, expected_version: claim.version, event_id: api.createRequestId('evt') }) });
      ui.showToast('수령 상태를 저장했습니다.');
      await Promise.all([loadClaims(), ...(adminPermissions.has('analytics:read') ? [loadMetrics()] : [])]);
    } catch (error) { ui.showToast(error.message); save.disabled = false; }
  };
  item.append(info, state, assignee, reason, external, save); return item;
}

document.querySelector('#btn-admin-login').onclick = login;
document.querySelector('#admin-password').addEventListener('keydown', (event) => { if (event.key === 'Enter') login(); });
document.querySelector('#btn-admin-logout').onclick = () => { accessToken = ''; sessionClear(); window.location.reload(); };
document.querySelector('#analytics-filter').onsubmit = (event) => { event.preventDefault(); loadMetrics().catch((error) => ui.showToast(error.message)); };
document.querySelector('#btn-refresh-claims').onclick = () => loadClaims().catch((error) => ui.showToast(error.message));
document.querySelector('#btn-refresh-ranking-contacts').onclick = () => loadRankingContacts().catch((error) => ui.showToast(error.message));
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

if (accessToken) showAdmin().catch(() => { accessToken = ''; sessionClear(); });
