"""Read-only metrics from authenticated, scoped source records and observations."""
from __future__ import annotations

import datetime as dt
import os

UTC = dt.timezone.utc


def _iso(value):
    return value.astimezone(UTC).isoformat().replace('+00:00', 'Z')


def _period(query, now):
    from operations import DomainError
    try:
        end = dt.datetime.fromisoformat(query['to'].replace('Z', '+00:00')) if query.get('to') else now
        start = dt.datetime.fromisoformat(query['from'].replace('Z', '+00:00')) if query.get('from') else end - dt.timedelta(days=7)
        if start.tzinfo is None or end.tzinfo is None or end <= start or end - start > dt.timedelta(days=366) or end > now + dt.timedelta(minutes=5):
            raise ValueError()
    except (ValueError, TypeError):
        raise DomainError('VALIDATION_ERROR', '시간대가 포함된 조회 기간을 확인해 주세요.') from None
    return start, end


def _metric(key, label, numerator, denominator=None, *, unique=None, events=None, estimated=False, definition='', window=1800):
    rate = numerator / denominator if denominator else None
    return dict(key=key, label=label, numerator=numerator, denominator=denominator,
                rate=rate, value=numerator, unique_participants=unique, event_count=events,
                estimated=estimated, definition=definition, observation_window_seconds=window)


def build_overview(conn, query, ctx):
    from operations import DomainError
    now = dt.datetime.now(UTC)
    start, end = _period(query, now)
    environment = query.get('environment') or ctx['environment']
    if environment not in {'local', 'test', 'preview'}:
        raise DomainError('VALIDATION_ERROR', '테스트 환경을 선택해 주세요.')
    try:
        window = int(os.getenv('ANALYTICS_OBSERVATION_WINDOW_SECONDS', '1800'))
        if not 600 <= window <= 86400:
            raise ValueError()
    except ValueError:
        raise DomainError('METRICS_CONFIGURATION', '지표 관측 기간 설정을 확인해 주세요.', 503) from None
    campaign = conn.execute('select c.* from dino_dev.campaign c join dino_dev.environment_guard g on g.campaign_id=c.id where g.singleton').fetchone()
    if not campaign:
        raise DomainError('CAMPAIGN_NOT_CONFIGURED', '행사 설정이 없습니다.', 503)
    filters = {k: str(query[k]) for k in ('link_kind', 'channel', 'content', 'won') if query.get(k)}
    if filters.get('won') not in (None, 'true', 'false') or any(len(x) > 64 for x in filters.values()):
        raise DomainError('VALIDATION_ERROR', '조회 조건을 확인해 주세요.')
    # Link/channel filters select the first-attribution cohort. Content selects
    # people who observed/clicked that content in this period, not only that event.
    clauses, extra = [], []
    for key, column in [('link_kind', 'first_link_kind'), ('channel', 'first_channel')]:
        if key in filters:
            clauses.append(f'p.{column}=%s'); extra.append(filters[key])
    if 'won' in filters:
        clauses.append('exists(select 1 from dino_dev.draw d where d.participant_id=p.id and d.campaign_id=p.campaign_id and (d.inventory_item_id is not null)=%s)')
        extra.append(filters['won'] == 'true')
    if 'content' in filters:
        clauses.append("exists(select 1 from dino_dev.analytics_event ce where ce.participant_id=p.id and ce.environment=p.environment and ce.received_at>=%s and ce.received_at<%s and ce.dimensions->>'content'=%s)")
        extra.extend([start, end, filters['content']])
    where = (' and ' + ' and '.join(clauses)) if clauses else ''
    scope = '''with people as (
      select p.* from dino_dev.participant p where p.campaign_id=%s and p.environment=%s and p.synthetic''' + where + '''
    ), observations as (
      select o.* from dino_dev.observation o left join people p on p.id=o.participant_id
      where o.environment=%s and o.synthetic and o.created_at>=%s and o.created_at<%s
        and (p.id is not null or (o.participant_id is null and %s))
    ), events as (
      select e.*,coalesce(e.participant_id,o.participant_id) person_id
      from dino_dev.analytics_event e left join observations o on o.id=e.observation_id
      left join people p on p.id=coalesce(e.participant_id,o.participant_id)
      where e.campaign_id=%s and e.environment=%s and e.synthetic and e.received_at>=%s and e.received_at<%s
        and (p.id is not null or (e.participant_id is null and o.id is not null))
    ) '''
    params = [campaign['id'], environment, *extra, environment, start, end, not bool(filters), campaign['id'], environment, start, end]

    def rows(sql, args=()):
        return [dict(row) for row in conn.execute(scope + sql, [*params, *args]).fetchall()]

    def one(sql, args=()):
        return rows(sql, args)[0]

    funnel = rows('''select event_name,source,count(*)::int events,count(distinct person_id)::int participants
      from events group by event_name,source order by event_name,source''')
    totals = one('''select count(*)::int events,count(distinct person_id)::int participants,
      (select count(*)::int from observations where participant_id is null) unlinked_observations,
      (select count(*)::int from people where created_at>=%s and created_at<%s) new_participants from events''', (start, end))
    # active_ms is a cumulative per-screen checkpoint: take the last/max value,
    # never SUM every checkpoint (which double-counts time).
    screens = rows('''select screen,count(*)::int visits,sum(active_ms)::bigint active_ms,
      count(*) filter(where not progressed and last_at>%s-make_interval(secs=>%s))::int ongoing,
      count(*) filter(where last_at<=%s-make_interval(secs=>%s) and not progressed)::int estimated_exits
      from (select coalesce(screen_view_id,visit_session_id,observation_id,person_id) visit,screen,
        max(coalesce(active_ms,0)) active_ms,max(received_at) last_at,
        bool_or(event_name in ('participant_ready','pouch_selected','scratch_completed','draw_result_viewed','claim_form_submitted','client_claim_form_submitted','client_scratch_completed','gemini_cta_clicked')
          or (event_name='screen_left' and dimensions->>'reason'='navigation')) progressed
        from events where source='client' and screen is not null
        group by coalesce(screen_view_id,visit_session_id,observation_id,person_id),screen) s group by screen''', (end, window, end, window))
    totals['active_ms'] = sum(int(row['active_ms'] or 0) for row in screens)
    loading = rows('''select case when last_active is null then 'unknown' when last_active<1000 then '0-1s'
      when last_active<2000 then '1-2s' when last_active<3000 then '2-3s' else '3s+' end bucket,
      count(*)::int observations,sum(event_count)::int events,
      count(*) filter(where not ready and last_at<=%s-make_interval(secs=>%s))::int estimated_exits,
      count(*) filter(where not ready and last_at>%s-make_interval(secs=>%s))::int pending,
      count(*) filter(where ready)::int ready
      from (select o.id,max(e.active_ms) filter(where e.screen='loading') last_active,coalesce(max(e.received_at),o.created_at) last_at,
        count(e.id) filter(where e.screen='loading') event_count,
        coalesce(bool_or(e.event_name='loading_ready' or (e.event_name='screen_entered' and e.screen<>'loading')),false) ready
        from observations o left join events e on e.observation_id=o.id and e.source='client'
        group by o.id,o.created_at) l group by 1 order by 1''', (end, window, end, window))
    for row in loading:
        decided = row['observations'] - row['pending']
        row['estimated_exit_rate'] = row['estimated_exits'] / decided if decided else None
    # Every click must follow an exposure at the SAME location, within the
    # observation window AND selected report period/environment/campaign.
    ctr = one('''select count(distinct v.person_id)::int exposed,count(*)::int exposure_events,
      count(distinct v.person_id) filter(where exists(select 1 from events c where c.source='client'
        and c.event_name='gemini_cta_clicked' and c.person_id=v.person_id
        and coalesce(c.dimensions->>'position','unknown')=coalesce(v.dimensions->>'position','unknown')
        and c.occurred_at>=v.occurred_at and c.occurred_at<=v.occurred_at+make_interval(secs=>%s)))::int clicked
      from events v where v.source='client' and v.person_id is not null and v.event_name='gemini_cta_viewed' ''', (window,))
    conversion = one('''select count(distinct person_id) filter(where event_name='gemini_cta_clicked')::int direct,
      count(*) filter(where event_name='gemini_cta_clicked')::int direct_events,
      0::int via_notion,
      count(distinct person_id) filter(where event_name='gemini_cta_clicked')::int union_participants,
      count(*) filter(where person_id is null and event_name='gemini_cta_clicked')::int unlinked_click_events,
      count(*) filter(where event_name='notion_redirect_requested')::int redirect_requests
      from events where source='client' ''')
    conversion.update(notion_enabled=False, definition='현재는 직접 클릭 고유 참가자만 집계. 승인되지 않은 Notion 경유 전환은 0이며 가이드 클릭·경유 GET·혜택 등록 성공은 제외.')
    # Source attribution is reported separately; a known participant alone does
    # not prove which later visit caused a server event.
    source_funnel = rows('''select 'first' attribution,coalesce(p.first_link_kind,'unknown') link_kind,
      coalesce(p.first_channel,'unknown') channel,count(distinct o.id)::int entries,count(distinct p.id)::int participants,
      count(distinct p.id) filter(where p.created_at>=%s)::int new_participants,
      count(distinct p.id) filter(where p.created_at<%s)::int returning_participants,
      count(distinct e.person_id) filter(where e.source='server' and e.event_name='game_start_approved')::int game_starts,
      count(distinct e.person_id) filter(where e.source='client' and e.event_name='gemini_cta_clicked')::int gemini_clicks
      from people p left join observations o on o.participant_id=p.id left join events e on e.person_id=p.id
      where o.id is not null or e.id is not null group by 2,3
      union all
      select 'session',coalesce(o.link_kind,'unknown'),coalesce(o.channel_code,'unknown'),count(distinct o.id)::int,
      count(distinct o.participant_id)::int,
      count(distinct p.id) filter(where p.created_at>=%s)::int,
      count(distinct p.id) filter(where p.created_at<%s)::int,
      count(distinct e.person_id) filter(where e.source='server' and e.event_name='game_start_approved')::int,
      count(distinct e.person_id) filter(where e.source='client' and e.event_name='gemini_cta_clicked')::int
      from observations o left join people p on p.id=o.participant_id
      left join events e on e.observation_id=o.id group by 2,3 order by 1,2,3''', (start,start,start,start))
    for row in source_funnel:
        row['game_start_rate'] = row['game_starts'] / row['participants'] if row['participants'] else None
        row['gemini_click_rate'] = row['gemini_clicks'] / row['participants'] if row['participants'] else None
    game = one('''select count(*)::int approved,count(distinct g.participant_id)::int approved_participants,
      count(*) filter(where g.status='FINISHED')::int finished,
      count(distinct g.participant_id) filter(where g.status='FINISHED')::int finished_participants,
      count(*) filter(where g.status='REJECTED')::int rejected,count(*) filter(where g.status='EXPIRED')::int expired,
      count(*) filter(where g.status='ABORTED')::int abandoned,count(*) filter(where g.status='FAULT_REPORTED')::int needs_review,
      count(*) filter(where g.status in ('RESERVED','ACTIVE') and g.expires_at>%s)::int ongoing,
      count(distinct g.participant_id) filter(where g.status='REJECTED')::int rejected_participants,
      count(distinct g.participant_id) filter(where g.status='EXPIRED')::int expired_participants,
      count(distinct g.participant_id) filter(where g.status='ABORTED')::int abandoned_participants,
      count(distinct g.participant_id) filter(where g.status='FAULT_REPORTED')::int needs_review_participants,
      count(distinct g.participant_id) filter(where g.status in ('RESERVED','ACTIVE') and g.expires_at>%s)::int ongoing_participants,
      coalesce(sum(g.valid_ticks) filter(where g.status='FINISHED'),0)::bigint verified_ticks
      from dino_dev.game_session g join people p on p.id=g.participant_id where g.reserved_at>=%s and g.reserved_at<%s''', (end, end, start, end))
    score_distribution = rows('''select (g.score/100)*100 score_from,(g.score/100)*100+99 score_to,count(*)::int games,
      count(distinct g.participant_id)::int participants from dino_dev.game_session g join people p on p.id=g.participant_id
      where g.status='FINISHED' and g.finished_at>=%s and g.finished_at<%s group by 1,2 order by 1''', (start, end))
    leaderboard = rows('''select b.rank,
      case when p.is_public then p.nickname else '익명 참가자' end nickname,b.score best_score,b.tied
      from (select participant_id,score,achieved_at,dense_rank() over(order by score desc)::int rank,
        count(*) over(partition by score)>1 tied from dino_dev.best_score) b
      join people p on p.id=b.participant_id
      order by b.rank,b.achieved_at asc limit 100''')
    ledger = rows('''select l.source_type,l.ticket_kind,count(*)::int events,count(distinct l.participant_id)::int participants
      from dino_dev.ticket_ledger l join people p on p.id=l.participant_id where l.created_at>=%s and l.created_at<%s group by 1,2''', (start, end))
    claims = rows('''select c.claim_type,c.status,count(*)::int claims,count(distinct c.participant_id)::int participants
      from dino_dev.claim c join people p on p.id=c.participant_id where c.created_at>=%s and c.created_at<%s group by 1,2''', (start, end))
    ranking = one('''select count(*)::int requested,count(*) filter(where r.status='SUBMITTED')::int submitted
      from dino_dev.ranking_contact r join people p on p.id=r.participant_id''')
    stages = rows(""" , stage_defs(key,label,entry_name,next_name) as (values
      ('draw.select','복주머니 진입→선택','draw_entered','pouch_selected'),
      ('scratch.start','주머니 선택→긁기 시작','pouch_selected','scratch_started'),
      ('scratch.complete','긁기 시작→완료','scratch_started','scratch_completed'),
      ('scratch.visible','긁기 완료→결과 실제 노출','scratch_completed','draw_result_viewed'),
      ('claim.submit','수령 양식 시작→제출','claim_form_started','claim_form_submitted'),
      ('ranking.submit','TOP3 양식 시작→제출','top3_profile_started','top3_profile_submitted'),
      ('invite.share','초대 CTA 노출→공유 시도','invite_cta_viewed','share_attempted'),
      ('gemini.exposure','혜택 화면→CTA 실제 노출','benefit_viewed','gemini_cta_viewed'),
      ('gemini.click','Gemini CTA 노출→클릭','gemini_cta_viewed','gemini_cta_clicked')
    ), normalized as (select *,regexp_replace(event_name,'^client_','') client_name from events where source='client'),
    entry_rows as (select d.*,e.person_id,e.screen_view_id,e.occurred_at,e.active_ms,
      nx.occurred_at next_at,nx.active_ms next_active_ms,tail.last_active_ms
      from stage_defs d join normalized e on e.client_name=d.entry_name
      left join lateral (select n.occurred_at,n.active_ms from normalized n
        where n.person_id=e.person_id and n.client_name=d.next_name
          and (e.screen_view_id is null or n.screen_view_id=e.screen_view_id)
          and n.occurred_at>=e.occurred_at and n.occurred_at<=e.occurred_at+make_interval(secs=>%s)
        order by n.occurred_at limit 1) nx on true
      left join lateral (select max(n.active_ms) last_active_ms from normalized n
        where n.person_id=e.person_id and e.screen_view_id is not null and n.screen_view_id=e.screen_view_id
          and n.id<>e.id
          and n.occurred_at>=e.occurred_at and n.occurred_at<=least(e.occurred_at+make_interval(secs=>%s),%s)) tail on true
      where e.person_id is not null)
    , people_stages as (select key,label,person_id,min(occurred_at) entered_at,
      bool_or(next_at is not null) progressed,min(extract(epoch from next_at-occurred_at)) elapsed_seconds,
      bool_or(next_at is not null and screen_view_id is not null and active_ms is not null and next_active_ms is not null) active_observed,
      min(greatest(0,next_active_ms-active_ms)) filter(where next_at is not null and screen_view_id is not null
        and active_ms is not null and next_active_ms is not null) active_dwell_ms,
      bool_or(next_at is null and screen_view_id is not null and active_ms is not null and last_active_ms is not null) abandoned_active_observed,
      max(greatest(0,last_active_ms-active_ms)) filter(where next_at is null and screen_view_id is not null
        and active_ms is not null and last_active_ms is not null) abandoned_active_dwell_ms
      from entry_rows group by key,label,person_id)
    select key,label,count(*)::int entered,
      (select count(*)::int from entry_rows er where er.key=people_stages.key) entry_events,
      count(*) filter(where progressed)::int progressed,
      count(*) filter(where not progressed and entered_at<=%s-make_interval(secs=>%s))::int estimated_exits,
      count(*) filter(where not progressed and entered_at>%s-make_interval(secs=>%s))::int pending,
      avg(elapsed_seconds)::float8 mean_observed_elapsed_seconds,
      avg(active_dwell_ms)::float8 mean_observed_active_ms,
      count(*) filter(where progressed and active_observed)::int active_dwell_observations,
      count(*) filter(where progressed and not active_observed)::int active_dwell_unknown,
      avg(abandoned_active_dwell_ms) filter(where not progressed and entered_at<=%s-make_interval(secs=>%s))::float8 mean_abandoned_active_ms,
      count(*) filter(where not progressed and entered_at<=%s-make_interval(secs=>%s) and abandoned_active_observed)::int abandoned_active_observations,
      count(*) filter(where not progressed and entered_at<=%s-make_interval(secs=>%s) and not abandoned_active_observed)::int abandoned_active_unknown
      from people_stages group by key,label order by key""",
      (window,window,end,end,window,end,window,end,window,end,window,end,window))
    result_dwell = rows("""select result_type,count(*)::int visits,coalesce(sum(active_ms),0)::bigint active_ms
      from (select coalesce(screen_view_id,visit_session_id,person_id) view_id,
        coalesce(max(dimensions->>'result_type') filter(where event_name='draw_result_viewed'),'unknown') result_type,
        greatest(0,max(coalesce(active_ms,0))-coalesce(min(active_ms) filter(where event_name='draw_result_viewed'),0)) active_ms
        from events where source='client' and screen='draw'
        group by coalesce(screen_view_id,visit_session_id,person_id)
        having bool_or(event_name='draw_result_viewed')) r group by 1""")
    invitation = rows("""select v.status,coalesce(v.reason,'unknown') reason,count(*)::int visits,
      count(distinct v.visitor_id)::int visitors from dino_dev.invitation_visit v join people p on p.id=v.inviter_id
      where v.created_at>=%s and v.created_at<%s group by 1,2 order by 1,2""", (start,end))
    sharing = rows("""select coalesce(dimensions->>'share_method','unknown') share_method,
      coalesce(dimensions->>'status','unknown') status,count(*)::int events,
      count(distinct person_id) filter(where person_id is not null)::int linked_participants,
      count(*) filter(where person_id is null)::int unlinked_events
      from events where source='client' and event_name='share_attempted'
      group by 1,2 order by 1,2""")
    sharing_totals = one("""select count(distinct person_id) filter(where person_id is not null)::int linked_participants,
      count(*) filter(where person_id is null)::int unlinked_events
      from events where source='client' and event_name='share_attempted'""")
    sharing_summary = {
      **sharing_totals,
      'attempt_events': sum(r['events'] for r in sharing if r['status'] == 'attempted'),
      'copy_success_events': sum(r['events'] for r in sharing if r['share_method'] == 'copy' and r['status'] == 'copied'),
      'share_sheet_closed_events': sum(r['events'] for r in sharing if r['status'] == 'share_sheet_closed'),
      'cancelled_events': sum(r['events'] for r in sharing if r['status'] == 'cancelled'),
      'failed_events': sum(r['events'] for r in sharing if r['status'] == 'failed'),
      'actual_delivery': 'unknown',
    }
    invitation_performance = one(""", grants as (
      select l.* from dino_dev.ticket_ledger l join people p on p.id=l.participant_id
      where l.ticket_kind='INVITATION' and l.source_type='INVITATION_GRANT'
        and l.created_at>=%s and l.created_at<%s
    ), uses as (
      select l.* from dino_dev.ticket_ledger l join people p on p.id=l.participant_id
      where l.ticket_kind='INVITATION' and l.source_type='PLAY_CONSUME'
        and l.created_at>=%s and l.created_at<%s
    ), reacquired as (
      select g.* from grants g where exists (
        select 1 from dino_dev.ticket_ledger prior where prior.participant_id=g.participant_id
          and prior.ticket_kind='INVITATION' and prior.cooldown_until is not null
          and prior.created_at<g.created_at and prior.cooldown_until<=g.created_at)
    ) select (select count(*)::int from grants) grant_events,
      (select count(distinct participant_id)::int from grants) granted_participants,
      (select count(*)::int from uses) use_events,
      (select count(distinct participant_id)::int from uses) using_participants,
      (select count(*)::int from reacquired) cooldown_reacquisition_events,
      (select count(distinct participant_id)::int from reacquired) cooldown_reacquisition_participants,
      (select count(*)::int from reacquired r where exists(select 1 from uses u
        where u.participant_id=r.participant_id and u.created_at>=r.created_at)) cooldown_reparticipation_events,
      (select count(distinct r.participant_id)::int from reacquired r where exists(select 1 from uses u
        where u.participant_id=r.participant_id and u.created_at>=r.created_at)) cooldown_reparticipation_participants""",
      (start,end,start,end))
    invitation_performance['period_use_to_grant_ratio'] = (
      invitation_performance['use_events'] / invitation_performance['grant_events']
      if invitation_performance['grant_events'] else None)
    invitation_performance['ratio_definition'] = '조회 기간의 초대권 사용 이벤트 / 초대권 지급 이벤트. 개별 지급권의 소비 전환율은 식별 불가.'
    game_progress_rows = rows("""select coalesce(last_stage,'unknown') last_stage,count(*)::int sessions,
      count(distinct participant_id)::int participants,
      avg(last_active_ms)::float8 mean_last_observed_active_ms,
      max(last_active_ms)::int max_last_observed_active_ms,
      count(*) filter(where last_active_ms is null)::int active_time_unknown
      from (select g.id,g.participant_id,last_event.last_stage,last_event.last_active_ms
        from dino_dev.game_session g join people p on p.id=g.participant_id
        left join lateral (select coalesce(
            (array_agg(e.dimensions->>'stage' order by e.occurred_at desc,e.id desc)
              filter(where e.dimensions ? 'stage'))[1],'unknown') last_stage,
          max(e.active_ms) last_active_ms from events e where e.game_session_id=g.id and e.source='client'
          and regexp_replace(e.event_name,'^client_','') in ('game_checkpoint','game_completed','game_fault_reported')
          ) last_event on true
        where g.reserved_at>=%s and g.reserved_at<%s) observed
      group by 1 order by 1""", (start,end))
    unlinked_game_progress = one("""select count(*)::int checkpoint_events from events
      where source='client' and regexp_replace(event_name,'^client_','')='game_checkpoint'
        and game_session_id is null""")['checkpoint_events']
    content = rows("""select coalesce(dimensions->>'content','unknown') content,
      count(*) filter(where event_name='content_clicked')::int click_events,
      count(*) filter(where event_name='notion_redirect_requested')::int outbound_request_events,
      count(distinct person_id) filter(where person_id is not null)::int linked_participants,
      count(*) filter(where person_id is null)::int unlinked_events
      from events where source='client' and event_name in ('content_clicked','notion_redirect_requested')
      group by 1 order by 1""")
    claim_conversion = one("""select count(*) filter(where c.claim_type='DRAW')::int eligible_winning_claims,
      count(*) filter(where c.claim_type='DRAW' and c.contact_submitted_at is not null)::int submitted_winning_claims
      from dino_dev.claim c join people p on p.id=c.participant_id where c.created_at>=%s and c.created_at<%s""", (start,end))
    metrics = []
    for row in stages:
        metrics.append(_metric('stage.'+row['key'],row['label'],row['progressed'],row['entered'],unique=row['progressed'],events=row['entry_events'],window=window,
          definition='같은 참가자에서 순서를 지킨 후속 행동; 아직 열린 관측창은 이탈로 세지 않음'))
        metrics.append(_metric('stage.exit.'+row['key'],row['label']+' 추정 이탈',row['estimated_exits'],row['entered']-row['pending'],
          unique=row['estimated_exits'],events=row['entry_events'],estimated=True,window=window))
    metrics.append(_metric('claim.eligible_submit','당첨자 수령 정보 접수',claim_conversion['submitted_winning_claims'],claim_conversion['eligible_winning_claims'],
      unique=claim_conversion['submitted_winning_claims'],events=claim_conversion['eligible_winning_claims'],
      definition='미당첨자는 분모에서 제외; 실제 수령 업무 원장 기준',window=window))
    for row in funnel:
        metrics.append(_metric('event.'+row['source']+'.'+row['event_name'], row['event_name']+' ('+row['source']+')', row['events'], unique=row['participants'], events=row['events'], window=window))
    metrics.extend([
      _metric('game.completion','정상 게임 완료',game['finished'],game['approved'],unique=game['finished_participants'],events=game['finished'],definition='서버 승인 세션 중 정상 물리 검증 완료 세션',window=window),
      _metric('game.rejected','검증 거절',game['rejected'],game['approved'],unique=game['rejected_participants'],events=game['rejected'],window=window),
      _metric('game.expired','만료 게임',game['expired'],game['approved'],unique=game['expired_participants'],events=game['expired'],window=window),
      _metric('game.abandoned','사용자 포기 게임',game['abandoned'],game['approved'],unique=game['abandoned_participants'],events=game['abandoned'],window=window),
      _metric('game.pending','진행 중 게임',game['ongoing'],unique=game['ongoing_participants'],events=game['ongoing'],window=window),
      _metric('game.fault_review','장애 판정 대기',game['needs_review'],unique=game['needs_review_participants'],events=game['needs_review'],window=window),
      _metric('ranking.registration','잠정 TOP3 정보 등록',ranking['submitted'],ranking['requested'],unique=ranking['submitted'],events=ranking['requested'],definition='최종 수상 확정·지급과 별도',window=window),
      _metric('gemini.ctr','Gemini 노출 후 클릭',ctr['clicked'],ctr['exposed'],unique=ctr['clicked'],events=ctr['exposure_events'],definition='같은 참가자·위치의 노출 이후 관측창 내 클릭 교집합',window=window),
      _metric('gemini.nonclick','Gemini 노출 후 미클릭',ctr['exposed']-ctr['clicked'],ctr['exposed'],unique=ctr['exposed']-ctr['clicked'],events=ctr['exposure_events'],window=window),
      _metric('gemini.union','현재 활성 경로의 Gemini 클릭 고유 참가자',conversion['union_participants'],unique=conversion['union_participants'],events=conversion['direct_events'],window=window),
      _metric('loading.unlinked','참가자 미연결 초기 관측',totals['unlinked_observations'],events=totals['unlinked_observations'],window=window),
    ])
    for row in screens:
        metrics.append(_metric('screen.exit.'+row['screen'],row['screen']+' 추정 이탈',row['estimated_exits'],row['visits']-row['ongoing'],events=row['visits'],estimated=True,definition='관측창이 지난 화면 방문 중 후속 진행 신호 미관측. 선택 기능 건너뛰기를 전체 이탈로 해석하지 않음.',window=window))
        metrics.append(_metric('screen.active.'+row['screen'],row['screen']+' 활성 체류(ms)',int(row['active_ms'] or 0),events=row['visits'],definition='방문·화면별 누적 활성 시간의 최댓값 합계; 백그라운드 제외',window=window))
    return 200, dict(campaign={k:campaign[k] for k in ('id','status','version')}, environment=environment,
      synthetic_only=True, filters=filters, filter_attribution='first_participant_cohort', period={'from':_iso(start),'to':_iso(end)},
      generated_at=_iso(now), observation_window_seconds=window, totals=totals, funnel=funnel, metrics=metrics,
      loading={'buckets':loading,'estimated':True}, screens=screens, game=game, score_distribution=score_distribution, leaderboard=leaderboard,
      source_funnel=source_funnel, ticket_ledger=ledger, claims=claims, ranking=ranking,
      stages=stages,result_dwell=result_dwell,invitation=invitation,
      sharing={'by_method_status':sharing, **sharing_summary}, invitation_performance=invitation_performance,
      game_progress={'by_last_stage':game_progress_rows,'unlinked_checkpoint_events':unlinked_game_progress},
      content=content,claim_conversion=claim_conversion,
      gemini_ctr={'numerator':ctr['clicked'],'denominator':ctr['exposed'],'rate':ctr['clicked']/ctr['exposed'] if ctr['exposed'] else None},
      gemini_conversion=conversion, definitions={
        'scope':'합성 테스트 데이터만 포함; 운영 통계로 사용 금지',
        'source_funnel':'최초 유입과 이번 방문을 별도 표시. 신규는 조회 기간 중 생성된 참가자, 재방문은 기간 이전 생성 참가자. 전환율 분모는 해당 행의 연결된 고유 참가자. 이번 방문의 서버 이벤트 연결이 없으면 0이며 인과를 추정하지 않음.',
        'loading':'준비 완료 전 마지막 관측 기반 추정. 관측창 진행 중은 이탈 제외. unknown은 활성 시간 미관측.',
        'active_ms':'누적 체크포인트 합산이 아닌 방문·화면별 최대값 합계',
        'stage_active_dwell':'같은 화면 진입에서 후속 단계까지 관측된 누적 활성 시간 차이. 신호가 없으면 active_dwell_unknown이며 wall clock으로 대체하지 않음.',
        'sharing':'클라이언트가 관측한 공유 수단 호출·복사 성공·취소·실패. 실제 전송·수신·도착 여부는 unknown.',
        'invitation_performance':'지급·사용은 서버 티켓 원장. 쿨다운 후 재획득은 과거 cooldown_until 종료 뒤 발생한 새 지급이며, 재참여는 그 뒤의 초대권 소비.',
        'game_progress':'서버 승인 게임별 마지막 연결된 클라이언트 체크포인트. 연결되지 않은 체크포인트와 활성 시간 미관측은 별도 unknown.',
        'content':'콘텐츠별 클라이언트 클릭 및 승인된 Notion 이동 요청. linked_participants는 중복 제거, unlinked_events는 별도.',
        'gemini':'클릭은 도착·인증·가입 완료가 아님; 0분모는 계산 대상 없음',
      })
