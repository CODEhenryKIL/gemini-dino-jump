-- Explicit local/test seed only. Bootstrap dino.environment_guard separately
-- with the audited database identity before running this file.
begin;

do $$
declare
  guard dino.environment_guard%rowtype;
begin
  select * into guard from dino.environment_guard where singleton=true;
  if not found or guard.environment not in ('local', 'test') or guard.synthetic_only is not true then
    raise exception 'Refusing seed: audited local/test environment_guard is required';
  end if;
  if guard.seeded then
    raise exception 'Refusing seed: environment is already marked seeded';
  end if;
end $$;

insert into dino.campaign(id, title, status, game_version, benefit_url, settings, is_test, real_prizes_enabled)
values (
  'gemini_dino_phase1_test', '공룡 점프 Phase 1 테스트', 'ACTIVE', '1.2.0',
  'https://gemini.google.com/students',
  '{"initial_tickets":3,"referral_reward":1,"referral_daily_limit":2,"referral_total_limit":5,"claim_ttl_seconds":259200}'::jsonb,
  true, false
);

insert into dino.prize(id, campaign_id, name, category, image_url, probability, is_active, is_test) values
  ('test_coffee', 'gemini_dino_phase1_test', '테스트 커피 쿠폰', 'COUPON', '/assets/icons/Picture-Light.png', 0.20, true, true),
  ('test_shipping', 'gemini_dino_phase1_test', '테스트 배송 경품', 'SHIPPING', '/assets/icons/Smile-Light.png', 0.05, true, true),
  ('test_no_prize', 'gemini_dino_phase1_test', '아쉽지만 다음 기회에', 'NO_PRIZE', '/assets/icons/Rocket-Dark.png', 0.75, true, true);

insert into dino.inventory_item(id, prize_id)
select 'test_coffee_' || lpad(n::text, 3, '0'), 'test_coffee' from generate_series(1, 20) n;
insert into dino.inventory_item(id, prize_id)
select 'test_shipping_' || lpad(n::text, 3, '0'), 'test_shipping' from generate_series(1, 5) n;

insert into dino.inventory_history(inventory_item_id, from_status, to_status, reason, related_type)
select id, null, 'AVAILABLE', 'EXPLICIT_TEST_SEED', 'seed' from dino.inventory_item;

do $$
begin
  update dino.environment_guard set seeded=true,updated_at=now()
  where singleton=true and environment in ('local','test') and synthetic_only=true and seeded=false;
  if not found then
    raise exception 'Seed guard finalization failed';
  end if;
end $$;

commit;
