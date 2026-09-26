/** Cookie-authenticated Phase 1 API client. Participant secrets never enter JS storage. */

function createRequestId(prefix = 'req') {
  if (globalThis.crypto?.randomUUID) return `${prefix}_${crypto.randomUUID()}`;
  return `${prefix}_${Date.now()}_${Math.random().toString(36).slice(2)}`;
}

export class ApiError extends Error {
  constructor(message, status, data = {}) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.data = data;
  }
}

async function request(endpoint, options = {}) {
  const headers = new Headers(options.headers || {});
  if (options.body != null && !(options.body instanceof FormData)) headers.set('Content-Type', 'application/json');
  if (options.idempotent) headers.set('Idempotency-Key', options.idempotencyKey || createRequestId('idem'));
  const fetchOptions = { ...options, credentials: 'same-origin', headers };
  let response;
  try {
    response = await fetch(endpoint, fetchOptions);
  } catch (error) {
    if (!options.idempotent) throw error;
    response = await fetch(endpoint, fetchOptions);
  }
  const data = await response.json().catch(() => ({}));
  if (!response.ok) throw new ApiError(data.message || data.error || '요청을 처리하지 못했습니다.', response.status, data);
  return data;
}

export const api = {
  participant: null,
  config: null,
  trackingContext: { observationId: null, visitSessionId: null },
  request,
  createRequestId,

  setTrackingContext(observationId, visitSessionId) {
    this.trackingContext = { observationId: observationId || null, visitSessionId: visitSessionId || null };
  },

  async getConfig() { this.config = await request('/api/config'); return this.config; },
  startObservation(payload) {
    return request('/api/observations', { method: 'POST', idempotent: true, idempotencyKey: payload.event_id, keepalive: true, body: JSON.stringify(payload) });
  },
  async initParticipant({ inviteCode = null, observationId = null, bootstrapToken = null, linkKind = null, channel = null, shareId = null } = {}) {
    const data = await request('/api/participants/anonymous', { method: 'POST', idempotent: true, body: JSON.stringify({ invite_code: inviteCode, observation_id: observationId, bootstrap_token: bootstrapToken, link_kind: linkKind, channel, share_id: shareId }) });
    this.participant = data.participant || null;
    return data;
  },
  getMe() { return request('/api/me'); },
  getCampaign() { return request('/api/campaign'); },
  updateProfile(profile) { return request('/api/me/profile', { method: 'PATCH', idempotent: true, body: JSON.stringify(profile) }); },
  getRankingProfile() { return request('/api/ranking/profile'); },
  submitTop3Profile(profile) {
    const eventId = createRequestId('evt');
    return request('/api/ranking/profile', { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ ...profile, event_id: eventId }) });
  },
  createSession() {
    const eventId = createRequestId('evt');
    return request('/api/game-sessions', {
      method: 'POST', idempotent: true, idempotencyKey: eventId,
      body: JSON.stringify({
        event_id: eventId,
        observation_id: this.trackingContext.observationId,
        visit_session_id: this.trackingContext.visitSessionId,
      }),
    });
  },
  startSession(sessionId) {
    const eventId = createRequestId('evt');
    return request(`/api/game-sessions/${encodeURIComponent(sessionId)}/start`, { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ event_id: eventId }) });
  },
  checkpointSession(sessionId, tick, stage = null) {
    const eventId = createRequestId('evt');
    return request(`/api/game-sessions/${encodeURIComponent(sessionId)}/checkpoint`, { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ tick, stage, event_id: eventId }) });
  },
  finishSession(sessionId, result, idempotencyKey) {
    return request(`/api/game-sessions/${encodeURIComponent(sessionId)}/finish`, { method: 'POST', idempotent: true, idempotencyKey, body: JSON.stringify({ ...result, event_id: idempotencyKey }) });
  },
  reportSessionFault(sessionId, fault, idempotencyKey) {
    return request(`/api/game-sessions/${encodeURIComponent(sessionId)}/fault`, { method: 'POST', idempotent: true, idempotencyKey, body: JSON.stringify({ ...fault, event_id: idempotencyKey }) });
  },
  getSession(sessionId) { return request(`/api/game-sessions/${encodeURIComponent(sessionId)}`); },
  getLeaderboard() { return request('/api/leaderboard'); },
  getDraw() { return request('/api/draws/me'); },
  drawPouch(pouchIndex) {
    const eventId = createRequestId('evt');
    return request('/api/draws', { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ pouch_index: pouchIndex, event_id: eventId }) });
  },
  completeScratch(drawId, idempotencyKey = null) {
    const eventId = idempotencyKey || createRequestId('evt');
    return request(`/api/draws/${encodeURIComponent(drawId)}/scratch-complete`, { method: 'PATCH', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ event_id: eventId }) });
  },
  getClaims() { return request('/api/claims'); },
  getClaimDraft(claimId) { return request(`/api/claims/${encodeURIComponent(claimId)}/draft`); },
  saveClaimDraft(claimId, payload) {
    const eventId = createRequestId('evt');
    return request(`/api/claims/${encodeURIComponent(claimId)}/draft`, { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify(payload) });
  },
  submitClaim(claimId, payload) {
    const eventId = createRequestId('evt');
    return request(`/api/claims/${encodeURIComponent(claimId)}/submit`, { method: 'POST', idempotent: true, idempotencyKey: eventId, body: JSON.stringify({ ...payload, event_id: eventId }) });
  },
  getReferralInfo() { return request('/api/referrals/me'); },
  qualifyReferral(payload) {
    return request('/api/referrals/qualify', { method: 'POST', idempotent: true, idempotencyKey: payload.event_id, body: JSON.stringify(payload) });
  },
  acknowledgeCooldown(cooldownUntil) {
    return request('/api/referrals/cooldown-notice/ack', { method: 'POST', idempotent: true, body: JSON.stringify({ cooldown_until: cooldownUntil }) });
  },
  postEvents(events, { keepalive = false, idempotencyKey = null } = {}) {
    if (!events.length) return Promise.resolve({ accepted: 0 });
    const batchKey = idempotencyKey || createRequestId('batch');
    return request('/api/events/batch', { method: 'POST', idempotent: true, idempotencyKey: batchKey, keepalive, body: JSON.stringify({ events }) });
  },
};
