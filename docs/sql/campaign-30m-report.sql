-- Read-only 30-minute campaign report. Participant means an account row, not live concurrent users.
with clock as (select now() as checked_at),
p as (select p.id,p.created_at from dino_prod.participant p where p.campaign_id='gemini_dino_campus_2026'),
wins as (
 select d.created_at,z.name as prize_name
 from dino_prod.draw d join dino_prod.prize z on z.id=d.prize_id and z.campaign_id=d.campaign_id
 where d.campaign_id='gemini_dino_campus_2026' and d.is_won=true and d.outcome_kind='PRIZE'
),
finished as (
 select distinct g.participant_id from dino_prod.game_session g
 where g.campaign_id='gemini_dino_campus_2026' and g.status='FINISHED'
),
drawn as (
 select distinct d.participant_id from dino_prod.draw d
 where d.campaign_id='gemini_dino_campus_2026'
)
select to_char(c.checked_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS') as queried_at_kst,
 (select count(*) from p) as participants_total,
 (select count(*) from p where created_at>=c.checked_at-interval '30 minutes' and created_at<=c.checked_at) as participants_new_30m,
 (select count(*) from finished) as game_finished_people,
 (select count(*) from drawn) as draw_people,
 (select round(100.0*count(*)/nullif((select count(*) from p),0),2) from drawn) as all_draw_percent,
 (select round(100.0*count(*)/nullif((select count(*) from finished),0),2) from drawn join finished using(participant_id)) as finished_draw_percent,
 (select count(*) from wins) as prize_wins_total,
 (select count(*) from wins where created_at>=c.checked_at-interval '30 minutes' and created_at<=c.checked_at) as prize_wins_30m,
 (select count(*) from dino_prod.ranking_award where campaign_id='gemini_dino_campus_2026' and participant_id is not null) as ranking_awards_confirmed,
 (select count(*) from dino_prod.claim where campaign_id='gemini_dino_campus_2026' and status='PAID') as paid_total,
 (select count(*) from dino_prod.claim where campaign_id='gemini_dino_campus_2026' and status='PAID' and paid_at>=c.checked_at-interval '30 minutes' and paid_at<=c.checked_at) as paid_30m,
 (select coalesce(jsonb_agg(jsonb_build_object('time_kst',to_char(created_at at time zone 'Asia/Seoul','YYYY-MM-DD HH24:MI:SS'),'prize',prize_name) order by created_at desc),'[]'::jsonb)
 from wins where created_at>=c.checked_at-interval '30 minutes' and created_at<=c.checked_at) as recent_prizes_30m
from clock c;
