import { ga4Analytics } from './ga4_analytics.js';

const PREFERENCE_KEY = 'dino_ga4_consent_v1';
let configured = false;
let preference = storedPreference();
// Read an existing choice before the application's first analytics event.
if (preference !== null) ga4Analytics.setConsent(preference);

function storedPreference() {
  try {
    const value = localStorage.getItem(PREFERENCE_KEY);
    return value === 'granted' ? true : value === 'denied' ? false : null;
  } catch (_) { return null; }
}

function choose(value) {
  const wasGranted = preference === true;
  preference = value;
  try { localStorage.setItem(PREFERENCE_KEY, value ? 'granted' : 'denied'); } catch (_) {}
  ga4Analytics.setConsent(value);
  const notice = document.getElementById('analytics-consent');
  if (notice) notice.hidden = true;
  // A loaded Google SDK can emit automatic cookieless events after a consent
  // update. Reload into the denied state so basic mode loads no SDK at all.
  if (wasGranted && !value) window.location.reload();
}

// Optional analytics must never interfere with participant creation or gameplay.
export function configureAnalyticsConsent(config) {
  try {
    ga4Analytics.configure(config);
    const settings = document.getElementById('analytics-settings');
    const notice = document.getElementById('analytics-consent');
    if (!settings || !notice) return;
    settings.hidden = !config?.ga4?.enabled;
    if (!config?.ga4?.enabled) { notice.hidden = true; return; }
    if (!configured) {
      configured = true;
      document.getElementById('analytics-accept')?.addEventListener('click', () => choose(true));
      document.getElementById('analytics-decline')?.addEventListener('click', () => choose(false));
      settings.addEventListener('click', () => { notice.hidden = false; document.getElementById('analytics-consent-title')?.focus(); });
    }
    if (preference !== null) ga4Analytics.setConsent(preference);
    notice.hidden = preference !== null;
  } catch (_) { /* The game remains usable when analytics or storage is blocked. */ }
}
