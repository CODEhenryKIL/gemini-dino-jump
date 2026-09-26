const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const metrics = fs.readFileSync(path.join(root, 'server/metrics.py'), 'utf8');
const admin = fs.readFileSync(path.join(root, 'public/js/admin.js'), 'utf8');

test('metrics scope leaderboard and histogram to the active game version', () => {
  assert.match(metrics, /game_version = ctx\.get\('game_version'\) or campaign\['game_version'\]/);
  assert.match(metrics, /score_source = _score_source\(game_version\)/);
  assert.match(metrics, /where g\.version=%s and g\.status='FINISHED'/);
  assert.match(metrics, /from \{score_source\}/);
  assert.match(admin, /게임 버전/);
});

test('gameplay totals come from trusted stored game summaries', () => {
  for (const key of ['coins', 'coin_score', 'hearts', 'revives']) {
    assert.match(metrics, new RegExp(`g\\.game_summary->>'${key}'`));
  }
  assert.match(metrics, /g\.end_reason='TIME_LIMIT'/);
  assert.match(metrics, /서버 재현 후 저장된 game_summary/);
});

test('loading milestones content CTR and all share purposes stay distinct', () => {
  for (const milestone of ['loading_data_ready', 'loading_intro_completed', 'loading_ready']) {
    assert.match(metrics, new RegExp(milestone));
  }
  assert.match(metrics, /event_name in \('content_viewed','content_clicked','notion_redirect_requested'\)/);
  assert.match(metrics, /row\['unique_ctr'\] = row\['converted_participants'\] \/ row\['viewed_participants'\]/);
  assert.match(metrics, /when dimensions->>'link_kind'='record_share' then 'record_share'/);
  assert.match(metrics, /when dimensions->>'link_kind'='prize_share' then 'prize_share'/);
  assert.match(metrics, /then 'retry_invite'/);
  assert.match(admin, /record_share_sharing/);
  assert.match(admin, /retry_invite_sharing/);
  assert.match(admin, /prize_share_sharing/);
  assert.match(admin, /고유 CTR/);
});

test('admin labels observed actions without claiming enrollment', () => {
  assert.doesNotMatch(admin, /가입\s*(?:성공|완료|전환)/);
  assert.match(admin, /기록 공유 수단/);
  assert.match(admin, /로딩 마일스톤/);
});
