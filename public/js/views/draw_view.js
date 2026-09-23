/**
 * S05 Lucky Pouch Selection & Scratch Card Reveal View (v1.1 Specification)
 */

import { api } from '../api.js';
import { ui } from '../ui.js';
import { audio } from '../game/audio.js';
import { ScratchCard } from '../components/scratch_card.js';
import { track } from '../analytics.js';

export const DrawView = {
  selectedPouch: null,
  drawResult: null,
  revealTimer: null,
  abortController: null,
  scratchCard: null,

  async render(container, router, epoch) {
    this.cleanup(); this.abortController = new AbortController();
    const lastResult = router.state.lastResult || {};
    const sessionId = lastResult.sessionId;

    if (!sessionId) {
      ui.showToast('완료된 게임 세션이 없습니다.');
      router.navigate('home');
      return;
    }

    container.innerHTML = `
      <!-- Step 1: Pouch Selection Stage -->
      <div id="pouch-select-stage" class="card pouch-selection-container" style="text-align: center; padding: 24px 16px;">
        <span class="sticker-badge badge-yellow">STEP 1. 행운의 주머니 선택</span>
        <h2 style="font-size: 20px; font-weight: 900; margin-top: 4px;">어떤 주머니에 행운이 있을까요?</h2>
        <p style="font-size: 13px; color: var(--text-sub);">
          같은 확률의 복주머니 3개 중 마음에 드는 1개를 골라주세요.
        </p>

        <!-- 3 Pouches Grid -->
        <div class="pouch-grid">
          <div class="pouch-item wiggle" data-index="0">
            <div class="pouch-icon">🧧</div>
            <div class="pouch-label">1번 복주머니</div>
          </div>
          <div class="pouch-item wiggle" data-index="1">
            <div class="pouch-icon">🧧</div>
            <div class="pouch-label">2번 복주머니</div>
          </div>
          <div class="pouch-item wiggle" data-index="2">
            <div class="pouch-icon">🧧</div>
            <div class="pouch-label">3번 복주머니</div>
          </div>
        </div>

        <button id="btn-open-pouch" class="btn btn-primary" style="height: 52px; opacity: 0.5; pointer-events: none;">
          <span>선택한 주머니 열기</span>
        </button>
      </div>

      <!-- Step 2: Scratch Lottery Stage (Initially Hidden) -->
      <div id="scratch-stage" class="card scratch-stage-container" style="display: none; text-align: center; padding: 24px 16px;">
        <span class="sticker-badge badge-blue">STEP 2. 즉석 복권 긁기</span>
        <h2 style="font-size: 20px; font-weight: 900; margin-top: 4px;">복권을 긁어 행운을 확인하세요!</h2>
        <p style="font-size: 13px; color: var(--text-sub);">
          은색 코팅을 손가락이나 마우스로 문질러보세요.
        </p>

        <!-- The Scratch Card -->
        <div class="scratch-ticket">
          <div class="ticket-header">
            <span>Team Gemini Lucky Ticket</span>
            <span id="ticket-number-label">№ 2026</span>
          </div>

          <div class="ticket-scratch-area">
            <!-- Underneath Result Content -->
            <div id="scratch-underlay" class="ticket-result-underlay">
              <img id="result-prize-img" src="/assets/icons/Smile-Light.png" alt="Prize">
              <div id="result-prize-title" class="result-title">메가커피 아메리카노</div>
              <div id="result-prize-sub" class="result-sub">축하합니다! 즉석 경품에 당첨되었습니다.</div>
            </div>

            <!-- Silver Canvas Coating on Top -->
            <canvas id="scratch-canvas"></canvas>
          </div>
        </div>

        <!-- Secondary Reveal Button & Hint -->
        <div style="display: flex; flex-direction: column; align-items: center; gap: 10px; width: 100%;">
          <div class="scratch-hint-text">
            <span>✨ 70% 이상 긁으면 전체 내용이 자동 공개됩니다</span>
          </div>

          <button id="btn-instant-reveal" class="btn btn-secondary btn-sm" style="max-width: 220px;">
            <span>⚡ 한 번에 확인하기</span>
          </button>
        </div>

        <!-- Next Action Button (After Revealed) -->
        <div id="post-reveal-actions" style="width: 100%; margin-top: 12px; display: none;">
          <button id="btn-claim-or-retry" class="btn btn-primary" style="height: 54px;">
            <span>결과 확인 완료</span>
          </button>
        </div>
      </div>
    `;

    const selectStage = container.querySelector('#pouch-select-stage');
    const scratchStage = container.querySelector('#scratch-stage');
    const openBtn = container.querySelector('#btn-open-pouch');
    const pouchItems = container.querySelectorAll('.pouch-item');

    try {
      const existing = await api.getSession(sessionId, { signal: this.abortController.signal });
      if (!router.isCurrent(epoch, 'draw')) return;
      if (existing.draw) { selectStage.style.display = 'none'; scratchStage.style.display = 'flex'; this.drawResult = existing.draw; this.initScratchTicket(container, router, existing.draw); return; }
    } catch (error) { if (error.name === 'AbortError') return; }

    // 1. Pouch selection handlers
    pouchItems.forEach((item) => {
      item.onclick = () => {
        pouchItems.forEach(p => p.classList.remove('selected'));
        item.classList.add('selected');
        this.selectedPouch = parseInt(item.dataset.index, 10);

        openBtn.style.opacity = '1';
        openBtn.style.pointerEvents = 'auto';
      };
    });

    // 2. Confirm selection & Open Pouch
    openBtn.onclick = async () => {
      if (this.selectedPouch === null) return;

      // Animate selection: fade out unselected
      pouchItems.forEach((p, idx) => {
        if (idx !== this.selectedPouch) {
          p.classList.add('faded');
        }
      });
      openBtn.textContent = '복주머니 여는 중...';
      openBtn.style.pointerEvents = 'none';

      try {
        // Call backend atomic draw API
        track('draw_open', { screen: 'draw' });
        const drawRes = await api.drawPouch(sessionId, this.selectedPouch, { signal: this.abortController.signal });
        if (!router.isCurrent(epoch, 'draw')) return;
        this.drawResult = drawRes;

        // 1.2s pouch opening animation delay
        this.revealTimer = setTimeout(() => {
          selectStage.style.display = 'none';
          scratchStage.style.display = 'flex';
          this.initScratchTicket(container, router, drawRes);
        }, 1200);

      } catch (err) {
        if (err.name !== 'AbortError') { openBtn.textContent = '같은 결과 다시 확인'; openBtn.style.pointerEvents = 'auto'; ui.showToast(err.message || '추첨 결과를 확인하지 못했습니다. 다시 시도해 주세요.'); }
      }
    };
  },

  initScratchTicket(container, router, drawRes) {
    const underlayImg = container.querySelector('#result-prize-img');
    const underlayTitle = container.querySelector('#result-prize-title');
    const underlaySub = container.querySelector('#result-prize-sub');
    const scratchCanvas = container.querySelector('#scratch-canvas');
    const instantBtn = container.querySelector('#btn-instant-reveal');
    const actionContainer = container.querySelector('#post-reveal-actions');
    const actionBtn = container.querySelector('#btn-claim-or-retry');

    // Populate underlay content based on draw result
    if (drawRes.is_won) {
      underlayImg.src = ui.safeImageUrl(drawRes.prize?.image_url, '/assets/icons/Heart-Dark.png');
      underlayTitle.textContent = drawRes.prize?.name || '테스트 경품';
      underlayTitle.style.color = 'var(--primary)';
      underlaySub.textContent = drawRes.is_test ? '개발용 테스트 추첨 결과입니다.' : '추첨 결과를 확인했습니다.';
      actionBtn.innerHTML = '<span>🎁 경품 수령함 확인하기</span>';
      actionBtn.classList.remove('btn-secondary');
      actionBtn.classList.add('btn-primary');
    } else {
      underlayImg.src = '/assets/icons/Rocket-Dark.png';
      underlayTitle.textContent = '이번 추첨은 미당첨입니다';
      underlayTitle.style.color = '#1967D2';
      underlaySub.textContent = '공식 Gemini 학생 혜택은 별도 안내에서 확인할 수 있습니다.';
      actionBtn.innerHTML = '<span>🌐 Gemini 학생 혜택 확인하기</span>';
      actionBtn.classList.remove('btn-secondary');
      actionBtn.classList.add('btn-primary');
    }

    // Initialize Scratch Card
    const scratchCard = new ScratchCard(scratchCanvas, {
      threshold: 0.70, // 70% 이상 긁어야 자동 공개
      onReveal: async () => {
        // Complete scratch on backend
        if (drawRes.draw_id) {
          api.completeScratch(drawRes.draw_id).catch(() => ui.showToast('긁기 완료 저장에 실패했습니다. 수령함에서 다시 확인해 주세요.'));
        }
        instantBtn.style.display = 'none';
        actionContainer.style.display = 'block';

        if (drawRes.is_won) {
          audio.playWin();
          ui.showToast(`🎉 ${drawRes.is_test ? '테스트 추첨' : '추첨'} 당첨: ${drawRes.prize?.name || '경품'}!`);
        } else {
          audio.playWin();
          ui.showToast('추첨 결과를 확인했습니다.');
        }
      }
    });
    this.scratchCard = scratchCard;

    instantBtn.onclick = () => {
      scratchCard.revealInstantly();
    };

    actionBtn.onclick = () => {
      if (drawRes.is_won) {
        router.navigate('claims');
      } else {
        router.navigate('benefit');
      }
    };
  },
  cleanup() { clearTimeout(this.revealTimer); this.revealTimer = null; this.abortController?.abort(); this.abortController = null; this.scratchCard?.destroy(); this.scratchCard = null; this.selectedPouch = null; }
};
