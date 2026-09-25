import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

const SHARE_COPY = {
  record_share: { title: '내 기록에 도전해 봐!', description: '친구가 유효 방문하면 재도전권이 적립돼요.' },
  prize_share: { title: '내 복주머니 결과를 확인해 봐!', description: '경품 결과 공유 링크도 같은 초대 보상 규칙을 적용해요.' },
  retry_invite: { title: '친구 초대하고 재도전하기', description: '친구가 유효 방문하면 재도전권이 적립돼요.' },
};

function copyFallback(text) {
  if (navigator.clipboard?.writeText) return navigator.clipboard.writeText(text);
  return Promise.reject(new Error('CLIPBOARD_UNSUPPORTED'));
}

export const InviteView = {
  async render(container, router, renderToken) {
    container.innerHTML = '<section class="card empty-state"><p>초대 현황을 불러오는 중...</p></section>';
    analytics.track('invite_cta_viewed');
    try {
      const data = await api.getReferralInfo();
      if (!router.isCurrent(renderToken)) return;
      const shareKind = ['record_share', 'prize_share', 'retry_invite'].includes(router.shareContext) ? router.shareContext : 'retry_invite';
      const copy = SHARE_COPY[shareKind];
      router.shareContext = null;
      container.innerHTML = `
        <section class="card compact-card"><span class="sticker-badge badge-blue">최대 3장 보유</span><h1 id="invite-title"></h1><p id="invite-description"></p><p>친구가 링크를 열고 화면이 보이는 상태에서 3초 이상 머문 뒤 한 번 누르면 방문을 확인해요.</p><button id="btn-invite-draw" class="btn btn-secondary" hidden>친구를 기다리지 않고 복주머니 열기</button></section>
        <section class="card share-card"><h2 id="invite-score"></h2><p class="public-share-note">공개 카드에는 닉네임·점수·공개 경품명만 사용할 수 있어요. 연락처와 수령 정보는 포함하지 않아요.</p><button id="btn-share-native" class="btn btn-primary">공유 창 열기</button><button id="btn-copy-link" class="btn btn-outline">초대 링크 복사</button><p id="share-fallback" class="status-note">공유 창이 열리지 않으면 링크 복사를 이용해 주세요.</p></section>
        <section class="card"><div class="stat-grid"><div><small>현재 초대권</small><strong id="invite-balance"></strong></div><div><small>누적 지급</small><strong id="ticket-granted"></strong></div><div><small>유효 방문</small><strong id="valid-visits"></strong></div></div><div class="ticket-ledger"><span id="ticket-used"></span><span id="ticket-refunded"></span></div><p id="invite-cooldown" class="status-note" role="status"></p><p class="status-note">먼저 복주머니를 열고 나중에 재도전해도 돼요. 추가 추첨은 없으며, 같은 브라우저와 쿠키를 유지할 때 참여 기록을 복원해요.</p></section>`;
      const setText = (selector, value) => { const node = container.querySelector(selector); if (node) ui.text(node, value); };
      setText('#invite-title', copy.title);
      setText('#invite-description', copy.description);
      setText('#invite-score', shareKind === 'prize_share' ? '복주머니 결과 공유' : `내 최고 기록 ${router.state.bestScore || 0}점`);
      this.updateSummary(container, data);
      this.updateDrawAction(container, router);
      const buildInviteUrl = (shareId) => {
        const url = new URL(data.invite_url, window.location.origin);
        url.searchParams.set('link', shareKind);
        url.searchParams.set('share', shareId);
        return url.toString();
      };
      const copyLink = async (inviteUrl, shareId) => {
        analytics.track('share_attempted', { share_method: 'copy', share_id: shareId, link_kind: shareKind, status: 'attempted' });
        try {
          await copyFallback(inviteUrl);
          analytics.track('share_attempted', { share_method: 'copy', share_id: shareId, link_kind: shareKind, status: 'copied' });
          ui.showToast('초대 링크를 복사했어요.');
        } catch (_) {
          analytics.track('share_attempted', { share_method: 'copy', share_id: shareId, link_kind: shareKind, status: 'failed' });
          setText('#share-fallback', `복사가 지원되지 않아요. 주소창에서 이 링크를 길게 눌러 복사해 주세요: ${inviteUrl}`);
        }
      };
      const share = async (method) => {
        const shareId = api.createRequestId('share');
        const inviteUrl = buildInviteUrl(shareId);
        if (method !== 'native' || typeof navigator.share !== 'function') return copyLink(inviteUrl, shareId);
        analytics.track('share_attempted', { share_method: 'native', share_id: shareId, link_kind: shareKind, status: 'attempted' });
        try {
          await navigator.share({ title: '공룡 점프 챌린지', text: shareKind === 'prize_share' ? '내 복주머니 결과를 확인해 봐!' : `내 기록 ${router.state.bestScore || 0}점에 도전해 봐!`, url: inviteUrl });
          analytics.track('share_attempted', { share_method: 'native', share_id: shareId, link_kind: shareKind, status: 'share_sheet_closed' });
          ui.showToast('공유 창을 닫았어요. 실제 전송 여부는 기기에서 확인해 주세요.');
        } catch (error) {
          analytics.track('share_attempted', { share_method: 'native', share_id: shareId, link_kind: shareKind, status: error?.name === 'AbortError' ? 'cancelled' : 'failed' });
        }
      };
      container.querySelector('#btn-share-native').onclick = () => share('native');
      container.querySelector('#btn-copy-link').onclick = () => share('copy');
    } catch (error) {
      if (!router.isCurrent(renderToken)) return;
      container.replaceChildren();
      const card = document.createElement('section'); card.className = 'card empty-state';
      const text = document.createElement('p'); text.textContent = error.message || '초대 현황을 불러오지 못했습니다.';
      const retry = document.createElement('button'); retry.className = 'btn btn-primary'; retry.textContent = '다시 불러오기'; retry.onclick = () => router.navigate('invite');
      const drawButton = document.createElement('button'); drawButton.id = 'btn-invite-draw'; drawButton.className = 'btn btn-secondary'; drawButton.hidden = true;
      card.append(text, retry, drawButton); container.appendChild(card);
      this.updateDrawAction(container, router);
    }
  },
  async updateState(container, router, renderToken) {
    if (!router.isCurrent(renderToken)) return;
    this.updateDrawAction(container, router);
    if (!container.querySelector('#invite-balance')) return;
    try {
      const data = await api.getReferralInfo();
      if (!router.isCurrent(renderToken)) return;
      this.updateSummary(container, data);
    } catch (_) {
      if (router.isCurrent(renderToken)) ui.text(container.querySelector('#invite-cooldown'), '최신 초대 현황을 불러오지 못했어요. 다시 접속하면 재확인하며, 적립된 게임권은 그대로 보존돼요.');
    }
  },
  updateDrawAction(container, router) {
    const button = container.querySelector?.('#btn-invite-draw');
    if (!button) return;
    const status = router.state?.draw?.status;
    button.hidden = !['AVAILABLE', 'DRAWN'].includes(status);
    button.textContent = status === 'DRAWN' ? '내 복주머니 결과 보기' : '친구를 기다리지 않고 복주머니 열기';
    button.onclick = () => {
      const latest = router.state?.draw?.status;
      if (!['AVAILABLE', 'DRAWN'].includes(latest)) return;
      analytics.track('draw_cta_clicked', { source: 'invite', draw_status: latest });
      router.navigate('draw');
    };
  },
  updateSummary(container, data) {
    const setText = (selector, value) => { const node = container.querySelector(selector); if (node) ui.text(node, value); };
    const totals = data.ticket_totals || {};
    setText('#invite-balance', `${data.invitation_balance || 0}장`);
    setText('#ticket-granted', `${totals.granted ?? data.rewarded_pairs ?? 0}장`);
    setText('#ticket-used', `사용 ${totals.used || 0}장`);
    setText('#ticket-refunded', `환급 ${totals.refunded || 0}장`);
    setText('#valid-visits', `${data.valid_visits || 0}회`);
    const waiting = new Date(data.cooldown_until).getTime() > Date.now();
    setText('#invite-cooldown', waiting
      ? `${new Date(data.cooldown_until).toLocaleString('ko-KR')}까지 새 초대권 적립 대기 중이에요. 가진 초대권은 사용할 수 있고 대기 중 방문은 이월되지 않아요.`
      : data.invitation_balance >= 3
        ? '초대권 3장을 보유 중이에요. 사용해 빈자리가 생기면 친구의 새로운 유효 방문으로 다시 적립할 수 있어요.'
        : '친구의 새로운 유효 방문으로 초대권을 받을 수 있어요. 잔액이 3장이 되면 10시간 추가 적립 대기가 시작돼요.');
  },
};
