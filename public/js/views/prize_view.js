import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { prepareResultReferralShare } from '../referral_share.js';

const STATUS_LABELS = {
  AWAITING_INFORMATION: '정보 입력 대기',
  INFORMATION_RECEIVED: '정보 접수', PENDING_REVIEW: '확인 대기', CONTACTED: '연락 완료',
  PAID: '지급 완료', ON_HOLD: '보류', INELIGIBLE: '부적격', NO_RESPONSE: '미응답', READY: '정보 입력 대기',
};
const STATUS_HELP = {
  AWAITING_INFORMATION: '수령 정보를 접수하면 운영팀이 대학생 대상 여부를 확인해요.', READY: '수령 정보를 접수하면 운영팀이 대학생 대상 여부를 확인해요.',
  INFORMATION_RECEIVED: '정보가 접수됐어요. 아직 지급 완료 상태는 아니에요.', PENDING_REVIEW: '운영팀이 접수 내용을 확인하고 있어요.',
  CONTACTED: '운영팀의 연락이 완료됐어요. 실제 지급 완료 상태는 별도로 표시돼요.', PAID: '운영팀에서 지급 완료로 처리했어요.',
  ON_HOLD: '확인할 내용이 있어 잠시 보류 중이에요.', INELIGIBLE: '운영 확인 결과 경품 수령 대상이 아니에요.', NO_RESPONSE: '운영팀 연락에 대한 응답을 기다리고 있어요.',
};

export const PrizeView = {
  async render(container, router, renderToken, { keepContent = false } = {}) {
    const request = this.loadRequest = Symbol('claims');
    if (!keepContent) container.innerHTML = '<section class="card empty-state"><p>수령 상태를 불러오는 중...</p></section>';
    try {
      const { claims = [] } = await api.getClaims();
      if (!router.isCurrent(renderToken) || this.loadRequest !== request) return;
      container.replaceChildren();
      const intro = document.createElement('section'); intro.className = 'card compact-card';
      const heading = document.createElement('h1'); heading.textContent = '내 수령함';
      intro.append(heading); container.appendChild(intro);
      if (!claims.length) return this.renderEmpty(container, router);
      for (const claim of claims) container.appendChild(this.claimCard(claim, router, renderToken));
    } catch (error) {
      if (!router.isCurrent(renderToken) || this.loadRequest !== request) return;
      if (!keepContent) container.replaceChildren();
      container.querySelector?.('.claim-load-error')?.remove();
      const card = document.createElement('section'); card.className = 'card empty-state claim-load-error';
      card.setAttribute('role', 'status');
      const p = document.createElement('p'); p.textContent = error.message || '수령함을 불러오지 못했습니다.';
      const retry = document.createElement('button'); retry.className = 'btn btn-secondary btn-sm'; retry.textContent = '수령 상태 다시 불러오기';
      retry.onclick = () => {
        if (!router.isCurrent(renderToken) || retry.disabled) return;
        retry.disabled = true;
        return this.render(container, router, renderToken, { keepContent: true });
      };
      card.append(p, retry); container.appendChild(card);
    }
  },

  updateState(container, router, renderToken) {
    return this.render(container, router, renderToken, { keepContent: true });
  },

  renderEmpty(container, router) {
    const card = document.createElement('section'); card.className = 'card empty-state';
    const status = router.state?.draw?.status || 'LOCKED';
    const title = document.createElement('h2'); title.textContent = status === 'LOCKED' ? '복주머니가 아직 잠겨 있어요' : '접수할 경품이 아직 없어요';
    const detail = document.createElement('p');
    detail.textContent = status === 'LOCKED' ? '정상 검증된 게임을 한 번 완료하면 행사당 한 번 열 수 있어요.' : status === 'DRAWN' ? '이미 저장된 복주머니 결과를 다시 확인할 수 있어요.' : '첫 게임을 완료했으니 복주머니를 열 수 있어요.';
    const button = document.createElement('button'); button.className = 'btn btn-primary';
    button.textContent = status === 'LOCKED' ? '홈에서 게임 시작하기' : status === 'DRAWN' ? '내 복주머니 결과 보기' : '복주머니 열기';
    button.onclick = () => {
      const latest = router.state?.draw?.status || 'LOCKED';
      if (!['AVAILABLE', 'DRAWN'].includes(latest)) { router.navigate('home'); return; }
      analytics.track('draw_cta_clicked', { source: 'claims', draw_status: latest });
      router.navigate('draw');
    };
    card.append(title, button, detail); container.appendChild(card);
  },

  claimCard(claim, router, renderToken) {
    const claimType = claim.claim_type || claim.type || 'DRAW';
    const card = document.createElement('article'); card.className = 'card claim-card';
    const header = document.createElement('div'); header.className = 'claim-card-header';
    const name = document.createElement('h2'); name.textContent = claim.prize_name || (claimType === 'RANKING' ? 'TOP3 접수 내역' : '경품');
    const badge = document.createElement('span'); badge.className = 'sticker-badge badge-blue'; badge.textContent = claim.draft_saved && !claim.contact_submitted ? '공유 단계 대기' : STATUS_LABELS[claim.status] || claim.status;
    header.append(name, badge);
    const type = document.createElement('p'); type.textContent = claimType === 'RANKING' ? '랭킹 경품' : '복주머니 경품';
    const help = document.createElement('p'); help.className = 'claim-help'; help.textContent = STATUS_HELP[claim.status] || '운영팀 확인 상태를 표시하고 있어요.';
    if (claimType === 'RANKING' && !['PAID', 'INELIGIBLE'].includes(claim.status)) {
      help.textContent += ' TOP3 진입에 따른 정보 접수이며, 최종 수상은 이벤트 종료 시점 기준으로 결정돼요.';
    }
    card.append(header, type, help);
    if (!claim.contact_submitted && !['PAID', 'INELIGIBLE'].includes(claim.status)) {
      const button = document.createElement('button'); button.className = 'btn btn-primary btn-sm'; button.textContent = claim.draft_saved ? '친구 공유하고 접수 완료하기' : '수령 정보 입력';
      button.onclick = () => claim.draft_saved ? this.claimShareModal(claim, router, renderToken) : this.claimModal(claim, router, renderToken); card.appendChild(button);
    }
    if (claim.contact_submitted || ['INFORMATION_RECEIVED', 'PENDING_REVIEW', 'CONTACTED', 'PAID', 'ON_HOLD', 'NO_RESPONSE'].includes(claim.status)) {
      const benefit = document.createElement('a'); benefit.className = 'btn btn-secondary btn-sm'; benefit.href = '#benefit'; benefit.textContent = 'Gemini 혜택과 활용 가이드 보기'; benefit.onclick = (event) => { event?.preventDefault?.(); router.navigate?.('benefit'); }; card.appendChild(benefit);
      const share = document.createElement('a'); share.className = 'btn btn-outline btn-sm'; share.href = '#invite'; share.textContent = claimType === 'RANKING' ? '기록 공유하기' : '경품 결과 공유하기'; share.onclick = (event) => { event?.preventDefault?.(); router.shareContext = claimType === 'RANKING' ? 'record_share' : 'prize_share'; router.navigate?.('invite'); }; card.appendChild(share);
    }
    return card;
  },

  async claimModal(claim, router, renderToken = router.renderToken) {
    let closed = false;
    const active = () => !closed && ( renderToken == null || !router.isCurrent || router.isCurrent(renderToken));
    let preparedShare = null;
    let acceptedOutcome = null;
    const shareReady = prepareResultReferralShare(router, { kind: (claim.claim_type || claim.type) === 'RANKING' ? 'record_share' : 'prize_share' }).then((value) => { preparedShare = value; }).catch(() => {});
    let draft;
    try { ({ draft } = await api.getClaimDraft(claim.id)); }
    catch (error) { if (active()) ui.showToast(error.message); return; }
    if (!active()) return;
    const claimType = claim.claim_type || claim.type || 'DRAW';
    analytics.track('claim_form_started', { claim_type: claimType });
    const form = document.createElement('form'); form.className = 'stack-form';
    const notice = document.createElement('p'); notice.className = 'claim-flow-notice';
    notice.textContent = '정보 입력 후 친구 공유 단계를 거치면 접수가 완료돼요.';
    form.appendChild(notice);
    const definitions = [
      ['이름', 'text', 'name', 80], ['연락처', 'tel', 'contact', 32], ['학교', 'text', 'school', 120],
      ...(claim.category === 'SHIPPING' ? [['주소', 'text', 'address', 300]] : []),
    ];
    const fields = definitions.map(([label, type, name, maxlength]) => ui.formField(label, type, name, { required: true, maxlength }));
    fields.forEach(({ label, input }) => { input.value = draft?.[input.name] || ''; form.appendChild(label); });
    const consent = document.createElement('label'); consent.className = 'consent-row';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox'; checkbox.required = true; checkbox.checked = draft?.consent === true;
    const words = document.createElement('span'); words.textContent = `경품 안내와 수령 확인을 위한\n이름·연락처·학교${claim.category === 'SHIPPING' ? '·주소' : ''} 수집에 동의합니다.`;
    consent.append(checkbox, words); form.appendChild(consent);
    const accuracyNote = document.createElement('p'); accuracyNote.className = 'result-contact-accuracy';
    accuracyNote.textContent = '정보 오기재로 인한 연락 불가 및 경품 미수령의 책임은\n본인에게 있습니다. 입력 내용을 꼭 확인해 주세요.';
    form.appendChild(accuracyNote);
    ui.showModal({
      title: '1 / 3 · 수령 정보 입력', content: form, confirmText: '저장 후\n친구에게 자랑하기', cancelText: '취소',
      onCancel: () => { closed = true; },
      onConfirm: async () => {
        if (!checkbox.checked || fields.some(({ input }) => !input.value.trim())) { ui.showToast('필수 항목을 입력하고 수집에 동의해 주세요.'); return false; }
        try {
          if (!preparedShare) { ui.showToast('공유를 준비하지 못했어요. 잠시 후 다시 열어 주세요.'); return false; }
          // Start both in the original click so opening the share sheet keeps user activation.
          const saving = api.saveClaimDraft(claim.id, { ...Object.fromEntries(fields.map(({ input }) => [input.name, input.value.trim()])), consent: true, notice_version: 'claim-contact-v1' });
          const sharing = acceptedOutcome ? Promise.resolve(acceptedOutcome) : preparedShare.share();
          const [saved, shared] = await Promise.allSettled([saving, sharing]);
          const outcome = shared.status === 'fulfilled' ? shared.value : { status: 'failed' };
          if (['share_sheet_closed', 'copied'].includes(outcome?.status) || (outcome?.method === 'kakao' && outcome.status === 'attempted')) acceptedOutcome = outcome;
          if (saved.status === 'rejected') throw saved.reason;
          router.announceStateChange?.();
          if (active()) this.claimShareModal(claim, router, renderToken, outcome);
          return true;
        } catch (error) { if (active()) ui.showToast(error.message); return false; }
      },
    });
    const confirm = document.querySelector?.('#common-modal-overlay .modal-actions .btn-primary');
    if (confirm) { confirm.classList.add('claim-save-share'); confirm.parentElement.classList.add('claim-save-actions'); confirm.disabled = true; void shareReady.finally(() => { confirm.disabled = false; }); }
  },

  claimShareModal(claim, router, renderToken = router.renderToken, initialOutcome = null) {
    let closed = false;
    const active = () => !closed && (renderToken == null || !router.isCurrent || router.isCurrent(renderToken));
    const content = document.createElement('div'); content.className = 'claim-share-step';
    const title = document.createElement('h2'); title.textContent = '접수까지 마지막 한 단계!';
    const description = document.createElement('p'); description.textContent = '친구에게 공룡 점프를 알려주세요.';
    const saved = document.createElement('p'); saved.className = 'claim-flow-notice'; saved.textContent = '입력한 정보는 임시 저장했어요. 수령함에서 이어서 진행할 수 있어요.';
    const feedback = document.createElement('p'); feedback.className = 'status-note'; feedback.setAttribute('role', 'status');
    const button = document.createElement('button'); button.type = 'button'; button.className = 'btn invite-kakao-share';
    button.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3C6.48 3 2 6.58 2 11c0 2.79 1.79 5.25 4.5 6.68L5.36 21l4.22-2.25c.78.16 1.59.25 2.42.25 5.52 0 10-3.58 10-8S17.52 3 12 3Z"/></svg><span>카카오톡으로 친구에게 공유하기</span>';
    button.disabled = true;
    content.append(title, description, saved, button, feedback);
    ui.showModal({ title: '2 / 3 · 친구에게 공유', content, confirmText: '나중에 계속하기', cancelText: '정보 수정',
      onConfirm: () => { if (active()) router.navigate('claims'); closed = true; },
      onCancel: () => { if (active()) void this.claimModal(claim, router, renderToken); closed = true; },
    });
    let prepared = null;
    let acceptedStatus = initialOutcome?.method === 'kakao' && initialOutcome.status === 'attempted' ? 'kakao_opened'
      : initialOutcome?.status === 'share_sheet_closed' ? 'share_sheet_closed'
      : initialOutcome?.status === 'copied' ? 'copied' : null;
    let pending = false;
    const prepare = async () => {
      try { prepared = await prepareResultReferralShare(router, { kind: (claim.claim_type || claim.type) === 'RANKING' ? 'record_share' : 'prize_share' }); if (!initialOutcome) feedback.textContent = ''; }
      catch (_) { feedback.textContent = '공유 준비에 실패했어요. 버튼을 눌러 다시 준비해 주세요.'; }
      finally { button.disabled = false; }
    };
    if (!acceptedStatus) void prepare();
    button.onclick = async () => {
      if (pending || !active()) return;
      pending = true; button.disabled = true;
      try {
        if (!prepared && !acceptedStatus) { await prepare(); return; }
        if (!acceptedStatus) {
          const outcome = await prepared.share();
          acceptedStatus = outcome?.method === 'kakao' && outcome.status === 'attempted' ? 'kakao_opened'
            : outcome?.status === 'share_sheet_closed' ? 'share_sheet_closed'
            : outcome?.status === 'copied' ? 'copied' : null;
          if (!acceptedStatus) { feedback.textContent = outcome?.status === 'cancelled' ? '공유를 취소했어요. 정보는 임시 저장되어 있어요.' : '공유가 열리지 않았어요. 다시 시도해 주세요.'; return; }
        }
        if (!active()) return;
        await api.submitClaim(claim.id, { share_status: acceptedStatus });
        analytics.track('claim_form_submitted', { claim_type: claim.claim_type || claim.type || 'DRAW' });
        router.announceStateChange?.();
        if (!active()) return;
        const done = document.createElement('div'); done.className = 'claim-share-step';
        const heading = document.createElement('h2'); heading.textContent = '수령 정보 접수가 완료됐어요.';
        const note = document.createElement('p'); note.textContent = '접수 내역은 수령함에서 확인할 수 있어요.';
        done.append(heading, note);
        ui.showModal({ title: '3 / 3 · 접수 완료', content: done, confirmText: '수령함 보기', onConfirm: () => router.navigate('claims') });
      } catch (error) {
        feedback.textContent = error.message || '접수를 완료하지 못했어요. 다시 시도해 주세요.';
        if (acceptedStatus) button.textContent = '접수 완료 다시 시도';
      } finally { pending = false; button.disabled = false; }
    };
    if (acceptedStatus) { button.textContent = '접수 완료 중…'; void button.onclick(); }
    else if (initialOutcome) feedback.textContent = initialOutcome.status === 'cancelled' ? '공유를 취소했어요. 정보는 임시 저장되어 있어요.' : '공유가 열리지 않았어요. 다시 시도해 주세요.';
  },
};
