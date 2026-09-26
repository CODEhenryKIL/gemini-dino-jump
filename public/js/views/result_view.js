import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { prepareResultReferralShare } from '../referral_share.js';

const resultGapRequests = new WeakMap();
const contactForms = new WeakMap();

export const ResultView = {
  render(container, router, renderToken) {
    resultGapRequests.set(container, Symbol('result-render'));
    const result = router.state.lastResult;
    if (!result) { router.navigate('home'); return; }
    container.innerHTML = `
      <section class="card result-card">
        <div class="home-event-badges"><span class="home-event-badge home-event-badge-team">#TeamGemini</span><span class="home-event-badge home-event-badge-campus">2026 캠퍼스 챌린지</span></div>
        <h1>게임 종료</h1>
        <div class="score-panel"><small>이번 판</small><strong id="result-score"></strong><div><span id="result-best"></span><span id="result-rank"></span></div></div>
        <div class="profile-row"><div><small>랭킹 닉네임</small><strong id="result-nickname"></strong></div><button id="btn-edit-nick" class="btn btn-secondary btn-sm">수정</button></div>
        <p id="result-top3-gap" class="result-gap" role="status"></p>
        <button id="btn-go-pouch" class="btn btn-primary">복주머니 확인하기</button>
        <div id="top3-request"></div>
        <div class="result-retry">
          <button id="btn-share-record" class="btn btn-share-retry" aria-label="카카오톡으로 친구한테 공유하고 한 판 더 하기" disabled><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3C6.48 3 2 6.45 2 10.7c0 2.76 1.89 5.18 4.72 6.54l-.93 3.38c-.08.29.25.52.5.36l3.97-2.61c.57.08 1.15.12 1.74.12 5.52 0 10-3.46 10-7.79C22 6.45 17.52 3 12 3Z"/></svg><span>친구한테 공유하고 한 판 더 하기</span></button>
          <p id="result-share-status" class="result-share-status" role="status"></p>
        </div>
      </section>`;
    ui.text(container.querySelector('#result-score'), `${result.score}점`);
    ui.text(container.querySelector('#result-best'), `최고 ${result.bestScore}점`);
    ui.text(container.querySelector('#result-rank'), result.rank ? `현재 ${result.rank}위` : '순위 집계 중');
    const gapNode = container.querySelector('#result-top3-gap');
    if (gapNode) this.renderGap(gapNode, result);
    ui.text(container.querySelector('#result-nickname'), router.state.participant?.nickname || '익명 러너');
    container.querySelector('#btn-go-pouch').onclick = () => {
      analytics.track('draw_cta_clicked', { source: 'result', draw_status: router.state.draw?.status || 'LOCKED' });
      router.navigate('draw');
    };
    this.prepareShare(container, router, renderToken);
    container.querySelector('#btn-edit-nick').onclick = () => this.nicknameModal(router, renderToken);
    this.updateState(container, router, renderToken);
    if (result.top3_gap == null && typeof api !== 'undefined' && typeof api.getLeaderboard === 'function') {
      this.loadTop3Gap(container, router, renderToken, result);
    }
  },

  async prepareShare(container, router, renderToken) {
    const button = container.querySelector('#btn-share-record');
    const status = container.querySelector('#result-share-status');
    const isCurrent = () => !router.isCurrent || router.isCurrent(renderToken);
    button.disabled = true;
    if (status) ui.text(status, '초대 링크 준비 중…');
    try {
      const prepared = await prepareResultReferralShare(router);
      if (!isCurrent()) return;
      button.disabled = false;
      if (status) ui.text(status, prepared.mode === 'native' ? '' : prepared.mode === 'copy' ? '초대 링크를 복사해 카카오톡으로 보낼 수 있어요.' : '친구가 방문하면 재도전권이 쌓여요.');
      button.onclick = () => { if (isCurrent()) return prepared.share(); };
    } catch (_) {
      if (!isCurrent()) return;
      button.disabled = false;
      if (status) ui.text(status, '초대 링크를 불러오지 못했어요. 버튼을 눌러 다시 준비해 주세요.');
      button.onclick = () => { if (isCurrent()) return this.prepareShare(container, router, renderToken); };
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
      if (currentGapNode) this.renderGap(currentGapNode, result);
      this.updateState(container, router, renderToken);
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
        return Number.isFinite(points) && points > 0 ? this.retryGapCopy(points) : 'TOP3 기준을 계산하는 중이에요.';
      }
      return 'TOP3 기준을 계산하는 중이에요.';
    }
    if (result.rank && result.rank <= 3) return `현재 ${result.rank}위로 TOP3예요.\n최종 경품 지급 순위는 이벤트 종료 시점에 확정돼요.`;
    const points = Number(gap);
    if (Number.isFinite(points) && points > 0) return this.retryGapCopy(points);
    if (points === 0) return '현재 3위 점수와 동점이에요. 최종 동점 수상 기준은 이벤트 종료 시점에 확정돼요.';
    return 'TOP3 기준을 계산하는 중이에요.';
  },

  renderGap(node, result) {
    ui.text(node, this.top3GapMessage(result));
    node.classList?.toggle('is-chasing', result.top3_gap?.status === 'CHASING' && Number(result.top3_gap.score_needed) > 0);
  },

  retryGapCopy(points) {
    // Current game rules award 10 time points per second; coins and revivals also affect ranking.
    return `TOP3까지 약 ${Math.ceil(points / 10)}초만 더!`;
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
    const result = router.state?.lastResult || {};
    const rank = result.top3_gap?.rank ?? result.rank;
    const eligible = profile?.eligible !== false && result.top3_gap?.status !== 'CHASING' && (Number.isInteger(rank) ? rank >= 1 && rank <= 3 : profile?.eligible === true);
    const previous = contactForms.get(target);
    if (previous?.router === router && previous.status === profile?.status && previous.version === profile?.game_version && previous.eligible === eligible) return;
    contactForms.set(target, { router, status: profile?.status, version: profile?.game_version, eligible });
    target.replaceChildren();
    target.hidden = !eligible || !['REQUESTED', 'SUBMITTED'].includes(profile?.status);
    if (target.hidden) return;
    const card = document.createElement('section');
    card.className = 'result-contact';
    const title = document.createElement('strong');
    title.textContent = profile.status === 'SUBMITTED' ? 'TOP3 정보 접수 완료' : '수령 정보를 등록해 주세요';
    card.appendChild(title);
    if (profile.status === 'REQUESTED') {
      const intro = document.createElement('p'); intro.className = 'result-contact-intro';
      intro.textContent = 'TOP3에 진입한 참가자에게는 경품 안내를 위해 수령 정보를 미리 받고 있어요.';
      card.append(intro, this.top3Form(router));
    } else {
      const text = document.createElement('p'); text.textContent = '수령함에서 접수 상태를 확인할 수 있어요.';
      card.appendChild(text);
    }
    target.appendChild(card);
  },

  top3Form(router, renderToken = router.renderToken) {
    const form = document.createElement('form'); form.className = 'stack-form';
    const fields = [
      ui.formField('이름', 'text', 'name', { maxlength: 80, autocomplete: 'name', required: true }),
      ui.formField('연락처', 'tel', 'contact', { maxlength: 32, autocomplete: 'tel', required: true }),
      ui.formField('학교', 'text', 'school', { maxlength: 120, autocomplete: 'organization', required: true }),
    ];
    fields.forEach(({ label }) => form.appendChild(label));
    const consent = document.createElement('label'); consent.className = 'consent-row';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.required = true;
    const consentText = document.createElement('span'); consentText.textContent = '경품 안내와 수령 확인을 위한\n이름·연락처·학교 수집에 동의합니다.';
    consent.append(checkbox, consentText); form.appendChild(consent);
    const accuracyNote = document.createElement('p'); accuracyNote.className = 'result-contact-accuracy';
    accuracyNote.textContent = '정보 오기재로 인한 연락 불가 및 경품 미수령의 책임은\n본인에게 있습니다. 입력 내용을 꼭 확인해 주세요.';
    form.appendChild(accuracyNote);
    const feedback = document.createElement('p'); feedback.className = 'result-form-status'; feedback.setAttribute('role', 'status');
    const button = document.createElement('button'); button.type = 'submit'; button.className = 'btn btn-secondary'; button.textContent = '수령 정보 등록';
    form.append(feedback, button);
    let started = false;
    let pending = false;
    form.onfocusin = () => {
      if (started) return;
      started = true;
      analytics.track('top3_profile_started');
    };
    form.onsubmit = async (event) => {
      event.preventDefault();
      if (pending || (renderToken != null && router.isCurrent && !router.isCurrent(renderToken))) return;
      if (!checkbox.checked || fields.some(({ input }) => !input.value.trim())) {
        feedback.textContent = '모든 항목을 입력하고 수집에 동의해 주세요.';
        return;
      }
      form.onfocusin();
      pending = true; button.disabled = true; button.textContent = '등록 중…'; feedback.textContent = '';
      try {
        const submitted = await api.submitTop3Profile({ ...Object.fromEntries(fields.map(({ input }) => [input.name, input.value.trim()])), consent: true, notice_version: 'top3-contact-v1' });
        const previousProfile = router.state.top3Profile || {};
        router.state.top3Profile = { ...previousProfile, required: false, status: submitted.status || 'SUBMITTED', submitted_at: submitted.submitted_at || previousProfile.submitted_at };
        if (router.state.lastResult) router.state.lastResult.top3Profile = router.state.top3Profile;
        router.announceStateChange?.();
        analytics.track('top3_profile_submitted');
        if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return;
        // Replace only this form, keeping score/share controls and scroll position intact.
        form.replaceChildren();
        const done = document.createElement('p'); done.className = 'result-form-status'; done.setAttribute('role', 'status'); done.textContent = '정보 접수 완료';
        form.appendChild(done);
      } catch (error) {
        if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return;
        feedback.textContent = error.message || '등록하지 못했어요. 다시 시도해 주세요.';
      } finally {
        pending = false; button.disabled = false; button.textContent = '수령 정보 등록';
      }
    };
    return form;
  },
};
