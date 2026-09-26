const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function node(tag = 'div') {
  return {
    tag, children: [], textContent: '', href: '', hidden: false, attrs: {},
    classList: { add() {} },
    append(...children) { this.children.push(...children); },
    appendChild(child) { this.children.push(child); },
    removeAttribute(name) { delete this.attrs[name]; },
    setAttribute(name, value) { this.attrs[name] = String(value); },
  };
}

function loadBenefit(globals) {
  const source = fs.readFileSync(path.join(root, 'public/js/views/benefit_view.js'), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace('export const BenefitView =', 'globalThis.__view =');
  const context = { console, URL, ...globals };
  context.globalThis = context;
  vm.runInNewContext(source, context, { filename: 'benefit_view.js' });
  return context.__view;
}

test('foreground return rechecks hidden intersections once and cleanup rejects stale callbacks', () => {
  const events = [];
  const listeners = new Map();
  const observers = [];
  const ratios = new Map();
  const document = {
    hidden: false,
    createElement: (tag) => node(tag),
    addEventListener(name, handler) { listeners.set(name, handler); },
    removeEventListener(name, handler) { if (listeners.get(name) === handler) listeners.delete(name); },
  };
  class ObserverMock {
    constructor(callback) { this.callback = callback; this.targets = new Set(); this.disconnected = false; observers.push(this); }
    observe(target) {
      this.targets.add(target);
      if (ratios.has(target)) this.callback([{ target, isIntersecting: ratios.get(target) > 0, intersectionRatio: ratios.get(target) }]);
    }
    unobserve(target) { this.targets.delete(target); }
    disconnect() { this.disconnected = true; this.targets.clear(); }
    takeRecords() { return []; }
    trigger(target, ratio) {
      ratios.set(target, ratio);
      if (!this.disconnected && this.targets.has(target)) this.callback([{ target, isIntersecting: ratio > 0, intersectionRatio: ratio }]);
    }
  }
  const link = node('a');
  const guideList = node();
  const nodes = new Map([
    ['#btn-go-benefit', link], ['#btn-copy-benefit', node('button')], ['#btn-share-benefit', node('button')],
    ['#benefit-fallback', node('p')], ['#content-guide-list', guideList],
  ]);
  const view = loadBenefit({
    document, IntersectionObserver: ObserverMock,
    analytics: { track: (name, dimensions = {}) => events.push({ name, dimensions }) },
    ui: { text: (target, value) => { target.textContent = String(value); }, showToast() {} },
    navigator: { clipboard: { writeText: async () => {} } },
  });
  const container = { innerHTML: '', querySelector: (selector) => nodes.get(selector) };
  view.render(container, { config: {
    official_url: 'https://gemini.google.com/students',
    content_guides: [{ id: 'study_note', title: '제미나이 노트북', description: '학습 가이드', url: 'https://example.test/guide', available: true }],
  } });
  const guideCard = guideList.children[0];
  document.hidden = true;
  observers[0].trigger(guideCard, 1);
  observers[1].trigger(link, 1);
  assert.equal(events.some(({ name }) => name === 'content_viewed' || name === 'gemini_cta_viewed'), false);

  document.hidden = false;
  listeners.get('visibilitychange')?.();
  assert.equal(events.filter(({ name }) => name === 'content_viewed').length, 1);
  assert.equal(events.filter(({ name }) => name === 'gemini_cta_viewed').length, 1);

  observers[0].trigger(guideCard, 1);
  observers[1].trigger(link, 1);
  view.cleanup();
  observers[0].callback([{ target: guideCard, isIntersecting: true, intersectionRatio: 1 }]);
  observers[1].callback([{ target: link, isIntersecting: true, intersectionRatio: 1 }]);
  listeners.get('visibilitychange')?.();
  assert.equal(events.filter(({ name }) => name === 'content_viewed').length, 1);
  assert.equal(events.filter(({ name }) => name === 'gemini_cta_viewed').length, 1);
  assert.equal(listeners.has('visibilitychange'), false);
});

test('missing IntersectionObserver does not fabricate measured exposure', () => {
  const events = [];
  const link = node('a');
  const nodes = new Map([
    ['#btn-go-benefit', link], ['#btn-copy-benefit', node('button')], ['#btn-share-benefit', node('button')],
    ['#benefit-fallback', node('p')], ['#content-guide-list', node()],
  ]);
  const view = loadBenefit({
    document: { hidden: false, createElement: (tag) => node(tag), addEventListener() {}, removeEventListener() {} },
    IntersectionObserver: undefined,
    analytics: { track: (name) => events.push(name) },
    ui: { text() {}, showToast() {} }, navigator: {},
  });
  view.render({ innerHTML: '', querySelector: (selector) => nodes.get(selector) }, { config: { official_url: 'https://gemini.google.com/students' } });
  assert.equal(events.includes('benefit_viewed'), true);
  assert.equal(events.includes('gemini_cta_viewed'), false);
  assert.equal(events.includes('content_viewed'), false);
});

test('foreground return discards queued positive snapshots and waits for a fresh 50 percent measurement', () => {
  const events = [];
  const listeners = new Map();
  const observers = [];
  const ratios = new Map();
  const document = {
    hidden: false,
    createElement: (tag) => node(tag),
    addEventListener(name, handler) { listeners.set(name, handler); },
    removeEventListener(name, handler) { if (listeners.get(name) === handler) listeners.delete(name); },
  };
  class ObserverMock {
    constructor(callback) { this.callback = callback; this.targets = new Set(); this.records = []; observers.push(this); }
    observe(target) {
      this.targets.add(target);
      if (ratios.has(target)) this.callback([{ target, isIntersecting: ratios.get(target) > 0, intersectionRatio: ratios.get(target) }]);
    }
    unobserve(target) { this.targets.delete(target); }
    disconnect() { this.targets.clear(); }
    takeRecords() { return this.records.splice(0); }
    queue(target, ratio) { this.records.push({ target, isIntersecting: ratio > 0, intersectionRatio: ratio }); }
    trigger(target, ratio) {
      ratios.set(target, ratio);
      if (this.targets.has(target)) this.callback([{ target, isIntersecting: ratio > 0, intersectionRatio: ratio }]);
    }
  }
  const link = node('a');
  const guideList = node();
  const nodes = new Map([
    ['#btn-go-benefit', link], ['#btn-copy-benefit', node('button')], ['#btn-share-benefit', node('button')],
    ['#benefit-fallback', node('p')], ['#content-guide-list', guideList],
  ]);
  const view = loadBenefit({
    document, IntersectionObserver: ObserverMock,
    analytics: { track: (name) => events.push(name) },
    ui: { text() {}, showToast() {} }, navigator: {},
  });
  view.render({ innerHTML: '', querySelector: (selector) => nodes.get(selector) }, { config: {
    official_url: 'https://gemini.google.com/students',
    content_guides: [{ id: 'guide', title: '가이드', description: '설명', url: 'https://example.test/guide', available: true }],
  } });
  const guideCard = guideList.children[0];
  document.hidden = true;
  observers[0].queue(guideCard, 1);
  observers[1].queue(link, 1);
  ratios.set(guideCard, 0);
  ratios.set(link, 0);

  document.hidden = false;
  listeners.get('visibilitychange')();
  assert.equal(events.includes('content_viewed'), false);
  assert.equal(events.includes('gemini_cta_viewed'), false);

  observers[0].trigger(guideCard, 0.5);
  observers[1].trigger(link, 0.5);
  observers[0].trigger(guideCard, 1);
  observers[1].trigger(link, 1);
  assert.equal(events.filter((name) => name === 'content_viewed').length, 1);
  assert.equal(events.filter((name) => name === 'gemini_cta_viewed').length, 1);
  view.cleanup();
});
