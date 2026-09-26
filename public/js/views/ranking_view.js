import { api } from '../api.js';
import { analytics } from '../analytics.js';

const rankingRequests = new WeakMap();

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
        const medal = document.createElement('span'); medal.className = 'ranking-medal'; medal.textContent = ['🥇', '🥈', '🥉'][index]; medal.setAttribute('aria-hidden', 'true');
        const place = document.createElement('span'); place.textContent = `${index + 1}위`;
        const value = document.createElement('strong'); value.textContent = amount;
        reward.append(medal, place, value); rewards.appendChild(reward);
      }
      const awardNote = document.createElement('p'); awardNote.className = 'ranking-award-note'; awardNote.textContent = '행사 종료 시 최종 순위 기준 · 동점 수상 기준은 추후 안내';
      prizes.append(title, rewards, awardNote); container.appendChild(prizes);
      const stats = document.createElement('section'); stats.className = 'card ranking-my-record'; stats.setAttribute('aria-label', '내 랭킹과 참가 현황');
      const gap = data.top3_gap ?? data.me?.top3_gap ?? {};
      const metrics = document.createElement('div'); metrics.className = 'ranking-metrics';
      const count = Number.isInteger(gap.participant_count) ? `${gap.participant_count.toLocaleString('ko-KR')}명` : '집계 중';
      for (const [label, value] of [['내 순위', data.me?.rank ? `${data.me.rank}위` : '기록 없음'], ['내 최고 점수', data.me?.rank ? `${Number(data.me.best_score).toLocaleString('ko-KR')}점` : '—'], ['랭킹 참가자', count]]) {
        const item = document.createElement('div');
        const caption = document.createElement('span'); caption.textContent = label;
        const number = document.createElement('strong'); number.textContent = value;
        item.append(caption, number); metrics.appendChild(item);
      }
      const comparison = document.createElement('p'); comparison.className = 'ranking-time-gap'; comparison.textContent = this.timeGapMessage(data);
      const explanation = document.createElement('p'); explanation.className = 'ranking-comparison-note'; explanation.textContent = '랭킹은 코인을 포함한 점수순이에요. 시간은 각 최고점 기록의 플레이 시간을 비교해요.';
      stats.append(metrics, comparison, explanation); container.appendChild(stats);
      const list = document.createElement('section'); list.className = 'card ranking-list';
      if (!data.leaderboard?.length) { const empty = document.createElement('p'); empty.textContent = '등록된 기록이 없습니다.'; list.appendChild(empty); }
      for (const entry of data.leaderboard || []) {
        const row = document.createElement('div'); row.className = `ranking-row${entry.is_me ? ' is-me' : ''}`;
        const rank = document.createElement('strong'); rank.textContent = `${entry.rank}위${entry.tied ? ' (동점)' : ''}`;
        const nickname = document.createElement('span'); nickname.textContent = entry.nickname;
        const score = document.createElement('span'); score.textContent = `${entry.score}점`;
        row.append(rank, nickname, score); list.appendChild(row);
      }
      container.appendChild(list);
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

  updateState(container, router, renderToken) {
    if (router.isCurrent(renderToken)) return this.load(container, router, renderToken);
  },

  timeGapMessage(data) {
    if (!data.me?.rank) return '첫 게임을 마치면 내 순위와 3위와의 시간 차이를 볼 수 있어요.';
    const gap = data.top3_gap ?? data.me.top3_gap ?? {};
    if (gap.third_score == null) return '아직 3위 기록이 없어요. 먼저 TOP3에 도전해 보세요!';
    const own = data.me.best_elapsed_seconds;
    const third = gap.third_elapsed_seconds;
    if (!Number.isFinite(own) || !Number.isFinite(third)) return '플레이 시간 기록을 확인하고 있어요.';
    const difference = own - third;
    const seconds = Math.abs(difference).toLocaleString('ko-KR', { minimumFractionDigits: 1, maximumFractionDigits: 1 });
    const same = Math.abs(difference) < 0.05;
    const comparison = same ? '3위 기록과 플레이 시간이 같아요.' : `3위 기록보다 ${seconds}초 ${difference < 0 ? '짧게' : '더'} 달렸어요.`;
    return `${comparison} (3위 대표 기록 ${third.toLocaleString('ko-KR', { maximumFractionDigits: 1 })}초)`;
  },
};
