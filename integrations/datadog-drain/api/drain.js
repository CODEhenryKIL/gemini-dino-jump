'use strict';

const crypto = require('node:crypto');
const sourceConfig = require('../source-config.js');

const MAX_BODY_BYTES = 2 * 1024 * 1024;
const MAX_BATCH_ITEMS = 1000;
const MAX_MESSAGE_BYTES = 4096;
const DATADOG_TIMEOUT_MS = 5000;
const DATADOG_INTAKE = 'https://http-intake.logs.us5.datadoghq.com/api/v2/logs';

const ROUTES = new Set([
  '/api/shared/game_constants.json', '/api/health', '/api/config', '/api/webhooks/kakao-share',
  '/api/observations', '/api/participants/anonymous', '/api/me', '/api/me/profile',
  '/api/referrals/me', '/api/referrals/qualify', '/api/referrals/share-reward',
  '/api/referrals/share-intents', '/api/referrals/share-intents/{id}',
  '/api/referrals/cooldown-notice/ack', '/api/game-sessions', '/api/game-sessions/{id}',
  '/api/game-sessions/{id}/start', '/api/game-sessions/{id}/checkpoint',
  '/api/game-sessions/{id}/finish', '/api/game-sessions/{id}/fault',
  '/api/game-sessions/{id}/abandon', '/api/leaderboard', '/api/ranking/profile',
  '/api/draws/me', '/api/draws', '/api/draws/{id}/scratch-complete', '/api/claims',
  '/api/claims/{id}/draft', '/api/claims/{id}/submit', '/api/events/batch',
  '/api/admin/session', '/api/admin/overview', '/api/admin/claims', '/api/admin/claims/{id}',
  '/api/admin/analytics/events', '/api/admin/game-faults', '/api/admin/game-faults/{id}',
  '/api/admin/ranking-snapshots', '/api/admin/ranking-snapshots/{id}/reviews',
  '/api/admin/ranking-snapshots/{id}/finalize', '/api/admin/ranking-contacts',
  '/api/admin/participants/{id}', '/api/admin/campaign',
]);
const METHODS = new Set(['GET', 'HEAD', 'POST', 'PATCH', 'OPTIONS']);
const OUTCOMES = new Set(['success', 'client_error', 'server_error']);
const OPERATION_OUTCOMES = new Set([
  'completed', 'failed', 'webhook_duplicate', 'webhook_expired', 'webhook_rejected',
  'webhook_reward_granted', 'webhook_reward_blocked', 'webhook_no_reward',
  'webhook_not_eligible', 'webhook_processing_failed',
]);
const ERROR_CLASSES = new Set([
  'none', 'validation', 'authentication', 'rate_limit', 'domain', 'database',
  'configuration', 'internal',
]);
const DATABASE_FAILURES = new Set(['pool_wait', 'connection', 'health_check', 'configuration']);
const LOG_TYPES = new Set(['stdout', 'stderr']);
const REQUEST_UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$/i;
const DEPLOYMENT = /^[A-Za-z0-9_.:-]{1,128}$/;
const ERROR_CODE = /^[A-Z][A-Z0-9_]{0,63}$/;
const SQLSTATE = /^[A-Z0-9]{5}$/;

class BodyTooLarge extends Error {}

function json(response, status, payload) {
  response.statusCode = status;
  response.setHeader('Content-Type', 'application/json; charset=utf-8');
  response.setHeader('Cache-Control', 'no-store');
  response.end(JSON.stringify(payload));
}

async function readRawBody(request) {
  const declared = Number(request.headers?.['content-length']);
  if (Number.isFinite(declared) && declared > MAX_BODY_BYTES) throw new BodyTooLarge();
  if (Buffer.isBuffer(request.rawBody)) {
    if (request.rawBody.length > MAX_BODY_BYTES) throw new BodyTooLarge();
    return request.rawBody;
  }
  const chunks = [];
  let size = 0;
  for await (const value of request) {
    const chunk = Buffer.isBuffer(value) ? value : Buffer.from(value);
    size += chunk.length;
    if (size > MAX_BODY_BYTES) throw new BodyTooLarge();
    chunks.push(chunk);
  }
  return Buffer.concat(chunks, size);
}

function validSignature(rawBody, supplied, secret) {
  if (typeof supplied !== 'string' || !/^[0-9a-f]{40}$/i.test(supplied)) return false;
  const expected = crypto.createHmac('sha1', secret).update(rawBody).digest();
  const actual = Buffer.from(supplied, 'hex');
  return actual.length === expected.length && crypto.timingSafeEqual(actual, expected);
}

function allowedCampaign(environment, campaign) {
  const campaigns = sourceConfig.campaignsByEnvironment[environment];
  return Array.isArray(campaigns) && campaigns.includes(campaign);
}

function severity(outcome) {
  if (outcome === 'server_error') return 'error';
  if (outcome === 'client_error') return 'warn';
  return 'info';
}

function scrubLog(log) {
  if (!log || typeof log !== 'object' || Array.isArray(log)) return null;
  if (log.source !== 'lambda') return null;
  if (log.projectId !== sourceConfig.projectId) return null;
  if (!Object.hasOwn(sourceConfig.campaignsByEnvironment, log.environment)) return null;
  if (typeof log.message !== 'string' || Buffer.byteLength(log.message, 'utf8') > MAX_MESSAGE_BYTES) return null;

  let record;
  try { record = JSON.parse(log.message); } catch (_) { return null; }
  if (!record || typeof record !== 'object' || Array.isArray(record)) return null;
  if (record.event !== 'api_request' || record.service !== 'gemini-dino-jump') return null;
  if (log.type != null && !LOG_TYPES.has(log.type)) return null;
  if (record.env !== log.environment || !allowedCampaign(record.env, record.campaign)) return null;
  if (!DEPLOYMENT.test(record.deployment || '') || record.deployment !== log.deploymentId) return null;
  if (!ROUTES.has(record.route) || record.route === '/api/unknown') return null;
  if (!METHODS.has(record.method) || !OUTCOMES.has(record.outcome)) return null;
  if (!OPERATION_OUTCOMES.has(record.operation_outcome) || !ERROR_CLASSES.has(record.error_class)) return null;
  if (!REQUEST_UUID.test(record.request_id || '')) return null;
  if (!Number.isInteger(record.status) || record.status < 100 || record.status > 599) return null;
  if (!Number.isInteger(record.duration_ms) || record.duration_ms < 0 || record.duration_ms > 60000) return null;
  if (!Number.isInteger(log.timestamp) || log.timestamp < 946684800000 || log.timestamp > 4133980800000) return null;

  const clean = {
    '@timestamp': new Date(log.timestamp).toISOString(),
    message: 'api_request',
    event: 'api_request',
    service: 'gemini-dino-jump',
    env: record.env,
    campaign: record.campaign,
    version: record.deployment,
    ddtags: `env:${record.env},campaign:${record.campaign},version:${record.deployment}`,
    route: record.route,
    method: record.method,
    status: severity(record.outcome),
    http: { status_code: record.status },
    duration_ms: record.duration_ms,
    request_id: record.request_id.toLowerCase(),
    outcome: record.outcome,
    operation_outcome: record.operation_outcome,
    error_class: record.error_class,
  };
  if (record.error_code != null && ERROR_CODE.test(record.error_code)) clean.error_code = record.error_code;
  if (record.database_failure != null
      && (DATABASE_FAILURES.has(record.database_failure) || SQLSTATE.test(record.database_failure))) {
    clean.database_failure = record.database_failure;
  }
  return clean;
}

async function sendToDatadog(records, apiKey) {
  const controller = new AbortController();
  const timer = setTimeout(() => controller.abort(), DATADOG_TIMEOUT_MS);
  try {
    const response = await fetch(DATADOG_INTAKE, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        'DD-API-KEY': apiKey,
      },
      body: JSON.stringify(records),
      signal: controller.signal,
    });
    return response.ok;
  } catch (_) {
    return false;
  } finally {
    clearTimeout(timer);
  }
}

async function handler(request, response) {
  if (request.method !== 'POST') return json(response, 405, { error: 'method_not_allowed' });
  const secret = process.env.VERCEL_DRAIN_SECRET;
  const apiKey = process.env.DD_API_KEY;
  if (!secret || !apiKey) return json(response, 503, { error: 'not_configured' });

  let rawBody;
  try { rawBody = await readRawBody(request); }
  catch (error) {
    return json(response, error instanceof BodyTooLarge ? 413 : 400, {
      error: error instanceof BodyTooLarge ? 'body_too_large' : 'invalid_body',
    });
  }
  if (!validSignature(rawBody, request.headers?.['x-vercel-signature'], secret)) {
    return json(response, 403, { error: 'invalid_signature' });
  }

  let batch;
  try { batch = JSON.parse(rawBody.toString('utf8')); }
  catch (_) { return json(response, 400, { error: 'invalid_json' }); }
  if (!Array.isArray(batch) || batch.length > MAX_BATCH_ITEMS) {
    return json(response, 400, { error: 'invalid_batch' });
  }
  const records = batch.map(scrubLog).filter(Boolean);
  if (!records.length) return json(response, 200, { accepted: 0 });
  if (!await sendToDatadog(records, apiKey)) return json(response, 502, { error: 'upstream_failed' });
  return json(response, 200, { accepted: records.length });
}

module.exports = handler;
module.exports.config = { api: { bodyParser: false } };
module.exports._test = {
  DATADOG_INTAKE, DATADOG_TIMEOUT_MS, MAX_BODY_BYTES, readRawBody, validSignature, scrubLog,
};
