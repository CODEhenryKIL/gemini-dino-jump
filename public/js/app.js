import { api } from './api.js';
import { analytics } from './analytics.js';
import { startVercelAnalytics } from './vercel_analytics.js';
import { ui } from './ui.js';
import { HomeView } from './views/home.js';
import { GameView } from './views/game_view.js';
import { ResultView } from './views/result_view.js';
import { DrawView } from './views/draw_view.js';
import { PrizeView } from './views/prize_view.js';
import { RankingView } from './views/ranking_view.js';
import { InviteView } from './views/invite_view.js';
import { BenefitView } from './views/benefit_view.js';

class AppRouter {
  constructor() {
    this.container = document.getElementById('view-container');
    this.ticketPill = document.getElementById('header-ticket-pill');
    this.currentView = null;
    this.renderToken = 0;
    this.initialized = false;
    this.inviteVisit = null;
    this.state = {
      participant: null,
      tickets: { initial: 0, invitation: 0, invitation_reserved: 0, available_total: 0, cooldown_until: null },
      bestScore: 0,
      rank: null,
      lastResult: null,
      draw: { status: 'LOCKED' },
      top3Profile: { required: false, status: 'NOT_REQUIRED' },
    };
    this.views = { home: HomeView, game: GameView, result: ResultView, draw: DrawView, claims: PrizeView, ranking: RankingView, invite: InviteView, benefit: BenefitView };
    this.channel = typeof BroadcastChannel === 'function' ? new BroadcastChannel('dino-state') : null;
    this.channel?.addEventListener('message', () => this.refreshState({ quiet: true }));
  }

  async init() {
    this.bindNavigation();
    const url = new URL(window.location.href);
    const pathInvite = url.pathname.match(/^\/invite\/([A-Za-z0-9_-]{12,64})$/);
    const inviteCode = url.searchParams.get('invite') || pathInvite?.[1] || null;
    const requestedView = url.searchParams.get('view');
    const requestedLinkKind = url.searchParams.get('link');
    const linkKind = inviteCode
      ? (requestedLinkKind === 'prize_share' ? 'prize_share' : 'retry_invite')
      : (requestedLinkKind === 'initial' ? 'initial' : 'direct');
    const shareId = (url.searchParams.get('share') || '').match(/^[A-Za-z0-9:_-]{8,128}$/)?.[0] || null;
    const channelCode = (url.searchParams.get('channel') || '').match(/^[A-Za-z][A-Za-z0-9_-]{0,31}$/)?.[0] || null;
    const campaignCode = (url.searchParams.get('campaign') || '').match(/^[A-Za-z][A-Za-z0-9_-]{0,31}$/)?.[0] || null;
    if (url.pathname !== '/' || url.search) history.replaceState({}, '', '/');
    analytics.setEntryAttribution({ link_kind: linkKind, channel: channelCode || 'unknown', campaign_code: campaignCode || '', share_id: shareId || '' });
    const observation = {
      observation_id: analytics.observationId,
      event_id: api.createRequestId('evt'),
      link_kind: linkKind,
      channel_code: channelCode,
      campaign_code: campaignCode,
      share_id: shareId,
    };
    try {
      const observationRequest = api.startObservation(observation).then((observed) => {
        analytics.setObservationReady();
        return observed;
      });
      const [observed, config] = await Promise.all([observationRequest, api.getConfig()]);
      const initialize = () => api.initParticipant({ inviteCode, observationId: analytics.observationId, bootstrapToken: observed.bootstrap_token || null, linkKind: observation.link_kind, channel: channelCode, shareId });
      const initialized = navigator.locks?.request
        ? await navigator.locks.request('dino-participant-init', initialize)
        : await initialize();
      this.config = config;
      startVercelAnalytics(config);
      this.inviteVisit = initialized.invite_visit || null;
      this.state.participant = initialized.participant;
      this.state.tickets = initialized.tickets || this.state.tickets;
      analytics.setParticipantReady({ is_new: initialized.is_new });
      await this.refreshState({ quiet: true });
      this.initialized = true;
      if (this.inviteVisit?.status === 'PENDING' && this.inviteVisit.visit_nonce) this.installInviteQualification(inviteCode, config?.limits?.invite_active_ms || 3000);
      else if (this.inviteVisit) {
        analytics.track('invite_visit_rejected', { status: this.inviteVisit.status || 'REJECTED', reason: this.inviteVisit.reason || 'NOT_ELIGIBLE' });
        ui.showToast(this.inviteVisit.status === 'SELF_INVITE' ? '내 초대 링크에는 초대권이 지급되지 않아요.' : this.inviteVisit.status === 'INVALID_CODE' ? '유효하지 않은 초대 링크예요.' : '현재 이 초대 방문은 게임권 지급 대상이 아니에요.');
      }
      const allowed = ['home', 'ranking', 'claims', 'invite', 'benefit'];
      this.navigate(allowed.includes(requestedView) ? requestedView : (this.state.draw.status === 'DRAWN' && !this.state.draw.draw?.scratch_completed ? 'draw' : 'home'));
      analytics.setLoadingReady();
      this.hideSplash();
      if (this.state.tickets.cooldown_notice_pending && this.state.tickets.cooldown_until) this.showCooldownNotice();
    } catch (error) {
      this.renderInitError(error);
    }
  }

  bindNavigation() {
    document.querySelectorAll('.bottom-nav .nav-item').forEach((item) => {
      item.addEventListener('click', (event) => {
        event.preventDefault();
        if (this.initialized) this.navigate(item.dataset.view);
      });
    });
  }

  async refreshState({ quiet = false } = {}) {
    try {
      const me = await api.getMe();
      this.state.participant = me.participant || this.state.participant;
      api.participant = this.state.participant;
      this.state.tickets = me.tickets || this.state.tickets;
      this.state.bestScore = me.best_score || 0;
      this.state.rank = me.rank ?? null;
      this.state.draw = typeof me.draw === 'string' ? { status: me.draw } : (me.draw || this.state.draw);
      this.state.top3Profile = me.top3_profile || this.state.top3Profile;
      this.state.pendingGameSession = me.pending_game_session || null;
      this.updateNav();
      return me;
    } catch (error) {
      if (!quiet) ui.showToast(error.message);
      throw error;
    }
  }

  updateNav() {
    const tickets = this.state.tickets;
    const available = Number(tickets.available_total ?? (Number(tickets.initial || 0) + Number(tickets.invitation || 0)));
    this.ticketPill.textContent = `🎟️ ${available}장`;
    this.ticketPill.title = `기본권 ${tickets.initial || 0}장, 초대권 ${tickets.invitation || 0}장`;
  }

  navigate(viewName) {
    const next = this.views[viewName] ? viewName : 'home';
    const previousView = this.currentView && this.views[this.currentView];
    previousView?.cleanup?.();
    ui.hideModal();
    this.currentView = next;
    this.renderToken += 1;
    document.querySelectorAll('.bottom-nav .nav-item').forEach((item) => item.classList.toggle('active', item.dataset.view === next));
    this.container.replaceChildren();
    analytics.enterScreen(next);
    this.views[next].render(this.container, this, this.renderToken);
    window.scrollTo({ top: 0, behavior: 'auto' });
  }

  isCurrent(token) { return token === this.renderToken; }
  announceStateChange() { this.channel?.postMessage({ type: 'refresh' }); }

  hideSplash() {
    const splash = document.getElementById('splash-screen');
    if (splash) { splash.setAttribute('aria-hidden', 'true'); splash.inert = true; }
    splash?.classList.add('fade-out');
    setTimeout(() => { if (splash) splash.hidden = true; }, 250);
  }

  renderInitError(error) {
    this.hideSplash();
    this.container.replaceChildren();
    const card = document.createElement('section');
    card.className = 'card empty-state';
    const title = document.createElement('h1');
    title.textContent = error.status === 401 ? '참여자 인증을 복원하지 못했어요' : '서비스 연결이 잠시 불안정해요';
    const detail = document.createElement('p');
    detail.textContent = error.status === 401
      ? '잘못되거나 만료된 쿠키로 새 참가자를 자동 생성하지 않았습니다. 운영자에게 문의하거나 쿠키를 직접 지운 뒤 다시 접속해 주세요.'
      : '기존 참여 기록을 보호하기 위해 임시 ID를 만들지 않았습니다. 잠시 후 다시 시도해 주세요.';
    const retry = document.createElement('button');
    retry.className = 'btn btn-primary';
    retry.textContent = '다시 연결';
    retry.onclick = () => window.location.reload();
    card.append(title, detail, retry);
    this.container.appendChild(card);
  }

  showCooldownNotice() {
    const until = this.state.tickets.cooldown_until;
    ui.showModal({
      title: '초대권이 3장이 되었어요',
      content: `${new Date(until).toLocaleString('ko-KR')}까지 새 초대권 추가 적립이 쉽니다. 가진 게임권은 지금 사용할 수 있고, 대기 중 방문은 자동 이월되지 않습니다.`,
      confirmText: '확인',
      onConfirm: async () => {
        try {
          await api.acknowledgeCooldown(until);
          this.state.tickets.cooldown_notice_pending = false;
        } catch (error) {
          ui.showToast(error.message);
          return false;
        }
      },
    });
  }

  installInviteQualification(code, requiredMs) {
    let visibleSince = document.hidden ? null : performance.now();
    let visibleMs = 0;
    let interacted = false;
    let sent = false;
    const eventId = api.createRequestId('evt');
    const cleanup = () => {
      document.removeEventListener('visibilitychange', onVisibility);
      document.removeEventListener('pointerdown', onInteraction, true);
      document.removeEventListener('keydown', onInteraction, true);
      clearInterval(timer);
    };
    const currentVisible = () => visibleMs + (visibleSince == null ? 0 : performance.now() - visibleSince);
    const qualify = async () => {
      if (sent || !interacted || currentVisible() < requiredMs || document.hidden) return;
      sent = true;
      analytics.track('invite_visit_interacted', {}, { activeMs: Math.round(currentVisible()) });
      try {
        const result = await api.qualifyReferral({ code, visit_nonce: this.inviteVisit.visit_nonce, active_ms: Math.round(currentVisible()), interacted: true, event_id: eventId });
        cleanup();
        analytics.track(result.status === 'REWARDED' ? 'invite_visit_qualified' : 'invite_visit_rejected', { status: result.status, reason: result.reason || '' });
        if (result.status === 'REWARDED') ui.showToast('초대 방문이 확인되어 친구에게 게임권이 지급됐어요.');
        await this.refreshState({ quiet: true });
      } catch (error) {
        const retryable = !error.status || error.status === 408 || error.status === 429 || error.status >= 500;
        if (retryable) sent = false;
        else {
          cleanup();
          analytics.track('invite_visit_rejected', { status: error.data?.error || 'REJECTED', reason: error.data?.error || 'QUALIFICATION_REJECTED' });
          ui.showToast(error.message || '이 초대 방문은 게임권 지급 대상이 아니에요.');
        }
      }
    };
    const onVisibility = () => {
      if (document.hidden && visibleSince != null) { visibleMs += performance.now() - visibleSince; visibleSince = null; }
      if (!document.hidden && visibleSince == null) visibleSince = performance.now();
      qualify();
    };
    const onInteraction = () => { interacted = true; qualify(); };
    document.addEventListener('visibilitychange', onVisibility);
    document.addEventListener('pointerdown', onInteraction, true);
    document.addEventListener('keydown', onInteraction, true);
    const timer = setInterval(qualify, 250);
    setTimeout(cleanup, 120000);
  }
}

document.addEventListener('DOMContentLoaded', () => {
  const router = new AppRouter();
  window.__geminiRouter = router;
  router.init();
});
