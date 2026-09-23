import { api } from '/js/api.js';
import { HomeView } from '/js/views/home.js';
import { GameView } from '/js/views/game_view.js';
import { ResultView } from '/js/views/result_view.js';
import { DrawView } from '/js/views/draw_view.js';
import { PrizeView } from '/js/views/prize_view.js';
import { RankingView } from '/js/views/ranking_view.js';
import { InviteView } from '/js/views/invite_view.js';
import { BenefitView } from '/js/views/benefit_view.js';
import { GameChoiceModal } from '/js/components/game_choice_modal.js';
import { audio } from '/js/game/audio.js';
import { MOCK, STATES } from './fixtures.js';
const state = new URLSearchParams(location.search).get('state') || 'home';
const wait = ms => new Promise(r => setTimeout(r, ms));
const won = { draw_id:'fixture-draw',is_won:true,prize:{name:'메가커피 아메리카노',category:'COUPON',image_url:'/assets/icons/Smile-Light.png'} };
MOCK.leaderboard.my_card=MOCK.leaderboard.leaderboard[1];
MOCK.claims.claims.push({id:'fixture-shipping',prize_name:'Team Gemini 굿즈',category:'GOODS',status:'READY',created_at:1789776000,image_url:'/assets/icons/Picture-Dark.png'});
MOCK.claims.claims.push({...MOCK.claims.claims[0],id:'fixture-issued',status:'ISSUED',coupon_code:'DEMO-CAFE-2026'});
MOCK.referral={summary:{qualified_count:4,daily_earned:2},invite_url:'/?invite=DEMO'};
Object.assign(api, {
 participant:MOCK.participant,token:'fixture',
 request:async()=>{throw Error('시각 검토 fixture에서는 실제 API 호출을 차단합니다.');},
 getMe:async()=>MOCK.me,getLeaderboard:async()=>MOCK.leaderboard,
 getClaims:async()=>state==='claims-empty'?{claims:[]}:MOCK.claims,
 getReferralInfo:async()=>MOCK.referral,
 createSession:async()=>({session_id:'fixture-session',seed:2026}),
 startSession:async()=>({}),finishSession:async()=>({score:1280,best_score:1280,rank:2}),
 drawPouch:async()=>won,completeScratch:async()=>({}),submitClaim:async()=>({}),
 verifyBenefit:async()=>({message:'화면 검토용 접수 예시'}),logEvent:async()=>({})
});
// Suppress only sound, never change the product templates or layout.
for(const key of Object.keys(audio))if(key.startsWith('play')&&typeof audio[key]==='function')audio[key]=()=>{};
const router={state:{tickets:3,bestScore:1280,lastResult:{sessionId:'fixture-session',score:1280,bestScore:1280,rank:2}},navigate:()=>{},updateNav:()=>{}};
async function shell(url){
 const parsed=new DOMParser().parseFromString(await (await fetch(url)).text(),'text/html');
 parsed.querySelectorAll('script').forEach(n=>n.remove());
 document.body.replaceChildren(...[...parsed.body.children].map(n=>document.importNode(n,true)));
}
async function gate(){
 await shell('/gate_runner.html');
 const script=document.createElement('script');script.src='/js/game/gate_runner.js';
 await new Promise((resolve,reject)=>{script.onload=resolve;script.onerror=reject;document.body.append(script);});
 await wait(180);
 if(state!=='gate-ready'){
  document.querySelector('#btn-start').click();await wait(700);
  document.querySelector('#btn-pause').click();
  if(state!=='gate-paused')document.querySelector('#pause-screen').hidden=true;
 }
 if(state==='gate-result')document.querySelector('#result-modal').style.display='flex';
}
async function main(){
 if(state.startsWith('gate-')){await gate();return;}
 await shell('/index.html');
 document.querySelector('#splash-screen').remove();
 document.querySelector('#header-ticket-pill').textContent='🎟️ 무제한';
 const el=document.querySelector('#view-container');
 const views={home:HomeView,game:GameView,result:ResultView,draw:DrawView,claims:PrizeView,ranking:RankingView,invite:InviteView,benefit:BenefitView};
 const key=state.startsWith('game-')?'game':state.startsWith('claims-')||['claim-form','coupon-modal'].includes(state)?'claims':state==='nickname'?'result':['choice','guide'].includes(state)?'home':['pouch','pouch-selected','scratch','reveal','reveal-benefit'].includes(state)?'draw':state.startsWith('ranking-')?'ranking':state==='benefit-confirmed'?'benefit':state;
 if(state==='claims-error')api.getClaims=async()=>{throw Error('Fixture error');};
 if(state==='ranking-empty')api.getLeaderboard=async()=>({leaderboard:[]});
 if(state==='ranking-error')api.getLeaderboard=async()=>{throw Error('Fixture error');};
 document.querySelectorAll('.nav-item').forEach(n=>n.classList.toggle('active',n.dataset.view===key));
 if(key==='game')GameView.runCountdown=(_seconds,_cb,overlay,num)=>{overlay.classList.add('active');num.textContent='3';};
 if(!views[key])throw Error('Unsupported fixture state '+state);
 await views[key].render(el,router);
 if(state==='choice')GameChoiceModal.open(router);
 if(state==='guide')HomeView.showGuideModal(router,true);
 if(state==='nickname')ResultView.showNicknameModal(MOCK.participant,router);
 if(state==='claim-form')PrizeView.showClaimModal('fixture-shipping','GOODS',router);
 if(state==='coupon-modal')PrizeView.showClaimModal('fixture-claim','COUPON',router);
 if(state==='pouch-selected')el.querySelectorAll('.pouch-item')[1].click();
 if(['scratch','reveal','reveal-benefit'].includes(state)){
  el.querySelector('#pouch-select-stage').style.display='none';
  el.querySelector('#scratch-stage').style.display='flex';
  DrawView.initScratchTicket(el,router,state==='reveal-benefit'?{draw_id:'fixture-benefit',is_won:false}:won);
  if(state!=='scratch'){
   el.querySelector('#btn-instant-reveal').click();await wait(650);
   document.querySelector('#toast')?.classList.remove('show');
  }
 }
 if(key==='game'){
  const engine=GameView.engine;engine.start(2026);engine.stop();
  await engine.dinoImg.decode().catch(()=>{});
  if(state!=='game-ready'){
   for(let i=0;i<100;i++)engine.updateSimulationTick();
   el.querySelector('#countdown-overlay').classList.remove('active');
  }
  engine.render();
  if(state==='game-paused'){
   engine.pause();el.querySelector('#countdown-overlay').classList.add('active');
   el.querySelector('#countdown-num').textContent='3';
  }
 }
 if(state==='benefit-confirmed'){
  el.querySelector('#btn-request-verify').click();await wait(50);document.querySelector('#toast')?.classList.remove('show');
 }
}
try{
 await main();
 await Promise.all([...document.images].map(i=>i.decode().catch(()=>{})));
 await wait(120);
 document.body.dataset.state=state;document.body.dataset.ready='true';
 document.title='화면 검토 · '+(STATES[state]||state);
 if(location.hash.includes('figmacapture=')){
  const style=document.createElement('style');style.textContent='#app-container{width:440px;height:956px;min-height:956px;margin:0}#app-container .bottom-nav{position:absolute;bottom:0}';document.head.append(style);
  const script=document.createElement('script');script.src='https://mcp.figma.com/mcp/html-to-design/capture.js';script.async=true;document.head.append(script);
 }
}catch(e){document.body.dataset.error=e.message;document.body.dataset.ready='error';console.error(e);}
