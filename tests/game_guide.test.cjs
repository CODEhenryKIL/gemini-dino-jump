const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function harness(getLeaderboard = async () => ({ leaderboard: [], me: {} })) {
  class Node {
    constructor(tag = 'div') {
      this.tagName = tag.toUpperCase(); this.children = []; this.attrs = {}; this.className = '';
      this.textContent = ''; this.hidden = false; this.disabled = false; this.isConnected = true;
      this.listeners = {}; this.classList = { add: (...names) => { this.addedClasses = names; } };
    }
    append(...nodes) { this.children.push(...nodes); }
    appendChild(node) { this.children.push(node); return node; }
    replaceChildren(...nodes) { this.children = nodes; }
    setAttribute(name, value) { this.attrs[name] = value; }
    addEventListener(name, listener) { this.listeners[name] = listener; }
    focus() { this.focused = true; }
    before(node) { this.beforeNode = node; }
  }

  const content = new Node();
  const title = new Node('h4');
  const rankHost = new Node();
  Object.defineProperty(content, 'innerHTML', {
    get: () => content._html || '',
    set: (value) => { content._html = value; rankHost.children = []; },
  });
  content.querySelector = (selector) => {
    if (selector === '.guide-slide-title') return title;
    if (selector === '.guide-rank-content' && /guide-rank-content/.test(content.innerHTML)) return rankHost;
    return null;
  };

  const confirm = new Node('button');
  const close = new Node('button');
  const card = new Node(); card.scrollTop = 0;
  card.insertBefore = (node) => { card.inserted = node; };
  const overlay = new Node();
  overlay.querySelector = (selector) => ({
    '.modal-actions .btn-primary': confirm,
    '.modal-card': card,
    '.modal-actions .btn-secondary': close,
  }[selector]);

  let modal; let hidden = 0;
  const writes = [];
  const navigations = [];
  const document = {
    createElement(tag) { return tag === 'div' && !this.createdContent ? (this.createdContent = content) : new Node(tag); },
    getElementById(id) { return id === 'common-modal-overlay' && overlay.isConnected ? overlay : null; },
  };
  const ui = {
    showModal(options) {
      modal = options;
      close.onclick = () => { if (options.onCancel) options.onCancel(); this.hideModal(); };
    },
    hideModal() { hidden++; content.isConnected = false; overlay.isConnected = false; },
  };
  const context = {
    api: { getLeaderboard }, ui, document, Node,
    localStorage: { setItem: (key, value) => writes.push([key, value]) },
    Intl, Number, console,
  };
  const source = fs.readFileSync(path.join(root, 'public/js/components/game_guide.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export function showGameGuide', 'function showGameGuide')
    .concat('\nglobalThis.showGameGuide = showGameGuide;');
  vm.runInNewContext(source, context, { filename: 'game_guide.js' });
  const router = { navigate: (view) => navigations.push(view) };
  context.showGameGuide(router, true);
  return { content, title, rankHost, confirm, close, card, overlay, modal: () => modal, writes, navigations, hidden: () => hidden };
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

test('guide uses concise touch instructions, previous navigation, and a top X close', () => {
  const h = harness();
  assert.match(h.content.innerHTML, /화면을 터치하면 점프!/);
  assert.doesNotMatch(h.content.innerHTML, /PC|키보드|스페이스/);
  assert.equal(h.close.textContent, '×');
  assert.equal(h.close.attrs['aria-label'], '가이드 닫기');
  assert.equal(h.card.inserted, h.close);
  assert.equal(h.confirm.beforeNode.textContent, '이전');
  assert.equal(h.confirm.beforeNode.disabled, true);
  h.modal().onConfirm();
  assert.match(h.content.innerHTML, /웃음 코인을 먹으면 \+10점/);
  assert.equal(h.confirm.beforeNode.disabled, false);
  h.confirm.beforeNode.onclick();
  assert.match(h.content.innerHTML, /화면을 터치하면 점프!/);
  h.close.onclick();
  assert.deepEqual(h.navigations, []);
  assert.deepEqual(h.writes, []);
});

test('skip records completion and starts the game exactly once', () => {
  const h = harness();
  const skip = h.card.children.at(-1);
  assert.equal(skip.textContent, '건너뛰고 게임 시작');
  skip.onclick();
  assert.deepEqual(h.writes, [['gemini_dino_guide_seen', 'true']]);
  assert.deepEqual(h.navigations, ['game']);
  assert.equal(h.hidden(), 1);
});

test('final slide shows rewards and safely renders live ranking data', async () => {
  const nickname = '<img src=x onerror=alert(1)>';
  const h = harness(async () => ({
    leaderboard: [{ rank: 1, nickname, score: 12345, tied: false, is_me: true }],
    me: { rank: 1, best_score: 12345 },
  }));
  h.modal().onConfirm(); h.modal().onConfirm(); h.modal().onConfirm();
  assert.match(h.content.innerHTML, /1위[\s\S]*5만원[\s\S]*2위[\s\S]*3만원[\s\S]*3위[\s\S]*1만원/);
  assert.match(h.rankHost.children[0].textContent, /불러오는 중/);
  await settle();
  const list = h.rankHost.children[0];
  assert.equal(list.children[0].children[1].textContent, nickname);
  assert.doesNotMatch(h.content.innerHTML, /onerror/);
  assert.match(h.rankHost.children[1].textContent, /내 순위 1위 · 최고 12,345점/);
});

test('ranking failure offers retry, and closing during a pending request is safe', async () => {
  const failed = harness(async () => { throw new Error('offline'); });
  failed.modal().onConfirm(); failed.modal().onConfirm(); failed.modal().onConfirm();
  await settle();
  assert.match(failed.rankHost.children[0].textContent, /불러오지 못했어요/);
  assert.equal(failed.rankHost.children[1].textContent, '다시 불러오기');

  let release;
  const pending = harness(() => new Promise((resolve) => { release = resolve; }));
  pending.modal().onConfirm(); pending.modal().onConfirm(); pending.modal().onConfirm();
  pending.close.onclick();
  release({ leaderboard: [{ rank: 1, nickname: '늦은 응답', score: 1 }], me: {} });
  await settle();
  assert.deepEqual(pending.navigations, []);
  assert.deepEqual(pending.writes, []);
});
