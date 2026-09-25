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
  const context = { document, sessionStorage: { getItem: () => '' }, api: {}, ui: {} };
  const read = (file) => fs.readFileSync(path.join(__dirname, '..', file), 'utf8').replace(/^import .*;\n/gm, '');
  vm.runInNewContext(`${read('public/js/admin.js')}\n globalThis.admin = { claimEditor, renderOperationalBreakdowns, setPermissions: (values) => { adminPermissions = new Set(values); } };`, context);
  vm.runInNewContext(`${read('public/js/views/prize_view.js').replace('export const PrizeView', 'const PrizeView')}\n globalThis.prize = PrizeView;`, context);
  return { ...context, nodes };
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
  const options = descendants(editor, 'option');
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
    attempt_events: count, copy_success_events: count, linked_participants: participants, unlinked_events: 0, actual_delivery: 'unknown',
    by_method_status: [{ share_method: 'copy', status: 'copied', events: count, linked_participants: participants, unlinked_events: 0 }],
  });
  admin.renderOperationalBreakdowns({ sharing: {
    ...summary(99, 99), invitation_sharing: summary(2, 1), gemini_sharing: summary(7, 3), unknown_sharing: summary(5, 2),
  } });
  const invite = Object.fromEntries(groupRows(nodes.get('#invitation-summary'), '초대 공유·전환 요약'));
  const gemini = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), 'Gemini 링크 복사·공유 요약'));
  const unknown = Object.fromEntries(groupRows(nodes.get('#gemini-summary'), '목적 미확인 공유 (초대·Gemini 합계 제외)'));
  assert.equal(invite['복사 성공'], '2');
  assert.equal(invite['공유 고유 참가자'], '1');
  assert.equal(gemini['복사 성공'], '7');
  assert.equal(gemini['공유 고유 참가자'], '3');
  assert.equal(unknown['복사 성공'], '5');
  assert.equal(gemini['실제 전송 완료'], 'unknown');
  assert.deepEqual(groupRows(nodes.get('#invitation-summary'), '초대 공유 수단과 확인 가능한 상태'), [['copy', 'copied', '2', '1', '0']]);
  assert.deepEqual(groupRows(nodes.get('#gemini-summary'), 'Gemini 공유 수단과 확인 가능한 상태'), [['copy', 'copied', '7', '3', '0']]);
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
