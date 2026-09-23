/**
 * SPA Main Router and Application Orchestrator
 */

import { api } from './api.js';
import { ui } from './ui.js';
import { GameChoiceModal } from './components/game_choice_modal.js';

import { HomeView } from './views/home.js';
import { GameView } from './views/game_view.js';
import { ResultView } from './views/result_view.js';
import { DrawView } from './views/draw_view.js';
import { PrizeView } from './views/prize_view.js';
import { RankingView } from './views/ranking_view.js';
import { InviteView } from './views/invite_view.js';
import { BenefitView } from './views/benefit_view.js';

class AppRouter {
  constructor() {
    this.container = document.getElementById('view-container');
    this.ticketPill = document.getElementById('header-ticket-pill');
    this.currentView = 'home';
    this.state = {
      tickets: 1,
      bestScore: 0,
      lastResult: null
    };

    this.views = {
      home: HomeView,
      game: GameView,
      result: ResultView,
      draw: DrawView,
      claims: PrizeView,
      ranking: RankingView,
      invite: InviteView,
      benefit: BenefitView
    };
  }

  async init() {
    // 0. Run 2-second official Google Student Ambassador splash sequence
    const splashPromise = this.runSplashScreen(2000);

    // 1. Parse invite code from URL if present
    const urlParams = new URLSearchParams(window.location.search);
    const inviteCode = urlParams.get('invite');

    try {
      // 2. Initialize or restore participant
      await api.initParticipant(inviteCode);
      if (inviteCode) {
        ui.showToast('친구 추천 코드가 적용되었습니다!');
      }

      // 3. Fetch latest /me state
      const meData = await api.getMe();
      this.state.tickets = meData.tickets;
      this.state.bestScore = meData.best_score;
      this.updateNav();

      // Check if there is an un-scratched draw waiting
      if (meData.pending_draw) {
        this.state.lastResult = {
          sessionId: meData.pending_draw.id,
          score: meData.pending_draw.score,
          bestScore: meData.best_score
        };
      }

    } catch (err) {
      console.error('App init error:', err);
    }

    // 4. Bind bottom navigation
    document.querySelectorAll('.bottom-nav .nav-item').forEach(item => {
      item.addEventListener('click', (e) => {
        e.preventDefault();
        const targetView = item.dataset.view;
        this.navigate(targetView);
      });
    });

    // 5. Wait for full 2-second official splash animation before revealing main app
    await splashPromise;
    this.hideSplashScreen();

    // 6. Initial route
    const requestedView = urlParams.get('view');
    const entryViews = ['home', 'ranking', 'claims', 'invite', 'benefit'];
    const initialView = entryViews.includes(requestedView) ? requestedView : 'home';
    this.navigate(initialView);

    // 7. 로딩 완료 직후 게임 선택 팝업 (주 1위 CJ 1만원권 챌린지) 자동 노출
    if (initialView === 'home') {
      setTimeout(() => {
        GameChoiceModal.open(this);
      }, 300);
    }
  }

  runSplashScreen(durationMs = 2000) {
    return new Promise((resolve) => {
      const progressBar = document.getElementById('splash-progress-bar');
      const statusText = document.getElementById('splash-status-text');
      if (!progressBar) {
        resolve();
        return;
      }

      const startTime = performance.now();
      const interval = setInterval(() => {
        const elapsed = performance.now() - startTime;
        const progress = Math.min(elapsed / durationMs, 1.0);

        progressBar.style.width = `${progress * 100}%`;

        if (progress < 0.35) {
          if (statusText) statusText.textContent = 'Google Student Ambassador 서버 연결 중...';
        } else if (progress < 0.75) {
          if (statusText) statusText.textContent = '🛡️ 보안 인증 및 학생 혜택 풀 동기화 중...';
        } else if (progress < 0.95) {
          if (statusText) statusText.textContent = '🦖 공룡 챌린지 준비 완료!';
        }

        if (progress >= 1.0) {
          clearInterval(interval);
          resolve();
        }
      }, 50);
    });
  }

  hideSplashScreen() {
    const splash = document.getElementById('splash-screen');
    if (splash) {
      splash.classList.add('fade-out');
      setTimeout(() => {
        splash.style.display = 'none';
      }, 500);
    }
  }

  navigate(viewName) {
    if (!this.views[viewName]) {
      viewName = 'home';
    }

    // Cleanup active view if applicable
    if (this.currentView === 'game' && this.views.game.cleanup) {
      this.views.game.cleanup();
    }

    this.currentView = viewName;

    // Update bottom nav active indicator
    document.querySelectorAll('.bottom-nav .nav-item').forEach(item => {
      if (item.dataset.view === viewName) {
        item.classList.add('active');
      } else {
        item.classList.remove('active');
      }
    });

    // Render new view
    const view = this.views[viewName];
    this.container.innerHTML = '';
    view.render(this.container, this);

    window.scrollTo({ top: 0, behavior: 'smooth' });
  }

  updateNav() {
    if (this.ticketPill) {
      this.ticketPill.textContent = `🎟️ 무제한`;
    }
  }
}

// Bootstrap on DOM ready
document.addEventListener('DOMContentLoaded', () => {
  const router = new AppRouter();
  router.init();
  window.__geminiRouter = router;
});
