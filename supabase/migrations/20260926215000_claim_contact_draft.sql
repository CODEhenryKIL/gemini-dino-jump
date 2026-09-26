begin;

create table if not exists dino_dev.claim_contact_draft (
  claim_id text primary key references dino_dev.claim(id) on delete cascade,
  recipient_name text not null,
  contact text not null,
  school text not null,
  address text,
  synthetic boolean not null default false,
  consent_at timestamptz not null,
  consent_version text not null check (consent_version = 'claim-contact-v1'),
  updated_at timestamptz not null default clock_timestamp()
);

alter table dino_dev.claim_contact_draft enable row level security;
alter table dino_dev.claim_contact_draft force row level security;
revoke all on dino_dev.claim_contact_draft from public;
do $$ begin
  if exists(select 1 from pg_roles where rolname='anon') then
    revoke all on dino_dev.claim_contact_draft from anon;
  end if;
  if exists(select 1 from pg_roles where rolname='authenticated') then
    revoke all on dino_dev.claim_contact_draft from authenticated;
  end if;
end $$;

drop policy if exists dino_dev_app_backend on dino_dev.claim_contact_draft;
create policy dino_dev_app_backend on dino_dev.claim_contact_draft
  for all to dino_dev_app using (true) with check (true);
grant select,insert,update,delete on dino_dev.claim_contact_draft to dino_dev_app;

alter table dino_dev.claim_contact
  drop constraint if exists claim_contact_real_consent_check;
alter table dino_dev.claim_contact
  add constraint claim_contact_real_consent_check
  check (
    synthetic or (
      consent_at is not null
      and consent_version in ('top3-contact-v1','claim-contact-v1')
    )
  );

insert into dino_dev.schema_version(version)
values ('20260926215000')
on conflict(version) do nothing;

commit;
