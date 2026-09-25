# Phase 2 실제 화면 계측 범위

작성 기준: 2026-09-25 로컬 코드. 화면 이벤트는 `screen_view_id`, `visit_session_id`, `observation_id`, 활성 시간과 함께 배치 전송한다. 클라이언트 이벤트는 관찰값이며 게임 점수·코인·하트·부활의 권위값은 서버 재현 결과다.

## 공통 화면 수명주기

- `analytics.enterScreen()`이 실제 라우터 렌더 직전에 `screen_entered`를 기록한다.
- 이동·페이지 종료 시 `screen_left`와 관찰된 활성 시간을 기록한다.
- 숨김 시간은 활성 체류에 더하지 않는다. 브라우저 강제 종료의 정확한 이탈 시각은 보장하지 않는다.
- 로딩의 데이터 준비와 2.5초 브랜드 연출은 `loading_data_ready`, `loading_intro_completed`로 따로 기록한다. `loading_ready`는 다음 화면 렌더 시점에 연결한다.

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
| 복주머니 | `draw_entered`, `pouch_selected` | 추첨 상태 조회·서버 추첨 | 선택과 서버 확정을 구분. 선택 이벤트가 당첨 결과를 결정하지 않음 |
| 긁기 | `scratch_started`, `scratch_reveal_requested`, `scratch_completed`, `draw_result_viewed` | scratch 완료 저장 | 보조 버튼/키보드 요청, 저장 완료, 실제 화면 결과 노출을 분리. 모든 방식은 같은 서버 결과를 공개 |
| 수령 | `claim_form_started`, `claim_form_submitted` | 수령 정보 접수 | 접수 성공까지만 의미. 연락 완료·지급 완료는 관리자 상태 전이 |
| Gemini | `benefit_viewed`, `gemini_cta_viewed`, `gemini_cta_clicked` | 설정의 공식 URL | CTA 가시 노출과 클릭을 구분. 도착·학생 인증·혜택 등록은 측정하지 않음 |
| 가이드 | `content_viewed`, `content_clicked` | 설정의 공개 가이드 URL | 전자는 가이드 카드가 전경에서 50% 이상 보인 사건, 후자는 외부 링크 클릭. 둘 다 Notion 본문 도착·열람·체류 완료를 뜻하지 않음 |

## 새 이벤트 계약

### `scratch_reveal_requested`

- 화면: `draw`
- 차원: `action=accessibility_button|keyboard`
- 시점: 긁기 대신 같은 결과를 공개하는 보조 입력을 사용했을 때
- 구분: `scratch_completed`는 서버에 결과 확인 상태가 저장된 뒤, `draw_result_viewed`는 결과 UI가 실제 공개될 때 기록

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

## 현재 통합 확인이 필요한 부분

2026-09-26 `40b21e4` Preview에서 실제 혜택 화면을 열고 두 가이드를 노출한 뒤, 해당 배포의 `benefit_viewed`, `gemini_cta_viewed`, `content_viewed(study_note/job_photo)`가 각각 1회·1명으로 원격 테스트 DB에 저장됨을 확인했다. 아래 관리자 집계·전체 흐름 검증과는 구분한다.

- 화면 코드와 현재 클라이언트·서버 허용 목록에는 `content_viewed`, `content_clicked`, `scratch_reveal_requested`가 등록돼 있다. 최종 Preview 전에 실제 저장과 관리자 집계·라벨까지 세 이름과 차원이 이어지는지 E2E로 확인해야 한다.
- `record_share`는 앱 parser와 서버 query allowlist까지 확인됐지만, 관찰·이벤트 서버 허용값과 관리자 목적별 집계를 전체 회귀로 확인해야 한다.
- `content_guides`는 화면 소비 계약이 구현됐다. 서버 `/api/config` 제공값, HTTPS URL, 실제 공개 접근, 카드 클릭을 한 흐름으로 확인해야 한다.
- 실제 기기·인앱 브라우저의 네이티브 공유, 클립보드 권한, 외부 브라우저 전환은 이 문서 작성 중 실기기 검증하지 않았다.
- 외부 Notion 페이지의 본문 열람과 공식 혜택 가입 완료는 현재 앱에서 관측할 수 없다.
