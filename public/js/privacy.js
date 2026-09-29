const PREFERENCE_KEY = 'dino_ga4_consent_v1';
const DEDUP_STORAGE_PREFIX = 'dino_ga4_dedup_v1:';
const OPTOUT_COOKIE = 'dino_ga4_optout';

function setStatus(message) {
  const status = document.getElementById('privacy-status');
  if (status) status.textContent = message;
}

function hasOptoutCookie() {
  try { return String(document.cookie || '').split(';').some((part) => part.trim() === `${OPTOUT_COOKIE}=1`); }
  catch (_) { return false; }
}

function setStorageHelp(visible) {
  const help = document.getElementById('privacy-storage-help');
  if (help) help.hidden = !visible;
}

function expireCookie(name) {
  const labels = location.hostname.split('.').filter(Boolean);
  const domains = ['', ...labels.flatMap((_, index) => {
    const suffix = labels.slice(index).join('.');
    return labels.length - index >= 2 ? [suffix, `.${suffix}`] : [];
  })];
  for (const domain of [...new Set(domains)]) {
    document.cookie = `${name}=; Max-Age=0; Path=/${domain ? `; Domain=${domain}` : ''}; SameSite=Lax`;
  }
}

function clearAnalyticsData() {
  try {
    const keys = [];
    for (let index = 0; index < localStorage.length; index += 1) {
      const key = localStorage.key(index);
      if (key?.startsWith(DEDUP_STORAGE_PREFIX)) keys.push(key);
    }
    keys.forEach((key) => localStorage.removeItem(key));
  } catch (_) {}
  String(document.cookie || '').split(';').map((part) => part.trim().split('=')[0])
    .filter((name) => /^_ga(?:_[A-Za-z0-9]+)?$/.test(name)).forEach(expireCookie);
}

function optout() {
  let storageSaved = false;
  try { localStorage.setItem(PREFERENCE_KEY, 'denied'); storageSaved = localStorage.getItem(PREFERENCE_KEY) === 'denied'; } catch (_) {}
  try { document.cookie = `${OPTOUT_COOKIE}=1; Max-Age=31536000; Path=/; SameSite=Lax`; } catch (_) {}
  const cookieSaved = hasOptoutCookie();
  clearAnalyticsData();
  const saved = storageSaved || cookieSaved;
  setStorageHelp(!saved);
  setStatus(saved ? '이 브라우저의 분석 사용을 중지했습니다.' : '브라우저가 분석 사용 중지 설정을 저장하지 못했습니다.');
}

function reenable() {
  let storageCleared = false;
  try { localStorage.removeItem(PREFERENCE_KEY); storageCleared = localStorage.getItem(PREFERENCE_KEY) !== 'denied'; } catch (_) {}
  expireCookie(OPTOUT_COOKIE);
  const cleared = storageCleared && !hasOptoutCookie();
  setStorageHelp(!cleared);
  setStatus(cleared
    ? '게임으로 돌아가면 자동 분석을 다시 사용합니다.'
    : '브라우저가 기존 분석 사용 중지 설정을 지우지 못했습니다.');
}

document.getElementById('analytics-optout')?.addEventListener('click', optout);
document.getElementById('analytics-reenable')?.addEventListener('click', reenable);

try {
  const disabled = localStorage.getItem(PREFERENCE_KEY) === 'denied'
    || String(document.cookie || '').split(';').some((part) => part.trim() === `${OPTOUT_COOKIE}=1`);
  setStatus(disabled
    ? '현재 이 브라우저의 분석 사용이 중지되어 있습니다.'
    : '자동 분석 허용 상태입니다. 서버에서 활성화된 경우 적용됩니다.');
} catch (_) {
  setStatus('브라우저 저장소 상태를 확인할 수 없습니다.');
}
