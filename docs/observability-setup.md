# 공룡 점프 관측 도구 설정 실행서

- 작성일: 2026-09-29
- 범위: GA4 보조 분석과 Datadog 장애 감시
- 현재 상태: Preview GA4·Datadog 연결 유지. Production 후보의 환경 변수·별도 로그 드레인·오류 모니터·대시보드 준비 및 실제 운영 상태 로그 수신 확인. 공개 주소는 아직 베타이며 최종 상태는 [오픈 실행 기록](final-launch-execution-report.md) 참조.
- 현재 공개 베타 환경: `APP_ENV=preview`
- 운영 원칙: GA4와 Datadog은 관측 도구이며 게임권, 추첨, 순위, 당첨 및 수령 권리의 판정 근거가 아니다.

## 1. 완료 상태와 남은 게이트

| 항목 | 현재 상태 | 외부 활성화 전 게이트 |
| --- | --- | --- |
| GA4 클라이언트 코드 | Preview 테스트 ID 적용·수신 확인 | Production 운영 ID·정확한 origin 별도 검증 |
| GA4 자동 수집 정책 | 팝업·상단 분석 설정 제거, 기존 거부·브라우저 거부 신호 우선, 개인정보 안내의 중지·재사용 경로 검증 | Production 공개 주소에서 자동 전송·기존 거부 유지 재검증 |
| GA4 운영 속성 | 생성·보존·신호 설정 확인, 사이트 미연결 | Production 환경 변수 적용 후 자동 전송 검증 |
| GA4 테스트 속성 | Preview 자동 수집·DebugView 수신, 중지 후 SDK 부재·재사용 확인 | 실제 트래픽의 중복·개인정보 지속 점검 |
| GA4 보고서 | 운영 속성에 게임·Gemini·TOP3·뽑기·수령·추천 발신·추천 유입·로딩 탐색 저장 | 본행사 수집 시작 후 실제 분모·전환 수 점검 |
| Datadog 구조화 서버 로그 | Vercel→수신기→Datadog 파싱·필드·개인정보 부재 검증 | 신규 경로·오류 유형 추가 시 허용 목록 재검증 |
| `/api/health` | Preview 외부 200·DB ready 확인 | DB 장애·복구 통제 테스트 확인 |
| Datadog 계정 | 로그인·학생 인증 확인 | 조직·사이트·혜택 기간과 실제 사용량을 조직 화면에서 계속 확인 |
| Datadog 로그 드레인 | Log Management·Preview·Lambda 전용 Vercel 드레인 활성화, 실제 수신 검증 | 24시간 사용량·수집 공백·비용 감시 |
| Datadog 대시보드·모니터 | 체크 2개·로그 실패 및 수집 공백 모니터·수신자·대시보드 5위젯 저장 | 테스트 알림 실제 메일함 수신 확인, 실제 트래픽 기반 임계치 보정 |
| 알림 수신자 | 사용자 확인 완료 | `sea42471@naver.com`; 실제 테스트 알림 수신 확인 필요 |

외부 화면에서 확인하지 않은 항목은 완료로 기록하지 않는다. API 키나 비밀값은 이 문서나 소스 코드에 저장하지 않는다.

### 1.1 확인된 외부 계정 상태

- Datadog: 조직 `KILMINKYU Backpack`, 사이트 US5, 계정 `henry42471@gmail.com`, 학생 인증 확인. 체크와 대시보드는 생성했으며 5일 비용 추정 후 Preview 전용 연속 로그 드레인이 명시적으로 승인되었다.
- Datadog 알림 수신자: `sea42471@naver.com`. 모니터 생성 후 통제된 테스트 알림과 복구 알림을 실제 수신했는지 별도로 기록한다.
- GA4 운영: 계정 `409928949`, 속성 `556455967`, 웹 스트림 `15863555614`, 측정 ID `G-6GMP7FRN3B`.
- GA4 운영 설정: Enhanced Measurement OFF, 이벤트 데이터 2개월, 사용자 데이터 2개월, 새 활동 시 보관기간 재설정 OFF, Google Signals·사용자 데이터 수집 OFF. 광고 개인화 화면 표시는 `0/307`이다.
- GA4 테스트: 속성 `556468075`, 웹 스트림 `15863631869`, 측정 ID `G-VG9FXGTRDE`.
- GA4 테스트 설정: Enhanced Measurement OFF, 이벤트 데이터 2개월, 사용자 데이터 2개월, 새 활동 시 보관기간 재설정 OFF, Google Signals·사용자 데이터 수집 OFF. 광고 개인화 화면 표시는 `0/307`이다.
- Preview 배포 `dpl_4oga5WktqE7j4g8VSQQm1YdgVnMY`는 READY이며 `dino-nanobanana-ogt2lb0sp-henry-kils-projects.vercel.app`과 [https://google-korea-team-gemini.vercel.app](https://google-korea-team-gemini.vercel.app) 별칭이 연결되었다. 공개 `/api/config`는 테스트 ID `G-VG9FXGTRDE`, `enabled=true`, `debug=true`를 반환했고 `/api/health`는 HTTP 200과 DB ready를 반환했다.
- **이전 동의형 버전의 당시 기록:** 동의 전과 거절 후에는 Google Tag Manager 스크립트가 없었고 순위 화면은 정상 작동했다. 허용 후에만 정확한 테스트 태그가 삽입되었다. 현재 정책의 동작 설명으로 사용하지 않는다.
- 테스트 속성 DebugView의 최근 30분 요약은 8개 이벤트를 표시했다: `content_view` 2건, `page_view` 2건, `benefit_view`, `first_visit`, `gemini_cta_view`, `session_start` 각 1건. `non_personalized_ads=1`은 이벤트가 아니라 사용자 속성으로 확인했다. 이는 Preview 허용 후 테스트 속성의 서버 수신을 확인한 결과다.
- 분석 설정은 각 속성에 사용자 정의 차원 11개와 `duration_seconds` 사용자 정의 지표를 생성했다. 운영 속성에는 01~07의 탐색 8개(06A·06B 분리)를 저장했다. TOP3는 입력을 시작한 대상자를 분모로 쓰며, 추천 발신자와 유입자를 서로 다른 사용자로 분리해 집계한다. 실제 URL과 해석 기준은 [GA4 보고서 구성](ga4-report-layout.md)에 기록했다. 현재 베타는 테스트 속성으로만 수집하므로 운영 탐색의 값은 비어 있다.
- **이전 동의형 버전의 당시 기록:** 분석 철회 후 재로드에서 CUA DOM의 Google 측정 스크립 목록은 빈 배열이었으며 혜택 화면은 정상 작동했다. CUA에서 원시 네트워크 로그는 직접 확인할 수 없었다.
- **현재 자동 수집 버전:** 사용자의 최종 승인에 따라 팝업과 상단 분석 설정을 제거했다. 기존 거부가 없는 브라우저는 GA4를 자동으로 사용하지만 방문만으로 `granted` 선택을 저장하지 않는다. 기존 거부 브라우저에서는 SDK가 없었고, 개인정보 안내에서 `자동 분석 다시 사용`을 선택한 뒤 팝업 없이 테스트 태그가 로드됐으며, 다시 `분석 사용 중지`를 선택한 뒤 SDK가 제거되는 흐름을 확인했다. 게임 기능은 계속 작동했다.
- Vercel 수신 프로젝트의 Production `DD_API_KEY`는 사용자 승인 후 UI에 민감 값으로 저장되었고, `VERCEL_DRAIN_SECRET`은 CLI로 Production에 저장되었다.
- 수신기 배포 `dpl_8H9tDzTwRNDvVnVBm9V5KYpBtkey`는 Production READY이다. 안정 도메인의 `/api/drain`은 서명 없는 요청에 403을 반환했고 Vercel 공식 전송 테스트에 200을 반환했다. 이 결과는 Datadog에 실제 로그가 최종 표시되었음을 증명하지는 않는다.
- Vercel 연속 드레인 `drn_fFTUMpevVS39jHws`(`gemini-dino-api-logs`)는 enabled 상태다. `filterV2`는 `sources=[lambda]`, 소스 프로젝트 `prj_U9Wi3VyA46EpOdOyrq0P3RRHwMSX`, `deploymentEnvironments=[preview]`로 제한되고 schema는 `log.v1`이다. 약 05:23 UTC에 정상 API 요청 2건을 발생시켜 HTTP 200을 확인했다.
- Datadog Log Management는 Vercel 드레인과 별도로 명시적 승인을 받은 후 활성화했다. Log Explorer에서 `2026-09-29T05:25:36.748Z` `/api/health` 로그를 확인했다. 필드는 `service=gemini-dino-jump`, `env=preview`, `campaign=gemini_dino_phase1_test`, `duration_ms=77`, `http.status_code=200`, `status=info`, `outcome=success`, `operation_outcome=completed`, `version=dpl_4oga5WktqE7j4g8VSQQm1YdgVnMY`였고 요청 ID는 무작위 UUID 형식이었다.
- Log Explorer의 전체 속성을 확인했을 때 허용된 정규화 필드만 있었고 IP, User-Agent, referrer, query, body, 비밀값은 없었다. 이로써 앱 로그 생성, Vercel 필터·서명, 수신기 정리, Datadog 파싱까지 전 구간을 검증했다.
- Datadog 원격 상태 확인은 HTTP 200, 응답 시간 162.1ms였고 3개 assertion이 모두 PASS했다. 압축 없는 JSON 표현에 의존하지 않도록 JSONPath `$.ok == true`, `$.database == ready`를 사용했다.
- Synthetic 모니터 2개와 로그 실패 모니터에 승인된 수신자 `sea42471@naver.com`을 저장했다. 대시보드는 요청 수 2, p95 44ms, 5xx, `error_class=database`, `operation_outcome=webhook_processing_failed` 계수를 보이는 5개 위젯으로 확인했다.
- 로그 실패 모니터 [22787526](https://us5.datadoghq.com/monitors/22787526) `Dino Preview Server database or webhook processing failures`를 저장했다. 조건은 Preview의 HTTP 5xx, `error_class:database`, `operation_outcome:webhook_processing_failed` 중 하나가 최근 5분에 3건 이상일 때 critical, 0건이면 recovery이다. missing data는 0으로 평가하고 표본 첨부·재알림·Bits는 끄며 현재 상태는 OK이다.
- Datadog UI에서 Test Notification Alert과 Alert Recovery 모두 `Test notifications sent`를 확인했다. 실제 메일함 도착은 확인 전이며, 서비스에 실제 장애를 유발하지 않았다.

## 2. GA4 설정

### 2.1 승인된 정책

- 사용자의 최종 승인에 따라 별도 동의 팝업과 상단 `분석 설정` 없이 GA4를 자동으로 사용한다. 방문 자체를 명시 동의로 기록하거나 `granted` 선택을 저장하지 않는다.
- 기존 `denied` 저장값과 수집 중지 쿠키, Global Privacy Control·Do Not Track·Google 차단 신호를 우선한다. 거부 상태이거나 저장소 확인에 실패하면 수집하지 않는다.
- 개인정보 안내의 `이 브라우저에서 분석 사용 중지`로 기존 GA 쿠키와 분석 중복 방지 기록을 삭제하고 이후 수집을 막는다. 같은 화면의 `자동 분석 다시 사용`으로 해당 브라우저의 사이트 거부값을 해제할 수 있다.
- 사용자별 이벤트 데이터 보관은 **2개월**로 설정한다.
- GA4 관리 화면의 **새 활동 시 보관기간 재설정**은 **끔(OFF)** 으로 설정한다.
- 테스트와 운영은 서로 다른 GA4 속성을 사용한다. 한 속성의 스트림만 나눠 운영 데이터 격리를 대신하지 않는다.
- 자체 참가자 ID를 GA4 User-ID로 보내지 않는다.
- 이름, 연락처, 학교, 주소, 초대 코드, 공유 식별자, 쿠키, 인증값을 보내지 않는다.

### 2.2 서버 환경 변수

코드는 기본적으로 꺼져 있다. `GA4_ENABLED`가 없거나 `false`이면 공개 설정은 `enabled=false`다.

| 변수 | 설정 원칙 |
| --- | --- |
| `GA4_ENABLED` | Preview·Production의 승인된 자동 분석에서는 `true`. 긴급 중지나 미검증 환경에서는 `false` |
| `GA4_TEST_MEASUREMENT_ID` | Preview 전용 테스트 속성의 `G-...` ID |
| `GA4_PRODUCTION_MEASUREMENT_ID` | 운영 전용 속성의 `G-...` ID. 테스트 ID와 달라야 함 |
| `GA4_ALLOWED_ORIGINS` | 전송을 허용할 정확한 HTTPS origin을 쉼표로 구분. 와일드카드·경로·쿼리 금지 |
| `GA4_DEBUG_MODE` | Preview DebugView 검증 중에만 `true`; 운영에서는 `false` |

두 측정 ID를 환경에 함께 준비하되 `APP_ENV=preview`는 테스트 ID만, `APP_ENV=production`은 운영 ID만 공개한다. `GA4_ALLOWED_ORIGINS`는 서버의 기존 허용 origin 안에 있는 값만 인정된다. 현재 공개 베타는 Preview이므로 운영 속성 전송을 켜지 않는다.

### 2.3 원격 속성 설정 순서

1. 사용할 Google 계정과 속성 소유자를 확인한다.
2. `Asia/Seoul` 시간대의 테스트 속성과 운영 속성을 각각 만든다.
3. 두 속성 모두 데이터 보관을 2개월, 새 활동 시 재설정을 OFF로 설정한다.
4. 각 속성에 실제 사이트용 웹 데이터 스트림을 만들고 서로 다른 측정 ID를 확인한다.
5. Preview의 정확한 HTTPS origin만 `GA4_ALLOWED_ORIGINS`에 넣는다.
6. Preview에서 `GA4_ENABLED=true`, 테스트 측정 ID, 필요 시 `GA4_DEBUG_MODE=true`를 적용한다.
7. 기존 거부가 없는 새 브라우저에서 팝업·상단 설정 없이 정확한 환경의 태그가 자동 로드되는지 확인한다. 방문만으로 `granted`가 저장되지 않아야 한다.
8. 기존 거부·브라우저 거부 신호에서는 SDK가 로드되지 않는지, 개인정보 안내의 중지·재사용과 `_ga` 쿠키 삭제가 동작하는지 확인한다.
9. DebugView에서 테스트 속성 이벤트를 확인하고 중복·개인정보·원시 URL이 없는지 검사한다. 운영 공개 후에는 운영 속성 Realtime 수신을 별도로 확인한다.
10. 운영 배포 승인 후 운영 origin과 운영 측정 ID로 별도 검증한다.
11. 문제가 있으면 `GA4_ENABLED=false`로 되돌린다. 게임 기능은 계속 동작해야 한다.

### 2.4 코드 기준 GA4 이벤트

`public/js/ga4_analytics.js`의 현재 매핑이다. 실제 DebugView에서 아래 이름이 그대로 들어오는지 확인한다.

| 앱 이벤트 | GA4 이벤트 | 앱 이벤트 | GA4 이벤트 |
| --- | --- | --- | --- |
| `entry_viewed` | `entry_viewed` | `loading_ready` | `loading_ready` |
| `game_cta_clicked` | `game_cta_click` | `game_start_approved` | `game_start` |
| `game_completed` | `game_complete` | `draw_cta_clicked` | `draw_cta_click` |
| `draw_entered` | `draw_entered` | `pouch_selected` | `pouch_selected` |
| `scratch_started` | `scratch_started` | `scratch_completed` | `scratch_complete` |
| `draw_result_viewed` | `draw_result_view` | `claim_form_started` | `claim_form_start` |
| `claim_draft_saved` | `claim_draft_saved` | `claim_form_submitted` | `claim_form_submit` |
| `top3_profile_started` | `top3_profile_start` | `top3_profile_submitted` | `top3_profile_submit` |
| `invite_cta_viewed` | `invite_cta_view` | `share_attempted` | `share_interaction` |
| `benefit_viewed` | `benefit_view` | `gemini_cta_viewed` | `gemini_cta_view` |
| `gemini_cta_clicked` | `gemini_cta_click` | `content_viewed` | `content_view` |
| `content_clicked` | `content_click` | `tutorial_viewed` | `tutorial_view` |
| `tutorial_progressed` | `tutorial_progress` | `tutorial_skipped` | `tutorial_skip` |

화면 이동은 `page_view`로 전송한다. `page_location`과 `page_referrer`는 실제 URL 대신 허용된 화면명의 `/virtual/{screen}` 경로를 사용한다. 허용 화면은 `loading`, `home`, `game`, `result`, `draw`, `claims`, `ranking`, `invite`, `benefit`이다.

허용 파라미터는 이벤트별로 제한된다.

- 유입: `campaign_source`, `campaign_medium`, `campaign_name`, `campaign_content`, `link_kind`
- 화면·CTA: `screen_name`, `source`, `position`
- 게임: `game_version`, `play_type`, `score`, `rank`, `end_reason`, `verification_status`
- 추첨: `pouch`, `result_type`, `round_number`
- 수령: `claim_type`
- 공유·콘텐츠: `content`, `share_method`, `share_status`, `tutorial_step`

허용 목록 밖 값은 버린다. 성공 이벤트는 게임 세션 또는 작업 식별자의 로컬 해시로 중복을 줄이며 원본 식별자는 GA4에 보내지 않는다.

## 3. Datadog 설정

### 3.1 계정과 한도 확인

- 학생용 공식 시작점: [Datadog Student Pack](https://studentpack.datadoghq.com/)
- 제공 사이트: **US5**
- 새 Datadog 계정에만 적용되는 조건을 확인한다.
- 학생 혜택은 비상업적 사용에 한정된다.
- 안내 한도: 월 로그 **500GB**, Synthetic API 테스트 실행 **10,000회**. 실제 조직 화면의 적용 상태와 기간을 다시 확인한다.
- 홈과 `/api/health` 두 테스트를 각각 10분 간격, 자동 재시도 0회로 실행하면 수동 실행을 제외하고 하루 288회, 5일 **1,440회**, 30일 **8,640회**다. 월 10,000회 가드를 넘지 않도록 수동 실행과 추가 테스트를 함께 계수한다.

혜택 활성화와 실제 남은 사용량을 계속 확인한다. Vercel 연속 로그 드레인처럼 별도 비용이 발생하는 기능은 사전 비용 승인 후 활성화한다.

### 3.2 Vercel 로그 전송 전 개인정보 게이트

현재 유료 연속 Datadog 로그 드레인은 명시적으로 승인되었고 Preview·Lambda 전용으로 활성화되었다. 애플리케이션 JSON 로그는 정규화된 경로만 기록한다. Vercel의 기본 요청·래퍼 로그는 애플리케이션 처리 전에 원래 경로, 쿼리, IP를 포함할 수 있다.

다음 조건을 실제 Vercel·Datadog 화면과 표본 로그로 확인하기 전 전송을 활성화하지 않는다.

1. 앱의 구조화 함수 로그만 선택하거나, 원래 경로·쿼리가 Datadog으로 전달되기 전에 제거·정규화되는가.
2. 원시 IP가 전달되지 않도록 숨김 또는 제거할 수 있는가.
3. 쿠키, `Authorization`, 요청 본문, 수령 정보, 초대·공유 식별값이 표본에 없는가.
4. Preview와 Production을 `env`, `campaign`, `deployment`로 구분할 수 있는가.
5. 같은 오류가 Vercel 플랫폼 로그와 앱 로그에서 중복 집계되지 않는가.

공식 연동 UI의 정확한 옵션명과 변환 형식은 활성화 시점의 문서와 화면에서 확인한다. 사전 전송 정리가 보장되지 않으면 해당 기본 요청 로그를 보내지 않고 안전한 앱 JSON 로그만 전달할 수 있는 구성을 사용한다.

### 3.3 Vercel Custom Log Drain 구성 절차

수신 프로젝트는 별도 Vercel 프로젝트 `dino-datadog-drain`을 사용한다. Production 자격 증명과 수신기 배포는 준비되었으며, 아래 Preview 전용 연속 드레인 생성은 5일 비용 안내 후 사용자가 승인했다.

1. `dino-datadog-drain` 프로젝트의 배포 URL과 `/api/drain` 응답 경로를 확인한다.
2. 수신 프로젝트에 `DD_API_KEY`와 `VERCEL_DRAIN_SECRET`을 비밀 환경 변수로 설정한다. 값은 문서·로그·소스에 기록하지 않는다.
3. 본 사이트 Vercel 프로젝트에서 Preview용과 Production용 Custom Log Drain을 각각 만든다.
4. 두 드레인의 전송 형식은 **JSON**, 배치는 **JSON 배열**, 로그 source는 **Lambda만** 선택한다.
5. 목적지는 각각 `https://<dino-datadog-drain 배포 도메인>/api/drain`으로 지정한다.
6. Preview 드레인은 Preview 환경만, Production 드레인은 Production 환경만 선택한다. 다른 프로젝트를 포함하지 않는다.
7. 두 드레인에 동일한 `VERCEL_DRAIN_SECRET`에 대응하는 서명 설정을 적용한다.
8. Preview에서 한 건을 전송해 `projectId`, `source=lambda`, `environment=preview`, `campaign=gemini_dino_phase1_test`, `deploymentId` 일치를 확인한다.
9. Datadog 수신 JSON에 `message=api_request`, `service`, `env`, `campaign`, `version`, `ddtags`, 정규화된 `route`만 남고 proxy 경로·쿼리·IP·header·body가 없는지 확인한다.
10. Preview 표본 승인 후 Production 드레인을 별도로 검증한다.

수신기는 Vercel 서명을 검증하고 정확한 프로젝트·환경·캠페인·배포·Lambda source만 허용한다. `type`은 없거나 `stdout`·`stderr`일 때 허용하며 명시적인 다른 값은 버린다. 허용된 유형이라도 정해진 구조의 `api_request`만 필드별 검사를 통과할 수 있고 일반 출력·임의 개인정보 JSON은 버린다. Datadog 전송 실패 시 502를 반환해 Vercel 재시도 대상으로 남기며 원본 payload나 키를 응답하지 않는다.

### 3.4 5일 비용 가정

사용자는 다음 5일 가격 추정을 확인한 후 Preview 전용 연속 드레인 연결을 명시적으로 승인했다. 다음은 승인된 작업의 추정 근거이며 비용 상한은 아니다.

- 참가자 5,000명, 1인당 50~100건, 1건당 2~5KB로 가정하면 약 0.5~2.5GB다.
- Vercel 드레인 단가를 GB당 $0.50로 가정한 전송 비용은 약 $0.25~$1.25다.
- 재시도, 래퍼 로그, 실제 바이트 계산, Datadog 기능 비용을 포함한 전체 계획 범위는 약 $1~$5로 본다. 이 금액은 상한, 견적, 비용 승인이 아니다.
- Vercel Usage UI에서 현재 주기는 9월 22일~10월 22일, Included Credit은 `$1.10 / $20`, 표시 잔액은 `$18.90`이며 사용량 데이터는 최대 1시간 지연될 수 있다. Vercel Pro 문서의 월 크레딧은 managed infrastructure 사용량에 먼저 적용된다.
- 현재 표시 기준으로는 추정 관측 비용 `$1~$5`가 남은 크레딧 안에 있다. 같은 주기의 전체 managed infrastructure 사용량이 크레딧을 넘지 않으면 카드 청구가 없을 수 있지만, 이는 무료 보증이 아니다.
- 승인 시에도 처음에는 Preview·Lambda·앱 JSON 로그만 선택하고 실제 24시간 사용량을 본 후 추정을 갱신한다.

### 3.5 코드 기준 Datadog 로그 스키마

서버는 한 요청당 `api_request` JSON 한 줄을 표준 오류 출력에 기록한다.

| 필드 | 값 |
| --- | --- |
| `event` | `api_request` |
| `service` | `gemini-dino-jump` |
| `env` | `local`, `test`, `preview`, `production` 또는 `unknown` |
| `campaign` | 서버 설정·DB guard의 캠페인 ID |
| `deployment` | 배포 식별값 |
| `route` | 허용 목록의 정적 경로 또는 `{id}` 템플릿; 그 외 `/api/unknown` |
| `method` | `GET`, `HEAD`, `POST`, `PATCH`, `OPTIONS` |
| `status` | Datadog 심각도: `info`, `warn`, `error` |
| `http.status_code` | 숫자 HTTP 상태 코드 |
| `duration_ms` | 전체 서버 요청 시간 |
| `request_id` | 응답의 `X-Request-ID`와 연결하는 요청 ID |
| `outcome` | `success`, `client_error`, `server_error` |
| `operation_outcome` | 일반 완료·실패 또는 제한된 카카오 웹훅 처리 결과 |
| `error_class` | `none`, `validation`, `authentication`, `rate_limit`, `domain`, `database`, `configuration`, `internal` |
| `error_code` | 서버의 제한된 오류 코드, 정상 요청은 `null` |
| `database_failure` | `pool_wait`, `connection`, `health_check`, `configuration`, PostgreSQL SQLSTATE 또는 `null` |

카카오 웹훅 HTTP 200 결과는 `webhook_duplicate`, `webhook_expired`, `webhook_rejected`, `webhook_reward_granted`, `webhook_reward_blocked`, `webhook_no_reward`, `webhook_not_eligible`로 구분한다. 정상 한도·자기 전송 제외·보상 없음은 서버 장애로 집계하지 않는다. 실제 응답 계약에 없는 조합은 `webhook_processing_failed`로 기록한다.

로그에는 요청 body, query, header, 쿠키, 토큰, IP, 이름, 연락처, 학교, 주소를 넣지 않는다.

### 3.6 상태 확인

- 홈: HTTP 성공과 예상 페이지 문구를 확인한다.
- `/api/health`: 캐시하지 않는 HTTP 응답, DB 연결, schema guard, 읽기 전용 `SELECT 1`, 캠페인 조회 성공을 확인한다.
- `campaign_status`가 `NOT_OPEN`, `PAUSED`, `ENDED`여도 서버·DB가 정상이면 `ok=true`다. 행사 상태를 장애로 알리지 않는다.
- DB 연결 또는 schema guard 실패는 503과 구조화된 `database_failure`로 확인한다.
- 두 테스트를 가까운 지원 지역 한 곳에서 10분 간격, 자동 재시도 0회로 실행하고 실패 시 알림을 보낸다.

### 3.7 검증된 필드 기반 질의

Log Explorer에서 `service`, `env`, `campaign`, `version`, `status`, `http.status_code`, `duration_ms`, `outcome`, `operation_outcome`의 파싱을 확인했다. 아래 질의는 실제 트래픽과 경보 조건을 보며 임계치를 조정한다.

```text
service:gemini-dino-jump env:preview status:error
service:gemini-dino-jump env:preview @http.status_code:[500 TO 599]
service:gemini-dino-jump env:preview @error_class:database
service:gemini-dino-jump env:preview @route:/api/health @http.status_code:503
service:gemini-dino-jump env:preview @operation_outcome:webhook_processing_failed
service:gemini-dino-jump env:preview @route:/api/game-sessions/{id}/finish
service:gemini-dino-jump env:preview @route:/api/draws
service:gemini-dino-jump env:preview @route:/api/claims/{id}/submit
```

초기 대시보드에는 환경·배포별 요청 수, 5xx 오류율, p95 `duration_ms`, DB 실패, 카카오 처리 실패, `/api/health` 결과를 둔다. 정상 `client_error`, `webhook_reward_blocked`, `webhook_rejected`, `webhook_expired`, `webhook_not_eligible`는 서버 장애 모니터에서 제외한다.

현재 Synthetic 상태 확인은 재시도 없이 실패를 알린다. 로그 실패 모니터의 실제 질의는 다음과 같다.

```text
logs("service:gemini-dino-jump env:preview (@http.status_code:[500 TO 599] OR @error_class:database OR @operation_outcome:webhook_processing_failed)").index("*").rollup("count").last("5m") > 2
```

critical은 3건 이상, recovery는 0건 이하로 설정했다.

다음 고급 경보는 아직 구현된 것으로 기록하지 않는다.

- 기능별 5분 오류 5건과 오류율 5% 복합 조건
- 5분 요청 20건 이상일 때 p95 3초 초과
- `webhook_processing_failed` 반복 전용 경보
- Vercel·Datadog 사용량과 비용 경계 경보

### 로그 수집 공백 감시

- 모니터: [Dino Preview - Health log ingestion gap](https://us5.datadoghq.com/monitors/22787598), ID `22787598`.
- 저장된 평가식: `logs("service:gemini-dino-jump env:preview @route:/api/health").index("*").rollup("count").last("30m") < 1`.
- 최근 30분 상태 확인 로그가 0건이면 경보, 1건 이상이면 회복한다. 누락 데이터는 0으로 평가한다.
- 수신처: `sea42471@naver.com`. 로그 표본 첨부·반복 알림·Bits는 사용하지 않는다.
- 10분 간격의 상태 확인 테스트가 켜져 있다는 전제다. 테스트를 의도적으로 중지하면 이 모니터도 함께 중지한다.
- 생성 직후 전파 대기 상태를 거친 뒤, 실제 상태 화면에서 `OK` 전환과 저장된 평가식을 확인했다.
- 공백 모니터 확인을 위해 실제 서비스를 중단하거나 추가 테스트 메일을 보내지는 않았다.

## 4. 활성화 검증 기록

활성화 작업 때 아래 증거만 채운다.

| 확인 항목 | 기록할 값 |
| --- | --- |
| GA4 테스트 속성·스트림 | 속성명, 확인 시각, 측정 ID 끝 4자리 |
| GA4 운영 속성·스트림 | 속성명, 확인 시각, 측정 ID 끝 4자리 |
| GA4 보관·재설정 | 2개월, reset OFF 화면 확인 시각 |
| GA4 자동 수집 검증 | 새 브라우저 자동 태그·전송, 팝업·상단 설정 부재, 기존 거부·브라우저 신호 우선, 개인정보 안내의 중지·재사용 결과 |
| Datadog 학생 혜택 | 조직명, US5, 적용 기간, 실제 한도 확인 시각 |
| Vercel 로그 연결 | 프로젝트·환경, 원시 경로·쿼리·IP 제거 표본 |
| Datadog 파싱 | 필드 목록과 예시 요청 ID 한 건 |
| Synthetic 테스트 | 홈·헬스 테스트 ID, 지역, 10분 주기, 재시도 0회 |
| 알림 수신자 | 사용자가 확인한 담당자 이메일 또는 채널 |
| 중단·정리 | `GA4_ENABLED=false`, 로그 드레인·Synthetic·모니터 중지 절차 확인 |

## 5. 공식 자료

### GA4

- [Google Analytics — 단일 페이지 애플리케이션 측정](https://developers.google.com/analytics/devguides/collection/ga4/single-page-applications)
- [Google Analytics — Funnel exploration](https://support.google.com/analytics/answer/9327974?hl=ko)
- [Google Analytics — 개인 식별 정보 전송 예방](https://support.google.com/analytics/answer/6366371?hl=ko)
- [Google Analytics — 데이터 반영 시간](https://support.google.com/analytics/answer/11198161?hl=en)

### Datadog·Vercel

- [Datadog Student Pack](https://studentpack.datadoghq.com/)
- [GitHub Student Developer Pack](https://education.github.com/pack)
- [Datadog 학생 프로그램 안내](https://www.datadoghq.com/blog/datadog-github-student-developer-pack/)
- [Datadog Vercel 연동](https://docs.datadoghq.com/integrations/vercel/)
- [Datadog HTTP API 테스트](https://docs.datadoghq.com/synthetics/api_tests/http_tests/)
- [Datadog 로그 인덱스와 보관](https://docs.datadoghq.com/logs/log_configuration/indexes/)
- [Datadog 가격](https://www.datadoghq.com/pricing/)
- [Vercel Drains 한도와 요금](https://vercel.com/docs/limits)
- [Vercel Pro 월 크레딧](https://vercel.com/docs/plans/pro-plan#monthly-credit)
- [Vercel Analytics 민감 데이터 제거](https://vercel.com/docs/analytics/redacting-sensitive-data)
