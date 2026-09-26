import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { prepareResultReferralShare } from '../referral_share.js';

const rankingRequests = new WeakMap();
const rankLabel = (rank) => ['🥇', '🥈', '🥉'][rank - 1] || `${rank}위`;

export const RankingView = {
  render(container, router, renderToken) {
    analytics.track('ranking_viewed');
    return this.load(container, router, renderToken);
  },

  async load(container, router, renderToken) {
    const request = Symbol('ranking');
    rankingRequests.set(container, request);
    container.innerHTML = '<section class="card empty-state"><p>랭킹을 불러오는 중...</p></section>';
    try {
      const data = await api.getLeaderboard();
      if (!router.isCurrent(renderToken) || rankingRequests.get(container) !== request) return;
      container.replaceChildren();
      const prizes = document.createElement('section'); prizes.className = 'ranking-prizes';
      const title = document.createElement('h1'); title.textContent = '랭킹 TOP3 선물';
      const rewards = document.createElement('div'); rewards.className = 'ranking-rewards';
      for (const [index, amount] of ['5만원', '3만원', '1만원'].entries()) {
        const reward = document.createElement('div'); reward.className = `ranking-reward ranking-reward-${index + 1}`;
        const place = document.createElement('span'); place.textContent = rankLabel(index + 1); place.className = 'ranking-reward-medal'; place.setAttribute('role', 'img'); place.setAttribute('aria-label', `${index + 1}위`);
        const value = document.createElement('strong'); value.textContent = amount;
        reward.append(place, value); rewards.appendChild(reward);
      }
      prizes.append(title, rewards); container.appendChild(prizes);
      const stats = document.createElement('section'); stats.className = 'card ranking-my-record'; stats.setAttribute('aria-label', '내 랭킹과 참가 현황');
      const gap = data.top3_gap ?? data.me?.top3_gap ?? {};
      const metrics = document.createElement('div'); metrics.className = 'ranking-metrics';
      const count = Number.isInteger(gap.participant_count) ? `${gap.participant_count.toLocaleString('ko-KR')}명` : '집계 중';
      for (const [label, value] of [['내 순위', data.me?.rank ? rankLabel(data.me.rank) : '기록 없음'], ['내 최고 점수', data.me?.rank ? `${Number(data.me.best_score).toLocaleString('ko-KR')}점` : '—'], ['랭킹 참가자', count]]) {
        const item = document.createElement('div');
        const caption = document.createElement('span'); caption.textContent = label;
        const number = document.createElement('strong'); number.textContent = value;
        item.append(caption, number); metrics.appendChild(item);
      }
      const comparison = document.createElement('p'); comparison.className = 'ranking-time-gap'; comparison.textContent = this.timeGapMessage(data);
      stats.append(metrics, comparison); container.appendChild(stats);
      const list = document.createElement('section'); list.className = 'card ranking-list';
      if (!data.leaderboard?.length) { const empty = document.createElement('p'); empty.textContent = '등록된 기록이 없습니다.'; list.appendChild(empty); }
      for (const entry of data.leaderboard || []) {
        const row = document.createElement('div'); row.className = `ranking-row${entry.is_me ? ' is-me' : ''}`;
        const rank = document.createElement('strong'); rank.textContent = `${rankLabel(entry.rank)}${entry.tied ? ' (동점)' : ''}`; rank.setAttribute('aria-label', `${entry.rank}위${entry.tied ? ' 동점' : ''}`);
        const nickname = document.createElement('span'); nickname.textContent = entry.nickname;
        const score = document.createElement('span'); score.textContent = `${entry.score}점`;
        row.append(rank, nickname, score); list.appendChild(row);
      }
      container.appendChild(list);
      const share = document.createElement('button'); share.type = 'button'; share.className = 'btn invite-kakao-share'; share.id = 'btn-ranking-share';
      share.innerHTML = '<svg viewBox="0 0 24 24" aria-hidden="true"><path fill="currentColor" d="M12 3C6.48 3 2 6.58 2 11c0 2.79 1.79 5.25 4.5 6.68L5.36 21l4.22-2.25c.78.16 1.59.25 2.42.25 5.52 0 10-3.58 10-8S17.52 3 12 3Z"/></svg><span>카카오톡으로 친구에게 공유하기</span>';
      const feedback = document.createElement('p'); feedback.className = 'status-note'; feedback.setAttribute('role', 'status'); feedback.hidden = true;
      container.append(share, feedback);
      void this.prepareSharing(share, feedback, router, () => router.isCurrent(renderToken) && rankingRequests.get(container) === request);
    } catch (error) {
      if (!router.isCurrent(renderToken) || rankingRequests.get(container) !== request) return;
      container.replaceChildren();
      const card = document.createElement('section'); card.className = 'card empty-state ranking-load-error'; card.setAttribute('role', 'status');
      const message = document.createElement('p'); message.textContent = error.message || '랭킹을 불러오지 못했습니다.';
      const retry = document.createElement('button'); retry.className = 'btn btn-secondary btn-sm'; retry.textContent = '랭킹 다시 불러오기';
      retry.onclick = () => {
        if (!router.isCurrent(renderToken) || retry.disabled) return;
        retry.disabled = true;
        return this.load(container, router, renderToken);
      };
      card.append(message, retry); container.appendChild(card);
    }
  },

  async prepareSharing(button, feedback, router, isCurrent) {
    button.disabled = true;
    try {
      const prepared = await prepareResultReferralShare(router, { kind: 'retry_invite' });
      if (!isCurrent()) return;
      button.disabled = false; feedback.hidden = true;
      button.onclick = async () => {
        if (button.disabled || !isCurrent()) return;
        button.disabled = true;
        try {
          const result = await prepared.share();
          if (isCurrent() && result?.status === 'failed') { feedback.textContent = '공유를 열지 못했어요. 다시 시도해 주세요.'; feedback.hidden = false; }
        } finally { if (isCurrent()) button.disabled = false; }
      };
    } catch (_) {
      if (!isCurrent()) return;
      feedback.textContent = '공유를 준비하지 못했어요. 버튼을 눌러 다시 준비해 주세요.'; feedback.hidden = false;
      button.disabled = false;
      button.onclick = () => this.prepareSharing(button, feedback, router, isCurrent);
    }
  },

  updateState(container, router, renderToken) {
    if (router.isCurrent(renderToken)) return this.load(container, router, renderToken);
  },

  timeGapMessage(data) {
    if (!data.me?.rank) return '첫 게임을 마치면\n내 순위와 3위와의 시간 차이를 볼 수 있어요.';
    const gap = data.top3_gap ?? data.me.top3_gap ?? {};
    if (gap.status === 'IN_TOP3' || data.me.rank <= 3) return `현재 ${data.me.rank}위로 TOP3예요!`;
    if (gap.third_score == null) return '아직 3위 기록이 없어요. 먼저 TOP3에 도전해 보세요!';
    const points = gap.score_needed;
    if (!Number.isFinite(points)) return '3위까지 남은 점수를 확인하고 있어요.';
    // Match the invite/result screens: 10 time points per second, rounded up.
    return `3위까지 약 ${Math.ceil(Math.max(0, points) / 10)}초 더!`;
  },
};
