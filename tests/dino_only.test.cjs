const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function loadHome(guideSeen = false, tickets = { initial: 1, invitation: 0, available_total: 1 }, campaignStatus = "ACTIVE") {
  const source = fs.readFileSync(path.join(root, 'public/js/views/home.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const HomeView', 'const HomeView');
  let modal;
  const guides = [];
  const navigations = [];
  const context = {
    showGameGuide: (router, autoStart) => guides.push({ router, autoStart }),
    analytics: { track() {} },
    window: { location: { hostname: 'localhost', protocol: 'http:' } },
    localStorage: {
      getItem: () => guideSeen ? 'true' : null,
      setItem: () => {},
    },
  };
  vm.runInNewContext(`${source}\nglobalThis.home = HomeView;`, context);

  const elements = new Map();
  const container = {
    innerHTML: '',
    querySelector(selector) {
      const id = selector.slice(1);
      if (!this.innerHTML.includes(`id="${id}"`)) return null;
      if (!elements.has(selector)) elements.set(selector, { onclick: null });
      return elements.get(selector);
    },
  };
  const router = {
    state: { tickets, bestScore: 42 },
    config: { campaign: { status: campaignStatus } },
    navigate: (view) => navigations.push(view),
  };
  context.home.render(container, router);
  return { container, elements, navigations, guides, getModal: () => modal };
}

test('home presents only Dino Jump and starts it after the guide', () => {
  const page = loadHome();
  assert.match(page.container.innerHTML, />게임 시작<\/button>/);
  assert.match(page.container.innerHTML.replace(/<[^>]+>/g, ''), /Google AI[\s\S]*공룡 게임/);
  assert.match(page.container.innerHTML, /추억의 공룡 게임 한 판 하고 삼텐바이미 받자!/);
  assert.doesNotMatch(page.container.innerHTML, /home-team-logo|home-draw-state|복주머니와 재도전|지금 사용 가능/);
  assert.doesNotMatch(page.container.innerHTML, /게이트 러너|종목 선택/);
  const start = page.elements.get('#btn-start-jump');
  assert.ok(start, 'a direct Dino Jump start button is present');
  start.onclick();
  assert.equal(page.guides.length, 1, 'first play opens the game guide');
  assert.equal(page.guides[0].autoStart, true);
  assert.deepEqual(page.navigations, []);
});

test('returning players see the tutorial on every new game', () => {
  const page = loadHome(true);
  page.elements.get('#btn-start-jump').onclick();
  assert.deepEqual(page.navigations, []);
  assert.equal(page.guides.length, 1);
  page.elements.get('#btn-start-jump').onclick();
  assert.equal(page.guides.length, 2);
  assert.doesNotMatch(page.container.innerHTML, /btn-how-to-play|조작 방법과 규칙/);
});

test('Dino Jump runtime has no Gate Runner navigation or port dependency', () => {
  const runtimeFiles = [
    'public/js/app.js',
    'public/js/views/home.js',
  ];
  for (const file of runtimeFiles) {
    const source = fs.readFileSync(path.join(root, file), 'utf8');
    assert.equal(/gate[_-]runner|GameChoiceModal|3001/i.test(source), false, file);
  }
  const server = fs.readFileSync(path.join(root, 'server/app.py'), 'utf8');
  assert.equal(/3001/.test(server), false);
  assert.match(server, /self\.send_header\('Location', '\/'\)/);
  const config = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
  assert.equal(config.rewrites.some(({ source }) => /gate[_-]runner/i.test(source)), false);
  assert.deepEqual(config.redirects.map(({ destination }) => destination), ['/', '/', '/']);
  assert.equal(fs.existsSync(path.join(root, 'public/gate_runner.html')), false);
});

 test('zero-ticket CTA opens invite, while unlimited starts a game and pause still blocks', () => {
  for (const flag of [false, undefined, 'true', true]) {
    const page = loadHome(true, { initial: 0, invitation: 0, available_total: 0, unlimited_play: flag });
    const button = page.elements.get('#btn-start-jump');
    assert.equal(button.disabled, false);
    button.onclick();
    assert.deepEqual(page.navigations, flag === true ? [] : ['invite']);
    assert.equal(page.guides.length, flag === true ? 1 : 0);
    assert.equal(page.elements.get('#home-basic-ticket').textContent, flag === true ? '무제한' : '0장');
    if (flag !== true) assert.match(button.textContent, /친구에게 공유하고 게임권 받기/);
  }
  const paused = loadHome(true, { unlimited_play: true, available_total: 0 }, 'PAUSED');
  paused.elements.get('#btn-start-jump').onclick();
  assert.deepEqual(paused.navigations, []);
 });
