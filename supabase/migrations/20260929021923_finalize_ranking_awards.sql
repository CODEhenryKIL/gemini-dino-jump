begin;

alter table dino_dev.ranking_snapshot
  drop constraint if exists ranking_snapshot_status_check;
alter table dino_dev.ranking_snapshot
  add constraint ranking_snapshot_status_check check (status in ('DRAFT','FINAL'));
alter table dino_dev.ranking_snapshot
  drop constraint if exists ranking_snapshot_tie_policy_check;
alter table dino_dev.ranking_snapshot
  add constraint ranking_snapshot_tie_policy_check
  check (tie_policy in ('UNDECIDED','EARLIEST_ACHIEVED_AT'));
alter table dino_dev.ranking_snapshot
  add column if not exists finalized_at timestamptz,
  add column if not exists finalized_by uuid references dino_dev.admin_member(auth_user_id);

alter table dino_dev.ranking_snapshot_entry
  add column if not exists achieved_at timestamptz;

create unique index if not exists ranking_snapshot_one_final_per_campaign
  on dino_dev.ranking_snapshot(campaign_id) where status='FINAL';

-- These rows are configured before finalization and deliberately use inventory
-- that is separate from the random draw pool. Finalization binds the configured
-- slot to an immutable snapshot winner and their existing/new ranking claim.
create table if not exists dino_dev.ranking_award (
  campaign_id text not null references dino_dev.campaign(id),
  rank smallint not null check (rank between 1 and 3),
  prize_id text not null,
  inventory_item_id text not null unique,
  snapshot_id text,
  participant_id text,
  claim_id text unique references dino_dev.claim(id),
  finalized_at timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  primary key(campaign_id,rank),
  foreign key(prize_id,campaign_id) references dino_dev.prize(id,campaign_id),
  foreign key(inventory_item_id,prize_id) references dino_dev.inventory_item(id,prize_id),
  foreign key(snapshot_id,participant_id)
    references dino_dev.ranking_snapshot_entry(snapshot_id,participant_id),
  check (
    (snapshot_id is null and participant_id is null and claim_id is null and finalized_at is null)
    or
    (snapshot_id is not null and participant_id is not null and claim_id is not null and finalized_at is not null)
  )
);

alter table dino_dev.ranking_snapshot enable row level security;
alter table dino_dev.ranking_snapshot force row level security;
alter table dino_dev.ranking_award enable row level security;
alter table dino_dev.ranking_award force row level security;
revoke all on dino_dev.ranking_award from public;

do $$ begin
  if not exists (
    select 1 from pg_policies where schemaname='dino_dev'
      and tablename='ranking_snapshot' and policyname='dino_dev_app_update'
  ) then
    create policy dino_dev_app_update on dino_dev.ranking_snapshot
      for update to dino_dev_app using (true) with check (true);
  end if;
  if not exists (
    select 1 from pg_policies where schemaname='dino_dev'
      and tablename='ranking_award' and policyname='dino_dev_app_read'
  ) then
    create policy dino_dev_app_read on dino_dev.ranking_award
      for select to dino_dev_app using (true);
  end if;
  if not exists (
    select 1 from pg_policies where schemaname='dino_dev'
      and tablename='ranking_award' and policyname='dino_dev_app_append'
  ) then
    create policy dino_dev_app_append on dino_dev.ranking_award
      for insert to dino_dev_app with check (true);
  end if;
  if not exists (
    select 1 from pg_policies where schemaname='dino_dev'
      and tablename='ranking_award' and policyname='dino_dev_app_update'
  ) then
    create policy dino_dev_app_update on dino_dev.ranking_award
      for update to dino_dev_app using (true) with check (true);
  end if;
end $$;

grant update on dino_dev.ranking_snapshot to dino_dev_app;
grant select,insert,update on dino_dev.ranking_award to dino_dev_app;

insert into dino_dev.schema_version(version)
values ('20260929021923')
on conflict(version) do nothing;

commit;
