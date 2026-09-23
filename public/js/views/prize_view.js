/**
 * S06 Winning / S07 Non-winning / S09 Prize Claim Box View Component
 */

import { api } from '../api.js';
import { ui } from '../ui.js';

export const PrizeView = {
  async render(container, router) {
    container.innerHTML = `
      <div style="display: flex; flex-direction: column; gap: 16px;">
        <div class="card" style="padding: 20px;">
          <div style="display: flex; justify-content: space-between; align-items: center; margin-bottom: 8px;">
            <h2 style="font-size: 20px; font-weight: 900;">🎁 내 경품 수령함</h2>
            <span class="sticker-badge badge-blue">72시간 이내 수령</span>
          </div>
          <p style="font-size: 13px; color: var(--text-sub);">
            복주머니 스크래치에서 당첨된 모바일 쿠폰과 굿즈를 확인하세요.
          </p>
        </div>

        <!-- Claims List Container -->
        <div id="claims-list-container" style="display: flex; flex-direction: column; gap: 12px;">
          <div style="text-align: center; padding: 40px 0; color: var(--text-sub);">
            수령함 내역을 불러오는 중...
          </div>
        </div>
      </div>
    `;

    const listContainer = container.querySelector('#claims-list-container');
    try {
      const res = await api.getClaims();
      const claims = res.claims || [];

      if (claims.length === 0) {
        listContainer.innerHTML = `
          <div class="card" style="text-align: center; padding: 40px 20px;">
            <div style="font-size: 48px; margin-bottom: 12px;">📦</div>
            <div style="font-size: 16px; font-weight: 700; color: var(--text-main); margin-bottom: 6px;">
              아직 당첨된 경품이 없어요
            </div>
            <p style="font-size: 13px; color: var(--text-sub); margin-bottom: 20px;">
              공룡 점프 게임을 완료하고 복주머니를 열어보세요!
            </p>
            <button id="btn-empty-play" class="btn btn-primary btn-sm">
              🦖 게임 시작하러 가기
            </button>
          </div>
        `;
        listContainer.querySelector('#btn-empty-play').onclick = () => {
          router.navigate('home');
        };
        return;
      }

      listContainer.innerHTML = claims.map((claim) => {
        const isCoupon = claim.category === 'COUPON';
        const isIssued = claim.status === 'ISSUED';

        return `
          <div class="card" style="padding: 16px;">
            <div style="display: flex; gap: 14px; align-items: center;">
              <div style="width: 60px; height: 60px; border-radius: 14px; background: #F8FAFF; border: 1px solid rgba(0,0,0,0.06); display: flex; align-items: center; justify-content: center;">
                <img src="${claim.image_url || '/assets/icons/Picture-Dark.png'}" alt="Prize" style="width: 44px; height: 44px; object-fit: contain;">
              </div>
              <div style="flex: 1;">
                <div style="display: flex; justify-content: space-between; align-items: center;">
                  <span class="sticker-badge ${isIssued ? 'badge-green' : 'badge-yellow'}" style="font-size: 11px;">
                    ${isIssued ? '발급 완료' : '수령 대기'}
                  </span>
                  <span style="font-size: 11px; color: var(--text-sub);">
                    ${new Date(claim.created_at * 1000).toLocaleDateString()}
                  </span>
                </div>
                <div style="font-size: 16px; font-weight: 800; color: var(--text-main); margin: 4px 0;">
                  ${claim.prize_name}
                </div>
                <div style="font-size: 12px; color: var(--text-sub);">
                  ${isCoupon ? '모바일 즉시 교환권' : '택배 배송 상품'}
                </div>
              </div>
            </div>

            <!-- Action Area -->
            <div style="margin-top: 14px; padding-top: 12px; border-top: 1px dashed rgba(0,0,0,0.08);">
              ${isIssued && claim.coupon_code ? `
                <div style="display: flex; gap: 8px; align-items: center; background: #F8FAFF; padding: 10px 12px; border-radius: 12px; border: 1px solid rgba(25, 103, 210, 0.15);">
                  <div style="flex: 1; font-family: monospace; font-size: 15px; font-weight: 800; color: var(--primary);">
                    ${claim.coupon_code}
                  </div>
                  <button class="btn btn-primary btn-sm btn-copy-code" data-code="${claim.coupon_code}" style="width: auto; padding: 6px 14px; min-height: 36px;">
                    복사
                  </button>
                </div>
              ` : `
                <button class="btn btn-primary btn-sm btn-claim-submit" data-id="${claim.id}" data-category="${claim.category}">
                  ${isCoupon ? '⚡ 쿠폰 코드 발급받기' : '📦 배송지 정보 입력하기'}
                </button>
              `}
            </div>
          </div>
        `;
      }).join('');

      // Copy Code Handlers
      listContainer.querySelectorAll('.btn-copy-code').forEach((btn) => {
        btn.onclick = () => {
          const code = btn.dataset.code;
          navigator.clipboard.writeText(code).then(() => {
            ui.showToast('쿠폰 번호가 복사되었습니다!');
          }).catch(() => {
            ui.showToast(`쿠폰 번호: ${code}`);
          });
        };
      });

      // Claim Submit Handlers
      listContainer.querySelectorAll('.btn-claim-submit').forEach((btn) => {
        btn.onclick = () => {
          const claimId = btn.dataset.id;
          const category = btn.dataset.category;
          this.showClaimModal(claimId, category, router);
        };
      });

    } catch (err) {
      listContainer.innerHTML = `
        <div class="card" style="text-align: center; color: #EA4335;">
          수령함 목록을 불러오지 못했습니다.
        </div>
      `;
    }
  },

  showClaimModal(claimId, category, router) {
    const isCoupon = category === 'COUPON';

    const formHtml = isCoupon ? `
      <div style="text-align: left; font-size: 14px;">
        <p style="margin-bottom: 12px;">즉시 바코드 / 쿠폰 코드를 발급받으시겠습니까?</p>
      </div>
    ` : `
      <div style="display: flex; flex-direction: column; gap: 10px; text-align: left;">
        <input id="claim-name" type="text" placeholder="수령인 성함" style="width: 100%; padding: 10px; border: 1px solid #CCC; border-radius: 10px;">
        <input id="claim-phone" type="tel" placeholder="연락처 (010-0000-0000)" style="width: 100%; padding: 10px; border: 1px solid #CCC; border-radius: 10px;">
        <input id="claim-addr" type="text" placeholder="상세 배송지 주소" style="width: 100%; padding: 10px; border: 1px solid #CCC; border-radius: 10px;">
      </div>
    `;

    ui.showModal({
      title: isCoupon ? '쿠폰 즉시 발급' : '배송지 정보 입력',
      content: formHtml,
      confirmText: '발급 완료',
      onConfirm: async () => {
        let name = '', phone = '', addr = '';
        if (!isCoupon) {
          name = document.getElementById('claim-name')?.value || '';
          phone = document.getElementById('claim-phone')?.value || '';
          addr = document.getElementById('claim-addr')?.value || '';
          if (!name || !phone || !addr) {
            ui.showToast('모든 항목을 입력해주세요.');
            return;
          }
        }
        try {
          await api.submitClaim(claimId, {
            recipient_name: name,
            contact_phone: phone,
            shipping_address: addr
          });
          ui.showToast(isCoupon ? '쿠폰 코드가 발급되었습니다!' : '배송지 접수가 완료되었습니다.');
          router.navigate('claims');
        } catch (err) {
          ui.showToast(err.message || '수령 처리에 실패했습니다.');
        }
      },
      cancelText: '취소'
    });
  }
};
