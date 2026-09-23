/**
 * Game Choice Modal Component
 * 
 * Google Student Ambassador 공식 챌린지 종목 선택 모달
 * - 불필요한 글을 전면 배제하고 직관적인 인게임 그림 중심의 미니멀 UI
 * - 세로형 직사각형 프로필 카드 2개 가로 배치 (Side-by-Side 1fr 1fr)
 */

export const GameChoiceModal = {
  modalEl: null,
  router: null,

  init(router) {
    this.router = router;
    if (document.getElementById('game-choice-modal')) {
      this.modalEl = document.getElementById('game-choice-modal');
      return;
    }

    const modal = document.createElement('div');
    modal.id = 'game-choice-modal';
    modal.className = 'modal-overlay game-choice-overlay';
    modal.innerHTML = `
      <div class="game-choice-card">
        <!-- Top Google Accent Bar (Google 4 Colors) -->
        <div class="gsa-accent-bar"></div>

        <!-- Close Button -->
        <button type="button" class="gsa-modal-close" id="btn-choice-close" aria-label="닫기">
          <svg width="18" height="18" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
          </svg>
        </button>

        <!-- Header from Uploaded Screenshot -->
        <div class="choice-header">
          <div class="choice-event-pill">
            <span class="pill-spark">🏆</span>
            <span class="pill-text">주간 랭킹 1위 특별 챌린지</span>
          </div>
          <h2 class="choice-main-title">
            각 게임 <span class="highlight-red">주 1위</span> 달성 시<br>
            <span class="highlight-blue">CJ 1만원권</span> 100% 증정! 🎁
          </h2>
          <p class="choice-sub-text">
            도전할 게임을 선택하세요
          </p>
        </div>

        <!-- 2 Tall Vertical Profile Cards (Side-by-Side Horizontal Layout) -->
        <div class="profile-cards-grid">
          
          <!-- Card 1: Classic Dino Jump -->
          <div class="game-profile-card card-jump" id="opt-dino-jump" role="button" tabindex="0">
            <!-- In-game Action Preview Graphic -->
            <div class="mini-gameplay-preview preview-jump">
              <svg viewBox="0 0 160 96" class="preview-svg">
                <!-- Sky Background -->
                <rect width="160" height="96" fill="#F8FAFF" rx="8" />
                <!-- Ground line -->
                <line x1="0" y1="78" x2="160" y2="78" stroke="#CBD5E1" stroke-width="2" stroke-dasharray="6,4" />
                
                <!-- Flying Pterodactyl in the sky -->
                <g transform="translate(118, 14)">
                  <path d="M0,7 Q6,1 14,0 Q18,5 22,11 Q14,8 8,10 Z" fill="#64748B" />
                  <circle cx="16" cy="3" r="1.5" fill="#38BDF8" />
                </g>
                
                <!-- Jump arc trajectory -->
                <path d="M22,76 Q40,22 56,46" fill="none" stroke="#93C5FD" stroke-width="1.5" stroke-dasharray="3,3" />
                
                <!-- Gemini Dino in mid-air (jumping) -->
                <image href="/assets/icons/Dino-Dark.png" x="42" y="24" width="32" height="32" />
                
                <!-- Cactus obstacle on the ground -->
                <g transform="translate(90, 52)">
                  <rect x="8" y="0" width="7" height="26" rx="2" fill="#10B981" />
                  <path d="M1,7 H8 V15 H1 Z" fill="#10B981" />
                  <path d="M15,10 H22 V18 H15 Z" fill="#10B981" />
                </g>
                
                <!-- Control Hint Badge -->
                <rect x="6" y="6" width="56" height="16" rx="4" fill="rgba(255,255,255,0.94)" stroke="#E2E8F0" stroke-width="0.8" />
                <text x="34" y="18" font-size="8.5" font-weight="700" fill="#1967D2" text-anchor="middle">👆 탭 점프</text>
              </svg>
            </div>

            <h3 class="profile-game-name">클래식 점프</h3>

            <button type="button" class="btn-profile-select btn-select-blue">
              <span>시작하기</span>
              <span class="btn-arrow">→</span>
            </button>
          </div>

          <!-- Card 2: Gate Runner (Gemini vs Claude Code) -->
          <div class="game-profile-card card-runner" id="opt-gate-runner" role="button" tabindex="0">
            <!-- In-game Action Preview Graphic -->
            <div class="mini-gameplay-preview preview-runner">
              <svg viewBox="0 0 160 96" class="preview-svg">
                <!-- Perspective Runway Background -->
                <rect width="160" height="96" fill="#FAF5FF" rx="8" />
                
                <!-- 3D Perspective Track Lines -->
                <polygon points="52,16 108,16 150,96 10,96" fill="#F3E8FF" />
                <line x1="80" y1="16" x2="80" y2="96" stroke="#E9D5FF" stroke-width="1" stroke-dasharray="4,4" />
                <line x1="66" y1="16" x2="32" y2="96" stroke="#DDD6FE" stroke-width="1.5" />
                <line x1="94" y1="16" x2="128" y2="96" stroke="#DDD6FE" stroke-width="1.5" />

                <!-- 3D Multiplier Gate in the center (Arch with ×2) -->
                <g transform="translate(60, 22)">
                  <rect x="0" y="0" width="40" height="30" rx="4" fill="rgba(37, 99, 235, 0.16)" stroke="#2563EB" stroke-width="1.5" />
                  <rect x="0" y="0" width="40" height="10" rx="3" fill="#2563EB" />
                  <text x="20" y="8" font-size="7" font-weight="900" fill="#FFFFFF" text-anchor="middle">★ MULTIPLY</text>
                  <text x="20" y="24" font-size="12" font-weight="900" fill="#1D4ED8" text-anchor="middle">×2</text>
                </g>

                <!-- Enemy Claude Code Boss waiting ahead -->
                <image href="/assets/icons/claude_code.svg" x="70" y="4" width="20" height="20" />

                <!-- Swarm of Multiplied Gemini Dinos Running -->
                <image href="/assets/icons/Dino-Dark.png" x="34" y="66" width="18" height="18" />
                <image href="/assets/icons/Dino-Dark.png" x="58" y="60" width="22" height="22" />
                <image href="/assets/icons/Dino-Dark.png" x="86" y="66" width="18" height="18" />
                <image href="/assets/icons/Dino-Dark.png" x="108" y="62" width="19" height="19" />

                <!-- Control Hint Badge -->
                <rect x="6" y="6" width="58" height="16" rx="4" fill="rgba(255,255,255,0.94)" stroke="#E2E8F0" stroke-width="0.8" />
                <text x="35" y="18" font-size="8.5" font-weight="700" fill="#7C3AED" text-anchor="middle">↔️ 좌우 이동</text>
              </svg>
            </div>

            <h3 class="profile-game-name">게이트 러너</h3>

            <button type="button" class="btn-profile-select btn-select-blue">
              <span>시작하기</span>
              <span class="btn-arrow">→</span>
            </button>
          </div>

        </div>

        <!-- Minimal Footer -->
        <div class="gsa-modal-footer">
          <button type="button" class="gsa-btn-dismiss" id="btn-choice-dismiss">
            홈 둘러보기
          </button>
        </div>
      </div>
    `;

    document.body.appendChild(modal);
    this.modalEl = modal;
    this.bindEvents();
  },

  bindEvents() {
    if (!this.modalEl) return;

    const closeBtn = this.modalEl.querySelector('#btn-choice-close');
    const dismissBtn = this.modalEl.querySelector('#btn-choice-dismiss');
    const optJump = this.modalEl.querySelector('#opt-dino-jump');
    const optRunner = this.modalEl.querySelector('#opt-gate-runner');

    const handleClose = () => {
      this.close();
    };

    if (closeBtn) closeBtn.onclick = handleClose;
    if (dismissBtn) dismissBtn.onclick = handleClose;

    // Click outside backdrop to close
    this.modalEl.onclick = (e) => {
      if (e.target === this.modalEl) {
        this.close();
      }
    };

    // Option 1: Classic Jump
    if (optJump) {
      optJump.onclick = (e) => {
        e.stopPropagation();
        this.close();
        if (this.router) {
          const hasSeenGuide = localStorage.getItem('gemini_dino_guide_seen');
          if (!hasSeenGuide) {
            this.router.navigate('home');
            setTimeout(() => {
              const startBtn = document.getElementById('btn-quick-jump');
              if (startBtn) startBtn.click();
            }, 100);
          } else {
            this.router.navigate('game');
          }
        }
      };
    }

    // Option 2: Gate Runner -> Direct navigate to gate_runner.html
    if (optRunner) {
      optRunner.onclick = (e) => {
        e.stopPropagation();
        this.close();
        window.location.href = '/gate_runner.html';
      };
    }
  },

  open(router) {
    if (router) this.router = router;
    if (!this.modalEl) this.init(this.router);

    document.body.style.overflow = 'hidden';
    this.modalEl.classList.add('active');
  },

  close() {
    if (this.modalEl) {
      this.modalEl.classList.remove('active');
      document.body.style.overflow = '';
    }
  }
};
