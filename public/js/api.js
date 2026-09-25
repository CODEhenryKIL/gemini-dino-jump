/** Backend API client. Raw participant tokens only travel in Authorization. */
const TOKEN_KEY = 'gemini_dino_token';
const PARTICIPANT_KEY = 'gemini_dino_participant';
const PENDING_FINISH_KEY = 'gemini_dino_pending_finish';
const PENDING_CREATE_KEY = 'gemini_dino_pending_create';

function readJson(storage, key) { try { return JSON.parse(storage.getItem(key) || 'null'); } catch { return null; } }
function randomId(prefix = 'req') { return `${prefix}_${crypto.randomUUID ? crypto.randomUUID() : `${Date.now()}_${Math.random().toString(16).slice(2)}`}`; }

export const api = {
  token: localStorage.getItem(TOKEN_KEY) || '',
  participant: readJson(localStorage, PARTICIPANT_KEY),
  config: null,
  setSession(participant, token = '') {
    this.participant = participant || null;
    if (token) { this.token = token; localStorage.setItem(TOKEN_KEY, token); }
    if (participant) localStorage.setItem(PARTICIPANT_KEY, JSON.stringify(participant));
  },
  clearSession() { this.token = ''; this.participant = null; localStorage.removeItem(TOKEN_KEY); localStorage.removeItem(PARTICIPANT_KEY); },
  async request(endpoint, options = {}) {
    const headers = { Accept: 'application/json', ...(options.body ? { 'Content-Type': 'application/json' } : {}), ...(options.headers || {}) };
    if (this.token && options.auth !== false) headers.Authorization = `Bearer ${this.token}`;
    const response = await fetch(endpoint, { ...options, headers, cache: 'no-store', credentials: 'same-origin' });
    const data = await response.json().catch(() => ({}));
    if (!response.ok) { const error = new Error(data.message || '요청을 처리하지 못했습니다.'); error.code = data.error || 'API_REQUEST_FAILED'; error.status = response.status; error.requestId = data.request_id; throw error; }
    return data;
  },
  async getConfig(options) { this.config = await this.request('/api/config', { ...options, auth: false }); return this.config; },
  getCampaign: (options) => api.request('/api/campaign', options),
  async initParticipant(referralCode = null, channel = null, options = {}) {
    if (this.token) {
      try { const me = await this.getMe(options); if (me.participant) this.setSession(me.participant); if (referralCode) me.referral_applied = (await this.attributeReferral(referralCode, options)).applied; return me; }
      catch (error) { if (error.status !== 401) throw error; this.clearSession(); }
    }
    const body = {}; if (referralCode) body.referral_code = referralCode; if (channel) body.channel = channel;
    const data = await this.request('/api/participants/anonymous', { method: 'POST', body: JSON.stringify(body), auth: false, signal: options.signal });
    this.setSession(data.participant, data.session_token); return data;
  },
  getMe: (options) => api.request('/api/me', options),
  updateProfile: (profile, options) => api.request('/api/me/profile', { method: 'PATCH', body: JSON.stringify(profile), ...options }),
  createSession(options = {}) { const key = options.idempotencyKey || sessionStorage.getItem(PENDING_CREATE_KEY) || randomId('game'); sessionStorage.setItem(PENDING_CREATE_KEY,key); return this.request('/api/game-sessions', { method: 'POST', headers: { 'Idempotency-Key': key }, body: JSON.stringify({ idempotency_key: key }), signal: options.signal }); },
  async startSession(id, options) { const result = await api.request(`/api/game-sessions/${encodeURIComponent(id)}/start`, { method: 'POST', body: '{}', ...options }); sessionStorage.removeItem(PENDING_CREATE_KEY); return result; },
  async abortSession(id, options) { try { return await api.request(`/api/game-sessions/${encodeURIComponent(id)}/abort`, { method: 'POST', body: '{}', ...options }); } finally { sessionStorage.removeItem(PENDING_CREATE_KEY); } },
  getSession: (id, options) => api.request(`/api/game-sessions/${encodeURIComponent(id)}`, options),
  async finishSession(sessionId, result, options = {}) {
    const payload = { session_id: sessionId, score: result.score, valid_ticks: result.valid_ticks ?? result.ticks, jump_ticks: result.jump_ticks || [], version: options.version || this.config?.game_version };
    localStorage.setItem(PENDING_FINISH_KEY, JSON.stringify(payload));
    const data = await this.request(`/api/game-sessions/${encodeURIComponent(sessionId)}/finish`, { method: 'POST', body: JSON.stringify(payload), signal: options.signal });
    localStorage.removeItem(PENDING_FINISH_KEY); return data;
  },
  getPendingFinish: () => readJson(localStorage, PENDING_FINISH_KEY),
  clearPendingFinish: () => localStorage.removeItem(PENDING_FINISH_KEY),
  getLeaderboard: (options) => api.request('/api/leaderboard?limit=100', options),
  drawPouch: (id, pouch, options) => api.request('/api/draws', { method: 'POST', body: JSON.stringify({ session_id: id, pouch_index: pouch }), ...options }),
  completeScratch: (id, options) => api.request(`/api/draws/${encodeURIComponent(id)}/scratch-complete`, { method: 'PATCH', body: '{}', ...options }),
  getClaims: (options) => api.request('/api/claims', options),
  submitClaim: (id, values, options) => api.request(`/api/claims/${encodeURIComponent(id)}/submit`, { method: 'POST', body: JSON.stringify({ ...values, consent: true }), ...options }),
  getReferralInfo: (options) => api.request('/api/referrals/me', options),
  attributeReferral: (code, options) => api.request('/api/referrals/attribute', { method: 'POST', body: JSON.stringify({ referral_code: code }), ...options }),
  verifyBenefit: (options) => api.request('/api/benefit-verifications', { method: 'POST', body: '{}', ...options }),
  sendEvents: (events, options) => api.request('/api/events', { method: 'POST', body: JSON.stringify({ events }), keepalive: true, ...options }).catch(() => null),
  newId: randomId
};
