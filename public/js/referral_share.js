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

export function loadKakaoSdk(key) {
  if (!key) return Promise.resolve(null);
  if (globalThis.Kakao?.init) {
    if (!globalThis.Kakao.isInitialized?.()) globalThis.Kakao.init(key);
    return globalThis.Kakao.Share?.sendDefault ? Promise.resolve(globalThis.Kakao) : Promise.reject(new Error('KAKAO_SDK_UNAVAILABLE'));
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
      if (!kakao?.init) {
        reject(new Error('KAKAO_SDK_UNAVAILABLE'));
        return;
      }
      try {
        if (!kakao.isInitialized?.()) kakao.init(key);
        if (!kakao.Share?.sendDefault) throw new Error('KAKAO_SDK_UNAVAILABLE');
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

export function buildReferralShareText(kind, info = {}) {
  if (kind === 'retry_invite' || kind === 'record_share') {
    const count = Number(info.participant_count);
    const hasCount = info.participant_count !== null && info.participant_count !== undefined && info.participant_count !== '';
    const countLine = hasCount && Number.isInteger(count) && count >= 0
      ? `\n현재 참여 인원 ${count}명, 도전해 볼 만하다!`
      : '';
    return `행사 종료 시 1위 달성하면 5만원${countLine}\n\n참여하면 삼텐바이미 받을 수도 있대!\n너도 한 판 해봐!`;
  }
  if (kind === 'prize_share' && info.won_prize_name) {
    return `나 ${info.won_prize_name} 이거 받음\n아직 삼텐바이미 남았다는데\n\n너도 게임 한 판 하고\n상품 뽑아봐!`;
  }
  return '나 게임 한 판 하고\n복주머니 열어봄!\n\n삼텐바이미 받을 수도 있다던데,\n너도 한번 해봐';
}

function shareLinkKind(kind) {
  return kind === 'general_share' ? 'prize_share' : kind;
}

function buildInviteUrl(rawUrl, shareId, kind) {
  const url = new URL(rawUrl, window.location.origin);
  url.searchParams.set('link', shareLinkKind(kind));
  url.searchParams.set('share', shareId);
  return url.toString();
}

function trackShare(method, shareId, status, context, kind) {
  analytics.track('share_attempted', {
    share_method: method,
    share_id: shareId,
    link_kind: shareLinkKind(kind),
    status,
  }, context);
}

async function copyInvite(inviteUrl, shareText, shareId, context, kind) {
  trackShare('copy', shareId, 'attempted', context, kind);
  const copyText = `${shareText}\n${inviteUrl}`;
  try {
    if (!navigator.clipboard?.writeText) throw new Error('CLIPBOARD_UNSUPPORTED');
    await navigator.clipboard.writeText(copyText);
    trackShare('copy', shareId, 'copied', context, kind);
    ui.showToast('초대 링크를 복사했어요. 카카오톡에 붙여 넣어 주세요.');
    return { method: 'copy', status: 'copied' };
  } catch (_) {
    trackShare('copy', shareId, 'failed', context, kind);
    if (typeof window.prompt === 'function') window.prompt('초대 문구와 링크를 복사해 주세요.', copyText);
    return { method: 'copy', status: 'failed', inviteUrl };
  }
}

/**
 * Prepares referral data and the optional Kakao SDK before a click. Calling
 * share() from the click handler keeps Kakao's popup inside the user gesture.
 */
export async function prepareResultReferralShare(router, options = {}) {
  const allowedKinds = new Set(['record_share', 'retry_invite', 'prize_share', 'general_share']);
  const requestedKind = options.kind || 'record_share';
  const kind = allowedKinds.has(requestedKind) ? requestedKind : 'record_share';
  const referral = options.referral || await api.getReferralInfo();
  const shareText = buildReferralShareText(kind, { ...referral, ...(options.info || {}) });
  const kakaoKey = router?.config?.share?.kakao_javascript_key
    || api.config?.share?.kakao_javascript_key
    || '';
  const kakao = await loadKakaoSdk(kakaoKey).catch((error) => { console.warn('Kakao SDK preparation failed:', error.message); return null; });
  let pending = false;

  return {
    mode: kakao ? 'kakao' : (typeof navigator.share === 'function' ? 'native' : 'copy'),
    async share() {
      if (pending) return { status: 'pending' };
      pending = true;
      const shareId = api.createRequestId('share');
      const inviteUrl = buildInviteUrl(referral.invite_url, shareId, kind);
      const context = captureAnalyticsContext();
      try {
        if (kakao) {
          trackShare('kakao', shareId, 'attempted', context, kind);
          try {
            kakao.Share.sendDefault({
              objectType: 'text',
              text: shareText,
              link: { mobileWebUrl: inviteUrl, webUrl: inviteUrl },
              buttonTitle: '한 판 도전하기',
            });
            return { method: 'kakao', status: 'attempted' };
          } catch (_) {
            trackShare('kakao', shareId, 'failed', context, kind);
          }
        }
        if (typeof navigator.share === 'function') {
          trackShare('native', shareId, 'attempted', context, kind);
          try {
            await navigator.share({
              title: '공룡 점프 챌린지',
              text: shareText,
              url: inviteUrl,
            });
            trackShare('native', shareId, 'share_sheet_closed', context, kind);
            return { method: 'native', status: 'share_sheet_closed' };
          } catch (error) {
            const status = error?.name === 'AbortError' ? 'cancelled' : 'failed';
            trackShare('native', shareId, status, context, kind);
            return { method: 'native', status };
          }
        }
        return await copyInvite(inviteUrl, shareText, shareId, context, kind);
      } finally {
        pending = false;
      }
    },
  };
}
