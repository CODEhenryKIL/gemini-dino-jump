begin;

-- Preserve every historical draw while allowing up to ten ordered rounds.
alter table dino_dev.draw
  add column if not exists round_number smallint;
update dino_dev.draw set round_number=1 where round_number is null;
alter table dino_dev.draw alter column round_number set not null;
alter table dino_dev.draw alter column round_number set default 1;
alter table dino_dev.draw
  add constraint draw_round_number_check check (round_number between 1 and 10);
alter table dino_dev.draw
  drop constraint if exists draw_campaign_id_participant_id_key;
alter table dino_dev.draw
  add constraint draw_campaign_participant_round_key
  unique(campaign_id,participant_id,round_number);

alter table dino_dev.draw
  add column if not exists outcome_kind text;
update dino_dev.draw
set outcome_kind=case when is_won then 'PRIZE' else 'BENEFIT' end
where outcome_kind is null;
alter table dino_dev.draw
  add constraint draw_outcome_kind_check check (outcome_kind in ('PRIZE','BENEFIT'));
alter table dino_dev.draw
  add constraint draw_outcome_matches_win_check check (
    (is_won and outcome_kind='PRIZE') or (not is_won and outcome_kind='BENEFIT')
  );
alter table dino_dev.draw
  add constraint draw_id_campaign_key unique(id,campaign_id);

-- Keep the schema compatible while an older application deployment is still
-- draining: omitted outcome_kind is derived from the already authoritative
-- is_won column before constraints are checked.
create or replace function dino_dev.fill_draw_outcome_kind()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
  if new.outcome_kind is null then
    new.outcome_kind:=case when new.is_won then 'PRIZE' else 'BENEFIT' end;
  end if;
  return new;
end $$;
drop trigger if exists draw_outcome_kind_compat on dino_dev.draw;
create trigger draw_outcome_kind_compat before insert or update of is_won,outcome_kind
on dino_dev.draw for each row execute function dino_dev.fill_draw_outcome_kind();
alter table dino_dev.draw alter column outcome_kind set not null;
revoke all on function dino_dev.fill_draw_outcome_kind() from public;
grant execute on function dino_dev.fill_draw_outcome_kind() to dino_dev_app;

-- Draw rights are intentionally separate from game tickets.
create table dino_dev.draw_credit_ledger (
  id bigint generated always as identity primary key,
  participant_id text not null references dino_dev.participant(id) on delete cascade,
  campaign_id text not null references dino_dev.campaign(id),
  delta smallint not null check (delta in (-1,1)),
  source_type text not null check (source_type in ('FIRST_GRANT','SHARE_GRANT','DRAW_CONSUME','ERROR_REFUND')),
  source_id text not null,
  balance_after smallint not null check (balance_after between 0 and 10),
  created_at timestamptz not null default clock_timestamp(),
  check (
    (source_type in ('FIRST_GRANT','SHARE_GRANT','ERROR_REFUND') and delta=1)
    or (source_type='DRAW_CONSUME' and delta=-1)
  ),
  foreign key(participant_id,campaign_id) references dino_dev.participant(id,campaign_id),
  unique(participant_id,source_type,source_id)
);
create index draw_credit_ledger_participant_time_idx
  on dino_dev.draw_credit_ledger(participant_id,created_at desc,id desc);

-- Represent the already-consumed first right for historical draws. This keeps
-- the old result and its claim untouched while making the new balance auditable.
insert into dino_dev.draw_credit_ledger
  (participant_id,campaign_id,delta,source_type,source_id,balance_after,created_at)
select participant_id,campaign_id,1,'FIRST_GRANT',eligible_session_id,1,created_at
from dino_dev.draw
on conflict(participant_id,source_type,source_id) do nothing;
insert into dino_dev.draw_credit_ledger
  (participant_id,campaign_id,delta,source_type,source_id,balance_after,created_at)
select participant_id,campaign_id,-1,'DRAW_CONSUME',id,0,created_at
from dino_dev.draw
on conflict(participant_id,source_type,source_id) do nothing;

-- A pool row is consumed exactly once. PRIZE rows bind to one inventory item;
-- BENEFIT rows deliberately have no inventory item.
alter table dino_dev.prize add constraint prize_id_campaign_key unique(id,campaign_id);
create table dino_dev.draw_pool_slot (
  id bigint generated always as identity primary key,
  campaign_id text not null references dino_dev.campaign(id),
  slot_number integer not null check (slot_number between 1 and 5000),
  outcome_kind text not null check (outcome_kind in ('PRIZE','BENEFIT')),
  prize_id text references dino_dev.prize(id),
  inventory_item_id text unique references dino_dev.inventory_item(id),
  allocated_draw_id text unique,
  allocated_at timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  unique(campaign_id,slot_number),
  foreign key(prize_id,campaign_id) references dino_dev.prize(id,campaign_id),
  foreign key(inventory_item_id,prize_id) references dino_dev.inventory_item(id,prize_id),
  foreign key(allocated_draw_id,campaign_id) references dino_dev.draw(id,campaign_id)
    deferrable initially deferred,
  check (
    (outcome_kind='BENEFIT' and prize_id is null and inventory_item_id is null)
    or
    (outcome_kind='PRIZE' and prize_id is not null and inventory_item_id is not null)
  ),
  check ((allocated_draw_id is null)=(allocated_at is null))
);
create index draw_pool_slot_available_idx
  on dino_dev.draw_pool_slot(campaign_id,slot_number)
  where allocated_draw_id is null;
alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_kind_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_kind_check
  check (kind in ('record_share','retry_invite','draw_retry','prize_share','general_share'));
alter table dino_dev.kakao_share_intent
  add column if not exists reward_type text;
alter table dino_dev.kakao_share_intent
  add column if not exists reward_contract_version smallint not null default 1
  check (reward_contract_version in (1,2));
update dino_dev.kakao_share_intent
set reward_type='GAME'
where reward_type is null;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_reward_type_check
  check (reward_type in ('GAME','DRAW','NONE'));
create or replace function dino_dev.fill_share_reward_type()
returns trigger language plpgsql security invoker set search_path='' as $$
begin
  -- Old application versions omit this column and historically reward every
  -- supported share kind with a game ticket. New code always sends the fixed
  -- purpose explicitly, so the cutover is both compatible and auditable.
  if new.reward_type is null then new.reward_type:='GAME'; end if;
  return new;
end $$;
drop trigger if exists kakao_share_reward_type_compat on dino_dev.kakao_share_intent;
create trigger kakao_share_reward_type_compat before insert or update of reward_type
on dino_dev.kakao_share_intent for each row execute function dino_dev.fill_share_reward_type();
alter table dino_dev.kakao_share_intent alter column reward_type set not null;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_reward_contract_v2_check check (
    reward_contract_version=1 or (
      (claim_id is null and (
          (kind in ('record_share','retry_invite') and reward_type='GAME')
          or (kind='draw_retry' and reward_type='DRAW')
          or (kind in ('prize_share','general_share') and reward_type='NONE')
        ))
      or (claim_id is not null and kind in ('prize_share','record_share') and reward_type='NONE')
    )
  );
revoke all on function dino_dev.fill_share_reward_type() from public;
grant execute on function dino_dev.fill_share_reward_type() to dino_dev_app;

alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_reward_status_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_reward_status_check
  check (reward_status in (
    'PENDING','GRANTED','BLOCKED_CAP','BLOCKED_COOLDOWN','BLOCKED_PRIZE_WON',
    'BLOCKED_DRAW_LIMIT','NOT_ELIGIBLE','NO_REWARD'
  ));

alter table dino_dev.draw_credit_ledger enable row level security;
alter table dino_dev.draw_credit_ledger force row level security;
alter table dino_dev.draw_pool_slot enable row level security;
alter table dino_dev.draw_pool_slot force row level security;
revoke all on dino_dev.draw_credit_ledger,dino_dev.draw_pool_slot from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on dino_dev.draw_credit_ledger,dino_dev.draw_pool_slot from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on dino_dev.draw_credit_ledger,dino_dev.draw_pool_slot from authenticated;
  end if;
end $$;
create policy dino_dev_app_backend on dino_dev.draw_credit_ledger
  for all to dino_dev_app using (true) with check (true);
create policy dino_dev_app_backend on dino_dev.draw_pool_slot
  for all to dino_dev_app using (true) with check (true);
grant select,insert on dino_dev.draw_credit_ledger to dino_dev_app;
grant usage,select on sequence dino_dev.draw_credit_ledger_id_seq to dino_dev_app;
grant select,insert,update on dino_dev.draw_pool_slot to dino_dev_app;
grant usage,select on sequence dino_dev.draw_pool_slot_id_seq to dino_dev_app;

insert into dino_dev.schema_version(version)
values ('20260928151903')
on conflict(version) do nothing;

commit;
