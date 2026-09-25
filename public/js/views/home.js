import { ui } from '../ui.js';
import { analytics } from '../analytics.js';

function guideContent() {
  if (typeof document === 'undefined') return '모바일은 화면을 눌러 점프하고, PC는 Space 또는 ↑ 키를 사용합니다.';
  const wrapper = document.createElement('div');
  wrapper.className = 'guide-list';
  for (const text of ['모바일은 화면이나 JUMP 버튼을 눌러 점프해요.', 'PC는 Space 또는 ↑ 키를 사용해요.', '장애물 충돌은 정상 종료이며 점수가 서버에서 검증돼요.', '첫 정상 게임 뒤 행사당 한 번 복주머니를 열 수 있어요.']) {
    const row = document.createElement('p');
    row.textContent = text;
    wrapper.appendChild(row);
  }
  return wrapper;
}

export const HomeView = {
  render(container, router) {
    const { tickets = { initial: router.state.tickets || 0, invitation: 0 }, bestScore } = router.state;
    container.innerHTML = `
      <section class="card hero-card">
        <span class="sticker-badge badge-blue">#TeamGemini</span>
        <h1>공룡 점프, 어디까지 갈 수 있어?</h1>
        <p>장애물을 피하고 나만의 최고 기록에 도전하세요.</p>
        <img class="hero-dino" src="/assets/icons/Dino-Dark.png" alt="달리는 공룡">
        <div class="stat-grid">
          <div><small>기본권</small><strong id="home-basic-ticket">0장</strong></div>
          <div><small>초대권</small><strong id="home-invite-ticket">0장</strong></div>
          <div><small>최고 점수</small><strong id="home-best-score">0점</strong></div>
        </div>
        <p id="home-ticket-note" class="status-note"></p>
        <button id="btn-start-jump" class="btn btn-primary">공룡 점프 시작</button>
        <button id="btn-how-to-play" class="btn btn-outline btn-sm">조작 방법과 규칙</button>
      </section>
      <section class="card compact-card">
        <h2>복주머니와 재도전</h2>
        <p>첫 정상 게임 후 복주머니는 참가자당 한 번 열 수 있어요. 친구가 링크에서 3초 이상 활동하고 화면을 누르면 초대권이 지급됩니다.</p>
      </section>`;
    container.querySelector('#home-basic-ticket').textContent = `${tickets.initial || 0}장`;
    container.querySelector('#home-invite-ticket').textContent = `${tickets.invitation || 0}장`;
    container.querySelector('#home-best-score').textContent = `${bestScore || 0}점`;
    const available = Number(tickets.available_total ?? ((tickets.initial || 0) + (tickets.invitation || 0)));
    const pendingSession = router.state.pendingGameSession;
    const campaignStatus = router.config?.campaign?.status || 'ACTIVE';
    const note = container.querySelector('#home-ticket-note');
    if (tickets.invitation_reserved) note.textContent = `장애 복구 중인 초대권 ${tickets.invitation_reserved}장이 별도로 보호되고 있어요.`;
    else if (tickets.cooldown_until) note.textContent = `초대권 추가 적립 대기: ${new Date(tickets.cooldown_until).toLocaleString('ko-KR')}까지`;
    else note.textContent = '기본권을 먼저 사용하고 이후 초대권을 사용합니다.';
    const start = container.querySelector('#btn-start-jump');
    start.disabled = !pendingSession && (campaignStatus !== 'ACTIVE' || available < 1);
    if (pendingSession) start.textContent = pendingSession.status === 'FAULT_REPORTED' ? '장애 복구 상태 확인' : '진행 중 게임 복원';
    else if (campaignStatus !== 'ACTIVE') {
      start.textContent = campaignStatus === 'ENDED' ? '행사가 종료됐어요' : '행사가 잠시 중단됐어요';
      note.textContent = '운영자가 행사를 다시 시작하면 게임에 참여할 수 있어요.';
    }
    else if (available < 1) start.textContent = '게임권이 필요해요';
    start.onclick = () => {
      if (typeof analytics !== 'undefined') analytics.track('game_cta_clicked', { source: 'home' });
      if (pendingSession) { router.navigate('game'); return; }
      let seen = false;
      try { seen = Boolean(localStorage.getItem('gemini_dino_guide_seen')); } catch (_) {}
      if (seen) router.navigate('game');
      else this.showGuideModal(router, true);
    };
    container.querySelector('#btn-how-to-play').onclick = () => this.showGuideModal(router, false);
  },
  showGuideModal(router, autoStart = true) {
    ui.showModal({
      title: '공룡 점프 조작 가이드', content: guideContent(), confirmText: autoStart ? '게임 시작' : '확인',
      cancelText: autoStart ? '취소' : null,
      onConfirm: () => { try { localStorage.setItem('gemini_dino_guide_seen', 'true'); } catch (_) {} if (autoStart) router.navigate('game'); },
    });
  },
};
