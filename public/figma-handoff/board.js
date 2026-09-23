const groups = [
 ['01 · 시작과 홈','처음 진입 → 홈 → 종목 선택 / 조작 가이드',[['home','홈','주 CTA, 보상 안내, 5개 하단 메뉴'],['choice','종목 선택 팝업','클래식 점프 / 게이트 러너 분기'],['guide','조작 가이드','게임 시작 전 안내와 취소 동선']]],
 ['02 · 클래식 점프','준비 → 플레이 → 탭 복귀 카운트다운 → 게임 결과',[['game-ready','시작 카운트다운','입력 방법과 준비 상태'],['game-playing','게임 진행','점수 · 난이도 · JUMP 조작'],['game-paused','탭 복귀 카운트다운','탭 전환 후 복귀 시 3초 카운트다운 · 별도 정지 UI 없음']]],
 ['03 · 기록 결과','검증 결과 → 닉네임 변경 / 복주머니 / 친구 초대',[['result','게임 결과','검증 완료, 현재/최고 점수와 순위'],['nickname','닉네임 수정 팝업','입력 제약과 확인/취소 버튼']]],
 ['04 · 복주머니와 복권','주머니 선택 → 개봉 → 스크래치 → 결과 → 수령함',[['pouch','주머니 선택 전','열기 버튼 비활성 상태'],['pouch-selected','주머니 선택 후','선택 강조와 열기 버튼 활성'],['scratch','스크래치 전','은색 코팅과 한 번에 확인하기'],['reveal','경품 공개','결과 확인 후 수령함으로 이동']]],
 ['05 · 경품 수령함','목록 → 수령 정보 → 발급/배송 · 빈 상태',[['claims-empty','수령함 · 비어 있음','경품이 없는 초기 상태'],['claims-filled','수령함 · 경품 있음','쿠폰과 배송형 경품 예시'],['claim-form','수령 정보 입력','실제 개인정보를 포함하지 않는 예시 폼']]],
 ['06 · 랭킹','하단 메뉴 → 내 순위 / 전체 순위',[['ranking','랭킹','순위와 내 기록 · 예시 데이터']]],
 ['07 · 친구 초대','결과 / 하단 메뉴 → 초대 링크 공유 → 친구 진입',[['invite','친구 초대','추천 링크와 초대 현황 · 예시 데이터']]],
 ['08 · 혜택 안내','복권 혜택 결과 / 하단 메뉴 → 외부 안내',[['benefit','혜택 안내','외부 이동 CTA와 확인 요청을 구분']]],
 ['09 · 게이트 러너','종목 선택 → 시작 → 플레이 → 일시정지 / 결과',[['gate-ready','게이트 · 시작','게임 02의 별도 진입 화면'],['gate-playing','게이트 · 진행','좌우 이동과 군단 수 HUD'],['gate-paused','게이트 · 일시정지','계속 달리기'],['gate-result','게이트 · 결과','다시 도전 / 점프 게임 복귀']]]
];
const status=document.querySelector('#status');
const capture=document.querySelector('#capture');
const total=groups.reduce((sum,g)=>sum+g[2].length,0);
const jump=document.querySelector('#jump');
const zoom=document.querySelector('#zoom');
jump.onchange=()=>document.getElementById(jump.value)?.scrollIntoView({behavior:'smooth',block:'start'});
zoom.onchange=()=>document.querySelector('#board').style.zoom=zoom.value;
const failures=[];
function copyNode(node,win){
 if(node.nodeType===3)return document.createTextNode(node.textContent);
 if(node.nodeType!==1 || ['SCRIPT','STYLE','LINK'].includes(node.tagName))return null;
 const cs=win.getComputedStyle(node);if(cs.display==='none')return null;
 let clone;
 if(node.tagName==='CANVAS'){clone=document.createElement('img');clone.src=node.toDataURL();clone.alt='캔버스 장면 · 시각 참고';}
 else clone=node.cloneNode(false);
 clone.removeAttribute('id');clone.removeAttribute('onclick');
 for(const p of cs)clone.style.setProperty(p,cs.getPropertyValue(p));
 clone.style.animation='none';clone.style.transition='none';
 if(node.tagName==='IMG')clone.src=node.currentSrc||node.src;
 if(node.tagName==='INPUT')clone.setAttribute('value',node.value);
 if(cs.position==='fixed'||cs.position==='sticky'){
   const rect=node.getBoundingClientRect();clone.style.position='absolute';clone.style.left=rect.x+'px';clone.style.top=rect.y+'px';clone.style.right='auto';clone.style.bottom='auto';clone.style.transform='none';clone.style.width=rect.width+'px';clone.style.height=rect.height+'px';
 }
 if(node.tagName!=='CANVAS')for(const child of node.childNodes){const c=copyNode(child,win);if(c)clone.append(c);}
 return clone;
}
const wait=ms=>new Promise(r=>setTimeout(r,ms));
let count=0;
for(const [title,description,states] of groups){
 const row=document.createElement('section');row.className='row';row.id='group-'+title.slice(0,2);row.style.scrollMarginTop='90px';row.innerHTML=`<h2>${title}</h2><p class="group-note">${description}</p><div class="screens"></div>`;document.querySelector('#groups').append(row);
 const option=document.createElement('option');option.value=row.id;option.textContent=title;jump.append(option);
 for(const [state,label,desc] of states){
  status.textContent=`화면 준비 중 ${++count} / ${total} · ${label}`;
  const card=document.createElement('article');card.className='screen-card';card.dataset.state=state;card.setAttribute('aria-label',label);card.innerHTML=`<div class="screen-label">${String(count).padStart(2,'0')} / ${label}</div><div class="phone"></div><div class="screen-desc">${desc}</div>`;row.querySelector('.screens').append(card);
  const iframe=document.createElement('iframe');iframe.className='source-frame';iframe.src=`./render.html?state=${state}`;document.body.append(iframe);
  await new Promise((resolve,reject)=>{iframe.onload=resolve;iframe.onerror=reject;});
  for(let i=0;i<120&&!iframe.contentDocument.body.dataset.ready;i++)await wait(100);
  if(iframe.contentDocument.body.dataset.ready!=='true'){failures.push(state);card.querySelector('.phone').textContent='화면 준비 오류: '+(iframe.contentDocument.body.dataset.error||state);iframe.remove();continue;}
  const isModal=['choice','guide','nickname','claim-form'].includes(state)||state.startsWith('game')||state.startsWith('gate');
  if(!isModal){iframe.style.height=Math.max(956,iframe.contentDocument.documentElement.scrollHeight)+'px';await wait(100);}
  const doc=iframe.contentDocument,win=iframe.contentWindow;
  await Promise.all([...doc.images].map(i=>i.decode().catch(()=>{})));
  const phone=card.querySelector('.phone');phone.style.height=iframe.clientHeight+'px';
  for(const child of doc.body.children){if(child.hasAttribute('data-handoff-label'))continue;const clone=copyNode(child,win);if(clone)phone.append(clone);}
  iframe.remove();
 }
}
await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));
status.textContent=failures.length?`완료 ${count-failures.length} / ${count} · 오류 ${failures.join(', ')}`:`${count}개 화면 준비 완료 · 편집 가능한 UI 레이어`;
document.body.dataset.ready=failures.length?'partial':'true';capture.disabled=!!failures.length;
// Load direct capture only after every state and image has finished rendering.
if(!failures.length&&location.hash.includes('figmacapture=')){
 const script=document.createElement('script');script.src='https://mcp.figma.com/mcp/html-to-design/capture.js';script.async=true;document.head.append(script);
}
capture.onclick=()=>{
 zoom.value='1';document.querySelector('#board').style.zoom='1';
 location.hash='figmacapture&figmaselector=%23board';
 const s=document.createElement('script');s.src='https://mcp.figma.com/mcp/html-to-design/capture.js';s.async=true;document.head.append(s);
 capture.disabled=true;
};
