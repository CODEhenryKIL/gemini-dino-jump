/**
 * S04 Game Result View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const ResultView = {
  abortController: null,
  render(container, router, epoch) {
    this.cleanup(); this.abortController = new AbortController();
    const res = router.state.lastResult || { score: 0, bestScore: 0, rank: 1 };
    const participant = api.participant || {};

    container.innerHTML = `
      <div class="card" style="text-align: center; padding: 28px 20px;">
        <div style="margin-bottom: 8px;">
          <span class="sticker-badge ${res.eligibleForDraw ? 'badge-green' : 'badge-red'}">${res.eligibleForDraw ? '✨ 기록 검증 완료' : '⚠️ 기록 검증 제외'}</span>
        </div>

        <h2 style="font-size: 22px; font-weight: 900; margin-bottom: 16px;">
          게임 종료!
        </h2>

        <!-- Score Board -->
        <div style="background: #F8FAFF; border: 2px solid rgba(25, 103, 210, 0.12); border-radius: 20px; padding: 20px; margin-bottom: 20px;">
          <div style="font-size: 13px; color: var(--text-sub); font-weight: 700;">이번 판 기록</div>
          <div style="font-size: 42px; font-weight: 900; color: var(--primary); font-family: monospace; line-height: 1.1; margin: 4px 0;">
            <span id="result-score"></span>
          </div>

          <div style="display: flex; justify-content: space-around; margin-top: 16px; padding-top: 14px; border-top: 1px dashed rgba(0,0,0,0.1);">
            <div>
              <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">내 최고 점수</div>
              <div id="result-best" style="font-size: 18px; font-weight: 800; color: #6200EE;"></div>
            </div>
            <div style="width: 1px; background: rgba(0,0,0,0.08);"></div>
            <div>
              <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">현재 순위</div>
              <div id="result-rank" style="font-size: 18px; font-weight: 800; color: #EA4335;"></div>
            </div>
          </div>
        </div>

        <!-- Nickname Setting Section -->
        <div style="display: flex; align-items: center; justify-content: space-between; background: #FFF; border: 1px solid rgba(0,0,0,0.08); padding: 10px 14px; border-radius: 14px; margin-bottom: 24px;">
          <div style="text-align: left;">
            <div style="font-size: 11px; color: var(--text-sub); font-weight: 600;">랭킹 닉네임</div>
            <div id="result-nickname" style="font-size: 14px; font-weight: 700;"></div>
          </div>
          <button id="btn-edit-nick" class="btn btn-secondary btn-sm" style="width: auto; padding: 6px 12px;">
            수정
          </button>
        </div>

        <!-- Action: Lucky Pouch S05 -->
        <button id="btn-go-pouch" class="btn btn-primary" style="font-size: 18px; height: 56px; margin-bottom: 10px; background: linear-gradient(135deg, #FBBC04 0%, #F29900 100%); color: #000; box-shadow: 0 6px 20px rgba(242, 153, 0, 0.3);">
          <span>${res.eligibleForDraw ? '🧧 테스트 추첨 결과 확인하기' : '검증되지 않은 기록은 추첨할 수 없습니다'}</span>
        </button>

        <button id="btn-share-record" class="btn btn-outline btn-sm">
          <span>📤 내 기록 자랑하고 친구 초대하기</span>
        </button>
      </div>
    `;

    container.querySelector('#result-score').textContent = `${Number(res.score || 0)}점`;
    container.querySelector('#result-best').textContent = `${Number(res.bestScore || 0)}점`;
    container.querySelector('#result-rank').textContent = res.rank ? `${Number(res.rank)}위` : '순위 제외';
    container.querySelector('#result-nickname').textContent = participant.nickname || '익명 러너';
    const drawButton = container.querySelector('#btn-go-pouch');
    drawButton.disabled = !res.eligibleForDraw;

    // Handlers
    container.querySelector('#btn-go-pouch').onclick = () => {
      if (res.eligibleForDraw) router.navigate('draw');
    };

    container.querySelector('#btn-share-record').onclick = () => {
      router.navigate('invite');
    };

    container.querySelector('#btn-edit-nick').onclick = () => {
      this.showNicknameModal(participant, router, epoch);
    };
  },

  showNicknameModal(participant, router, epoch) {
    const wrapper = document.createElement('div');
    const input = document.createElement('input'); input.id = 'modal-nick-input'; input.type = 'text'; input.maxLength = 12; input.value = participant.nickname || ''; input.placeholder = '2~12자 닉네임 입력'; input.style.cssText = 'width:100%;padding:12px;font-size:16px;border:1.5px solid var(--primary);border-radius:12px;outline:none;margin-top:8px';
    const note = document.createElement('div'); note.textContent = '* 연락처나 부적절한 단어는 사용할 수 없습니다.'; note.style.cssText = 'font-size:11px;color:var(--text-sub);margin-top:6px'; wrapper.append(input,note);

    ui.showModal({
      title: '닉네임 변경',
      content: wrapper,
      confirmText: '변경 완료',
      onConfirm: async () => {
        const input = document.getElementById('modal-nick-input');
        const newNick = input ? input.value.trim() : '';
        if (newNick.length < 2 || newNick.length > 12) {
          ui.showToast('2자 이상 12자 이하로 입력해주세요.');
          return false;
        }
        try {
          await api.updateProfile({ nickname: newNick, is_public: api.participant?.is_public !== false }, { signal: this.abortController.signal });
          if (!router.isCurrent(epoch, 'result')) return false;
          if (api.participant) api.participant.nickname = newNick;
          api.setSession(api.participant);
          ui.showToast('닉네임이 변경되었습니다.');
          router.navigate('result');
        } catch (err) {
          if (err.name !== 'AbortError') ui.showToast(err.message || '닉네임 변경에 실패했습니다.');
          return false;
        }
      },
      cancelText: '취소'
    });
  },
  cleanup(){this.abortController?.abort();this.abortController=null;}
};
