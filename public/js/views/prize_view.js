import { api } from '../api.js';
import { ui } from '../ui.js';
import { track } from '../analytics.js';

function make(tag, text, css = '') { const node = document.createElement(tag); if (text != null) node.textContent = String(text); if (css) node.style.cssText = css; return node; }

export const PrizeView = {
  abortController: null,
  async render(container, router, epoch) {
    this.cleanup(); this.abortController = new AbortController();
    container.innerHTML = '<div style="display:flex;flex-direction:column;gap:16px"><div class="card" style="padding:20px"><div style="display:flex;justify-content:space-between;align-items:center;margin-bottom:8px"><h2 style="font-size:20px;font-weight:900">🎁 내 경품 수령함</h2><span class="sticker-badge badge-blue">미완료 수령 재확인</span></div><p style="font-size:13px;color:var(--text-sub)">테스트 추첨 결과와 접수 상태를 확인하세요. 접수 완료는 실제 발송 완료를 뜻하지 않습니다.</p></div><div id="claims-list-container" style="display:flex;flex-direction:column;gap:12px"><div style="text-align:center;padding:40px 0;color:var(--text-sub)">수령함 내역을 불러오는 중...</div></div></div>';
    const list = container.querySelector('#claims-list-container');
    try {
      const data = await api.getClaims({ signal: this.abortController.signal }); if (!router.isCurrent(epoch,'claims')) return;
      const claims = data.claims || []; list.replaceChildren();
      if (!claims.length) { const empty=make('div',null,'text-align:center;padding:40px 20px'); empty.className='card'; empty.append(make('div','📦','font-size:48px;margin-bottom:12px'),make('div','아직 수령할 테스트 경품이 없어요','font-size:16px;font-weight:700;margin-bottom:6px')); const btn=make('button','🦖 게임 시작하러 가기');btn.className='btn btn-primary btn-sm';btn.onclick=()=>router.navigate('home');empty.append(btn);list.append(empty);return; }
      claims.forEach(claim => list.append(this.claimCard(claim, router, epoch)));
    } catch (error) { if(error.name!=='AbortError'){ list.replaceChildren(make('div','수령함을 불러오지 못했습니다. 잠시 뒤 다시 열어 주세요.','text-align:center;color:#EA4335')); } }
  },
  claimCard(claim, router, epoch) {
    const card=make('div');card.className='card';card.style.padding='16px';
    const top=make('div',null,'display:flex;justify-content:space-between;gap:12px');
    const info=make('div'); info.append(make('div',claim.is_test?'개발용 테스트 경품':'행사 경품','font-size:11px;color:var(--primary);font-weight:700'),make('div',claim.prize_name||'경품','font-size:16px;font-weight:800;margin:4px 0'),make('div',`상태: ${claim.status || 'PENDING'}`,'font-size:12px;color:var(--text-sub)'));
    top.append(info,make('div',this.formatDate(claim.expires_at),'font-size:11px;color:var(--text-sub)'));card.append(top);
    const action=make('div',null,'margin-top:14px;padding-top:12px;border-top:1px dashed rgba(0,0,0,.08)');
    if (['ISSUED','TEST_ISSUED'].includes(claim.status) && claim.coupon_code) { const code=make('div',claim.coupon_code,'font-family:monospace;font-weight:800'); const copy=make('button','복사');copy.className='btn btn-primary btn-sm';copy.onclick=()=>navigator.clipboard.writeText(claim.coupon_code).then(()=>ui.showToast('테스트 쿠폰 번호를 복사했습니다.'));action.append(code,copy); }
    else if (!['SUBMITTED','DELIVERY_PENDING','DELIVERED','TEST_ISSUED','ISSUED','EXPIRED','VOID'].includes(claim.status)) { const button=make('button',claim.is_test?'테스트 수령 정보 접수':'수령 정보 접수');button.className='btn btn-primary btn-sm';button.onclick=()=>this.showClaimModal(claim,router,epoch);action.append(button); }
    else action.append(make('div',claim.status==='SUBMITTED'?'접수되었습니다. 실제 발송 완료 상태는 아닙니다.':'처리 상태를 확인해 주세요.','font-size:12px;color:var(--text-sub)'));
    card.append(action);return card;
  },
  formatDate(value){if(!value)return '기한 확인 필요';const ms=typeof value==='number'?value*1000:Date.parse(value);return Number.isFinite(ms)?`기한 ${new Date(ms).toLocaleString('ko-KR')}`:'기한 확인 필요';},
  showClaimModal(claim, router, epoch) {
    const isNonProduction=api.config?.environment!=='production'; const wrapper=make('div');
    wrapper.append(make('p',isNonProduction?'개발 환경에서는 합성 개인정보만 접수합니다. 아래 테스트 값으로 정합성을 확인합니다.':'수령에 필요한 정보를 입력해 주세요.','margin-bottom:10px'));
    const fields=[['recipient_name','수령인',isNonProduction?'TEST_USER':''],['contact_phone','연락처',isNonProduction?'01000000000':''],['shipping_address','주소',isNonProduction?'TEST_ADDRESS':'']];
    for(const [id,label,value] of fields){const input=document.createElement('input');input.id=`claim-${id}`;input.value=value;input.placeholder=label;input.readOnly=isNonProduction;input.style.cssText='width:100%;padding:10px;margin:4px 0;border:1px solid #ccc;border-radius:10px';wrapper.append(input);}
    track('claim_start',{screen:'claims'});
    ui.showModal({title:claim.is_test?'테스트 수령 접수':'경품 수령 접수',content:wrapper,confirmText:'접수',onConfirm:async()=>{const values={};for(const [id]of fields)values[id]=document.getElementById(`claim-${id}`)?.value.trim()||'';if(Object.values(values).some(v=>!v)){ui.showToast('필수 항목을 입력해 주세요.');return false;}try{await api.submitClaim(claim.id,values,{signal:this.abortController.signal});if(!router.isCurrent(epoch,'claims'))return false;ui.showToast('수령 정보가 접수되었습니다.');router.navigate('claims');}catch(error){if(error.name!=='AbortError')ui.showToast(error.message||'접수에 실패했습니다. 다시 시도해 주세요.');return false;}},cancelText:'취소'});
  },
  cleanup(){this.abortController?.abort();this.abortController=null;}
};
