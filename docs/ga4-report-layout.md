# GA4 보고서 구성

## 속성

- 운영: `556455967`
- 테스트: `556468075`
- 기본 분석 기간: 최근 28일
- 퍼널 방식: 폐쇄형 퍼널. 각 보고서의 첫 단계가 분모다.

## 맞춤 정의

운영과 테스트 속성에 아래 이벤트 범위 측정기준을 동일하게 등록했다.

| 표시 이름 | 이벤트 매개변수 |
| --- | --- |
| 화면 | `screen_name` |
| 플레이 유형 | `play_type` |
| 뽑기 회차 | `round_number` |
| 결과 유형 | `result_type` |
| 수령 유형 | `claim_type` |
| 진입 출처 | `source` |
| 노출 위치 | `position` |
| 링크 목적 | `link_kind` |
| 콘텐츠 유형 | `content` |
| 공유 방식 | `share_method` |
| 공유 상태 | `share_status` |

맞춤 측정항목 `게임 시간`은 이벤트 매개변수 `duration_seconds`, 단위 `초`로 등록했다.

캠페인 소스·매체·이름·콘텐츠는 GA4 기본 캠페인 측정기준을 사용한다. 별도 맞춤 정의를 만들지 않는다.

## 생성한 운영 탐색

### 01 게임 참여 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/irKUIRzoRcqJ8YMeUixV7A>
- 분모: `entry_viewed`
- 단계: `entry_viewed` → `game_cta_click` → `game_start` → `game_complete`
- 분해 기준: `play_type` (`first`, `retry`)
- 로딩과 튜토리얼 이탈은 07 탐색에서 별도로 본다.
- 기간: 최근 28일

### 02 Gemini 전환 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/dOjHmEG9SzOhrdxuFI_UFg>
- 분모: `benefit_view`
- 단계: `benefit_view` → `gemini_cta_view` → `gemini_cta_click`
- 기간: 최근 28일

### 03 TOP3 수령 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/LdvtPHJWTzOGIj_WTDyXfA>
- 분모: `top3_profile_start`
- 단계: `top3_profile_start` → `top3_profile_submit`
- 해석: 순위 경품 입력 폼을 시작한 대상자 중 제출 완료율을 본다. 전체 게임 완료자를 수령 대상자로 간주하지 않는다.
- 기간: 최근 28일

### 04 뽑기 완료 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/mDTr7hkpSDWTBVl9uqWm_g>
- 분모: `draw_entered`
- 단계: `draw_entered` → `pouch_selected` → `scratch_started` → `scratch_complete` → `draw_result_view`
- 분해 기준: `round_number`, `result_type`
- 기간: 최근 28일

### 05 경품 수령 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/9YNDB4wXQYCHpzgryG2xjg>
- 분모: `claim_form_start`
- 단계: `claim_form_start` → `claim_draft_saved` → `claim_form_submit`
- 분해 기준: `claim_type` (`DRAW`, `RANKING`)
- 기간: 최근 28일

### 06A 추천 공유 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/OXg103YQTTOfq_yVyQcINA>
- 분모: `invite_cta_view`
- 단계: `invite_cta_view` → `share_interaction`
- 분해 기준: `link_kind`, `share_method`, `share_status`, `position`
- 해석: 같은 발신 사용자의 공유 버튼 노출 대비 공유 상호작용을 본다.
- 기간: 최근 28일

### 06B 추천 유입·재도전 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/p0fhZTTYSTGogXttAQkEBA>
- 분모: `entry_viewed`
- 단계: `entry_viewed` → `loading_ready` → `game_cta_click` → `game_start`
- 분해 기준: `play_type`, 캠페인 소스·콘텐츠
- 해석: 추천 링크 수신자의 진입 후 게임 시작을 본다. 06A의 발신자와 사용자를 연결하지 않고 두 탐색의 집계 추세를 비교한다.
- 기간: 최근 28일

### 07 로딩·튜토리얼 퍼널

- URL: <https://analytics.google.com/analytics/web/#/analysis/a409928949p556455967/edit/fjV0VMaORoO2buwGI93Qdw>
- 분모: `entry_viewed`
- 단계: `entry_viewed` → `loading_ready` → `tutorial_view` → `tutorial_progress`
- 보조 지표: `tutorial_skip`은 성공 단계가 아니라 별도 이벤트 수로 본다.
- 기간: 최근 28일

## 운영 메모

- 맞춤 정의는 등록 전 이벤트에 소급 적용되지 않는다.
- 운영 속성은 현재 수집 데이터가 없어 퍼널 값이 비어 있다. 테스트 속성에서는 DebugView 이벤트 8건을 확인했다.
- GA4 동의 전 이벤트는 의도적으로 전송하지 않는다. 따라서 `entry_viewed` 분모는 전체 방문자가 아니라 분석 수집에 동의한 관측 진입자다.
- 각 탐색은 기본으로 `기기 카테고리` 세분화를 저장했다. 채널 분석 시 `세션 기본 채널 그룹`, 행동 분석 시 위 맞춤 측정기준으로 세분화를 바꾼다.
- 테스트 속성은 DebugView 검증용이며, 저장 탐색은 운영 속성에 만들었다.
