const test = require('node:test');
const assert = require('node:assert/strict');
const fs = require('node:fs');
const path = require('node:path');

const root = path.join(__dirname, '..');
const read = file => fs.readFileSync(path.join(root, file), 'utf8');

function storage() {
  const values = new Map();
  return { getItem: key => values.has(key) ? values.get(key) : null, setItem: (key,value) => values.set(key,String(value)), removeItem: key => values.delete(key) };
}

async function loadApi() {
  global.localStorage = storage();
  global.sessionStorage = storage();
  global.crypto = { randomUUID: () => '00000000-0000-4000-8000-000000000000' };
  const source = read('public/js/api.js').replace('export const api =', 'const api =') + '\nexport default api;';
  return (await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`)).default;
}

test('session creation reuses its idempotency key after response loss and clears it on start', async () => {
  const api = await loadApi();
  const seen = [];
  global.fetch = async (url, options) => {
    seen.push({ url, options });
    if (seen.length === 1) throw new Error('response lost');
    return { ok: true, json: async () => url.endsWith('/start') ? ({ tickets: 2 }) : ({ session_id: 'game-1' }) };
  };
  await assert.rejects(api.createSession());
  await api.createSession();
  assert.equal(seen[0].options.headers['Idempotency-Key'], seen[1].options.headers['Idempotency-Key']);
  await api.startSession('game-1');
  assert.equal(sessionStorage.getItem('gemini_dino_pending_create'), null);
});

test('participant token stays in Authorization and never enters request JSON', async () => {
  const api = await loadApi();
  api.token = 'secret-participant-token';
  let seen;
  global.fetch = async (url, options) => { seen = { url, options }; return { ok: true, json: async () => ({ ok: true }) }; };
  await api.attributeReferral('invite-code');
  assert.equal(seen.options.headers.Authorization, 'Bearer secret-participant-token');
  assert.doesNotMatch(seen.options.body, /secret-participant-token|session_token/);
  assert.deepEqual(JSON.parse(seen.options.body), { referral_code: 'invite-code' });
});

test('finish retries persist the exact versioned payload until server success', async () => {
  const api = await loadApi();
  api.config = { game_version: 'dino-v2' };
  global.fetch = async () => { throw new Error('offline'); };
  await assert.rejects(api.finishSession('session-1', { score: 12, ticks: 90, jump_ticks: [{ tick: 4, high: false }] }));
  assert.deepEqual(api.getPendingFinish(), { session_id: 'session-1', score: 12, valid_ticks: 90, jump_ticks: [{ tick: 4, high: false }], version: 'dino-v2' });
  global.fetch = async () => ({ ok: true, json: async () => ({ session_id: 'session-1', score: 12 }) });
  await api.finishSession('session-1', api.getPendingFinish());
  assert.equal(api.getPendingFinish(), null);
});

test('frontend has finite tickets, rejected-score gate, stale guards and timer cleanup', () => {
  const app = read('public/js/app.js');
  const home = read('public/js/views/home.js');
  const game = read('public/js/views/game_view.js');
  const result = read('public/js/views/result_view.js');
  assert.doesNotMatch(`${app}\n${home}\n${game}`, /무제한|♾️/);
  assert.match(result, /eligibleForDraw/);
  assert.match(app, /navigationEpoch/);
  assert.match(app, /closeInterruptedSession/);
  assert.match(app, /SESSION_EXPIRED/);
  assert.match(app, /SESSION_NOT_ACTIVE/);
  assert.match(app, /GAME_VERSION_MISMATCH/);
  assert.ok(app.indexOf('await this.recoverPendingFinish()') < app.indexOf('await this.closeInterruptedSession()'));
  assert.match(game, /clearInterval\(this\.countdownTimer\)/);
  assert.match(game, /abortSession/);
  const scratch = read('public/js/components/scratch_card.js');
  const draw = read('public/js/views/draw_view.js');
  assert.match(scratch, /destroy\(\)/);
  assert.match(scratch, /removeEventListener\('touchmove'/);
  assert.match(draw, /scratchCard\?\.destroy\(\)/);
});

test('analytics sends only an allowlisted, identifier-free schema', () => {
  const source = read('public/js/analytics.js');
  assert.match(source, /const ALLOWED = new Set/);
  assert.match(source, /const SAFE_FIELDS = new Set\(\['screen','active_ms','channel','error_code'\]\)/);
  assert.doesNotMatch(source, /participant_id|session_token|referral_code|invite_url/);
  assert.match(source, /visibilitychange/);
  assert.match(source, /page_engagement/);
  assert.match(source, /script\.dataset\.disableAutoTrack = '1'/);
  assert.match(source, /window\.va\('pageview', \{ route: path, path \}\)/);
  assert.doesNotMatch(source, /screen_view/);
});

test('Vercel page views are manual-only and redact invite queries and hashes', async () => {
  global.window = { location: { origin: 'https://preview.example' } };
  const source = read('public/js/analytics.js').replace(
    "import { api } from './api.js';",
    "const api = { newId: () => 'evt_safe', token: '', config: {}, sendEvents: async () => true };"
  );
  const module = await import(`data:text/javascript;base64,${Buffer.from(source).toString('base64')}`);
  assert.equal(module.safeScreen('invite/SECRET'), 'home');
  const redacted = module.redactVercelEvent({ type: 'pageview', url: 'https://preview.example/?invite=PRIVATE#token', referrer: 'https://social.example/user-secret', invite: 'PRIVATE' });
  assert.deepEqual(redacted, { type: 'pageview', url: 'https://preview.example/screen/home' });
  assert.doesNotMatch(JSON.stringify(redacted), /PRIVATE|invite|token|\?|#/);
  const html = read('public/index.html');
  assert.match(html, /<meta name="referrer" content="no-referrer">/);
});

test('admin credentials stay out of storage and logs; access token is session only', () => {
  const source = read('public/js/admin.js');
  assert.match(source, /sessionStorage\.setItem\(AUTH_KEY,data\.access_token\)/);
  assert.doesNotMatch(source, /localStorage|console\./);
  assert.doesNotMatch(source, /setItem\([^,]+,(?:email|password)/);
  assert.match(source, /supabase_publishable_key/);
  assert.match(source, /include_synthetic/);
  assert.match(source, /item\.prize_id/);
});

test('server strings are rendered through textContent in dynamic lists', () => {
  for (const file of ['public/js/views/prize_view.js','public/js/views/ranking_view.js','public/js/admin.js']) {
    const source = read(file);
    assert.match(source, /textContent/);
    assert.doesNotMatch(source, /innerHTML\s*=.*(?:nickname|prize_name|coupon_code|verification_result)/);
  }
});
