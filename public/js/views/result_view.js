/**
 * S04 Game Result View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const ResultView = {
  render(container, router) {
    const res = router.state.lastResult || { score: 0, bestScore: 0, rank: 1 };
    const participant = api.participant || {};

    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 28px 20px;">
        <div style="margin-bottom: 8px;">
          <span class="sticker-badge badge-green">✨ 기록 검증 완료</span>
        </div>

        <h2 style="font-size: 22px; font-weight: 900; margin-bottom: 16px;">
          게임 종료!
        </h2>

        <!-- Score Board -->
        <div style="background: #F8FAFF; border: 2px solid rgba(25, 103, 210, 0.12); border-radius: 20px; padding: 20px; margin-bottom: 20px;">
          <div style="font-size: 13px; color: var(--text-sub); font-weight: 700;">이번 판 기록</div>
          <div style="font-size: 42px; font-weight: 900; color: var(--primary); font-family: monospace; line-height: 1.1; margin: 4px 0;">
            ${res.score}점
          </div>

          <div style="display: flex; justify-content: space-around; margin-top: 16px; padding-top: 14px; border-top: 1px dashed rgba(0,0,0,0.1);">
            <div>
              <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">내 최고 점수</div>
              <div style="font-size: 18px; font-weight: 800; color: #6200EE;">${res.bestScore}점</div>
            </div>
            <div style="width: 1px; background: rgba(0,0,0,0.08);"></div>
            <div>
              <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">현재 순위</div>
              <div style="font-size: 18px; font-weight: 800; color: #EA4335;">${res.rank}위</div>
            </div>
          </div>
        </div>

        <!-- Nickname Setting Section -->
        <div style="display: flex; align-items: center; justify-content: space-between; background: #FFF; border: 1px solid rgba(0,0,0,0.08); padding: 10px 14px; border-radius: 14px; margin-bottom: 24px;">
          <div style="text-align: left;">
            <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">랭킹 닉네임</div>
            <div style="font-size: 14px; font-weight: 700;">${participant.nickname || '익명 러너'}</div>
          </div>
          <button id="btn-edit-nick" class="btn btn-secondary btn-sm" style="width: auto; padding: 6px 12px;">
            수정
          </button>
        </div>

        <!-- Action: Lucky Pouch S05 -->
        <button id="btn-go-pouch" class="btn btn-primary" style="font-size: 18px; height: 56px; margin-bottom: 10px; background: linear-gradient(135deg, #FBBC04 0%, #F29900 100%); color: #000; box-shadow: 0 6px 20px rgba(242, 153, 0, 0.3);">
          <span>🧧 복주머니 고르러 가기 (1회)</span>
        </button>

        <button id="btn-share-record" class="btn btn-outline btn-sm">
          <span>📤 내 기록 자랑하고 친구 초대하기</span>
        </button>
      </div>
    `;

    // Handlers
    container.querySelector('#btn-go-pouch').onclick = () => {
      router.navigate('draw');
    };

    container.querySelector('#btn-share-record').onclick = () => {
      router.navigate('invite');
    };

    container.querySelector('#btn-edit-nick').onclick = () => {
      this.showNicknameModal(participant, router);
    };
  },

  showNicknameModal(participant, router) {
    const inputHtml = `
      <input id="modal-nick-input" type="text" maxlength="12" value="${participant.nickname || ''}" 
             placeholder="2~12자 닉네임 입력"
             style="width: 100%; padding: 12px; font-size: 16px; border: 1.5px solid var(--primary); border-radius: 12px; outline: none; margin-top: 8px;">
      <div style="font-size: 11px; color: var(--text-sub); margin-top: 6px;">* 연락처나 부적절한 단어는 사용할 수 없습니다.</div>
    `;

    ui.showModal({
      title: '닉네임 변경',
      content: inputHtml,
      confirmText: '변경 완료',
      onConfirm: async () => {
        const input = document.getElementById('modal-nick-input');
        const newNick = input ? input.value.trim() : '';
        if (newNick.length < 2 || newNick.length > 12) {
          ui.showToast('2자 이상 12자 이하로 입력해주세요.');
          return;
        }
        try {
          await api.updateProfile({ nickname: newNick });
          if (api.participant) api.participant.nickname = newNick;
          ui.showToast('닉네임이 변경되었습니다.');
          router.navigate('result');
        } catch (err) {
          ui.showToast(err.message || '닉네임 변경에 실패했습니다.');
        }
      },
      cancelText: '취소'
    });
  }
};
