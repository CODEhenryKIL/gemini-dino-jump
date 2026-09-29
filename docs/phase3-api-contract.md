# 3차 변경 API 계약

작성: 2026-09-29. 쿠키 인증·Origin·멱등 키·연락처 비공개 등 공통 규칙은 기존 API 계약을 유지한다. 아래 내용이 기존 단일 추첨·방문 보상 계약을 대체한다.

## 행사 화면 시간

`GET /api/config`는 `server_time`에 DB 현재 시각을 제공하고 기존 no-store 응답 정책을 유지한다. 클라이언트는 이를 받은 시점의 단조 증가 시간을 기준으로 시작·종료 경계를 계산한다. 기기 날짜 변경으로 행동 버튼을 조기에 닫지 않으며, 실제 게임·추첨 허용과 마감 판정은 서버가 수행한다. 앱 복귀와 상태 새로고침 때 행사 설정과 시각을 다시 받는다.

## 추첨 상태

`GET /api/me`의 `draw`와 `GET /api/draws/me`의 `draw_state`에 다음 상태를 제공한다.

| 필드 | 의미 |
| --- | --- |
| `status` | `LOCKED` 게임 미완료 / `AVAILABLE` 사용 가능한 권리 / `DRAWN` 혜택 결과 확인·공유 가능 / `WON` 실제 상품 당첨으로 종료 / `EXHAUSTED` 10회 사용 |
| `used_count`, `max_count` | 이미 확정한 추첨 수, 상한 10 |
| `available_credits` | 이미 받은 미사용 권리. 실제 상품 당첨 뒤에는 잔액이 있어도 사용 불가 |
| `remaining_possible` | 앞으로 추가 적립 가능한 최대 횟수. 보유권이 아님 |
| `actual_prize_won` | 실제 상품 배정 여부 |
| `draw_id` | 가장 최근 회차 ID |

`GET /api/draws/me`는 최신 `draw`와 시간순 `draws` 전체를 함께 반환한다. 회차 결과에는 `round_number`, `outcome_kind: PRIZE|BENEFIT`, `is_actual_prize`, 기존 경품·공개·긁기·수령 요청 필드가 포함된다. Gemini 혜택은 `BENEFIT`이며 상품 수령 요청을 만들지 않는다.

## 새 회차 생성과 응답 유실

`POST /api/draws`:

```json
{"pouch_index": 0, "event_id": "opaque-stable-event-id", "expected_round_number": 2}
```

- `pouch_index`는 0–2, `expected_round_number`는 1–10이다.
- 화면은 요청 전에 회차·주머니·요청 ID를 저장하고, 재시도에서 그대로 사용한다. 성공 확인 전에 새 요청 ID로 다음 회차를 만들지 않는다.
- 동일 회차·주머니가 이미 확정되었다면 같은 결과를 `200`으로 반환한다. 같은 회차의 다른 주머니는 `409 DRAW_ROUND_CONFLICT`다.
- 이전 클라이언트가 회차를 생략하는 첫 추첨은 허용하지만, 기존 추첨이 있으면 `409 DRAW_ROUND_REQUIRED`로 새 상태 조회를 요구한다.
- 다음 회차 불일치, 권리 없음, 실제 상품 당첨, 10회 사용, 전체 풀 소진은 별도 `409`로 거부한다.
- 재고·추첨 자리·회차·권리 소비·실상품 수령 요청 생성은 한 트랜잭션이다. 설정이 잘못된 3차 풀은 `503 DRAW_CONFIG_INVALID`이며 과거 확률 방식으로 대체하지 않는다.
- 기존 결과 조회는 새 추첨을 하지 않는다. `PATCH /api/draws/{id}/scratch-complete`도 결과를 바꾸지 않는다.

## 카카오 공유 목적

`POST /api/referrals/share-intents`는 `kind`와 선택적 `claim_id`를 받는다. 서버가 보상 종류를 결정한다.

| kind | 보상 |
| --- | --- |
| `retry_invite`, `record_share` | `GAME` |
| `draw_retry` | `DRAW` |
| `prize_share`, `general_share` | `NONE` |

- 소유한 `claim_id`가 있는 수령 접수용 공유는 항상 `NONE`이다. 이 요청만 본인 `MemoChat` 전송 확인으로 접수를 완료할 수 있고, 추가 권리는 지급하지 않는다. DRAW 수령 요청은 `prize_share`, RANKING은 `prize_share` 또는 `record_share`만 허용한다.
- 신규 공유는 보상 계약 v2로 저장한다. 기존 v1 전송·접수 기록은 보존한다.
- 응답은 `share_id`, `status`, `reward_type`, `reward_status`, 만료·확인 시각을 제공한다. 생성 응답의 `callback_args`는 카카오 전달용이며 사용자 화면이나 분석 이벤트에 노출하지 않는다.
- `GET /api/referrals/share-intents/{id}`는 본인 요청만 조회하며 게임권 상태를 함께 제공한다. `DRAW` 목적에는 `draw_state`도 포함된다.
- 인증된 카카오 웹훅만 권리를 적립한다. `GAME`·`DRAW`의 나에게 보내기와 위조·만료·다른 환경·중복 요청은 적립하지 않는다. 소유한 `claim_id`의 `NONE` 수령 접수 공유는 본인 `MemoChat`에서도 확인할 수 있지만 적립하지 않는다.
- 한 공유 요청은 여러 방·중복 웹훅에도 최대 1회만 적립한다. 게임권과 뽑기권은 같은 요청에서 함께 지급하지 않는다.
- 게임권은 3장 보유·10시간 규칙을 유지한다. 뽑기권은 사용 수+미사용 권리가 10을 넘지 않고, 실제 상품 당첨 후에는 새로 적립하지 않는다.
- 공유 확인과 보상 지급은 별개다. `confirmed`여도 `NO_REWARD`, 한도·쿨다운 차단 등일 수 있으므로 `reward_status`까지 확인한다.

## 관리자 수동 지급 확인

`PATCH /api/admin/claims/{id}`는 `claims:write` 권한과 최신 `expected_version`을 확인한다. 연락 완료 상태의 실제 상품 수령 건을 `PAID`로 바꿀 때는 다음을 함께 확인한다.

- `verification_status: VERIFIED`와 유효한 `verification_reference`: 관리자의 자격 확인 기록.
- `external_delivery: true`: 운영자가 실제 외부 전달을 확인했다는 명시적 값. 문자열 `"true"`는 허용하지 않는다.
- 3자 이상의 `reason`: 전달 확인 사유. 개인정보·증빙 원본을 기록하는 용도가 아니다.
- 현재 베타 참조 형식은 기존 `TEST_REF_...`를 유지한다. 본행사의 자격 판정 기준과 증빙 처리 정책을 이 필드로 임의 확정하지 않는다.

자격·전달·증거 누락은 각각 `CLAIM_VERIFICATION_REQUIRED`, `DELIVERY_CONFIRMATION_REQUIRED`, `DELIVERY_EVIDENCE_REQUIRED`의 `409`로 거부한다. 실패하면 수령 상태·버전·재고·감사 기록을 변경하지 않는다. 성공 시 수령 상태, 재고의 RESERVED→PAID, 재고 이력, 전후 확인 상태와 담당자 감사 기록을 한 트랜잭션에 저장한다. 오래된 버전 재요청은 `VERSION_CONFLICT`로 거부하며 재고를 다시 처리하지 않는다.

이미 지급 완료된 건에서도 필수 확인 상태를 해제할 수 없다. 랭킹 지급은 해당 참가자·수령 요청·재고가 FINAL 스냅샷의 ranking_award에 연결된 경우에만 허용하며, 미확정은 `FINAL_RANKING_UNDECIDED`로 차단한다. 이 API는 실제 쿠폰·경품을 발송하지 않는다.

수령 정보 미접수 건은 기본적으로 관리자 수정이 차단된다. 예외는 접수 기한 경과 후 `AWAITING_INFORMATION → NO_RESPONSE` 마감뿐이다. 최신 버전·claims:write 권한·3자 이상 사유를 요구하며, 개인정보·외부 전달·자격 확인 상태를 임의로 채우거나 재고를 재배정하지 않는다. 목록의 `can_close_no_response`는 서버 시각과 해당 행사의 접수 기한으로 계산되며, PATCH에서 조건을 재검증한다.

전체 지급 종료 감사 기록이 있으면 `NO_RESPONSE → PENDING_REVIEW` 재개를 `FULFILLMENT_ALREADY_COMPLETE`로 거부한다. 개인정보 정리 기산일 확정 후 지급 절차를 임의로 다시 열지 않는다.

## 최종 TOP3 플레이 검토

`POST /api/admin/ranking-snapshots/{id}/reviews`는 `ranking:write` 권한·멱등 키와 다음 본문을 사용한다.

```json
{"participant_id":"참가자 ID","outcome":"APPROVED","evidence_reference":"REF_REVIEW_01","reason":"플레이 기록 검토 사유","event_id":"고유 이벤트 ID"}
```

- `outcome`은 APPROVED / HOLD. 참조는 production에서 REF_, 베타에서는 TEST_REF_ 접두사를 쓴다.
- 현재 행사의 DRAFT 스냅샷 TOP3만 검토하며, 승인하려면 참가자가 ACTIVE이고 검토 대상 세션·최고점·달성 시각이 현재 기록과 일치해야 한다.
- RANKING_GAMEPLAY_REVIEW 감사 기록을 남기고 목록의 candidates에 검토 결과와 세션 정보를 제공한다. 대학생 자격 확인과 플레이 검토는 별도다.
- 최종 확정은 참가자 행을 잠근 뒤 검토와 상태를 다시 검사한다. 미검토는 RANKING_GAMEPLAY_REVIEW_REQUIRED, 보류는 RANKING_GAMEPLAY_REVIEW_ON_HOLD, 변경된 기록은 RANKING_CANDIDATE_STALE로 거부한다.
- 의심 후보는 보류·재검토한다. 자동 차순위 선정이나 자동 플레이 완전 차단을 의미하지 않는다.

## 배포·호환성

- 새 migration은 기존 추첨을 1회차로 보존하고 최초 지급·소비 원장을 연결한다. 기존 claim·연락처·지급 상태를 초기화하지 않는다.
- 새 클라이언트·새 API·새 스키마를 함께 검증한다. 다회차 데이터 생성 후 예전 단일 추첨 코드로 되돌리는 것은 일반 롤백으로 취급하지 않는다.
- 현재 베타의 합성 재고·무제한 설정과 본행사 재고·환경 승인은 별개다.
