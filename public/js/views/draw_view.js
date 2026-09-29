import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { ScratchCard } from '../components/scratch_card.js';
import { prepareResultReferralShare } from '../referral_share.js';

const SCRATCH_KEY_PREFIX = 'dino_scratch_';
const PENDING_DRAW_KEY = 'dino_pending_draw_v1';
function storageGet(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }
function storageSet(key, value) { try { sessionStorage.setItem(key, value); } catch (_) {} }
function storageRemove(key) { try { sessionStorage.removeItem(key); } catch (_) {} }
function pendingDrawGet() {
  try {
    const value = JSON.parse(storageGet(PENDING_DRAW_KEY) || 'null');
    if (!value || typeof value.event_id !== 'string' || !Number.isInteger(value.pouch_index) || !Number.isInteger(value.expected_round_number)) return null;
    return value;
  } catch (_) { return null; }
}
function pendingDrawSet(value) { storageSet(PENDING_DRAW_KEY, JSON.stringify(value)); }
function pendingDrawClear() { storageRemove(PENDING_DRAW_KEY); }
function drawRound(state) { return Number(state?.draw?.round_number || state?.used_count || 0); }
function pendingDrawCommitted(state, pending) { return Boolean(pending && drawRound(state) >= pending.expected_round_number); }

export const DrawView = {
  scratchCard: null,
  selectedPouch: null,
  renderToken: 0,
  resultViewed: false,
  activeDrawContext: null,
  postActionVersion: 0,

  async render(container, router, renderToken) {
    this.cleanup();
    this.renderToken = renderToken;
    container.innerHTML = '<section class="card empty-state"><p>복주머니 상태를 확인하는 중...</p></section>';
    analytics.track('draw_entered');
    try {
      const state = await api.getDraw();
      if (!router.isCurrent(renderToken)) return;
      this.renderResolvedState(container, router, renderToken, state);
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      this.renderError(container, router, error);
    }
  },

  renderResolvedState(container, router, renderToken, state) {
    router.state.draw = state;
    const pending = pendingDrawGet();
    if (pendingDrawCommitted(state, pending)) pendingDrawClear();
    if (state.status === 'LOCKED') return this.renderLocked(container, router);
    const latestNeedsAttention = state.draw && state.draw.scratch_completed !== true;
    if ((['DRAWN', 'WON', 'EXHAUSTED'].includes(state.status) || latestNeedsAttention) && state.draw) {
      return this.renderScratch(container, router, state.draw, renderToken, state);
    }
    return this.renderSelection(container, router, renderToken);
  },

  renderLocked(container, router) {
    container.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '복주머니가 아직 잠겨 있어요';
    const text = document.createElement('p'); text.textContent = '정상 검증된 게임을 한 번 완료하면 첫 복주머니를 열 수 있어요.';
    const button = document.createElement('button'); button.className = 'btn btn-primary'; button.textContent = '게임하러 가기'; button.onclick = () => router.navigate('home');
    card.append(title, text, button); container.appendChild(card);
  },

  renderSelection(container, router, renderToken = this.renderToken) {
    const drawState = router.state?.draw || {};
    container.innerHTML = `
      <section class="card pouch-selection-container">
        <span class="sticker-badge badge-yellow">최대 10회</span>
        <h2>복주머니 하나를 골라주세요</h2>
        <p class="draw-round-progress">사용 ${Number(drawState.used_count || 0)}/${Number(drawState.max_count || 10)}회 · 남은 뽑기권 ${Number(drawState.available_credits || 0)}장</p>
        <p class="pouch-selection-description">하나를 고르면 결과가 정해져요.<br>정해진 결과는 새로고침해도 같아요.</p>
        <div class="pouch-grid">
          <button class="pouch-item wiggle" data-index="0"><span class="pouch-icon">🧧</span><span class="pouch-label">1번</span></button>
          <button class="pouch-item wiggle" data-index="1"><span class="pouch-icon">🧧</span><span class="pouch-label">2번</span></button>
          <button class="pouch-item wiggle" data-index="2"><span class="pouch-icon">🧧</span><span class="pouch-label">3번</span></button>
        </div>
        <button id="btn-open-pouch" class="btn btn-primary" disabled>선택한 주머니 열기</button>
      </section>`;
    const open = container.querySelector('#btn-open-pouch');
    const pouches = [...container.querySelectorAll('.pouch-item')];
    const expectedRound = Number(drawState.used_count || 0) + 1;
    let pending = pendingDrawGet();
    if (pending && pending.expected_round_number !== expectedRound) {
      pendingDrawClear();
      pending = null;
    }
    const lockPouchChoice = (pouchIndex) => {
      this.selectedPouch = pouchIndex;
      pouches.forEach((item) => {
        item.classList.toggle('selected', Number(item.dataset.index) === pouchIndex);
        item.disabled = true;
      });
      open.disabled = false;
    };
    if (pending) {
      lockPouchChoice(pending.pouch_index);
      open.textContent = '결과 다시 확인';
    } else {
      pouches.forEach((pouch) => {
        pouch.onclick = () => {
          pouches.forEach((item) => item.classList.toggle('selected', item === pouch));
          this.selectedPouch = Number(pouch.dataset.index);
          open.disabled = false;
          analytics.track('pouch_selected', { action: `pouch_${this.selectedPouch}` });
        };
      });
    }
    open.onclick = async () => {
      const requestToken = renderToken;
      let request = pendingDrawGet();
      if (request && request.expected_round_number !== expectedRound) {
        pendingDrawClear();
        request = null;
      }
      if (request) {
        try {
          const current = await api.getDraw();
          if (!router.isCurrent(requestToken)) return;
          if (pendingDrawCommitted(current, request)) {
            pendingDrawClear();
            return this.renderResolvedState(container, router, requestToken, current);
          }
        } catch (_) { /* Retrying the same idempotency key remains safe. */ }
      }
      if (!request) {
        const eventId = api.createRequestId?.('draw') || `draw_${Date.now()}_${Math.random().toString(36).slice(2)}`;
        request = { event_id: eventId, pouch_index: this.selectedPouch, expected_round_number: expectedRound };
        pendingDrawSet(request);
        lockPouchChoice(request.pouch_index);
      }
      open.disabled = true;
      open.textContent = '결과 확정 중...';
      try {
        const response = await api.drawPouch(request.pouch_index, request.event_id, request.expected_round_number);
        const draw = response.draw || response;
        pendingDrawClear();
        router.announceStateChange();
        if (router.isCurrent(requestToken)) {
          const nextState = response.draw_state || { status: draw.is_actual_prize || draw.is_won ? 'WON' : 'DRAWN', draw_id: draw.draw_id };
          this.renderResolvedState(container, router, requestToken, { ...nextState, draw_id: draw.draw_id, draw });
        } else {
          await router.refreshState({ quiet: true });
        }
      } catch (error) {
        if (!router.isCurrent(requestToken)) return;
        try {
          const current = await api.getDraw();
          if (!router.isCurrent(requestToken)) return;
          if (pendingDrawCommitted(current, request)) {
            pendingDrawClear();
            return this.renderResolvedState(container, router, requestToken, current);
          }
        } catch (_) { /* The durable key is retained for the next retry. */ }
        open.disabled = false;
        open.textContent = '결과 다시 확인';
        ui.showToast(error.message);
      }
    };
  },

  renderScratch(container, router, draw, renderToken = this.renderToken, drawState = router.state?.draw || {}) {
    this.cleanup();
    container.innerHTML = `
      <section class="card scratch-stage-container">
        <span class="sticker-badge badge-blue">${Number(draw.round_number || drawState.used_count || 1)}/${Number(drawState.max_count || 10)}회 결과</span>
        <h2 id="scratch-title">복권을 긁어 결과를 확인하세요</h2>
        <div class="scratch-ticket">
          <div class="ticket-header"><span>Team Gemini Lucky Ticket</span><span>최대 10회</span></div>
          <div class="ticket-scratch-area">
            <div class="ticket-result-underlay" id="scratch-result-content" aria-hidden="true" inert><img id="result-prize-img" src="/assets/icons/Smile-Light.png" alt=""><div id="result-prize-title" class="result-title"></div><div id="result-prize-sub" class="result-sub"></div></div>
            <canvas id="scratch-canvas" tabindex="0" role="button" aria-label="복권 긁기. Enter 또는 Space 키로 같은 결과를 바로 확인할 수 있습니다." aria-describedby="scratch-instruction"></canvas>
          </div>
        </div>
        <p id="scratch-instruction" class="scratch-hint-text">화면을 긁거나 아래 버튼으로 같은 서버 확정 결과를 확인하세요.</p>
        <button id="btn-instant-reveal" class="btn btn-secondary btn-sm">긁기 어려우면 결과 확인</button>
        <p id="restored-pouch" class="status-note"></p>
        <p id="scratch-save-status" class="status-note" role="status"></p>
        <div id="post-reveal-actions" class="post-reveal-actions" hidden>
          <button id="btn-after-draw" class="btn btn-primary"></button>
          <button id="btn-draw-share" class="btn btn-share-retry" type="button" hidden></button>
          <p id="draw-share-status" class="status-note" role="status"></p>
        </div>
      </section>`;
    const prize = draw.prize || {};
    const resultContent = container.querySelector('#scratch-result-content');
    resultContent.setAttribute('aria-hidden', 'true');
    resultContent.inert = true;
    const scratchCanvas = container.querySelector('#scratch-canvas');
    scratchCanvas.tabIndex = 0;
    const img = container.querySelector('#result-prize-img');
    const actualPrize = draw.is_actual_prize === true || draw.outcome_kind === 'PRIZE' || draw.is_won === true;
    img.src = prize.image_url || (actualPrize ? '/assets/icons/Heart-Dark.png' : '/assets/icons/Rocket-Dark.png');
    img.alt = actualPrize ? '당첨 경품' : 'Gemini 1년 무료 혜택';
    ui.text(container.querySelector('#result-prize-title'), actualPrize ? prize.name : '축하드려요!');
    ui.text(container.querySelector('#result-prize-sub'), actualPrize ? '운영자가 정보를 확인하고 직접 연락해 지급합니다.' : 'Gemini 1년 무료 당첨');
    if (Number.isInteger(draw.pouch_index)) ui.text(container.querySelector('#restored-pouch'), `${draw.pouch_index + 1}번 주머니에서 정해진 결과예요. 새로고침해도 같아요.`);
    const after = container.querySelector('#btn-after-draw');
    after.textContent = actualPrize ? '수령함에서 확인하기' : '혜택 적용하기';
    after.onclick = () => router.navigate(actualPrize ? 'claims' : 'benefit');
    this.activeDrawContext = { container, router, renderToken, draw, drawState, actualPrize, resultRevealed: false };
    const preparePostActions = () => {
      const context = this.activeDrawContext;
      if (!context || context.renderToken !== renderToken || !context.resultRevealed || context.draw.scratch_completed !== true) return;
      void this.preparePostDrawShare(container, router, renderToken, draw, context.drawState, actualPrize);
    };
    const showResult = () => {
      if (!router.isCurrent(renderToken)) return;
      ui.text(container.querySelector('#scratch-title'), '복주머니 결과를 확인하세요');
      const instruction = container.querySelector('#scratch-instruction');
      ui.text(instruction, '');
      instruction.hidden = true;
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
        analytics.track('draw_result_viewed', { result_type: actualPrize ? 'prize' : 'benefit', round_number: Number(draw.round_number || 1) });
      }
      if (this.activeDrawContext?.renderToken === renderToken) this.activeDrawContext.resultRevealed = true;
      router.announceStateChange();
    };
    const persistReveal = async () => {
      const requestToken = renderToken;
      if (!router.isCurrent(requestToken)) return;
      showResult();
      if (draw.scratch_completed) { preparePostActions(); return; }
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
        analytics.track('scratch_completed', { result_type: actualPrize ? 'prize' : 'benefit', prize_kind: prize.category || 'NONE', round_number: Number(draw.round_number || 1) });
        preparePostActions();
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
      if (draw.scratch_completed) preparePostActions();
    }
  },

  async preparePostDrawShare(container, router, renderToken, draw, drawState, actualPrize) {
    const button = container.querySelector('#btn-draw-share');
    const status = container.querySelector('#draw-share-status');
    if (!button || !status) return;
    const used = Number(drawState.used_count ?? draw.round_number ?? 1);
    const max = Number(drawState.max_count || 10);
    const availableCredits = Number(drawState.available_credits || 0);
    const actionKey = actualPrize ? 'prize' : availableCredits > 0 ? `direct:${availableCredits}` : used >= max ? `exhausted:${max}` : `share:${used}:${max}`;
    const context = this.activeDrawContext?.renderToken === renderToken ? this.activeDrawContext : null;
    if (context?.actionKey === actionKey || context?.preparingActionKey === actionKey) return;
    if (context) context.preparingActionKey = actionKey;
    const actionVersion = ++this.postActionVersion;
    const isCurrent = () => (!router.isCurrent || router.isCurrent(renderToken)) && actionVersion === this.postActionVersion;
    if (!actualPrize && availableCredits > 0) {
      button.hidden = false;
      button.disabled = false;
      button.textContent = '한 번 더 뽑기';
      ui.text(status, `사용 가능한 복주머니가 ${availableCredits}개 있어요.`);
      button.onclick = () => {
        if (!isCurrent()) return;
        router.state.draw = { ...drawState };
        router.navigate('draw');
      };
      if (context) { context.actionKey = actionKey; context.preparingActionKey = null; }
      return;
    }
    if (!actualPrize && used >= max) {
      ui.text(status, `${max}회 복주머니를 모두 확인했어요.`);
      if (context) { context.actionKey = actionKey; context.preparingActionKey = null; }
      return;
    }
    button.hidden = false;
    button.disabled = true;
    button.textContent = actualPrize ? '카카오톡으로 당첨 자랑하기' : '카카오톡으로 공유하고 한 번 더 뽑기';
    try {
      const prepared = await prepareResultReferralShare(router, {
        kind: actualPrize ? 'prize_share' : 'draw_retry',
        info: actualPrize ? { won_prize_name: prizeName(draw) } : {},
        onReceipt: (receipt) => {
          if (!isCurrent() || actualPrize || receipt?.reward_type !== 'DRAW') return;
          if (receipt.draw_state) {
            router.state.draw = receipt.draw_state;
            if (this.activeDrawContext?.renderToken === renderToken) this.activeDrawContext.drawState = receipt.draw_state;
          }
          if (receipt.status === 'confirmed' && receipt.reward_status === 'granted') {
            void this.updateState(container, router, renderToken);
          } else if (receipt.status !== 'pending') ui.text(status, '추가 뽑기권을 받을 수 없는 상태예요.');
        },
      });
      if (!isCurrent()) return;
      if (context) { context.actionKey = actionKey; context.preparingActionKey = null; }
      button.disabled = false;
      button.onclick = async () => {
        if (button.disabled || !isCurrent()) return;
        button.disabled = true;
        try {
          const outcome = await prepared.share();
          if (!isCurrent()) return;
          if (outcome?.status === 'pending') ui.text(status, actualPrize ? '카카오톡 공유창을 열었어요.' : '전송 확인 후 새 복주머니가 열려요.');
          else if (outcome?.status === 'failed') ui.text(status, '공유를 열지 못했어요. 다시 시도해 주세요.');
        } finally { if (isCurrent()) button.disabled = false; }
      };
    } catch (_) {
      if (context) context.preparingActionKey = null;
      if (!isCurrent()) return;
      button.disabled = false;
      ui.text(status, '공유를 준비하지 못했어요. 버튼을 눌러 다시 시도해 주세요.');
      button.onclick = () => this.preparePostDrawShare(container, router, renderToken, draw, drawState, actualPrize);
    }
  },

  async updateState(container, router, renderToken) {
    const context = this.activeDrawContext;
    if (!context || context.container !== container || context.renderToken !== renderToken || !router.isCurrent(renderToken)) return;
    context.drawState = { ...context.drawState, ...(router.state?.draw || {}) };
    if (!context.resultRevealed || context.draw.scratch_completed !== true) return;
    await this.preparePostDrawShare(container, router, renderToken, context.draw, context.drawState, context.actualPrize);
  },

  renderError(container, router, error) {
    container.replaceChildren();
    const card = document.createElement('section'); card.className = 'card empty-state';
    const p = document.createElement('p'); p.textContent = error.message || '복주머니 상태를 불러오지 못했습니다.';
    const retry = document.createElement('button'); retry.className = 'btn btn-primary'; retry.textContent = '다시 시도'; retry.onclick = () => router.navigate('draw');
    card.append(p, retry); container.appendChild(card);
  },
  cleanup() {
    this.scratchCard?.destroy?.();
    this.scratchCard = null;
    this.selectedPouch = null;
    this.resultViewed = false;
    this.activeDrawContext = null;
    this.postActionVersion += 1;
  },
};

function prizeName(draw) {
  return String(draw?.prize?.name || '상품').trim() || '상품';
}
