const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

function harness() {
  class Element {
    constructor(tag = 'div') { this.tagName = tag.toUpperCase(); this.children = []; this.parent = null; this.attrs = {}; this.inert = false; }
    append(...children) { children.forEach((child) => this.appendChild(child)); }
    appendChild(child) { child.parent = this; this.children.push(child); }
    contains(target) { return this === target || this.children.some((child) => child.contains(target)); }
    remove() { this.parent.children = this.parent.children.filter((child) => child !== this); this.parent = null; }
    setAttribute(key, value) { this.attrs[key] = value; }
    focus() { document.activeElement = this; }
    getClientRects() { return this.hidden ? [] : [{}]; }
    querySelectorAll() {
      return this.children.flatMap((child) => [child, ...child.querySelectorAll()])
        .filter((child) => ['BUTTON', 'INPUT', 'SELECT', 'TEXTAREA', 'A'].includes(child.tagName) && !child.disabled && child.type !== 'hidden');
    }
  }
  const descendants = (element) => [element, ...element.children.flatMap(descendants)];
  const document = {
    body: new Element('body'), activeElement: null,
    createElement: (tag) => new Element(tag),
    getElementById: (id) => descendants(document.body).find((child) => child.id === id) || null,
  };
  const app = document.createElement('div'); app.id = 'app-container';
  const opener = document.createElement('button'); app.append(opener); document.body.append(app); opener.focus();
  const microtasks = [];
  const context = { document, Node: Element, queueMicrotask: (callback) => microtasks.push(callback) };
  const source = fs.readFileSync(path.join(__dirname, '../public/js/ui.js'), 'utf8').replace('export const ui =', 'globalThis.ui =');
  vm.runInNewContext(source, context);
  return {
    ui: context.ui, document, app, opener,
    flush() { while (microtasks.length) microtasks.shift()(); },
    modal: () => document.getElementById('common-modal-overlay'),
    key(key, shiftKey = false) { const event = { key, shiftKey, prevented: false, preventDefault() { this.prevented = true; } }; this.modal().onkeydown(event); return event; },
  };
}

test('an old submission finishing cannot close a newer modal or move focus back to the removed form', async () => {
  const h = harness();
  let release;
  const pending = new Promise((resolve) => { release = resolve; });
  h.ui.showModal({ title: '수령 정보', content: '이전 폼', onConfirm: () => pending });
  const previousConfirm = h.modal().children[0].children[2].children[0];
  const submitting = previousConfirm.onclick();
  h.ui.showModal({ title: '새 폼', content: '입력 중인 정보' });
  const current = h.modal();
  const currentConfirm = current.children[0].children[2].children[0];
  h.flush();
  assert.equal(h.document.activeElement, currentConfirm);
  release(true);
  await submitting;
  assert.equal(h.modal(), current);
  assert.equal(h.document.activeElement, currentConfirm);
  assert.equal(h.app.inert, true);
  await currentConfirm.onclick();
  assert.equal(h.modal(), null);
  assert.equal(h.app.inert, false);
  assert.equal(h.document.activeElement, h.opener);
});

test('a named form dialog focuses its first field and contains forward and backward keyboard navigation', () => {
  const h = harness();
  const form = h.document.createElement('form');
  const hidden = h.document.createElement('input'); hidden.type = 'hidden';
  const input = h.document.createElement('input');
  form.append(hidden, input);
  h.ui.showModal({ title: '수령 정보 접수', content: form, cancelText: '취소' });
  h.flush();
  const modal = h.modal();
  assert.equal(h.document.getElementById(modal.attrs['aria-labelledby']).textContent, '수령 정보 접수');
  assert.equal(h.document.activeElement, input);
  assert.equal(h.app.inert, true);
  const confirm = modal.children[0].children[2].children[1];
  assert.equal(h.key('Tab', true).prevented, true);
  assert.equal(h.document.activeElement, confirm);
  assert.equal(h.key('Tab').prevented, true);
  assert.equal(h.document.activeElement, input);
});

test('Escape cancels a cancellable form and restores its opener without submitting', () => {
  const h = harness(); let cancelled = 0; let submitted = 0;
  h.ui.showModal({ title: '입력', content: '', cancelText: '취소', onCancel: () => cancelled++, onConfirm: () => submitted++ });
  h.flush();
  assert.equal(h.key('Escape').prevented, true);
  assert.equal(cancelled, 1); assert.equal(submitted, 0);
  assert.equal(h.modal(), null);
  assert.equal(h.app.inert, false);
  assert.equal(h.document.activeElement, h.opener);
});

test('pending confirmation is single flight and failure keeps the same form available', async () => {
  const h = harness(); let release; let submissions = 0;
  const pending = new Promise((resolve) => { release = resolve; });
  h.ui.showModal({ title: '입력', content: '', onConfirm: () => { submissions++; return pending; } });
  h.flush();
  const modal = h.modal(); const confirm = modal.children[0].children[2].children[0];
  const first = confirm.onclick();
  await confirm.onclick();
  assert.equal(submissions, 1);
  assert.equal(h.key('Escape').prevented, false);
  release(false); await first;
  assert.equal(h.modal(), modal);
  assert.equal(confirm.disabled, false);
  h.ui.hideModal();
  assert.equal(h.document.activeElement, h.opener);
});
