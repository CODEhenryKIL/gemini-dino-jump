import { api } from './api.js';
import { analytics } from './analytics.js';
import { ui } from './ui.js';

const KAKAO_SDK_URL = 'https://t1.kakaocdn.net/kakao_js_sdk/2.8.3/kakao.min.js';
let kakaoSdkPromise = null;

function captureAnalyticsContext() {
  const context = {};
  if (typeof analytics.screen === 'string' && analytics.screen) context.screen = analytics.screen;
  if (typeof analytics.screenViewId === 'string' && analytics.screenViewId) context.screenViewId = analytics.screenViewId;
  const activeMs = typeof analytics.currentActiveMs === 'function' ? analytics.currentActiveMs() : null;
  if (Number.isFinite(activeMs)) context.activeMs = activeMs;
  return context;
}

function loadKakaoSdk(key) {
  if (!key) return Promise.resolve(null);
  if (globalThis.Kakao?.Share?.sendDefault) {
    if (!globalThis.Kakao.isInitialized?.()) globalThis.Kakao.init(key);
    return Promise.resolve(globalThis.Kakao);
  }
  if (kakaoSdkPromise) return kakaoSdkPromise;
  kakaoSdkPromise = new Promise((resolve, reject) => {
    const script = document.createElement('script');
    script.src = KAKAO_SDK_URL;
    script.async = true;
    script.crossOrigin = 'anonymous';
    const timer = setTimeout(() => { script.remove(); reject(new Error('KAKAO_SDK_TIMEOUT')); }, 5000);
    script.onload = () => {
      clearTimeout(timer);
      const kakao = globalThis.Kakao;
      if (!kakao?.Share?.sendDefault) {
        reject(new Error('KAKAO_SDK_UNAVAILABLE'));
        return;
      }
      try {
        if (!kakao.isInitialized?.()) kakao.init(key);
        resolve(kakao);
      } catch (error) { script.remove(); reject(error); }
    };
    script.onerror = () => { clearTimeout(timer); script.remove(); reject(new Error('KAKAO_SDK_LOAD_FAILED')); };
    document.head.appendChild(script);
  }).catch((error) => {
    kakaoSdkPromise = null;
    throw error;
  });
  return kakaoSdkPromise;
}

function buildInviteUrl(rawUrl, shareId) {
  const url = new URL(rawUrl, window.location.origin);
  url.searchParams.set('link', 'record_share');
  url.searchParams.set('share', shareId);
  return url.toString();
}

function trackShare(method, shareId, status, context) {
  analytics.track('share_attempted', {
    share_method: method,
    share_id: shareId,
    link_kind: 'record_share',
    status,
  }, context);
}

async function copyInvite(inviteUrl, shareId, context) {
  trackShare('copy', shareId, 'attempted', context);
  try {
    if (!navigator.clipboard?.writeText) throw new Error('CLIPBOARD_UNSUPPORTED');
    await navigator.clipboard.writeText(inviteUrl);
    trackShare('copy', shareId, 'copied', context);
    ui.showToast('초대 링크를 복사했어요. 카카오톡에 붙여 넣어 주세요.');
    return { method: 'copy', status: 'copied' };
  } catch (_) {
    trackShare('copy', shareId, 'failed', context);
    if (typeof window.prompt === 'function') window.prompt('초대 링크를 복사해 주세요.', inviteUrl);
    return { method: 'copy', status: 'failed', inviteUrl };
  }
}

/**
 * Prepares referral data and the optional Kakao SDK before a click. Calling
 * share() from the click handler keeps Kakao's popup inside the user gesture.
 */
export async function prepareResultReferralShare(router) {
  const referral = await api.getReferralInfo();
  const kakaoKey = router?.config?.share?.kakao_javascript_key
    || api.config?.share?.kakao_javascript_key
    || '';
  const kakao = await loadKakaoSdk(kakaoKey).catch(() => null);
  let pending = false;

  return {
    mode: kakao ? 'kakao' : (typeof navigator.share === 'function' ? 'native' : 'copy'),
    async share() {
      if (pending) return { status: 'pending' };
      pending = true;
      const shareId = api.createRequestId('share');
      const inviteUrl = buildInviteUrl(referral.invite_url, shareId);
      const context = captureAnalyticsContext();
      const bestScore = Number(router?.state?.bestScore) || 0;
      try {
        if (kakao) {
          trackShare('kakao', shareId, 'attempted', context);
          try {
            kakao.Share.sendDefault({
              objectType: 'text',
              text: `내 공룡 점프 기록 ${bestScore}점에 도전해 봐!`,
              link: { mobileWebUrl: inviteUrl, webUrl: inviteUrl },
              buttonTitle: '한 판 도전하기',
            });
            return { method: 'kakao', status: 'attempted' };
          } catch (_) {
            trackShare('kakao', shareId, 'failed', context);
          }
        }
        if (typeof navigator.share === 'function') {
          trackShare('native', shareId, 'attempted', context);
          try {
            await navigator.share({
              title: '공룡 점프 챌린지',
              text: `내 기록 ${bestScore}점에 도전해 봐!`,
              url: inviteUrl,
            });
            trackShare('native', shareId, 'share_sheet_closed', context);
            return { method: 'native', status: 'share_sheet_closed' };
          } catch (error) {
            const status = error?.name === 'AbortError' ? 'cancelled' : 'failed';
            trackShare('native', shareId, status, context);
            return { method: 'native', status };
          }
        }
        return await copyInvite(inviteUrl, shareId, context);
      } finally {
        pending = false;
      }
    },
  };
}
