import { api } from './api.js';

const ALLOWED = new Set(['page_view','page_engagement','draw_open','claim_start','invite_copy','invite_share_open','gemini_link_click','client_error']);
const SAFE_FIELDS = new Set(['screen','active_ms','channel','error_code']);
const SCREENS = new Set(['home','game','result','draw','claims','ranking','invite','benefit']);
let queue = [], timer = null, current = 'home', visibleSince = null, activeMs = 0, initialized = false;

export function safeScreen(value) {
  const screen = String(value || '').toLowerCase();
  return SCREENS.has(screen) ? screen : 'home';
}

function screenPath(screen = current) { return `/screen/${safeScreen(screen)}`; }

export function redactVercelEvent(event) {
  if (!event || !['pageview', 'event'].includes(event.type)) return null;
  const url = new URL(screenPath(), window.location.origin);
  return { type: event.type, url: url.href };
}

function clean(name, fields = {}) {
  if (!ALLOWED.has(name)) return null;
  const event = { event_id: api.newId('evt'), event_name: name };
  for (const [key, value] of Object.entries(fields)) {
    if (!SAFE_FIELDS.has(key)) continue;
    event[key] = key === 'active_ms'
      ? Math.max(0, Math.min(86400000, Number(value) || 0))
      : (key === 'screen' ? safeScreen(value) : String(value).slice(0, 64));
  }
  return event;
}

export function track(name, fields) {
  const event = clean(name, fields);
  if (!event) return;
  queue.push(event);
  if (queue.length >= 10) flush();
  else if (!timer) timer = setTimeout(flush, 4000);
}

export function flush() {
  clearTimeout(timer); timer = null;
  if (!queue.length || !api.token) return;
  const batch = queue.splice(0, 20);
  api.sendEvents(batch).then(ok => { if (!ok) queue = batch.concat(queue).slice(0, 40); });
}

function accrue() {
  if (visibleSince !== null) {
    activeMs += Math.max(0, performance.now() - visibleSince);
    visibleSince = null;
  }
}

function closeScreen() {
  accrue();
  if (current && activeMs > 0) track('page_engagement', { screen: current, active_ms: Math.round(activeMs) });
  activeMs = 0;
}

export function page(screen) {
  closeScreen();
  current = safeScreen(screen);
  if (!document.hidden) visibleSince = performance.now();
  track('page_view', { screen: current });
  if (api.config?.web_analytics_enabled && typeof window.va === 'function') {
    const path = screenPath(current);
    window.va('pageview', { route: path, path });
  }
}

export function initAnalytics() {
  if (initialized) return;
  initialized = true;
  document.addEventListener('visibilitychange', () => {
    if (document.hidden) { closeScreen(); flush(); }
    else visibleSince = performance.now();
  });
  window.addEventListener('pagehide', () => { closeScreen(); flush(); });
  if (api.config?.web_analytics_enabled) {
    window.va = window.va || function () { (window.vaq = window.vaq || []).push(arguments); };
    window.va('beforeSend', redactVercelEvent);
    const script = document.createElement('script');
    script.defer = true;
    script.src = '/_vercel/insights/script.js';
    script.dataset.disableAutoTrack = '1';
    document.head.appendChild(script);
  }
}
