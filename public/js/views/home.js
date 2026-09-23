/**
 * S01 Home & S02 Guide View Component
 */

import { ui } from '../ui.js';

export const HomeView = {
  render(container, router) {
    const bestScore = router.state.bestScore || 0;

    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 28px 20px; background: #FFF;">
        <div style="margin-bottom: 12px;">
          <span class="sticker-badge badge-blue">#TeamGemini</span>
          <span class="sticker-badge badge-yellow" style="margin-left: 4px;">2026 캠퍼스 챌린지</span>
        </div>

        <div style="font-size: 13px; color: var(--text-sub); font-weight: 600; margin-bottom: 6px;">
          공식 Google Student Ambassador 운영
        </div>

        <h1 style="font-size: 26px; font-weight: 900; color: var(--text-main); line-height: 1.25; margin-bottom: 8px;">
          공룡 점프,<br><span style="color: var(--primary);">어디까지 갈 수 있어?</span>
        </h1>

        <p style="font-size: 14px; color: var(--text-sub); margin-bottom: 18px;">
          장애물을 넘고 최고 기록에 도전하세요.<br>
          한 판만 완주해도 <strong>100% 즉석 복주머니 복권</strong> 증정!
        </p>

        <!-- Dino Hero Visual -->
        <div style="position: relative; width: 130px; height: 130px; margin: 0 auto 16px;">
          <div style="position: absolute; inset: 0; background: radial-gradient(circle, rgba(66,133,244,0.15) 0%, transparent 70%); border-radius: 50%;"></div>
          <img src="/assets/icons/Dino-Dark.png" alt="Gemini Dino" style="width: 100%; height: 100%; object-fit: contain; filter: drop-shadow(0 8px 16px rgba(25, 103, 210, 0.2));">
        </div>

        <!-- Google Student Ambassador Official Challenge Banner -->
        <div style="background: #F8FAFF; border: 1px solid #D2E3FC; border-radius: 16px; padding: 12px 14px; margin-bottom: 18px; display: flex; align-items: center; gap: 12px; text-align: left;">
          <div style="width: 36px; height: 36px; border-radius: 10px; background: #E8F0FE; display: flex; align-items: center; justify-content: center; font-size: 18px; flex-shrink: 0;">
            🏆
          </div>
          <div style="flex: 1; min-width: 0;">
            <div style="font-size: 11px; font-weight: 700; color: #1967D2; letter-spacing: 0.2px;">주간 랭킹 챌린지</div>
            <div style="font-size: 13.5px; font-weight: 700; color: #202124; line-height: 1.35;">
              주간 1위 유지 시 <span style="color: #1967D2;">CJ 1만 원 증정</span>
            </div>
          </div>
        </div>

        <!-- Ticket & Best Score Stats -->
        <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px; margin-bottom: 20px;">
          <div style="background: var(--primary-light); padding: 12px; border-radius: 16px; text-align: center;">
            <div style="font-size: 12px; color: var(--primary); font-weight: 700;">내 잔여 게임권</div>
            <div style="font-size: 20px; font-weight: 900; color: var(--primary);">무제한 ♾️</div>
          </div>
          <div style="background: var(--secondary-light); padding: 12px; border-radius: 16px; text-align: center;">
            <div style="font-size: 12px; color: #6200EE; font-weight: 700;">내 최고 점수</div>
            <div style="font-size: 20px; font-weight: 900; color: #6200EE;">${bestScore}점</div>
          </div>
        </div>

        <!-- Start Dino Jump -->
        <div>
          <button id="btn-start-jump" class="btn btn-primary" style="font-size: 15px; width: 100%; height: 52px; background: #1967D2; box-shadow: 0 4px 14px rgba(25, 103, 210, 0.25); border-radius: 14px; border: none; cursor: pointer; color: #FFF; font-weight: 700;">
            <span>공룡 점프 시작</span>
            <span style="font-size: 14px; margin-left: 4px;">➔</span>
          </button>
        </div>

        <button id="btn-how-to-play" class="btn btn-outline btn-sm" style="margin-top: 14px; border-color: rgba(25, 103, 210, 0.3); font-size: 13px;">
          <span>🕹️ 조작 방법 & 규칙 보기</span>
        </button>
      </div>

      <!-- Quick Prize Showcase Card -->
      <div class="card" style="padding: 16px 20px;">
        <div class="card-title" style="font-size: 15px; justify-content: space-between;">
          <span>🎁 참여 리워드 안내</span>
          <span class="sticker-badge badge-blue">주 1위 및 완주자 리워드</span>
        </div>
        <div style="display: flex; gap: 12px; overflow-x: auto; padding: 6px 0;">
          <div style="flex: 0 0 94px; text-align: center; background: #F8FAFF; padding: 10px 6px; border-radius: 14px; border: 1px solid #D2E3FC;">
            <div style="font-size: 24px;">💳</div>
            <div style="font-size: 11px; font-weight: 700; color: #1967D2;">CJ 1만원권</div>
            <div style="font-size: 9.5px; color: #5F6368;">주간 1위 증정</div>
          </div>
          <div style="flex: 0 0 90px; text-align: center; background: #F8F9FA; padding: 10px 6px; border-radius: 14px; border: 1px solid #E8EAED;">
            <div style="font-size: 24px;">☕</div>
            <div style="font-size: 11px; font-weight: 700; color: #3C4043;">메가커피</div>
            <div style="font-size: 9.5px; color: #5F6368;">즉석 복권 추첨</div>
          </div>
          <div style="flex: 0 0 90px; text-align: center; background: #F8F9FA; padding: 10px 6px; border-radius: 14px; border: 1px solid #E8EAED;">
            <div style="font-size: 24px;">🏪</div>
            <div style="font-size: 11px; font-weight: 700; color: #3C4043;">GS25 상품권</div>
            <div style="font-size: 9.5px; color: #5F6368;">즉석 복권 추첨</div>
          </div>
          <div style="flex: 0 0 90px; text-align: center; background: #F8F9FA; padding: 10px 6px; border-radius: 14px; border: 1px solid #E8EAED;">
            <div style="font-size: 24px;">🛵</div>
            <div style="font-size: 11px; font-weight: 700; color: #3C4043;">배민 1만원권</div>
            <div style="font-size: 9.5px; color: #5F6368;">즉석 복권 추첨</div>
          </div>
        </div>
      </div>
    `;

    // Event Listeners
    container.querySelector('#btn-start-jump').onclick = () => {
      const hasSeenGuide = localStorage.getItem('gemini_dino_guide_seen');
      if (!hasSeenGuide) {
        this.showGuideModal(router);
      } else {
        router.navigate('game');
      }
    };

    container.querySelector('#btn-how-to-play').onclick = () => {
      this.showGuideModal(router, false);
    };
  },

  showGuideModal(router, autoStart = true) {
    ui.showModal({
      title: '🕹️ 10초 스피드 조작 가이드',
      content: `
        <div style="display: flex; flex-direction: column; gap: 10px; font-size: 14px; text-align: left;">
          <div>👆 <strong>모바일</strong>: 화면 어디든 탭하거나 하단 [JUMP] 버튼을 누르세요.</div>
          <div>⌨️ <strong>PC</strong>: [Space] 또는 [↑] 방향키로 점프합니다.</div>
          <div>⚡ <strong>난이도</strong>: 1단계부터 6단계까지 자동으로 속도가 빨라집니다.</div>
          <div>🎁 <strong>보상</strong>: 한 번이라도 부딪혀 끝나면 <strong>복주머니 3개 중 1개</strong>를 골라 즉석 복권을 긁을 수 있어요!</div>
        </div>
      `,
      confirmText: autoStart ? '준비 완료! 게임 시작' : '확인',
      onConfirm: () => {
        localStorage.setItem('gemini_dino_guide_seen', 'true');
        if (autoStart) router.navigate('game');
      },
      cancelText: autoStart ? '취소' : null
    });
  }
};
