import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

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
  async render(container, router, renderToken) {
    container.innerHTML = '<section class="card empty-state"><p>수령 상태를 불러오는 중...</p></section>';
    try {
      const { claims = [] } = await api.getClaims();
      if (!router.isCurrent(renderToken)) return;
      container.replaceChildren();
      const intro = document.createElement('section'); intro.className = 'card compact-card';
      const heading = document.createElement('h1'); heading.textContent = '내 수령함';
      const text = document.createElement('p'); text.textContent = '경품은 자동 발급되지 않습니다. 정보를 접수하면 관리자가 확인하고 직접 연락한 뒤 지급 상태를 변경합니다.';
      intro.append(heading, text); container.appendChild(intro);
      if (!claims.length) return this.renderEmpty(container, router);
      for (const claim of claims) container.appendChild(this.claimCard(claim, router, renderToken));
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      container.replaceChildren();
      const card = document.createElement('section'); card.className = 'card empty-state';
      const p = document.createElement('p'); p.textContent = error.message || '수령함을 불러오지 못했습니다.';
      card.appendChild(p); container.appendChild(card);
    }
  },

  renderEmpty(container, router) {
    const card = document.createElement('section'); card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '접수할 경품이 아직 없어요';
    const button = document.createElement('button'); button.className = 'btn btn-primary'; button.textContent = '복주머니 확인'; button.onclick = () => {
      analytics.track('draw_cta_clicked', { source: 'claims', draw_status: router.state?.draw?.status || 'LOCKED' });
      router.navigate('draw');
    };
    card.append(title, button); container.appendChild(card);
  },

  claimCard(claim, router, renderToken) {
    const card = document.createElement('article'); card.className = 'card claim-card';
    const header = document.createElement('div'); header.className = 'claim-card-header';
    const name = document.createElement('h2'); name.textContent = claim.prize_name || '경품';
    const badge = document.createElement('span'); badge.className = 'sticker-badge badge-blue'; badge.textContent = STATUS_LABELS[claim.status] || claim.status;
    header.append(name, badge);
    const claimType = claim.claim_type || claim.type || 'DRAW';
    const type = document.createElement('p'); type.textContent = claimType === 'RANKING' ? '랭킹 경품' : '복주머니 경품';
    const help = document.createElement('p'); help.className = 'claim-help'; help.textContent = STATUS_HELP[claim.status] || '운영팀 확인 상태를 표시하고 있어요.';
    card.append(header, type, help);
    if (!claim.contact_submitted && !['PAID', 'INELIGIBLE'].includes(claim.status)) {
      const button = document.createElement('button'); button.className = 'btn btn-primary btn-sm'; button.textContent = '합성 테스트 수령 정보 입력';
      button.onclick = () => this.claimModal(claim, router, renderToken); card.appendChild(button);
    }
    if (claim.contact_submitted || ['INFORMATION_RECEIVED', 'PENDING_REVIEW', 'CONTACTED', 'PAID', 'ON_HOLD', 'NO_RESPONSE'].includes(claim.status)) {
      const benefit = document.createElement('a'); benefit.className = 'btn btn-secondary btn-sm'; benefit.href = '#benefit'; benefit.textContent = 'Gemini 혜택과 활용 가이드 보기'; benefit.onclick = (event) => { event?.preventDefault?.(); router.navigate?.('benefit'); }; card.appendChild(benefit);
      const share = document.createElement('a'); share.className = 'btn btn-outline btn-sm'; share.href = '#invite'; share.textContent = '경품 결과 공유하기'; share.onclick = (event) => { event?.preventDefault?.(); router.shareContext = 'prize_share'; router.navigate?.('invite'); }; card.appendChild(share);
    }
    return card;
  },

  claimModal(claim, router, renderToken = router.renderToken) {
    const claimType = claim.claim_type || claim.type || 'DRAW';
    analytics.track('claim_form_started', { claim_type: claimType });
    const form = document.createElement('form'); form.className = 'stack-form';
    const definitions = [
      ['이름 (테스트 정보)', 'text', 'name', 30], ['연락처 (테스트 정보)', 'text', 'contact', 60], ['학교 (테스트 정보)', 'text', 'school', 60], ['주소 (필요한 경우)', 'text', 'address', 120],
    ];
    const fields = definitions.map(([label, type, name, maxlength]) => ui.formField(label, type, name, { required: name !== 'address', maxlength }));
    fields[0].input.value = 'TEST_사용자';
    fields[1].input.value = '01000000000';
    fields[2].input.value = 'TEST_학교';
    fields[3].input.value = 'TEST_주소';
    fields.forEach(({ label }) => form.appendChild(label));
    const consent = document.createElement('label'); consent.className = 'consent-row';
    const checkbox = document.createElement('input'); checkbox.type = 'checkbox';
    const words = document.createElement('span'); words.textContent = '현재는 Preview 검증용 합성 정보이며 실제 개인정보를 입력하지 않습니다.';
    consent.append(checkbox, words); form.appendChild(consent);
    ui.showModal({
      title: '수령 정보 접수', content: form, confirmText: '접수', cancelText: '취소',
      onConfirm: async () => {
        if (!checkbox.checked || fields.filter(({ input }) => input.required).some(({ input }) => !input.value.trim())) { ui.showToast('필수 항목과 확인란을 완료해 주세요.'); return false; }
        try {
          await api.submitClaim(claim.id, Object.fromEntries(fields.map(({ input }) => [input.name, input.value.trim()])));
          analytics.track('claim_form_submitted', { claim_type: claimType });
          router.announceStateChange();
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          router.navigate('claims');
        } catch (error) {
          if (renderToken != null && router.isCurrent && !router.isCurrent(renderToken)) return true;
          ui.showToast(error.message); return false;
        }
      },
    });
  },
};
