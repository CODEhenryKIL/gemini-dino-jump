begin;

alter table dino_dev.claim_contact
  drop constraint if exists claim_contact_synthetic_check;

alter table dino_dev.claim_contact
  add column if not exists consent_at timestamptz,
  add column if not exists consent_version text;

alter table dino_dev.claim_contact
  drop constraint if exists claim_contact_real_consent_check;

alter table dino_dev.claim_contact
  add constraint claim_contact_real_consent_check
  check (synthetic or (consent_at is not null and consent_version is not null and consent_version = 'top3-contact-v1'));

comment on column dino_dev.claim_contact.synthetic is
  'False for participant-provided TOP3 contact; true for generated test claim data.';
comment on column dino_dev.claim_contact.consent_at is
  'Time the participant accepted the versioned TOP3 contact collection notice.';

insert into dino_dev.schema_version(version)
values ('20260926103809')
on conflict(version) do nothing;

commit;
