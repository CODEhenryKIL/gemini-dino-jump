import { api } from './api.js';
import { ui } from './ui.js';
import { initAnalytics, page, track } from './analytics.js';
import { HomeView } from './views/home.js';
import { GameView } from './views/game_view.js';
import { ResultView } from './views/result_view.js';
import { DrawView } from './views/draw_view.js';
import { PrizeView } from './views/prize_view.js';
import { RankingView } from './views/ranking_view.js';
import { InviteView } from './views/invite_view.js';
import { BenefitView } from './views/benefit_view.js';

export class AppRouter {
  constructor() {
    this.container = document.getElementById('view-container'); this.ticketPill = document.getElementById('header-ticket-pill');
    this.currentView = null; this.navigationEpoch = 0; this.state = { tickets: 0, bestScore: 0, lastResult: null, campaign: null, config: null };
    this.views = { home: HomeView, game: GameView, result: ResultView, draw: DrawView, claims: PrizeView, ranking: RankingView, invite: InviteView, benefit: BenefitView };
  }
  async init() { this.bindNavigation(); const splash = this.runSplashScreen(1000); await this.initializeRemoteState(); await splash; this.hideSplashScreen(); }
  async initializeRemoteState() {
    const params = new URLSearchParams(location.search); const invite = params.get('invite'); const channel = params.get('channel');
    try {
      this.state.config = await api.getConfig();
      const participantResponse = await api.initParticipant(invite, channel);
      this.state.campaign = await api.getCampaign();
      const me = participantResponse.participant && 'tickets' in participantResponse ? participantResponse : await api.getMe();
      this.applyMe(me); initAnalytics();
      if (invite && participantResponse.referral_applied) ui.showToast('친구 추천이 적용되었습니다.');
      await this.recoverPendingFinish();
      if (!api.getPendingFinish()) this.applyMe(await this.closeInterruptedSession());
      const requested = params.get('view'); const allowed = ['home','ranking','claims','invite','benefit']; this.navigate(allowed.includes(requested) ? requested : 'home');
    } catch (error) { track('client_error', { screen: 'startup', error_code: error.code || 'INIT_FAILED' }); this.renderStartupError(error); }
  }
  applyMe(me) {
    if (me.participant) api.setSession(me.participant); this.state.tickets = Number(me.tickets || 0); this.state.bestScore = Number(me.best_score || 0);
    const pending = me.pending_draw; if (pending) this.state.lastResult = { sessionId: pending.session_id || pending.id, score: pending.score || 0, bestScore: this.state.bestScore, draw: pending.draw || null, eligibleForDraw: true };
    this.updateNav();
  }
  async closeInterruptedSession() {
    const current = await api.getMe(); const active = current?.active_session; if (!active?.id) return current;
    await api.abortSession(active.id);
    const refreshed = await api.getMe();
    ui.showToast('새로고침으로 중단된 이전 게임을 종료했습니다. 사용한 티켓은 복구되지 않습니다.');
    return refreshed;
  }
  async recoverPendingFinish() {
    const pending = api.getPendingFinish(); if (!pending?.session_id) return;
    try { const session = await api.getSession(pending.session_id); if (session.result) { api.clearPendingFinish(); this.state.lastResult = this.resultState(session.result,pending.session_id); } else if (session.status === 'ACTIVE') { const result = await api.finishSession(pending.session_id,pending,{version:pending.version}); this.state.lastResult=this.resultState(result,pending.session_id); } else api.clearPendingFinish(); }
    catch (error) { const terminal = new Set(['SESSION_EXPIRED','SESSION_NOT_ACTIVE','GAME_VERSION_MISMATCH']); if ([404,410,422].includes(error.status)||terminal.has(error.code)) api.clearPendingFinish(); }
  }
  resultState(result, sessionId) { return { sessionId, score: result.score, bestScore: result.best_score, rank: result.rank, verificationResult: result.verification_result, eligibleForDraw: Boolean(result.eligible_for_draw) }; }
  renderStartupError(error) {
    this.container.innerHTML = '<div class="card" style="text-align:center;padding:28px 20px"><h2 style="font-size:20px;margin-bottom:10px">서버에 연결하지 못했습니다</h2><p style="font-size:14px;color:var(--text-sub);margin-bottom:18px">저장 기능을 사용할 수 없어 게임을 시작하지 않았습니다. 연결을 확인한 뒤 다시 시도해 주세요.</p><button id="btn-retry-init" class="btn btn-primary">다시 연결</button></div>';
    this.ticketPill.textContent = '🎟️ 연결 필요'; this.container.querySelector('#btn-retry-init').onclick = () => { this.container.textContent='다시 연결하는 중...'; this.initializeRemoteState(); };
    if (error?.requestId) this.container.querySelector('p').title = `요청 ${error.requestId}`;
  }
  bindNavigation() { document.querySelectorAll('.bottom-nav .nav-item').forEach(item => item.addEventListener('click',e => { e.preventDefault(); this.navigate(item.dataset.view); })); }
  runSplashScreen(durationMs) { return new Promise(resolve => { const bar=document.getElementById('splash-progress-bar'); if(!bar)return resolve(); const start=performance.now(); const timer=setInterval(()=>{ const p=Math.min((performance.now()-start)/durationMs,1); bar.style.width=`${p*100}%`; if(p>=1){clearInterval(timer);resolve();}},50); }); }
  hideSplashScreen() { const splash=document.getElementById('splash-screen'); if(splash){splash.classList.add('fade-out');setTimeout(()=>{splash.style.display='none';},500);} }
  isCurrent(epoch,view){return epoch===this.navigationEpoch&&this.currentView===view;}
  async refreshMe(){const me=await api.getMe();this.applyMe(me);return me;}
  navigate(viewName) {
    if(!this.views[viewName])viewName='home'; const prior=this.currentView; if(prior&&this.views[prior]?.cleanup)this.views[prior].cleanup(); ui.hideModal(); this.currentView=viewName; const epoch=++this.navigationEpoch;
    document.querySelectorAll('.bottom-nav .nav-item').forEach(item=>item.classList.toggle('active',item.dataset.view===viewName)); this.container.replaceChildren(); page(viewName);
    Promise.resolve(this.views[viewName].render(this.container,this,epoch)).catch(error=>{if(this.isCurrent(epoch,viewName)){track('client_error',{screen:viewName,error_code:error.code||'RENDER_FAILED'});ui.showToast(error.message||'화면을 불러오지 못했습니다.');}}); scrollTo({top:0,behavior:'smooth'});
  }
  updateNav(){if(this.ticketPill)this.ticketPill.textContent=`🎟️ ${Math.max(0,this.state.tickets)}장`;}
}
document.addEventListener('DOMContentLoaded',()=>{const router=new AppRouter();router.init();window.__geminiRouter=router;});
