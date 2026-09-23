/**
 * S11 Referral & Invite View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const InviteView = {
  async render(container, router) {
    const bestScore = router.state.bestScore || 0;
    const participant = api.participant || {};

    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <!-- Header Card -->
        <div class="card" style="padding: 20px;">
          <span class="sticker-badge badge-blue">무제한 확산 루프</span>
          <h2 style="font-size: 20px; font-weight: 900; margin-top: 4px;">친구 초대하고 게임권 받기</h2>
          <p style="font-size: 13px; color: var(--text-sub); margin-top: 4px;">
            친구가 내 링크로 들어와 <strong>첫 게임을 완료(유효 충돌)</strong>하면<br>
            초대자에게 <strong>게임권 +1장</strong>이 즉시 충전됩니다!
          </p>
        </div>

        <!-- Share Preview Card (Canvas/Visual Card) -->
        <div class="card" style="background: linear-gradient(135deg, #1967D2 0%, #4285F4 100%); color: #FFF; padding: 24px 20px; text-align: center; position: relative; overflow: hidden;">
          <div style="position: absolute; right: -15px; bottom: -15px; opacity: 0.15; font-size: 120px; line-height: 1;">🦖</div>
          
          <div style="font-size: 12px; font-weight: 700; opacity: 0.9; margin-bottom: 8px;">
            #TeamGemini 공룡 점프 챌린지 2026
          </div>

          <div style="font-size: 24px; font-weight: 900; margin-bottom: 4px; line-height: 1.3;">
            “나 공룡 점프 ${bestScore}점!<br>내 기록 넘을 수 있어? 🔥”
          </div>

          <div style="font-size: 13px; opacity: 0.85; margin-bottom: 20px;">
            도전자: ${participant.nickname || '익명 러너'}
          </div>

          <!-- Share Buttons -->
          <div style="display: flex; flex-direction: column; gap: 8px;">
            <button id="btn-share-native" class="btn btn-primary" style="background: #FFF; color: var(--primary); font-weight: 900;">
              <span>📲 친구에게 도전장 보내기 (공유)</span>
            </button>
            <button id="btn-copy-link" class="btn btn-outline" style="border-color: rgba(255,255,255,0.6); color: #FFF;">
              <span>🔗 초대 링크 복사하기</span>
            </button>
          </div>
        </div>

        <!-- Referral Stats Card -->
        <div class="card" style="padding: 20px;">
          <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 14px;">내 초대 현황</h3>
          <div id="referral-stats-grid" style="display: grid; grid-template-columns: 1fr 1fr; gap: 12px;">
            <div style="background: #F8FAFF; padding: 14px; border-radius: 14px; text-align: center;">
              <div style="font-size: 12px; color: var(--text-sub); font-weight: 600;">초대 완료 친구</div>
              <div id="ref-qualified-count" style="font-size: 22px; font-weight: 900; color: var(--primary); margin-top: 4px;">- 명</div>
            </div>
            <div style="background: #F8FAFF; padding: 14px; border-radius: 14px; text-align: center;">
              <div style="font-size: 12px; color: var(--text-sub); font-weight: 600;">오늘 획득 게임권</div>
              <div id="ref-daily-earned" style="font-size: 22px; font-weight: 900; color: #34A853; margin-top: 4px;">- / 3장</div>
            </div>
          </div>
          <div style="font-size: 11px; color: var(--text-sub); margin-top: 10px; line-height: 1.4;">
            * 하루 최대 3장, 행사 기간 동안 최대 10장까지 추천 보상을 받을 수 있습니다.
          </div>
        </div>
      </div>
    `;

    // Fetch live referral stats
    try {
      const data = await api.getReferralInfo();
      const summary = data.summary || {};
      container.querySelector('#ref-qualified-count').textContent = `${summary.qualified_count || 0}명`;
      container.querySelector('#ref-daily-earned').textContent = `${summary.daily_earned || 0} / 3장`;

      const inviteUrl = `${window.location.origin}${data.invite_url}`;

      const shareText = `나 공룡 점프 ${bestScore}점 달성! 내 기록 넘을 수 있어? 🦖\n지금 도전하고 100% 즉석 경품 복주머니 열어보세요!`;

      // Native Share Sheet
      container.querySelector('#btn-share-native').onclick = async () => {
        if (navigator.share) {
          try {
            await navigator.share({
              title: 'Team Gemini 공룡 점프 챌린지',
              text: shareText,
              url: inviteUrl
            });
            ui.showToast('공유 창이 열렸습니다.');
          } catch (e) {
            // canceled
          }
        } else {
          // Fallback to clipboard
          navigator.clipboard.writeText(inviteUrl).then(() => {
            ui.showToast('초대 링크가 복사되었습니다!');
          });
        }
      };

      // Copy Link Button
      container.querySelector('#btn-copy-link').onclick = () => {
        navigator.clipboard.writeText(inviteUrl).then(() => {
          ui.showToast('초대 링크가 클립보드에 복사되었습니다!');
        }).catch(() => {
          ui.showToast(`초대 링크: ${inviteUrl}`);
        });
      };

    } catch (err) {
      ui.showToast('추천 정보를 불러오지 못했습니다.');
    }
  }
};
