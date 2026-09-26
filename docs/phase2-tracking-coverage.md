# Phase 2 실제 화면 계측 범위

작성 기준: 2026-09-25 로컬 코드. 화면 이벤트는 `screen_view_id`, `visit_session_id`, `observation_id`, 활성 시간과 함께 배치 전송한다. 클라이언트 이벤트는 관찰값이며 게임 점수·코인·하트·부활의 권위값은 서버 재현 결과다.

## 공통 화면 수명주기

- `analytics.enterScreen()`이 실제 라우터 렌더 직전에 `screen_entered`를 기록한다.
- 이동·페이지 종료 시 `screen_left`와 관찰된 활성 시간을 기록한다.
- 숨김 시간은 활성 체류에 더하지 않는다. 브라우저 강제 종료의 정확한 이탈 시각은 보장하지 않는다.
- 로딩의 데이터 준비와 2.5초 브랜드 연출은 `loading_data_ready`, `loading_intro_completed`로 따로 기록한다. `loading_ready`는 다음 화면 렌더 시점에 연결한다.
- 익명 이벤트 전송과 참가자 연결의 처리 순서가 뒤바뀌어 `PARTICIPANT_NOT_READY`로 거절되면, 참가자 초기화 완료 후 해당 이벤트만 한 번 재전송한다. 기존 ID·발생 시각·활성 시간은 유지하며 서버의 소유권 검사와 중복 방지는 그대로 적용한다. 영구 거절은 이벤트 이름·정해진 오류 코드로 진단하고 원본 값이나 인증 정보는 출력하지 않는다.

## 화면·행동 커버리지

| 단계 | 클라이언트 이벤트 | 서버/API 연결 | 의미와 제한 |
| --- | --- | --- | --- |
| 유입 | `entry_viewed` | `POST /api/observations` | `link_kind`, 채널, 캠페인, 불투명 `share_id`를 기록한다. 참가자 생성이나 초대 보상 아님 |
| 참가 준비 | `participant_ready`, `loading_*` | 참가자 초기화와 `/api/me` | 연출 완료와 데이터 준비를 분리. 초기화 실패는 성공 이벤트로 처리하지 않음 |
| 게임 시작 | `game_cta_clicked`, `game_start_approved` | 세션 생성·시작 | CTA 클릭과 서버 승인된 실제 시작을 분리 |
| 게임 진행 | `game_checkpoint`, `game_coin_collected`, `game_heart_collected`, `game_revived` | 체크포인트, 최종 서버 검증 | 화면 관찰 이벤트. 최종 집계 권위값은 서버가 seed와 입력으로 재현한 결과 |
| 게임 종료 | `game_completed`, `game_fault_reported`, `game_recovered` | 완료·장애·세션 조회 | 검증 완료, 장애 보고, 복구를 분리. 정상 이탈을 장애 환급으로 계산하지 않음 |
| 랭킹 | `ranking_viewed`, `top3_profile_started`, `top3_profile_submitted` | 랭킹 조회·프로필 접수 | TOP3 노출과 정보 접수. 최종 수상·지급을 의미하지 않음 |
| 공유 | `invite_cta_viewed`, `share_attempted` | 추천 현황 조회 | `link_kind`, `share_id`, 실제 사용한 수단, attempted/copied/cancelled/failed/share_sheet_closed 기록. 실제 메시지 전달은 알 수 없음 |
| 유효 방문 | `invite_visit_interacted`, `invite_visit_qualified`, `invite_visit_rejected` | `POST /api/referrals/qualify` | 3초 활성+상호작용 후 서버 판정. 링크 조회나 크롤러 요청만으로 보상하지 않음 |
| 복주머니 | `draw_cta_clicked`, `draw_entered`, `pouch_selected` | 추첨 상태 조회·서버 추첨 | 홈·초대·결과·수령함의 버튼 클릭, 화면 진입, 주머니 선택, 서버 확정을 구분. 클릭만으로 추첨하거나 보상하지 않음 |
| 긁기 | `scratch_started`, `scratch_reveal_requested`, `scratch_completed`, `draw_result_viewed` | scratch 완료 저장 | 보조 버튼/키보드 요청, 저장 완료, 실제 화면 결과 노출을 분리. 모든 방식은 같은 서버 결과를 공개 |
| 수령 | `claim_form_started`, `claim_form_submitted` | 수령 정보 접수 | 접수 성공까지만 의미. 연락 완료·지급 완료는 관리자 상태 전이 |
| Gemini | `benefit_viewed`, `gemini_cta_viewed`, `gemini_cta_clicked` | 설정의 공식 URL | CTA 가시 노출과 클릭을 구분. 도착·학생 인증·혜택 등록은 측정하지 않음 |
| 가이드 | `content_viewed`, `content_clicked` | 설정의 공개 가이드 URL | 전자는 가이드 카드가 전경에서 50% 이상 보인 사건, 후자는 외부 링크 클릭. 둘 다 Notion 본문 도착·열람·체류 완료를 뜻하지 않음 |

## 새 이벤트 계약

### `draw_cta_clicked`

- 화면/차원: `source=home|invite|result|claims`, `draw_status=LOCKED|AVAILABLE|DRAWN`.
- 시점: 복주머니 화면으로 이동하는 버튼을 누를 때. 홈·초대에서는 서버가 `AVAILABLE` 또는 `DRAWN`으로 알려준 경우에만 버튼을 노출한다.
- 관리자: 기존 이벤트 집계에 `복주머니 버튼 클릭 (client)`로 표시하며 클릭 건수와 고유 참가자 수를 분리한다.
- 제한: 추첨 횟수나 결과 노출 수가 아니다. 친구 초대나 게임권 잔액을 복주머니 접근의 추가 조건으로 사용하지 않는다.

### `scratch_reveal_requested`

- 화면: `draw`
- 차원: `action=accessibility_button|keyboard`
- 시점: 긁기 대신 같은 결과를 공개하는 보조 입력을 사용했을 때
- 구분: `scratch_completed`는 서버에 결과 확인 상태가 저장된 뒤, `draw_result_viewed`는 결과 UI가 실제 공개될 때 기록
- 직접 긁기·키보드·보조 버튼 모두 새 공개를 시작할 때 `scratch_started`를 한 번 기록한다. 이미 공개한 결과 복원은 새 긁기 시작이나 완료 저장 이벤트를 만들지 않는다.
- 관리자 단계는 시작→실제 노출과 시작→완료 저장을 각각 집계한다. 결과가 저장 응답보다 먼저 보이는 실제 순서를 유지하며, 저장 실패를 결과 미노출로 계산하지 않는다.

### `content_viewed`

- 화면: `benefit`
- 차원: `content=study_note|job_photo` 등 설정 ID, `position=benefit_guides`
- 시점: 해당 가이드 카드가 문서 전경에서 50% 이상 노출됐을 때. 카드별 화면 렌더당 한 번만 기록하고 화면 이탈 때 observer를 해제한다.
- 숨김 탭에서 전경으로 돌아오면 아직 기록하지 않은 카드와 Gemini CTA의 교차 상태를 새로 측정한다. 화면 이탈 후 도착하는 observer 콜백은 버린다.
- IntersectionObserver 미지원 브라우저에서는 카드·CTA 노출을 추정해서 기록하지 않는다. 화면 진입과 실제 링크 클릭은 계속 기록하므로 해당 환경의 노출 기반 클릭률은 미측정 범위로 해석한다.
- 제한: 외부 Notion 본문을 실제로 읽었다는 증거로 사용하지 않는다. 관리자 보고에서는 `가이드 카드 노출`로 표시해야 한다.

### `content_clicked`

- 화면: `benefit`
- 차원: `content=study_note|job_photo` 등 설정 ID, `position=benefit_guides`
- 시점: 사용자가 활성화된 공개 가이드 링크를 눌렀을 때
- 제한: Notion 도착, 본문 열람, 체류 완료를 의미하지 않는다. 관리자 보고에서는 `가이드 링크 클릭`으로 표시해야 한다.

## 공유 목적별 계약

| `link_kind` | 생성 위치 | 보상 판정 | 집계 의미 |
| --- | --- | --- | --- |
| `retry_invite` | 초대 화면 기본 진입 | 동일한 유효 방문·중복·자기초대·상한·쿨다운 규칙 | 재도전 초대 링크 시도 |
| `record_share` | 결과 화면의 기록 공유 | 위와 동일 | 기록 공유 링크 시도 |
| `prize_share` | 수령함의 경품 결과 공유 | 위와 동일 | 경품 결과 공유 링크 시도 |

세 문맥은 표시와 유입 분류만 다르고, 같은 초대자–방문자 관계는 문맥을 바꿔도 한 번만 보상한다. `share_attempted`의 `share_sheet_closed`는 전송 완료가 아니다.

## 통합 확인 결과와 남은 범위

2026-09-26 `40b21e4` Preview에서 실제 혜택 화면을 열고 두 가이드를 노출한 뒤, 해당 배포의 `benefit_viewed`, `gemini_cta_viewed`, `content_viewed(study_note/job_photo)`가 각각 1회·1명으로 원격 테스트 DB에 저장됨을 확인했다. 아래 관리자 집계·전체 흐름 검증과는 구분한다.

- 원격 관리자 API에서도 두 가이드 노출이 각각 1회·1명, 클릭 0명으로 일치했다. Gemini 관찰 중 참가자는 확정 CTR 분모에서 제외됐다. 관리자 전체 업무 화면 검증은 남아 있다.
- 세 공유 유형의 유효 방문·보상 관계를 원격 DB와 대조했다. 같은 브라우저의 유형 변경 재방문은 중복 거절되고, 서로 다른 방문자 세 명의 지급으로 잔액 3장·10시간 쿨다운이 시작됐다. 관리자 목적별 전체 집계와 당첨 후 경품 공유 UI는 별도 검증 범위다.
- `20926c5` Preview의 초대·홈 복주머니 버튼 클릭은 관리자 API에서 `복주머니 버튼 클릭 (client)`, 이벤트 2회·고유 참가자 1명으로 확인됐다.
- `f1557b1` 실제 앱의 로컬 10판 순차 플레이에서 게임별 서버 `game_start_approved`·`game_finish_verified`, 클라이언트 `client_game_start_approved`·`client_game_completed`는 각각 1건이었다. 같은 기간·`phase2_repeat`·직접 유입 참가자 필터의 실제 관리자 집계 함수도 승인 10·완료 10·고유 참가자 1·코인 32·하트/부활 각각 5로 일치했다. 원격 관리자 UI 또는 동시 부하 확인은 아니다.
- `e4cf367` Preview의 단일 참가자 `phase2_metrics` 흐름에서 TOP3 합성 정보 접수, 기록 공유 링크 복사, 복주머니 선택·보조 공개·저장, 공식 혜택 복사·이동을 확인했다. 원격 관리자 API는 TOP3 제출 진행 1명, 기록 공유와 Gemini 복사 각각 시도 1·성공 1, 공식 링크 클릭 1명으로 일치했다. 확정 CTR은 아직 관찰 중이어서 분모 0·값 null이다.
- 이때 긁기 보조 버튼의 시작 이벤트 누락과, 노출→저장 순서를 반대로 가정한 관리자 단계 오류를 재현했다. 실제 결과가 보였는데 `scratch.start`와 `scratch.visible`이 진행 0·관찰 중 1로 집계됐다. 수정 후 자동 회귀로 버튼/키보드/직접 긁기·복원과 실제 DB의 정상/저장 실패/복원 집계를 검증했다. 이전 이벤트는 소급 생성하거나 수정하지 않는다.
- 수정 `5b45834` Preview의 단일 참가자 흐름에서 관리자 `scratch.start`·`scratch.visible`·`scratch.complete` 모두 진입 1·진행 1·관찰 중 0·이탈 0으로 확인했다. 실제 노출 308ms → 저장 485ms 순서를 유지했다. 새로고침 복원 뒤 DB의 시작·완료는 각 1건이고 노출만 두 화면에 맞춰 2건이었다.
- 이전 Preview의 분석 전송 거절 경고 한 번은 이벤트별 사유가 없어 정확한 대상을 특정하지 못했다. 해당 흐름의 주요 게임·접수·공유·복권·혜택 사건은 저장됐고 수정 Preview 단일 흐름은 경고가 없었으나, 전체 분석 무누락 확인과는 구분한다.

- 화면 코드와 현재 클라이언트·서버 허용 목록에는 `content_viewed`, `content_clicked`, `scratch_reveal_requested`가 등록돼 있다. 최종 Preview 전에 실제 저장과 관리자 집계·라벨까지 세 이름과 차원이 이어지는지 E2E로 확인해야 한다.
- `record_share`의 parser·query allowlist·관찰 연결·유효 방문 보상은 확인했다. 관리자 목적별 집계까지 이어지는 전체 흐름은 추가 확인해야 한다.
- `content_guides`는 화면 소비 계약이 구현됐다. 서버 `/api/config` 제공값, HTTPS URL, 실제 공개 접근, 카드 클릭을 한 흐름으로 확인해야 한다.
- 실제 기기·인앱 브라우저의 네이티브 공유, 클립보드 권한, 외부 브라우저 전환은 이 문서 작성 중 실기기 검증하지 않았다.
- 외부 Notion 페이지의 본문 열람과 공식 혜택 가입 완료는 현재 앱에서 관측할 수 없다.
