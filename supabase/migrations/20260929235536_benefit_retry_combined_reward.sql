begin;

alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_kind_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_kind_check
  check (kind in (
    'record_share','retry_invite','draw_retry','benefit_retry',
    'prize_share','general_share'
  ));

alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_reward_type_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_reward_type_check
  check (reward_type in ('GAME','DRAW','BOTH','NONE'));

alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_reward_contract_version_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_reward_contract_version_check
  check (reward_contract_version in (1,2,3));

alter table dino_dev.kakao_share_intent
  add column game_reward_status text not null default 'NOT_APPLICABLE',
  add column game_reward_quantity smallint not null default 0,
  add column draw_reward_status text not null default 'NOT_APPLICABLE',
  add column draw_reward_quantity smallint not null default 0;

alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_game_reward_status_check
  check (game_reward_status in (
    'NOT_APPLICABLE','PENDING','GRANTED','BLOCKED_CAP','BLOCKED_COOLDOWN',
    'BLOCKED_PRIZE_WON','NOT_ELIGIBLE'
  )),
  add constraint kakao_share_intent_draw_reward_status_check
  check (draw_reward_status in (
    'NOT_APPLICABLE','PENDING','GRANTED','BLOCKED_DRAW_LIMIT',
    'BLOCKED_PRIZE_WON','NOT_ELIGIBLE'
  )),
  add constraint kakao_share_intent_game_reward_quantity_check
  check (game_reward_quantity=case when game_reward_status='GRANTED' then 1 else 0 end),
  add constraint kakao_share_intent_draw_reward_quantity_check
  check (draw_reward_quantity=case when draw_reward_status='GRANTED' then 1 else 0 end);

alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_reward_contract_v2_check;
alter table dino_dev.kakao_share_intent
  drop constraint if exists kakao_share_intent_reward_contract_v2_check;
alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_reward_contract_check check (
    (reward_contract_version=1 and game_reward_status='NOT_APPLICABLE'
      and draw_reward_status='NOT_APPLICABLE')
    or
    (reward_contract_version=2 and game_reward_status='NOT_APPLICABLE'
      and draw_reward_status='NOT_APPLICABLE' and (
        (claim_id is null and (
          (kind in ('record_share','retry_invite') and reward_type='GAME')
          or (kind='draw_retry' and reward_type='DRAW')
          or (kind in ('prize_share','general_share') and reward_type='NONE')
        ))
        or (claim_id is not null and kind in ('prize_share','record_share')
          and reward_type='NONE')
      ))
    or
    (reward_contract_version=3 and claim_id is null
      and kind='benefit_retry' and reward_type='BOTH'
      and game_reward_status<>'NOT_APPLICABLE'
      and draw_reward_status<>'NOT_APPLICABLE')
  );

alter table dino_dev.kakao_share_intent
  add constraint kakao_share_intent_combined_outcome_check check (
    reward_contract_version<>3
    or (
      status='PENDING'
      and reward_status='PENDING'
      and game_reward_status='PENDING'
      and draw_reward_status='PENDING'
    )
    or (
      status='CONFIRMED'
      and game_reward_status<>'PENDING'
      and draw_reward_status<>'PENDING'
      and ((reward_status='GRANTED')=(
        game_reward_status='GRANTED' or draw_reward_status='GRANTED'
      ))
    )
    or (
      status in ('REJECTED','EXPIRED')
      and reward_status='NOT_ELIGIBLE'
      and game_reward_status='NOT_ELIGIBLE'
      and draw_reward_status='NOT_ELIGIBLE'
    )
  );

insert into dino_dev.schema_version(version)
values ('20260929235536')
on conflict(version) do nothing;

commit;
