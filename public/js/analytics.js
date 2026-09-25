import { api } from './api.js';

const EVENT_ALLOWLIST = new Set([
  'entry_viewed', 'participant_ready', 'loading_data_ready', 'loading_intro_completed', 'loading_ready', 'loading_checkpoint', 'screen_entered', 'screen_left',
  'game_cta_clicked', 'game_start_approved', 'game_checkpoint', 'game_coin_collected', 'game_heart_collected', 'game_revived', 'game_completed',
  'game_fault_reported', 'game_recovered', 'ranking_viewed', 'top3_profile_started',
  'top3_profile_submitted', 'invite_cta_viewed', 'share_attempted', 'invite_visit_interacted',
  'invite_visit_qualified', 'invite_visit_rejected', 'draw_entered', 'pouch_selected',
  'scratch_reveal_requested', 'scratch_started', 'scratch_completed', 'draw_result_viewed', 'claim_form_started',
  'claim_form_submitted', 'benefit_viewed', 'gemini_cta_viewed', 'gemini_cta_clicked',
  'content_viewed', 'content_clicked', 'notion_redirect_requested',
]);
const SAFE_DIMENSIONS = new Set([
  'previous_screen', 'source', 'link_kind', 'channel', 'campaign_code', 'content', 'position',
  'action', 'status', 'reason', 'stage', 'bucket', 'result_type', 'prize_kind', 'share_method',
  'checkpoint', 'is_new', 'is_synthetic', 'connected', 'observed', 'score', 'rank',
  'game_version', 'draw_status', 'claim_type', 'share_id', 'end_reason', 'coin_count',
  'coin_score', 'hearts', 'revive_count', 'tick', 'reduced_motion',
]);

function cleanDimensions(payload = {}) {
  const clean = {};
  for (const [key, value] of Object.entries(payload)) {
    if (!SAFE_DIMENSIONS.has(key)) continue;
    if (typeof value === 'string' && value.length) clean[key] = value.slice(0, 80);
    else if (typeof value === 'number' && Number.isFinite(value)) clean[key] = value;
    else if (typeof value === 'boolean') clean[key] = value;
  }
  return clean;
}

class Analytics {
  constructor() {
    this.observationId = api.createRequestId('obs');
    this.visitSessionId = this.sessionGet('dino_visit_id') || api.createRequestId('visit');
    this.sessionSet('dino_visit_id', this.visitSessionId);
    this.queue = [];
    this.screen = 'loading';
    this.screenViewId = api.createRequestId('screen');
    this.screenStartedAt = performance.now();
    this.visibleStartedAt = document.hidden ? null : performance.now();
    this.activeMs = 0;
    this.lastCheckpoint = 0;
    this.flushing = false;
    this.observationReady = false;
    this.loadingTransition = null;
    this.loadingMilestones = new Set();
    this.interval = setInterval(() => { this.checkpoint(); this.flush(); }, 2000);
    this.onVisibility = () => {
      const now = performance.now();
      if (document.hidden && this.visibleStartedAt != null) {
        this.activeMs += now - this.visibleStartedAt;
        this.visibleStartedAt = null;
        this.recordLoadingCheckpoint(true);
        this.flush(true);
      } else if (!document.hidden && this.visibleStartedAt == null) {
        this.visibleStartedAt = now;
      }
    };
    this.onPageHide = (event) => {
      this.recordLoadingCheckpoint(true);
      if (event.persisted) { this.flush(true); return; }
      this.leaveScreen('pagehide');
      this.flush(true);
    };
    this.onPageShow = (event) => {
      if (event.persisted && !document.hidden && this.visibleStartedAt == null) this.visibleStartedAt = performance.now();
    };
    document.addEventListener('visibilitychange', this.onVisibility);
    window.addEventListener('pagehide', this.onPageHide);
    window.addEventListener('pageshow', this.onPageShow);
    this.track('entry_viewed', { connected: false });
  }

  sessionGet(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }
  sessionSet(key, value) { try { sessionStorage.setItem(key, value); } catch (_) {} }

  track(name, dimensions = {}, extra = {}) {
    if (!EVENT_ALLOWLIST.has(name) || this.queue.length >= 40) return;
    const event = {
      event_id: api.createRequestId('evt'),
      name,
      occurred_at: new Date().toISOString(),
      screen: extra.screen || this.screen || 'unknown',
      screen_view_id: this.screenViewId,
      visit_session_id: this.visitSessionId,
      observation_id: this.observationId,
      game_session_id: extra.gameSessionId || undefined,
      active_ms: Number.isFinite(extra.activeMs) ? Math.round(extra.activeMs) : this.currentActiveMs(),
      dimensions: cleanDimensions(dimensions),
    };
    if (extra.screenViewId) event.screen_view_id = extra.screenViewId;
    this.queue.push(event);
    if (this.queue.length >= 10) this.flush();
  }

  setParticipantReady(meta = {}) {
    api.setTrackingContext(this.observationId, this.visitSessionId);
    this.recordLoadingCheckpoint(true);
    this.track('participant_ready', { connected: true, is_new: Boolean(meta.is_new) });
    this.flush();
  }

  setLoadingReady() {
    const transition = this.loadingTransition;
    const renderMs = transition && transition.visible && !document.hidden
      ? Math.max(0, performance.now() - transition.startedAt)
      : 0;
    this.track('loading_ready', { connected: true }, {
      screen: 'loading',
      screenViewId: transition?.screenViewId,
      activeMs: Math.round((transition?.activeMs || 0) + renderMs),
    });
    this.loadingTransition = null;
    this.flush();
  }

  trackLoadingMilestone(name, dimensions = {}) {
    if (this.loadingMilestones.has(name)) return;
    this.loadingMilestones.add(name);
    this.recordLoadingCheckpoint(true);
    this.track(name, dimensions, {
      screen: 'loading',
      screenViewId: this.loadingTransition?.screenViewId || this.screenViewId,
      activeMs: this.loadingTransition?.activeMs || this.currentActiveMs(),
    });
    this.flush();
  }

  setLoadingDataReady(meta = {}) { this.trackLoadingMilestone('loading_data_ready', { connected: true, ...meta }); }
  setLoadingIntroCompleted(meta = {}) { this.trackLoadingMilestone('loading_intro_completed', meta); }

  setObservationReady() {
    this.observationReady = true;
    this.flush();
  }

  setEntryAttribution(dimensions = {}) {
    const entry = this.queue.find((event) => event.name === 'entry_viewed');
    if (entry) entry.dimensions = { ...entry.dimensions, ...cleanDimensions(dimensions) };
  }

  enterScreen(screen) {
    if (this.screen && this.screen !== screen) this.leaveScreen('navigation');
    this.screen = screen;
    this.screenViewId = api.createRequestId('screen');
    this.screenStartedAt = performance.now();
    this.activeMs = 0;
    this.visibleStartedAt = document.hidden ? null : performance.now();
    this.lastCheckpoint = 0;
    this.track('screen_entered');
  }

  currentActiveMs() {
    return Math.round(this.activeMs + (this.visibleStartedAt == null ? 0 : performance.now() - this.visibleStartedAt));
  }

  checkpoint() {
    if (document.hidden || !this.screen) return;
    const activeMs = this.currentActiveMs();
    const seconds = Math.floor(activeMs / 1000);
    const checkpoint = [1, 2, 3, 5, 10, 20, 30, 60].filter((mark) => seconds >= mark).pop();
    if (!checkpoint || checkpoint <= this.lastCheckpoint) return;
    this.lastCheckpoint = checkpoint;
    if (this.screen === 'game') this.track('game_checkpoint', { checkpoint }, { activeMs });
    else if (this.screen === 'loading') this.recordLoadingCheckpoint(false);
  }

  recordLoadingCheckpoint(force) {
    if (this.screen !== 'loading') return;
    const activeMs = this.currentActiveMs();
    const bucket = activeMs < 1000 ? '0-1s' : activeMs < 2000 ? '1-2s' : activeMs < 3000 ? '2-3s' : '3s+';
    if (!force && this.loadingBucket === bucket) return;
    if (this.loadingBucket === bucket && force) return;
    this.loadingBucket = bucket;
    this.track('loading_checkpoint', { checkpoint: Math.floor(activeMs / 1000), bucket }, { activeMs });
  }

  leaveScreen(reason) {
    if (!this.screen) return;
    const activeMs = this.currentActiveMs();
    if (this.screen === 'loading') {
      this.loadingTransition = {
        activeMs,
        screenViewId: this.screenViewId,
        startedAt: performance.now(),
        visible: !document.hidden,
      };
    }
    this.track('screen_left', { reason }, {
      activeMs,
    });
  }

  async flush(keepalive = false) {
    if (!this.observationReady || !this.queue.length || this.flushing) return;
    this.flushing = true;
    const events = this.queue.splice(0, 20);
    try {
      const result = await api.postEvents(events, { keepalive });
      if (result.rejected) console.warn('analytics_batch_rejected', { rejected: result.rejected });
    } catch (error) {
      const retryable = !error.status || error.status === 408 || error.status === 429 || error.status >= 500;
      if (retryable) this.queue.unshift(...events.slice(0, Math.max(0, 40 - this.queue.length)));
      else console.warn('analytics_batch_failed', { status: error.status, count: events.length });
    } finally {
      this.flushing = false;
    }
  }
}

export const analytics = new Analytics();
export { EVENT_ALLOWLIST, SAFE_DIMENSIONS };
