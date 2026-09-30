import { benefitRetryAvailability, benefitRewardMessage } from '../benefit_retry.js';
import { showGameGuide } from '../components/game_guide.js';
import { ResultView } from './result_view.js';
import { PrizeView } from './prize_view.js';
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
const campaignStatus = (router) => router.campaignStatus?.() || router.config?.campaign?.status || 'ACTIVE';

export const DrawView = {
  scratchCard: null,
  selectedPouch: null,
  renderToken: 0,
  resultViewed: false,
  activeDrawContext: null,
  activeSelectionContext: null,
  dockContext: null,
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
      this.renderScratch(container, router, state.draw, renderToken, state);
    } else {
      this.renderSelection(container, router, renderToken);
    }
    Promise.resolve().then(() => {
      // A confirmed physical prize owns the first modal. TOP3 remains available
      // from the compact request card after the prize contact flow is closed.
      if (router.isCurrent(renderToken) && typeof ResultView !== 'undefined' && !isActualPrizeDraw(state.draw)) ResultView.openTop3Modal(router, renderToken);
    });
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
    const selectionTitle = Number(drawState.used_count || 0) === 0 ? '이번 판 경품도 받아가세요' : '경품을 한 번 더 뽑아보세요';
    container.innerHTML = `
      <div id="draw-game-summary" class="draw-game-summary" hidden></div>
      <section class="card pouch-selection-container">
        <span class="sticker-badge badge-yellow">최대 10회</span>
        <h2>${selectionTitle}</h2>
        <p class="draw-round-progress">사용 ${Number(drawState.used_count || 0)}/${Number(drawState.max_count || 10)}회 · 남은 뽑기권 ${Number(drawState.available_credits || 0)}장</p>
        <p class="pouch-selection-description">하나를 고르면 결과가 정해져요.<br>정해진 결과는 새로고침해도 같아요.</p>
        <div class="pouch-grid">
          <button class="pouch-item wiggle" data-index="0"><span class="pouch-icon">🧧</span><span class="pouch-label">1번</span></button>
          <button class="pouch-item wiggle" data-index="1"><span class="pouch-icon">🧧</span><span class="pouch-label">2번</span></button>
          <button class="pouch-item wiggle" data-index="2"><span class="pouch-icon">🧧</span><span class="pouch-label">3번</span></button>
        </div>
        <button id="btn-open-pouch" class="btn btn-primary" disabled>선택한 주머니 열기</button>
      </section>
      ${this.dockMarkup()}`;
    const open = container.querySelector('#btn-open-pouch');
    const pouches = [...container.querySelectorAll('.pouch-item')];
    const description = container.querySelector('.pouch-selection-description');
    this.activeSelectionContext = { container, router, renderToken, open, pouches, description };
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
          if (campaignStatus(router) !== 'ACTIVE') return;
          pouches.forEach((item) => item.classList.toggle('selected', item === pouch));
          this.selectedPouch = Number(pouch.dataset.index);
          open.disabled = false;
          analytics.track('pouch_selected', { action: `pouch_${this.selectedPouch}`, round_number: expectedRound });
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
      if (!request && campaignStatus(router) !== 'ACTIVE') {
        this.updateSelectionCampaignState(container, router, renderToken);
        return;
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
    this.renderGameSummary(container, router);
    this.updateActionDock(container, router, renderToken);
    this.updateSelectionCampaignState(container, router, renderToken);
  },

  updateSelectionCampaignState(container, router, renderToken) {
    const context = this.activeSelectionContext;
    if (!context || context.container !== container || context.renderToken !== renderToken) return;
    const pending = pendingDrawGet();
    const blocked = campaignStatus(router) !== 'ACTIVE' && !pending;
    if (blocked) {
      context.pouches.forEach((pouch) => { pouch.disabled = true; });
      context.open.disabled = true;
      if (context.description) context.description.textContent = campaignStatus(router) === 'NOT_OPEN'
        ? '행사 시작 후 새 복주머니를 열 수 있어요.'
        : campaignStatus(router) === 'ENDED' ? '행사가 종료되어 새 복주머니를 열 수 없어요.' : '행사가 잠시 중단되어 새 복주머니를 열 수 없어요.';
      return;
    }
    if (!pending) {
      context.pouches.forEach((pouch) => { pouch.disabled = false; });
      context.open.disabled = this.selectedPouch == null;
      if (context.description) context.description.innerHTML = '하나를 고르면 결과가 정해져요.<br>정해진 결과는 새로고침해도 같아요.';
    }
    this.updateActionDock(container, router, renderToken);
  },

  renderScratch(container, router, draw, renderToken = this.renderToken, drawState = router.state?.draw || {}) {
    this.cleanup();
    container.innerHTML = `
      <div id="draw-game-summary" class="draw-game-summary" hidden></div>
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
          <button id="btn-draw-again" class="btn btn-prize-draw" type="button" hidden>🧧 한 번 더 뽑기</button>
          <button id="btn-draw-game" class="btn btn-secondary" type="button" hidden>게임 다시 하기</button>
          <button id="btn-draw-share" class="btn btn-share-retry" type="button" hidden></button>
          <p id="draw-share-status" class="status-note" role="status"></p>
          <p id="draw-top3-note" class="result-gap" hidden></p>
          <div id="draw-top3-request"></div>
        </div>
      </section>
      ${this.dockMarkup()}`;
    this.renderGameSummary(container, router);
    this.updateActionDock(container, router, renderToken);
    const prize = draw.prize || {};
    const resultContent = container.querySelector('#scratch-result-content');
    resultContent.setAttribute('aria-hidden', 'true');
    resultContent.inert = true;
    const scratchCanvas = container.querySelector('#scratch-canvas');
    scratchCanvas.tabIndex = 0;
    const img = container.querySelector('#result-prize-img');
    const actualPrize = draw.is_actual_prize === true || draw.outcome_kind === 'PRIZE' || draw.is_won === true;
    container.querySelector('.scratch-stage-container')?.classList.toggle('actual-prize-result', actualPrize);
    img.src = prize.image_url || (actualPrize ? '/assets/icons/Heart-Dark.png' : '/assets/icons/Rocket-Dark.png');
    img.alt = actualPrize ? '당첨 경품' : 'Gemini 1년 무료 혜택';
    ui.text(container.querySelector('#result-prize-title'), actualPrize ? prize.name : '축하드려요!');
    ui.text(container.querySelector('#result-prize-sub'), actualPrize ? '운영자가 정보를 확인하고 직접 연락해 지급합니다.' : 'Gemini 1년 무료 당첨');
    if (Number.isInteger(draw.pouch_index)) ui.text(container.querySelector('#restored-pouch'), `${draw.pouch_index + 1}번 주머니에서 정해진 결과예요. 새로고침해도 같아요.`);
    const after = container.querySelector('#btn-after-draw');
    after.textContent = actualPrize ? '수령 정보 입력' : '혜택 적용하기';
    after.disabled = actualPrize && !draw.scratch_completed;
    after.onclick = () => {
      if (after.disabled) return;
      return actualPrize ? this.maybeOpenActualPrizeClaim(container, router, renderToken, draw, { force: true }) : router.navigate('benefit');
    };
    this.activeDrawContext = { container, router, renderToken, draw, drawState, actualPrize, resultRevealed: false };
    const preparePostActions = () => {
      const context = this.activeDrawContext;
      if (!context || context.renderToken !== renderToken || !context.resultRevealed || context.draw.scratch_completed !== true) return;
      if (actualPrize) void this.maybeOpenActualPrizeClaim(container, router, renderToken, draw);
      void this.preparePostDrawShare(container, router, renderToken, draw, context.drawState, actualPrize, { prepareShare: actualPrize });
      void this.updateActionDock(container, router, renderToken);
    };
    const showResult = () => {
      if (!router.isCurrent(renderToken)) return;
      ui.text(container.querySelector('#scratch-title'), actualPrize ? '경품 당첨을 축하드려요!' : 'Gemini 혜택을 받았어요!');
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
        analytics.track('draw_result_viewed', { result_type: actualPrize ? 'prize' : 'benefit', round_number: Number(draw.round_number || 1) }, { dedupKey: `draw-result:${draw.draw_id}` });
      }
      if (this.activeDrawContext?.renderToken === renderToken) this.activeDrawContext.resultRevealed = true;
      this.renderTop3Result(container, router);
      this.updateActionDock(container, router, renderToken);
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
        const completed = await api.completeScratch(draw.draw_id, eventId);
        if (!router.isCurrent(requestToken)) return;
        draw.scratch_completed = true;
        if (completed?.claim_id) draw.claim_id = completed.claim_id;
        after.disabled = false;
        storageRemove(storageKey);
        status.textContent = '결과 확인이 저장됐습니다.';
        analytics.track('scratch_completed', { result_type: actualPrize ? 'prize' : 'benefit', prize_kind: prize.category || 'NONE', round_number: Number(draw.round_number || 1) }, { dedupKey: `scratch:${draw.draw_id}` });
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
      onStart: () => analytics.track('scratch_started', { round_number: Number(draw.round_number || 1) }),
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

  renderGameSummary(container, router) {
    const summary = container.querySelector('#draw-game-summary');
    const result = router.state?.lastResult;
    if (!summary || !result) return;
    summary.hidden = false;
    summary.replaceChildren();
    const line = document.createElement('div'); line.className = 'draw-score-line';
    const score = document.createElement('strong'); score.textContent = `${Number(result.score || 0).toLocaleString('ko-KR')}점`;
    const rank = document.createElement('span'); rank.className = 'draw-rank-pill'; rank.textContent = result.rank ? `현재 ${result.rank}위` : '순위 집계 중';
    line.append(score, rank); summary.appendChild(line);
    const target = document.createElement('p'); target.className = 'draw-rank-target'; target.textContent = ResultView.top3GapMessage(result);
    summary.appendChild(target);
  },

  renderTop3Result(container, router) {
    const target = container.querySelector('#draw-top3-request');
    if (!target) return;
    const profile = router.state.top3Profile || router.state.lastResult?.top3Profile;
    ResultView.renderTop3Request(target, router, profile);
    const note = container.querySelector('#draw-top3-note');
    if (note) {
      note.hidden = target.hidden;
      if (!target.hidden) note.textContent = ResultView.top3GapMessage(router.state.lastResult || {});
    }
  },

  async maybeOpenActualPrizeClaim(container, router, renderToken, draw, { force = false } = {}) {
    if (!router.isCurrent(renderToken) || !draw?.scratch_completed) return false;
    let claim = draw.claim_id ? {
      id: draw.claim_id,
      claim_type: 'DRAW',
      prize_name: prizeName(draw),
      category: draw.prize?.category || draw.category,
      status: 'AWAITING_INFORMATION',
      contact_submitted: false,
    } : null;
    try {
      const response = await api.getClaims();
      if (!router.isCurrent(renderToken)) return false;
      const claims = response?.claims || [];
      claim = draw.claim_id
        ? claims.find((item) => item.id === draw.claim_id) || claim
        : claims.find((item) => (item.claim_type || item.type) === 'DRAW' && Boolean(item.draw_id) && item.draw_id === draw.draw_id && !item.contact_submitted) || null;
    } catch (_) { /* A claim id returned with the draw is enough to keep the immediate flow usable. */ }
    if (!claim?.id) {
      ui.showToast('수령 정보 준비가 덜 끝났어요. 수령함에서 다시 시도해 주세요.');
      return false;
    }
    if (claim.contact_submitted || ['INFORMATION_RECEIVED', 'PENDING_REVIEW', 'CONTACTED', 'PAID'].includes(claim.status)) {
      const after = container.querySelector?.('#btn-after-draw');
      if (after) {
        after.textContent = '혜택 보러 가기';
        after.onclick = () => router.navigate('benefit');
      }
      if (force) router.navigate('benefit');
      return true;
    }
    const options = { onSubmitted: () => router.navigate('benefit') };
    return force
      ? PrizeView.directClaimModal(claim, router, renderToken, options)
      : PrizeView.openImmediateClaim(claim, router, renderToken, options);
  },

  dockMarkup() {
    return `<aside class="draw-action-dock" aria-label="게임 재도전">
      <button id="draw-dock-primary" class="btn btn-secondary" type="button" disabled>재도전 준비 중</button>
      <button id="draw-dock-secondary" class="draw-dock-secondary" type="button" hidden></button>
      <p id="draw-dock-status" class="status-note" role="status"></p>
    </aside>`;
  },

  async updateActionDock(container, router, renderToken) {
    const primary = container.querySelector('#draw-dock-primary');
    const secondary = container.querySelector('#draw-dock-secondary');
    const status = container.querySelector('#draw-dock-status');
    if (!primary || !secondary || !status || !router.isCurrent(renderToken)) return;
    const drawState = router.state?.draw || {};
    const tickets = router.state?.tickets || {};
    const active = campaignStatus(router) === 'ACTIVE';
    const context = this.activeDrawContext?.renderToken === renderToken ? this.activeDrawContext : null;
    const benefitResult = Boolean(context && !context.actualPrize && context.resultRevealed && context.draw?.scratch_completed === true);
    const availability = benefitRetryAvailability(drawState, tickets, campaignStatus(router));
    const cooldown = Date.parse(tickets.cooldown_until || '') > Date.now();
    const capped = Number(tickets.invitation || 0) + Number(tickets.invitation_reserved || 0) >= 3;
    const gameReady = tickets.unlimited_play === true || Number(tickets.available_total ?? (Number(tickets.initial || 0) + Number(tickets.invitation || 0))) > 0;
    const gameGrant = active && !cooldown && !capped;
    const drawGrant = benefitResult && availability.drawGrant;
    const sharePossible = gameGrant || drawGrant;
    const kind = benefitResult ? 'benefit_retry' : 'retry_invite';
    const key = JSON.stringify([kind, context?.draw?.draw_id || 'before-draw', gameGrant, drawGrant]);

    primary.textContent = gameReady ? '한 판 더 하기' : sharePossible ? '친구에게 공유하고\n다시 도전하기' : active ? '게임권 적립 대기 중' : '행사가 종료됐어요';
    primary.className = `btn ${gameReady ? 'btn-primary' : sharePossible ? 'btn-share-retry' : 'btn-secondary'}`;
    secondary.hidden = !gameReady || !sharePossible;
    secondary.textContent = drawGrant && gameGrant ? '공유하고 게임권 + 뽑기권 받기' : gameGrant ? '공유하고 게임권 더 받기' : '공유하고 경품 한 번 더 뽑기';
    ui.text(status, !active
      ? '새 게임과 추가 적립이 종료됐어요.'
      : drawGrant && gameGrant ? '카카오톡 전송 확인 시 게임권 1장 + 경품 뽑기 1회'
      : drawGrant ? '경품 뽑기 1회 지급 · 게임권은 적립 대기 중'
      : gameGrant ? '카카오톡 전송 확인 시 게임권 1장'
      : gameReady ? '보유 중인 게임권으로 바로 도전할 수 있어요.' : availability.message);

    const mounted = () => router.isCurrent(renderToken) && container.querySelector('#draw-dock-primary') === primary;
    const runGame = () => { if (mounted() && active && gameReady) showGameGuide(router, true); };
    const current = this.dockContext;
    if (current?.failed && current.key === key) {
      if (gameReady) secondary.textContent = '공유 다시 준비하기';
      else primary.textContent = '공유 다시 준비하기';
      ui.text(status, '공유 준비를 불러오지 못했어요. 버튼을 눌러 다시 시도해 주세요.');
    }
    primary.onclick = gameReady ? runGame : () => current?.key === key && current.share?.();
    secondary.onclick = () => current?.key === key && current.share?.();
    primary.disabled = !gameReady && (!sharePossible || current?.key !== key || current.busy);
    secondary.disabled = current?.key !== key || current.busy;
    if (!sharePossible || current?.key === key || current?.preparingKey === key) return;

    const dock = { key: '', preparingKey: key, share: null, busy: false, failed: false };
    this.dockContext = dock;
    try {
      const prepared = await prepareResultReferralShare(router, {
        kind,
        onReceipt: (receipt) => {
          if (!mounted()) return;
          if (receipt?.tickets) router.state.tickets = receipt.tickets;
          if (receipt?.draw_state) router.state.draw = receipt.draw_state;
          ui.text(status, benefitRewardMessage(receipt));
          dock.busy = false;
          dock.key = '';
          void this.updateActionDock(container, router, renderToken);
        },
      });
      if (!mounted() || this.dockContext !== dock) return;
      dock.key = key;
      dock.preparingKey = '';
      dock.share = async () => {
        if (dock.busy || !mounted()) return;
        dock.busy = true;
        primary.disabled = true;
        secondary.disabled = true;
        try {
          const outcome = await prepared.share();
          if (mounted() && outcome?.status === 'pending') ui.text(status, '전송 확인 중이에요. 확인되면 보상이 지급돼요.');
        } finally {
          dock.busy = false;
          if (mounted()) void this.updateActionDock(container, router, renderToken);
        }
      };
      this.updateActionDock(container, router, renderToken);
    } catch (_) {
      if (!mounted() || this.dockContext !== dock) return;
      dock.preparingKey = '';
      dock.key = key;
      dock.failed = true;
      dock.share = () => {
        if (!mounted()) return;
        dock.key = '';
        this.dockContext = null;
        void this.updateActionDock(container, router, renderToken);
      };
      ui.text(status, '공유 준비를 불러오지 못했어요. 잠시 후 다시 시도해 주세요.');
      this.updateActionDock(container, router, renderToken);
    }
  },

  async preparePostDrawShare(container, router, renderToken, draw, drawState, actualPrize, { prepareShare = true } = {}) {
    const button = container.querySelector('#btn-draw-share');
    const status = container.querySelector('#draw-share-status');
    if (!button || !status) return;
    const available = benefitRetryAvailability(drawState, router.state.tickets, campaignStatus(router));
    const isMounted = () => !router.isCurrent || router.isCurrent(renderToken);
    const again = container.querySelector('#btn-draw-again');
    if (again) {
      again.hidden = actualPrize || !available.drawReady;
      again.disabled = !available.active;
      again.onclick = () => { if (isMounted() && !again.disabled && !again.hidden) router.navigate('draw'); };
    }
    const game = container.querySelector('#btn-draw-game');
    if (game) {
      game.hidden = !available.gameReady;
      game.disabled = !available.active;
      game.onclick = () => { if (isMounted() && !game.disabled && !game.hidden) showGameGuide(router, true); };
    }
    if (!prepareShare) return;
    const context = this.activeDrawContext?.renderToken === renderToken ? this.activeDrawContext : null;
    const actionKey = JSON.stringify([actualPrize, available.drawGrant, available.gameGrant, available.active]);
    button.hidden = !actualPrize && !available.drawGrant && !available.gameGrant;
    ui.text(status, context?.receipt ? benefitRewardMessage(context.receipt) : actualPrize ? '' : available.message);
    if (context?.actionKey === actionKey || context?.preparingActionKey === actionKey) return;
    if (context) context.preparingActionKey = actionKey;
    const actionVersion = ++this.postActionVersion;
    const isCurrent = () => isMounted() && actionVersion === this.postActionVersion;
    button.disabled = true;
    button.textContent = actualPrize ? '카카오톡으로 당첨 자랑하기' : '친구에게 공유하고\n다시 도전하기';
    if (button.hidden) {
      if (context) { context.actionKey = actionKey; context.preparingActionKey = null; }
      return;
    }
    try {
      const prepared = await prepareResultReferralShare(router, {
        kind: actualPrize ? 'prize_share' : 'benefit_retry',
        info: actualPrize ? { won_prize_name: prizeName(draw) } : {},
        onReceipt: (receipt) => {
          // A balance refresh may replace the prepared action while Kakao is open.
          if (!isMounted() || actualPrize || !['BOTH', 'DRAW'].includes(receipt?.reward_type)) return;
          if (receipt.tickets) router.state.tickets = receipt.tickets;
          if (receipt.draw_state) router.state.draw = receipt.draw_state;
          if (context && this.activeDrawContext === context) {
            context.drawState = { ...context.drawState, ...(receipt.draw_state || {}) };
            context.receipt = receipt;
          }
          if (receipt.status !== 'pending') {
            void this.preparePostDrawShare(container, router, renderToken, draw, router.state.draw || drawState, actualPrize);
            ui.text(status, benefitRewardMessage(receipt));
          }
        },
      });
      if (!isCurrent()) return;
      if (context) { context.actionKey = actionKey; context.preparingActionKey = null; }
      button.disabled = !actualPrize && campaignStatus(router) !== 'ACTIVE';
      button.onclick = async () => {
        if (button.disabled || !isCurrent() || (!actualPrize && campaignStatus(router) !== 'ACTIVE')) return;
        button.disabled = true;
        if (context) context.receipt = null;
        try {
          const outcome = await prepared.share();
          if (!isCurrent()) return;
          if (outcome?.status === 'pending' && !context?.receipt) ui.text(status, actualPrize ? '카카오톡 공유창을 열었어요.' : '전송 확인 중이에요. 확인되면 받을 수 있는 재도전권이 적립돼요.');
          else if (outcome?.status === 'failed') ui.text(status, '공유를 열지 못했어요. 다시 시도해 주세요.');
        } finally { if (isCurrent()) button.disabled = !actualPrize && campaignStatus(router) !== 'ACTIVE'; }
      };
    } catch (_) {
      if (context) context.preparingActionKey = null;
      if (!isCurrent()) return;
      button.disabled = !actualPrize && campaignStatus(router) !== 'ACTIVE';
      ui.text(status, '공유를 준비하지 못했어요. 버튼을 눌러 다시 시도해 주세요.');
      button.onclick = () => this.preparePostDrawShare(container, router, renderToken, draw, drawState, actualPrize);
    }
  },

  async updateState(container, router, renderToken) {
    if (this.activeSelectionContext?.container === container && this.activeSelectionContext?.renderToken === renderToken) {
      this.updateSelectionCampaignState(container, router, renderToken);
      await this.updateActionDock(container, router, renderToken);
      return;
    }
    const context = this.activeDrawContext;
    if (!context || context.container !== container || context.renderToken !== renderToken || !router.isCurrent(renderToken)) return;
    context.drawState = { ...context.drawState, ...(router.state?.draw || {}) };
    this.renderGameSummary(container, router);
    await this.updateActionDock(container, router, renderToken);
    if (!context.resultRevealed || context.draw.scratch_completed !== true) return;
    this.renderTop3Result(container, router);
    await this.preparePostDrawShare(container, router, renderToken, context.draw, context.drawState, context.actualPrize, { prepareShare: context.actualPrize });
    await this.updateActionDock(container, router, renderToken);
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
    this.activeSelectionContext = null;
    this.dockContext = null;
    this.postActionVersion += 1;
  },
};

function prizeName(draw) {
  return String(draw?.prize?.name || '상품').trim() || '상품';
}

function isActualPrizeDraw(draw) {
  return draw?.is_actual_prize === true || draw?.outcome_kind === 'PRIZE' || draw?.is_won === true;
}
