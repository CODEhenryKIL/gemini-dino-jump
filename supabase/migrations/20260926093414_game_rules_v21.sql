begin;

-- Add v2.1 alongside the frozen v2.0 rules. Existing sessions and scores stay
-- tied to their original version and remain replayable by the old verifier.
alter table dino_dev.game_session drop constraint if exists game_session_score_check;
alter table dino_dev.game_session add constraint game_session_score_check
  check (score is null or (score >= 0 and score <= case when version in ('2.0.0','2.1.0') then 9000 else 6000 end));

alter table dino_dev.game_session drop constraint if exists game_session_end_reason_check;
alter table dino_dev.game_session add constraint game_session_end_reason_check check (
  end_reason is null
  or end_reason='COLLISION'
  or (version in ('2.0.0','2.1.0') and end_reason='TIME_LIMIT' and valid_ticks=36000)
);

alter table dino_dev.versioned_best_score
  drop constraint if exists versioned_best_score_game_version_check;
alter table dino_dev.versioned_best_score
  add constraint versioned_best_score_game_version_check
  check (game_version in ('2.0.0','2.1.0'));

alter table dino_dev.ranking_contact_version
  drop constraint if exists ranking_contact_version_game_version_check;
alter table dino_dev.ranking_contact_version
  add constraint ranking_contact_version_game_version_check
  check (game_version in ('1.2.0','2.0.0','2.1.0'));

insert into dino_dev.schema_version(version) values('20260926093414') on conflict(version) do nothing;
commit;
