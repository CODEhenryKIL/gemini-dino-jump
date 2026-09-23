/**
 * S08 Gemini Student Benefits & S12 Event Rules View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const BenefitView = {
  async render(container, router) {
    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <!-- Gemini Benefits Card -->
        <div class="card" style="padding: 22px;">
          <span class="sticker-badge badge-blue">Google Gemini X 대학생</span>
          <h2 style="font-size: 20px; font-weight: 900; margin-top: 6px; line-height: 1.3;">
            대학생을 위한<br>Gemini 특별 혜택 가이드
          </h2>
          <p style="font-size: 13px; color: var(--text-sub); margin-top: 4px;">
            과제, 시험공부, 코딩까지! 대학생 전용 혜택을 확인하고 등록해보세요.
          </p>

          <div style="background: #F8FAFF; border-radius: 16px; padding: 16px; margin: 16px 0; border: 1px solid rgba(25, 103, 210, 0.08);">
            <div style="font-weight: 800; font-size: 15px; color: var(--primary); margin-bottom: 8px;">
              💡 Gemini 학생 플랜 핵심 혜택
            </div>
            <ul style="font-size: 13px; color: #3C4043; line-height: 1.7; padding-left: 18px;">
              <li>구글 최신 AI 모델 무료 체험 및 크레딧 제공</li>
              <li>긴 문서 요약 및 논문 분석, 리서치 보조</li>
              <li>파이썬 및 웹 개발 실시간 디버깅 & 코드 생성</li>
              <li>Google One 클라우드 드라이브 넉넉한 용량 연계</li>
            </ul>
          </div>

          <!-- Official Link Button -->
          <a id="btn-go-benefit" href="https://gemini.google.com/students" target="_blank" rel="noopener noreferrer" 
             class="btn btn-primary" style="margin-bottom: 8px; text-decoration: none;">
            <span>🌐 Gemini 학생 혜택 확인하기</span>
          </a>

          <!-- Verification Trigger Button -->
          <button id="btn-request-verify" class="btn btn-secondary btn-sm" style="margin-bottom: 6px;">
            <span>📝 학생 혜택 등록 확인 접수</span>
          </button>

          <div id="benefit-verify-status" style="font-size: 12px; color: var(--text-sub); text-align: center;">
            * 단순 페이지 방문은 등록 완료로 인정되지 않으며, 실제 확인 절차를 거칩니다.
          </div>
        </div>

        <!-- S12 Event Rules & Notice Card -->
        <div class="card" style="padding: 20px;">
          <h3 style="font-size: 16px; font-weight: 800; margin-bottom: 12px;">📋 행사 운영 기준 및 공지</h3>
          
          <div style="font-size: 13px; color: var(--text-sub); line-height: 1.6; display: flex; flex-direction: column; gap: 8px;">
            <div><strong>운영 주체:</strong> 공식 Google Student Ambassador 운영</div>
            <div><strong>참여 대상:</strong> 전국 대학생 및 일반 참여자</div>
            <div><strong>공룡 점프 규칙:</strong> 6단계 점진 난이도 러너, 1판 1장 차감, 장애물 충돌 시 즉시 종료.</div>
            <div><strong>복주머니 추첨:</strong> 정상 완료 게임당 3개 주머니 중 1개 선택 후 캔버스 복권을 긁어 즉석 결과 확인 (100% 꽝 없는 보너스).</div>
            <div><strong>부정행위 방지:</strong> 모든 점수는 서버 시뮬레이터를 통해 물리 재현 검증을 거치며, 변조된 점수는 랭킹에서 자동 제외됩니다.</div>
            <div><strong>경품 수령 기한:</strong> 당첨 후 72시간 이내 수령 정보를 접수해야 합니다.</div>
          </div>
        </div>
      </div>
    `;

    // Analytics: Benefit Link Click
    container.querySelector('#btn-go-benefit').onclick = () => {
      api.logEvent('benefit_link_clicked', { source: 'benefit_view' });
    };

    // Request Benefit Verification
    const verifyStatusEl = container.querySelector('#benefit-verify-status');
    container.querySelector('#btn-request-verify').onclick = async () => {
      try {
        const res = await api.verifyBenefit();
        verifyStatusEl.innerHTML = `<span class="sticker-badge badge-yellow">접수 완료: ${res.message}</span>`;
        ui.showToast('등록 확인이 접수되었습니다.');
      } catch (err) {
        ui.showToast(err.message || '확인 접수에 실패했습니다.');
      }
    };
  }
};
