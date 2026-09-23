/**
 * S03 Game Play View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';
import { audio } from '../game/audio.js';
import { DinoGameEngine } from '../game/engine.js';

export const GameView = {
  engine: null,
  sessionId: null,

  async render(container, router) {
    container.innerHTML = `
      <div class="game-screen-wrapper">
        <!-- Strictly Centered Game Play Section -->
        <div class="game-center-section">
          <div class="game-viewport-container">
            <canvas id="game-canvas"></canvas>

            <!-- Top HUD Overlay -->
            <div class="game-hud">
              <div class="hud-left">
                <span id="hud-stage-badge" class="stage-tag">STAGE 1</span>
              </div>
              <div class="hud-right">
                <div class="score-display">
                  <div id="hud-current-score" class="current-score">0</div>
                  <div class="best-score-label">BEST ${router.state.bestScore || 0}</div>
                </div>
                <button id="btn-toggle-sound" class="sound-toggle-btn" title="음소거 토글">
                  ${audio.isMuted() ? '🔇' : '🔊'}
                </button>
              </div>
            </div>

            <!-- Non-blocking Stage Transition Banner -->
            <div id="stage-flash-badge">
              <div class="stage-name">STAGE 1</div>
              <div class="stage-sub">가볍게 시작!</div>
            </div>

            <!-- Countdown Overlay -->
            <div id="countdown-overlay" class="countdown-overlay active">
              <div id="countdown-num" class="countdown-number">3</div>
              <div style="font-size: 14px; font-weight: 700; color: var(--text-sub); margin-top: 8px;">
                탭하여 점프하세요!
              </div>
            </div>
          </div>

          <div class="jump-hint-box">
            💡 <strong>탭:</strong> 낮게 점프 &nbsp;|&nbsp; <strong>꾹 누르기:</strong> 높게 점프 &nbsp;|&nbsp; 🦅 <strong>높은 새:</strong> 점프 금지!
          </div>
        </div>

        <!-- Mobile Fixed Bottom Jump Control Bar -->
        <div class="jump-bottom-dock">
          <button id="btn-jump" class="big-jump-btn">
            <span>🚀 점프 (짧게: 낮게 / 길게: 높게)</span>
          </button>
        </div>
      </div>
    `;

    const canvas = container.querySelector('#game-canvas');
    const stageBadge = container.querySelector('#hud-stage-badge');
    const scoreEl = container.querySelector('#hud-current-score');
    const flashBadge = container.querySelector('#stage-flash-badge');
    const countdownOverlay = container.querySelector('#countdown-overlay');
    const countdownNum = container.querySelector('#countdown-num');
    const soundBtn = container.querySelector('#btn-toggle-sound');
    const jumpBtn = container.querySelector('#btn-jump');

    // 1. Initialize Engine
    this.engine = new DinoGameEngine(canvas, {
      onScoreUpdate: (score) => {
        scoreEl.textContent = score;
      },
      onStageChange: (stage) => {
        stageBadge.textContent = stage.title;
        flashBadge.querySelector('.stage-name').textContent = stage.title;
        flashBadge.querySelector('.stage-sub').textContent = stage.sub;
        flashBadge.classList.add('show');
        setTimeout(() => {
          flashBadge.classList.remove('show');
        }, 1500);
      },
      onGameOver: async (result) => {
        this.handleGameOver(result, router);
      }
    });

    // Sound toggle button
    soundBtn.onclick = (e) => {
      e.stopPropagation();
      const muted = audio.toggleMute();
      soundBtn.textContent = muted ? '🔇' : '🔊';
    };

    // 2-Stage Jump Input Event Handlers
    const handleJumpPress = (e) => {
      if (e) {
        if (e.cancelable) e.preventDefault();
        e.stopPropagation();
      }
      if (this.engine) this.engine.jumpPress();
    };

    const handleJumpRelease = (e) => {
      if (e) {
        if (e.cancelable) e.preventDefault();
        e.stopPropagation();
      }
      if (this.engine) this.engine.jumpRelease();
    };

    // Pointer Events (supports Touch, Mouse, Pen)
    jumpBtn.addEventListener('pointerdown', handleJumpPress);
    jumpBtn.addEventListener('pointerup', handleJumpRelease);
    jumpBtn.addEventListener('pointercancel', handleJumpRelease);

    canvas.addEventListener('pointerdown', handleJumpPress);
    canvas.addEventListener('pointerup', handleJumpRelease);
    canvas.addEventListener('pointercancel', handleJumpRelease);

    // Global release listener
    this.windowPointerUpHandler = handleJumpRelease;
    window.addEventListener('pointerup', this.windowPointerUpHandler);

    // Keyboard Events
    this.keyDownHandler = (e) => {
      if ((e.code === 'Space' || e.code === 'ArrowUp') && !e.repeat) {
        e.preventDefault();
        handleJumpPress();
      }
    };
    this.keyUpHandler = (e) => {
      if (e.code === 'Space' || e.code === 'ArrowUp') {
        e.preventDefault();
        handleJumpRelease();
      }
    };
    window.addEventListener('keydown', this.keyDownHandler);
    window.addEventListener('keyup', this.keyUpHandler);

    // Visibility change handler for auto-pause and 3s countdown resumption
    this.visibilityHandler = () => {
      if (document.hidden) {
        if (this.engine && this.engine.isRunning) {
          this.engine.pause();
        }
      } else {
        if (this.engine && this.engine.isPaused) {
          this.runCountdown(3, () => {
            if (this.engine) this.engine.resume();
          }, countdownOverlay, countdownNum);
        }
      }
    };
    document.addEventListener('visibilitychange', this.visibilityHandler);

    // 2. Start game session flow
    try {
      const sessionData = await api.createSession();
      this.sessionId = sessionData.session_id;

      // Keep unlimited tickets visual
      router.updateNav();

      // Run initial 3s countdown
      this.runCountdown(3, async () => {
        try {
          await api.startSession(this.sessionId);
          this.engine.start(sessionData.seed);
        } catch (err) {
          ui.showToast('게임 시작 중 오류가 발생했습니다.');
          router.navigate('home');
        }
      }, countdownOverlay, countdownNum);

    } catch (err) {
      ui.showToast(err.message || '세션 생성에 실패했습니다.');
      router.navigate('home');
    }
  },

  runCountdown(seconds, callback, overlay, numEl) {
    overlay.classList.add('active');
    let count = seconds;
    numEl.textContent = count;

    const timer = setInterval(() => {
      count--;
      if (count > 0) {
        numEl.textContent = count;
      } else {
        clearInterval(timer);
        overlay.classList.remove('active');
        callback();
      }
    }, 1000);
  },

  async handleGameOver(result, router) {
    this.cleanup();
    ui.showToast('💥 장애물에 충돌했습니다!');

    try {
      const verifyRes = await api.finishSession(this.sessionId, result);
      // Update global router state
      router.state.bestScore = Math.max(router.state.bestScore || 0, verifyRes.best_score);
      router.state.lastResult = {
        sessionId: this.sessionId,
        score: verifyRes.score,
        bestScore: verifyRes.best_score,
        rank: verifyRes.rank,
        verificationResult: verifyRes.verification_result
      };
      router.updateNav();

      setTimeout(() => {
        router.navigate('result');
      }, 1000);
    } catch (err) {
      ui.showToast('점수 저장 중 오류가 발생했습니다.');
      router.navigate('home');
    }
  },

  cleanup() {
    if (this.engine) {
      this.engine.stop();
      this.engine = null;
    }
    if (this.keyDownHandler) {
      window.removeEventListener('keydown', this.keyDownHandler);
    }
    if (this.keyUpHandler) {
      window.removeEventListener('keyup', this.keyUpHandler);
    }
    if (this.windowPointerUpHandler) {
      window.removeEventListener('pointerup', this.windowPointerUpHandler);
    }
    if (this.visibilityHandler) {
      document.removeEventListener('visibilitychange', this.visibilityHandler);
    }
  }
};
