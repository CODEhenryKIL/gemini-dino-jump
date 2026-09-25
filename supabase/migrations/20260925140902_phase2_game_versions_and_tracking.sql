begin;

-- Additive rollout: legacy deployments keep their 1.2.0 leaderboard and campaign.
-- No campaign switch, ticket reset, participant replacement or history deletion.
alter table dino_dev.game_session
  add column if not exists game_summary jsonb not null default '{}'::jsonb,
  add column if not exists end_reason text;
alter table dino_dev.game_session drop constraint if exists game_session_score_check;
alter table dino_dev.game_session add constraint game_session_score_check
  check (score is null or (score >= 0 and score <= case when version='2.0.0' then 9000 else 6000 end));
do $$ begin
  if not exists(select 1 from pg_constraint where conrelid='dino_dev.game_session'::regclass and conname='game_session_end_reason_check') then
    alter table dino_dev.game_session add constraint game_session_end_reason_check
      check (end_reason is null or end_reason='COLLISION' or (version='2.0.0' and end_reason='TIME_LIMIT' and valid_ticks=36000));
  end if;
  if not exists(select 1 from pg_constraint where conrelid='dino_dev.game_session'::regclass and conname='game_session_version_identity') then
    alter table dino_dev.game_session add constraint game_session_version_identity unique(id,participant_id,version);
  end if;
end $$;

create table if not exists dino_dev.versioned_best_score (
  participant_id text not null references dino_dev.participant(id),
  game_version text not null check (game_version='2.0.0'),
  session_id text not null unique,
  score integer not null check (score between 0 and 9000),
  achieved_at timestamptz not null,
  primary key(participant_id,game_version),
  foreign key(session_id,participant_id,game_version) references dino_dev.game_session(id,participant_id,version)
);
create index if not exists versioned_best_score_rank_idx
  on dino_dev.versioned_best_score(game_version,score desc,achieved_at);
alter table dino_dev.versioned_best_score enable row level security;
alter table dino_dev.versioned_best_score force row level security;
revoke all on dino_dev.versioned_best_score from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on dino_dev.versioned_best_score from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on dino_dev.versioned_best_score from authenticated;
  end if;
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='versioned_best_score' and policyname='dino_dev_app_scores') then
    create policy dino_dev_app_scores on dino_dev.versioned_best_score
      for all to dino_dev_app using (true) with check (true);
  end if;
end $$;
grant select,insert,update on dino_dev.versioned_best_score to dino_dev_app;

alter table dino_dev.ranking_contact add column if not exists game_version text not null default '1.2.0';

-- Contact details remain reusable while every qualifying game version is retained.
create table if not exists dino_dev.ranking_contact_version (
  participant_id text not null references dino_dev.participant(id),
  game_version text not null check(game_version in ('1.2.0','2.0.0')),
  qualified_at timestamptz not null default clock_timestamp(),
  primary key(participant_id,game_version)
);
alter table dino_dev.ranking_contact_version enable row level security;
alter table dino_dev.ranking_contact_version force row level security;
revoke all on dino_dev.ranking_contact_version from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on dino_dev.ranking_contact_version from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on dino_dev.ranking_contact_version from authenticated;
  end if;
  if not exists(select 1 from pg_policies where schemaname='dino_dev' and tablename='ranking_contact_version' and policyname='dino_dev_app_contact_versions') then
    create policy dino_dev_app_contact_versions on dino_dev.ranking_contact_version
      for all to dino_dev_app using (true) with check (true);
  end if;
end $$;
grant select,insert on dino_dev.ranking_contact_version to dino_dev_app;
insert into dino_dev.ranking_contact_version(participant_id,game_version,qualified_at)
  select participant_id,game_version,requested_at from dino_dev.ranking_contact
  on conflict do nothing;

-- BEFORE INSERT also sees legacy ON CONFLICT DO NOTHING attempts, so an old
-- Preview qualifying an existing v2 contact still records its v1 provenance.
create or replace function dino_dev.record_ranking_contact_version() returns trigger
language plpgsql security invoker set search_path=pg_catalog,dino_dev as $$
begin
  insert into dino_dev.ranking_contact_version(participant_id,game_version,qualified_at)
    values(new.participant_id,new.game_version,coalesce(new.requested_at,clock_timestamp()))
    on conflict do nothing;
  return new;
end $$;
revoke all on function dino_dev.record_ranking_contact_version() from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on function dino_dev.record_ranking_contact_version() from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on function dino_dev.record_ranking_contact_version() from authenticated;
  end if;
end $$;
grant execute on function dino_dev.record_ranking_contact_version() to dino_dev_app;
drop trigger if exists record_ranking_contact_version on dino_dev.ranking_contact;
create trigger record_ranking_contact_version before insert or update of game_version
  on dino_dev.ranking_contact for each row execute function dino_dev.record_ranking_contact_version();

alter table dino_dev.ranking_snapshot add column if not exists game_version text not null default '1.2.0';
alter table dino_dev.ranking_snapshot_entry drop constraint if exists ranking_snapshot_entry_score_check;
alter table dino_dev.ranking_snapshot_entry add constraint ranking_snapshot_entry_score_check check(score between 0 and 9000);

insert into dino_dev.schema_version(version) values('20260925140902') on conflict(version) do nothing;
commit;
