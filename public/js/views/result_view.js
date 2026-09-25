import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

export const ResultView = {
  render(container, router) {
    const result = router.state.lastResult;
    if (!result) { router.navigate('home'); return; }
    container.innerHTML = `
      <section class="card result-card">
        <span class="sticker-badge badge-green">기록 검증 완료</span>
        <h1>게임 종료</h1>
        <div class="score-panel"><small>이번 판</small><strong id="result-score"></strong><div><span id="result-best"></span><span id="result-rank"></span></div></div>
        <div class="profile-row"><div><small>랭킹 닉네임</small><strong id="result-nickname"></strong></div><button id="btn-edit-nick" class="btn btn-secondary btn-sm">수정</button></div>
        <div id="top3-request"></div>
        <button id="btn-go-pouch" class="btn btn-primary">복주머니 확인하기</button>
        <button id="btn-share-record" class="btn btn-outline btn-sm">기록 공유하고 친구 초대하기</button>
      </section>`;
    ui.text(container.querySelector('#result-score'), `${result.score}점`);
    ui.text(container.querySelector('#result-best'), `최고 ${result.bestScore}점`);
    ui.text(container.querySelector('#result-rank'), result.rank ? `현재 ${result.rank}위` : '순위 집계 중');
    ui.text(container.querySelector('#result-nickname'), router.state.participant?.nickname || '익명 러너');
    container.querySelector('#btn-go-pouch').onclick = () => router.navigate('draw');
    container.querySelector('#btn-share-record').onclick = () => { router.shareContext = 'prize_share'; router.navigate('invite'); };
    container.querySelector('#btn-edit-nick').onclick = () => this.nicknameModal(router);
    const profile = router.state.top3Profile || result.top3Profile;
    if (profile?.required || profile?.status === 'REQUESTED') this.renderTop3Request(container.querySelector('#top3-request'), router, profile);
  },

  nicknameModal(router) {
    const field = ui.formField('닉네임', 'text', 'nickname', { maxlength: 12, autocomplete: 'nickname' });
    field.input.value = router.state.participant?.nickname || '';
    ui.showModal({
      title: '랭킹 닉네임 변경', content: field.label, confirmText: '저장', cancelText: '취소',
      onConfirm: async () => {
        const nickname = field.input.value.trim();
        if (nickname.length < 2) { ui.showToast('닉네임은 2자 이상 입력해 주세요.'); return false; }
        try {
          const participant = await api.updateProfile({ nickname });
          router.state.participant = participant.participant || participant;
          api.participant = router.state.participant;
          router.navigate('result');
        } catch (error) { ui.showToast(error.message); return false; }
      },
    });
  },

  renderTop3Request(target, router, profile) {
    const card = document.createElement('section');
    card.className = 'inline-notice';
    const title = document.createElement('strong'); title.textContent = '잠정 TOP3 수령 정보를 등록해 주세요';
    const text = document.createElement('p'); text.textContent = '현재 순위가 내려가더라도 이 요청 상태는 보존됩니다. 최종 수상 확정은 운영 마감 뒤 별도입니다.';
    const button = document.createElement('button'); button.className = 'btn btn-secondary btn-sm';
    button.textContent = profile.status === 'SUBMITTED' ? '정보 접수 완료' : '합성 테스트 정보 입력';
    button.disabled = profile.status === 'SUBMITTED';
    button.onclick = () => this.top3Modal(router);
    card.append(title, text, button); target.appendChild(card);
  },

  top3Modal(router) {
    analytics.track('top3_profile_started');
    const form = document.createElement('form'); form.className = 'stack-form';
    const fields = [
      ui.formField('이름 (테스트 정보)', 'text', 'name', { maxlength: 30, autocomplete: 'name' }),
      ui.formField('연락처 (테스트 정보)', 'text', 'contact', { maxlength: 60, autocomplete: 'off' }),
      ui.formField('학교 (테스트 정보)', 'text', 'school', { maxlength: 60, autocomplete: 'organization' }),
    ];
    fields[0].input.value = 'TEST_사용자';
    fields[1].input.value = '01000000000';
    fields[2].input.value = 'TEST_학교';
    fields.forEach(({ label }) => form.appendChild(label));
    const consent = document.createElement('label'); consent.className = 'consent-row';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
    const consentText = document.createElement('span'); consentText.textContent = 'Preview에서는 실제 개인정보가 아닌 합성 테스트 정보만 입력합니다.';
    consent.append(checkbox, consentText); form.appendChild(consent);
    ui.showModal({
      title: '잠정 TOP3 정보 접수', content: form, confirmText: '접수', cancelText: '취소',
      onConfirm: async () => {
        if (!checkbox.checked || fields.some(({ input }) => !input.value.trim())) { ui.showToast('모든 항목과 테스트 정보 확인을 완료해 주세요.'); return false; }
        try {
          const submitted = await api.submitTop3Profile(Object.fromEntries(fields.map(({ input }) => [input.name, input.value.trim()])));
          analytics.track('top3_profile_submitted');
          router.state.top3Profile = { required: true, status: submitted.status || 'SUBMITTED' };
          if (router.state.lastResult) router.state.lastResult.top3Profile = router.state.top3Profile;
          router.navigate('result');
        } catch (error) { ui.showToast(error.message); return false; }
      },
    });
  },
};
