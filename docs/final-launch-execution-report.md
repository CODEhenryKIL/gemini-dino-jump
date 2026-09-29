# 공룡 점프 최종 오픈 실행 기록

- 작성일: 2026-09-29
- 실행 계획: [최종 오픈 실행 계획](final-launch-execution-plan.md)
- 실행 브랜치: `codex/final-launch-preflight`
- 현재 상태: **운영 DB·비공개 Production 후보·관측 경로 준비 중. 공개 전환, 베타 삭제, 최종 원격 부하는 실행하지 않음.**

## 확인한 운영 준비 상태

| 항목 | 확인 결과 | 남은 게이트 |
| --- | --- | --- |
| Supabase 운영 구역 | 기존 프로젝트 `igfrnexknwtiljdqjrbp`에 `dino_prod` 32개 테이블·12개 schema version과 `dino_prod_app` LOGIN 역할 생성. 역할은 비밀번호 유효기간과 최소 권한을 확인했고 `public`·`dino_dev` 테이블 접근은 0건 | 최종 배포의 manifest SHA·DB guard·역할을 공개 직전 다시 대조 |
| 운영 재고 | 복주머니 5,000자리 = 실제 상품 77 + 혜택 4,923. 별도 랭킹 경품 3개를 포함한 재고 80개. 참가자·게임·추첨·수령 기록은 모두 0건 | 실제 구매·발송 증빙과 공개 시점 재고 재대조 |
| 운영 캠페인 | `gemini_dino_campus_2026`, `PAUSED`, `event_enabled=false`, `test_seed=false` | 모든 공개 증거·승인 완료 후에만 `APPROVED`/이벤트 ON 검토 |
| 베타 백업 | 2026-09-29 15:58:54 KST 기준 32개 테이블을 비공개 보관. 격리 로컬 PostgreSQL 복원에서 전체 행·제약·identity sequence 일치 | 베타는 계속 쓰기 가능하므로 삭제 직전 쓰기 차단 후 최종 백업 재생성 |
| 운영 관리자 | `sea42471@naver.com`을 기존 인증 완료 Auth 계정에 최소 업무 권한으로 등록. 사용자 ID는 공개 기록에 남기지 않음 | 비밀번호 분실로 실제 로그인은 미확인. 복구 UI 보완 후 실제 로그인·권한 확인 |

`dino_prod` 적재 요약은 `.local/final-launch/production-provision-manifest.json`과 `provision-export.log`, 런타임 guard 요약은 `production-runtime-check.log`, 베타 복원 결과는 `backup-restore.log`에 보관했다. 이 파일들과 원본 백업·접속 자격증명은 `.local/`에 있으며 Git·공개 배포에 포함하지 않는다. 이 문서에는 비밀값·사용자 ID·참가자 식별자·수령 정보를 옮기지 않았다.

## 비공개 Production 후보 검증

- 후보 배포 `dpl_B2yiyqfbieA6NY7uWuvadQ7fH2xm`은 READY이며, 비공개 고유 주소 `https://dino-nanobanana-ipjw1lnmh-henry-kils-projects.vercel.app`에서만 확인했다.
- `/api/health`는 HTTP 200, `environment=production`, `database=ready`, `schema=dino_prod`, `synthetic_only=false`, `test_seed=false`, `campaign_status=PAUSED`, 남은 재고 80을 반환했다.
- `/api/config`는 운영 캠페인·게임 버전·GA4 운영 속성·정확한 허용 origin과 `event_enabled=false`를 반환했다. 비밀값은 응답에 없었다.
- 새 참가자, 게임, 추첨 POST는 모두 HTTP 409 `EVENT_NOT_ENABLED`로 거절됐고 미인증 관리자 API는 HTTP 401 `ADMIN_AUTH_REQUIRED`로 거절됐다. 결과는 `.local/final-launch/candidate-health.json`, `candidate-config.json`, `candidate-denied-writes.json`에 보관했다.
- 친근 공개 별칭 `google-korea-team-gemini.vercel.app`과 기존 Production 주소 `dino-nanobanana.vercel.app`는 이전 배포를 계속 가리킨다. 후보 생성 중 자동으로 변경된 보조 프로젝트 별칭은 이전 대상으로 명시적 복구했다. 이 후보를 공개 별칭으로 승격하지 않았다.

## 관측 준비

- Production 전용 Vercel 로그 드레인 `drn_bzjpXu6NoqXGx75u`를 생성하고 검증 요청 HTTP 200을 확인했다. 소스는 Lambda, 환경은 Production, 프로젝트와 캠페인은 허용 목록으로 제한한다.
- Production Datadog 대시보드·모니터·수신자 검증은 진행 중이며 완료로 기록하지 않는다.
- GA4는 운영 전용 속성과 운영 origin으로 분리됐고 debug mode는 OFF다. 실제 사용자 동의·철회·전송은 공개 전 운영 후보에서 다시 확인한다.

## 코드·회귀 검증

| 검사 | 결과 | 증거·한계 |
| --- | --- | --- |
| JavaScript 전체 | 288 통과, 실패 0 | `.local/final-launch/node-regressions.log` |
| Python 전체 | 339건 실행, 337 통과, 조건부 2 생략, 실패 0 | `.local/final-launch/python-combined-summary.log` |
| Production guard 집중 검사 | 39 통과 | manifest·역할·DB guard·GA4 운영 분리 |
| 베타 초기화 집중 검사 | 11 통과 | 현재 도구의 direct/MCP 동일 범위, 권한 회수·잠금·지연 쓰기·교차 캠페인 보존 |
| 5,000자리 전량 소진 증명 | 1 통과 | 격리 로컬 DB에서 5,000건 중복 0, 상품 77, 혜택 4,923, 추가 추첨 `DRAW_POOL_EXHAUSTED`; `.local/final-launch/local-pool-result.json` |

전체 회귀 결과는 현재 진행 중인 관리자 비밀번호 복구 UI 변경 전 실행이다. 복구 UI 변경을 반영한 뒤 영향받는 관리자·인증 검사와 최종 전체 회귀를 다시 실행한다. 지정 소스와 추적·미추적 파일을 포함한 독립 검토에서 P0는 발견하지 않았다. 필수 미추적 런타임 파일은 최종 커밋에 포함하고 clean checkout에서 재검증한다.

## 삭제·공개·부하 현황

- 베타 초기화 도구와 runbook은 준비했지만, 원격 베타 데이터를 삭제하지 않았다. 쓰기 차단·최종 백업·계획 토큰 대조 후 공개 절차의 최종 단계에서만 실행한다.
- 공개 URL은 기존 Preview 배포를 계속 가리키며, 비공개 Production 후보를 공개하지 않았다.
- 최종 원격 부하·cohort 준비·대량 요청은 사용자 지시대로 계속 보류했다. 새 버전의 용량·p95·동시성 합격을 주장하지 않는다.

## 남은 공개 게이트

1. 관리자 비밀번호 복구 UI 반영 후 실제 로그인·최소 권한 확인.
2. 실제 모바일 확대·안전 영역·키보드와 수령용 나에게 보내기→접수 완료 확인.
3. Production Datadog 모니터·대시보드·실제 알림 수신, GA4 동의 흐름, 복구 경로 검증.
4. 혜택·브랜드·공개 승인, 링크, 물리 기기 QA, 롤백 리허설, 재고 구매·발송 대조.
5. 보류 중인 최종 부하 게이트의 재개 여부와 한계를 사용자가 정하고 manifest에 실제 증거 또는 명시적 한계 수용 기록을 남김.
6. `config/phase3-launch.json`과 `server/production-launch-manifest.json`의 최종 승인 기록·SHA-256·DB guard 일치 확인.
7. 트래킹된 변경과 필수 미추적 소스를 하나의 릴리스 커밋에 포함하고 clean checkout에서 최종 회귀·빌드 확인.

위 게이트가 남아 있으므로 현재 상태는 **준비 진행 중**이며 **공개 완료**가 아니다.

## 관리자 비밀번호 설정 보완

사용자가 별도 관리자 비밀번호를 정한 적이 없거나 기억하지 못한다고 답했다. 관리자 화면에 이메일로 설정 링크를 요청하는 버튼과 복구 전용 새 비밀번호 입력 화면을 추가했다. 비밀번호는 사용자가 직접 입력하며, 실제 관리자 역할 확인 전에는 새 비밀번호 폼을 활성화하지 않는다. 복구 토큰은 주소에서 제거하고 관리자 검증 전 저장하지 않는다. 관련 프론트 검사 35개, 전체 프론트 292개 통과. 이메일 링크의 정확한 허용 주소와 새 후보 배포를 준비 중이며 실제 이메일 수신·비밀번호 설정·관리자 로그인은 아직 미확인이다.
