import { showGameGuide } from '../components/game_guide.js';
import { analytics } from '../analytics.js';

export const HomeView = {
  render(container, router) {
    container.innerHTML = `
      <section class="card hero-card">
        <div class="home-event-header">
          <div class="home-event-badges">
            <span class="home-event-badge home-event-badge-team">#TeamGemini</span>
            <span class="home-event-badge home-event-badge-campus">2026 캠퍼스 챌린지</span>
          </div>
          <p class="home-event-organizer">공식 Google Student Ambassador 운영</p>
        </div>
        <h1><span class="home-built-with"><img class="home-antigravity-logo" src="/assets/logos/antigravity-icon-full-color.png" alt="Antigravity" width="32" height="32"><span><span class="home-ai-word"><span class="google-blue">G</span><span class="google-red">o</span><span class="google-yellow">o</span><span class="google-blue">g</span><span class="google-green">l</span><span class="google-red">e</span> <span class="google-blue">A</span><span class="google-green">I</span></span>로 만든</span></span><span class="home-game-title">공룡 게임</span></h1>
        <p class="home-campaign-line">추억의 공룡 게임 한 판 하고 삼텐바이미 받자!</p>
        <img class="hero-dino" src="/assets/icons/Dino-Dark.png" alt="달리는 공룡">
        <div class="stat-grid">
          <div><small>기본권</small><strong id="home-basic-ticket">0장</strong></div>
          <div><small>초대권</small><strong id="home-invite-ticket">0장</strong></div>
          <div><small>최고 점수</small><strong id="home-best-score">0점</strong></div>
        </div>
        <p id="home-ticket-note" class="status-note" role="status" hidden></p>
        <button id="btn-start-jump" class="btn btn-primary">게임 시작</button>
        <button id="btn-home-draw" class="btn btn-secondary" hidden>복주머니 열기</button>
        <button id="btn-how-to-play" class="btn btn-outline btn-sm">조작 방법과 규칙</button>
        <p class="home-eligibility">게임은 누구나 참여할 수 있고, 경품 수령은 대학생을 대상으로 해요.</p>
      </section>`;
    this.updateState(container, router);
    container.querySelector('#btn-start-jump').onclick = () => {
      if (typeof analytics !== 'undefined') analytics.track('game_cta_clicked', { source: 'home' });
      if (router.state.pendingGameSession) { router.navigate('game'); return; }
      let seen = false;
      try { seen = Boolean(localStorage.getItem('gemini_dino_guide_seen')); } catch (_) {}
      if (seen) router.navigate('game');
      else this.showGuideModal(router, true);
    };
    container.querySelector('#btn-how-to-play').onclick = () => this.showGuideModal(router, false);
    container.querySelector('#btn-home-draw').onclick = () => {
      const status = router.state.draw?.status;
      if (!['AVAILABLE', 'DRAWN'].includes(status)) return;
      analytics.track('draw_cta_clicked', { source: 'home', draw_status: status });
      router.navigate('draw');
    };
  },
  updateState(container, router) {
    const { tickets = {}, bestScore } = router.state;
    const start = container.querySelector('#btn-start-jump');
    if (!start) return;
    container.querySelector('#home-basic-ticket').textContent = `${tickets.initial || 0}장`;
    container.querySelector('#home-invite-ticket').textContent = `${tickets.invitation || 0}장`;
    container.querySelector('#home-best-score').textContent = `${bestScore || 0}점`;
    const available = Number(tickets.available_total ?? ((tickets.initial || 0) + (tickets.invitation || 0)));
    const pendingSession = router.state.pendingGameSession;
    const drawStatus = router.state.draw?.status || 'LOCKED';
    const drawButton = container.querySelector('#btn-home-draw');
    drawButton.hidden = !['AVAILABLE', 'DRAWN'].includes(drawStatus);
    drawButton.textContent = drawStatus === 'DRAWN' ? '내 복주머니 결과 보기' : '복주머니 열기';
    const campaignStatus = router.config?.campaign?.status || 'ACTIVE';
    const note = container.querySelector('#home-ticket-note');
    note.hidden = true;
    note.textContent = '';
    if (tickets.invitation_reserved) {
      note.hidden = false;
      note.textContent = `장애 복구 중인 초대권 ${tickets.invitation_reserved}장이 별도로 보호되고 있어요.`;
    } else if (new Date(tickets.cooldown_until).getTime() > Date.now()) {
      note.hidden = false;
      note.textContent = `초대권 추가 적립 대기: ${new Date(tickets.cooldown_until).toLocaleString('ko-KR')}까지 · 가진 게임권은 사용할 수 있어요.`;
    } else if (!pendingSession && available < 1) {
      note.hidden = false;
      note.textContent = '사용 가능한 게임권이 없어요. 친구의 새 유효 방문으로 초대권을 받을 수 있어요.';
    }
    start.disabled = !pendingSession && (campaignStatus !== 'ACTIVE' || available < 1);
    start.textContent = '게임 시작';
    if (pendingSession) start.textContent = pendingSession.status === 'FAULT_REPORTED' ? '장애 복구 상태 확인' : '진행 중 게임 복원';
    else if (campaignStatus !== 'ACTIVE') {
      start.textContent = campaignStatus === 'ENDED' ? '행사가 종료됐어요' : '행사가 잠시 중단됐어요';
      note.hidden = false;
      note.textContent = campaignStatus === 'ENDED' ? '행사가 종료되어 새 게임을 시작할 수 없어요. 기존 기록과 수령 상태는 확인할 수 있어요.' : '운영자가 행사를 다시 시작하면 게임에 참여할 수 있어요.';
    }
    else if (available < 1) start.textContent = '게임권이 필요해요';
  },
  showGuideModal(router, autoStart = true) {
    showGameGuide(router, autoStart);
  },
};
