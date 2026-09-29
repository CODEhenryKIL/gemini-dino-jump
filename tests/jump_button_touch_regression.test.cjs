const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function eventTarget(parent) {
  const listeners = new Map();
  return {
    listeners,
    addEventListener(type, listener, options) {
      const entries = listeners.get(type) || [];
      entries.push({ listener, options });
      listeners.set(type, entries);
    },
    removeEventListener(type, listener) {
      listeners.set(type, (listeners.get(type) || []).filter((entry) => entry.listener !== listener));
    },
    dispatch(type, event = {}) {
      event.type = type;
      for (const { listener } of [...(listeners.get(type) || [])]) listener(event);
      parent?.dispatch(type, event);
    },
  };
}

function loadGameView() {
  const windowTarget = eventTarget();
  const documentTarget = eventTarget();
  const engines = [];
  class FakeEngine {
    constructor() {
      this.presses = 0;
      this.releases = 0;
      engines.push(this);
    }
    jumpPress() { this.presses += 1; }
    jumpRelease() { this.releases += 1; }
    stop() {}
  }
  const context = {
    api: { getLeaderboard: async () => ({}) },
    analytics: { track() {} },
    ui: { text(node, value) { node.textContent = String(value); } },
    audio: { toggleMute() { return false; } },
    DinoGameEngine: FakeEngine,
    document: { ...documentTarget, hidden: false },
    window: { ...windowTarget, matchMedia: () => ({ matches: false }) },
    sessionStorage: { getItem() { return null; }, setItem() {}, removeItem() {} },
    setTimeout, clearTimeout, setInterval, clearInterval, Date, console,
  };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, 'public/js/views/game_view.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const GameView =', 'globalThis.GameView =');
  vm.runInNewContext(source, context, { filename: 'game_view.js' });
  return { view: context.GameView, engines };
}

function createHarness() {
  const jumpButton = eventTarget();
  const viewport = eventTarget();
  const canvas = eventTarget(viewport);
  const sound = eventTarget(viewport);
  const inertNode = {
    textContent: '', offsetWidth: 0,
    classList: { add() {}, remove() {} },
    querySelector() { return inertNode; },
  };
  const nodes = new Map([
    ['#game-canvas', canvas],
    ['.game-viewport-container', viewport],
    ['#btn-jump', jumpButton],
    ['#btn-toggle-sound', sound],
  ]);
  const container = { querySelector(selector) { return nodes.get(selector) || inertNode; } };
  return { canvas, container, jumpButton, sound, viewport };
}

function cancelableEvent() {
  return {
    defaultPrevented: false,
    preventDefault() { this.defaultPrevented = true; },
  };
}

test('repeated jump-button touches suppress Safari selection while pointer press/release still run', () => {
  const { view, engines } = loadGameView();
  const { container, jumpButton } = createHarness();
  view.gameVersion = '2.1.0';
  view.bindEngine(container, { isCurrent: () => true }, 1, 7);

  for (let attempt = 0; attempt < 2; attempt += 1) {
    const pointerDown = cancelableEvent();
    jumpButton.dispatch('pointerdown', pointerDown);
    assert.equal(pointerDown.defaultPrevented, true);

    for (const eventName of ['touchstart', 'touchmove', 'touchend', 'selectstart', 'dblclick']) {
      const event = cancelableEvent();
      jumpButton.dispatch(eventName, event);
      assert.equal(event.defaultPrevented, true, `${eventName} must be cancelled on the jump button`);
    }

    const pointerUp = cancelableEvent();
    jumpButton.dispatch('pointerup', pointerUp);
    assert.equal(pointerUp.defaultPrevented, true);
  }

  assert.equal(engines[0].presses, 2);
  assert.equal(engines[0].releases, 2);
  for (const eventName of ['touchstart', 'touchmove', 'touchend']) {
    assert.equal(jumpButton.listeners.get(eventName)[0].options.passive, false);
  }
});

test('game board cancels native selection without duplicating or prematurely releasing a held jump', () => {
  const { view, engines } = loadGameView();
  const { container, canvas, viewport, sound } = createHarness();
  view.bindEngine(container, { isCurrent: () => true }, 1, 7);

  canvas.dispatch('pointerdown', cancelableEvent());
  for (const eventName of ['contextmenu', 'dragstart', 'selectstart', 'dblclick', 'touchstart', 'touchmove', 'touchend']) {
    const event = cancelableEvent();
    canvas.dispatch(eventName, event);
    assert.equal(event.defaultPrevented, true, `${eventName} must be cancelled on the canvas`);
  }
  assert.equal(engines[0].presses, 1);
  assert.equal(engines[0].releases, 0, 'native-event suppression must not release a held super jump');
  canvas.dispatch('pointerup', cancelableEvent());
  canvas.dispatch('pointerdown', cancelableEvent());
  canvas.dispatch('pointercancel', cancelableEvent());
  assert.equal(engines[0].presses, 2);
  assert.equal(engines[0].releases, 2);

  const hudSelection = cancelableEvent();
  viewport.dispatch('selectstart', hudSelection);
  assert.equal(hudSelection.defaultPrevented, true);
  for (const eventName of ['touchstart', 'touchmove', 'touchend']) {
    assert.equal(canvas.listeners.get(eventName)[0].options.passive, false);
    const soundTouch = cancelableEvent();
    sound.dispatch(eventName, soundTouch);
    assert.equal(soundTouch.defaultPrevented, false, 'sound control touch must remain native');
  }
  sound.onclick({ stopPropagation() {}, currentTarget: sound });
  assert.equal(sound.textContent, '🔊');
});

test('cleanup removes every game-board and jump-button suppression and pointer handler', () => {
  const { view } = loadGameView();
  const { container, jumpButton, canvas, viewport } = createHarness();
  view.gameVersion = '2.1.0';
  view.bindEngine(container, { isCurrent: () => true }, 1, 7);
  view.cleanup();

  for (const eventName of [
    'contextmenu', 'dragstart', 'selectstart', 'dblclick',
    'touchstart', 'touchmove', 'touchend',
    'pointerdown', 'pointerup', 'pointercancel',
  ]) {
    for (const element of [jumpButton, canvas, viewport]) {
      assert.equal(element.listeners.get(eventName)?.length || 0, 0, `${eventName} listener leaked`);
    }
  }
});

test('selection and touch suppression stay off unrelated form controls and global CSS', () => {
  const { view } = loadGameView();
  const { container } = createHarness();
  const formControl = eventTarget();
  view.gameVersion = '2.1.0';
  view.bindEngine(container, { isCurrent: () => true }, 1, 7);

  for (const eventName of ['selectstart', 'dblclick', 'touchstart', 'touchmove', 'touchend']) {
    assert.equal(formControl.listeners.has(eventName), false);
  }

  const css = fs.readFileSync(path.join(root, 'public/css/game.css'), 'utf8');
  assert.match(css, /\.big-jump-btn \{[\s\S]*?touch-action:\s*none/);
  assert.match(css, /\.game-viewport-container,\s*\.game-viewport-container \*\s*\{[^}]*-webkit-user-select:\s*none;[^}]*-webkit-touch-callout:\s*none;/);
  assert.doesNotMatch(css, /(?:^|\n)(?:html|body|\*)[^\{]*\{[^}]*(?:touch-action:\s*none|user-select:\s*none)/);
});
