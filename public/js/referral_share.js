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

let prizeImagePromise = null;
export function prepareKakaoPrizeImage(kakao) {
  if (!kakao) return Promise.resolve(null);
  if (!prizeImagePromise) {
    let timer;
    const timeout = new Promise((_, reject) => { timer = setTimeout(() => reject(new Error('KAKAO_IMAGE_TIMEOUT')), 5000); });
    prizeImagePromise = Promise.race([kakao.Share.scrapImage({
      imageUrl: 'https://google-korea-team-gemini.vercel.app/assets/prizes/prize-lineup-cutout-v2.png',
    }), timeout]).then((response) => {
      const imageUrl = response.infos?.original?.url;
      if (!imageUrl || !/^https?:\/\//.test(imageUrl)) throw new Error('KAKAO_IMAGE_UNAVAILABLE');
      return imageUrl;
    }).catch((error) => { prizeImagePromise = null; throw error; }).finally(() => clearTimeout(timer));
  }
  return prizeImagePromise;
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
    ui.showToast('초대 링크를 복사했어요. 링크 복사로는 게임권이 지급되지 않아요.');
    return { method: 'copy', status: 'copied' };
  } catch (_) {
    trackShare('copy', shareId, 'failed', context, kind);
    if (typeof window.prompt === 'function') window.prompt('초대 문구와 링크를 복사해 주세요.', copyText);
    return { method: 'copy', status: 'failed', inviteUrl };
  }
}

// Only the authenticated server webhook can confirm delivery or grant a ticket.
async function watchInvitationShare(router, shareId) {
  for (let attempt = 0; attempt < 8; attempt += 1) {
    try {
      const receipt = await api.getReferralShareIntent(shareId);
      if (receipt.status !== 'pending') {
        if (receipt.tickets && router?.state) router.state.tickets = receipt.tickets;
        router?.updateNav?.();
        router?.announceStateChange?.();
        if (receipt.status === 'confirmed') {
          ui.showToast(receipt.reward_status === 'granted' ? '전송이 확인되어 게임권 1장을 받았어요!' : '카카오톡 전송을 확인했어요. 초대권은 보유 한도와 대기 시간에 따라 지급돼요.');
          void router?.refreshState?.({ quiet: true })?.catch?.(() => {});
        } else if (receipt.status === 'rejected') ui.showToast('친구에게 보낸 카카오톡 공유만 게임권을 받을 수 있어요.');
        return;
      }
    } catch (_) { /* A delayed webhook remains recoverable from server state. */ }
    if (attempt < 7) await new Promise((resolve) => setTimeout(resolve, 1500));
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
  let kakao = await loadKakaoSdk(kakaoKey).catch((error) => { console.warn('Kakao SDK preparation failed:', error.message); return null; });
  let imageUrl = null;
  try { imageUrl = await prepareKakaoPrizeImage(kakao); } catch (_) { kakao = null; }
  let pending = false;
  let intent = null;
  let preparingIntent = null;
  const webhookEnabled = (router?.config?.share || api.config?.share)?.webhook_enabled === true;
  const prepareIntent = () => {
    if (!kakao || !webhookEnabled) return Promise.resolve();
    if (!preparingIntent) preparingIntent = api.createReferralShareIntent(kind, options.claimId || null)
      .then((value) => { intent = value; })
      .catch(() => { intent = null; })
      .finally(() => { preparingIntent = null; });
    return preparingIntent;
  };
  await prepareIntent();

  return {
    mode: kakao ? 'kakao' : (typeof navigator.share === 'function' ? 'native' : 'copy'),
    async share() {
      if (pending) return { status: 'pending' };
      pending = true;
      const shareId = intent?.share_id || api.createRequestId('share');
      const inviteUrl = buildInviteUrl(referral.invite_url, shareId, kind);
      const context = captureAnalyticsContext();
      try {
        if (kakao) {
          if (!intent || Date.parse(intent.expires_at) <= Date.now()) {
            void prepareIntent();
            ui.showToast(webhookEnabled ? '전송 확인을 준비 중이에요. 잠시 후 다시 눌러 주세요.' : '지금은 카카오톡 초대를 이용할 수 없어요. 잠시 후 다시 시도해 주세요.');
            return { method: 'kakao', status: 'unavailable' };
          }
          const sendingIntent = intent;
          intent = null;
          trackShare('kakao', shareId, 'attempted', context, kind);
          try {
            kakao.Share.sendDefault({
              objectType: 'feed',
              serverCallbackArgs: sendingIntent.callback_args,
              content: {
                title: shareText.split('\n')[0],
                description: shareText.split('\n').slice(1).join('\n').trim(),
                imageUrl,
                imageWidth: 1254,
                imageHeight: 1254,
                link: { mobileWebUrl: inviteUrl, webUrl: inviteUrl },
              },
              buttons: [{ title: '한 판 도전하기', link: { mobileWebUrl: inviteUrl, webUrl: inviteUrl } }],
            });
            ui.showToast('카카오톡으로 전송하면 확인 후 게임권이 적립돼요.');
            if (!options.claimId) void watchInvitationShare(router, shareId);
            return { method: 'kakao', status: 'pending', shareId };

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
            ui.showToast('게임권은 카카오톡 전송이 확인된 경우에만 지급돼요.');
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
        if (!intent && !options.claimId) void prepareIntent();
      }
    },
  };
}
