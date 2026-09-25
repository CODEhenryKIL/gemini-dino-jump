import { api } from '../api.js';
import { analytics } from '../analytics.js';
import { ResultView } from './result_view.js';

export const RankingView = {
  async render(container, router, renderToken) {
    container.innerHTML = '<section class="card empty-state"><p>랭킹을 불러오는 중...</p></section>';
    analytics.track('ranking_viewed');
    try {
      const data = await api.getLeaderboard();
      if (!router.isCurrent(renderToken)) return;
      container.replaceChildren();
      const intro = document.createElement('section'); intro.className = 'card compact-card';
      const title = document.createElement('h1'); title.textContent = '검증된 최고 점수 랭킹';
      const note = document.createElement('p'); note.textContent = '동점자는 같은 순위로 표시합니다. 최종 동점 수상 정책은 아직 확정하지 않았습니다.';
      const mine = document.createElement('strong'); mine.textContent = data.me?.rank ? `내 순위 ${data.me.rank}위 · ${data.me.best_score}점` : '아직 내 기록이 없어요';
      const gap = document.createElement('p'); gap.className = 'result-gap'; gap.textContent = ResultView.top3GapMessage({ rank: data.me?.rank, top3_gap: data.top3_gap ?? data.me?.top3_gap });
      intro.append(title, note, mine, gap); container.appendChild(intro);
      if (router.state.top3Profile?.status === 'REQUESTED') {
        const contact = document.createElement('section'); contact.className = 'card compact-card';
        const copy = ResultView.top3RequestCopy(router.state.top3Profile, router.config);
        const contactTitle = document.createElement('h2'); contactTitle.textContent = copy.title;
        const contactText = document.createElement('p'); contactText.textContent = `${copy.description} 새로고침하거나 현재 순위가 내려가도 접수 요청은 유지됩니다.`;
        const contactButton = document.createElement('button'); contactButton.className = 'btn btn-primary'; contactButton.textContent = '합성 테스트 정보 입력';
        contactButton.onclick = () => ResultView.top3Modal(router, renderToken);
        contact.append(contactTitle, contactText, contactButton); container.appendChild(contact);
      }
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
      if (!router.isCurrent(renderToken)) return;
      container.replaceChildren(); const card = document.createElement('section'); card.className = 'card empty-state'; card.textContent = error.message; container.appendChild(card);
    }
  },
};
