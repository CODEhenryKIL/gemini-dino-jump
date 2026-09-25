import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

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

export const BenefitView = {
  observer: null,
  contentObserver: null,
  render(container, router) {
    this.cleanup();
    container.innerHTML = `
      <section class="card compact-card">
        <span class="sticker-badge badge-blue">Gemini 학생 혜택</span>
        <h1>공식 페이지에서 현재 혜택을 확인하세요</h1>
        <p>대상·기간·가격·신청 조건은 공식 페이지의 최신 안내를 기준으로 확인해 주세요.</p>
        <a id="btn-go-benefit" class="btn btn-primary" target="_blank" rel="noopener noreferrer">공식 혜택 확인하기</a>
        <button id="btn-copy-benefit" class="btn btn-outline">공식 혜택 링크 복사</button>
        <button id="btn-share-benefit" class="btn btn-secondary">공식 혜택 링크 공유</button>
        <p id="benefit-fallback" class="status-note">인앱 브라우저에서 페이지가 열리지 않으면 링크를 복사해 Safari·Chrome 같은 외부 브라우저 주소창에 붙여 넣어 주세요.</p>
      </section>
      <section class="card compact-card">
        <h2>이미 Gemini를 사용 중이라면</h2>
        <p>혜택 신청 여부와 관계없이 공개된 활용 가이드를 바로 볼 수 있어요.</p>
        <div id="content-guide-list" class="content-guide-list"></div>
      </section>
      <section class="card compact-card"><h2>경품과 혜택은 별개예요</h2><p>Gemini 페이지 방문이나 가이드 열람은 경품 지급 조건이 아니며, 운영팀의 수령 확인과 실제 지급 상태는 수령함에서 확인할 수 있어요.</p></section>`;
    const configuredUrl = router.config?.official_url || router.config?.benefit_url;
    const safeUrl = safeExternalUrl(configuredUrl);
    const link = container.querySelector('#btn-go-benefit');
    if (safeUrl) link.href = safeUrl;
    else { link.removeAttribute?.('href'); link.setAttribute?.('aria-disabled', 'true'); link.classList?.add('is-disabled'); link.textContent = '공식 링크 준비 중'; }

    const guideList = container.querySelector('#content-guide-list');
    const guides = Array.isArray(router.config?.content_guides) ? router.config.content_guides : [];
    const displayGuides = guides.length ? guides : [{ id: 'unavailable', title: '활용 가이드', description: '확인된 공개 가이드가 준비되면 이곳에 연결됩니다.', available: false }];
    const guideCards = new Map();
    for (const guide of guideList ? displayGuides : []) {
      const card = document.createElement('article'); card.className = 'content-guide-card';
      const title = document.createElement('h3'); title.textContent = String(guide.title || '활용 가이드');
      const description = document.createElement('p'); description.textContent = String(guide.description || '가이드 설명을 준비 중입니다.');
      const guideUrl = guide.available ? safeExternalUrl(guide.url) : null;
      const action = document.createElement(guideUrl ? 'a' : 'button'); action.className = 'btn btn-secondary btn-sm';
      if (guideUrl) {
        action.href = guideUrl; action.target = '_blank'; action.rel = 'noopener noreferrer'; action.textContent = '가이드 열기';
        action.onclick = () => analytics.track('content_clicked', { content: String(guide.id || 'guide').slice(0, 64), position: 'benefit_guides' });
      } else { action.type = 'button'; action.disabled = true; action.textContent = '공개 가이드 준비 중'; }
      card.append(title, description, action); guideList.appendChild(card);
      if (guide.id !== 'unavailable') guideCards.set(card, String(guide.id || 'guide').slice(0, 64));
    }

    const viewedGuides = new Set();
    this.contentObserver = typeof IntersectionObserver === 'function' && guideCards.size ? new IntersectionObserver((entries) => {
      if (document.hidden) return;
      for (const entry of entries) {
        const content = guideCards.get(entry.target);
        if (!content || viewedGuides.has(content) || !entry.isIntersecting || entry.intersectionRatio < 0.5) continue;
        viewedGuides.add(content);
        analytics.track('content_viewed', { content, position: 'benefit_guides' });
        this.contentObserver?.unobserve(entry.target);
      }
    }, { threshold: [0.5] }) : null;
    if (this.contentObserver) for (const card of guideCards.keys()) this.contentObserver.observe(card);

    analytics.track('benefit_viewed');
    let viewed = false;
    this.observer = typeof IntersectionObserver === 'function' && safeUrl ? new IntersectionObserver((entries) => {
      if (!viewed && !document.hidden && entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.5)) {
        viewed = true; analytics.track('gemini_cta_viewed', { position: 'benefit_main' }); this.observer?.disconnect();
      }
    }, { threshold: [0.5] }) : null;
    if (this.observer) this.observer.observe(link);
    else if (!document.hidden && safeUrl) analytics.track('gemini_cta_viewed', { position: 'benefit_main' });
    link.onclick = safeUrl ? () => analytics.track('gemini_cta_clicked', { position: 'benefit_main' }) : (event) => event.preventDefault();
    const trackShare = (method, status) => analytics.track('share_attempted', { source: 'gemini', position: 'benefit_main', share_method: method, status });
    const showManualFallback = () => { const node = container.querySelector('#benefit-fallback'); if (node) ui.text(node, safeUrl ? `자동 복사가 지원되지 않아요. 이 주소를 길게 눌러 복사한 뒤 외부 브라우저에서 열어 주세요: ${safeUrl}` : '확인된 공식 링크를 준비 중입니다.'); };
    container.querySelector('#btn-copy-benefit').onclick = async () => {
      trackShare('copy', 'attempted');
      if (!safeUrl) { trackShare('copy', 'failed'); showManualFallback(); return; }
      try { await copyText(safeUrl); trackShare('copy', 'copied'); ui.showToast('공식 혜택 링크를 복사했어요.'); }
      catch (_) { trackShare('copy', 'failed'); showManualFallback(); }
    };
    container.querySelector('#btn-share-benefit').onclick = async () => {
      if (!safeUrl) { trackShare('native', 'failed'); showManualFallback(); return; }
      if (typeof navigator.share !== 'function') {
        trackShare('copy', 'attempted');
        try { await copyText(safeUrl); trackShare('copy', 'copied'); ui.showToast('공유 창을 지원하지 않아 링크를 복사했어요.'); }
        catch (_) { trackShare('copy', 'failed'); showManualFallback(); }
        return;
      }
      trackShare('native', 'attempted');
      try { await navigator.share({ title: 'Gemini 학생 혜택', url: safeUrl }); trackShare('native', 'share_sheet_closed'); }
      catch (error) { trackShare('native', error?.name === 'AbortError' ? 'cancelled' : 'failed'); }
    };
  },
  cleanup() { this.observer?.disconnect(); this.observer = null;
    this.contentObserver?.disconnect(); this.contentObserver = null;
  },
};
