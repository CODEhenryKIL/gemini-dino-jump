# Phase 1 준비 상태 보고서

갱신: 2026-09-25 KST. 브랜치: `codex/phase1-operating-foundation` (`f57c3d1` 기반).

증거 기준: GitHub PR·브랜치와 로컬 문서는 9월 25일 재확인했다. 아래 Supabase·Vercel·브라우저 결과는 9월 23일 작업에서 마지막으로 확인한 기록이며, 9월 25일 서비스 상태를 다시 조회한 결과가 아니다.

**전체 상태: 미완료 / 새 1차 지시서 대기.** 전용 DB 연결·테스트 데이터·Preview 환경변수까지 준비했으나 Preview 빌드가 실패했다. 실제 Preview E2E와 원격 부하 테스트는 수행하지 않았으며, 200명 동시 이용 성능은 검증되지 않았다.

## 0. 최신 사용자 방향과 복구 상태

사용자는 1차 지시서를 다시 작성하고, **게이트러너 제거가 완료된 공룡 점프 상태에서 Supabase·Vercel 연결을 다시 시작**하려 한다.

- 복구 기준 코드는 `f57c3d123296202bc1ef4360c45427d7df9a33e8`이다. 현재 `main`과 PR base가 이 커밋이다.
- 로컬 작업 브랜치와 PR에는 아직 기존 Phase 1 구현이 남아 있다. **코드·Supabase·Vercel 복구는 실행하지 않았다.**
- GitHub 저장소·기존 커밋·작업 브랜치·초안 PR은 유지한다. PR은 open/draft이며 병합하지 않았다.
- Supabase·Vercel은 이전 작업에서 추가한 설정과 테스트 데이터가 있는 상태로 기록한다. 복구 완료 또는 연결 해제 완료로 간주하면 안 된다.
- 기존 프로젝트의 원래 데이터와 운영 배포를 보존하면서 Phase 1 추가분만 정리하는 방향을 논의했다. 이 문서는 삭제·배포·재연결 실행 지시가 아니다.
- 채팅 이미지의 실행 취소는 게이트러너 분리 변경까지 취소할 수 있다. 원격 서비스 설정까지 함께 되돌리는 수단으로 사용하지 않는다.

새 지시서가 확정되기 전에는 아래 기존 계획을 자동으로 재개하지 않는다.

## 1. 구현 완료

- SQLite 영구 저장과 레거시 서비스 4개를 제거하고 PostgreSQL transaction 서비스로 통합했다.
- private dino 스키마 20개 테이블, 강제 RLS, 전용 역할, 외래키·고유 제약, 티켓 원장·재고 이력·수령 개인정보 분리를 구현했다.
- 서버 잔액 게임권, 정상 시작·차감, 유효 종료만 랭킹/추천/추첨 반영, 소유권·멱등성·마지막 재고 잠금·합성 수령을 구현했다.
- Supabase Auth + 명시적 관리자 membership, 변경 감사 로그, 요청 제한·입력 경계·Origin·no-store 응답을 구현했다.
- 승인된 Preview project ref를 고정하고 미구성 Production을 거부한다. Auth 확인 대기 중에는 DB 연결을 반환한다.
- 결과 전송 재시도·저장 payload 보존, 활성 세션 정리, 미완료 추첨·수령 조회, 화면 이탈 cleanup, 오래된 비동기 응답 방어를 구현했다.
- 논리 화면 이벤트, 합성 데이터 필터, KST 집계, 당첨 기준 수령 분모, 경품별 재고와 관리자 지표를 연결했다.
- Vercel 정적 파일/API 분리, 서울 icn1, Preview 환경 예시, 배포 파일 제외 규칙을 구성했다.
- 전체 부하 프로필, 실제 simulator/플레이 대기, 누적 시간·API·토큰 원장, 심각 오류 중단, 결과 보고서를 구현했다.
- README·실행 스크립트를 PostgreSQL 구성에 맞추고 오래된 Gate Runner 전용 안내를 제거했다. Figma 문서는 수정하지 않았다.

## 2. 원격에서 확인한 사실

| 대상 | 실제 확인 |
|---|---|
| GitHub | 대상 저장소 push/admin 접근; 사용자 요청대로 public 전환 후 API 재조회 확인 |
| Vercel | active Pro, 7개 프로젝트, dino-nanobanana 대상 식별, Git 연결 없음 |
| Supabase | CODEhenryKIL's Org Pro, 프로젝트 2개, 승인된 기존 서울 프로젝트 igfrnexknwtiljdqjrbp ACTIVE |
| 초기 migration | 적용 성공; dino 테이블 20개 모두 RLS 및 FORCE RLS |
| 조회 인덱스 migration | 랭킹·READY 수령 만료·행사별 경품 인덱스 3개 적용 및 정의 조회 확인 |
| 기존 데이터 | public 11개 테이블의 기존 행 수 유지, Storage 객체 47개 유지 |
| Auth | 기존 3명 유지, 합성 테스트 계정 2개 추가 및 실제 password grant 성공 |
| DB 전용 계정 | 사용자 명시 승인 후 dino_app LOGIN·연결 한도 20 설정; 공식 CA와 verify-full로 실제 pooler 접속 성공; 기존 public 11개 테이블 SELECT/INSERT/UPDATE/DELETE 권한 없음 |
| 테스트 데이터 | Preview guard·seed 적용, 테스트 재고 25개, 합성 참가자 5,000명·초기 티켓 원장 5,000개(총 15,000장)·page_view 5,000개, 합성 관리자 membership 등록 |
| Preview 환경변수 | Preview 범위에 8개 등록 완료; 비밀값은 저장소에 포함하지 않음 |
| Preview 배포 | 1회 시도 후 Python 3.11 인터프리터를 찾지 못해 빌드 실패; READY 배포 미확인 |
| Web Analytics | 사용자 추가 승인 후 CLI 활성화 성공; 실제 Preview 수집은 아직 미검증 |
| 백업 | 대시보드의 물리 백업 7개 확인; 실제 복원 미실행 |

초기 migration 원본 SHA256: `98e3f9e6420d4f21d044e4589b2b7a233a4e1b29444aa9c7cca6e905b4584ea4`.

| 로컬 migration 파일/원격 history | 설명 |
|---|---|
| 20260923043028_phase1_operating_foundation.sql | 초기 스키마. MCP가 부여한 실제 version으로 파일명 정렬; 내용 불변 |
| 20260923045244_phase1_query_indexes.sql | 조회 인덱스 3개 |
| dino.schema_version = 20260923033611 | 앱의 스키마 계약 버전; migration 기록 시각과 별개 |

Supabase CLI `migration list --linked`에서도 로컬·원격의 위 두 version이 모두 일치했다.

기존 public 행 수: questions 33, score_results 1, analysis_jobs 2, cost_logs 45, profiles 3, question_sets 3, test_sessions 5, answers 26, transcripts 22, audio_analyses 22, feedbacks 22. 초기 migration 전후 컬럼 정의 fingerprint는 `6e5c0a823cd05c44fac1fd502b76874c`로 일치했다. 행 수·구조 비교는 각 행 내용의 전체 해시 비교를 대신하지 않는다. 이번 migration은 기존 테이블 데이터 변경문을 포함하지 않는다.

Supabase 대시보드 main의 PRODUCTION 표시는 기본 브랜치 명칭이다. 사용자가 승인한 용도는 기존 자료를 보존하는 공룡 점프 개발/Preview이며 실운영 환경 승인이 아니다.

## 3. 로컬 검증 결과

2026-09-23 현재 작업트리에서 실제 실행:

| 검사 | 결과 | 범위·한계 |
|---|---|---|
| `.venv/bin/python test_suite.py` | 29/29 PASS | PostgreSQL 17.6 및 임시 HTTP 서버 포함 |
| `node --test tests/dino_only.test.cjs tests/frontend_phase1.test.cjs` | 11/11 PASS | DOM 대역/VM·회귀 검사, 실제 브라우저 E2E와 구분 |
| Python compileall | PASS | api/server/scripts/tests 문법 |
| `bash -n run.sh` | PASS | shell 구문 |
| `git diff --check` | PASS | 공백 오류 |
| 빈 PostgreSQL migration/seed | PASS | 로컬 실제 PostgreSQL; 원격 Preview seed도 이후 별도로 적용 완료 |
| 부하 full dry-run | PASS | 예상량·안전장치, 실제 부하 결과 아님 |

최초 sandbox 실행에서는 로컬 TCP와 HTTP bind가 차단됐다. 동일 검사에 loopback 접근을 허용해 재실행한 결과가 위 PASS다. 당시 DB 업무 검사는 관리 테스트 연결의 SET ROLE로 전용 역할 권한을 검증했다. 이후 사용자 승인에 따라 전용 계정 LOGIN을 설정하고 실제 연결도 확인했다.

Python 구성: load guard 9개, 업무 transaction/권한 통합 검사 2개(다수 assertion), 물리 회귀 3개, config/Auth/HTTP 15개. 물리 fixture 12개는 기존 충돌 결과와 비교한다.

업무 통합 검사로 확인한 것:

- 시작 티켓 1회 차감, 종료 재전송 시 기존 결과, 추천 저장·보상 1회
- 타인의 세션·수령 접근 거부, 실제처럼 보이는 개인정보 제출 거부
- 동시 마지막 재고 1개 경쟁, 최대 1명 배정
- 수령 재시도·같은 쿠폰, 만료의 DB 확정, 지급 중복 방지
- 잘못된 wall-clock 종료 거부, 비관리자·설정/membership 변경 차단
- 관리자 보정 idempotency 충돌, 알려진 이벤트 중복·KST 집계 대조

주의: 업무 통합 검사의 일부 유효 게임 fixture는 verification 결과를 직접 주입한다. 이것만으로 실제 플레이 → HTTP 검증 → DB → 브라우저 전체 연결을 증명하지 않는다. 이후 로컬 브라우저에서 실제 게임 시작 → 자연 충돌 → 검증된 32점 결과 → 티켓 3장 중 1장 차감(잔액 2장)을 확인했다. 추첨·수령·관리자 화면까지의 전체 E2E와 원격 Preview E2E는 미완료다.

5천 행 로컬 EXPLAIN ANALYZE에서 랭킹 조회 2.407ms → 0.474ms, READY 수령 만료 조회 0.947ms → 0.071ms를 관측했다. 이는 해당 로컬 쿼리 측정이며 Vercel/Supabase 응답시간 보장이 아니다.

## 4. 작업 지시서별 완료 판정

| 지시서 | 구현/현재 증거 | 남은 증거 |
|---|---|---|
| 1 목표·범위 | 테스트 정책 분리·실경품 차단 | 실제 Preview 전체 흐름·원격 성능 |
| 2 연결 확인 | 계정·리전·플랜, 전용 DB 로그인, Preview env 등록 | 배포된 Preview 앱에서 연결 확인 |
| 3 Dino 전용 | 코드·정적 회귀, legacy redirect | 실제 Preview 화면/라우트 |
| 4 PostgreSQL·배포 | migration·권한·seed·pooler 실접속·공식 CA 검증 | 실패한 Preview 빌드 해결·READY/health |
| 5 정합성 | local transaction·동시성·소유권 검사 | Preview에서 유효 플레이와 재전송·재고 경쟁 |
| 6 보안·복구 | 입력/Origin/권한/장애 HTTP 검사·frontend regression | 실제 Auth→membership, 브라우저 이탈/숨김/재개·응답 유실 |
| 7 지표 | known-data 로컬 집계·admin UI·Analytics 활성화·원격 5천명 준비 | 실제 Preview 수집/관리자 표시·원격 5천명 집계 성능 |
| 8 기능·브라우저 | local DB·HTTP 경계·로컬 실제 게임 결과/티켓 차감 | 추첨·수령·관리자 전체 E2E, Preview E2E, 모바일/실제 휴대폰 |
| 9 원격 부하 | exact 프로필·안전장치·비용 영향 계산 | 원격 10/50/100/200 VU + burst, p95/실패율/DB 관측 |
| 10 산출물 | 코드·migration·seed·env·런북·보고서·커밋·초안 PR·실패 배포 기록 | 정상 Preview URL, 실제 원격 측정 보고 |
| 11 승인 제한 | Production/실경품/DNS/새 유료 프로젝트 미변경 | 종료 시 재확인 |

## 5. 승인 이력과 Preview 실패

DB 전용 계정 LOGIN 변경은 처음에 자동 승인 검사에서 차단됐다. 이후 범위와 위험을 설명했고, 사용자가 **“공룡 점프 전용 계정의 DB 접속 허용”**이라고 명시적으로 승인했다. 그 승인에 따라 전용 계정 비밀번호·LOGIN을 설정했다. 더 이상 LOGIN 승인 대기 상태가 아니다.

초기 pooler TLS 인증서 검증 실패는 공식 Supabase CA를 추가하여 해결했다. 수정 커밋은 `1834951af1b6a905789d01910ffa48ee407f688a`이며, 전용 계정으로 실제 원격 접속과 참가자 5,000명·재고 25개·page_view 5,000개 조회를 확인했다.

Preview 범위에 `APP_ENV`, `SUPABASE_PROJECT_REF`, `DATABASE_URL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, `SESSION_TOKEN_PEPPER`, `WEB_ANALYTICS_ENABLED`, `GEMINI_BENEFIT_URL`을 등록했다. Production 환경변수는 변경하지 않았다.

Preview 배포는 `.python-version`의 3.11 지정과 빌드 환경의 인터프리터 지원 불일치로 실패했다. 로그의 핵심 오류는 `No interpreter found for Python 3.11 in managed installations or search path`다. 버전 수정·재배포는 수행하지 않았다.

- [실패한 배포 기록](https://vercel.com/henry-kils-projects/dino-nanobanana/3GsE4tNgifko1J8wBD8iKQf1DGRX)
- 할당된 주소: `https://dino-nanobanana-3j22nng2u-henry-kils-projects.vercel.app` — 정상 동작하는 Preview로 전달할 수 없음
- Production 배포·DNS 변경·실경품 발송·새 유료 프로젝트 생성·main 병합은 수행하지 않음

Vercel Web Analytics는 별도 명시적 승인을 받아 켰다. 추가 Plus 구독·PITR·자동 사양 증설은 하지 않았다. 기능 활성화와 실제 수집 검증은 구분한다.

## 6. 기존 원격 부하 계획과 미측정 항목

아래는 기존 지시서의 미실행 계획이다. 새 지시서가 확정되면 범위와 한도를 다시 정한다.

full 프로필: 10 VU/60초, 50/120초, 100/180초, 200/300초, burst 200/30초. 단계 합계 690초, 정리·preflight 안전 예약 780초. 기본 대기 45초.

- flow 시도 상한 2,170회, fresh token 필요 2,172/5,000개
- API 구조상 상한 17,801회, 안전여유 포함 23,877회
- 변경 API 요청 상한 15,626회, client event 2,170개, server domain event 시도 6,727개
- 초기 5,000명 fixture는 참가자·티켓 원장·page_view 각 5,000개
- 모든 재시험과 smoke는 동일 누적 ledger의 30,000호출/30분 한도에 포함
- 도구는 추가 유료 서비스 없이 실행하지만 Vercel 함수·Supabase DB 사용량 비용은 생길 수 있음
- 위 숫자는 DB 실제 row mutation 수나 확정 청구액이 아님. 쿼리별 rate bucket·업무 쓰기와 실행 후 사용량을 함께 확인해야 함

실제 원격 측정은 **0회**다. p50/p95/p99, RPS, 실패율, timeout, 함수/DB 오류·연결·잠금·느린 쿼리, 원격 과배정/중복 지급, Analytics 추가 부하는 모두 미측정이다. 실행 지역·cold/warm 조건도 실행 시 기록해야 한다.

## 7. Advisors와 운영 한계

초기 migration 후 dino 보안 경고는 없었다. 기존 public.set_updated_at search_path, public.rls_auto_enable의 anon/authenticated SECURITY DEFINER 실행권한, Auth leaked-password protection 관련 경고는 기존 프로젝트 범위이며 임의 변경하지 않았다.

- [search_path 경고](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable)
- [anon 실행권한 경고](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable)
- [authenticated 실행권한 경고](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable)
- [비밀번호 보호](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)

FK index INFO는 기존 UNIQUE/선두 인덱스 및 실제 조회 경로로 검토했다. 랭킹·만료·행사 경품에 필요한 3개만 추가했다. 나머지 append-only/불변 관계와 기존 선두 인덱스로 지원되는 관계는 쓰기 비용을 고려해 추가하지 않았으며, 앞으로 삭제·역방향 조회 기능이 생기면 재검토한다. [FK index advisor](https://supabase.com/docs/guides/database/database-linter?lint=0001_unindexed_foreign_keys).

실제 휴대폰의 조작/FPS와 모바일 에뮬레이션, Supabase 전체 복원 시험은 아직 미검증이다. DB 연결 한도는 프로세스별이며 분산 인스턴스 전체 상한은 원격 관측이 필요하다. 게임 검증 입력은 10분/36,000tick·최대 2,048점프로 제한되어 있어 장시간 게임 운영 정책은 실운영 전 확인한다.

## 8. 후속 운영 정책

기본 티켓, 추천 보상·일/누적 제한, 경품 확률·수량, 랭킹 경품·마감, 학생 인증, Gemini 가입 확인, 개인정보 보존/파기 기간, 장시간 게임 제한, 실경품 공급자를 별도로 확정한다. 현재 합성 쿠폰은 TEST_ISSUED이며 실제 지급 완료로 집계하지 않는다.

## 9. 전달 상태

- 저장소: https://github.com/CODEhenryKIL/gemini-dino-jump
- 작업 브랜치: codex/phase1-operating-foundation
- 구현 commit: `0b3ccd03de87671157bb2707eba911095a9ecf0c`
- 초안 PR: https://github.com/CODEhenryKIL/gemini-dino-jump/pull/1 (병합 안 함)
- 마지막 구현 커밋: `1834951af1b6a905789d01910ffa48ee407f688a` (공식 CA 추가)
- Preview deployment: 1회 빌드 실패; 정상 서비스 URL 없음
- 원격 실행 보고서: 아직 없음
- 실행·관리자·백업·복구: [운영 런북](phase1-operations-runbook.md)

## 10. 추후 복구 시 확인할 범위 — 아직 미실행

| 대상 | Phase 1 추가분 / 확인할 항목 |
|---|---|
| 로컬 코드 | `f57c3d1` 이후 구현과 로컬 전용 설정·테스트 DB·실행 프로세스. 신규 사용자 변경 확인 후 복구 범위 결정 |
| Supabase | `dino` 스키마 20개 테이블·테스트 데이터·guard·관리자 membership, 전용 `dino_app` 역할, 이번 합성 Auth 계정 2개, migration 이력 2건 |
| Vercel | Preview 환경변수 8개, Web Analytics 활성화, 실패한 Preview 배포 기록 |
| 보존할 것 | 기존 public 11개 테이블·원래 Auth 사용자·Storage, 기존 Production 배포·환경변수, GitHub 저장소·커밋·PR |

삭제 전에 실제 의존성과 그 이후 추가된 데이터를 확인해야 한다. 프로젝트 전체 초기화나 백업 전체 복원은 이 범위를 넘어선다. 아직 연결 정보와 테스트 데이터가 남아 있으므로 기존 migration·seed를 처음부터 재실행하지 않는다.
