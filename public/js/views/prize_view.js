import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

const STATUS_LABELS = {
  INFORMATION_RECEIVED: '정보 접수', PENDING_REVIEW: '확인 대기', CONTACTED: '연락 완료',
  PAID: '지급 완료', ON_HOLD: '보류', INELIGIBLE: '부적격', NO_RESPONSE: '미응답', READY: '정보 입력 대기',
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
      for (const claim of claims) container.appendChild(this.claimCard(claim, router));
    } catch (error) {
      container.replaceChildren();
      const card = document.createElement('section'); card.className = 'card empty-state';
      const p = document.createElement('p'); p.textContent = error.message || '수령함을 불러오지 못했습니다.';
      card.appendChild(p); container.appendChild(card);
    }
  },

  renderEmpty(container, router) {
    const card = document.createElement('section'); card.className = 'card empty-state';
    const title = document.createElement('h2'); title.textContent = '접수할 경품이 아직 없어요';
    const button = document.createElement('button'); button.className = 'btn btn-primary'; button.textContent = '복주머니 확인'; button.onclick = () => router.navigate('draw');
    card.append(title, button); container.appendChild(card);
  },

  claimCard(claim, router) {
    const card = document.createElement('article'); card.className = 'card claim-card';
    const header = document.createElement('div'); header.className = 'claim-card-header';
    const name = document.createElement('h2'); name.textContent = claim.prize_name || '경품';
    const badge = document.createElement('span'); badge.className = 'sticker-badge badge-blue'; badge.textContent = STATUS_LABELS[claim.status] || claim.status;
    header.append(name, badge);
    const claimType = claim.claim_type || claim.type || 'DRAW';
    const type = document.createElement('p'); type.textContent = claimType === 'RANKING' ? '랭킹 경품' : '복주머니 경품';
    card.append(header, type);
    if (!claim.contact_submitted && !['PAID', 'CONTACTED'].includes(claim.status)) {
      const button = document.createElement('button'); button.className = 'btn btn-primary btn-sm'; button.textContent = '합성 테스트 수령 정보 입력';
      button.onclick = () => this.claimModal(claim, router); card.appendChild(button);
    }
    return card;
  },

  claimModal(claim, router) {
    const claimType = claim.claim_type || claim.type || 'DRAW';
    analytics.track('claim_form_started', { claim_type: claimType });
    const form = document.createElement('form'); form.className = 'stack-form';
    const definitions = [
      ['이름 (테스트 정보)', 'text', 'name', 30], ['연락처 (테스트 정보)', 'text', 'contact', 60], ['학교 (선택)', 'text', 'school', 60], ['주소 (필요한 경우)', 'text', 'address', 120],
    ];
    const fields = definitions.map(([label, type, name, maxlength]) => ui.formField(label, type, name, { required: name !== 'school' && name !== 'address', maxlength }));
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
          router.announceStateChange(); router.navigate('claims');
        } catch (error) { ui.showToast(error.message); return false; }
      },
    });
  },
};
