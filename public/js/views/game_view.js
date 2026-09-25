import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { audio } from '../game/audio.js';
import { DinoGameEngine } from '../game/engine.js';

const PENDING_RESULT_KEY = 'dino_pending_result';
const CHECKPOINT_PREFIX = 'dino_checkpoint_';
const FAULT_PREFIX = 'dino_fault_';
const SNAPSHOT_PREFIX = 'dino_snapshot_';
function storageGet(key) { try { return sessionStorage.getItem(key); } catch (_) { return null; } }
function storageSet(key, value) { try { sessionStorage.setItem(key, value); return true; } catch (_) { return false; } }
function storageRemove(key) { try { sessionStorage.removeItem(key); } catch (_) {} }

export const GameView = {
  engine: null,
  sessionId: null,
  ticketKind: null,
  cleanupTasks: [],
  countdownTimer: null,
  completing: false,
  normalEnd: false,
  currentStage: 'stage_1',
  gameVersion: null,
  countdownResolve: null,
  countdownRunId: 0,
  heartsCollected: 0,
  expiryTimer: null,

  async render(container, router, renderToken) {
    this.resetRuntime();
    this.renderGameShell(container);
    try {
      const recovered = await this.recoverPendingResult(router, renderToken);
      if (recovered || !router.isCurrent(renderToken)) return;
      if (router.state.pendingGameSession) {
        this.renderInterruptedSession(container, router, renderToken, router.state.pendingGameSession);
        return;
      }
      if (!router.isCurrent(renderToken)) return;
      await this.startNewSession(container, router, renderToken);
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      this.renderFailure(container, router, error);
    }
  },

  renderGameShell(container) {
    container.innerHTML = `
      <section class="game-screen-wrapper">
        <div class="game-center-section">
          <div class="game-viewport-container">
            <canvas id="game-canvas"></canvas>
            <div class="game-hud">
              <div class="hud-left"><span id="hud-stage-badge" class="stage-tag">STAGE 1</span><span class="hud-item hud-coin" aria-label="획득 코인"><span aria-hidden="true">●</span><strong id="hud-coin-count">0</strong></span><span class="hud-item hud-heart" aria-label="보유 부활권"><img src="/assets/icons/Heart-Light.png" alt=""><strong id="hud-heart-count">0</strong></span><span class="hud-item hud-revive" aria-label="이번 판 부활 횟수">↻ <strong id="hud-revive-count">0</strong></span></div>
              <div class="hud-right"><strong id="hud-current-score" class="current-score">0</strong><button id="btn-toggle-sound" class="sound-toggle-btn" aria-label="소리 켜기 또는 끄기">🔊</button></div>
            </div>
            <div id="stage-flash-badge"><div class="stage-name">STAGE 1</div><div class="stage-sub">가볍게 시작!</div></div>
            <div id="revive-flash" class="revive-flash" role="status" aria-live="polite"><img src="/assets/icons/Heart-Light.png" alt=""><strong>부활!</strong><span>보호막이 잠시 유지돼요</span></div>
            <div id="countdown-overlay" class="countdown-overlay active"><div id="countdown-num" class="countdown-number">3</div><div>탭하여 점프하세요!</div></div>
          </div>
          <div class="jump-hint-box">탭: 낮게 점프 · 꾹 누르기: 높게 점프 · 높은 새: 점프 금지</div>
          <div id="game-session-notice" class="game-session-notice" role="status" hidden></div>
        </div>
        <div class="jump-bottom-dock"><button id="btn-jump" class="big-jump-btn">🚀 점프</button></div>
      </section>`;
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
        storageRemove(`${SNAPSHOT_PREFIX}${pending.sessionId}`);
        this.acceptResult(state.result || state, router);
        analytics.track('game_recovered', { status: 'FINISHED' }, { gameSessionId: pending.sessionId });
        router.navigate('result');
        return true;
      }
      const result = await api.finishSession(pending.sessionId, pending.payload, pending.key);
      storageRemove(PENDING_RESULT_KEY);
      storageRemove(`${SNAPSHOT_PREFIX}${pending.sessionId}`);
      this.acceptResult(result, router);
      router.navigate('result');
      return true;
    } catch (error) {
      if (error.status && error.status < 500) storageRemove(PENDING_RESULT_KEY);
      throw error;
    }
  },

  renderInterruptedSession(container, router, renderToken, pending) {
    const id = pending.id || pending.session_id;
    const faultMarker = this.readFaultMarker(id);
    const snapshot = this.readResumeSnapshot(id);
    container.replaceChildren();
    const card = document.createElement('section'); card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '완료되지 않은 게임이 있어요';
    const detail = document.createElement('p'); detail.textContent = pending.status === 'FAULT_REPORTED' ? '장애 기록을 확인하고 사용한 게임권을 복구하는 중입니다. 정상 종료나 자발적 이탈은 환급 대상이 아닙니다.' : faultMarker ? '이 브라우저에 저장된 장애 시점과 서버 체크포인트를 확인해 복구를 요청합니다. 정상 종료나 자발적 이탈은 환급 대상이 아닙니다.' : snapshot ? '저장된 진행 시점과 서버 체크포인트를 확인한 뒤 같은 게임을 이어갑니다.' : '이 브라우저에 이어하기 데이터가 없어 게임을 처음부터 다시 시작할 수 없습니다. 세션 만료 또는 복구 상태를 확인해 주세요. 정상 종료나 자발적 이탈은 환급 대상이 아닙니다.';
    const check = document.createElement('button'); check.className = 'btn btn-primary'; check.textContent = pending.status === 'FAULT_REPORTED' ? '복구 상태 확인' : faultMarker ? '장애 복구 요청' : snapshot ? '같은 게임 이어하기' : '복구 상태 확인';
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
          const state = await api.getSession(id);
          if (!router.isCurrent(renderToken)) return;
          if (state.status === 'FINISHED') { storageRemove(`${SNAPSHOT_PREFIX}${id}`); this.acceptResult(state.result || state, router); router.navigate('result'); return; }
          if (state.status === 'ABORTED' || state.status === 'EXPIRED') { this.clearSessionStorage(id); await router.refreshState(); analytics.track('game_recovered', { status: state.status }, { gameSessionId: id }); router.navigate('home'); return; }
          const currentSnapshot = this.readResumeSnapshot(id);
          const invalidReason = this.validateResumeSnapshot(currentSnapshot, state);
          if (invalidReason) {
            storageRemove(`${SNAPSHOT_PREFIX}${id}`);
            detail.textContent = `${invalidReason} 게임을 처음부터 다시 시작하지 않습니다. 세션 만료 또는 장애 복구 상태를 다시 확인해 주세요.`;
            check.textContent = '복구 상태 확인';
            check.disabled = false;
            return;
          }
          await this.resumeActiveSession(container, router, renderToken, state, currentSnapshot);
          return;
        }
        const state = await api.getSession(id);
        if (state.status === 'FINISHED') { this.acceptResult(state.result || state, router); router.navigate('result'); return; }
        if (state.status === 'ABORTED') { this.clearSessionStorage(id); await router.refreshState(); analytics.track('game_recovered', { status: 'ABORTED' }, { gameSessionId: id }); router.navigate('home'); return; }
        detail.textContent = '서버가 장애 기록을 확인 중입니다. 잠시 후 다시 확인해 주세요.';
      } catch (error) { ui.showToast(error.message); }
      check.disabled = false;
    };
    const home = document.createElement('button'); home.className = 'btn btn-secondary'; home.textContent = '홈으로'; home.onclick = () => router.navigate('home');
    card.append(title, detail, check, home); container.appendChild(card);
  },

  readResumeSnapshot(sessionId) {
    const raw = storageGet(`${SNAPSHOT_PREFIX}${sessionId}`);
    if (!raw) return null;
    try { return JSON.parse(raw); } catch (_) { storageRemove(`${SNAPSHOT_PREFIX}${sessionId}`); return null; }
  },

  validateResumeSnapshot(snapshot, state) {
    if (!snapshot) return '이 브라우저에 저장된 진행 데이터가 없습니다.';
    if (state?.status !== 'ACTIVE' && state?.status !== 'RESERVED') return '이어갈 수 있는 활성 게임이 아닙니다.';
    if (state.version !== '2.0.0' || snapshot.version !== state.version) return '게임 버전이 일치하지 않습니다.';
    if (snapshot.sessionId !== (state.session_id || state.id) || Number(snapshot.seed) !== Number(state.seed)) return '게임 세션 정보가 일치하지 않습니다.';
    const tick = Number(snapshot.tick);
    const checkpoint = Number(state.last_checkpoint_tick || 0);
    if (!Number.isInteger(tick) || tick < checkpoint || tick < 0 || tick >= 36000) return '저장 시점이 서버 체크포인트보다 오래되었거나 올바르지 않습니다.';
    if (state.status === 'RESERVED' && tick !== 0) return '시작 전 세션의 진행 데이터가 올바르지 않습니다.';
    let previousJumpTick = -1;
    if (!Array.isArray(snapshot.jumpTicks) || snapshot.jumpTicks.some((jump) => {
      const jumpTick = Number(jump?.tick);
      const invalid = !Number.isInteger(jumpTick) || jumpTick < 0 || jumpTick >= tick || jumpTick <= previousJumpTick || typeof jump?.high !== 'boolean';
      previousJumpTick = jumpTick;
      return invalid;
    })) return '저장된 점프 기록이 올바르지 않습니다.';
    const expiresAt = Date.parse(state.expires_at || '');
    if (!Number.isFinite(expiresAt) || expiresAt <= Date.now()) return '게임 세션 시간이 만료되었습니다.';
    return null;
  },

  persistResumeSnapshot() {
    if (!this.sessionId || this.normalEnd || this.completing || !this.engine) return false;
    const snapshot = this.engine.getResumeSnapshot?.();
    if (!snapshot) return false;
    return storageSet(`${SNAPSHOT_PREFIX}${this.sessionId}`, JSON.stringify({ sessionId: this.sessionId, ...snapshot }));
  },

  clearSessionStorage(sessionId) {
    storageRemove(`${CHECKPOINT_PREFIX}${sessionId}`);
    storageRemove(`${FAULT_PREFIX}${sessionId}`);
    storageRemove(`${SNAPSHOT_PREFIX}${sessionId}`);
  },

  async resumeActiveSession(container, router, renderToken, state, snapshot) {
    this.sessionId = state.session_id || state.id;
    this.ticketKind = state.ticket_kind || null;
    this.gameVersion = state.version;
    this.renderGameShell(container);
    this.bindEngine(container, router, renderToken, state.seed);
    let restored;
    try {
      restored = this.engine.restoreSnapshot(snapshot);
    } catch (_) {
      this.cleanup();
      storageRemove(`${SNAPSHOT_PREFIX}${this.sessionId}`);
      this.renderInterruptedSession(container, router, renderToken, state);
      return false;
    }
    this.currentStage = `stage_${restored.stage.stage}`;
    this.heartsCollected = Number(restored.summary.hearts || 0);
    ui.text(container.querySelector('#hud-stage-badge'), restored.stage.title);
    ui.text(container.querySelector('#hud-current-score'), restored.score);
    ui.text(container.querySelector('#hud-coin-count'), Number(restored.summary.coins || 0));
    ui.text(container.querySelector('#hud-heart-count'), Number(restored.heart || 0));
    ui.text(container.querySelector('#hud-revive-count'), Number(restored.summary.revives || 0));
    let expiresAt = state.expires_at;
    if (state.status === 'RESERVED') {
      const started = await api.startSession(this.sessionId);
      if (!router.isCurrent(renderToken)) { this.cleanup(); return false; }
      expiresAt = started.expires_at;
    }
    this.monitorSessionExpiry(container, router, renderToken, expiresAt);
    const countdownCompleted = await this.runCountdown(container, 3);
    if (!countdownCompleted || !router.isCurrent(renderToken)) return;
    this.engine.resumeRestored();
    this.persistResumeSnapshot();
    this.checkpointTimer = setInterval(() => this.sendCheckpoint(), 5000);
    analytics.track('game_recovered', { status: 'ACTIVE', game_version: this.gameVersion, checkpoint: Number(snapshot.tick) }, { gameSessionId: this.sessionId });
    return true;
  },

  async startNewSession(container, router, renderToken) {
    const session = await api.createSession();
    if (!router.isCurrent(renderToken)) return;
    this.sessionId = session.session_id;
    this.ticketKind = session.ticket_kind || null;
    this.gameVersion = session.version || router.config?.game_version || '2.0.0';
    storageSet(`${CHECKPOINT_PREFIX}${this.sessionId}`, '0');
    storageSet(`${SNAPSHOT_PREFIX}${this.sessionId}`, JSON.stringify({ sessionId: this.sessionId, version: this.gameVersion, seed: session.seed, tick: 0, jumpTicks: [] }));
    await router.refreshState({ quiet: true });
    if (!router.isCurrent(renderToken)) return;
    this.bindEngine(container, router, renderToken, session.seed);
    const countdownCompleted = await this.runCountdown(container, 3);
    if (!countdownCompleted || !router.isCurrent(renderToken)) return;
    const started = await api.startSession(this.sessionId);
    if (!router.isCurrent(renderToken)) return;
    this.monitorSessionExpiry(container, router, renderToken, started.expires_at);
    analytics.track('game_start_approved', { game_version: session.version || '' }, { gameSessionId: this.sessionId });
    analytics.track('game_checkpoint', { stage: 'stage_1', checkpoint: 0 }, { gameSessionId: this.sessionId });
    this.engine.start(session.seed);
    this.persistResumeSnapshot();
    this.checkpointTimer = setInterval(() => this.sendCheckpoint(), 5000);
  },

  async sendCheckpoint() {
    if (!this.sessionId || !this.engine?.isRunning || this.completing) return;
    const tick = Number(this.engine.currentTick || 0);
    if (tick <= 0) return;
    this.persistResumeSnapshot();
    try {
      await api.checkpointSession(this.sessionId, tick, this.currentStage);
      storageSet(`${CHECKPOINT_PREFIX}${this.sessionId}`, String(tick));
      storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
    } catch (error) {
      if (!error.status || error.status >= 500) this.persistFaultMarker('NETWORK_ERROR', tick);
    }
  },

  monitorSessionExpiry(container, router, renderToken, expiresAt) {
    clearInterval(this.expiryTimer);
    const deadline = Date.parse(expiresAt || '');
    if (!Number.isFinite(deadline)) return;
    const notice = container.querySelector('#game-session-notice');
    const update = () => {
      if (!router.isCurrent(renderToken)) { clearInterval(this.expiryTimer); return; }
      const remaining = Math.ceil((deadline - Date.now()) / 1000);
      if (remaining <= 0) {
        clearInterval(this.expiryTimer);
        clearInterval(this.checkpointTimer);
        this.normalEnd = true;
        this.stopEngine();
        storageRemove(`${SNAPSHOT_PREFIX}${this.sessionId}`);
        this.renderFailure(container, router, { message: '게임 세션 시간이 만료됐어요. 상태를 갱신한 뒤 다시 시작해 주세요.' });
        return;
      }
      if (notice && remaining <= 120) {
        notice.hidden = false;
        notice.textContent = `세션 종료까지 ${Math.ceil(remaining / 60)}분 · 10분 완주 시 기록이 자동 확정돼요.`;
      }
    };
    update();
    this.expiryTimer = setInterval(update, 1000);
  },

  bindEngine(container, router, renderToken, seed) {
    const canvas = container.querySelector('#game-canvas');
    const stageBadge = container.querySelector('#hud-stage-badge');
    const score = container.querySelector('#hud-current-score');
    const coinCount = container.querySelector('#hud-coin-count');
    const heartCount = container.querySelector('#hud-heart-count');
    const reviveCount = container.querySelector('#hud-revive-count');
    const reviveFlash = container.querySelector('#revive-flash');
    const flash = container.querySelector('#stage-flash-badge');
    this.engine = new DinoGameEngine(canvas, {
      version: this.gameVersion,
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
      onCoinCollected: (event = {}) => {
        const count = Number(event.coin_count || 0);
        ui.text(coinCount, count);
        if (Number.isFinite(event.score)) ui.text(score, event.score);
        analytics.track('game_coin_collected', { game_version: this.gameVersion, coin_count: count, coin_score: Number(event.coin_score || 0), score: Number(event.score || 0), tick: Number(this.engine?.currentTick || 0) }, { gameSessionId: this.sessionId });
      },
      onHeartChange: (event = {}) => {
        const hearts = Math.max(0, Math.min(1, Number(event.hearts || 0)));
        ui.text(heartCount, hearts);
        const collected = Number(event.hearts_collected || 0);
        if (collected > this.heartsCollected) {
          this.heartsCollected = collected;
          analytics.track('game_heart_collected', { game_version: this.gameVersion, hearts, tick: Number(this.engine?.currentTick || 0) }, { gameSessionId: this.sessionId });
        }
      },
      onRevive: (event = {}) => {
        const revives = Number(event.revive_count || 0);
        ui.text(heartCount, Math.max(0, Math.min(1, Number(event.hearts || 0))));
        ui.text(reviveCount, revives);
        reviveFlash.classList.remove('show');
        void reviveFlash.offsetWidth;
        reviveFlash.classList.add('show');
        const timer = setTimeout(() => reviveFlash.classList.remove('show'), window.matchMedia?.('(prefers-reduced-motion: reduce)').matches ? 120 : 650);
        this.cleanupTasks.push(() => clearTimeout(timer));
        analytics.track('game_revived', { game_version: this.gameVersion, revive_count: revives, hearts: Number(event.hearts || 0), tick: Number(this.engine?.currentTick || 0) }, { gameSessionId: this.sessionId });
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
      else if (this.engine?.isPaused) this.runCountdown(container, 3).then((completed) => { if (completed && router.isCurrent(renderToken)) this.engine?.resume(); });
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
    const pageHide = () => this.persistResumeSnapshot();
    window.addEventListener('pagehide', pageHide);
    this.cleanupTasks.push(() => window.removeEventListener('pagehide', pageHide));
  },

  runCountdown(container, seconds) {
    clearInterval(this.countdownTimer);
    this.countdownResolve?.(false);
    const runId = ++this.countdownRunId;
    const overlay = container.querySelector('#countdown-overlay');
    const number = container.querySelector('#countdown-num');
    if (!overlay || !number) return Promise.resolve(false);
    overlay.classList.add('active');
    let remaining = seconds;
    number.textContent = remaining;
    return new Promise((resolve) => {
      this.countdownResolve = resolve;
      this.countdownTimer = setInterval(() => {
        if (runId !== this.countdownRunId || !overlay.isConnected) {
          clearInterval(this.countdownTimer);
          this.countdownResolve = null;
          resolve(false);
          return;
        }
        remaining -= 1;
        number.textContent = remaining;
        if (remaining <= 0) {
          clearInterval(this.countdownTimer);
          overlay.classList.remove('active');
          this.countdownResolve = null;
          resolve(true);
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
    const summary = result.summary || this.engine?.getSummary?.() || {};
    const payload = {
      version: result.version || this.gameVersion || '2.0.0',
      end_reason: result.end_reason || 'COLLISION',
      score: result.score,
      ticks: result.ticks,
      jump_ticks: result.jump_ticks,
      checkpoints: result.checkpoints || [],
      summary: {
        coins: Number(summary.coins || 0),
        coin_score: Number(summary.coin_score || 0),
        hearts: Number(summary.hearts || 0),
        revives: Number(summary.revives || 0),
      },
    };
    storageSet(PENDING_RESULT_KEY, JSON.stringify({ sessionId: this.sessionId, payload, key }));
    try {
      const response = await api.finishSession(this.sessionId, payload, key);
      storageRemove(PENDING_RESULT_KEY);
      storageRemove(`${CHECKPOINT_PREFIX}${this.sessionId}`);
      storageRemove(`${FAULT_PREFIX}${this.sessionId}`);
      storageRemove(`${SNAPSHOT_PREFIX}${this.sessionId}`);
      this.acceptResult(response, router);
      analytics.track('game_completed', { game_version: payload.version, end_reason: payload.end_reason, score: response.score, rank: response.rank || 0, status: response.verification, coin_count: payload.summary.coins, coin_score: payload.summary.coin_score, revive_count: payload.summary.revives }, { gameSessionId: this.sessionId });
      router.announceStateChange();
      router.navigate('result');
    } catch (error) {
      this.renderFinishRetry(container, router, error);
    }
  },

  acceptResult(result, router) {
    const pendingSession = router.state.pendingGameSession;
    const ticketKind = result.ticket_kind || pendingSession?.ticket_kind || this.ticketKind;
    router.state.pendingGameSession = null;
    if (result.tickets) router.state.tickets = result.tickets;
    else if (ticketKind === 'INVITATION' && Number(router.state.tickets?.invitation_reserved || 0) > 0) {
      router.state.tickets.invitation_reserved = Math.max(0, Number(router.state.tickets.invitation_reserved) - 1);
    }
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
    router.updateNav?.();
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
    this.ticketKind = null;
    this.completing = false;
    this.normalEnd = false;
    this.currentStage = 'stage_1';
    this.gameVersion = null;
    this.heartsCollected = 0;
    this.cleanupTasks = [];
  },
  cleanup() {
    this.countdownRunId += 1;
    clearInterval(this.countdownTimer);
    this.countdownResolve?.(false);
    this.countdownResolve = null;
    clearInterval(this.checkpointTimer);
    clearInterval(this.expiryTimer);
    this.persistResumeSnapshot();
    this.stopEngine();
    for (const cleanup of this.cleanupTasks || []) cleanup();
    this.cleanupTasks = [];
  },
};
