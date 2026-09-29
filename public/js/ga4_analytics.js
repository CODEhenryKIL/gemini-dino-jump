const MEASUREMENT_ID = /^G-[A-Z0-9]{6,20}$/;
const BUFFER_LIMIT = 12;
const DEDUP_LIMIT = 64;
const DEDUP_TTL_MS = 7 * 24 * 60 * 60 * 1000;
const DEDUP_STORAGE_PREFIX = 'dino_ga4_dedup_v1:';
const REGIONAL_CONSENT_DENIED = [
  'AT', 'BE', 'BG', 'CH', 'CY', 'CZ', 'DE', 'DK', 'EE', 'ES', 'FI', 'FR', 'GB', 'GR',
  'HR', 'HU', 'IE', 'IS', 'IT', 'LI', 'LT', 'LU', 'LV', 'MT', 'NL', 'NO', 'PL', 'PT',
  'RO', 'SE', 'SI', 'SK',
];

const SCREENS = new Set(['loading', 'home', 'game', 'result', 'draw', 'claims', 'ranking', 'invite', 'benefit']);
const SOURCES = new Set(['home', 'result', 'invite', 'claims', 'gemini', 'benefit']);
const POSITIONS = new Set(['benefit_main', 'benefit_guides']);
const LINK_KINDS = new Set(['initial', 'direct', 'retry_invite', 'record_share', 'draw_retry', 'prize_share', 'general_share']);
const CONTENTS = new Set(['study_note', 'job_photo']);
const SHARE_METHODS = new Set(['kakao', 'native', 'copy']);
const SHARE_STATUSES = new Set(['attempted', 'copied', 'share_sheet_closed', 'cancelled', 'failed', 'unavailable']);
const CLAIM_TYPES = new Set(['DRAW', 'RANKING']);
const RESULT_TYPES = new Set(['prize', 'benefit']);
const END_REASONS = new Set(['COLLISION', 'TIME_LIMIT', 'ABORTED']);
const GAME_STATUSES = new Set(['VERIFIED', 'REJECTED']);
const PLAY_TYPES = new Set(['first', 'retry']);
const CHANNELS = new Map([
  ['kakao', 'referral'],
  ['instagram', 'social'],
  ['campus_community', 'community'],
  ['campus_poster', 'qr'],
  ['direct', 'none'],
]);
const CAMPAIGNS = new Set(['dino_jump', 'dino_jump_2026', 'gemini_dino_jump']);
const CAMPAIGN_CONTENTS = new Set(['profile', 'story', 'poster', 'friend_invite', 'direct']);

const EVENT_NAMES = new Map([
  ['entry_viewed', 'entry_viewed'],
  ['loading_ready', 'loading_ready'],
  ['game_cta_clicked', 'game_cta_click'],
  ['game_start_approved', 'game_start'],
  ['game_completed', 'game_complete'],
  ['draw_cta_clicked', 'draw_cta_click'],
  ['draw_entered', 'draw_entered'],
  ['pouch_selected', 'pouch_selected'],
  ['scratch_started', 'scratch_started'],
  ['scratch_completed', 'scratch_complete'],
  ['draw_result_viewed', 'draw_result_view'],
  ['claim_form_started', 'claim_form_start'],
  ['claim_draft_saved', 'claim_draft_saved'],
  ['claim_form_submitted', 'claim_form_submit'],
  ['top3_profile_started', 'top3_profile_start'],
  ['top3_profile_submitted', 'top3_profile_submit'],
  ['invite_cta_viewed', 'invite_cta_view'],
  ['share_attempted', 'share_interaction'],
  ['benefit_viewed', 'benefit_view'],
  ['gemini_cta_viewed', 'gemini_cta_view'],
  ['gemini_cta_clicked', 'gemini_cta_click'],
  ['content_viewed', 'content_view'],
  ['content_clicked', 'content_click'],
  ['tutorial_viewed', 'tutorial_view'],
  ['tutorial_progressed', 'tutorial_progress'],
  ['tutorial_skipped', 'tutorial_skip'],
]);

const SUCCESS_EVENTS = new Set([
  'game_start_approved', 'game_completed', 'scratch_completed', 'draw_result_viewed', 'claim_draft_saved',
  'claim_form_submitted', 'top3_profile_submitted',
]);

function enumValue(value, allowed) {
  const normalized = typeof value === 'string' ? value : '';
  return allowed.has(normalized) ? normalized : undefined;
}

function boundedInteger(value, min, max) {
  const number = Number(value);
  return Number.isInteger(number) && number >= min && number <= max ? number : undefined;
}

function boundedNumber(value, min, max) {
  const number = Number(value);
  return Number.isFinite(number) && number >= min && number <= max
    ? Math.round(number * 10) / 10
    : undefined;
}

function gameVersion(value) {
  return typeof value === 'string' && /^\d{1,3}\.\d{1,3}\.\d{1,3}$/.test(value) ? value : undefined;
}

function fingerprint(value) {
  if (typeof value !== 'string' || !value) return '';
  let hash = 2166136261;
  for (let index = 0; index < value.length; index += 1) {
    hash ^= value.charCodeAt(index);
    hash = Math.imul(hash, 16777619);
  }
  return (hash >>> 0).toString(36);
}

function sanitizeParams(name, dimensions = {}, screen = '') {
  const params = {};
  const safeScreen = enumValue(screen, SCREENS);
  if (safeScreen) params.screen_name = safeScreen;
  const source = enumValue(dimensions.source, SOURCES);
  const position = enumValue(dimensions.position, POSITIONS);
  const linkKind = enumValue(dimensions.link_kind, LINK_KINDS);
  const content = enumValue(dimensions.content, CONTENTS);
  const shareMethod = enumValue(dimensions.share_method, SHARE_METHODS);
  const shareStatus = enumValue(dimensions.status, SHARE_STATUSES);
  const claimType = enumValue(dimensions.claim_type, CLAIM_TYPES);
  const resultType = enumValue(dimensions.result_type, RESULT_TYPES);
  const round = boundedInteger(dimensions.round_number, 1, 10);
  const step = boundedInteger(dimensions.tutorial_step, 1, 4);

  if (['game_cta_clicked', 'draw_cta_clicked'].includes(name) && source) params.source = source;
  if (name === 'game_start_approved') {
    const version = gameVersion(dimensions.game_version);
    const playType = enumValue(dimensions.play_type, PLAY_TYPES);
    if (version) params.game_version = version;
    if (playType) params.play_type = playType;
  }
  if (name === 'game_completed') {
    const version = gameVersion(dimensions.game_version);
    const score = boundedInteger(dimensions.score, 0, 1000000);
    const rank = boundedInteger(dimensions.rank, 0, 1000000);
    const reason = enumValue(dimensions.end_reason, END_REASONS);
    const status = enumValue(dimensions.status, GAME_STATUSES);
    const duration = boundedNumber(dimensions.duration_seconds, 1, 600);
    if (version) params.game_version = version;
    if (score !== undefined) params.score = score;
    if (rank !== undefined) params.rank = rank;
    if (reason) params.end_reason = reason;
    if (status) params.verification_status = status;
    if (duration !== undefined) params.duration_seconds = duration;
  }
  if (name === 'pouch_selected') {
    const pouch = typeof dimensions.action === 'string' && /^pouch_[0-2]$/.test(dimensions.action) ? dimensions.action : undefined;
    if (pouch) params.pouch = pouch;
    if (round !== undefined) params.round_number = round;
  }
  if (name === 'scratch_started' && round !== undefined) params.round_number = round;
  if (['scratch_completed', 'draw_result_viewed'].includes(name)) {
    if (resultType) params.result_type = resultType;
    if (round !== undefined) params.round_number = round;
  }
  if (['claim_form_started', 'claim_draft_saved', 'claim_form_submitted'].includes(name) && claimType) params.claim_type = claimType;
  if (name === 'share_attempted') {
    if (source) params.source = source;
    if (position) params.position = position;
    if (linkKind) params.link_kind = linkKind;
    if (content) params.content = content;
    if (shareMethod) params.share_method = shareMethod;
    if (shareStatus) params.share_status = shareStatus;
  }
  if (['gemini_cta_viewed', 'gemini_cta_clicked'].includes(name) && position) params.position = position;
  if (['content_viewed', 'content_clicked'].includes(name)) {
    if (content) params.content = content;
    if (position) params.position = position;
  }
  if (name.startsWith('tutorial_') && step !== undefined) params.tutorial_step = step;
  return params;
}

function captureAttribution(runtime) {
  const attribution = {};
  try {
    const search = new URL(runtime.location?.href || runtime.window?.location?.href || 'https://invalid.local/').searchParams;
    const source = search.get('utm_source') || search.get('channel');
    const medium = search.get('utm_medium');
    const expectedMedium = CHANNELS.get(source);
    if (expectedMedium && (!medium || medium === expectedMedium)) {
      attribution.campaign_source = source;
      attribution.campaign_medium = expectedMedium;
    }
    const campaign = search.get('utm_campaign') || search.get('campaign');
    if (CAMPAIGNS.has(campaign)) attribution.campaign_name = campaign;
    const campaignContent = search.get('utm_content');
    if (CAMPAIGN_CONTENTS.has(campaignContent)) attribution.campaign_content = campaignContent;
    const linkKind = search.get('link');
    if (LINK_KINDS.has(linkKind)) attribution.link_kind = linkKind;
  } catch (_) { /* Missing or malformed location carries no attribution. */ }
  return attribution;
}

function normalizeOrigin(value) {
  try {
    const url = new URL(value);
    return url.origin === value.replace(/\/$/, '') ? url.origin : null;
  } catch (_) { return null; }
}

export class Ga4Analytics {
  constructor(runtime = globalThis) {
    this.runtime = runtime;
    this.configured = false;
    this.enabled = false;
    this.consent = null;
    this.consentSource = 'unset';
    this.loaded = false;
    this.blocked = false;
    this.measurementId = '';
    this.origin = '';
    this.debugMode = false;
    this.buffer = [];
    // A bounded in-memory map remains the fallback when storage is unavailable.
    this.dedup = new Map();
    this.dedupStorageKey = '';
    this.currentScreen = '';
    this.lastPageScreen = '';
    this.previousPageScreen = '';
    this.attribution = captureAttribution(runtime);
  }

  configure(publicConfig = {}) {
    const config = publicConfig.ga4 || {};
    const environment = publicConfig.environment;
    const propertyEnvironment = config.property_environment;
    const origin = this.runtime.location?.origin || this.runtime.window?.location?.origin || '';
    const allowedOrigins = Array.isArray(config.allowed_origins)
      ? config.allowed_origins.map(normalizeOrigin).filter(Boolean)
      : [];
    const environmentMatches = (environment === 'preview' && propertyEnvironment === 'test')
      || (environment === 'production' && propertyEnvironment === 'production');
    this.configured = true;
    this.enabled = config.enabled === true
      && MEASUREMENT_ID.test(config.measurement_id || '')
      && environmentMatches
      && allowedOrigins.includes(origin);
    this.measurementId = this.enabled ? config.measurement_id : '';
    this.origin = this.enabled ? origin : '';
    this.debugMode = this.enabled && environment === 'preview' && config.debug_mode === true;
    if (!this.enabled) {
      this.buffer = [];
      return false;
    }
    this.dedupStorageKey = `${DEDUP_STORAGE_PREFIX}${environment}:${propertyEnvironment}:${fingerprint(config.measurement_id)}`;
    if (this.consent === true) this.loadPersistentDedup();
    this.runtime[`ga-disable-${this.measurementId}`] = this.consent !== true;
    this.start();
    return true;
  }

  setConsent(granted, source = 'explicit') {
    const wasGranted = this.consent === true;
    this.consent = granted === true;
    this.consentSource = typeof source === 'string' && source ? source : 'explicit';
    if (!this.consent) {
      this.buffer = [];
      this.dedup.clear();
      this.clearPersistentDedup();
      this.lastPageScreen = '';
      this.previousPageScreen = '';
      if (this.measurementId) this.runtime[`ga-disable-${this.measurementId}`] = true;
      if (this.loaded && typeof this.runtime.gtag === 'function') {
        this.runtime.gtag('consent', 'update', {
          analytics_storage: 'denied',
          ad_storage: 'denied',
          ad_user_data: 'denied',
          ad_personalization: 'denied',
        });
      }
      this.clearAnalyticsCookies();
      return;
    }
    if (this.measurementId) this.runtime[`ga-disable-${this.measurementId}`] = false;
    if (this.configured && this.enabled) this.loadPersistentDedup();
    if (!wasGranted && source !== 'automatic' && this.loaded && typeof this.runtime.gtag === 'function') {
      this.runtime.gtag('consent', 'update', {
        analytics_storage: 'granted',
        ad_storage: 'denied',
        ad_user_data: 'denied',
        ad_personalization: 'denied',
      });
    }
    if (!wasGranted && this.currentScreen) this.pageView(this.currentScreen);
    this.start();
  }

  persistentStorageAllowed() {
    return this.consent === true && ['explicit', 'stored_choice'].includes(this.consentSource);
  }

  setAttribution(dimensions = {}) {
    const source = enumValue(dimensions.channel, new Set(CHANNELS.keys()));
    if (source) {
      this.attribution.campaign_source = source;
      this.attribution.campaign_medium = CHANNELS.get(source);
    }
    const campaign = enumValue(dimensions.campaign_code, CAMPAIGNS);
    if (campaign) this.attribution.campaign_name = campaign;
    const linkKind = enumValue(dimensions.link_kind, LINK_KINDS);
    if (linkKind) this.attribution.link_kind = linkKind;
  }

  track(name, dimensions = {}, context = {}) {
    if (name === 'screen_entered') {
      this.setCurrentScreen(context.screen);
      return this.pageView(context.screen);
    }
    const eventName = EVENT_NAMES.get(name);
    if (!eventName || this.blocked || this.consent !== true || (this.configured && !this.enabled)) return false;
    const screen = enumValue(context.screen, SCREENS) || '';
    const params = sanitizeParams(name, dimensions, screen);
    const dedupSource = context.dedupKey || context.gameSessionId;
    const campaignScope = fingerprint(this.attribution.campaign_name || 'campaign-unset');
    const dedupKey = SUCCESS_EVENTS.has(name) && dedupSource ? `${name}:${campaignScope}:${fingerprint(String(dedupSource))}` : '';
    if (dedupKey && this.hasDedup(dedupKey)) return false;
    const event = { eventName, params: { ...params, ...this.attribution }, dedupKey };
    if (!this.ready()) {
      if (this.buffer.length < BUFFER_LIMIT) {
        this.buffer.push(event);
        if (dedupKey) this.rememberDedup(dedupKey);
        return true;
      }
      return false;
    }
    if (dedupKey) this.rememberDedup(dedupKey);
    return this.send(event);
  }

  now() {
    return typeof this.runtime.Date?.now === 'function' ? this.runtime.Date.now() : Date.now();
  }

  hasDedup(key) {
    const expiresAt = this.dedup.get(key);
    if (!Number.isFinite(expiresAt)) return false;
    if (expiresAt <= this.now()) {
      this.dedup.delete(key);
      return false;
    }
    return true;
  }

  rememberDedup(key) {
    this.dedup.delete(key);
    this.dedup.set(key, this.now() + DEDUP_TTL_MS);
    while (this.dedup.size > DEDUP_LIMIT) this.dedup.delete(this.dedup.keys().next().value);
    this.persistDedup();
  }

  loadPersistentDedup() {
    if (!this.persistentStorageAllowed() || !this.dedupStorageKey) return;
    try {
      const parsed = JSON.parse(this.runtime.localStorage?.getItem(this.dedupStorageKey) || '{}');
      const now = this.now();
      const entries = Array.isArray(parsed.entries) ? parsed.entries.slice(-DEDUP_LIMIT) : [];
      for (const entry of entries) {
        if (entry && typeof entry.key === 'string'
          && /^[a-z_]+:[a-z0-9]+:[a-z0-9]+$/.test(entry.key)
          && Number.isFinite(entry.expires_at) && entry.expires_at > now
          && !this.dedup.has(entry.key)) this.dedup.set(entry.key, entry.expires_at);
      }
      while (this.dedup.size > DEDUP_LIMIT) this.dedup.delete(this.dedup.keys().next().value);
      this.persistDedup();
    } catch (_) { /* Storage denial leaves bounded in-memory dedup active. */ }
  }

  persistDedup() {
    if (!this.persistentStorageAllowed() || !this.dedupStorageKey) return;
    try {
      const now = this.now();
      const entries = [...this.dedup.entries()]
        .filter(([, expiresAt]) => expiresAt > now)
        .slice(-DEDUP_LIMIT)
        .map(([key, expiresAt]) => ({ key, expires_at: expiresAt }));
      if (entries.length) this.runtime.localStorage?.setItem(this.dedupStorageKey, JSON.stringify({ entries }));
      else this.runtime.localStorage?.removeItem(this.dedupStorageKey);
    } catch (_) { /* Storage denial leaves bounded in-memory dedup active. */ }
  }

  clearPersistentDedup() {
    try {
      const storage = this.runtime.localStorage;
      if (!storage) return;
      const keys = [];
      for (let index = 0; index < storage.length; index += 1) {
        const key = storage.key(index);
        if (typeof key === 'string' && key.startsWith(DEDUP_STORAGE_PREFIX)) keys.push(key);
      }
      keys.forEach((key) => storage.removeItem(key));
    } catch (_) { /* Revocation still disables measurement when storage is blocked. */ }
  }

  pageView(screen) {
    const safeScreen = enumValue(screen, SCREENS);
    if (!safeScreen) return false;
    this.currentScreen = safeScreen;
    if (this.blocked || this.consent !== true || (this.configured && !this.enabled)) return false;
    if (safeScreen === this.lastPageScreen) return false;
    const previous = this.lastPageScreen;
    this.previousPageScreen = previous;
    this.lastPageScreen = safeScreen;
    const event = { eventName: 'page_view', pageScreen: safeScreen, previousScreen: previous };
    if (!this.ready()) {
      if (this.buffer.length < BUFFER_LIMIT) { this.buffer.push(event); return true; }
      return false;
    }
    return this.send(event);
  }

  setCurrentScreen(screen) {
    const safeScreen = enumValue(screen, SCREENS);
    if (!safeScreen) return false;
    this.currentScreen = safeScreen;
    return true;
  }

  ready() {
    return this.enabled && this.consent === true && this.loaded && !this.blocked && typeof this.runtime.gtag === 'function';
  }

  start() {
    if (!this.enabled || this.consent !== true || this.loaded || this.blocked) return;
    const documentRef = this.runtime.document;
    if (!documentRef?.createElement || !documentRef.head?.appendChild) return;
    const dataLayer = this.runtime.dataLayer = Array.isArray(this.runtime.dataLayer) ? this.runtime.dataLayer : [];
    this.runtime.gtag = this.runtime.gtag || function gtag() { dataLayer.push(arguments); };
    this.runtime[`ga-disable-${this.measurementId}`] = false;
    this.runtime.gtag('consent', 'default', {
      analytics_storage: 'granted',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
    });
    this.runtime.gtag('consent', 'default', {
      analytics_storage: 'denied',
      ad_storage: 'denied',
      ad_user_data: 'denied',
      ad_personalization: 'denied',
      region: REGIONAL_CONSENT_DENIED,
    });
    this.runtime.gtag('js', new Date());
    this.runtime.gtag('config', this.measurementId, {
      send_page_view: false,
      debug_mode: this.debugMode,
      cookie_expires: 60 * 86400,
      cookie_update: false,
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      ads_data_redaction: true,
    });
    const script = documentRef.createElement('script');
    script.async = true;
    script.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(this.measurementId)}`;
    script.onload = () => { this.flush(); };
    script.onerror = () => { this.blocked = true; this.buffer = []; };
    documentRef.head.appendChild(script);
    this.loaded = true;
    this.flush();
  }

  flush() {
    if (!this.ready()) return;
    const queued = this.buffer.splice(0, BUFFER_LIMIT);
    for (const event of queued) this.send(event);
  }

  send(event) {
    try {
      if (event.eventName === 'page_view') {
        const pageLocation = `${this.origin}/virtual/${event.pageScreen}`;
        const pageReferrer = event.previousScreen
          ? `${this.origin}/virtual/${event.previousScreen}`
          : `${this.origin}/virtual/entry`;
        this.runtime.gtag('event', 'page_view', {
          page_title: `Dino Jump · ${event.pageScreen}`,
          page_location: pageLocation,
          page_referrer: pageReferrer,
          screen_name: event.pageScreen,
          ...this.attribution,
        });
      } else {
        this.runtime.gtag('event', event.eventName, { ...event.params, ...this.attribution });
      }
      return true;
    } catch (_) {
      this.blocked = true;
      return false;
    }
  }

  clearAnalyticsCookies() {
    const documentRef = this.runtime.document;
    if (!documentRef || typeof documentRef.cookie !== 'string') return;
    const names = documentRef.cookie.split(';').map((part) => part.trim().split('=')[0])
      .filter((name) => /^_ga(?:_[A-Za-z0-9]+)?$/.test(name));
    const hostname = this.runtime.location?.hostname || this.runtime.window?.location?.hostname || '';
    const labels = hostname.split('.').filter(Boolean);
    const hostDomains = labels.flatMap((_, index) => {
      const suffix = labels.slice(index).join('.');
      return labels.length - index >= 2 ? [suffix, `.${suffix}`] : [];
    });
    const domains = ['', ...hostDomains].filter((value, index, all) => all.indexOf(value) === index);
    for (const name of names) {
      for (const domain of domains) {
        const domainPart = domain ? `; Domain=${domain}` : '';
        documentRef.cookie = `${name}=; Max-Age=0; Path=/${domainPart}; SameSite=Lax`;
      }
    }
  }
}

export const ga4Analytics = new Ga4Analytics();
export { BUFFER_LIMIT, DEDUP_LIMIT, DEDUP_TTL_MS, EVENT_NAMES, REGIONAL_CONSENT_DENIED, SCREENS };
