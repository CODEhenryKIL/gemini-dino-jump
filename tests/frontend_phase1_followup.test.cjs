const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.disabled = false; this.value = ''; this._text = ''; }
  set textContent(value) { this._text = String(value); this.children = []; }
  get textContent() { return this._text + this.children.map((child) => child.textContent).join(''); }
  append(...nodes) { this.children.push(...nodes); }
  appendChild(node) { this.append(node); return node; }
  replaceChildren(...nodes) { this._text = ''; this.children = nodes; }
  addEventListener() {}
}

function loadUi() {
  const nodes = new Map();
  const document = {
    createElement: (tag) => new Element(tag),
    querySelector(selector) {
      if (!nodes.has(selector)) nodes.set(selector, new Element('div'));
      return nodes.get(selector);
    },
  };
  const toasts = [];
  const context = { document, sessionStorage: { getItem: () => '' }, api: { createRequestId: () => 'test-request' }, ui: { showToast: (message) => toasts.push(message) } };
  const read = (file) => fs.readFileSync(path.join(__dirname, '..', file), 'utf8').replace(/^import .*;\n/gm, '');
  vm.runInNewContext(`${read('public/js/admin.js')}\n globalThis.admin = { claimEditor, renderDrawSummary, renderOperationalBreakdowns, setPermissions: (values) => { adminPermissions = new Set(values); }, setRequest: (handler) => { adminRequest = handler; } };`, context);
  vm.runInNewContext(`${read('public/js/views/prize_view.js').replace('export const PrizeView', 'const PrizeView')}\n globalThis.prize = PrizeView;`, context);
  return { ...context, nodes, toasts };
}

function descendants(node, tag) {
  return node.children.flatMap((child) => [...(child.tag === tag ? [child] : []), ...descendants(child, tag)]);
}

function groupRows(container, title) {
  const index = container.children.findIndex((child) => child.tag === 'h3' && child.textContent === title);
  assert.notEqual(index, -1, `missing group: ${title}`);
  return descendants(container.children[index + 1], 'tbody')
    .flatMap((body) => body.children.map((row) => row.children.map((cell) => cell.textContent)));
}

test('unsubmitted winner sees information waiting and the administrator cannot process it', () => {
  const { admin, prize } = loadUi();
  const claim = { id: 'claim-1', claim_type: 'DRAW', status: 'AWAITING_INFORMATION', contact_submitted: false, version: 1 };
  const card = prize.claimCard(claim, {});
  assert.equal(descendants(card, 'span')[0].textContent, '정보 입력 대기');
  assert.equal(descendants(card, 'button').length, 1);
  assert.match(descendants(card, 'button')[0].textContent, /수령 정보 입력/);
  admin.setPermissions(['claims:write']);
  const editor = admin.claimEditor(claim);
  assert.match(editor.textContent, /참가자가 수령 정보를 제출한 뒤/);
  assert.equal(descendants(editor, 'select')[0].disabled, true);
  assert.equal(descendants(editor, 'button')[0].disabled, true);
  assert.ok(descendants(editor, 'input').every((input) => input.disabled));
  const options = descendants(descendants(editor, 'select')[0], 'option');
  assert.equal(options.find((option) => option.selected).value, 'AWAITING_INFORMATION');
  assert.ok(options.filter((option) => option.value !== 'AWAITING_INFORMATION').every((option) => option.disabled));
});

test('submitted claims remove the entry form and preserve ranking and read-only restrictions', () => {
  const { admin, prize } = loadUi();
  const claim = { claim_type: 'RANKING', status: 'INFORMATION_RECEIVED', contact_submitted: true, contact_submitted_at: '2026-09-25T00:00:00Z', recipient_name: 'TEST', contact: '01000000000', version: 2 };
  const card = prize.claimCard(claim, {});
  assert.equal(descendants(card, 'span')[0].textContent, '정보 접수');
  assert.equal(descendants(card, 'button').length, 0);
  admin.setPermissions(['claims:write']);
  const editor = admin.claimEditor(claim);
  const options = descendants(editor, 'option');
  assert.equal(options.find((option) => option.value === 'AWAITING_INFORMATION').disabled, true);
  assert.equal(options.find((option) => option.value === 'PAID').disabled, true);
  assert.equal(options.find((option) => option.value === 'PENDING_REVIEW').disabled, false);
  assert.equal(descendants(editor, 'button')[0].disabled, false);
  admin.setPermissions(['claims:read']);
  assert.equal(descendants(admin.claimEditor(claim), 'button')[0].disabled, true);
});

test('legacy claim without real contact cannot be processed even if its status progressed', () => {
  const { admin } = loadUi();
  admin.setPermissions(['claims:write']);
  for (const claim of [
    { status: 'PENDING_REVIEW', contact_submitted_at: null },
    { status: 'CONTACTED', contact_submitted_at: '2026-09-25T00:00:00Z' },
  ]) {
    const editor = admin.claimEditor({ claim_type: 'DRAW', version: 3, ...claim });
    assert.equal(descendants(editor, 'button')[0].disabled, true);
    assert.equal(descendants(editor, 'select')[0].disabled, true);
    assert.ok(descendants(editor, 'input').every((input) => input.disabled));
  }
});

test('administrator must confirm eligibility, delivery and evidence before recording payment', async () => {
  const { admin, toasts } = loadUi();
  admin.setPermissions(['claims:write']);
  const requests = [];
  admin.setRequest(async (url, options = {}) => { requests.push({ url, options }); return { claims: [] }; });
  const editor = admin.claimEditor({ id: 'payment-1', claim_type: 'DRAW', status: 'CONTACTED', version: 7,
    contact_submitted_at: '2026-09-29T00:00:00Z', recipient_name: 'TEST', contact: '01000000000' });
  const [state, verification] = descendants(editor, 'select');
  const reference = descendants(editor, 'input').find((node) => node.ariaLabel === '자격 확인 참조');
  const reason = descendants(editor, 'input').find((node) => node.placeholder === '변경 사유');
  const external = descendants(editor, 'input').find((node) => node.type === 'checkbox');
  const save = descendants(editor, 'button')[0];
  state.value = 'PAID'; state.onchange();
  await save.onclick();
  assert.match(toasts.at(-1), /자격 확인을 완료/);
  verification.value = 'VERIFIED';
  await save.onclick();
  assert.match(toasts.at(-1), /확인 참조/);
  reference.value = 'TEST_REF_student';
  await save.onclick();
  assert.match(toasts.at(-1), /외부 전달 완료/);
  external.checked = true;
  await save.onclick();
  assert.match(toasts.at(-1), /전달 확인 사유/);
  assert.equal(requests.length, 0);
  assert.equal(save.disabled, false);
  reason.value = 'TEST_DELIVERY_CONFIRMED';
  await save.onclick();
  const mutation = requests.filter((request) => request.options.method === 'PATCH');
  assert.equal(mutation.length, 1);
  const body = JSON.parse(mutation[0].options.body);
  assert.equal(body.status, 'PAID');
  assert.equal(body.verification_status, 'VERIFIED');
  assert.equal(body.verification_reference, 'TEST_REF_student');
  assert.equal(body.external_delivery, true);
  assert.equal(body.reason, 'TEST_DELIVERY_CONFIRMED');
  assert.equal(body.expected_version, 7);
});

test('paid evidence cannot be unchecked and verification remains disabled for read-only administrators', () => {
  const { admin } = loadUi();
  const claim = { claim_type: 'DRAW', status: 'PAID', version: 8, contact_submitted_at: '2026-09-29T00:00:00Z',
    recipient_name: 'TEST', contact: '01000000000', verification_status: 'VERIFIED', verification_reference: 'TEST_REF_verified', external_delivery: true };
  admin.setPermissions(['claims:write']);
  const paid = admin.claimEditor(claim);
  assert.equal(descendants(paid, 'select')[1].disabled, true);
  assert.equal(descendants(paid, 'input').find((node) => node.ariaLabel === '자격 확인 참조').disabled, true);
  assert.equal(descendants(paid, 'input').find((node) => node.type === 'checkbox').disabled, true);
  admin.setPermissions(['claims:read']);
  const readonly = admin.claimEditor({ ...claim, status: 'CONTACTED' });
  assert.ok(descendants(readonly, 'select').every((node) => node.disabled));
  assert.ok(descendants(readonly, 'input').every((node) => node.disabled));
});

test('claim forms are not offered for finalized claims with missing legacy contact information', () => {
  const { prize } = loadUi();
  for (const status of ['PAID', 'INELIGIBLE']) {
    const card = prize.claimCard({ status, claim_type: 'DRAW', contact_submitted: false }, {});
    assert.equal(descendants(card, 'button').length, 0, status);
  }
});

test('legacy nonterminal claims can submit missing contact without showing an incorrect new status', () => {
  const { prize } = loadUi();
  const opened = [];
  prize.claimModal = (claim) => opened.push(claim);
  for (const status of ['CONTACTED', 'ON_HOLD', 'NO_RESPONSE']) {
    const claim = { id: `legacy-${status}`, status, claim_type: 'DRAW', contact_submitted: false };
    const card = prize.claimCard(claim, {});
    const button = descendants(card, 'button')[0];
    assert.ok(button, `${status} requires a recovery form`);
    button.onclick();
    assert.equal(opened.at(-1), claim);
    assert.notEqual(descendants(card, 'span')[0].textContent, '정보 입력 대기');
  }
});

test('dashboard renders invitation, Gemini and unknown shares from separate purpose totals', () => {
  const { admin, nodes } = loadUi();
  const summary = (count, participants) => ({
    attempt_events: count, copy_success_events: count, linked_participants: participants, unlinked_events: 0, actual_delivery: 'unknown', server_confirmed_intents: count - 1, server_confirmed_participants: Math.max(0, participants - 1),
    by_method_status: [{ share_method: 'copy', status: 'copied', events: count, linked_participants: participants, unlinked_events: 0 }],
  });
  admin.renderOperationalBreakdowns({ sharing: {
    ...summary(99, 99), invitation_sharing: summary(2, 1), claim_share_sharing: { ...summary(4, 2), by_method_status: [{ share_method: 'claim-kakao', status: 'confirmed', events: 4, linked_participants: 2, unlinked_events: 0 }] }, gemini_sharing: summary(7, 3), unknown_sharing: summary(5, 2),
  } });
  const invite = Object.fromEntries(groupRows(nodes.get('#invitation-summary'), '게임 재도전 공유·전환 요약'));
  const gemini = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), 'Gemini 링크 복사·공유 요약'));
  const unknown = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), '목적 미확인 공유 (초대·Gemini 합계 제외)'));
  assert.equal(invite['복사 성공'], '2');
  assert.equal(invite['공유 고유 참가자'], '1');
  assert.equal(gemini['복사 성공'], '7');
  assert.equal(gemini['공유 고유 참가자'], '3');
  assert.equal(unknown['복사 성공'], '5');
  assert.equal(gemini['실제 전송 완료'], 'unknown');
  assert.deepEqual(groupRows(nodes.get('#invitation-summary'), '게임 재도전 공유 수단과 확인 가능한 상태'), [['copy', 'copied', '2', '1', '0']]);
  assert.deepEqual(groupRows(nodes.get('#gemini-summary'), 'Gemini 공유 수단과 확인 가능한 상태'), [['copy', 'copied', '7', '3', '0']]);
  assert.equal(invite['카카오 인증 전송'], '1');
  assert.equal(invite['카카오 인증 전송 참가자'], '0');
  assert.match(nodes.get('#invitation-summary').textContent, /claim-kakao/);
});

test('dashboard keeps open observations out of final nonclick counts and handles no closed cohort', () => {
  const { admin, nodes } = loadUi();
  admin.renderOperationalBreakdowns({ gemini_ctr: { numerator: 2, denominator: 3, rate: 2 / 3, pending_participants: 4, pending_exposure_events: 6 } });
  let rows = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), 'Gemini 전환'));
  assert.equal(rows['관찰 완료 후 미클릭 참가자'], '1');
  assert.equal(rows['관찰 중 참가자 (확정 집계 제외)'], '4');
  assert.equal(rows['관찰 완료 CTR'], '66.7%');
  admin.renderOperationalBreakdowns({ gemini_ctr: { numerator: 0, denominator: 0, rate: null, pending_participants: 4, pending_exposure_events: 6 } });
  rows = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), 'Gemini 전환'));
  assert.equal(rows['관찰 완료 후 미클릭 참가자'], '0');
  assert.equal(rows['관찰 완료 CTR'], '계산 대상 없음');
  assert.equal(rows['관찰 중 참가자 (확정 집계 제외)'], '4');
});

test('dashboard exposes draw outcomes and credits and stays safe for a legacy response', () => {
  const { admin, nodes } = loadUi();
  admin.renderDrawSummary({
    total_draws: 12, actual_prize_draws: 2, actual_prize_winners: 2, benefit_results: 10, paid_prizes: 1,
  }, [{ source_type: 'SHARE_GRANT', events: 7, participants: 5, net_credits: 7 }]);
  const summary = descendants(nodes.get('#draw-summary'), 'tbody')[0].children
    .map((row) => row.children.map((cell) => cell.textContent));
  assert.deepEqual(summary, [
    ['총 추첨 횟수', '12'], ['실제 상품 당첨', '2'], ['실제 상품 당첨자', '2'],
    ['Gemini 혜택 결과', '10'], ['실제 지급 완료', '1'],
  ]);
  assert.deepEqual(descendants(nodes.get('#draw-credit-ledger'), 'tbody')[0].children
    .map((row) => row.children.map((cell) => cell.textContent)), [['SHARE_GRANT', '7', '5', '7']]);
  assert.doesNotThrow(() => admin.renderDrawSummary(undefined, undefined));
  assert.match(nodes.get('#draw-summary').textContent, /총 추첨 횟수0/);
});

test('claims load ordered draw history and links an actual prize claim to its round', async () => {
  const { api, prize } = loadUi();
  api.getClaims = async () => ({ claims: [{ id: 'claim-2', claim_type: 'DRAW', prize_name: '헤드셋', status: 'PAID', contact_submitted: true }] });
  api.getDraw = async () => ({ draws: [
    { draw_id: 'draw-1', round_number: 1, outcome_kind: 'BENEFIT', scratch_completed: true, prize: {} },
    { draw_id: 'draw-2', round_number: 2, outcome_kind: 'PRIZE', is_actual_prize: true, scratch_completed: true, claim_id: 'claim-2', prize: { name: '헤드셋' } },
  ] });
  const container = new Element('main');
  await prize.render(container, { isCurrent: () => true, state: { draw: { status: 'WON' } } }, 1);
  const history = container.children.find((child) => child.className === 'card draw-history-card');
  assert.ok(history);
  const rows = descendants(history, 'li').map((row) => row.children.map((child) => child.textContent));
  assert.deepEqual(rows, [['2회차', '헤드셋', '확인 완료'], ['1회차', 'Gemini 혜택', '확인 완료']]);
  const claimCard = container.children.find((child) => child.className === 'card claim-card');
  assert.match(claimCard.textContent, /복주머니 2회차 경품/);
});

test('claims history does not expose an unrevealed result', () => {
  const { prize } = loadUi();
  const history = prize.drawHistory([{ round_number: 3, outcome_kind: 'PRIZE', scratch_completed: false, revealed: false, prize: { name: '삼텐바이미' } }]);
  assert.match(history.textContent, /3회차결과 확인 전확인 전/);
  assert.doesNotMatch(history.textContent, /삼텐바이미/);
});
