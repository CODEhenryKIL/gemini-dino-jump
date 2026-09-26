import { api } from '../api.js';
import { ui } from '../ui.js';

const slides = [
  {
    title: '화면을 터치하면 점프!',
    description: '게임 화면이나 아래 점프 버튼을 누르세요.',
    detail: '짧게 톡 → 낮게 점프 · 꾹 누르면 → 높게 점프',
    scene: `<div class="guide-game-demo" aria-hidden="true"><span class="guide-demo-stage">STAGE 1</span><span class="guide-demo-score">0000</span><img class="guide-demo-dino" src="/assets/icons/Dino-Dark.png" alt=""><span class="guide-demo-obstacle"></span><span class="guide-touch-ring"></span><span class="guide-demo-ground"></span></div><div class="guide-demo-jump" aria-hidden="true">점프<span class="guide-button-touch"></span></div>`,
    className: 'guide-slide-touch',
  },
  {
    title: '웃음 코인을 먹으면 +10점',
    description: '달리면서 코인을 모아 점수를 높여요.',
    detail: '더 높은 점수로 랭킹에 도전하세요.',
    scene: `<div class="guide-item-demo guide-coin-demo" aria-hidden="true"><img class="guide-item-dino" src="/assets/icons/Dino-Dark.png" alt=""><img class="guide-pickup" src="/assets/icons/Smile-Light.png" alt=""><span class="guide-pickup-result">+10점</span><span class="guide-demo-ground"></span></div>`,
    className: 'guide-slide-coin',
  },
  {
    title: '하트는 한 번 더 살아날 기회',
    description: '하트가 있으면 부딪혀도 다시 달려요.',
    detail: '최대 1개 보관 · 쓰고 다시 얻을 수 있어요.',
    scene: `<div class="guide-item-demo guide-heart-demo" aria-hidden="true"><img class="guide-item-dino" src="/assets/icons/Dino-Dark.png" alt=""><img class="guide-pickup" src="/assets/icons/Heart-Light.png" alt=""><span class="guide-pickup-result">부활 +1</span><span class="guide-revive-ring"></span><span class="guide-demo-ground"></span></div>`,
    className: 'guide-slide-heart',
  },
  {
    title: '랭킹 TOP3에 도전하세요',
    description: '행사 종료 시 최종 순위에 따라 선물을 드려요.',
    detail: '동점자는 같은 순위로 표시하며, 최종 동점 수상 기준은 추후 안내해요.',
    scene: `<div class="guide-rank-rewards"><div><span>1위</span><strong>5만원</strong></div><div><span>2위</span><strong>3만원</strong></div><div><span>3위</span><strong>1만원</strong></div></div><section class="guide-live-ranking" aria-label="현재 랭킹"><h4>현재 TOP3</h4><div class="guide-rank-content" aria-live="polite"></div></section>`,
    className: 'guide-slide-ranking',
  },
];

export function showGameGuide(router, autoStart = true) {
  const content = document.createElement('div');
  content.className = 'game-guide';
  let index = 0;
  let ranking = null;
  let rankingError = false;
  let loading = false;
  let confirm;
  let previous;
  let skip;
  let overlay;
  const finish = () => {
    ui.hideModal();
    if (autoStart) router.navigate('game');
  };

  function renderRanking() {
    const host = content.querySelector('.guide-rank-content');
    if (!host) return;
    host.replaceChildren();
    if (!ranking) {
      const message = document.createElement('p');
      message.className = 'guide-ranking-message';
      message.textContent = rankingError ? '지금 랭킹을 불러오지 못했어요.' : '현재 기록을 불러오는 중…';
      host.appendChild(message);
      if (rankingError) {
        const retry = document.createElement('button');
        retry.type = 'button'; retry.className = 'guide-text-button'; retry.textContent = '다시 불러오기';
        retry.onclick = loadRanking;
        host.appendChild(retry);
      }
      return;
    }
    const leaders = (ranking.leaderboard || []).filter((entry) => entry.rank <= 3);
    if (!leaders.length) {
      const empty = document.createElement('p'); empty.className = 'guide-ranking-message';
      empty.textContent = '아직 기록이 없어요. 첫 주인공이 되어 보세요!'; host.appendChild(empty);
    } else {
      const list = document.createElement('ol'); list.className = 'guide-ranking-list';
      for (const entry of leaders) {
        const row = document.createElement('li');
        if (entry.is_me) row.className = 'is-me';
        const rank = document.createElement('strong'); rank.textContent = `${entry.rank}위${entry.tied ? ' 공동' : ''}`;
        const nickname = document.createElement('span'); nickname.textContent = entry.nickname || '참가자';
        const score = document.createElement('span'); score.textContent = `${Number(entry.score || 0).toLocaleString('ko-KR')}점`;
        row.append(rank, nickname, score); list.appendChild(row);
      }
      host.appendChild(list);
    }
    const mine = document.createElement('p'); mine.className = 'guide-my-ranking';
    mine.textContent = ranking.me?.rank
      ? `내 순위 ${ranking.me.rank}위 · 최고 ${Number(ranking.me.best_score || 0).toLocaleString('ko-KR')}점`
      : '내 기록은 게임을 마치면 확인할 수 있어요.';
    host.appendChild(mine);
  }

  async function loadRanking() {
    if (loading || !content.isConnected) return;
    loading = true;
    rankingError = false;
    renderRanking();
    try {
      const response = await api.getLeaderboard();
      if (!content.isConnected) return;
      ranking = response;
    } catch (_) {
      if (content.isConnected) rankingError = true;
    } finally {
      loading = false;
      if (content.isConnected) renderRanking();
    }
  }

  function renderSlide() {
    const slide = slides[index];
    content.innerHTML = `<div class="guide-step-indicator" aria-label="${slides.length}단계 중 ${index + 1}단계">${slides.map((_, i) => `<span class="${i === index ? 'active' : ''}" aria-hidden="true"></span>`).join('')}<small>${index + 1} / ${slides.length}</small></div><section class="guide-slide ${slide.className}" aria-roledescription="슬라이드"><h4 tabindex="-1" class="guide-slide-title">${slide.title}</h4><p class="guide-slide-description">${slide.description}</p>${slide.scene}${slide.detail ? `<p class="guide-slide-detail">${slide.detail}</p>` : ''}</section>`;
    if (previous) previous.disabled = index === 0;
    if (confirm) confirm.textContent = index === slides.length - 1 ? (autoStart ? '게임 시작' : '확인') : '다음';
    if (skip) skip.hidden = index === slides.length - 1;
    if (index === slides.length - 1) {
      renderRanking();
      if (!ranking && !rankingError) loadRanking();
    }
  }

  function changeSlide(next) {
    index = Math.max(0, Math.min(slides.length - 1, next));
    renderSlide();
    content.querySelector('.guide-slide-title').focus({ preventScroll: true });
    overlay.querySelector('.modal-card').scrollTop = 0;
  }

  renderSlide();
  ui.showModal({
    title: '공룡 점프 가이드', content, confirmText: '다음', cancelText: '닫기',
    onConfirm: () => {
      if (index < slides.length - 1) { changeSlide(index + 1); return false; }
      finish();
    },
  });
  overlay = document.getElementById('common-modal-overlay');
  overlay.classList.add('game-guide-dialog');
  confirm = overlay.querySelector('.modal-actions .btn-primary');
  const card = overlay.querySelector('.modal-card');
  const close = overlay.querySelector('.modal-actions .btn-secondary');
  close.className = 'guide-close';
  close.textContent = '×';
  close.setAttribute('aria-label', '가이드 닫기');
  card.insertBefore(close, card.firstChild);
  previous = document.createElement('button');
  previous.type = 'button'; previous.className = 'btn btn-secondary guide-previous';
  previous.textContent = '이전'; previous.disabled = true;
  previous.onclick = () => changeSlide(index - 1);
  confirm.before(previous);
  skip = document.createElement('button'); skip.type = 'button'; skip.className = 'guide-text-button guide-skip';
  skip.textContent = autoStart ? '건너뛰고 게임 시작' : '건너뛰기'; skip.onclick = finish;
  overlay.querySelector('.modal-card').appendChild(skip);

  let touchStart = null;
  content.addEventListener('touchstart', (event) => {
    if (event.touches.length !== 1) { touchStart = null; return; }
    touchStart = { x: event.touches[0].clientX, y: event.touches[0].clientY };
  }, { passive: true });
  content.addEventListener('touchend', (event) => {
    if (!touchStart || !event.changedTouches.length) return;
    const dx = event.changedTouches[0].clientX - touchStart.x;
    const dy = event.changedTouches[0].clientY - touchStart.y;
    touchStart = null;
    if (Math.abs(dx) > 55 && Math.abs(dx) > Math.abs(dy) * 1.5) changeSlide(index + (dx < 0 ? 1 : -1));
  }, { passive: true });
  content.addEventListener('touchcancel', () => { touchStart = null; }, { passive: true });
}
