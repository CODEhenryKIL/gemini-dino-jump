import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

const resultGapRequests = new WeakMap();

export const ResultView = {
  render(container, router, renderToken) {
    resultGapRequests.set(container, Symbol('result-render'));
    const result = router.state.lastResult;
    if (!result) { router.navigate('home'); return; }
    container.innerHTML = `
      <section class="card result-card">
        <span class="sticker-badge badge-green">기록 검증 완료</span>
        <h1>게임 종료</h1>
        <div class="score-panel"><small>이번 판</small><strong id="result-score"></strong><div><span id="result-best"></span><span id="result-rank"></span></div></div>
        <p id="result-top3-gap" class="result-gap" role="status"></p>
        <div class="profile-row"><div><small>랭킹 닉네임</small><strong id="result-nickname"></strong></div><button id="btn-edit-nick" class="btn btn-secondary btn-sm">수정</button></div>
        <div id="top3-request"></div>
        <button id="btn-go-pouch" class="btn btn-primary">복주머니 확인하기</button>
        <button id="btn-share-record" class="btn btn-outline btn-sm">기록 공유하고 친구 초대하기</button>
      </section>`;
    ui.text(container.querySelector('#result-score'), `${result.score}점`);
    ui.text(container.querySelector('#result-best'), `최고 ${result.bestScore}점`);
    ui.text(container.querySelector('#result-rank'), result.rank ? `현재 ${result.rank}위` : '순위 집계 중');
    const gapNode = container.querySelector('#result-top3-gap');
    if (gapNode) ui.text(gapNode, this.top3GapMessage(result));
    ui.text(container.querySelector('#result-nickname'), router.state.participant?.nickname || '익명 러너');
    container.querySelector('#btn-go-pouch').onclick = () => {
      analytics.track('draw_cta_clicked', { source: 'result', draw_status: router.state.draw?.status || 'LOCKED' });
      router.navigate('draw');
    };
    container.querySelector('#btn-share-record').onclick = () => { router.shareContext = 'record_share'; router.navigate('invite'); };
    container.querySelector('#btn-edit-nick').onclick = () => this.nicknameModal(router, renderToken);
    this.updateState(container, router, renderToken);
    if (result.top3_gap == null && typeof api !== 'undefined' && typeof api.getLeaderboard === 'function') {
      this.loadTop3Gap(container, router, renderToken, result);
    }
  },

  async loadTop3Gap(container, router, renderToken, result) {
    const request = Symbol('result-top3-gap');
    resultGapRequests.set(container, request);
    const gapNode = container.querySelector('#result-top3-gap');
    if (gapNode) ui.text(gapNode, 'TOP3 기준을 계산하는 중이에요.');
    try {
      const data = await api.getLeaderboard();
      if ((router.isCurrent && !router.isCurrent(renderToken)) || resultGapRequests.get(container) !== request) return;
      if (data.me?.rank != null) {
        result.rank = data.me.rank;
        const rankNode = container.querySelector('#result-rank');
        if (rankNode) ui.text(rankNode, `현재 ${result.rank}위`);
      }
      result.top3_gap = data.top3_gap ?? data.me?.top3_gap ?? null;
      const currentGapNode = container.querySelector('#result-top3-gap');
      if (currentGapNode) ui.text(currentGapNode, this.top3GapMessage(result));
    } catch (_error) {
      if ((router.isCurrent && !router.isCurrent(renderToken)) || resultGapRequests.get(container) !== request) return;
      const currentGapNode = container.querySelector('#result-top3-gap');
      if (!currentGapNode) return;
      currentGapNode.replaceChildren();
      const message = document.createElement('span'); message.textContent = 'TOP3 기준을 불러오지 못했어요. 게임 결과와 복주머니 진행에는 영향이 없어요.';
      const retry = document.createElement('button'); retry.className = 'btn btn-secondary btn-sm'; retry.textContent = 'TOP3 기준 다시 불러오기';
      retry.onclick = () => {
        if ((router.isCurrent && !router.isCurrent(renderToken)) || retry.disabled) return;
        retry.disabled = true;
        return this.loadTop3Gap(container, router, renderToken, result);
      };
      currentGapNode.append(message, retry);
    }
  },

  updateState(container, router, renderToken) {
    if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return;
    const target = container.querySelector('#top3-request');
    if (target) this.renderTop3Request(target, router, router.state.top3Profile || router.state.lastResult?.top3Profile);
  },

  top3GapMessage(result) {
    const gap = result.top3_gap;
    if (gap == null) return result.rank ? 'TOP3 기준을 계산하는 중이에요.' : '아직 비교할 내 기록이 없어요.';
    if (typeof gap === 'object') {
      const status = String(gap.status || '').toUpperCase();
      if (status === 'NO_SCORE') return '검증된 점수가 생기면 TOP3와의 차이를 보여드려요.';
      if (status === 'TOO_FEW') return `현재 참가자는 ${Number(gap.participant_count) || 0}명이에요. 3위 점수가 생기면 차이를 보여드려요.`;
      if (status === 'IN_TOP3') {
        return `현재 ${Number(gap.rank) || Number(result.rank) || 3}위로 TOP3예요.\n최종 경품 지급 순위는 이벤트 종료 시점에 확정돼요.`;
      }
      if (status === 'CHASING') {
        const points = Number(gap.score_needed);
        if (gap.tied && points === 0) return '현재 3위 점수와 동점이에요. 최종 동점 수상 기준은 이벤트 종료 시점에 확정돼요.';
        return Number.isFinite(points) && points > 0 ? `현재 3위까지 ${points}점이 더 필요해요.${gap.tied ? ' 내 점수와 동점인 참가자가 있어요.' : ''}` : 'TOP3 기준을 계산하는 중이에요.';
      }
      return 'TOP3 기준을 계산하는 중이에요.';
    }
    if (result.rank && result.rank <= 3) return `현재 ${result.rank}위로 TOP3예요.\n최종 경품 지급 순위는 이벤트 종료 시점에 확정돼요.`;
    const points = Number(gap);
    if (Number.isFinite(points) && points > 0) return `현재 3위까지 ${points}점 차이예요.`;
    if (points === 0) return '현재 3위 점수와 동점이에요. 최종 동점 수상 기준은 이벤트 종료 시점에 확정돼요.';
    return 'TOP3 기준을 계산하는 중이에요.';
  },

  nicknameModal(router, renderToken) {
    const field = ui.formField('닉네임', 'text', 'nickname', { maxlength: 12, autocomplete: 'nickname' });
    field.input.value = router.state.participant?.nickname || '';
    ui.showModal({
      title: '랭킹 닉네임 변경', content: field.label, confirmText: '저장', cancelText: '취소',
      onConfirm: async () => {
        const nickname = field.input.value.trim();
        if (nickname.length < 2) { ui.showToast('닉네임은 2자 이상 입력해 주세요.'); return false; }
        try {
          const participant = await api.updateProfile({ nickname });
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          router.state.participant = participant.participant || participant;
          api.participant = router.state.participant;
          router.navigate('result');
        } catch (error) {
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          ui.showToast(error.message); return false;
        }
      },
    });
  },

  renderTop3Request(target, router, profile) {
    target.replaceChildren();
    target.hidden = !['REQUESTED', 'SUBMITTED'].includes(profile?.status);
    if (target.hidden) return;
    const card = document.createElement('section');
    card.className = 'inline-notice';
    const copy = this.top3RequestCopy(profile, router.config);
    const title = document.createElement('strong'); title.textContent = copy.title;
    const text = document.createElement('p'); text.textContent = copy.description;
    const button = document.createElement('button'); button.className = 'btn btn-secondary btn-sm';
    button.textContent = profile.status === 'SUBMITTED' ? '정보 접수 완료' : '합성 테스트 정보 입력';
    button.disabled = profile.status === 'SUBMITTED';
    button.onclick = () => this.top3Modal(router, router.renderToken);
    card.append(title, text, button); target.appendChild(card);
  },

  top3RequestCopy(profile, config) {
    if (profile?.status === 'SUBMITTED') {
      return {
        title: 'TOP3 정보 접수 완료',
        description: '이미 등록한 정보가 저장되어 있어 다시 입력하지 않아도 돼요. 수령함에서 접수 상태를 확인할 수 있어요. 최종 수상과 지급 여부는 이벤트 종료 후 운영팀이 확인해요.',
      };
    }
    const requestVersion = profile?.game_version;
    const currentVersion = config?.campaign?.game_version;
    if (requestVersion && currentVersion && requestVersion !== currentVersion) {
      return {
        title: '이전 게임 규칙에서 생성된 수령 정보 요청',
        description: `게임 규칙 ${requestVersion} 기록에서 생성된 요청이에요. 접수 요청은 유지되지만 현재 ${currentVersion} 규칙의 TOP3라는 뜻은 아니며, 최종 수상 확정은 운영 마감 뒤 별도예요.`,
      };
    }
    return {
      title: '잠정 TOP3 수령 정보를 등록해 주세요',
      description: '현재 순위가 내려가더라도 이 요청 상태는 보존됩니다. 최종 수상 확정은 운영 마감 뒤 별도입니다.',
    };
  },

  top3Modal(router, renderToken = router.renderToken) {
    const returnView = router.currentView === 'ranking' ? 'ranking' : 'result';
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
          const previousProfile = router.state.top3Profile || {};
          router.state.top3Profile = { ...previousProfile, required: false, status: submitted.status || 'SUBMITTED', submitted_at: submitted.submitted_at || previousProfile.submitted_at };
          if (router.state.lastResult) router.state.lastResult.top3Profile = router.state.top3Profile;
          router.announceStateChange?.();
          analytics.track('top3_profile_submitted');
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          await router.navigate(returnView, { replace: true });
        } catch (error) {
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          ui.showToast(error.message); return false;
        }
      },
    });
  },
};
