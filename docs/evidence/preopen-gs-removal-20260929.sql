begin;
set local statement_timeout='20s'; set local lock_timeout='5s';
select pg_advisory_xact_lock(hashtext('dino-prod-cutover'));
lock table dino_prod.environment_guard,dino_prod.campaign,dino_prod.participant,dino_prod.game_session,dino_prod.draw,dino_prod.claim,dino_prod.inventory_item,dino_prod.inventory_history,dino_prod.prize,dino_prod.draw_pool_slot in access exclusive mode;
create temporary table gs_remove on commit drop as select id from dino_prod.inventory_item where prize_id='gemini_dino_campus_2026_convenience_5000' and status='VOID';
do $revision$
begin
 if not exists(select 1 from dino_prod.environment_guard where singleton and environment='production' and project_ref='igfrnexknwtiljdqjrbp' and not event_enabled and not unlimited_play and draw_prize_quantity=63 and launch_manifest_sha256='a1aa02b7fff3314b14d3920717e73383e83c4ee00fbe26bf7b893bf140a15e7b') then raise exception 'PREOPEN_SOURCE_GUARD_MISMATCH'; end if;
 if not exists(select 1 from dino_prod.campaign where id='gemini_dino_campus_2026' and status='PAUSED' and version=2) then raise exception 'PREOPEN_SOURCE_CAMPAIGN_MISMATCH'; end if;
 if exists(select 1 from dino_prod.participant) or exists(select 1 from dino_prod.game_session) or exists(select 1 from dino_prod.draw) or exists(select 1 from dino_prod.claim) then raise exception 'PRODUCTION_NOT_EMPTY'; end if;
 if (select count(*) from gs_remove)<>14 or exists(select 1 from dino_prod.inventory_item i where i.id in(select id from gs_remove) and (reserved_by_draw_id is not null or reserved_at is not null or paid_at is not null or not exists(select 1 from dino_prod.inventory_history h where h.inventory_item_id=i.id and h.from_status='AVAILABLE' and h.to_status='VOID' and h.reason='PREOPEN_GS_REDUCTION_20260929'))) then raise exception 'GS_REMOVAL_SCOPE_MISMATCH'; end if;
 if exists(select 1 from dino_prod.draw_pool_slot where inventory_item_id in(select id from gs_remove)) then raise exception 'GS_REMOVAL_STILL_IN_POOL'; end if;
end $revision$;
delete from dino_prod.inventory_history where inventory_item_id in(select id from gs_remove);
delete from dino_prod.inventory_item where id in(select id from gs_remove);
update dino_prod.environment_guard set launch_manifest_sha256='5326e40f39189b9a91e4fe0fdfbc77a788c1526c71af4f26e4eaf9517b2886f9',updated_at=clock_timestamp() where singleton;
update dino_prod.campaign set version=version+1,probability_version='phase3-20260929-v6-preparation',settings=settings||jsonb_build_object('phase3_manifest_hash','5326e40f39189b9a91e4fe0fdfbc77a788c1526c71af4f26e4eaf9517b2886f9','pool_exhaustion','BENEFIT_ONLY_AFTER_POOL_EXHAUSTION'),updated_at=clock_timestamp() where id='gemini_dino_campus_2026';
do $revision$
begin
 if (select count(*) from dino_prod.inventory_item)<>66 or exists(select 1 from dino_prod.inventory_item where status<>'AVAILABLE') then raise exception 'INVENTORY_TARGET_MISMATCH'; end if;
 if (select count(*) from dino_prod.draw_pool_slot where outcome_kind='PRIZE')<>63 or (select count(*) from dino_prod.draw_pool_slot where outcome_kind='BENEFIT')<>4937 then raise exception 'POOL_TARGET_MISMATCH'; end if;
 if (select count(*) from dino_prod.inventory_item where prize_id='gemini_dino_campus_2026_convenience_5000')<>10 then raise exception 'GS_TARGET_MISMATCH'; end if;
end $revision$;
commit;
