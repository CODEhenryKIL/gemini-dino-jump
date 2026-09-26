import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ResultView } from './result_view.js';

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
      const intro = document.createElement('section'); intro.className = 'card compact-card';
      const title = document.createElement('h1'); title.textContent = '검증된 최고 점수 랭킹';
      const note = document.createElement('p'); note.textContent = '동점자는 같은 순위로 표시합니다. 최종 동점 수상 정책은 아직 확정하지 않았습니다.';
      const mine = document.createElement('strong'); mine.textContent = data.me?.rank ? `내 순위 ${data.me.rank}위 · ${data.me.best_score}점` : '아직 내 기록이 없어요';
      const gap = document.createElement('p'); gap.className = 'result-gap'; gap.textContent = ResultView.top3GapMessage({ rank: data.me?.rank, top3_gap: data.top3_gap ?? data.me?.top3_gap });
      intro.append(title, note, mine, gap); container.appendChild(intro);
      const contact = document.createElement('section'); contact.id = 'top3-request';
      contact.className = 'card compact-card';
      container.appendChild(contact);
      this.updateState(container, router, renderToken);
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
    if (!router.isCurrent(renderToken)) return;
    const target = container.querySelector('#top3-request');
    if (target) ResultView.renderTop3Request(target, router, router.state.top3Profile);
  },
};
