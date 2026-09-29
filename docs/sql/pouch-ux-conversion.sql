with times as (
  select '2026-09-29T22:11:08+09:00'::timestamptz as cutoff,
         least(now(), '2026-10-03T00:00:00+09:00'::timestamptz) as checked_at
), first_draw as (
  select participant_id, min(created_at) as first_draw_at
  from dino_prod.draw where campaign_id='gemini_dino_campus_2026'
  group by participant_id
), first_game as (
  select participant_id, min(finished_at) as first_game_at
  from dino_prod.game_session
  where campaign_id='gemini_dino_campus_2026' and status='FINISHED'
  group by participant_id
), people as (
  select p.created_at, d.first_draw_at, g.first_game_at
  from dino_prod.participant p
  left join first_draw d on d.participant_id=p.id
  left join first_game g on g.participant_id=p.id
  cross join times t
  where p.campaign_id='gemini_dino_campus_2026' and p.created_at<t.checked_at
), cohorts as (
  select 'before_deployment' as period,p.*,t.cutoff as observed_until
  from people p cross join times t where p.created_at<t.cutoff
  union all
  select 'new_after_deployment',p.*,t.checked_at
  from people p cross join times t where p.created_at>=t.cutoff
  union all
  select 'all_current',p.*,t.checked_at from people p cross join times t
  union all
  select 'before_deployment_30m',p.*,p.created_at+interval '30 minutes'
  from people p cross join times t where p.created_at<=t.cutoff-interval '30 minutes'
  union all
  select 'new_after_deployment_30m',p.*,p.created_at+interval '30 minutes'
  from people p cross join times t
  where p.created_at>=t.cutoff and p.created_at<=t.checked_at-interval '30 minutes'
), periods(period) as (
  values ('before_deployment'),('new_after_deployment'),('all_current'),
         ('before_deployment_30m'),('new_after_deployment_30m')
), stats as (
  select periods.period,count(c.created_at) as participants,
    count(*) filter(where first_draw_at<observed_until) as drawn,
    count(*) filter(where first_game_at<observed_until) as completed_game,
    count(*) filter(where first_game_at<observed_until and first_draw_at<observed_until) as completed_and_drawn
  from periods left join cohorts c using(period) group by periods.period
)
select to_char((select checked_at from times) at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as observed_until_kst,
  to_char(now() at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as queried_at_kst,
  period,participants,drawn,participants-drawn as undrawn,
  round(100.0*drawn/nullif(participants,0),2) as drawn_percent,
  round(100.0*(participants-drawn)/nullif(participants,0),2) as undrawn_percent,
  completed_game,completed_and_drawn,
  round(100.0*completed_and_drawn/nullif(completed_game,0),2) as completed_game_drawn_percent
from stats order by period;
