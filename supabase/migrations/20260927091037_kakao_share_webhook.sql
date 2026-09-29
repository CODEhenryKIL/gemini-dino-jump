begin;

alter table dino_dev.ticket_ledger
  drop constraint if exists ticket_ledger_source_type_check;
alter table dino_dev.ticket_ledger
  add constraint ticket_ledger_source_type_check
  check (source_type in (
    'INITIAL_GRANT',
    'INVITATION_GRANT',
    'SHARE_GRANT',
    'PLAY_CONSUME',
    'FAULT_REFUND',
    'LOW_SCORE_REFUND',
    'INCOMPLETE_REFUND'
  ));

alter table dino_dev.invitation_visit
  drop constraint if exists invitation_visit_status_check;
alter table dino_dev.invitation_visit
  add constraint invitation_visit_status_check
  check (status in (
    'PENDING',
    'QUALIFIED',
    'ALREADY_QUALIFIED',
    'REWARDED',
    'ALREADY_REWARDED',
    'SELF_INVITE',
    'COOLDOWN',
    'BALANCE_FULL',
    'NOT_QUALIFIED',
    'INVALID_NONCE'
  ));

create table dino_dev.kakao_share_intent (
  id text primary key,
  participant_id text not null references dino_dev.participant(id) on delete cascade,
  campaign_id text not null references dino_dev.campaign(id),
  claim_id text references dino_dev.claim(id) on delete cascade,
  kind text not null check (kind in ('record_share','retry_invite','prize_share','general_share')),
  callback_token_hash text not null unique check (length(callback_token_hash)=64),
  environment text not null check (environment in ('local','test','preview')),
  status text not null default 'PENDING' check (status in ('PENDING','CONFIRMED','REJECTED','EXPIRED')),
  reward_status text not null default 'PENDING' check (reward_status in ('PENDING','GRANTED','BLOCKED_CAP','BLOCKED_COOLDOWN','NOT_ELIGIBLE')),
  resource_id text,
  chat_type text,
  hash_chat_id text,
  expires_at timestamptz not null,
  confirmed_at timestamptz,
  created_at timestamptz not null default clock_timestamp(),
  updated_at timestamptz not null default clock_timestamp(),
  foreign key(participant_id,campaign_id) references dino_dev.participant(id,campaign_id),
  check (resource_id is null or char_length(resource_id) between 1 and 128),
  check (hash_chat_id is null or char_length(hash_chat_id) between 1 and 256)
);
create unique index kakao_share_intent_resource_idx
  on dino_dev.kakao_share_intent(resource_id)
  where resource_id is not null;
create index kakao_share_intent_participant_time_idx
  on dino_dev.kakao_share_intent(participant_id,created_at desc);
create index kakao_share_intent_claim_time_idx
  on dino_dev.kakao_share_intent(claim_id,created_at desc)
  where claim_id is not null;

alter table dino_dev.kakao_share_intent enable row level security;
alter table dino_dev.kakao_share_intent force row level security;
revoke all on dino_dev.kakao_share_intent from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on dino_dev.kakao_share_intent from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on dino_dev.kakao_share_intent from authenticated;
  end if;
end $$;
drop policy if exists dino_dev_app_backend on dino_dev.kakao_share_intent;
create policy dino_dev_app_backend on dino_dev.kakao_share_intent
  for all to dino_dev_app using (true) with check (true);
grant select,insert,update on dino_dev.kakao_share_intent to dino_dev_app;

insert into dino_dev.schema_version(version)
values ('20260927091037')
on conflict(version) do nothing;

commit;
