/**
 * Backend API Client with Automatic Session Persistence and Auth
 */

const TOKEN_KEY = 'gemini_dino_token';
const PARTICIPANT_KEY = 'gemini_dino_participant';

export const api = {
  token: localStorage.getItem(TOKEN_KEY) || '',
  participant: JSON.parse(localStorage.getItem(PARTICIPANT_KEY) || 'null'),

  setSession(participant) {
    this.participant = participant;
    this.token = participant.session_token;
    localStorage.setItem(TOKEN_KEY, this.token);
    localStorage.setItem(PARTICIPANT_KEY, JSON.stringify(participant));
  },

  async request(endpoint, options = {}) {
    const headers = {
      'Content-Type': 'application/json',
      ...(options.headers || {})
    };

    if (this.token) {
      headers['Authorization'] = `Bearer ${this.token}`;
    }

    const res = await fetch(endpoint, {
      ...options,
      headers
    });

    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const error = new Error(data.message || data.error || 'API_REQUEST_FAILED');
      error.status = res.status;
      error.data = data;
      throw error;
    }
    return data;
  },

  async getCampaign() {
    return this.request('/api/campaign');
  },

  async initParticipant(inviteCode = null) {
    const body = {};
    if (this.token) body.session_token = this.token;
    if (inviteCode) body.invite_code = inviteCode;

    const data = await this.request('/api/participants/anonymous', {
      method: 'POST',
      body: JSON.stringify(body)
    });
    this.setSession(data);
    return data;
  },

  async getMe() {
    return this.request('/api/me');
  },

  async updateProfile({ nickname, is_public }) {
    return this.request('/api/me/profile', {
      method: 'PATCH',
      body: JSON.stringify({ nickname, is_public })
    });
  },

  async createSession() {
    return this.request('/api/game-sessions', {
      method: 'POST'
    });
  },

  async startSession(sessionId) {
    return this.request(`/api/game-sessions/${sessionId}/start`, {
      method: 'POST'
    });
  },

  async finishSession(sessionId, { score, ticks, jump_ticks }) {
    return this.request(`/api/game-sessions/${sessionId}/finish`, {
      method: 'POST',
      body: JSON.stringify({ score, ticks, jump_ticks })
    });
  },

  async getSession(sessionId) {
    return this.request(`/api/game-sessions/${sessionId}`);
  },

  async getLeaderboard() {
    return this.request('/api/leaderboard');
  },

  async drawPouch(sessionId, pouchIndex) {
    return this.request('/api/draws', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId, pouch_index: pouchIndex })
    });
  },

  async completeScratch(drawId) {
    return this.request(`/api/draws/${drawId}/scratch-complete`, {
      method: 'PATCH'
    });
  },

  async getClaims() {
    return this.request('/api/claims');
  },

  async submitClaim(claimId, { recipient_name, contact_phone, shipping_address }) {
    return this.request(`/api/claims/${claimId}/submit`, {
      method: 'POST',
      body: JSON.stringify({ recipient_name, contact_phone, shipping_address })
    });
  },

  async getReferralInfo() {
    return this.request('/api/referrals/me');
  },

  async verifyBenefit() {
    return this.request('/api/benefit-verifications', {
      method: 'POST'
    });
  },

  async logEvent(eventName, payload = {}) {
    return this.request('/api/events', {
      method: 'POST',
      body: JSON.stringify({ event_name: eventName, payload })
    }).catch(() => {});
  }
};
