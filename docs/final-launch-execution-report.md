# 공룡 점프 최종 오픈 실행 기록

- 작성일: 2026-09-29
- 실행 계획: [최종 오픈 실행 계획](final-launch-execution-plan.md)
- 실행 브랜치: `codex/final-launch-preflight`
- 현재 상태: **운영 DB·관리자·관측 경로 준비 및 전환 보호 보완 완료. 후보 고유 URL은 외부에서 열리지만 친근 공개 별칭으로 승격하지 않았고 이벤트는 OFF. 공개 전환, 베타 삭제, 최종 원격 부하는 실행하지 않음.**

## 확인한 운영 준비 상태

| 항목 | 확인 결과 | 남은 게이트 |
| --- | --- | --- |
| Supabase 운영 구역 | 기존 프로젝트 `igfrnexknwtiljdqjrbp`에 `dino_prod` 32개 테이블·12개 schema version과 `dino_prod_app` LOGIN 역할 생성. 역할은 비밀번호 유효기간과 최소 권한을 확인했고 `public`·`dino_dev` 테이블 접근은 0건 | 최종 배포의 manifest SHA·DB guard·역할을 공개 직전 다시 대조 |
| 운영 재고 | 복주머니 5,000자리 = 실제 상품 77 + 혜택 4,923. 별도 랭킹 경품 3개를 포함한 재고 80개. 참가자·게임·추첨·수령 기록은 모두 0건 | 공개 시점 수량·정책·OFF 플래그 재대조. 상품은 당첨자 연락처 취합 후 구매·일괄 발송하며 발송일은 미정으로, 구매 완료 증빙은 공개 선행 게이트가 아님 |
| 운영 캠페인 | `gemini_dino_campus_2026`, `PAUSED`, `event_enabled=false`, `test_seed=false` | 모든 공개 증거·승인 완료 후에만 `APPROVED`/이벤트 ON 검토 |
| 베타 백업 | 2026-09-29 15:58:54 KST 기준 32개 테이블을 비공개 보관. 격리 로컬 PostgreSQL 복원에서 전체 행·제약·identity sequence 일치 | 베타는 계속 쓰기 가능하므로 삭제 직전 쓰기 차단 후 최종 백업 재생성 |
| 운영 관리자 | `sea42471@naver.com`의 비밀번호 설정·관리자 진입을 사용자가 확인. 브라우저에서도 로그인 완료, 통계·수령·랭킹 관리 영역과 운영 환경 `production`을 확인. 후보·정식 주소의 정확한 `/admin.html` redirect 등록, 기존 Site URL 유지 | 공개 별칭 전환 후 같은 운영 계정의 접속 경로 확인 |

`dino_prod` 적재 요약은 `.local/final-launch/production-provision-manifest.json`과 `provision-export.log`, 런타임 guard 요약은 `production-runtime-check.log`, 베타 복원 결과는 `backup-restore.log`에 보관했다. 이 파일들과 원본 백업·접속 자격증명은 `.local/`에 있으며 Git·공개 배포에 포함하지 않는다. 이 문서에는 비밀값·사용자 ID·참가자 식별자·수령 정보를 옮기지 않았다.

## Production 후보 검증

- 최신 후보 배포 `dpl_2QNuiZQHwoBqsYDvmFwti9Yo4zeH`은 커밋 `ba5826d`의 운영 전환 보호 코드를 포함해 READY다. 고유 주소는 `https://dino-nanobanana-jwpczflr5-henry-kils-projects.vercel.app`이며, 이벤트는 OFF로 유지했다. 관리자 비밀번호 설정·실제 로그인 확인은 이전 후보 `dpl_94Yqtt6yTqrELm6Rp9JGdwdeNVv7`에서 완료했다. 두 고유 URL 모두 외부에서 접근 가능하며 친근 공개 별칭으로는 승격하지 않았다.
- `/api/health`는 HTTP 200, `environment=production`, `database=ready`, `schema=dino_prod`, `synthetic_only=false`, `test_seed=false`, `campaign_status=PAUSED`, 남은 재고 80을 반환했다.
- `/api/config`는 운영 캠페인·게임 버전·GA4 운영 속성·정확한 허용 origin과 `event_enabled=false`를 반환했다. 비밀값은 응답에 없었다.
- 최신 후보에서 새 참가자, 게임, 추첨 POST는 모두 HTTP 409 `EVENT_NOT_ENABLED`로 거절됐고 미인증 관리자 API는 HTTP 401 `ADMIN_AUTH_REQUIRED`로 거절됐다. `/api/health`·`/api/config`는 HTTP 200이다. 증거는 `.local/final-launch/cutover-candidate-verification.json`에 보관했다. 추가한 공유 트랜잭션 잠금도 실제 운영 전용 역할에서 실행됐으며 참여·추첨 기록은 생성하지 않았다.
- 친근 공개 별칭 `google-korea-team-gemini.vercel.app`과 기존 Production 주소 `dino-nanobanana.vercel.app`는 이전 배포를 계속 가리킨다. 후보 생성 중 자동으로 변경된 보조 프로젝트 별칭은 이전 대상으로 명시적 복구했다. 이 후보를 공개 별칭으로 승격하지 않았다.

행사 ON 이후에는 정식 `APP_BASE_URL`의 Host에서만 참가자·게임·추첨·공유·수령 API가 처리된다. 후보의 상태·설정 조회와 인증된 관리자 기능은 유지한다. 공개 GET·카카오 GET/POST·OPTIONS도 후보 주소에서는 거절하며 전달 헤더로 우회할 수 없다. 이 ON 분기는 격리 HTTP 검사로 확인했고 실제 운영 ON으로 시험하지 않았다. 전환 도구와 API는 같은 advisory lock을 사용하며, 업무 트랜잭션 안에서 guard를 다시 검사한다. 실제 PostgreSQL 동시성 검사에서 진행 중 요청의 commit을 기다린 뒤 중단하고, 이전 설정의 후속 쓰기를 거절했다. 관련 집중 검사 41건이 통과했다(`cutover-runtime-regressions.log`).

## Gemini 학생 혜택 링크 확인

- 2026-09-29 17:13~17:14 KST에 로그인·신청·데이터 제출 없이 공개 GET으로 `https://VQyu3J.s.gy/Game`을 확인했다. Short.io의 HTTP 302가 `https://gemini.google/students/?utm_source=student&utm_medium=social&utm_campaign=microsite_campus_seoultech-ambassador`로 이동했고 Google Frontend가 HTTP 200을 반환했다. 링크는 현재 Google의 공식 학생 페이지로 연결된다.
- 공식 한국어 페이지는 Google AI Plus 학생 요금제를 12개월 무료로 제공한다고 게시하며, 공개된 약관은 2026-12-31까지 교환해야 한다고 정한다: <https://gemini.google/students/> 및 <https://one.google.com/offer/studentoffer8>. 약관 최종 갱신일은 2026-08-19다.
- 개인별 수급 자격은 이 공개 확인으로 증명되지 않는다. 약관상 만 18세 이상, 지원되는 국가·지역의 고등교육기관 재학, SheerID 학생 인증, 개인 Google 계정, 적격 결제수단이 필요하며, 가족 그룹·일부 기존 구독 등 제외 조건이 있다. 무료 기간 종료 전 취소하지 않으면 해당 국가의 표준 월 요금이 자동 청구된다. 프로모션 UI는 이 확인으로 변경하지 않았다.

## 관측 준비

- Production 전용 Vercel 로그 드레인 `drn_bzjpXu6NoqXGx75u`를 생성하고 검증 요청 HTTP 200을 확인했다. 소스는 Lambda, 환경은 Production, 프로젝트와 캠페인은 허용 목록으로 제한한다.
- Production 오류 모니터 `22788890`은 `env:production`으로 활성화했다. 수집 공백 모니터 `22788937`은 현재 공개 heartbeat가 베타를 가리키므로 공개 전환 전까지 DRAFT로 두었다. Production 대시보드 `a27-779-mch` 내보내기에서 위젯 5개, 질의 5개 모두 `env:production`, Preview 질의 0개를 확인했다.
- 수신 호환성 보완은 `dpl_ELKJ4CvrHAg3g8LF5j1Wx1EghxpA`로 READY 배포했다. Datadog Logs Explorer에서 Production 로그 2건을 확인했다. 최신 표본은 2026-09-29 16:51:25.116 KST의 `env=production`, `campaign=gemini_dino_campus_2026`, `version=dpl_94Yqtt6yTqrELm6Rp9JGdwdeNVv7`, `GET /api/health`, HTTP 200, `duration_ms=54`, `error_class=none`이다. 16:48:31.856 KST의 보완 전 로그도 늦게 도착했으므로, 이 보완이 문제의 유일한 원인 해결이었다고 주장하지 않는다. 사용자가 제공한 메일함 화면에서 2026-09-29 14:32의 Datadog Alerting `Triggered: [TEST] Dino Preview`와 `Recovered: [TEST] Dino Preview` 메일 수신을 확인했다. 이는 베타 모니터의 테스트 발생·복구 알림이며 실제 장애가 아니다. 운영 모니터의 실제 발송까지 확인한 증거로 확대하지 않는다.
- GA4 운영 허용 origin은 친근 공개 도메인만 허용한다. 따라서 후보 고유 URL에서는 동의 후에도 운영 이벤트를 전송할 수 없으며, 후보에서의 미전송은 설계된 차단이다. Preview 동의 흐름은 확인했지만 실제 Production 동의·전송은 공개 별칭 전환 직후의 cutover 검사로 남아 있다.

## 카카오 운영 도메인 확인

- 2026-09-29 17:46~17:50 KST에 Kakao Developers 앱 `1588671`(`Google Student Ambassador`)의 보이는 설정을 읽기 전용으로 확인했다. JS SDK 허용 도메인과 기본 제품 링크 도메인은 모두 `https://google-korea-team-gemini.vercel.app` 한 개였다.
- 공유 웹훅은 `사용함`, `POST`, `https://google-korea-team-gemini.vercel.app/api/webhooks/kakao-share`였다. 관리자 키 조회·변경, 새 권한 부여, 메시지 전송은 하지 않았다. 확인용 탭은 닫았다.
- 공개 베타 `dpl_4oga5WktqE7j4g8VSQQm1YdgVnMY`와 운영 OFF 후보 `dpl_2QNuiZQHwoBqsYDvmFwti9Yo4zeH`의 공개 설정 모두 JavaScript 키 준비와 `share.webhook_enabled=true`를 반환했다. 이 설정 확인을 실제 카카오 전송 성공으로 확대하지 않는다. 비밀값 없는 요약은 `.local/final-launch/kakao-console-verification.json`에 보관했다.
- 수령 접수용 `claim_id` 결합 `NONE` 공유만 자기 전송을 허용하고 `GAME`·`DRAW`의 자기 전송 보상은 제외하는 현재 규칙으로 규범 문서 5개를 맞췄다. 과거 자기 전송이 거절됐던 실행 결과는 당시 증거로 보존했다. 실제 모바일 수령용 자기 전송 검증은 별도 미완료다.
- 격리 PostgreSQL에 베타 GAME/DRAW 요청을 만들고 운영 역할·guard·webhook dispatch로 전달해 `SHARE_INTENT_NOT_FOUND`를 확인했다. 베타 요청 상태·운영 게임권/뽑기권 원장·초대권 잔액은 불변이었다. 운영 요청의 환경·캠페인을 각각 불일치시킨 경우도 `INVALID_WEBHOOK`으로 거절됐다. 기존 전환 잠금·운영 격리 검사와 함께 3/3 통과했고 증거는 `.local/final-launch/late-beta-callback-regressions.log`에 보관했다. 실제 카카오 전송을 모사한 로컬 서버 검사이며 원격 보상 지급은 없었다.

## 마지막 모바일 수령 테스트 준비

- 사용자가 지정한 베타 참가자는 이미 상품 수령 접수가 완료돼 있었다. 기존 건을 되돌리는 대신 현재 TOP3 자격과 미제출 랭킹 요청을 확인하고, 별도의 `RANKING / AWAITING_INFORMATION` 접수 1건만 만들었다. 상품·재고 배정은 없으며 기존 DRAW/연락처 행의 버전, 점수, 랭킹 요청, 추첨과 재고 지문이 전후 같음을 단일 트랜잭션에서 검사했다.
- `scripts/prepare_claim_qa.py`는 `dino_dev`의 합성 Preview/test에 한정된다. 30분 이내 계획과 실제 상태를 대조하고 기존 RANKING 접수·자격/환경 불일치·상태 변화는 거절한다. Supabase SQL connector로 실행했으며 비공개 계획·SQL은 `.local/final-launch/claim-qa-*`에 보관했다. 원격 운영 스키마는 변경하지 않았다.
- 베타 캠페인에 저장된 옛 게임 버전 `1.2.0`과 현재 런타임 `2.1.0`을 구분했다. 실제 API와 같은 `2.1.0` 최고 기록으로 QA 자격을 판정하고 캠페인 값은 바꾸지 않았다. 수령함 API 노출·기존 데이터 보존·계획 만료/변경 거절·정리 거절을 격리 PostgreSQL에서 5/5 확인했다(`claim-qa-regressions.log`). 독립 코드 검토에서 차단 사항은 없었다.
- 사용자는 같은 휴대폰 브라우저의 `/?view=claims`에서 새 **TOP3 접수 내역 → 수령 정보 입력 → 다음 → 카카오톡 공유 → 나에게 보내기**를 검사한다. 결과 화면의 TOP3 입력 폼은 다른 경로이므로 사용하지 않는다. 시험값은 `TEST_QA / 01000000000 / TEST_SCHOOL`이다. 실제 메시지 전송과 3단계 완료, 큰 글씨·키보드에서 버튼 접근 결과는 답변 대기 중이다.
- 정보 입력·공유 등으로 사용한 시험 건은 개별 정리 도구가 지우지 않는다. 예정된 베타 초기화에 포함한다. 미사용 시험 건만 정확한 ID와 계획을 대조하고 접수 행을 잠근 뒤 정리할 수 있다. 이 시험에서는 정리를 실행하지 않았다.

## 코드·회귀 검증

| 검사 | 결과 | 증거·한계 |
| --- | --- | --- |
| JavaScript 전체 | 293 통과, 실패 0 | `.local/final-launch/node-regressions.log` |
| Python 전체 | 340건 실행, 338 통과, 조건부 2 생략, 실패 0 | `.local/final-launch/python-combined-summary.log` |
| Production guard 집중 검사 | 39 통과 | manifest·역할·DB guard·GA4 운영 분리 |
| 베타 초기화 집중 검사 | 11 통과 | 현재 도구의 direct/MCP 동일 범위, 권한 회수·잠금·지연 쓰기·교차 캠페인 보존 |
| 5,000자리 전량 소진 증명 | 1 통과 | 격리 로컬 DB에서 5,000건 중복 0, 상품 77, 혜택 4,923, 추가 추첨 `DRAW_POOL_EXHAUSTED`; `.local/final-launch/local-pool-result.json` |
| 전환 보호·런타임 집중 검사 | 41 통과 | 후보 호스트·Origin·전달 헤더 우회 차단, 실제 DB 잠금/설정 재검사, 기존 운영 설정·스키마·요청 경계 검사 |
| 운영 전환 도구 | 8 통과 | 활성화→기록 생성→SQL rollback 보존, JSON 계획 왕복, 만료·스키마 전체 누락 거절, connector snapshot 일치; `cutover-tool-regressions.log` |

전체 회귀에 관리자 비밀번호 복구 UI 변경을 포함했다. 지정 소스와 추적·미추적 파일을 포함한 독립 검토에서 P0는 발견하지 않았다. 앱 릴리스 소스는 커밋 `4edab6dd7d9edf0cc9c20df4315e728260bfbff1`로 push했고 draft PR [#9](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/9)에서 검토 중이다.

후속 런타임 전환 보호는 `ba5826d`로 push·OFF 후보 배포했고 위 집중 검사로 추가 검증했다. 운영 전환은 [전환 runbook](production-cutover-runbook.md)의 해시 검증 계획과 단일 트랜잭션 도구로 준비했다. 이 도구는 배포/별칭을 직접 변경하지 않으며, 원격 운영 활성화나 rollback에 아직 사용하지 않았다. 초기 오픈과 기록 보존 중단이 범위이며, 이미 기록이 쌓인 뒤 재개는 별도 검토가 필요하다.

같은 커밋의 깨끗한 Git 아카이브에서 필수 런타임 파일, 정적 참조 77개, JavaScript 구문 24개, 집중 검사 48개, Python 컴파일 21개와 API handler import를 별도로 확인했다. 누락 파일은 없었다. 로컬 Python은 3.11이므로 3.12 실행 검증으로 확대하지 않으며, 실제 Vercel 후보의 READY·상태 API 검증과 구분한다. 이후 변경은 별도 Datadog 수신 서버와 문서이며, 수신 서버 집중 검사 10개·전체 JavaScript 293개가 통과했고 수신 서버 배포 후 실제 운영 로그가 도착했다.

## 복구 절차 확인

격리 PostgreSQL에서 전환 실패 롤백을 연습했다. 원자적 실패 시 롤백되고, 호환되는 `PAUSED`/OFF 조합은 성공했으며, stale manifest hash는 거절됐다. 리허설 종료 시 참가자 1명, 재고 80, 원장 1건이 보존됐다. 증거는 `.local/final-launch/rollback-postgres-result.json` 및 `rollback-postgres.log`에 보관했다. 실제 Vercel 별칭 전환 실패를 이 리허설로 검증한 것은 아니며, 그 실패 경로는 미검증이다.

## 삭제·공개·부하 현황

- 베타 초기화 도구와 runbook은 준비했지만, 원격 베타 데이터를 삭제하지 않았다. 쓰기 차단·최종 백업·계획 토큰 대조 후 공개 절차의 최종 단계에서만 실행한다.
- 친근 공개 URL은 기존 Preview 배포를 계속 가리킨다. Production 후보의 고유 URL은 접근 가능하지만 친근 공개 별칭으로 승격하지 않았고 `event_enabled=false`다.
- 최종 원격 부하·cohort 준비·대량 요청은 사용자 지시대로 계속 보류했다. 새 버전의 용량·p95·동시성 합격을 주장하지 않는다.

## 남은 공개 게이트

1. 운영 관리자 로그인은 확인 완료. 공개 별칭 전환 후 정식 주소에서 접속 경로 확인.
2. 실제 모바일 확대·안전 영역·키보드와 수령용 나에게 보내기→접수 완료 확인.
3. Datadog 베타 테스트 메일의 수신은 확인 완료. 공개 시점 운영 모니터·수신처 재대조와 공백 모니터 활성화, 친근 공개 도메인에서의 GA4 동의·전송 cutover 검증.
4. 혜택·브랜드·공개 승인, 링크, 물리 기기 QA, 롤백 리허설, 공개 시점 재고 수량·정책 대조. 실제 구매는 확정 정책대로 당첨자 연락처 취합 후 진행.
5. 보류 중인 최종 부하 게이트의 재개 여부와 한계를 사용자가 정하고 manifest에 실제 증거 또는 명시적 한계 수용 기록을 남김.
6. `config/phase3-launch.json`과 `server/production-launch-manifest.json`의 최종 승인 기록·SHA-256·DB guard 일치. 최종 ON·OFF 후보를 같은 코드로 고정하고 활성화 직전 새 전환 계획을 생성.
7. 후속 변경까지 draft PR에 반영하고, 최종 활성 설정을 만들 때 해당 커밋·배포·manifest 해시를 다시 연결.

위 게이트가 남아 있으므로 현재 상태는 **준비 진행 중**이며 **공개 완료**가 아니다.

## 관리자 비밀번호 설정 보완

사용자가 별도 관리자 비밀번호를 정한 적이 없거나 기억하지 못한다고 답했다. 관리자 화면에 이메일로 설정 링크를 요청하는 버튼과 복구 전용 새 비밀번호 입력 화면을 추가하고 최신 Production 후보에 반영했다. 복구 토큰은 주소에서 제거하고 관리자 역할이 확인되기 전에 지속 저장하지 않으며, 비밀번호 변경은 관리자 역할 확인을 통과해야 요청한다. 후보·정식 주소의 정확한 `/admin.html` redirect는 사용자 승인 후 Supabase URL Configuration에 등록했고 Site URL은 변경하지 않았다.

사용자가 직접 비밀번호를 설정하고 관리자 화면 진입을 확인했다. 이어 브라우저에서 `admin-app` 표시·로그인 폼 숨김, 통계·수령·행사·장애·랭킹에 부여된 권한, `환경 production`과 캠페인 `PAUSED`를 확인했다. 비밀번호·접근 토큰을 읽거나 문서에 기록하지 않았다. 전체 JavaScript 293개와 Python 340건 중 338건이 통과했고 Python 2건은 조건부 생략이다.
