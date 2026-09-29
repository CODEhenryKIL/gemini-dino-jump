const assert = require('node:assert/strict');
const crypto = require('node:crypto');
const fs = require('node:fs');
const path = require('node:path');
const { Readable } = require('node:stream');
const test = require('node:test');

const root = path.resolve(__dirname, '..');
const handler = require('../integrations/datadog-drain/api/drain.js');
const sourceConfig = require('../integrations/datadog-drain/source-config.js');
const source = fs.readFileSync(path.join(root, 'integrations/datadog-drain/api/drain.js'), 'utf8');
const SECRET = 'test-drain-signature-secret';
const API_KEY = 'test-datadog-api-key';

function applicationRecord(overrides = {}) {
  return {
    event: 'api_request', service: 'gemini-dino-jump', env: 'production',
    campaign: 'gemini_dino_campus_2026', route: '/api/game-sessions/{id}/finish',
    deployment: 'dpl_private',
    method: 'POST', status: 200, duration_ms: 125,
    request_id: '643af4e3-975a-4cc7-9e7a-1eda11539d90', outcome: 'success',
    operation_outcome: 'completed', error_class: 'none', error_code: null,
    database_failure: null, ...overrides,
  };
}

function envelope(record = applicationRecord(), overrides = {}) {
  return {
    id: 'platform-log-id', deploymentId: 'dpl_private', source: 'lambda', type: 'stderr',
    host: 'private-host.vercel.app', timestamp: 1790665200000,
    projectId: sourceConfig.projectId, environment: 'production',
    message: JSON.stringify(record),
    proxy: {
      path: '/invite/private-code?phone=01012345678', clientIp: '203.0.113.5',
      referer: 'https://private.example/?token=secret', userAgent: ['private-agent'],
    },
    ...overrides,
  };
}

function signature(body) {
  return crypto.createHmac('sha1', SECRET).update(body).digest('hex');
}

function responseMock() {
  return {
    statusCode: 0, headers: {}, body: '',
    setHeader(name, value) { this.headers[name.toLowerCase()] = value; },
    end(value = '') { this.body = String(value); },
  };
}

async function invoke(body, options = {}) {
  const buffer = Buffer.isBuffer(body) ? body : Buffer.from(body);
  const request = Readable.from(options.chunks || [buffer]);
  request.method = options.method || 'POST';
  request.headers = {
    'content-length': String(options.contentLength ?? buffer.length),
    'x-vercel-signature': options.signature ?? signature(buffer),
  };
  const response = responseMock();
  const previousFetch = global.fetch;
  const previousSecret = process.env.VERCEL_DRAIN_SECRET;
  const previousApiKey = process.env.DD_API_KEY;
  process.env.VERCEL_DRAIN_SECRET = SECRET;
  process.env.DD_API_KEY = API_KEY;
  const calls = [];
  global.fetch = options.fetch || (async (...args) => { calls.push(args); return { ok: true, status: 202 }; });
  try {
    await handler(request, response);
    return { response, calls };
  } finally {
    global.fetch = previousFetch;
    if (previousSecret === undefined) delete process.env.VERCEL_DRAIN_SECRET;
    else process.env.VERCEL_DRAIN_SECRET = previousSecret;
    if (previousApiKey === undefined) delete process.env.DD_API_KEY;
    else process.env.DD_API_KEY = previousApiKey;
  }
}

test('valid signed app logs are rebuilt from an allowlist before the fixed US5 intake', async () => {
  const record = applicationRecord({
    participant_id: 'participant-private', session_id: 'session-private', share_id: 'share-private',
    name: 'PRIVATE NAME', phone: '01012345678', token: 'private-token',
    request: { authorization: 'Bearer private' }, response: { address: 'PRIVATE ADDRESS' },
  });
  const body = JSON.stringify([envelope(record)]);
  const { response, calls } = await invoke(body);
  assert.equal(response.statusCode, 200);
  assert.deepEqual(JSON.parse(response.body), { accepted: 1 });
  assert.equal(calls.length, 1);
  assert.equal(calls[0][0], handler._test.DATADOG_INTAKE);
  assert.equal(calls[0][1].headers['DD-API-KEY'], API_KEY);
  assert.ok(calls[0][1].signal instanceof AbortSignal);
  const sent = JSON.parse(calls[0][1].body);
  assert.deepEqual(sent, [{
    '@timestamp': '2026-09-29T07:00:00.000Z', message: 'api_request', event: 'api_request',
    service: 'gemini-dino-jump', env: 'production', campaign: 'gemini_dino_campus_2026',
    version: 'dpl_private',
    ddtags: 'env:production,campaign:gemini_dino_campus_2026,version:dpl_private',
    route: '/api/game-sessions/{id}/finish', method: 'POST', status: 'info',
    http: { status_code: 200 },
    duration_ms: 125, request_id: '643af4e3-975a-4cc7-9e7a-1eda11539d90',
    outcome: 'success', operation_outcome: 'completed', error_class: 'none',
  }]);
  assert.doesNotMatch(calls[0][1].body, /participant-private|session-private|share-private|PRIVATE NAME|PRIVATE ADDRESS|010123|Bearer|proxy|referer|clientIp|deploymentId|projectId/i);
});

test('actual preview campaign is accepted without requiring the optional stderr type', async () => {
  const preview = applicationRecord({
    env: 'preview', campaign: 'gemini_dino_phase1_test', deployment: 'dpl_preview',
  });
  const body = JSON.stringify([envelope(preview, {
    environment: 'preview', deploymentId: 'dpl_preview', type: undefined,
  })]);
  const { response, calls } = await invoke(body);
  assert.deepEqual(JSON.parse(response.body), { accepted: 1 });
  const sent = JSON.parse(calls[0][1].body)[0];
  assert.equal(sent.message, 'api_request');
  assert.equal(sent.version, 'dpl_preview');
  assert.equal(sent.ddtags, 'env:preview,campaign:gemini_dino_phase1_test,version:dpl_preview');
});

test('Datadog status is severity while HTTP status remains queryable as http.status_code', () => {
  const warning = handler._test.scrubLog(envelope(applicationRecord({
    status: 409, outcome: 'client_error', operation_outcome: 'failed', error_class: 'domain',
    error_code: 'CAMPAIGN_CLOSED',
  })));
  const failure = handler._test.scrubLog(envelope(applicationRecord({
    status: 503, outcome: 'server_error', operation_outcome: 'failed', error_class: 'database',
    error_code: 'SERVICE_UNAVAILABLE', database_failure: 'connection',
  })));
  assert.equal(warning.status, 'warn');
  assert.deepEqual(warning.http, { status_code: 409 });
  assert.equal(failure.status, 'error');
  assert.deepEqual(failure.http, { status_code: 503 });
});

test('an invalid signature is rejected before malformed JSON is parsed', async () => {
  const { response, calls } = await invoke('{not-json', { signature: '0'.repeat(40) });
  assert.equal(response.statusCode, 403);
  assert.deepEqual(JSON.parse(response.body), { error: 'invalid_signature' });
  assert.equal(calls.length, 0);
});

test('validly signed malformed JSON is rejected without forwarding', async () => {
  const { response, calls } = await invoke('{not-json');
  assert.equal(response.statusCode, 400);
  assert.deepEqual(JSON.parse(response.body), { error: 'invalid_json' });
  assert.equal(calls.length, 0);
});

test('the raw request body is capped at two MiB even without a trustworthy content length', async () => {
  const oversized = Buffer.alloc(handler._test.MAX_BODY_BYTES + 1, 0x61);
  const { response, calls } = await invoke(oversized, { contentLength: 1 });
  assert.equal(response.statusCode, 413);
  assert.deepEqual(JSON.parse(response.body), { error: 'body_too_large' });
  assert.equal(calls.length, 0);
});

test('unrelated projects, environment mismatches, campaigns and unknown routes are filtered', async () => {
  const batch = [
    envelope(applicationRecord(), { projectId: 'prj_other' }),
    envelope(applicationRecord({ env: 'preview' })),
    envelope(applicationRecord({ env: 'preview', campaign: 'gemini_dino_phase1_test' })),
    envelope(applicationRecord({ campaign: 'private_campaign' })),
    envelope(applicationRecord({ deployment: 'dpl_other' })),
    envelope(applicationRecord({ route: '/api/unknown' })),
    envelope(applicationRecord(), { source: 'build' }),
    envelope(applicationRecord(), { type: 'stdout' }),
  ];
  const { response, calls } = await invoke(JSON.stringify(batch));
  assert.equal(response.statusCode, 200);
  assert.deepEqual(JSON.parse(response.body), { accepted: 0 });
  assert.equal(calls.length, 0);
});

test('Datadog failure returns a retryable gateway error without echoing key or payload', async () => {
  const calls = [];
  const body = JSON.stringify([envelope()]);
  const { response } = await invoke(body, {
    fetch: async (...args) => { calls.push(args); return { ok: false, status: 503 }; },
  });
  assert.equal(response.statusCode, 502);
  assert.deepEqual(JSON.parse(response.body), { error: 'upstream_failed' });
  assert.equal(calls.length, 1);
  assert.doesNotMatch(response.body, /datadog|api.?key|request_id|campaign/i);
});

test('source contains no console logging or dynamic outbound endpoint', () => {
  assert.doesNotMatch(source, /console\.|process\.env\.(?!VERCEL_DRAIN_SECRET|DD_API_KEY)/);
  assert.match(source, /https:\/\/http-intake\.logs\.us5\.datadoghq\.com\/api\/v2\/logs/);
  assert.match(source, /crypto\.timingSafeEqual/);
  assert.deepEqual(Object.keys(sourceConfig.campaignsByEnvironment).sort(), ['preview', 'production']);
});
