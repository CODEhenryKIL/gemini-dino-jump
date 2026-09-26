const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function loadHome(guideSeen = false) {
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
    state: { tickets: 1, bestScore: 42 },
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

test('returning players start Dino Jump directly', () => {
  const page = loadHome(true);
  page.elements.get('#btn-start-jump').onclick();
  assert.deepEqual(page.navigations, ['game']);
  assert.equal(page.getModal(), undefined);
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
