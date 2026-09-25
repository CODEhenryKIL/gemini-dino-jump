begin;

do $$ begin
  if not exists (select 1 from pg_roles where rolname = 'dino_dev_app') then
    create role dino_dev_app nologin nosuperuser nocreatedb nocreaterole noinherit nobypassrls connection limit 20;
  end if;
end $$;

create schema if not exists dino_dev;
revoke all on schema dino_dev from public;
grant usage on schema dino_dev to dino_dev_app;

create table dino_dev.schema_version (
  version text primary key,
  applied_at timestamptz not null default clock_timestamp()
);
insert into dino_dev.schema_version(version) values ('20260925083548');

create table dino_dev.environment_guard (
  singleton boolean primary key default true check (singleton),
  environment text not null check (environment in ('local','test','preview')),
  project_ref text not null,
  schema_name text not null default 'dino_dev' check (schema_name = 'dino_dev'),
  synthetic_only boolean not null default true check (synthetic_only),
  test_seed boolean not null default false,
  updated_at timestamptz not null default clock_timestamp()
);

create table dino_dev.campaign (
  id text primary key,
  title text not null,
  status text not null default 'ACTIVE' check (status in ('ACTIVE','PAUSED','ENDED')),
  version integer not null default 1 check (version > 0),
  game_version text not null,
  benefit_url text not null,
  settings jsonb not null default '{}'::jsonb,
  probability_version text not null,
  opens_at timestamptz,
  closes_at timestamptz,
  is_test boolean not null default true check (is_test),
  real_prizes_enabled boolean not null default false check (not real_prizes_enabled),
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp()
);
alter table dino_dev.environment_guard add column campaign_id text references dino_dev.campaign(id);

create table dino_dev.participant (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  token_hash text not null unique check (length(token_hash) = 64),
  token_expires_at timestamptz not null,
  nickname text not null check (char_length(nickname) between 1 and 24),
  is_public boolean not null default true,
  referral_code text not null unique check (char_length(referral_code) between 12 and 64),
  status text not null default 'ACTIVE' check (status in ('ACTIVE','BLOCKED','WITHDRAWN')),
  environment text not null check (environment in ('local','test','preview')),
  synthetic boolean not null default true check (synthetic),
  initial_balance smallint not null default 1 check (initial_balance between 0 and 1),
  invitation_balance smallint not null default 0 check (invitation_balance between 0 and 3),
  invitation_refund_pending smallint not null default 0 check (invitation_refund_pending between 0 and 3),
  cooldown_until timestamptz,
  cooldown_notice_pending boolean not null default false,
  first_link_kind text,
  first_channel text,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  check (invitation_balance + invitation_refund_pending <= 3),
  unique(id,campaign_id)
);

create table dino_dev.ticket_ledger (
  id bigint generated always as identity primary key,
  participant_id text not null references dino_dev.participant(id),
  ticket_kind text not null check (ticket_kind in ('INITIAL','INVITATION')),
  delta smallint not null check (delta in (-1,1)),
  source_type text not null check (source_type in ('INITIAL_GRANT','INVITATION_GRANT','PLAY_CONSUME','FAULT_REFUND')),
  source_id text not null,
  balance_after smallint not null check (balance_after between 0 and 3),
  cooldown_until timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  unique(participant_id,source_type,source_id)
);
create index ticket_ledger_participant_time_idx on dino_dev.ticket_ledger(participant_id,created_at desc);

create table dino_dev.observation (
  id text primary key,
  event_id text not null unique,
  actor_key text not null,
  idempotency_key text not null,
  request_hash text not null,
  participant_id text references dino_dev.participant(id),
  link_kind text,
  channel_code text,
  campaign_code text,
  share_id text,
  referrer_origin text,
  environment text not null,
  synthetic boolean not null default true,
  created_at timestamptz not null default clock_timestamp(),
  linked_at timestamptz,
  unique(actor_key,idempotency_key)
);

create table dino_dev.bootstrap (
  token_hash text primary key check (length(token_hash)=64),
  observation_id text not null unique references dino_dev.observation(id),
  participant_id text unique references dino_dev.participant(id),
  expires_at timestamptz not null,
  consumed_at timestamptz,
  created_at timestamptz not null default clock_timestamp()
);

create table dino_dev.invitation_visit (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  inviter_id text not null references dino_dev.participant(id),
  visitor_id text not null references dino_dev.participant(id),
  nonce_hash text not null unique check (length(nonce_hash) = 64),
  share_id text,
  status text not null default 'PENDING' check (status in ('PENDING','REWARDED','ALREADY_REWARDED','SELF_INVITE','COOLDOWN','BALANCE_FULL','NOT_QUALIFIED','INVALID_NONCE')),
  reason text,
  expires_at timestamptz not null,
  qualified_at timestamptz,
  active_ms integer,
  interacted boolean,
  created_at timestamptz not null default clock_timestamp(),
  check (inviter_id <> visitor_id)
);
create index invitation_visit_inviter_time_idx on dino_dev.invitation_visit(inviter_id,created_at desc);
create index invitation_visit_visitor_time_idx on dino_dev.invitation_visit(visitor_id,created_at desc);

create table dino_dev.invitation_reward (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  inviter_id text not null references dino_dev.participant(id),
  visitor_id text not null references dino_dev.participant(id),
  visit_id text not null unique references dino_dev.invitation_visit(id),
  granted_at timestamptz not null default clock_timestamp(),
  unique(campaign_id,inviter_id,visitor_id),
  check (inviter_id <> visitor_id)
);

create table dino_dev.game_session (
  id text primary key,
  participant_id text not null,
  campaign_id text not null,
  idempotency_key text not null,
  seed bigint not null,
  version text not null,
  status text not null default 'RESERVED' check (status in ('RESERVED','ACTIVE','FAULT_REPORTED','FINISHED','REJECTED','ABORTED','EXPIRED')),
  ticket_kind text not null check (ticket_kind in ('INITIAL','INVITATION')),
  ticket_refund_status text not null default 'PENDING' check (ticket_refund_status in ('PENDING','NOT_DUE','REFUNDED')),
  reserved_at timestamptz not null default clock_timestamp(),
  started_at timestamptz,
  finished_at timestamptz,
  expires_at timestamptz not null,
  score integer check (score between 0 and 6000),
  valid_ticks integer check (valid_ticks between 0 and 36000),
  verification_result text,
  fault_reason text,
  fault_reported_at timestamptz,
  fault_review_status text not null default 'NONE' check (fault_review_status in ('NONE','PENDING','AUTO_APPROVED','APPROVED','DENIED')),
  fault_review_version integer not null default 0 check (fault_review_version >= 0),
  fault_reviewed_by uuid,
  fault_reviewed_at timestamptz,
  fault_review_reason text,
  last_checkpoint_tick integer check (last_checkpoint_tick is null or last_checkpoint_tick between 0 and 36000),
  environment text not null,
  synthetic boolean not null default true,
  unique(participant_id,idempotency_key),
  unique(id,participant_id),
  foreign key(participant_id,campaign_id) references dino_dev.participant(id,campaign_id)
);
create index game_session_participant_status_idx on dino_dev.game_session(participant_id,status,reserved_at desc);

create table dino_dev.best_score (
  participant_id text primary key references dino_dev.participant(id),
  session_id text not null unique,
  score integer not null check (score between 0 and 6000),
  achieved_at timestamptz not null,
  foreign key(session_id,participant_id) references dino_dev.game_session(id,participant_id)
);
create index best_score_rank_idx on dino_dev.best_score(score desc,achieved_at);

create table dino_dev.ranking_contact (
  participant_id text primary key references dino_dev.participant(id),
  status text not null default 'REQUESTED' check (status in ('REQUESTED','SUBMITTED')),
  recipient_name text,
  contact text,
  school text,
  synthetic boolean not null default true check (synthetic),
  requested_at timestamptz not null default clock_timestamp(),
  submitted_at timestamptz,
  updated_at timestamptz not null default clock_timestamp()
);

create table dino_dev.prize (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  name text not null,
  category text not null check (category in ('COUPON','DIGITAL','SHIPPING','NO_PRIZE')),
  image_url text not null,
  probability numeric(8,7) not null check (probability between 0 and 1),
  is_active boolean not null default true,
  is_test boolean not null default true check (is_test)
);

create table dino_dev.inventory_item (
  id text primary key,
  prize_id text not null references dino_dev.prize(id),
  status text not null default 'AVAILABLE' check (status in ('AVAILABLE','RESERVED','PAID','EXPIRED','VOID')),
  reserved_by_draw_id text unique,
  reserved_at timestamptz,
  paid_at timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  unique(id,prize_id)
);
create index inventory_available_idx on dino_dev.inventory_item(prize_id,created_at,id) where status='AVAILABLE';

create table dino_dev.draw (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  participant_id text not null references dino_dev.participant(id),
  eligible_session_id text not null,
  pouch_index smallint not null check (pouch_index between 0 and 2),
  prize_id text not null references dino_dev.prize(id),
  inventory_item_id text unique references dino_dev.inventory_item(id),
  is_won boolean not null,
  probability_version text not null,
  random_audit_hash text not null check (length(random_audit_hash)=64),
  revealed boolean not null default false,
  scratch_completed boolean not null default false,
  created_at timestamptz not null default clock_timestamp(),
  unique(campaign_id,participant_id),
  foreign key(eligible_session_id,participant_id) references dino_dev.game_session(id,participant_id)
);
alter table dino_dev.inventory_item add constraint inventory_draw_fk
  foreign key(reserved_by_draw_id) references dino_dev.draw(id) deferrable initially deferred;

create table dino_dev.inventory_history (
  id bigint generated always as identity primary key,
  inventory_item_id text not null references dino_dev.inventory_item(id),
  from_status text,
  to_status text not null,
  reason text not null,
  related_type text,
  related_id text,
  created_at timestamptz not null default clock_timestamp()
);

create table dino_dev.claim (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  participant_id text not null references dino_dev.participant(id),
  draw_id text unique references dino_dev.draw(id),
  claim_type text not null check (claim_type in ('DRAW','RANKING')),
  prize_id text references dino_dev.prize(id),
  inventory_item_id text unique references dino_dev.inventory_item(id),
  status text not null default 'INFORMATION_RECEIVED' check (status in ('INFORMATION_RECEIVED','PENDING_REVIEW','CONTACTED','PAID','ON_HOLD','INELIGIBLE','NO_RESPONSE')),
  assignee_user_id uuid,
  hold_reason text,
  external_delivery boolean not null default false,
  verification_status text not null default 'NOT_REQUESTED' check (verification_status in ('NOT_REQUESTED','PENDING','VERIFIED','REJECTED')),
  verification_reference text,
  version integer not null default 1 check (version > 0),
  contact_submitted_at timestamptz,
  contacted_at timestamptz,
  paid_at timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  unique(campaign_id,participant_id,claim_type)
);
create index claim_work_queue_idx on dino_dev.claim(status,assignee_user_id,updated_at,id);

create table dino_dev.claim_contact (
  claim_id text primary key references dino_dev.claim(id) on delete cascade,
  recipient_name text not null,
  contact text not null,
  school text,
  address text,
  synthetic boolean not null default true check (synthetic),
  created_at timestamptz not null default clock_timestamp()
);

create table dino_dev.analytics_event (
  id bigint generated always as identity primary key,
  event_id text not null unique,
  campaign_id text not null references dino_dev.campaign(id),
  participant_id text references dino_dev.participant(id),
  observation_id text references dino_dev.observation(id),
  event_name text not null,
  screen text,
  screen_view_id text,
  visit_session_id text,
  game_session_id text references dino_dev.game_session(id),
  active_ms integer check (active_ms is null or active_ms between 0 and 3600000),
  dimensions jsonb not null default '{}'::jsonb,
  environment text not null,
  deployment text not null,
  event_version text not null,
  synthetic boolean not null default true,
  source text not null check (source in ('client','server')),
  occurred_at timestamptz not null,
  received_at timestamptz not null default clock_timestamp()
);
create index analytics_scope_idx on dino_dev.analytics_event(environment,synthetic,received_at,event_name);
create index analytics_participant_event_idx on dino_dev.analytics_event(participant_id,event_name,occurred_at);
create index analytics_observation_idx on dino_dev.analytics_event(observation_id,occurred_at);

create table dino_dev.idempotency_request (
  actor_key text not null,
  route text not null,
  idempotency_key text not null,
  request_hash text not null,
  response_status integer not null,
  response_body jsonb not null,
  created_at timestamptz not null default clock_timestamp(),
  primary key(actor_key,route,idempotency_key)
);

create table dino_dev.admin_member (
  auth_user_id uuid primary key,
  display_name text not null,
  active boolean not null default true,
  permissions text[] not null default array['analytics:read']::text[],
  synthetic boolean not null default true check (synthetic),
  created_at timestamptz not null default clock_timestamp()
);

create table dino_dev.ranking_snapshot (
  id text primary key,
  campaign_id text not null references dino_dev.campaign(id),
  status text not null default 'DRAFT' check (status = 'DRAFT'),
  tie_policy text not null default 'UNDECIDED' check (tie_policy = 'UNDECIDED'),
  campaign_closes_at timestamptz,
  captured_at timestamptz not null default clock_timestamp(),
  created_by uuid not null references dino_dev.admin_member(auth_user_id),
  synthetic boolean not null default true check (synthetic)
);

create table dino_dev.ranking_snapshot_entry (
  snapshot_id text not null references dino_dev.ranking_snapshot(id),
  participant_id text not null references dino_dev.participant(id),
  score integer not null check (score between 0 and 6000),
  rank integer not null check (rank > 0),
  tied boolean not null,
  contact_status text not null,
  primary key(snapshot_id,participant_id)
);

create table dino_dev.admin_audit (
  id bigint generated always as identity primary key,
  admin_user_id uuid not null,
  action text not null,
  target_type text not null,
  target_id text,
  before_value jsonb,
  after_value jsonb,
  reason text,
  event_id text not null unique,
  created_at timestamptz not null default clock_timestamp()
);

create table dino_dev.rate_limit_bucket (
  bucket_key text primary key,
  window_started_at timestamptz not null,
  count integer not null check (count >= 0),
  updated_at timestamptz not null default clock_timestamp()
);

create or replace function dino_dev.consume_rate_limit(p_key text,p_limit integer,p_window_seconds integer)
returns boolean language plpgsql security invoker set search_path=dino_dev,pg_temp as $$
declare allowed boolean;
begin
  if p_limit < 1 or p_window_seconds < 1 then return false; end if;
  insert into dino_dev.rate_limit_bucket(bucket_key,window_started_at,count) values(p_key,clock_timestamp(),1)
  on conflict(bucket_key) do update set
    count=case when dino_dev.rate_limit_bucket.window_started_at <= clock_timestamp()-make_interval(secs=>p_window_seconds) then 1 else dino_dev.rate_limit_bucket.count+1 end,
    window_started_at=case when dino_dev.rate_limit_bucket.window_started_at <= clock_timestamp()-make_interval(secs=>p_window_seconds) then clock_timestamp() else dino_dev.rate_limit_bucket.window_started_at end,
    updated_at=clock_timestamp()
  returning count <= p_limit into allowed;
  return allowed;
end $$;

do $$ declare t text; begin
  foreach t in array array[
    'schema_version','environment_guard','campaign','participant','ticket_ledger','observation','bootstrap',
    'invitation_visit','invitation_reward','game_session','best_score','ranking_contact','prize',
    'inventory_item','draw','inventory_history','claim','claim_contact','analytics_event',
    'idempotency_request','admin_member','ranking_snapshot','ranking_snapshot_entry','admin_audit','rate_limit_bucket'
  ] loop
    execute format('alter table dino_dev.%I enable row level security',t);
    execute format('alter table dino_dev.%I force row level security',t);
    execute format('revoke all on dino_dev.%I from public',t);
    if exists(select 1 from pg_roles where rolname='anon') then execute format('revoke all on dino_dev.%I from anon',t); end if;
    if exists(select 1 from pg_roles where rolname='authenticated') then execute format('revoke all on dino_dev.%I from authenticated',t); end if;
  end loop;
end $$;

do $$ declare t text; begin
  foreach t in array array['participant','observation','bootstrap','invitation_visit','game_session','best_score','ranking_contact','inventory_item','draw','claim','rate_limit_bucket'] loop
    execute format('create policy dino_dev_app_backend on dino_dev.%I for all to dino_dev_app using (true) with check (true)',t);
  end loop;
  foreach t in array array['schema_version','environment_guard','admin_member','prize'] loop
    execute format('create policy dino_dev_app_read on dino_dev.%I for select to dino_dev_app using (true)',t);
  end loop;
  foreach t in array array['ticket_ledger','invitation_reward','inventory_history','claim_contact','analytics_event','idempotency_request','admin_audit'] loop
    execute format('create policy dino_dev_app_read on dino_dev.%I for select to dino_dev_app using (true)',t);
    execute format('create policy dino_dev_app_append on dino_dev.%I for insert to dino_dev_app with check (true)',t);
  end loop;
  foreach t in array array['ranking_snapshot','ranking_snapshot_entry'] loop
    execute format('create policy dino_dev_app_read on dino_dev.%I for select to dino_dev_app using (true)',t);
    execute format('create policy dino_dev_app_append on dino_dev.%I for insert to dino_dev_app with check (true)',t);
  end loop;
end $$;
create policy dino_dev_app_campaign_read on dino_dev.campaign for select to dino_dev_app using (true);
create policy dino_dev_app_campaign_update on dino_dev.campaign for update to dino_dev_app using (true) with check (true);

grant select on dino_dev.schema_version,dino_dev.environment_guard,dino_dev.admin_member,dino_dev.prize to dino_dev_app;
grant select,update(status,version,updated_at) on dino_dev.campaign to dino_dev_app;
grant select,insert,update on dino_dev.participant,dino_dev.observation,dino_dev.bootstrap,dino_dev.invitation_visit,
  dino_dev.game_session,dino_dev.best_score,dino_dev.ranking_contact,dino_dev.inventory_item,dino_dev.draw,
  dino_dev.claim,dino_dev.rate_limit_bucket to dino_dev_app;
grant select,insert on dino_dev.ticket_ledger,dino_dev.invitation_reward,dino_dev.inventory_history,
  dino_dev.claim_contact,dino_dev.analytics_event,dino_dev.idempotency_request,dino_dev.ranking_snapshot,
  dino_dev.ranking_snapshot_entry,dino_dev.admin_audit to dino_dev_app;
grant usage,select on all sequences in schema dino_dev to dino_dev_app;
revoke all on function dino_dev.consume_rate_limit(text,integer,integer) from public;
grant execute on function dino_dev.consume_rate_limit(text,integer,integer) to dino_dev_app;
alter default privileges in schema dino_dev revoke all on tables from public;
alter default privileges in schema dino_dev revoke all on tables from dino_dev_app;
alter default privileges in schema dino_dev revoke all on sequences from dino_dev_app;

commit;
