import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';

export const InviteView = {
  async render(container, router, renderToken) {
    container.innerHTML = '<section class="card empty-state"><p>초대 현황을 불러오는 중...</p></section>';
    analytics.track('invite_cta_viewed');
    try {
      const data = await api.getReferralInfo();
      if (!router.isCurrent(renderToken)) return;
      container.innerHTML = `
        <section class="card compact-card"><span class="sticker-badge badge-blue">최대 3장 보유</span><h1>친구 초대하고 재도전하기</h1><p>친구가 링크를 열고 화면이 보이는 상태에서 3초 이상 머문 뒤 한 번 누르면 방문을 확인합니다.</p></section>
        <section class="card share-card"><h2 id="invite-score"></h2><button id="btn-share-native" class="btn btn-primary">공유 창 열기</button><button id="btn-copy-link" class="btn btn-outline">초대 링크 복사</button></section>
        <section class="card"><div class="stat-grid"><div><small>현재 초대권</small><strong id="invite-balance"></strong></div><div><small>보상된 관계</small><strong id="rewarded-pairs"></strong></div><div><small>유효 방문</small><strong id="valid-visits"></strong></div></div><p id="invite-cooldown" class="status-note"></p></section>`;
      ui.text(container.querySelector('#invite-score'), `내 최고 기록 ${router.state.bestScore}점`);
      ui.text(container.querySelector('#invite-balance'), `${data.invitation_balance || 0}장`);
      ui.text(container.querySelector('#rewarded-pairs'), `${data.rewarded_pairs || 0}명`);
      ui.text(container.querySelector('#valid-visits'), `${data.valid_visits || 0}회`);
      ui.text(container.querySelector('#invite-cooldown'), data.cooldown_until ? `${new Date(data.cooldown_until).toLocaleString('ko-KR')}까지 추가 적립 대기 중입니다. 대기 중 방문은 이월되지 않아요.` : '초대권 잔액이 3장이 되는 순간 10시간 추가 적립 대기가 시작됩니다.');
      const shareKind = router.shareContext === 'prize_share' ? 'prize_share' : 'retry_invite';
      router.shareContext = null;
      const buildInviteUrl = (shareId) => {
        const url = new URL(data.invite_url, window.location.origin);
        if (shareKind === 'prize_share') url.searchParams.set('link', 'prize_share');
        url.searchParams.set('share', shareId);
        return url.toString();
      };
      const share = async (method) => {
        const shareId = api.createRequestId('share');
        const inviteUrl = buildInviteUrl(shareId);
        analytics.track('share_attempted', { share_method: method, share_id: shareId, link_kind: shareKind, status: 'attempted' });
        if (method === 'native' && navigator.share) {
          try {
            await navigator.share({ title: '공룡 점프 챌린지', text: `내 기록 ${router.state.bestScore}점에 도전해 봐!`, url: inviteUrl });
            analytics.track('share_attempted', { share_method: method, share_id: shareId, link_kind: shareKind, status: 'share_sheet_closed' });
            ui.showToast('공유 창을 닫았어요. 전송 여부는 기기에서 확인해 주세요.');
          } catch (error) {
            analytics.track('share_attempted', { share_method: method, share_id: shareId, link_kind: shareKind, status: error?.name === 'AbortError' ? 'cancelled' : 'failed' });
          }
        } else {
          try {
            await navigator.clipboard.writeText(inviteUrl);
            analytics.track('share_attempted', { share_method: 'copy', share_id: shareId, link_kind: shareKind, status: 'copied' });
            ui.showToast('초대 링크를 복사했어요.');
          } catch (_) {
            analytics.track('share_attempted', { share_method: 'copy', share_id: shareId, link_kind: shareKind, status: 'failed' });
            ui.showToast('링크를 복사하지 못했습니다.');
          }
        }
      };
      container.querySelector('#btn-share-native').onclick = () => share('native');
      container.querySelector('#btn-copy-link').onclick = () => share('copy');
    } catch (error) { container.replaceChildren(); const card = document.createElement('section'); card.className = 'card empty-state'; card.textContent = error.message; container.appendChild(card); }
  },
};
