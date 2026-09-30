-- Read-only four-cohort UX comparison. Run this SELECT every 30 minutes.
--
-- Cohorts are assigned by participant.created_at, so the cutoffs only compare
-- arrival periods. In particular, 2026-09-30 10:42:59 KST is the time the B
-- deployment was verified, not proof that every participant saw that UI.
--
-- The draw table stores scratch_completed as a boolean but has no authoritative
-- completion timestamp. Client analytics cannot be joined to a draw reliably,
-- so this report stops at each participant's first draw instead of inventing a
-- participant -> scratch_completed time conversion.

-- 1) Four arrival cohorts: full observed window and a like-for-like first 30m.
with times as (
  select least(now(), '2026-10-03T00:00:00+09:00'::timestamptz) as checked_at
), windows(version,starts_at,ends_at) as (
  values
    ('original',
      '2026-09-29T21:00:00+09:00'::timestamptz,
      '2026-09-29T22:11:08+09:00'::timestamptz),
    ('position_first',
      '2026-09-29T22:11:08+09:00'::timestamptz,
      '2026-09-29T22:52:01+09:00'::timestamptz),
    ('green_prize_copy',
      '2026-09-29T22:52:01+09:00'::timestamptz,
      '2026-09-30T10:42:59+09:00'::timestamptz),
    ('b_postgame_auto_draw',
      '2026-09-30T10:42:59+09:00'::timestamptz,
      '2026-10-03T00:00:00+09:00'::timestamptz)
), first_draw as (
  select participant_id,min(created_at) as first_draw_at
  from dino_prod.draw
  where campaign_id='gemini_dino_campus_2026'
  group by participant_id
), first_game as (
  select participant_id,min(finished_at) as first_game_at
  from dino_prod.game_session
  where campaign_id='gemini_dino_campus_2026' and status='FINISHED'
  group by participant_id
), people as (
  select p.id,p.created_at,d.first_draw_at,g.first_game_at
  from dino_prod.participant p
  left join first_draw d on d.participant_id=p.id
  left join first_game g on g.participant_id=p.id
  where p.campaign_id='gemini_dino_campus_2026'
), cohorts as (
  select w.version,w.starts_at,least(w.ends_at,t.checked_at) as observed_until,m.mode
  from windows w
  cross join times t
  cross join (values ('within_version'),('first_30m')) m(mode)
), stats as (
  select c.version,c.mode,c.starts_at,c.observed_until,
    count(p.id) as participants,
    count(p.id) filter (
      where p.first_game_at < case when c.mode='first_30m'
        then p.created_at+interval '30 minutes' else c.observed_until end
    ) as completed_game,
    count(p.id) filter (
      where p.first_draw_at < case when c.mode='first_30m'
        then p.created_at+interval '30 minutes' else c.observed_until end
    ) as drawn,
    count(p.id) filter (
      where p.first_game_at < case when c.mode='first_30m'
        then p.created_at+interval '30 minutes' else c.observed_until end
      and p.first_draw_at < case when c.mode='first_30m'
        then p.created_at+interval '30 minutes' else c.observed_until end
    ) as completed_and_drawn
  from cohorts c
  left join people p
    on p.created_at>=c.starts_at and p.created_at<c.observed_until
    and (c.mode='within_version' or p.created_at+interval '30 minutes'<=c.observed_until)
  group by c.version,c.mode,c.starts_at,c.observed_until
), rates as (
  select s.*,
    round(100.0*completed_game/nullif(participants,0),2) as game_completed_percent,
    round(100.0*drawn/nullif(participants,0),2) as drawn_percent,
    round(100.0*completed_and_drawn/nullif(completed_game,0),2) as completed_game_drawn_percent
  from stats s
), compared as (
  select r.*,
    lag(game_completed_percent) over(partition by mode order by starts_at) as previous_game_completed_percent,
    lag(drawn_percent) over(partition by mode order by starts_at) as previous_drawn_percent,
    lag(completed_game_drawn_percent) over(partition by mode order by starts_at) as previous_completed_game_drawn_percent
  from rates r
)
select
  to_char(now() at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as queried_at_kst,
  version,mode,
  to_char(starts_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as starts_at_kst,
  to_char(observed_until at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as observed_until_kst,
  participants,completed_game,drawn,participants-drawn as undrawn,completed_and_drawn,
  game_completed_percent,
  case when previous_game_completed_percent is null then null
    else round(game_completed_percent-previous_game_completed_percent,2) end as game_completed_change_pp,
  drawn_percent,
  case when previous_drawn_percent is null then null
    else round(drawn_percent-previous_drawn_percent,2) end as drawn_change_pp,
  completed_game_drawn_percent,
  case when previous_completed_game_drawn_percent is null then null
    else round(completed_game_drawn_percent-previous_completed_game_drawn_percent,2) end as completed_game_drawn_change_pp
from compared
order by starts_at,mode;
