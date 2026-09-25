begin;

alter table dino_dev.campaign
  add column if not exists opens_at timestamptz,
  add column if not exists closes_at timestamptz;
alter table dino_dev.observation add column if not exists share_id text;
alter table dino_dev.invitation_visit add column if not exists share_id text;
alter table dino_dev.analytics_event add column if not exists screen_view_id text;
alter table dino_dev.claim
  add column if not exists verification_status text not null default 'NOT_REQUESTED'
    check (verification_status in ('NOT_REQUESTED','PENDING','VERIFIED','REJECTED')),
  add column if not exists verification_reference text;

alter table dino_dev.game_session
  add column if not exists fault_review_status text not null default 'NONE'
    check (fault_review_status in ('NONE','PENDING','AUTO_APPROVED','APPROVED','DENIED')),
  add column if not exists fault_review_version integer not null default 0 check (fault_review_version >= 0),
  add column if not exists fault_reviewed_by uuid,
  add column if not exists fault_reviewed_at timestamptz,
  add column if not exists fault_review_reason text,
  add column if not exists last_checkpoint_tick integer check (last_checkpoint_tick is null or last_checkpoint_tick between 0 and 36000);

create table if not exists dino_dev.ranking_snapshot (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  status text not null default 'DRAFT' check (status = 'DRAFT'),
  tie_policy text not null default 'UNDECIDED' check (tie_policy = 'UNDECIDED'),
  campaign_closes_at timestamptz,
  captured_at timestamptz not null default clock_timestamp(),
  created_by uuid not null references dino_dev.admin_member(auth_user_id),
  synthetic boolean not null default true check (synthetic)
);
create table if not exists dino_dev.ranking_snapshot_entry (
  snapshot_id text not null references dino_dev.ranking_snapshot(id),
  participant_id text not null references dino_dev.participant(id),
  score integer not null check (score between 0 and 6000),
  rank integer not null check (rank > 0),
  tied boolean not null,
  contact_status text not null,
  primary key(snapshot_id,participant_id)
);

alter table dino_dev.ranking_snapshot enable row level security;
alter table dino_dev.ranking_snapshot force row level security;
alter table dino_dev.ranking_snapshot_entry enable row level security;
alter table dino_dev.ranking_snapshot_entry force row level security;
revoke all on dino_dev.ranking_snapshot,dino_dev.ranking_snapshot_entry from public;

do $$ begin
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='ranking_snapshot' and policyname='dino_dev_app_read') then
    create policy dino_dev_app_read on dino_dev.ranking_snapshot for select to dino_dev_app using (true);
  end if;
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='ranking_snapshot' and policyname='dino_dev_app_append') then
    create policy dino_dev_app_append on dino_dev.ranking_snapshot for insert to dino_dev_app with check (true);
  end if;
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='ranking_snapshot_entry' and policyname='dino_dev_app_read') then
    create policy dino_dev_app_read on dino_dev.ranking_snapshot_entry for select to dino_dev_app using (true);
  end if;
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='ranking_snapshot_entry' and policyname='dino_dev_app_append') then
    create policy dino_dev_app_append on dino_dev.ranking_snapshot_entry for insert to dino_dev_app with check (true);
  end if;
end $$;

grant select,insert on dino_dev.ranking_snapshot,dino_dev.ranking_snapshot_entry to dino_dev_app;
insert into dino_dev.schema_version(version) values ('20260925092759') on conflict(version) do nothing;

commit;
