import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { ScratchCard } from '../components/scratch_card.js';

const SCRATCH_KEY_PREFIX = 'dino_scratch_';
function storageGet(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }
function storageSet(key, value) { try { sessionStorage.setItem(key, value); } catch (_) {} }
function storageRemove(key) { try { sessionStorage.removeItem(key); } catch (_) {} }

export const DrawView = {
  scratchCard: null,
  selectedPouch: null,
  renderToken: 0,
  resultViewed: false,

  async render(container, router, renderToken) {
    this.cleanup();
    this.renderToken = renderToken;
    container.innerHTML = '<section class="card empty-state"><p>복주머니 상태를 확인하는 중...</p></section>';
    analytics.track('draw_entered');
    try {
      const state = await api.getDraw();
      if (!router.isCurrent(renderToken)) return;
      router.state.draw = state;
      if (state.status === 'LOCKED') return this.renderLocked(container, router);
      if (state.status === 'DRAWN' && state.draw) return this.renderScratch(container, router, state.draw, renderToken);
      this.renderSelection(container, router, renderToken);
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      this.renderError(container, router, error);
    }
  },

  renderLocked(container, router) {
    container.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '복주머니가 아직 잠겨 있어요';
    const text = document.createElement('p'); text.textContent = '정상 검증된 게임을 한 번 완료하면 행사당 한 번 열 수 있어요.';
    const button = document.createElement('button'); button.className = 'btn btn-primary'; button.textContent = '게임하러 가기'; button.onclick = () => router.navigate('home');
    card.append(title, text, button); container.appendChild(card);
  },

  renderSelection(container, router, renderToken = this.renderToken) {
    container.innerHTML = `
      <section class="card pouch-selection-container">
        <span class="sticker-badge badge-yellow">행사당 한 번</span>
        <h2>복주머니 하나를 골라주세요</h2>
        <p>하나를 고르면 결과가 정해져요. 정해진 결과는 새로고침해도 같아요.</p>
        <div class="pouch-grid">
          <button class="pouch-item wiggle" data-index="0"><span class="pouch-icon">🧧</span><span class="pouch-label">1번</span></button>
          <button class="pouch-item wiggle" data-index="1"><span class="pouch-icon">🧧</span><span class="pouch-label">2번</span></button>
          <button class="pouch-item wiggle" data-index="2"><span class="pouch-icon">🧧</span><span class="pouch-label">3번</span></button>
        </div>
        <button id="btn-open-pouch" class="btn btn-primary" disabled>선택한 주머니 열기</button>
      </section>`;
    const open = container.querySelector('#btn-open-pouch');
    const pouches = [...container.querySelectorAll('.pouch-item')];
    pouches.forEach((pouch) => {
      pouch.onclick = () => {
        pouches.forEach((item) => item.classList.toggle('selected', item === pouch));
        this.selectedPouch = Number(pouch.dataset.index);
        open.disabled = false;
        analytics.track('pouch_selected', { action: `pouch_${this.selectedPouch}` });
      };
    });
    open.onclick = async () => {
      const requestToken = renderToken;
      open.disabled = true;
      open.textContent = '결과 확정 중...';
      try {
        const response = await api.drawPouch(this.selectedPouch);
        const draw = response.draw || response;
        router.announceStateChange();
        if (router.isCurrent(requestToken)) {
          router.state.draw = { status: 'DRAWN', draw_id: draw.draw_id, draw };
          this.renderScratch(container, router, draw, requestToken);
        } else {
          await router.refreshState({ quiet: true });
        }
      } catch (error) {
        if (!router.isCurrent(requestToken)) return;
        open.disabled = false;
        open.textContent = '다시 열기';
        ui.showToast(error.message);
      }
    };
  },

  renderScratch(container, router, draw, renderToken = this.renderToken) {
    this.cleanup();
    container.innerHTML = `
      <section class="card scratch-stage-container">
        <span class="sticker-badge badge-blue">결과 공개</span>
        <h2>복권을 긁어 결과를 확인하세요</h2>
        <div class="scratch-ticket">
          <div class="ticket-header"><span>Team Gemini Lucky Ticket</span><span>행사당 1회</span></div>
          <div class="ticket-scratch-area">
            <div class="ticket-result-underlay" id="scratch-result-content" aria-hidden="true" inert><img id="result-prize-img" src="/assets/icons/Smile-Light.png" alt=""><div id="result-prize-title" class="result-title"></div><div id="result-prize-sub" class="result-sub"></div></div>
            <canvas id="scratch-canvas" tabindex="0" role="button" aria-label="복권 긁기. Enter 또는 Space 키로 같은 결과를 바로 확인할 수 있습니다." aria-describedby="scratch-instruction"></canvas>
          </div>
        </div>
        <p id="scratch-instruction" class="scratch-hint-text">화면을 긁거나 아래 버튼으로 같은 서버 확정 결과를 확인하세요.</p>
        <button id="btn-instant-reveal" class="btn btn-secondary btn-sm">긁기 어려우면 결과 확인</button>
        <p id="restored-pouch" class="status-note"></p>
        <p id="scratch-save-status" class="status-note" role="status"></p>
        <div id="post-reveal-actions" hidden><button id="btn-after-draw" class="btn btn-primary"></button></div>
      </section>`;
    const prize = draw.prize || {};
    const resultContent = container.querySelector('#scratch-result-content');
    resultContent.setAttribute('aria-hidden', 'true');
    resultContent.inert = true;
    const scratchCanvas = container.querySelector('#scratch-canvas');
    scratchCanvas.tabIndex = 0;
    const img = container.querySelector('#result-prize-img');
    img.src = prize.image_url || (draw.is_won ? '/assets/icons/Heart-Dark.png' : '/assets/icons/Rocket-Dark.png');
    img.alt = draw.is_won ? '당첨 경품' : '혜택 안내';
    ui.text(container.querySelector('#result-prize-title'), draw.is_won ? prize.name : '이번 복주머니는 미당첨이에요');
    ui.text(container.querySelector('#result-prize-sub'), draw.is_won ? '운영자가 정보를 확인하고 직접 연락해 지급합니다.' : '게임 기록과 초대 도전은 계속 이용할 수 있어요.');
    if (Number.isInteger(draw.pouch_index)) ui.text(container.querySelector('#restored-pouch'), `${draw.pouch_index + 1}번 주머니에서 정해진 결과예요. 새로고침해도 같아요.`);
    const after = container.querySelector('#btn-after-draw');
    after.textContent = draw.is_won ? '수령 정보 입력하기' : '혜택 안내 보기';
    after.onclick = () => router.navigate(draw.is_won ? 'claims' : 'benefit');
    const showResult = () => {
      if (!router.isCurrent(renderToken)) return;
      resultContent.inert = false;
      resultContent.removeAttribute('inert');
      resultContent.setAttribute('aria-hidden', 'false');
      const revealButton = container.querySelector('#btn-instant-reveal');
      container.querySelector('#post-reveal-actions').hidden = false;
      if (typeof document !== 'undefined' && (document.activeElement === scratchCanvas || document.activeElement === revealButton)) after.focus();
      scratchCanvas.tabIndex = -1;
      scratchCanvas.setAttribute('aria-hidden', 'true');
      revealButton.hidden = true;
      if (!this.resultViewed) {
        this.resultViewed = true;
        analytics.track('draw_result_viewed', { result_type: draw.is_won ? 'won' : 'no_prize' });
      }
      router.announceStateChange();
    };
    const persistReveal = async () => {
      const requestToken = renderToken;
      if (!router.isCurrent(requestToken)) return;
      showResult();
      if (draw.scratch_completed) return;
      const storageKey = `${SCRATCH_KEY_PREFIX}${draw.draw_id}`;
      const eventId = storageGet(storageKey) || api.createRequestId('scratch');
      storageSet(storageKey, eventId);
      const status = container.querySelector('#scratch-save-status');
      const revealButton = container.querySelector('#btn-instant-reveal');
      status.textContent = '결과 확인 상태를 저장하는 중...';
      try {
        await api.completeScratch(draw.draw_id, eventId);
        if (!router.isCurrent(requestToken)) return;
        draw.scratch_completed = true;
        storageRemove(storageKey);
        status.textContent = '결과 확인이 저장됐습니다.';
        analytics.track('scratch_completed', { result_type: draw.is_won ? 'won' : 'no_prize', prize_kind: prize.category || 'NONE' });
      } catch (error) {
        if (!router.isCurrent(requestToken)) return;
        status.textContent = '결과는 그대로 유지됩니다. 저장 연결을 다시 시도해 주세요.';
        revealButton.hidden = false;
        revealButton.textContent = '저장 다시 시도';
        revealButton.onclick = persistReveal;
        ui.showToast(error.message || '결과 확인 상태를 저장하지 못했습니다.');
      }
    };
    this.scratchCard = new ScratchCard(scratchCanvas, {
      threshold: 0.7,
      onStart: () => analytics.track('scratch_started'),
      onKeyboardReveal: () => analytics.track('scratch_reveal_requested', { action: 'keyboard' }),
      onReveal: persistReveal,
    });
    container.querySelector('#btn-instant-reveal').onclick = () => {
      analytics.track('scratch_reveal_requested', { action: 'accessibility_button' });
      this.scratchCard.revealInstantly();
    };
    if (draw.scratch_completed || draw.revealed) {
      this.scratchCard.revealInstantly({ restored: true });
      showResult();
    }
  },

  renderError(container, router, error) {
    container.replaceChildren();
    const card = document.createElement('section'); card.className = 'card empty-state';
    const p = document.createElement('p'); p.textContent = error.message || '복주머니 상태를 불러오지 못했습니다.';
    const retry = document.createElement('button'); retry.className = 'btn btn-primary'; retry.textContent = '다시 시도'; retry.onclick = () => router.navigate('draw');
    card.append(p, retry); container.appendChild(card);
  },
  cleanup() { this.scratchCard?.destroy?.(); this.scratchCard = null; this.selectedPouch = null; this.resultViewed = false; },
};
