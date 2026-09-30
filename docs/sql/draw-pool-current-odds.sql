with config as (
 select id,probability_version,settings->'draw_pool_policy' policy
 from dino_prod.campaign where id='gemini_dino_campus_2026'
), active as (
 select s.* from dino_prod.draw_pool_slot s join config c on c.id=s.campaign_id
 where s.allocated_draw_id is null
   and s.slot_number<=coalesce((c.policy->>'active_slot_max')::int,5000)
), pool as (
 select count(*)::int remaining,count(*) filter(where outcome_kind='PRIZE')::int prizes,
 count(*) filter(where outcome_kind='BENEFIT')::int benefits from active
), items as (
 select p.name,count(*)::int quantity,
 round(100.0*count(*)/nullif((select remaining from pool),0),5) next_draw_percent
 from active s join dino_prod.prize p on p.id=s.prize_id where s.outcome_kind='PRIZE'
 group by p.id,p.name order by p.name
)
select clock_timestamp() at time zone 'Asia/Seoul' checked_at,
 c.probability_version,c.policy,
 (select row_to_json(pool) from pool) active_pool,
 round(100.0*(select prizes from pool)/nullif((select remaining from pool),0),5) next_draw_prize_percent,
 (select coalesce(jsonb_agg(items),'[]'::jsonb) from items) prizes,
 (select count(*)::int from dino_prod.draw where campaign_id=c.id and is_won and outcome_kind='PRIZE') won_count,
 (select count(*)::int from dino_prod.claim where campaign_id=c.id and status='PAID') paid_count,
 (select count(*)::int from dino_prod.draw_pool_slot where campaign_id=c.id) physical_slots
from config c;
