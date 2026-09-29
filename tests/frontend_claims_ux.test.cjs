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
  const [benefit, share] = descendants(card, 'button');
  assert.equal(options.kind, 'draw_retry');
  assert.equal(benefit.textContent, '혜택 보러 가기');
  assert.equal(share.textContent, '친구에게 공유하고\n한 번 더 뽑기');
  await share.onclick();
  assert.equal(shares, 1);
  options.onReceipt({
    status: 'confirmed', reward_type: 'DRAW', reward_status: 'granted',
    draw_state: { status: 'AVAILABLE', used_count: 1, max_count: 10, available_credits: 1 },
  });
  assert.equal(router.state.draw.available_credits, 1);
  assert.equal(share.textContent, '한 번 더 뽑기');
  share.onclick();
  assert.deepEqual(routes, ['draw']);
});

test('Gemini benefit card respects the ten-draw limit and prepares no extra reward share', () => {
  let preparations = 0;
  const view = loadPrize(async () => { preparations += 1; return { share: async () => ({}) }; });
  const card = view.benefitCard({ used_count: 10, max_count: 10, available_credits: 0 }, { isCurrent: () => true }, 1);
  const share = descendants(card, 'button')[1];
  assert.equal(preparations, 0);
  assert.equal(share.textContent, '경품 뽑기 10회 완료');
  assert.equal(share.disabled, true);
});
