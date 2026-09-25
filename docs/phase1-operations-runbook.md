# Phase 1 운영 런북

구현 기준일: 2026-09-23. 상태 안내 갱신: 2026-09-25.

**현재 새 1차 지시서 대기 중이며 복구는 미실행이다.** 이 문서는 기존 구현의 실행 절차를 보관한다. 연결·seed·배포를 자동 재개하지 않는다. 실제 완료 여부와 변경 이력은 [준비 상태 보고서](phase1-readiness-report.md)를 확인한다.

## 1. 환경과 범위

| 환경 | 대상 | 데이터 |
|---|---|---|
| local/test | loopback PostgreSQL 17, ref `local` | 합성 참가자·테스트 경품 |
| preview | Vercel `dino-nanobanana`, Supabase `igfrnexknwtiljdqjrbp` | 합성 참가자·테스트 경품 |
| production | 이번 작업에서 구성하지 않음 | 별도 환경·정책 승인 필요 |

기존 Supabase 프로젝트를 개발/Preview로 재사용하도록 사용자가 승인했다. Supabase 대시보드의 기본 브랜치는 `main / PRODUCTION`으로 표시되지만, 공룡 점프 실운영 환경으로 승인한 것은 아니다. 다른 앱이 현재 운영되지 않는다는 사용자 확인에 따라 기존 자료를 보존하며 `dino` 스키마를 추가한다. 실운영 전에는 개발 데이터와 분리된 환경을 정한다.

기존 public 데이터·Storage 객체·Auth 사용자를 보존한다. Auth 검증용 합성 계정 2개를 추가했으며 기존 3개와 구분한다. Auth provider, 전역 URL, exposed schema, 기존 테이블 권한은 변경하지 않는다. Figma 문서는 작업 대상에서 제외한다.

## 2. 연결과 비밀 설정

Vercel Function은 psycopg의 짧은 연결로 Supabase transaction pooler에 접속한다. 기존 Python을 유지하면서 티켓·재고·수령을 SQL transaction으로 함께 확정하기 위해 선택했다.

- 원격 포트 6543, 역할 `dino_app.<PROJECT_REF>`
- 관측한 서울 pooler: `aws-1-ap-northeast-2.pooler.supabase.com`
- prepared statements 비활성화, 프로세스당 동시 DB 연결 2개
- 연결 대기 3초, 연결 설정 5초, transaction 쿼리 5초·잠금 2초·idle 10초 제한
- 원격 TLS 인증서·호스트 검증 사용
- 요청마다 schema version과 환경·ref·합성 데이터 guard 확인
- DB 장애·설정 불일치는 503; 대체 저장소나 가짜 성공 없음

프로세스당 제한은 프로젝트 전체 연결 수를 보장하지 않는다. 실제 pooler 연결·잠금은 원격 부하 테스트에서 확인한다. [Supabase 연결](https://supabase.com/docs/guides/database/connecting-to-postgres), [psycopg prepared statements](https://www.psycopg.org/psycopg3/docs/advanced/prepare.html).

| 변수 | 규칙 |
|---|---|
| APP_ENV | local/test/preview; Vercel 환경과 일치 |
| DATABASE_URL | 전용 역할의 로컬 또는 transaction pooler URL |
| SUPABASE_PROJECT_REF | local 또는 승인된 Preview ref |
| SUPABASE_URL | 해당 프로젝트 Auth URL |
| SUPABASE_PUBLISHABLE_KEY | publishable 또는 legacy anon; service-role 금지 |
| SESSION_TOKEN_PEPPER | 독립 난수 32자 이상, 서버 전용 |
| APP_BASE_URL | 로컬 origin; Preview는 생략 시 VERCEL_URL 사용 |
| GEMINI_BENEFIT_URL | 승인된 외부 혜택 URL; 추적 파라미터 추가 안 함 |
| ALLOWED_ORIGINS | 필요한 정확한 origin만 쉼표로 구분 |
| WEB_ANALYTICS_ENABLED | Preview 수집 연결 시 true, 로컬 false |
| PORT | 로컬 기본 3000 |

`.env.example`에는 형식만 남긴다. 비밀번호·토큰·pepper를 Git·채팅·URL query·로그에 넣지 않는다. Vercel Preview scope로만 설정하며 민감값은 CLI 인자 대신 stdin으로 전달한다. `vercel env add NAME preview --sensitive` 사용 전 현재 `--help`를 확인한다. Supabase service-role 키는 합성 계정 준비에만 사용하고 게임 서버에 등록하지 않는다.

## 3. Migration·seed·계정

원격 초기 migration `20260923043028_phase1_operating_foundation.sql`은 이미 적용됐다. SHA256: `98e3f9e6420d4f21d044e4589b2b7a233a4e1b29444aa9c7cca6e905b4584ea4`. 파일명은 Supabase MCP가 기록한 실제 migration version에 맞췄다. DB의 앱 계약 schema_version은 원래 값 `20260923033611`을 유지한다. 인덱스 추가 migration `20260923045244_phase1_query_indexes.sql`도 원격 적용했다. 재적용하거나 내용을 수정하지 않는다. 추가 변경은 `supabase migration new <name>`으로 만든 새 migration에서 수행한다.

새 개발 DB 준비 순서:

1. 관리 연결로 migration을 시간순 적용한다.
2. environment_guard를 한 번 삽입한다. 기존 행을 덮어쓰지 않는다.
3. local/test는 `supabase/seed.sql`, 정확한 승인 Preview는 `supabase/preview_seed.sql`을 실행한다.
4. 승인된 전용 역할 LOGIN과 강한 비밀번호를 설정하고 서버용 비밀 설정에 저장한다.
5. 전용 계정 업무 접근과 설정·관리자 membership 변경 거부를 확인한다.

사용자의 명시적 승인 후 전용 계정 LOGIN·비밀번호 설정, Preview guard·seed·5,000명 합성 데이터 준비 및 실제 pooler 접속을 완료했다. 아래 SQL과 seed 절차는 신규 환경용 예시이며, 기존 연결 대상에 중복 실행하지 않는다. 현재는 새 지시서를 기다리며 기존 자원을 복구하거나 재설정하지 않았다.

```sql
-- Preview에서만 실행. local/test는 환경값과 ref를 각각 local로 변경.
insert into dino.environment_guard
  (singleton, environment, project_ref, synthetic_only, seeded)
values (true, 'preview', 'igfrnexknwtiljdqjrbp', true, false);
```

두 seed 모두 guard를 검사하고 하나의 transaction으로 실행한다. 테스트값: 게임권 3장, 추천 1장·일 2회·누적 5회, 수령 기한 3일, 커피 재고 20개·배송 재고 5개, 미당첨 확률 75%. 운영 정책으로 확정한 값이 아니다. 실제 경품은 DB 제약으로 비활성화되어 있다.

## 4. 로컬 실행

Supabase CLI + Docker를 우선한다. 이번 컴퓨터에는 Docker가 없어 PostgreSQL 17.6을 loopback에서 실행했다. native PostgreSQL 검사는 실제 Supabase Auth E2E의 증거가 아니다.

Supabase CLI에서는 `supabase start` 후 migration 상태를 확인하고 누락분만 적용한다. 자동 seed는 config.toml에서 꺼져 있으므로 local guard → local seed를 별도로 적용한다. linked 원격 DB에서 `db reset`을 실행하지 않는다.

README에 따라 `.venv`, `.env.local`을 준비한 후 `./run.sh` 또는 `.venv/bin/python scripts/run_local.py`로 시작한다. runner는 NAME=value를 문자 그대로 읽고 local/test만 허용한다. shell에 이미 있는 환경변수가 우선하므로 이전 원격 설정을 그대로 사용하지 않는다.

```bash
curl -fsS http://127.0.0.1:3000/api/config
curl -fsS http://127.0.0.1:3000/api/health
curl -fsS http://127.0.0.1:3000/api/campaign
```

Supabase 로컬 DB 기본 포트는 54322다. 이번 통합 테스트 DB는 `127.0.0.1:55432/dino_operations_test`이며 fixture를 정리하므로 실제 작업 데이터와 공유하지 않는다.

## 5. 관리자와 지표

`/admin.html`에서 Supabase Auth로 로그인한다. 서버는 `/auth/v1/user`로 확인한 사용자 UUID와 활성 `dino.admin_member`를 모두 검사한다. 로그인 성공이나 user_metadata만으로 관리자 권한을 부여하지 않는다.

- 확인된 Auth UUID의 membership 추가는 관리 작업이다. 게임 서버 계정에는 쓰기 권한이 없다.
- 비밀번호는 저장하지 않고 access token은 현재 탭 sessionStorage에 보관한다.
- Preview에서는 합성 데이터 포함을 선택해 테스트 숫자를 본다. Production 집계는 합성 데이터를 제외한다.
- 행사 변경·티켓 보정은 담당자·시각·대상·전후 값·사유를 감사 기록에 남긴다.
- 수령 개인정보는 별도 테이블에 저장하며 현재 관리자 화면에 출력하지 않는다.

| 지표 | 의미 |
|---|---|
| 참가자 | 기간 중 생성된 익명 ID 수; 실제 사람 수와 다름 |
| 화면 조회 | SPA 논리 화면 page_view |
| 활성 체류 | 화면이 보이는 동안 수집한 시간; 마지막 전송 유실 가능 |
| 추정 이탈 | 기간 중 참가자의 마지막 관측 page_view 화면 |
| 공유창 열림 | 실제 공유 완료와 다름 |
| Gemini 클릭 | 외부 가입·학생 인증 완료와 다름 |
| 퍼널 | 기간별 발생 건수; 같은 참가자 코호트 전환율은 아님 |
| 수령 비율 | 당첨 건수(wins)를 분모로 사용 |
| 재고 | 조회 시점의 경품별 상태; 기간 이벤트 수와 구분 |

DB 시각은 UTC, 조회 날짜와 화면은 Asia/Seoul을 사용한다. 정상 충돌은 오류가 아니다. 서버 확정 이벤트와 클라이언트 클릭을 구분하고 event_id 중복을 제거한다.

Vercel Web Analytics는 2026-09-23 사용자 추가 승인을 받아 프로젝트에서 켰다. 자동 pageview를 끄고 allowlist 논리 화면만 수동 전송한다. 초대 코드·query·hash·referrer·개인정보·게임 토큰을 전달하지 않는다. 실제 수집은 Preview 배포 후 확인한다. Plus 추가 기능은 켜지 않았다. 승인 당시 Pro 사용량 가격은 1,000건당 $0.03이며 청구·크레딧은 실제 사용량에 따른다. [공식 가격](https://vercel.com/docs/analytics/limits-and-pricing).

## 6. 테스트와 Preview 배포

마지막 Preview 배포는 Python 3.11 인터프리터를 찾지 못해 빌드 실패했다. 현재 `.python-version`은 여전히 3.11이다. 아래 절차는 배포 성공 기록이 아니며, 재개 시 새 지시서와 지원 런타임을 확인해야 한다.

```bash
.venv/bin/python test_suite.py
node --test tests/dino_only.test.cjs tests/frontend_phase1.test.cjs
.venv/bin/python -m compileall -q api server scripts tests
git diff --check
```

전체 Python 검사는 로컬 PostgreSQL과 임시 loopback HTTP 서버가 필요하다. socket sandbox 차단을 코드 오류와 구분한다. 업무 단위 검사에 검증 결과를 주입한 fixture는 실제 플레이 검증의 증거가 아니다. 물리 회귀 및 실제 HTTP/브라우저 E2E 결과를 따로 기록한다.

배포 전 migration/guard/seed, 전용 pooler 접속, 기존 자료 보존, Preview 환경변수, 실제 경품 비활성, 비밀값 제외를 확인한다. `vercel deploy --dry --json`은 업로드 대상 검사이고 배포 성공 증거가 아니다.

승인된 배포는 Preview뿐이다. `vercel deploy --target=preview`로 만들고 URL·deployment ID·commit·build log를 기록한다. Git 연결은 현재 없으므로 branch push만으로 배포됐다고 가정하지 않는다. 배포 후 config/health/campaign이 preview·정확한 ref·synthetic_only=true·is_test=true·real_prizes_enabled=false인지 확인한다.

브라우저에서 게임 → 유효 종료 → 추첨 → 합성 수령 → 관리자 지표와 재전송·새로고침·권한 거부를 확인한다. 화면 크기 에뮬레이션과 실제 휴대폰 결과는 구분한다.

## 7. 부하 테스트

```bash
.venv/bin/python scripts/phase1_load.py --profile full --dry-run
```

실행 전 최신 dry-run에서 모든 반복을 포함한 API·변경 요청·이벤트 예상량을 검토한다. 토큰 파일은 5,000개 고유 합성 token과 정확한 preview ref를 포함하며 권한 0600으로 Git 밖에 보관한다. 보고서에는 token·쿠폰·개인정보를 넣지 않는다.

```bash
.venv/bin/python scripts/phase1_load.py --mode remote --base-url https://<PREVIEW_HOST> --profile full --tokens <PRIVATE_COHORT_JSON> --ledger <PRIVATE_CUMULATIVE_LEDGER_JSON> --report <PRIVATE_REPORT_JSON> --expected-project-ref igfrnexknwtiljdqjrbp
```

- 10 VU 60초 → 50 VU 120초 → 100 VU 180초 → 200 VU 300초 → 별도 200 VU burst 30초
- 실제 simulator 충돌 기록과 플레이 대기를 거쳐 정상 API로 종료·추첨·일부 수령
- 전체 누적 30,000 API 호출·30분, 실행 간 같은 budget ledger와 token cursor 유지
- 심각한 권한·정합성·서버 오류는 즉시 중단; 무제한 재실행·유료 도구·자동 증설 금지
- API별 p50/p95/p99·실제 RPS·상태·timeout·실패율·단계 수치·함수/DB/잠금·중복 지급/과배정 기록
- 목표: 일반 p95≤1초, finish/draw p95≤2초, 예상하지 않은 실패<1%, 중복 지급·과배정 0

기본 대기는 45초다. full 예상 흐름 상한 2,170회, 필요 token 2,172개, 스크립트 구조상 API 17,801회, 안전여유 상한 23,877회다. 변경 API 요청 상한 15,626회, client event 2,170개, server domain event 시도 6,727개다. 이는 실제 DB 행 쓰기 수나 요금 확정값이 아니다. 5,000명 초기 fixture는 별도로 참가자·초기 티켓·page_view 각 5,000개를 만든다.

200 VU는 200 requests/second가 아니다. API 부하는 FPS 검사가 아니다. 순수 HTTP 부하 도구는 외부 Analytics script를 실행하지 않지만 내부 이벤트 쓰기는 포함한다. 클라우드 사용량이 무료라고 보장하지 않는다.

## 8. 로그·장애·복구

1. health의 환경·DB 상태·ref를 확인한다. 503을 성공으로 바꾸지 않는다.
2. Vercel 로그에서 request_id·HTTP status·duration_ms를 확인한다. CLI 옵션은 현재 `vercel logs --help`를 따른다.
3. Supabase 연결·lock wait·느린 쿼리를 확인한다. 보고서에는 정규화한 집계만 기록한다.
4. 환경변수 scope, guard/schema, campaign 상태, pooler 설정을 확인한다.
5. 복구 후 같은 세션과 같은 Idempotency-Key로 재시도해 DB의 확정 결과를 반환하는지 확인한다. request_id는 로그 대조에 사용한다.

게임 프레임·점프마다 네트워크를 호출하지 않는다. 저장 대기 payload는 보존하고 재방문 시 먼저 복구한다. 그 뒤 남은 ACTIVE 세션은 종료 안내 후 정리한다. 시작한 게임권은 자동 환불하지 않는다.

## 9. 백업과 롤백

2026-09-23 대시보드에서 9월 16~22일 물리 백업 7개를 확인했다. 최신 표시 시각은 `2026-09-22 21:53:51 UTC` (`2026-09-23 06:53:51 KST`)다. 백업 목록 확인은 복원 시험 성공을 의미하지 않는다.

- 앱 롤백: 이전 정상 commit으로 새 Preview를 만든다. DB는 자동 복구되지 않는다.
- DB 수정: 새 migration으로 전진 수정한다. 적용 파일 수정이나 공유 원격 DB 초기화는 하지 않는다.
- 논리 백업: 관리 연결로 `pg_dump --schema=dino --format=custom --no-owner --no-acl`을 실행하고 접근 제한 파일로 보관한다. 복원 시험은 별도 로컬 DB에서 한다.
- 전체 프로젝트 복원은 기존 public/auth에도 영향을 주고 중단이 발생하므로 별도 승인 대상이다.
- DB 백업에는 Storage 파일 본문이 포함되지 않는다. 별도 보관·복원 절차가 필요하다.
- 일일 백업은 custom role 비밀번호를 보관하지 않으므로 복원 후 안전하게 재설정하고 서버 비밀 설정을 갱신한다.
- 새 유료 PITR·복제 프로젝트는 생성하지 않는다.

[백업 대시보드](https://supabase.com/dashboard/project/igfrnexknwtiljdqjrbp/database/backups/scheduled), [Supabase 백업·복구](https://supabase.com/docs/guides/platform/backups).
