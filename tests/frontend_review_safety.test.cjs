const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

const root = path.resolve(__dirname, '..');

function loadView(file, exportName, globals) {
  const context = { ...globals, console };
  context.globalThis = context;
  const source = fs.readFileSync(path.join(root, file), 'utf8')
    .replace(/^import .*;$/gm, '')
    .replace(`export const ${exportName} =`, `globalThis.__view =`);
  vm.runInNewContext(source, context, { filename: file });
  return context.__view;
}

test('editing a nickname preserves the participant leaderboard privacy setting', async () => {
  for (const isPublic of [false, true]) {
    let modal;
    let submitted;
    const field = { label: {}, input: { value: '', name: 'nickname' } };
    const api = {
      async updateProfile(payload) {
        submitted = payload;
        return { participant: { nickname: payload.nickname, is_public: isPublic } };
      },
    };
    const router = {
      state: { participant: { nickname: '기존닉네임', is_public: isPublic } },
      navigate() {},
    };
    const view = loadView('public/js/views/result_view.js', 'ResultView', {
      api,
      analytics: { track() {} },
      ui: {
        formField() { return field; },
        showModal(options) { modal = options; },
        showToast() {},
      },
    });

    view.nicknameModal(router);
    field.input.value = '새닉네임';
    await modal.onConfirm();

    assert.deepEqual(JSON.parse(JSON.stringify(submitted)), { nickname: '새닉네임' });
    assert.equal(router.state.participant.is_public, isPublic);
  }
});

async function renderInvite(navigatorMock) {
  const events = [];
  const toasts = [];
  const nodes = new Map();
  for (const selector of ['#invite-score', '#invite-balance', '#rewarded-pairs', '#valid-visits', '#invite-cooldown', '#btn-share-native', '#btn-copy-link']) {
    nodes.set(selector, { onclick: null, textContent: '' });
  }
  const api = {
    async getReferralInfo() {
      return { invite_url: 'https://example.test/invite/abcdefghijkl', invitation_balance: 0, rewarded_pairs: 0, valid_visits: 0 };
    },
    createRequestId() { return 'share_12345678'; },
  };
  const container = {
    innerHTML: '',
    querySelector(selector) { return nodes.get(selector); },
    replaceChildren() { throw new Error('invite render unexpectedly failed'); },
    appendChild() {},
  };
  const view = loadView('public/js/views/invite_view.js', 'InviteView', {
    api,
    analytics: { track(name, dimensions = {}) { events.push({ name, dimensions }); } },
    ui: {
      text(node, value) { node.textContent = String(value); },
      showToast(message) { toasts.push(message); },
    },
    navigator: navigatorMock,
    window: { location: { origin: 'https://example.test' } },
    URL,
    document: { createElement() { return {}; } },
  });
  const router = { state: { bestScore: 321 }, shareContext: 'retry_invite', isCurrent: () => true };
  await view.render(container, router, 'render-1');
  return { events, nodes, toasts };
}

test('unsupported native sharing falls back to copy without fabricating a native attempt', async () => {
  const copied = [];
  const { events, nodes } = await renderInvite({ clipboard: { async writeText(value) { copied.push(value); } } });
  await nodes.get('#btn-share-native').onclick();

  assert.equal(copied.length, 1);
  assert.match(copied[0], /\/invite\/abcdefghijkl\?link=retry_invite&share=share_12345678/);
  assert.deepEqual(JSON.parse(JSON.stringify(events.filter(({ name }) => name === 'share_attempted').map(({ dimensions }) => dimensions))), [
    { share_method: 'copy', share_id: 'share_12345678', link_kind: 'retry_invite', status: 'attempted' },
    { share_method: 'copy', share_id: 'share_12345678', link_kind: 'retry_invite', status: 'copied' },
  ]);
});

test('copy failure and native cancellation record the actual attempted method and outcome', async () => {
  const copy = await renderInvite({ clipboard: { async writeText() { throw new Error('denied'); } } });
  await copy.nodes.get('#btn-copy-link').onclick();
  assert.deepEqual(copy.events.filter(({ name }) => name === 'share_attempted').map(({ dimensions }) => [dimensions.share_method, dimensions.status]), [
    ['copy', 'attempted'], ['copy', 'failed'],
  ]);

  const native = await renderInvite({
    clipboard: { async writeText() { throw new Error('must not copy'); } },
    async share() { throw { name: 'AbortError' }; },
  });
  await native.nodes.get('#btn-share-native').onclick();
  assert.deepEqual(native.events.filter(({ name }) => name === 'share_attempted').map(({ dimensions }) => [dimensions.share_method, dimensions.status]), [
    ['native', 'attempted'], ['native', 'cancelled'],
  ]);
});

test('Vercel invite routes require the same 12 to 64 character code as the app and server', () => {
  const config = JSON.parse(fs.readFileSync(path.join(root, 'vercel.json'), 'utf8'));
  const inviteRewrite = config.rewrites.find(({ source }) => source.startsWith('/invite/'));
  assert.equal(inviteRewrite.source, '/invite/([A-Za-z0-9_-]{12,64})');
});
