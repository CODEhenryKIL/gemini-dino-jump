import { analytics } from '../analytics.js';

export const BenefitView = {
  observer: null,
  render(container, router) {
    container.innerHTML = `
      <section class="card compact-card">
        <span class="sticker-badge badge-blue">Gemini 학생 혜택</span>
        <h1>공식 혜택 페이지에서 내용을 확인하세요</h1>
        <p>이 화면은 링크 노출과 클릭만 측정합니다. 클릭은 도착·학생 인증·혜택 등록 완료를 뜻하지 않습니다.</p>
        <a id="btn-go-benefit" class="btn btn-primary" target="_blank" rel="noopener noreferrer">Gemini 혜택 확인하기</a>
      </section>
      <section class="card compact-card">
        <h2>콘텐츠 안내</h2>
        <p>승인되지 않은 Notion 경유 링크는 비활성화되어 있습니다. 외부 페이지 내부 열람과 체류를 이 서비스가 관측한다고 표시하지 않습니다.</p>
        <button class="btn btn-secondary" disabled>학습 가이드 · 승인 대기</button>
        <button class="btn btn-secondary" disabled>취업 가이드 · 승인 대기</button>
        <button class="btn btn-secondary" disabled>활용 사례 · 승인 대기</button>
      </section>
      <section class="card compact-card"><h2>현재 행사 규칙</h2><p>최초 기본권 1장, 초대권 최대 3장, 3장 도달 시 10시간 추가 적립 대기, 참가자당 복주머니 1회, 관리자 수동 연락 및 지급입니다.</p></section>`;
    const link = container.querySelector('#btn-go-benefit');
    const safeUrl = router.config?.benefit_url || 'https://gemini.google.com/students';
    link.href = safeUrl;
    analytics.track('benefit_viewed');
    let viewed = false;
    this.observer = typeof IntersectionObserver === 'function' ? new IntersectionObserver((entries) => {
      if (!viewed && !document.hidden && entries.some((entry) => entry.isIntersecting && entry.intersectionRatio >= 0.5)) {
        viewed = true;
        analytics.track('gemini_cta_viewed', { position: 'benefit_main' });
        this.observer?.disconnect();
      }
    }, { threshold: [0.5] }) : null;
    if (this.observer) this.observer.observe(link);
    else if (!document.hidden) analytics.track('gemini_cta_viewed', { position: 'benefit_main' });
    link.onclick = () => analytics.track('gemini_cta_clicked', { position: 'benefit_main' });
  },
  cleanup() { this.observer?.disconnect(); this.observer = null; },
};
