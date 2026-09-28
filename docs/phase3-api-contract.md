# 3차 변경 API 계약

작성: 2026-09-29. 쿠키 인증·Origin·멱등 키·연락처 비공개 등 공통 규칙은 기존 API 계약을 유지한다. 아래 내용이 기존 단일 추첨·방문 보상 계약을 대체한다.

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

- 소유한 `claim_id`가 있는 수령 접수용 공유는 항상 `NONE`이다. DRAW 수령 요청은 `prize_share`, RANKING은 `prize_share` 또는 `record_share`만 허용한다.
- 신규 공유는 보상 계약 v2로 저장한다. 기존 v1 전송·접수 기록은 보존한다.
- 응답은 `share_id`, `status`, `reward_type`, `reward_status`, 만료·확인 시각을 제공한다. 생성 응답의 `callback_args`는 카카오 전달용이며 사용자 화면이나 분석 이벤트에 노출하지 않는다.
- `GET /api/referrals/share-intents/{id}`는 본인 요청만 조회하며 게임권 상태를 함께 제공한다. `DRAW` 목적에는 `draw_state`도 포함된다.
- 인증된 카카오 웹훅만 권리를 적립한다. 나에게 보내기·위조·만료·다른 환경·중복 요청은 적립하지 않는다.
- 한 공유 요청은 여러 방·중복 웹훅에도 최대 1회만 적립한다. 게임권과 뽑기권은 같은 요청에서 함께 지급하지 않는다.
- 게임권은 3장 보유·10시간 규칙을 유지한다. 뽑기권은 사용 수+미사용 권리가 10을 넘지 않고, 실제 상품 당첨 후에는 새로 적립하지 않는다.
- 공유 확인과 보상 지급은 별개다. `confirmed`여도 `NO_REWARD`, 한도·쿨다운 차단 등일 수 있으므로 `reward_status`까지 확인한다.

## 배포·호환성

- 새 migration은 기존 추첨을 1회차로 보존하고 최초 지급·소비 원장을 연결한다. 기존 claim·연락처·지급 상태를 초기화하지 않는다.
- 새 클라이언트·새 API·새 스키마를 함께 검증한다. 다회차 데이터 생성 후 예전 단일 추첨 코드로 되돌리는 것은 일반 롤백으로 취급하지 않는다.
- 현재 베타의 합성 재고·무제한 설정과 본행사 재고·환경 승인은 별개다.
