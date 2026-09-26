import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { loadKakaoSdk } from '../referral_share.js';

function safeExternalUrl(value) {
  if (typeof value !== 'string' || !/^https:\/\/[^\s]+$/i.test(value)) return null;
  try {
    if (typeof URL === 'undefined') return value;
    const url = new URL(value); return url.protocol === 'https:' ? url.toString() : null;
  } catch (_) { return null; }
}

async function copyText(value) {
  if (!navigator.clipboard?.writeText) throw new Error('CLIPBOARD_UNSUPPORTED');
  await navigator.clipboard.writeText(value);
}

function captureAnalyticsContext() {
  const context = {};
  if (typeof analytics.screen === 'string' && analytics.screen) context.screen = analytics.screen;
  if (typeof analytics.screenViewId === 'string' && analytics.screenViewId) context.screenViewId = analytics.screenViewId;
  const activeMs = typeof analytics.currentActiveMs === 'function' ? analytics.currentActiveMs() : null;
  if (Number.isFinite(activeMs)) context.activeMs = activeMs;
  return context;
}

export const BenefitView = {
  observer: null,
  contentObserver: null,
  visibilityHandler: null,
  observationGeneration: 0,
  render(container, router) {
    this.cleanup();
    const observationGeneration = this.observationGeneration;
    const isActiveRender = () => this.observationGeneration === observationGeneration;
    container.innerHTML = `
      <section class="card compact-card benefit-hero">
        <div class="home-event-badges"><span class="home-event-badge home-event-badge-team">Gemini 1년 무료 혜택</span></div>
        <div class="benefit-link-box">
          <div class="benefit-link-address"><span class="benefit-link-label">공식 혜택 링크</span><p id="benefit-official-url" class="benefit-official-url"></p></div>
          <div class="benefit-link-actions">
          <button id="btn-copy-benefit" class="btn btn-outline" type="button" aria-label="공식 혜택 링크 복사하기" title="공식 혜택 링크 복사하기">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>
          </button>
          <button id="btn-share-benefit" class="btn btn-secondary" type="button" aria-label="공유하기" title="공유하기">
            <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.8" aria-hidden="true"><path d="M12 15V3m-4 4 4-4 4 4M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/></svg>
          </button>
          </div>
        </div>
        <a id="btn-go-benefit" class="btn btn-primary" target="_blank" rel="noopener noreferrer">링크 접속하기</a>
        <p id="benefit-fallback" class="status-note" hidden></p>
      </section>
      <section class="card compact-card benefit-notes">
        <h2><span class="benefit-notes-eyebrow">이미 1년 무료 혜택을 이용 중이라면?</span><span class="benefit-notes-title">비밀 노트를 받으세요!</span></h2>
        <div id="content-guide-list" class="content-guide-list"></div>
      </section>
      <button id="btn-kakao-benefit" class="btn benefit-kakao-share" type="button" aria-label="카카오톡으로 혜택 친구한테 알리기">
        <svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3C6.48 3 2 6.45 2 10.7c0 2.76 1.89 5.18 4.72 6.54l-.93 3.38c-.08.29.25.52.5.36l3.97-2.61c.57.08 1.15.12 1.74.12 5.52 0 10-3.46 10-7.79C22 6.45 17.52 3 12 3Z"/></svg>
        <span>혜택 친구한테 알리기</span>
      </button>`;
    const configuredUrl = router.config?.official_url || router.config?.benefit_url;
    const safeUrl = safeExternalUrl(configuredUrl);
    const kakaoButton = container.querySelector('#btn-kakao-benefit');
    let kakao = null;
    kakaoButton.disabled = true;
    loadKakaoSdk(router.config?.share?.kakao_javascript_key || '').catch(() => null).then((sdk) => {
      if (!isActiveRender()) return;
      kakao = sdk;
      kakaoButton.disabled = !safeUrl;
    });
    ui.text(container.querySelector('#benefit-official-url'), safeUrl || '공식 링크 준비 중');
    const link = container.querySelector('#btn-go-benefit');
    if (safeUrl) link.href = safeUrl;
    else { link.removeAttribute?.('href'); link.setAttribute?.('aria-disabled', 'true'); link.classList?.add('is-disabled'); link.textContent = '공식 링크 준비 중'; }

    const guideList = container.querySelector('#content-guide-list');
    const guides = Array.isArray(router.config?.content_guides) ? router.config.content_guides : [];
    const displayGuides = guides.length ? guides : [{ id: 'unavailable', title: '활용 가이드', description: '확인된 공개 가이드가 준비되면 이곳에 연결됩니다.', available: false }];
    const guideCards = new Map();
    for (const guide of guideList ? displayGuides : []) {
      const card = document.createElement('article'); card.className = 'content-guide-card';
      if (guide.id === 'job_photo') card.classList.add('content-guide-career');
      const title = document.createElement('h3'); title.textContent = String(guide.title || '활용 가이드');
      const content = String(guide.id || 'guide').slice(0, 64);
      const actions = document.createElement('div'); actions.className = 'content-guide-actions';
      const guideUrl = guide.available ? safeExternalUrl(guide.url) : null;
      const action = document.createElement(guideUrl ? 'a' : 'button'); action.className = 'btn btn-secondary btn-sm content-guide-open';
      if (guideUrl) {
        action.href = guideUrl; action.target = '_blank'; action.rel = 'noopener noreferrer'; action.textContent = '접속하기';
        action.onclick = () => analytics.track('content_clicked', { content: String(guide.id || 'guide').slice(0, 64), position: 'benefit_guides' });
      } else { action.type = 'button'; action.disabled = true; action.textContent = '공개 가이드 준비 중'; }
      actions.appendChild(action);
      const fallback = document.createElement('p'); fallback.className = 'content-guide-fallback'; fallback.hidden = true;
      let guidePending = false;
      for (const method of ['copy', 'share']) {
        const button = document.createElement('button'); button.type = 'button'; button.className = 'btn btn-secondary btn-sm content-guide-icon';
        const buttonLabel = method === 'copy' ? '복사하기' : '공유하기'; button.disabled = !guideUrl;
        button.setAttribute('aria-label', `${title.textContent} ${buttonLabel}`); button.title = buttonLabel;
        button.innerHTML = method === 'copy'
          ? '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><rect x="8" y="8" width="12" height="12" rx="2"/><path d="M16 8V5a2 2 0 0 0-2-2H5a2 2 0 0 0-2 2v9a2 2 0 0 0 2 2h3"/></svg>'
          : '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.7" aria-hidden="true"><path d="M12 15V3m-4 4 4-4 4 4M5 12v7a2 2 0 0 0 2 2h10a2 2 0 0 0 2-2v-7"/></svg>';
        button.onclick = async () => {
          if (guidePending || !guideUrl) return;
          guidePending = true;
          const trackingContext = captureAnalyticsContext();
          const shareMethod = method === 'share' && typeof navigator.share === 'function' ? 'native' : 'copy';
          const track = (status) => analytics.track('share_attempted', { source: 'content', content, position: 'benefit_guides', share_method: shareMethod, status }, trackingContext);
          track('attempted');
          try {
            if (shareMethod === 'native') {
              await navigator.share({ title: title.textContent, url: guideUrl });
              track('share_sheet_closed');
            } else {
              await copyText(guideUrl); track('copied');
              if (isActiveRender()) ui.showToast(method === 'share' ? '공유 창을 지원하지 않아 링크를 복사했어요.' : '노트 링크를 복사했어요.');
            }
          } catch (error) {
            track(error?.name === 'AbortError' ? 'cancelled' : 'failed');
            if (error?.name !== 'AbortError' && isActiveRender()) { fallback.hidden = false; fallback.textContent = `이 주소를 길게 눌러 복사해 주세요: ${guideUrl}`; }
          } finally { guidePending = false; }
        };
        actions.appendChild(button);
      }
      card.append(title, actions, fallback); guideList.appendChild(card);
      if (guide.id !== 'unavailable') guideCards.set(card, String(guide.id || 'guide').slice(0, 64));
    }

    const viewedGuides = new Set();
    let contentObserver = null;
    const handleGuideEntries = (entries) => {
      if (!isActiveRender() || document.hidden) return;
      for (const entry of entries) {
        const content = guideCards.get(entry.target);
        if (!content || viewedGuides.has(content) || !entry.isIntersecting || entry.intersectionRatio < 0.5) continue;
        viewedGuides.add(content);
        analytics.track('content_viewed', { content, position: 'benefit_guides' });
        contentObserver?.unobserve(entry.target);
      }
    };
    contentObserver = typeof IntersectionObserver === 'function' && guideCards.size
      ? new IntersectionObserver(handleGuideEntries, { threshold: [0.5] })
      : null;
    this.contentObserver = contentObserver;
    if (this.contentObserver) for (const card of guideCards.keys()) this.contentObserver.observe(card);

    analytics.track('benefit_viewed');
    let viewed = false;
    let ctaObserver = null;
    const handleCtaEntries = (entries) => {
      if (!isActiveRender() || document.hidden || viewed) return;
      if (entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.5)) {
        viewed = true; analytics.track('gemini_cta_viewed', { position: 'benefit_main' }); ctaObserver?.disconnect();
      }
    };
    ctaObserver = typeof IntersectionObserver === 'function' && safeUrl
      ? new IntersectionObserver(handleCtaEntries, { threshold: [0.5] })
      : null;
    this.observer = ctaObserver;
    if (this.observer) this.observer.observe(link);
    if (contentObserver || ctaObserver) {
      this.visibilityHandler = () => {
        if (!isActiveRender() || document.hidden) return;
        contentObserver?.takeRecords?.();
        for (const [card, content] of guideCards) {
          if (!contentObserver || viewedGuides.has(content)) continue;
          contentObserver.unobserve(card);
          contentObserver.observe(card);
        }
        ctaObserver?.takeRecords?.();
        if (ctaObserver && !viewed) {
          ctaObserver.unobserve(link);
          ctaObserver.observe(link);
        }
      };
      document.addEventListener?.('visibilitychange', this.visibilityHandler);
    }
    link.onclick = safeUrl ? () => analytics.track('gemini_cta_clicked', { position: 'benefit_main' }) : (event) => event.preventDefault();
    const trackShare = (method, status, trackingContext) => analytics.track(
      'share_attempted',
      { source: 'gemini', position: 'benefit_main', share_method: method, status },
      trackingContext,
    );
    const showManualFallback = () => { const node = container.querySelector('#benefit-fallback'); if (node) { node.hidden = false; ui.text(node, safeUrl ? `자동 복사가 지원되지 않아요. 이 주소를 길게 눌러 복사해 주세요: ${safeUrl}` : '확인된 공식 링크를 준비 중입니다.'); } };
    let sharePending = false;
    container.querySelector('#btn-copy-benefit').onclick = async () => {
      if (sharePending) return;
      sharePending = true;
      const trackingContext = captureAnalyticsContext();
      trackShare('copy', 'attempted', trackingContext);
      try {
        if (!safeUrl) { trackShare('copy', 'failed', trackingContext); if (isActiveRender()) showManualFallback(); return; }
        await copyText(safeUrl);
        trackShare('copy', 'copied', trackingContext);
        if (isActiveRender()) ui.showToast('공식 혜택 링크를 복사했어요.');
      } catch (_) {
        trackShare('copy', 'failed', trackingContext);
        if (isActiveRender()) showManualFallback();
      } finally {
        sharePending = false;
      }
    };
    const shareBenefit = async (preferKakao = false) => {
      if (sharePending) return;
      sharePending = true;
      const trackingContext = captureAnalyticsContext();
      try {
        if (!safeUrl) { trackShare('native', 'failed', trackingContext); if (isActiveRender()) showManualFallback(); return; }
        if (preferKakao && kakao) {
          trackShare('kakao', 'attempted', trackingContext);
          try {
            kakao.Share.sendDefault({ objectType: 'text', text: 'Gemini 1년 무료 혜택, 친구와 함께 확인해 보세요!', link: { mobileWebUrl: safeUrl, webUrl: safeUrl }, buttonTitle: '혜택 확인하기' });
            return;
          } catch (_) { trackShare('kakao', 'failed', trackingContext); }
        }
        if (typeof navigator.share !== 'function') {
          trackShare('copy', 'attempted', trackingContext);
          try {
            await copyText(safeUrl);
            trackShare('copy', 'copied', trackingContext);
            if (isActiveRender()) ui.showToast('공유 창을 지원하지 않아 링크를 복사했어요.');
          } catch (_) {
            trackShare('copy', 'failed', trackingContext);
            if (isActiveRender()) showManualFallback();
          }
          return;
        }
        trackShare('native', 'attempted', trackingContext);
        try {
          await navigator.share({ title: 'Gemini 학생 혜택', url: safeUrl });
          trackShare('native', 'share_sheet_closed', trackingContext);
        } catch (error) {
          trackShare('native', error?.name === 'AbortError' ? 'cancelled' : 'failed', trackingContext);
        }
      } finally {
        sharePending = false;
      }
    };
    container.querySelector('#btn-share-benefit').onclick = () => shareBenefit();
    kakaoButton.onclick = () => shareBenefit(true);
  },
  cleanup() { this.observer?.disconnect(); this.observer = null;
    this.observationGeneration += 1;
    if (this.visibilityHandler) document.removeEventListener?.('visibilitychange', this.visibilityHandler);
    this.visibilityHandler = null;
    this.contentObserver?.disconnect(); this.contentObserver = null;
  },
};
