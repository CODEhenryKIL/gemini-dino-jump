begin;
set local statement_timeout='20s';
set local lock_timeout='5s';
select pg_advisory_xact_lock(hashtext('dino-prod-cutover'));
lock table dino_prod.environment_guard,dino_prod.campaign,dino_prod.participant,dino_prod.game_session,dino_prod.draw,dino_prod.claim,dino_prod.inventory_item,dino_prod.inventory_history,dino_prod.prize,dino_prod.draw_pool_slot in access exclusive mode;
do $revision$
begin
 if not exists(select 1 from pg_roles where rolname=current_user and (rolsuper or rolbypassrls)) then raise exception 'MAINTENANCE_ROLE_REQUIRED'; end if;
 if not exists(select 1 from dino_prod.environment_guard where singleton and environment='production' and project_ref='igfrnexknwtiljdqjrbp' and not event_enabled and not unlimited_play and draw_prize_quantity=77 and launch_manifest_sha256='fae7d1cec7d1ffafb48fb2ba1047f83ff5d1585b1f844f55d64b30c300b000bc') then raise exception 'PREOPEN_SOURCE_GUARD_MISMATCH'; end if;
 if not exists(select 1 from dino_prod.campaign where id='gemini_dino_campus_2026' and status='PAUSED' and version=1 and settings->>'phase3_manifest_hash'='fae7d1cec7d1ffafb48fb2ba1047f83ff5d1585b1f844f55d64b30c300b000bc') then raise exception 'PREOPEN_SOURCE_CAMPAIGN_MISMATCH'; end if;
 if exists(select 1 from dino_prod.participant) or exists(select 1 from dino_prod.game_session) or exists(select 1 from dino_prod.draw) or exists(select 1 from dino_prod.claim) then raise exception 'PRODUCTION_NOT_EMPTY'; end if;
 if exists(select 1 from dino_prod.draw_pool_slot where allocated_draw_id is not null or allocated_at is not null) then raise exception 'POOL_ALREADY_USED'; end if;
 if (select count(*) from dino_prod.inventory_item)<>80 or exists(select 1 from dino_prod.inventory_item where status<>'AVAILABLE' or reserved_by_draw_id is not null or reserved_at is not null or paid_at is not null) then raise exception 'INVENTORY_ALREADY_USED'; end if;
 if (select count(*) from dino_prod.draw_pool_slot)<>5000 or (select count(*) from dino_prod.draw_pool_slot where outcome_kind='PRIZE')<>77 then raise exception 'POOL_SOURCE_MISMATCH'; end if;
 if (select count(*) from dino_prod.inventory_item where prize_id='gemini_dino_campus_2026_convenience_5000')<>24 then raise exception 'GS_SOURCE_MISMATCH'; end if;
end $revision$;
create temporary table gs_retire on commit drop as
 select i.id from dino_prod.inventory_item i
 where i.prize_id='gemini_dino_campus_2026_convenience_5000'
 order by i.id offset 10;
do $revision$
begin
 if (select count(*) from gs_retire)<>14 or (select count(*) from dino_prod.draw_pool_slot where inventory_item_id in(select id from gs_retire))<>14 then raise exception 'GS_RETIRE_SELECTION_MISMATCH'; end if;
end $revision$;
update dino_prod.draw_pool_slot set outcome_kind='BENEFIT',prize_id=null,inventory_item_id=null where inventory_item_id in(select id from gs_retire);
with retired as (
 update dino_prod.inventory_item set status='VOID' where id in(select id from gs_retire) returning id
) insert into dino_prod.inventory_history(inventory_item_id,from_status,to_status,reason,related_type,related_id)
 select id,'AVAILABLE','VOID','PREOPEN_GS_REDUCTION_20260929','CAMPAIGN','gemini_dino_campus_2026' from retired;
update dino_prod.prize set name='GS 5천원권',probability=0.002 where id='gemini_dino_campus_2026_convenience_5000';
update dino_prod.prize set probability=0.9874 where id='gemini_dino_campus_2026_benefit';
alter table dino_prod.environment_guard drop constraint environment_guard_draw_prize_quantity_check;
alter table dino_prod.environment_guard add constraint environment_guard_draw_prize_quantity_check check(draw_prize_quantity=63) not valid;
update dino_prod.environment_guard set launch_manifest_sha256='a1aa02b7fff3314b14d3920717e73383e83c4ee00fbe26bf7b893bf140a15e7b',campaign_opens_at='2026-09-29T21:00:00+09:00',draw_prize_quantity=63,updated_at=clock_timestamp() where singleton;
alter table dino_prod.environment_guard validate constraint environment_guard_draw_prize_quantity_check;
update dino_prod.campaign set opens_at='2026-09-29T21:00:00+09:00',version=version+1,probability_version='phase3-20260929-v5-preparation',settings=settings||jsonb_build_object('phase3_manifest_hash','a1aa02b7fff3314b14d3920717e73383e83c4ee00fbe26bf7b893bf140a15e7b','phase3_draw_prize_quantity',63),updated_at=clock_timestamp() where id='gemini_dino_campus_2026';
do $revision$
begin
 if (select count(*) from dino_prod.inventory_item where status='AVAILABLE')<>66 or (select count(*) from dino_prod.inventory_item where status='VOID')<>14 then raise exception 'INVENTORY_TARGET_MISMATCH'; end if;
 if (select count(*) from dino_prod.draw_pool_slot where outcome_kind='PRIZE')<>63 or (select count(*) from dino_prod.draw_pool_slot where outcome_kind='BENEFIT')<>4937 then raise exception 'POOL_TARGET_MISMATCH'; end if;
 if (select count(*) from dino_prod.inventory_item where prize_id='gemini_dino_campus_2026_convenience_5000' and status='AVAILABLE')<>10 then raise exception 'GS_TARGET_MISMATCH'; end if;
 if not exists(select 1 from dino_prod.environment_guard where not event_enabled and launch_manifest_sha256='a1aa02b7fff3314b14d3920717e73383e83c4ee00fbe26bf7b893bf140a15e7b') or not exists(select 1 from dino_prod.campaign where status='PAUSED' and version=2 and opens_at='2026-09-29T21:00:00+09:00') then raise exception 'PAUSED_TARGET_MISMATCH'; end if;
end $revision$;
commit;
