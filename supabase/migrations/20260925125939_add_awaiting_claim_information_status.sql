begin;

alter table dino_dev.claim drop constraint if exists claim_status_check;
alter table dino_dev.claim alter column status set default 'AWAITING_INFORMATION';
alter table dino_dev.claim add constraint claim_status_check check (
  status in (
    'AWAITING_INFORMATION','INFORMATION_RECEIVED','PENDING_REVIEW','CONTACTED',
    'PAID','ON_HOLD','INELIGIBLE','NO_RESPONSE'
  )
);

-- Only old rows that never received contact information are moved back to the
-- waiting state. Claims already being processed or finalized keep their state.
update dino_dev.claim c
set status='AWAITING_INFORMATION',updated_at=clock_timestamp()
where c.status='INFORMATION_RECEIVED'
  and c.contact_submitted_at is null
  and c.version=1
  and c.assignee_user_id is null
  and c.hold_reason is null
  and not c.external_delivery
  and c.verification_status='NOT_REQUESTED'
  and c.verification_reference is null
  and c.contacted_at is null
  and c.paid_at is null
  and not exists (
    select 1 from dino_dev.claim_contact cc where cc.claim_id=c.id
  )
  and not exists (
    select 1 from dino_dev.admin_audit a
    where a.target_type='claim' and a.target_id=c.id
  );

-- Older ranking submissions stored contact details without a submission time.
-- Repair the timestamp while preserving every workflow state.
update dino_dev.claim c
set contact_submitted_at=cc.created_at,updated_at=clock_timestamp()
from dino_dev.claim_contact cc
where cc.claim_id=c.id and c.contact_submitted_at is null;

insert into dino_dev.schema_version(version)
values ('20260925125939')
on conflict(version) do nothing;

commit;
