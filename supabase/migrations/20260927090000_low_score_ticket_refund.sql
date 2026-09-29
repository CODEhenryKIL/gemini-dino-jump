begin;

alter table dino_dev.ticket_ledger
  drop constraint if exists ticket_ledger_source_type_check;
alter table dino_dev.ticket_ledger
  add constraint ticket_ledger_source_type_check
  check (source_type in (
    'INITIAL_GRANT',
    'INVITATION_GRANT',
    'PLAY_CONSUME',
    'FAULT_REFUND',
    'LOW_SCORE_REFUND'
  ));

insert into dino_dev.schema_version(version)
values ('20260927090000')
on conflict(version) do nothing;

commit;
