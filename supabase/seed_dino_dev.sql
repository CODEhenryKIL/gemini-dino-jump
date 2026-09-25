-- Explicit synthetic-only seed. Never run automatically from application startup.
begin;
do $$ declare g dino_dev.environment_guard%rowtype; begin
  select * into g from dino_dev.environment_guard where singleton for update;
  if not found or not g.synthetic_only or g.environment not in ('local','test','preview') or g.test_seed then
    raise exception 'Refusing dino_dev seed: exact unseeded synthetic guard required';
  end if;
end $$;

insert into dino_dev.campaign(id,title,status,game_version,benefit_url,settings,probability_version)
values('gemini_dino_phase1_test','공룡 점프 Phase 1 합성 테스트','ACTIVE','1.2.0','https://gemini.google.com/students',
  '{"initial_tickets":1,"invitation_balance_max":3,"invitation_cooldown_hours":10,"invite_active_ms":3000}'::jsonb,'phase1-test-v1');
insert into dino_dev.prize(id,campaign_id,name,category,image_url,probability) values
 ('test_coffee','gemini_dino_phase1_test','테스트 커피','COUPON','/assets/icons/Picture-Light.png',0.20),
 ('test_shipping','gemini_dino_phase1_test','테스트 배송 경품','SHIPPING','/assets/icons/Smile-Light.png',0.05),
 ('test_no_prize','gemini_dino_phase1_test','다음 기회에','NO_PRIZE','/assets/icons/Rocket-Dark.png',0.75);
insert into dino_dev.inventory_item(id,prize_id)
select 'test_coffee_'||lpad(n::text,3,'0'),'test_coffee' from generate_series(1,20)n;
insert into dino_dev.inventory_item(id,prize_id)
select 'test_shipping_'||lpad(n::text,3,'0'),'test_shipping' from generate_series(1,5)n;
insert into dino_dev.inventory_history(inventory_item_id,from_status,to_status,reason,related_type)
select id,null,'AVAILABLE','EXPLICIT_SYNTHETIC_SEED','seed' from dino_dev.inventory_item;
update dino_dev.environment_guard set test_seed=true,campaign_id='gemini_dino_phase1_test',updated_at=clock_timestamp() where singleton and synthetic_only and not test_seed;
commit;
