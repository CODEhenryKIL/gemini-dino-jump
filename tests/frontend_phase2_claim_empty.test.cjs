const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function element(tag = 'div') {
  return {
    tag, className: '', textContent: '', children: [],
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
  };
}

function harness(status) {
  const events = [];
  const routes = [];
  const context = {
    api: {}, ui: {},
    analytics: { track: (name, dimensions) => events.push({ name, ...dimensions }) },
    document: { createElement: (tag) => element(tag) },
    console,
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/views/prize_view.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const PrizeView =', 'globalThis.PrizeView =');
  vm.runInNewContext(source, context, { filename: 'prize_view.js' });
  const container = element();
  const router = { state: { draw: { status } }, navigate: (route) => routes.push(route) };
  context.PrizeView.renderEmpty(container, router);
  const card = container.children[0];
  return { title: card.children[0], button: card.children[1], detail: card.children[2], router, events, routes };
}

test('empty claims send a locked participant home to finish the first game without draw tracking', () => {
  const h = harness('LOCKED');
  assert.match(h.title.textContent.normalize('NFD'), /복주머니가 아직 잠겨/);
  assert.match(h.detail.textContent.normalize('NFD'), /정상 검증된 게임/);
  assert.equal(h.button.textContent.normalize('NFD'), '홈에서 게임 시작하기');
  h.button.onclick();
  assert.deepEqual(h.routes, ['home']);
  assert.deepEqual(h.events, []);
});

test('empty claims distinguish available and drawn pouch actions', () => {
  const available = harness('AVAILABLE');
  assert.equal(available.button.textContent.normalize('NFD'), '복주머니 열기');
  available.button.onclick();
  assert.deepEqual(available.routes, ['draw']);
  assert.deepEqual(available.events, [{ name: 'draw_cta_clicked', source: 'claims', draw_status: 'AVAILABLE' }]);

  const drawn = harness('DRAWN');
  assert.equal(drawn.button.textContent.normalize('NFD'), '내 복주머니 결과 보기');
  drawn.button.onclick();
  assert.deepEqual(drawn.routes, ['draw']);
  assert.deepEqual(drawn.events, [{ name: 'draw_cta_clicked', source: 'claims', draw_status: 'DRAWN' }]);
});

test('empty claims recheck the latest draw state at click time', () => {
  const becameLocked = harness('AVAILABLE');
  becameLocked.router.state.draw.status = 'LOCKED';
  becameLocked.button.onclick();
  assert.deepEqual(becameLocked.routes, ['home']);
  assert.deepEqual(becameLocked.events, []);

  const becameAvailable = harness('LOCKED');
  becameAvailable.router.state.draw.status = 'AVAILABLE';
  becameAvailable.button.onclick();
  assert.deepEqual(becameAvailable.routes, ['draw']);
  assert.deepEqual(becameAvailable.events, [{ name: 'draw_cta_clicked', source: 'claims', draw_status: 'AVAILABLE' }]);
});
