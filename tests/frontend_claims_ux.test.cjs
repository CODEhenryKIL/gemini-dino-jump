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
    this.textContent = '';
    this.disabled = false;
    this.onclick = null;
  }
  setAttribute() {}
  append(...children) { this.children.push(...children); }
  appendChild(child) { this.children.push(child); return child; }
}

function descendants(node, tag) {
  return (node.children || []).flatMap((child) => [
    ...(child.tag === tag ? [child] : []),
    ...descendants(child, tag),
  ]);
}

function loadPrize(prepareResultReferralShare) {
  const source = fs.readFileSync(path.join(root, 'public/js/views/prize_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const PrizeView =', 'globalThis.PrizeView =');
  const context = {
    console,
    document: { createElement: (tag) => new Element(tag) },
    api: {},
    analytics: { track() {} },
    ui: { showToast() {} },
    prepareResultReferralShare,
  };
  context.globalThis = context;
  vm.runInNewContext(fs.readFileSync(path.join(root, 'public/js/benefit_retry.js'), 'utf8').replace(/export function /g, 'function '), context);
  vm.runInNewContext(source, context, { filename: 'prize_view.js' });
  return context.PrizeView;
}

test('Gemini benefit card shares for a draw credit and then exposes the direct next draw action', async () => {
  let options;
  let shares = 0;
  const view = loadPrize(async (_router, received) => {
    options = received;
    return { share: async () => { shares += 1; return { method: 'kakao', status: 'pending', shareId: 'draw-share-1' }; } };
  });
  const routes = [];
  const router = { state: {}, isCurrent: () => true, navigate: (route) => routes.push(route) };
  const card = view.benefitCard({ used_count: 1, max_count: 10, available_credits: 0 }, router, 4);
  await new Promise(setImmediate);
  const [benefit, again, game, share] = descendants(card, 'button');
  assert.equal(options.kind, 'benefit_retry');
  assert.equal(benefit.textContent, '혜택 보러 가기');
  assert.equal(share.textContent, '친구에게 공유하고\n다시 도전하기');
  await share.onclick();
  assert.equal(shares, 1);
  options.onReceipt({
    status: 'confirmed', reward_type: 'BOTH', reward_status: 'granted', rewards: { game: { quantity: 1 }, draw: { quantity: 1 } }, tickets: { invitation: 1, available_total: 1 },
    draw_state: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1 },
  });
  assert.equal(router.state.draw.available_credits, 1);
  assert.equal(again.hidden, false);
  assert.equal(game.hidden, false);
  again.onclick();
  assert.deepEqual(routes, ['draw']);
});

test('Gemini benefit card hides sharing when both reward limits apply', () => {
  let preparations = 0;
  const view = loadPrize(async () => { preparations += 1; return { share: async () => ({}) }; });
  const card = view.benefitCard({ used_count: 10, max_count: 10, available_credits: 0 }, { state: { tickets: { invitation: 3 } }, isCurrent: () => true }, 1);
  const share = descendants(card, 'button')[3];
  assert.equal(preparations, 0);
  assert.equal(share.hidden, true);
});

test('an actual prize saves and submits contact directly without a Kakao share gate', async () => {
  let modal; let saved; let submitted; const routes = [];
  const view = loadPrize(async () => { throw new Error('claim submission must not prepare sharing'); });
  const originalUi = view;
  const source = fs.readFileSync(path.join(root, 'public/js/views/prize_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const PrizeView =', 'globalThis.PrizeView =');
  const context = {
    console,
    document: { createElement: (tag) => new Element(tag) },
    api: {
      getClaimDraft: async () => ({ draft: {} }),
      saveClaimDraft: async (_id, payload) => { saved = payload; },
      submitClaim: async (_id, payload) => { submitted = payload; return { status: 'INFORMATION_RECEIVED' }; },
    },
    analytics: { track() {} },
    ui: {
      showToast() {}, showModal(options) { modal = options; },
      formField(_label, _type, name) { const label = new Element('label'); const input = new Element('input'); input.name = name; label.append(input); return { label, input }; },
    },
    prepareResultReferralShare: async () => { throw new Error('must not share'); },
    benefitRetryAvailability() {}, benefitRewardMessage() {}, showGameGuide() {},
  };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: 'prize_view.js' });
  const router = { state: {}, isCurrent: () => true, navigate: (route) => routes.push(route), announceStateChange() {} };
  await context.PrizeView.directClaimModal({ id: 'claim-direct', claim_type: 'DRAW', prize_name: '테스트 커피', category: 'COUPON' }, router, 1);
  const inputs = descendants(modal.content, 'input');
  for (const input of inputs) {
    if (input.name === 'name') input.value = '홍길동';
    if (input.name === 'contact') input.value = '01012345678';
    if (input.name === 'school') input.value = '테스트대';
    if (!input.name) input.checked = true;
  }
  assert.equal(modal.confirmText, '저장하고 혜택 보기');
  assert.equal(typeof modal.content.onsubmit, 'function', 'Enter submission is intercepted instead of exposing PII in the URL');
  assert.equal(await modal.onConfirm(), true);
  assert.equal(saved.notice_version, 'claim-contact-v1');
  assert.deepEqual(JSON.parse(JSON.stringify(submitted)), {});
  assert.deepEqual(routes, ['benefit']);
  assert.ok(originalUi, 'existing benefit coverage remains loaded');
});
