/**
 * S10 Real-time Leaderboard View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const RankingView = {
  async render(container, router) {
    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <!-- Header Card -->
        <div class="card" style="padding: 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2 style="font-size: 20px; font-weight: 900;">🏆 명예의 전당</h2>
            <span class="sticker-badge badge-blue">실시간 검증</span>
          </div>
          <p style="font-size: 13px; color: var(--text-sub);">
            * 검증된 최고 점수 기준이며, 동점일 경우 <strong>먼저 달성한 순서</strong>로 정렬됩니다.
          </p>
        </div>

        <!-- My Ranking Float Card -->
        <div id="my-ranking-card" class="card" style="background: linear-gradient(135deg, #1967D2 0%, #4285F4 100%); color: #FFF; padding: 16px 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center;">
            <div>
              <div style="font-size: 11px; opacity: 0.85; font-weight: 600;">내 최고 순위</div>
              <div id="my-rank-text" style="font-size: 26px; font-weight: 900;">- 위</div>
            </div>
            <div style="text-align: right;">
              <div id="my-nick-text" style="font-size: 13px; font-weight: 700;">-</div>
              <div id="my-score-text" style="font-size: 24px; font-weight: 900; font-family: monospace;">0점</div>
            </div>
          </div>
        </div>

        <!-- Leaderboard List -->
        <div class="card" style="padding: 12px 16px;">
          <div id="leaderboard-list" style="display: flex; flex-direction: column; gap: 8px;">
            <div style="text-align: center; padding: 30px; color: var(--text-sub);">
              랭킹을 불러오는 중...
            </div>
          </div>
        </div>
      </div>
    `;

    const listEl = container.querySelector('#leaderboard-list');
    const myRankEl = container.querySelector('#my-rank-text');
    const myNickEl = container.querySelector('#my-nick-text');
    const myScoreEl = container.querySelector('#my-score-text');

    try {
      const data = await api.getLeaderboard();
      const list = data.leaderboard || [];
      const myCard = data.my_card;

      if (myCard) {
        myRankEl.textContent = `${myCard.rank}위`;
        myNickEl.textContent = myCard.nickname;
        myScoreEl.textContent = `${myCard.score}점`;
      } else {
        myRankEl.textContent = '기록 없음';
        myScoreEl.textContent = '0점';
      }

      if (list.length === 0) {
        listEl.innerHTML = `
          <div style="text-align: center; padding: 30px; color: var(--text-sub);">
            아직 등록된 랭킹 기록이 없습니다.<br>첫 번째 챔피언이 되어보세요!
          </div>
        `;
        return;
      }

      listEl.innerHTML = list.map((item) => {
        let rankBadge = `${item.rank}`;
        let rankColor = '#202124';
        if (item.rank === 1) { rankBadge = '🥇 1'; rankColor = '#FBBC04'; }
        else if (item.rank === 2) { rankBadge = '🥈 2'; rankColor = '#9E9E9E'; }
        else if (item.rank === 3) { rankBadge = '🥉 3'; rankColor = '#CD7F32'; }

        return `
          <div style="display: flex; align-items: center; justify-content: space-between; padding: 10px 8px; border-radius: 12px; ${item.is_me ? 'background: #E8F2FF; border: 1px solid rgba(25, 103, 210, 0.2);' : 'border-bottom: 1px solid rgba(0,0,0,0.04);'}">
            <div style="display: flex; align-items: center; gap: 12px;">
              <span style="font-size: 16px; font-weight: 900; color: ${rankColor}; min-width: 40px;">
                ${rankBadge}
              </span>
              <div>
                <span style="font-size: 14px; font-weight: 700; color: #202124;">
                  ${item.nickname}
                </span>
                ${item.is_me ? '<span class="sticker-badge badge-blue" style="font-size: 10px; margin-left: 4px;">나</span>' : ''}
              </div>
            </div>

            <div style="font-size: 16px; font-weight: 900; font-family: monospace; color: var(--primary);">
              ${item.score}점
            </div>
          </div>
        `;
      }).join('');

    } catch (err) {
      listEl.innerHTML = `
        <div style="text-align: center; padding: 20px; color: #EA4335;">
          랭킹 정보를 불러오지 못했습니다.
        </div>
      `;
    }
  }
};
