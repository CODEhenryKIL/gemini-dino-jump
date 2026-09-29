const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');
const vm = require('node:vm');

class Element {
  constructor(tag) { this.tag = tag; this.children = []; this.className = ''; this.textContent = ''; }
  append(...items) { this.children.push(...items); }
  appendChild(item) { this.children.push(item); }
  replaceChildren(...items) { this.children = items; }
  setAttribute() {}
}

function harness(data) {
  let requestedView;
  const context = {
    document: { createElement: tag => new Element(tag) },
    api: { getLeaderboard: async options => { requestedView = options.view; return data; } },
    analytics: { track() {} },
    prepareResultReferralShare: async () => ({ share: async () => ({ status: 'cancelled' }) }),
  };
  const source = fs.readFileSync(path.join(__dirname, '../public/js/views/ranking_view.js'), 'utf8')
    .replace(/^import .*;\s*$/gm, '')
    .replace('export const RankingView =', 'globalThis.RankingView =');
  vm.runInNewContext(source, context);
  return { view: context.RankingView, requestedView: () => requestedView };
}

const entries = Array.from({ length: 60 }, (_, index) => ({
  rank: index + 1, nickname: `참가자${index + 1}`, score: 2000 - index, tied: false, is_me: index === 54,
}));
const textOf = node => [node.textContent, ...node.children.map(textOf)].join(' ');

test('ranking lists only the requested milestones while preserving a personal rank beyond fifty', async () => {
  const data = { leaderboard: entries.slice(0, 3), rank_highlights: entries, me: { rank: 55, best_score: 1946 }, top3_gap: { participant_count: 60 } };
  const h = harness(data);
  const container = new Element('main');
  await h.view.render(container, { isCurrent: () => true }, 1);
  assert.equal(h.requestedView(), 'milestones');
  const list = container.children.find(node => node.className === 'card ranking-list');
  assert.deepEqual(list.children.map(row => row.children[1].textContent), [
    ...Array.from({ length: 10 }, (_, i) => `참가자${i + 1}`), '참가자20', '참가자30', '참가자40', '참가자50',
  ]);
  const personal = container.children.find(node => node.className.includes('ranking-my-record'));
  assert.match(textOf(personal), /55위/);
  assert.match(textOf(personal), /1,946점/);
  assert.doesNotMatch(textOf(list), /참가자55/);
});

test('a short or older leaderboard never invents milestone records and duplicate ranks occupy one row', () => {
  const h = harness({});
  const visible = h.view.visibleRanks({ leaderboard: [entries[0], { ...entries[0], nickname: '공동1위' }, entries[9], entries[10], entries[18], entries[19]] });
  assert.deepEqual(Array.from(visible, entry => entry.rank), [1, 10, 20]);
  assert.equal(h.view.visibleRanks({ rank_highlights: [], leaderboard: entries }).length, 0);
  assert.equal(h.view.visibleRanks({}).length, 0);
});

test('ranking follows server order without showing the former joint-rank label', async () => {
  const h = harness({
    rank_highlights: [{ rank: 1, nickname: '먼저 달성', score: 1000, tied: true }],
    me: { rank: 1, best_score: 1000 }, top3_gap: { status: 'IN_TOP3', participant_count: 1 },
  });
  const container = new Element('main');
  await h.view.render(container, { isCurrent: () => true }, 1);
  const list = container.children.find(node => node.className === 'card ranking-list');
  assert.doesNotMatch(textOf(list), /동점|공동/);
  assert.match(textOf(list), /🥇/);
});

test('ranking rounds a positive score gap up and never tells a stale tied response to play zero seconds', () => {
  const h = harness({});
  const base = { me: { rank: 4 }, top3_gap: { status: 'CHASING', third_score: 100 } };
  assert.equal(h.view.timeGapMessage({ ...base, top3_gap: { ...base.top3_gap, score_needed: 1 } }), '3위까지 약 1초 더!');
  assert.equal(h.view.timeGapMessage({ ...base, top3_gap: { ...base.top3_gap, score_needed: 11 } }), '3위까지 약 2초 더!');
  assert.match(h.view.timeGapMessage({ ...base, top3_gap: { ...base.top3_gap, score_needed: 0, tied: true } }), /확인/);
});
