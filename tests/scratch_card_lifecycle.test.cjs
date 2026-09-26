const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness() {
  const events = [];
  const timers = new Map();
  let timerId = 0;
  const target = () => ({
    listeners: new Map(),
    addEventListener(type, handler) { this.listeners.set(type, handler); },
    removeEventListener(type) { this.listeners.delete(type); },
  });
  const window = target();
  const canvas = Object.assign(target(), {
    parentElement: { getBoundingClientRect: () => ({ width: 316, height: 140 }) },
    getBoundingClientRect: () => ({ left: 0, top: 0 }),
    classList: { add() {} },
    getContext: () => ({
      createLinearGradient: () => ({ addColorStop() {} }),
      fillRect() {}, beginPath() {}, arc() {}, fill() {}, fillText() {},
    }),
  });
  const source = fs.readFileSync(path.join(__dirname, '../public/js/components/scratch_card.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export class ScratchCard', 'globalThis.ScratchCard = class ScratchCard');
  const context = {
    window, performance: { now: () => 100 },
    navigator: { vibrate: () => events.push('vibrate') },
    audio: { playWin: () => events.push('sound'), playScratch() {} },
    setTimeout(callback) { const id = ++timerId; timers.set(id, callback); return id; },
    clearTimeout(id) { timers.delete(id); },
  };
  vm.runInNewContext(source, context);
  const card = new context.ScratchCard(canvas, {
    onStart: () => events.push('start'),
    onKeyboardReveal: () => events.push('keyboard'),
    onReveal: () => events.push('reveal'),
  });
  return {
    card, events, canvas, window,
    flush() { for (const [id, callback] of timers) { timers.delete(id); callback(); } },
    emit(type, props = {}) { canvas.listeners.get(type)?.({ preventDefault() {}, clientX: 10, clientY: 10, ...props }); },
  };
}

test('instant reveal starts a fresh scratch once before exposing the result', () => {
  const h = harness();
  h.card.revealInstantly();
  h.card.revealInstantly();
  assert.deepEqual(h.events, ['start', 'vibrate', 'sound']);
  h.flush();
  assert.deepEqual(h.events, ['start', 'vibrate', 'sound', 'reveal']);
});

test('keyboard and pointer starts are not counted twice by instant reveal', () => {
  for (const input of ['keyboard', 'pointer']) {
    const h = harness();
    if (input === 'keyboard') h.emit('keydown', { key: 'Enter' });
    else { h.emit('mousedown'); h.card.revealInstantly(); }
    h.flush();
    assert.equal(h.events.filter((event) => event === 'start').length, 1);
    assert.equal(h.events.filter((event) => event === 'reveal').length, 1);
    assert.equal(h.events.filter((event) => event === 'keyboard').length, input === 'keyboard' ? 1 : 0);
  }
});

test('restoring an already revealed result does not report a new scratch or celebrate again', () => {
  const h = harness();
  h.card.revealInstantly({ restored: true });
  h.flush();
  assert.deepEqual(h.events, ['reveal']);
});

test('leaving the screen cancels a queued reveal and removes input listeners', () => {
  const h = harness();
  h.card.revealInstantly();
  h.card.destroy();
  h.flush();
  assert.equal(h.events.includes('reveal'), false);
  assert.equal(h.canvas.listeners.size, 0);
  assert.equal(h.window.listeners.size, 0);
});
