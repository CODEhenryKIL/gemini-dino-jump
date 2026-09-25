import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { audio } from '../game/audio.js';
import { DinoGameEngine } from '../game/engine.js';

const PENDING_RESULT_KEY = 'dino_pending_result';
const CHECKPOINT_PREFIX = 'dino_checkpoint_';
const FAULT_PREFIX = 'dino_fault_';
function storageGet(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }
function storageSet(key, value) { try { sessionStorage.setItem(key, value); return true; } catch (_) { return false; } }
function storageRemove(key) { try { sessionStorage.removeItem(key); } catch (_) {} }

export const GameView = {
  engine: null,
  sessionId: null,
  cleanupTasks: [],
  countdownTimer: null,
  completing: false,
  normalEnd: false,
  currentStage: 'stage_1',

  async render(container, router, renderToken) {
    this.resetRuntime();
    container.innerHTML = `
      <section class="game-screen-wrapper">
        <div class="game-center-section">
          <div class="game-viewport-container">
            <canvas id="game-canvas"></canvas>
            <div class="game-hud">
              <span id="hud-stage-badge" class="stage-tag">STAGE 1</span>
              <div class="hud-right"><strong id="hud-current-score" class="current-score">0</strong><button id="btn-toggle-sound" class="sound-toggle-btn" aria-label="소리 켜기 또는 끄기">🔊</button></div>
            </div>
            <div id="stage-flash-badge"><div class="stage-name">STAGE 1</div><div class="stage-sub">가볍게 시작!</div></div>
            <div id="countdown-overlay" class="countdown-overlay active"><div id="countdown-num" class="countdown-number">3</div><div>탭하여 점프하세요!</div></div>
          </div>
          <div class="jump-hint-box">탭: 낮게 점프 · 꾹 누르기: 높게 점프 · 높은 새: 점프 금지</div>
        </div>
        <div class="jump-bottom-dock"><button id="btn-jump" class="big-jump-btn">🚀 점프</button></div>
      </section>`;
    try {
      const recovered = await this.recoverPendingResult(router, renderToken);
      if (recovered || !router.isCurrent(renderToken)) return;
      if (router.state.pendingGameSession) {
        this.renderInterruptedSession(container, router, router.state.pendingGameSession);
        return;
      }
      if (!router.isCurrent(renderToken)) return;
      await this.startNewSession(container, router, renderToken);
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      this.renderFailure(container, router, error);
    }
  },

  async recoverPendingResult(router, renderToken) {
    const raw = storageGet(PENDING_RESULT_KEY);
    if (!raw) return false;
    let pending;
    try { pending = JSON.parse(raw); } catch (_) { storageRemove(PENDING_RESULT_KEY); return false; }
    if (!pending?.sessionId || !pending?.payload || !pending?.key) { storageRemove(PENDING_RESULT_KEY); return false; }
    try {
      const state = await api.getSession(pending.sessionId);
      if (!router.isCurrent(renderToken)) return true;
      if (state.status === 'FINISHED') {
        storageRemove(PENDING_RESULT_KEY);
        this.acceptResult(state.result || state, router);
        analytics.track('game_recovered', { status: 'FINISHED' }, { gameSessionId: pending.sessionId });
        router.navigate('result');
        return true;
      }
      const result = await api.finishSession(pending.sessionId, pending.payload, pending.key);
      storageRemove(PENDING_RESULT_KEY);
      this.acceptResult(result, router);
      router.navigate('result');
      return true;
    } catch (error) {
      if (error.status && error.status < 500) storageRemove(PENDING_RESULT_KEY);
      throw error;
    }
  },

  renderInterruptedSession(container, router, pending) {
    const id = pending.id || pending.session_id;
    const faultMarker = this.readFaultMarker(id);
    container.replaceChildren();
    const card = document.createElement('section'); card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '완료되지 않은 게임이 있어요';
    const detail = document.createElement('p'); detail.textContent = pending.status === 'FAULT_REPORTED' ? '장애 기록을 확인하고 사용한 게임권을 복구하는 중입니다.' : faultMarker ? '이 브라우저에 저장된 장애 시점과 서버 체크포인트를 확인해 복구를 요청합니다.' : '실제 브라우저 또는 통신 장애로 중단된 경우에만 복구를 요청해 주세요. 정상 종료나 자발적 이탈은 환급 대상이 아닙니다.';
    const check = document.createElement('button'); check.className = 'btn btn-primary'; check.textContent = pending.status === 'FAULT_REPORTED' ? '복구 상태 확인' : faultMarker ? '장애 복구 요청' : '같은 게임 이어하기';
    check.onclick = async () => {
      check.disabled = true;
      try {
        if (pending.status !== 'FAULT_REPORTED' && faultMarker) {
          this.sessionId = id;
          await this.reportFault(faultMarker.reason, faultMarker.tick, faultMarker.key);
          pending.status = 'FAULT_REPORTED';
          router.state.pendingGameSession = { ...pending, status: 'FAULT_REPORTED' };
          detail.textContent = '장애 기록이 접수됐습니다. 서버 확인 뒤 게임권 복구 상태를 확인할 수 있어요.';
          check.textContent = '복구 상태 확인';
          check.disabled = false;
          return;
        }
        if (pending.status !== 'FAULT_REPORTED') {
          router.state.pendingGameSession = null;
          analytics.track('game_recovered', { status: pending.status }, { gameSessionId: id });
          router.navigate('game');
          return;
        }
        const state = await api.getSession(id);
        if (state.status === 'FINISHED') { this.acceptResult(state.result || state, router); router.navigate('result'); return; }
        if (state.status === 'ABORTED') { storageRemove(`${CHECKPOINT_PREFIX}${id}`); storageRemove(`${FAULT_PREFIX}${id}`); await router.refreshState(); analytics.track('game_recovered', { status: 'ABORTED' }, { gameSessionId: id }); router.navigate('home'); return; }
        detail.textContent = '서버가 장애 기록을 확인 중입니다. 잠시 후 다시 확인해 주세요.';
      } catch (error) { ui.showToast(error.message); }
      check.disabled = false;
    };
    const home = document.createElement('button'); home.className = 'btn btn-secondary'; home.textContent = '홈으로'; home.onclick = () => router.navigate('home');
    card.append(title, detail, check, home); container.appendChild(card);
  },

  async startNewSession(container, router, renderToken) {
    const session = await api.createSession();
    if (!router.isCurrent(renderToken)) return;
    this.sessionId = session.session_id;
    storageSet(`${CHECKPOINT_PREFIX}${this.sessionId}`, '0');
    await router.refreshState({ quiet: true });
    this.bindEngine(container, router, renderToken, session.seed);
    await this.runCountdown(container, 3);
    if (!router.isCurrent(renderToken)) return;
    await api.startSession(this.sessionId);
    analytics.track('game_start_approved', { game_version: session.version || '' }, { gameSessionId: this.sessionId });
    analytics.track('game_checkpoint', { stage: 'stage_1', checkpoint: 0 }, { gameSessionId: this.sessionId });
    this.engine.start(session.seed);
    this.checkpointTimer = setInterval(() => this.sendCheckpoint(), 5000);
  },

  async sendCheckpoint() {
    if (!this.sessionId || !this.engine?.isRunning || this.completing) return;
    const tick = Number(this.engine.currentTick || 0);
    if (tick <= 0) return;
    try {
      await api.checkpointSession(this.sessionId, tick, this.currentStage);
      storageSet(`${CHECKPOINT_PREFIX}${this.sessionId}`, String(tick));
      storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
    } catch (error) {
      if (!error.status || error.status >= 500) this.persistFaultMarker('NETWORK_ERROR', tick);
    }
  },

  bindEngine(container, router, renderToken, seed) {
    const canvas = container.querySelector('#game-canvas');
    const stageBadge = container.querySelector('#hud-stage-badge');
    const score = container.querySelector('#hud-current-score');
    const flash = container.querySelector('#stage-flash-badge');
    this.engine = new DinoGameEngine(canvas, {
      onScoreUpdate: (value) => ui.text(score, value),
      onStageChange: (stage) => {
        const stageNumber = Number(String(stage.title || '').match(/\d+/)?.[0] || 1);
        this.currentStage = `stage_${stageNumber}`;
        analytics.track('game_checkpoint', { stage: this.currentStage, checkpoint: Number(this.engine?.currentTick || 0) }, { gameSessionId: this.sessionId });
        ui.text(stageBadge, stage.title);
        ui.text(flash.querySelector('.stage-name'), stage.title);
        ui.text(flash.querySelector('.stage-sub'), stage.sub);
        flash.classList.add('show');
        const timer = setTimeout(() => flash.classList.remove('show'), 1500);
        this.cleanupTasks.push(() => clearTimeout(timer));
      },
      onGameOver: (result) => {
        if (router.isCurrent(renderToken)) this.handleGameOver(result, router, container);
      },
    });
    const press = (event) => { event?.preventDefault?.(); this.engine?.jumpPress(); };
    const release = (event) => { event?.preventDefault?.(); this.engine?.jumpRelease(); };
    for (const element of [canvas, container.querySelector('#btn-jump')]) {
      element.addEventListener('pointerdown', press);
      element.addEventListener('pointerup', release);
      element.addEventListener('pointercancel', release);
      this.cleanupTasks.push(() => { element.removeEventListener('pointerdown', press); element.removeEventListener('pointerup', release); element.removeEventListener('pointercancel', release); });
    }
    const keyDown = (event) => { if ((event.code === 'Space' || event.code === 'ArrowUp') && !event.repeat) press(event); };
    const keyUp = (event) => { if (event.code === 'Space' || event.code === 'ArrowUp') release(event); };
    window.addEventListener('keydown', keyDown);
    window.addEventListener('keyup', keyUp);
    this.cleanupTasks.push(() => { window.removeEventListener('keydown', keyDown); window.removeEventListener('keyup', keyUp); });
    const visibility = () => {
      if (document.hidden) this.engine?.pause();
      else if (this.engine?.isPaused) this.runCountdown(container, 3).then(() => this.engine?.resume());
    };
    document.addEventListener('visibilitychange', visibility);
    this.cleanupTasks.push(() => document.removeEventListener('visibilitychange', visibility));
    container.querySelector('#btn-toggle-sound').onclick = (event) => {
      event.stopPropagation();
      event.currentTarget.textContent = audio.toggleMute() ? '🔇' : '🔊';
    };
    const runtimeError = () => {
      const tick = Number(this.engine?.currentTick || 0);
      this.persistFaultMarker('CLIENT_ERROR', tick);
      this.reportFault('CLIENT_ERROR', tick).catch(() => {});
    };
    window.addEventListener('error', runtimeError, { once: true });
    this.cleanupTasks.push(() => window.removeEventListener('error', runtimeError));
  },

  runCountdown(container, seconds) {
    clearInterval(this.countdownTimer);
    const overlay = container.querySelector('#countdown-overlay');
    const number = container.querySelector('#countdown-num');
    overlay.classList.add('active');
    let remaining = seconds;
    number.textContent = remaining;
    return new Promise((resolve) => {
      this.countdownTimer = setInterval(() => {
        remaining -= 1;
        number.textContent = remaining;
        if (remaining <= 0) {
          clearInterval(this.countdownTimer);
          overlay.classList.remove('active');
          resolve();
        }
      }, 1000);
    });
  },

  async handleGameOver(result, router, container) {
    if (this.completing) return;
    this.completing = true;
    this.normalEnd = true;
    this.stopEngine();
    const key = `finish_${this.sessionId}`;
    const payload = { score: result.score, ticks: result.ticks, jump_ticks: result.jump_ticks, checkpoints: result.checkpoints || [] };
    storageSet(PENDING_RESULT_KEY, JSON.stringify({ sessionId: this.sessionId, payload, key }));
    try {
      const response = await api.finishSession(this.sessionId, payload, key);
      storageRemove(PENDING_RESULT_KEY);
      storageRemove(`${CHECKPOINT_PREFIX}${this.sessionId}`);
      storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
      this.acceptResult(response, router);
      analytics.track('game_completed', { score: response.score, rank: response.rank || 0, status: response.verification }, { gameSessionId: this.sessionId });
      router.announceStateChange();
      router.navigate('result');
    } catch (error) {
      this.renderFinishRetry(container, router, error);
    }
  },

  acceptResult(result, router) {
    router.state.bestScore = result.best_score || router.state.bestScore;
    router.state.rank = result.rank ?? router.state.rank;
    router.state.lastResult = {
      sessionId: result.session_id || this.sessionId,
      score: result.score || 0,
      bestScore: result.best_score || 0,
      rank: result.rank,
      verification: result.verification || 'VERIFIED',
      draw: result.draw || { status: 'AVAILABLE' },
      top3Profile: result.top3_profile || { required: false, status: 'NOT_REQUIRED' },
    };
    router.state.draw = result.draw || router.state.draw;
    router.state.top3Profile = result.top3_profile || router.state.top3Profile;
  },

  renderFinishRetry(container, router, error) {
    container.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card empty-state';
    const title = document.createElement('h2');
    title.textContent = '결과 확인이 아직 끝나지 않았어요';
    const text = document.createElement('p');
    text.textContent = '완료 기록을 이 브라우저에 보관했습니다. 다시 확인하면 서버에 저장된 결과부터 조회합니다.';
    const retry = document.createElement('button');
    retry.className = 'btn btn-primary';
    retry.textContent = '결과 다시 확인';
    retry.onclick = () => router.navigate('game');
    const home = document.createElement('button');
    home.className = 'btn btn-secondary';
    home.textContent = '나중에 확인';
    home.onclick = () => router.navigate('home');
    card.append(title, text, retry, home);
    container.appendChild(card);
    ui.showToast(error.message || '결과 확인에 실패했습니다.');
  },

  readFaultMarker(sessionId) {
    const raw = storageGet(`${FAULT_PREFIX}${sessionId}`);
    if (!raw) return null;
    try {
      const marker = JSON.parse(raw);
      return marker?.sessionId === sessionId && marker?.key && marker?.reason ? marker : null;
    } catch (_) { storageRemove(`${FAULT_PREFIX}${sessionId}`); return null; }
  },

  persistFaultMarker(reason, lastTick = 0) {
    if (!this.sessionId || this.normalEnd) return null;
    const previous = this.readFaultMarker(this.sessionId);
    const marker = {
      sessionId: this.sessionId,
      reason,
      tick: Math.max(Number(previous?.tick || 0), Number(lastTick || 0)),
      key: previous?.key || api.createRequestId('fault'),
    };
    storageSet(`${FAULT_PREFIX}${this.sessionId}`, JSON.stringify(marker));
    return marker;
  },

  async reportFault(reason, lastTick = 0, existingKey = null) {
    if (!this.sessionId || this.normalEnd) return;
    const marker = this.persistFaultMarker(reason, lastTick);
    const key = existingKey || marker?.key || api.createRequestId('fault');
    let tick = Math.max(Number(lastTick || 0), Number(storageGet(`${CHECKPOINT_PREFIX}${this.sessionId}`) || 0));
    try {
      if (tick >= 60) {
        try {
          await api.checkpointSession(this.sessionId, tick, this.currentStage);
          storageSet(`${CHECKPOINT_PREFIX}${this.sessionId}`, String(tick));
        } catch (error) {
          if (error.status === 409) {
            const state = await api.getSession(this.sessionId);
            const accepted = Number(state.last_checkpoint_tick || 0);
            if (accepted < 60) throw error;
            tick = Math.max(tick, accepted);
          } else throw error;
        }
      }
      await api.reportSessionFault(this.sessionId, { reason, last_tick: tick }, key);
      storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
      analytics.track('game_fault_reported', { reason }, { gameSessionId: this.sessionId });
    } catch (error) {
      if (error.status && error.status < 500 && error.status !== 408 && error.status !== 429) storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
      throw error;
    }
  },

  renderFailure(container, router, error) {
    container.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card empty-state';
    const title = document.createElement('h2');
    title.textContent = '게임을 준비하지 못했어요';
    const detail = document.createElement('p');
    detail.textContent = error.message || '연결을 확인한 뒤 다시 시도해 주세요.';
    const retry = document.createElement('button');
    retry.className = 'btn btn-primary';
    retry.textContent = '다시 시도';
    retry.onclick = () => router.navigate('game');
    const home = document.createElement('button');
    home.className = 'btn btn-secondary';
    home.textContent = '홈으로';
    home.onclick = () => router.navigate('home');
    card.append(title, detail, retry, home);
    container.appendChild(card);
  },

  stopEngine() { this.engine?.stop(); this.engine = null; },
  resetRuntime() {
    this.cleanup();
    this.sessionId = null;
    this.completing = false;
    this.normalEnd = false;
    this.currentStage = 'stage_1';
    this.cleanupTasks = [];
  },
  cleanup() {
    clearInterval(this.countdownTimer);
    clearInterval(this.checkpointTimer);
    this.stopEngine();
    for (const cleanup of this.cleanupTasks || []) cleanup();
    this.cleanupTasks = [];
  },
};
