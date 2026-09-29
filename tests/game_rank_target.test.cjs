const assert = require('node:assert/strict');
const fs = require('node:fs');
const test = require('node:test');
const vm = require('node:vm');
const source = fs.readFileSync('public/js/views/game_view.js', 'utf8').replace(/^import .*;\s*$/gm, '').replace('export const GameView =', 'globalThis.GameView =');
function harness(getLeaderboard = async () => ({})) {
  const label = { hidden: true, textContent: '' };
  const context = { api: { getLeaderboard }, ui: { text(node, value) { node.textContent = String(value); } }, console };
  vm.runInNewContext(source, context);
  const view = context.GameView;
  view.sessionId = 'current'; view.gameVersion = '2.1.0'; view.engine = { score: 150 };
  return { view, label, container: { querySelector: () => label }, router: { isCurrent: () => true } };
}
test('current run advances bronze to silver to gold at tied thresholds and reverses after a penalty', () => {
  const { view, label, container } = harness();
  view.rankTargets = [{ rank: 1, score: 500 }, { rank: 2, score: 300 }, { rank: 3, score: 200 }];
  for (const [score, text] of [[0, '🥉까지 200점'], [199, '🥉까지 1점'], [200, '🥈까지 100점'], [300, '🥇까지 200점'], [500, '🥇 목표 달성!'], [600, '🥇 목표 달성!'], [150, '🥉까지 50점']]) {
    view.updateRankTarget(container, score); assert.equal(label.textContent, text);
  }
});
test('empty or sparse ranking has no invented target score', () => {
  const { view, label, container } = harness();
  view.rankTargets = []; view.updateRankTarget(container, 0); assert.equal(label.textContent, '첫 기록에 도전!');
  view.rankTargets = [{ rank: 1, score: 100 }]; view.updateRankTarget(container, 10); assert.equal(label.textContent, '🥇까지 90점');
});
test('ranking loads once without blocking game and uses the score at response time', async () => {
  let resolve; let calls = 0;
  const h = harness(() => { calls++; return new Promise(done => { resolve = done; }); });
  const pending = h.view.loadRankTargets(h.container, h.router, 7);
  h.view.engine.score = 175;
  resolve({ game_version: '2.1.0', rank_targets: [{ rank: 1, score: 500 }] });
  await pending;
  assert.equal(h.label.textContent, '🥇까지 325점');
  h.view.updateRankTarget(h.container, 200); assert.equal(calls, 1);
});
test('late, failed or different-version rankings cannot update a new game HUD', async () => {
  for (const scenario of ['late', 'failed', 'old-version']) {
    let resolve, reject;
    const h = harness(() => new Promise((ok, fail) => { resolve = ok; reject = fail; }));
    const pending = h.view.loadRankTargets(h.container, h.router, 7);
    if (scenario === 'late') h.view.lifecycleId++;
    if (scenario === 'failed') reject(new Error('offline'));
    else resolve({ game_version: scenario === 'old-version' ? '2.0.0' : '2.1.0', rank_targets: [{ rank: 1, score: 500 }] });
    await pending; assert.equal(h.label.hidden, true);
  }
});
