# 공룡 점프 최종 오픈 실행 기록

- 작성일: 2026-09-29
- 실행 계획: [최종 오픈 실행 계획](final-launch-execution-plan.md)
- 실행 브랜치: `codex/final-launch-preflight`
- 현재 상태: **운영 DB·Production 후보·관측 경로 준비 중. 후보 고유 URL은 외부에서 열리지만 친근 공개 별칭으로 승격하지 않았고 이벤트는 OFF. 공개 전환, 베타 삭제, 최종 원격 부하는 실행하지 않음.**

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

- 최신 후보 배포 `dpl_94Yqtt6yTqrELm6Rp9JGdwdeNVv7`은 READY이며, 고유 주소 `https://dino-nanobanana-aqf4cht0m-henry-kils-projects.vercel.app`에서 관리자 복구 UI와 `event_enabled=false`를 확인했다. 고유 URL은 외부에서 접근 가능하며 친근 공개 별칭으로는 승격하지 않았다. 요약은 `.local/final-launch/admin-recovery-candidate.json`에 보관했다.
- `/api/health`는 HTTP 200, `environment=production`, `database=ready`, `schema=dino_prod`, `synthetic_only=false`, `test_seed=false`, `campaign_status=PAUSED`, 남은 재고 80을 반환했다.
- `/api/config`는 운영 캠페인·게임 버전·GA4 운영 속성·정확한 허용 origin과 `event_enabled=false`를 반환했다. 비밀값은 응답에 없었다.
- 새 참가자, 게임, 추첨 POST는 모두 HTTP 409 `EVENT_NOT_ENABLED`로 거절됐고 미인증 관리자 API는 HTTP 401 `ADMIN_AUTH_REQUIRED`로 거절됐다. 이 쓰기 차단 증거는 이전 Production 후보에서 수집했으며 `.local/final-launch/candidate-health.json`, `candidate-config.json`, `candidate-denied-writes.json`에 보관했다. 최신 후보도 같은 DB guard와 이벤트 OFF 설정을 사용한다.
- 친근 공개 별칭 `google-korea-team-gemini.vercel.app`과 기존 Production 주소 `dino-nanobanana.vercel.app`는 이전 배포를 계속 가리킨다. 후보 생성 중 자동으로 변경된 보조 프로젝트 별칭은 이전 대상으로 명시적 복구했다. 이 후보를 공개 별칭으로 승격하지 않았다.

## 관측 준비

- Production 전용 Vercel 로그 드레인 `drn_bzjpXu6NoqXGx75u`를 생성하고 검증 요청 HTTP 200을 확인했다. 소스는 Lambda, 환경은 Production, 프로젝트와 캠페인은 허용 목록으로 제한한다.
- Production 오류 모니터 `22788890`은 `env:production`으로 활성화했다. 수집 공백 모니터 `22788937`은 현재 공개 heartbeat가 베타를 가리키므로 공개 전환 전까지 DRAFT로 두었다. Production 대시보드 `a27-779-mch` 내보내기에서 위젯 5개, 질의 5개 모두 `env:production`, Preview 질의 0개를 확인했다.
- 수신 호환성 보완은 `dpl_ELKJ4CvrHAg3g8LF5j1Wx1EghxpA`로 READY 배포했다. Datadog Logs Explorer에서 Production 로그 2건을 확인했다. 최신 표본은 2026-09-29 16:51:25.116 KST의 `env=production`, `campaign=gemini_dino_campus_2026`, `version=dpl_94Yqtt6yTqrELm6Rp9JGdwdeNVv7`, `GET /api/health`, HTTP 200, `duration_ms=54`, `error_class=none`이다. 16:48:31.856 KST의 보완 전 로그도 늦게 도착했으므로, 이 보완이 문제의 유일한 원인 해결이었다고 주장하지 않는다. 실제 알림 이메일 수신은 아직 미확인이다.
- GA4는 운영 전용 속성과 운영 origin으로 분리됐고 debug mode는 OFF다. 실제 사용자 동의·철회·전송은 공개 전 운영 후보에서 다시 확인한다.

## 코드·회귀 검증

| 검사 | 결과 | 증거·한계 |
| --- | --- | --- |
| JavaScript 전체 | 293 통과, 실패 0 | `.local/final-launch/node-regressions.log` |
| Python 전체 | 340건 실행, 338 통과, 조건부 2 생략, 실패 0 | `.local/final-launch/python-combined-summary.log` |
| Production guard 집중 검사 | 39 통과 | manifest·역할·DB guard·GA4 운영 분리 |
| 베타 초기화 집중 검사 | 11 통과 | 현재 도구의 direct/MCP 동일 범위, 권한 회수·잠금·지연 쓰기·교차 캠페인 보존 |
| 5,000자리 전량 소진 증명 | 1 통과 | 격리 로컬 DB에서 5,000건 중복 0, 상품 77, 혜택 4,923, 추가 추첨 `DRAW_POOL_EXHAUSTED`; `.local/final-launch/local-pool-result.json` |

전체 회귀에 관리자 비밀번호 복구 UI 변경을 포함했다. 지정 소스와 추적·미추적 파일을 포함한 독립 검토에서 P0는 발견하지 않았다. 앱 릴리스 소스는 커밋 `4edab6dd7d9edf0cc9c20df4315e728260bfbff1`로 push했고 draft PR [#9](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/9)에서 검토 중이다.

같은 커밋의 깨끗한 Git 아카이브에서 필수 런타임 파일, 정적 참조 77개, JavaScript 구문 24개, 집중 검사 48개, Python 컴파일 21개와 API handler import를 별도로 확인했다. 누락 파일은 없었다. 로컬 Python은 3.11이므로 3.12 실행 검증으로 확대하지 않으며, 실제 Vercel 후보의 READY·상태 API 검증과 구분한다. 이후 변경은 별도 Datadog 수신 서버와 문서이며, 수신 서버 집중 검사 10개·전체 JavaScript 293개가 통과했고 수신 서버 배포 후 실제 운영 로그가 도착했다.

## 복구 절차 확인

로컬 메모리 DB 대역과 임시 manifest로 별칭 전환 실패 상황을 재현했다. 실제 런타임 설정·guard 검증 함수를 사용해 ACTIVE 설정에서 호환되는 OFF/PAUSED 조합으로 복구되고, 모의 운영 기록 3건이 유지되며, 이전 ACTIVE·이전 OFF·잘못된 파일 해시는 거절되는 것을 확인했다. 증거는 `.local/final-launch/rollback-rehearsal-result.json`에 보관했다. 이는 모의 실행으로, 실제 PostgreSQL 전환 트랜잭션이나 본행사 공개 별칭 복구의 실증으로 기록하지 않는다. 후보 배포 중 이동한 보조 Vercel 별칭은 실제로 이전 배포에 복구했고 세 공개 별칭의 기존 대상을 다시 확인했다.

## 삭제·공개·부하 현황

- 베타 초기화 도구와 runbook은 준비했지만, 원격 베타 데이터를 삭제하지 않았다. 쓰기 차단·최종 백업·계획 토큰 대조 후 공개 절차의 최종 단계에서만 실행한다.
- 친근 공개 URL은 기존 Preview 배포를 계속 가리킨다. Production 후보의 고유 URL은 접근 가능하지만 친근 공개 별칭으로 승격하지 않았고 `event_enabled=false`다.
- 최종 원격 부하·cohort 준비·대량 요청은 사용자 지시대로 계속 보류했다. 새 버전의 용량·p95·동시성 합격을 주장하지 않는다.

## 남은 공개 게이트

1. 운영 관리자 로그인은 확인 완료. 공개 별칭 전환 후 정식 주소에서 접속 경로 확인.
2. 실제 모바일 확대·안전 영역·키보드와 수령용 나에게 보내기→접수 완료 확인.
3. Production Datadog 실제 알림 이메일 수신, 공개 시점 공백 모니터 활성화, GA4 동의 흐름·복구 경로 검증.
4. 혜택·브랜드·공개 승인, 링크, 물리 기기 QA, 롤백 리허설, 공개 시점 재고 수량·정책 대조. 실제 구매는 확정 정책대로 당첨자 연락처 취합 후 진행.
5. 보류 중인 최종 부하 게이트의 재개 여부와 한계를 사용자가 정하고 manifest에 실제 증거 또는 명시적 한계 수용 기록을 남김.
6. `config/phase3-launch.json`과 `server/production-launch-manifest.json`의 최종 승인 기록·SHA-256·DB guard 일치 확인.
7. 후속 변경까지 draft PR에 반영하고, 최종 활성 설정을 만들 때 해당 커밋·배포·manifest 해시를 다시 연결.

위 게이트가 남아 있으므로 현재 상태는 **준비 진행 중**이며 **공개 완료**가 아니다.

## 관리자 비밀번호 설정 보완

사용자가 별도 관리자 비밀번호를 정한 적이 없거나 기억하지 못한다고 답했다. 관리자 화면에 이메일로 설정 링크를 요청하는 버튼과 복구 전용 새 비밀번호 입력 화면을 추가하고 최신 Production 후보에 반영했다. 복구 토큰은 주소에서 제거하고 관리자 역할이 확인되기 전에 지속 저장하지 않으며, 비밀번호 변경은 관리자 역할 확인을 통과해야 요청한다. 후보·정식 주소의 정확한 `/admin.html` redirect는 사용자 승인 후 Supabase URL Configuration에 등록했고 Site URL은 변경하지 않았다.

사용자가 직접 비밀번호를 설정하고 관리자 화면 진입을 확인했다. 이어 브라우저에서 `admin-app` 표시·로그인 폼 숨김, 통계·수령·행사·장애·랭킹에 부여된 권한, `환경 production`과 캠페인 `PAUSED`를 확인했다. 비밀번호·접근 토큰을 읽거나 문서에 기록하지 않았다. 전체 JavaScript 293개와 Python 340건 중 338건이 통과했고 Python 2건은 조건부 생략이다.
