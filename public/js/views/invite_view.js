import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ui } from '../ui.js';
import { prepareResultReferralShare } from '../referral_share.js';

export const InviteView = {
  renderGeneration: 0,
  async render(container, router, renderToken) {
    const renderGeneration = ++this.renderGeneration;
    const isActiveRender = () => this.renderGeneration === renderGeneration && router.isCurrent(renderToken);
    container.innerHTML = '<section class="card empty-state"><p>초대 현황을 불러오는 중...</p></section>';
    analytics.track('invite_cta_viewed');
    try {
      const data = await api.getReferralInfo();
      if (!isActiveRender()) return;
      const shareKind = ['record_share', 'prize_share', 'retry_invite'].includes(router.shareContext) ? router.shareContext : 'retry_invite';
      router.shareContext = null;
      container.innerHTML = `
        <section class="ranking-prizes"><h1>랭킹 TOP3 선물</h1><div class="ranking-rewards"><div class="ranking-reward ranking-reward-1"><span class="ranking-reward-medal" role="img" aria-label="1위">🥇</span><strong>5만원</strong></div><div class="ranking-reward ranking-reward-2"><span class="ranking-reward-medal" role="img" aria-label="2위">🥈</span><strong>3만원</strong></div><div class="ranking-reward ranking-reward-3"><span class="ranking-reward-medal" role="img" aria-label="3위">🥉</span><strong>1만원</strong></div></div></section>
        <section class="card compact-card invite-hero"><h1>친구 초대하고 재도전하기</h1><p id="invite-gap" class="result-gap" role="status">3위 기록을 확인하고 있어요.</p><button id="btn-share-native" class="btn invite-kakao-share" type="button"><svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3C6.48 3 2 6.58 2 11c0 2.79 1.79 5.25 4.5 6.68L5.36 21l4.22-2.25c.78.16 1.59.25 2.42.25 5.52 0 10-3.58 10-8S17.52 3 12 3Z"/></svg><span>카카오톡으로 친구 초대하기</span></button><p id="share-fallback" class="status-note" hidden></p><button id="btn-invite-draw" class="btn btn-secondary" hidden>친구를 기다리지 않고 복주머니 열기</button></section>
        <section class="card invite-stats"><div class="stat-grid"><div><small>현재 초대권</small><strong id="invite-balance"></strong></div><div><small>누적 지급</small><strong id="ticket-granted"></strong></div><div><small>유효 방문</small><strong id="valid-visits"></strong></div></div><div class="ticket-ledger"><span id="ticket-used"></span><span id="ticket-refunded"></span></div><p id="invite-cooldown" class="status-note" role="status"></p></section>`;
      void this.loadGap(container, isActiveRender);
      this.updateSummary(container, data);
      this.updateDrawAction(container, router);
      const button = container.querySelector('#btn-share-native');
      button.disabled = true;
      const prepared = await prepareResultReferralShare(router, { kind: shareKind, referral: data });
      if (!isActiveRender()) return;
      button.disabled = false;
      button.onclick = async () => {
        if (button.disabled) return;
        button.disabled = true;
        try {
          const outcome = await prepared.share();
          if (isActiveRender() && outcome?.status === 'failed') ui.showToast('공유를 열지 못했어요. 다시 시도해 주세요.');
        } finally { if (isActiveRender()) button.disabled = false; }
      };
    } catch (error) {
      if (!isActiveRender()) return;
      container.replaceChildren();
      const card = document.createElement('section'); card.className = 'card empty-state';
      const text = document.createElement('p'); text.textContent = error.message || '초대 현황을 불러오지 못했습니다.';
      const retry = document.createElement('button'); retry.className = 'btn btn-primary'; retry.textContent = '다시 불러오기'; retry.onclick = () => router.navigate('invite');
      const drawButton = document.createElement('button'); drawButton.id = 'btn-invite-draw'; drawButton.className = 'btn btn-secondary'; drawButton.hidden = true;
      card.append(text, retry, drawButton); container.appendChild(card);
      this.updateDrawAction(container, router);
    }
  },
  async loadGap(container, isActiveRender) {
    try {
      const data = await api.getLeaderboard();
      if (!isActiveRender()) return;
      const gap = data.top3_gap ?? data.me?.top3_gap ?? {};
      let message = '첫 게임을 마치면 3위까지 남은 시간을 볼 수 있어요.';
      if (gap.status === 'IN_TOP3') message = `현재 ${gap.rank ?? data.me?.rank}위로 TOP3예요!`;
      else if (gap.status === 'TOO_FEW') message = '먼저 TOP3에 도전해 보세요!';
      else if (gap.status === 'CHASING' && Number.isFinite(gap.score_needed)) message = `3위까지 약 ${Math.ceil(gap.score_needed / 10)}초 더!`;
      const node = container.querySelector('#invite-gap');
      if (node) {
        ui.text(node, message);
        node.classList.toggle('is-chasing', gap.status === 'CHASING');
      }
    } catch (_) {
      if (isActiveRender()) {
        const node = container.querySelector('#invite-gap');
        if (node) ui.text(node, '친구와 함께 TOP3에 도전해 보세요!');
      }
    }
  },
  async updateState(container, router, renderToken) {
    if (!router.isCurrent(renderToken)) return;
    this.updateDrawAction(container, router);
    void this.loadGap(container, () => router.isCurrent(renderToken));
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
        : '친구의 새로운 유효 방문으로 초대권을 받을 수 있어요.\n잔액이 3장이 되면 10시간 추가 적립 대기가 시작돼요.');
  },
};
