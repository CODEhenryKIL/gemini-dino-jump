const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

test('an old submission finishing cannot close a newer modal or move focus back to the removed form', async () => {
  class Element {
    constructor() { this.children = []; this.parent = null; }
    append(...children) { children.forEach((child) => this.appendChild(child)); }
    appendChild(child) { child.parent = this; this.children.push(child); }
    contains(target) { return this === target || this.children.some((child) => child.contains(target)); }
    remove() { this.parent.children = this.parent.children.filter((child) => child !== this); this.parent = null; }
    setAttribute() {}
    focus() { document.activeElement = this; }
  }
  const document = {
    body: new Element(), activeElement: null,
    createElement: () => new Element(),
    getElementById: (id) => document.body.children.find((child) => child.id === id) || null,
  };
  const microtasks = [];
  const context = { document, Node: Element, queueMicrotask: (callback) => microtasks.push(callback) };
  const source = fs.readFileSync(path.join(__dirname, '../public/js/ui.js'), 'utf8').replace('export const ui =', 'globalThis.ui =');
  vm.runInNewContext(source, context);
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  context.ui.showModal({ title: '수령 정보', content: '이전 폼', onConfirm: () => pending });
  const previous = document.getElementById('common-modal-overlay');
  const previousConfirm = previous.children[0].children[2].children[0];
  const submitting = previousConfirm.onclick();
  context.ui.showModal({ title: '새 폼', content: '입력 중인 정보' });
  const current = document.getElementById('common-modal-overlay');
  const currentConfirm = current.children[0].children[2].children[0];
  microtasks.forEach((callback) => callback());
  assert.equal(document.activeElement, currentConfirm);
  release(true);
  await submitting;
  assert.equal(document.getElementById('common-modal-overlay'), current);
  assert.equal(document.activeElement, currentConfirm);
  await currentConfirm.onclick();
  assert.equal(document.getElementById('common-modal-overlay'), null);
});
