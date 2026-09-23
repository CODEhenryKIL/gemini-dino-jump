begin;

do $$
begin
  if exists (select 1 from pg_namespace where nspname = 'dino') then
    raise exception 'Refusing migration: pre-existing dino schema requires manual audit';
  end if;
end $$;
create schema dino;
revoke all on schema dino from public;
do $$
begin
  if exists(select 1 from pg_roles where rolname='anon') then revoke all on schema dino from anon; end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then revoke all on schema dino from authenticated; end if;
end $$;

do $$
begin
  if exists (select 1 from pg_roles where rolname = 'dino_app') then
    if not exists (
      select 1 from pg_roles r
      left join pg_shdescription d on d.objoid=r.oid and d.classoid='pg_authid'::regclass
      where r.rolname='dino_app' and not r.rolsuper and not r.rolcreatedb
        and not r.rolcreaterole and not r.rolinherit and not r.rolbypassrls
        and not r.rolcanlogin and d.description='gemini-dino-jump phase1 backend role'
    ) then
      raise exception 'Refusing migration: pre-existing dino_app role requires manual audit';
    end if;
    return;
  end if;
  create role dino_app nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls;
  comment on role dino_app is 'gemini-dino-jump phase1 backend role';
end $$;

grant usage on schema dino to dino_app;

create table dino.schema_version (
  version text primary key,
  applied_at timestamptz not null default now()
);
insert into dino.schema_version(version) values ('20260923033611');

create table dino.environment_guard (
  singleton boolean primary key default true check (singleton),
  environment text not null check (environment in ('local','test','preview','production')),
  project_ref text not null,
  synthetic_only boolean not null default true,
  seeded boolean not null default false,
  updated_at timestamptz not null default now(),
  check (environment <> 'production' or synthetic_only = false)
);

create table dino.campaign (
  id text primary key,
  title text not null,
  status text not null check (status in ('ACTIVE','MAINTENANCE','PAUSED','ENDED')),
  game_version text not null,
  benefit_url text not null,
  settings jsonb not null default '{}'::jsonb,
  is_test boolean not null default false,
  real_prizes_enabled boolean not null default false,
  updated_at timestamptz not null default now(),
  check (real_prizes_enabled = false)
);

create table dino.participant (
  id text primary key,
  campaign_id text not null references dino.campaign(id),
  token_hash text not null unique check (length(token_hash) between 32 and 128),
  nickname text not null check (char_length(nickname) between 1 and 24),
  is_public boolean not null default true,
  referral_code text not null unique,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','BLOCKED','WITHDRAWN')),
  environment text not null check (environment in ('local','test','preview','production')),
  synthetic boolean not null default false,
  channel text,
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now(),
  unique(id, campaign_id)
);

create table dino.ticket_ledger (
  id bigint generated always as identity primary key,
  participant_id text not null references dino.participant(id),
  delta integer not null check (delta <> 0),
  source_type text not null check (source_type in ('INITIAL','REFERRAL','PLAY_CONSUME','ADMIN_ADJUST')),
  source_id text not null,
  idempotency_key text,
  request_hash text,
  created_at timestamptz not null default now(),
  unique (participant_id, source_type, source_id),
  unique (participant_id, idempotency_key)
);
create index ticket_ledger_participant_created_idx on dino.ticket_ledger(participant_id, created_at desc);

create table dino.game_session (
  id text primary key,
  participant_id text not null,
  campaign_id text not null references dino.campaign(id),
  idempotency_key text not null,
  seed bigint not null,
  version text not null,
  status text not null default 'RESERVED' check (status in ('RESERVED','ACTIVE','FINISHED','REJECTED','ABORTED','EXPIRED')),
  reserved_at timestamptz not null default now(),
  started_at timestamptz,
  expires_at timestamptz not null,
  finished_at timestamptz,
  score integer check (score between 0 and 10000000),
  valid_ticks integer check (valid_ticks between 0 and 36000),
  verification_result text,
  environment text not null,
  synthetic boolean not null default false,
  created_at timestamptz not null default now(),
  unique(participant_id, idempotency_key),
  unique(id, participant_id),
  unique(id, participant_id, campaign_id),
  foreign key(participant_id, campaign_id) references dino.participant(id, campaign_id)
);
create index game_session_participant_status_idx on dino.game_session(participant_id, status, created_at desc);

create table dino.best_score (
  participant_id text primary key references dino.participant(id),
  session_id text not null unique,
  score integer not null check (score >= 0),
  achieved_at timestamptz not null,
  foreign key(session_id,participant_id) references dino.game_session(id,participant_id)
);

create table dino.referral (
  id text primary key,
  inviter_id text not null references dino.participant(id),
  invitee_id text not null unique references dino.participant(id),
  status text not null default 'PENDING' check (status in ('PENDING','QUALIFIED','REWARDED')),
  created_at timestamptz not null default now(),
  qualified_at timestamptz,
  rewarded_at timestamptz,
  check (inviter_id <> invitee_id)
);
create index referral_inviter_status_idx on dino.referral(inviter_id, status);

create table dino.prize (
  id text primary key,
  campaign_id text not null references dino.campaign(id),
  name text not null,
  category text not null check (category in ('COUPON','DIGITAL','SHIPPING','NO_PRIZE')),
  image_url text not null,
  probability numeric(8,7) not null check (probability >= 0 and probability <= 1),
  is_active boolean not null default false,
  is_test boolean not null default false
);

create table dino.inventory_item (
  id text primary key,
  prize_id text not null references dino.prize(id),
  status text not null default 'AVAILABLE' check (status in ('AVAILABLE','RESERVED','TEST_ISSUED','ISSUED','EXPIRED','VOID')),
  reserved_by_draw_id text,
  reserved_at timestamptz,
  issued_at timestamptz,
  created_at timestamptz not null default now(),
  unique(id, prize_id)
);
create index inventory_prize_status_idx on dino.inventory_item(prize_id, status, created_at);

create table dino.draw (
  id text primary key,
  session_id text not null unique,
  participant_id text not null references dino.participant(id),
  pouch_index smallint not null check (pouch_index between 0 and 2),
  prize_id text not null references dino.prize(id),
  inventory_item_id text unique references dino.inventory_item(id),
  is_won boolean not null,
  scratch_completed boolean not null default false,
  is_test boolean not null default false,
  created_at timestamptz not null default now(),
  unique(id, participant_id, prize_id, inventory_item_id),
  foreign key(session_id, participant_id) references dino.game_session(id, participant_id),
  foreign key(inventory_item_id, prize_id) references dino.inventory_item(id, prize_id)
);
alter table dino.inventory_item add constraint inventory_reserved_draw_fk foreign key (reserved_by_draw_id) references dino.draw(id) deferrable initially deferred;

create table dino.inventory_history (
  id bigint generated always as identity primary key,
  inventory_item_id text not null references dino.inventory_item(id),
  from_status text,
  to_status text not null,
  reason text not null,
  related_type text,
  related_id text,
  created_at timestamptz not null default now()
);

create table dino.claim (
  id text primary key,
  draw_id text not null unique,
  participant_id text not null references dino.participant(id),
  prize_id text not null references dino.prize(id),
  inventory_item_id text not null unique references dino.inventory_item(id),
  status text not null default 'READY' check (status in ('READY','SUBMITTED','DELIVERY_PENDING','TEST_ISSUED','ISSUED','FAILED','EXPIRED','REJECTED')),
  expires_at timestamptz not null,
  submitted_at timestamptz,
  is_test boolean not null default false,
  created_at timestamptz not null default now(),
  foreign key(draw_id, participant_id, prize_id, inventory_item_id) references dino.draw(id, participant_id, prize_id, inventory_item_id),
  foreign key(inventory_item_id, prize_id) references dino.inventory_item(id, prize_id)
);
create index claim_participant_status_idx on dino.claim(participant_id, status, created_at desc);

create table dino.claim_recipient (
  claim_id text primary key references dino.claim(id) on delete cascade,
  recipient_name text not null,
  contact_phone text not null,
  shipping_address text,
  consented_at timestamptz not null,
  synthetic boolean not null
);

create table dino.delivery_attempt (
  id text primary key,
  claim_id text not null references dino.claim(id),
  provider text not null,
  idempotency_key text not null,
  status text not null check (status in ('PENDING','SUCCEEDED','FAILED','DISABLED')),
  response jsonb not null default '{}'::jsonb,
  created_at timestamptz not null default now(),
  unique(claim_id, idempotency_key)
);

create table dino.benefit_verification (
  participant_id text primary key references dino.participant(id),
  status text not null default 'PENDING' check (status in ('PENDING','REJECTED')),
  updated_at timestamptz not null default now()
);

create table dino.analytics_event (
  id bigint generated always as identity primary key,
  event_id text not null unique,
  participant_id text references dino.participant(id),
  event_name text not null,
  screen text,
  active_ms integer check (active_ms is null or active_ms between 0 and 3600000),
  channel text,
  error_code text,
  environment text not null,
  synthetic boolean not null default false,
  source text not null check (source in ('client','server')),
  occurred_at timestamptz not null default now()
);
create index analytics_environment_time_idx on dino.analytics_event(environment, synthetic, occurred_at);
create index analytics_name_time_idx on dino.analytics_event(event_name, occurred_at);

create table dino.admin_member (
  auth_user_id uuid primary key,
  active boolean not null default true,
  can_view_claim_metadata boolean not null default false,
  created_at timestamptz not null default now()
);

create table dino.admin_audit (
  id bigint generated always as identity primary key,
  admin_user_id uuid not null,
  action text not null,
  target_type text not null,
  target_id text,
  before_value jsonb,
  after_value jsonb,
  reason text not null check (char_length(reason) between 3 and 500),
  idempotency_key text,
  created_at timestamptz not null default now(),
  unique(admin_user_id, action, idempotency_key)
);

create table dino.rate_limit_bucket (
  bucket_key text primary key,
  window_started_at timestamptz not null,
  count integer not null check (count >= 0),
  updated_at timestamptz not null default now()
);

create or replace function dino.consume_rate_limit(p_key text, p_limit integer, p_window_seconds integer)
returns boolean language plpgsql security invoker set search_path = dino, pg_temp as $$
declare allowed boolean;
begin
  if p_limit < 1 or p_window_seconds < 1 then return false; end if;
  insert into dino.rate_limit_bucket(bucket_key, window_started_at, count)
  values (p_key, now(), 1)
  on conflict (bucket_key) do update
    set count = case when dino.rate_limit_bucket.window_started_at <= now() - make_interval(secs => p_window_seconds) then 1 else dino.rate_limit_bucket.count + 1 end,
        window_started_at = case when dino.rate_limit_bucket.window_started_at <= now() - make_interval(secs => p_window_seconds) then now() else dino.rate_limit_bucket.window_started_at end,
        updated_at = now()
  returning count <= p_limit into allowed;
  return allowed;
end $$;

do $$
declare t text;
begin
  foreach t in array array['campaign','participant','ticket_ledger','game_session','best_score','referral','prize','inventory_item','inventory_history','draw','claim','claim_recipient','delivery_attempt','benefit_verification','analytics_event','admin_audit','rate_limit_bucket']
  loop
    execute format('alter table dino.%I enable row level security', t);
    execute format('alter table dino.%I force row level security', t);
    execute format('revoke all on dino.%I from public', t);
    if exists(select 1 from pg_roles where rolname='anon') then execute format('revoke all on dino.%I from anon', t); end if;
    if exists(select 1 from pg_roles where rolname='authenticated') then execute format('revoke all on dino.%I from authenticated', t); end if;
    execute format('create policy dino_app_backend on dino.%I for all to dino_app using (true) with check (true)', t);
  end loop;
end $$;
grant select on dino.campaign to dino_app;
grant update(status,updated_at) on dino.campaign to dino_app;
grant select, insert, update on dino.participant, dino.game_session, dino.best_score, dino.referral, dino.draw, dino.claim, dino.benefit_verification, dino.rate_limit_bucket to dino_app;
grant select, insert on dino.ticket_ledger, dino.delivery_attempt, dino.analytics_event, dino.admin_audit to dino_app;
grant insert on dino.inventory_history, dino.claim_recipient to dino_app;
grant select on dino.prize to dino_app;
grant select, update on dino.inventory_item to dino_app;
alter table dino.schema_version enable row level security;
alter table dino.schema_version force row level security;
alter table dino.environment_guard enable row level security;
alter table dino.environment_guard force row level security;
alter table dino.admin_member enable row level security;
alter table dino.admin_member force row level security;
revoke all on dino.schema_version, dino.environment_guard, dino.admin_member from public, dino_app;
do $$
begin
  if exists(select 1 from pg_roles where rolname='anon') then revoke all on dino.schema_version, dino.environment_guard, dino.admin_member from anon; end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then revoke all on dino.schema_version, dino.environment_guard, dino.admin_member from authenticated; end if;
end $$;
grant select on dino.schema_version, dino.environment_guard, dino.admin_member to dino_app;
create policy dino_app_read_version on dino.schema_version for select to dino_app using (true);
create policy dino_app_read_environment on dino.environment_guard for select to dino_app using (true);
create policy dino_app_read_admin_members on dino.admin_member for select to dino_app using (true);
grant usage, select on all sequences in schema dino to dino_app;
revoke all on function dino.consume_rate_limit(text, integer, integer) from public;
do $$
begin
  if exists(select 1 from pg_roles where rolname='anon') then revoke all on function dino.consume_rate_limit(text, integer, integer) from anon; end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then revoke all on function dino.consume_rate_limit(text, integer, integer) from authenticated; end if;
end $$;
grant execute on function dino.consume_rate_limit(text, integer, integer) to dino_app;

commit;
