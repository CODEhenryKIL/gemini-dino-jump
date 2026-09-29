import { ga4Analytics } from './ga4_analytics.js';

const PREFERENCE_KEY = 'dino_ga4_consent_v1';
const OPTOUT_COOKIE = 'dino_ga4_optout';
let optoutListenerBound = false;

function hasOptoutCookie() {
  try {
    return String(document.cookie || '').split(';').some((part) => part.trim() === `${OPTOUT_COOKIE}=1`);
  } catch (_) { return false; }
}

function storedPreference() {
  if (hasOptoutCookie()) return false;
  try {
    const value = localStorage.getItem(PREFERENCE_KEY);
    if (value === 'denied') return false;
    if (value === 'granted') return true;
  } catch (_) {
    return hasOptoutCookie() ? false : undefined;
  }
  return null;
}

function privacySignalEnabled() {
  try {
    if (navigator.globalPrivacyControl === true) return true;
    const values = [navigator.doNotTrack, window.doNotTrack, navigator.msDoNotTrack];
    return values.some((value) => value === '1' || String(value).toLowerCase() === 'yes');
  } catch (_) { return false; }
}

function browserOptoutEnabled(config) {
  const measurementId = config?.ga4?.measurement_id;
  return typeof measurementId === 'string' && window[`ga-disable-${measurementId}`] === true;
}

function bindCrossTabOptout() {
  if (optoutListenerBound || typeof window.addEventListener !== 'function') return;
  optoutListenerBound = true;
  window.addEventListener('storage', (event) => {
    if (event.key !== PREFERENCE_KEY || event.newValue !== 'denied') return;
    try { ga4Analytics.setConsent(false, 'stored_optout'); } catch (_) {}
  });
}

// Optional analytics must never interfere with participant creation or gameplay.
export function configureAnalyticsConsent(config) {
  try {
    bindCrossTabOptout();
    const preference = storedPreference();
    const browserOptout = privacySignalEnabled() || browserOptoutEnabled(config);
    const collectionAllowed = !browserOptout && (preference === true || preference === null);
    const source = browserOptout ? 'browser_signal'
      : preference === true ? 'stored_choice'
        : collectionAllowed ? 'automatic'
          : preference === false ? 'stored_optout' : 'storage_unavailable';
    ga4Analytics.setConsent(collectionAllowed, source);
    ga4Analytics.configure(config);
  } catch (_) {
    try { ga4Analytics.setConsent(false, 'check_failed'); } catch (_) {}
  }
}

export { OPTOUT_COOKIE, PREFERENCE_KEY };
