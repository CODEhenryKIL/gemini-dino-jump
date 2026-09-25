# 1차 환경·배포·복구 절차

## 적용 범위

이 절차는 `codex/phase1-clean-start`와 후속 보완 브랜치 `codex/phase1-followup-fixes`의 합성 테스트 환경을 위한 것입니다. GitHub의 최초 개발 기준은 게이트러너 제거 커밋 `f57c3d1`이며, 1차 구현과 보완 코드는 사용자 승인된 PR을 통해 `main`에 반영합니다. Production 배포, 도메인 변경, 유료 프로젝트 생성, 기존 데이터 초기화는 포함하지 않습니다.

| 대상 | 값 |
| --- | --- |
| GitHub | CODEhenryKIL/gemini-dino-jump |
| Vercel 프로젝트 | dino-nanobanana / prj_U9Wi3VyA46EpOdOyrq0P3RRHwMSX |
| Vercel 팀 | henry-kils-projects / team_BhbQ5LTcQ0r7hANiiKA2PmoR |
| 배포 환경·리전 | Preview / icn1 |
| Supabase 프로젝트 | igfrnexknwtiljdqjrbp / 서울 |
| 테스트 스키마·접속 역할 | dino_dev / dino_dev_app |

## DB 준비

1. 프로젝트 상태·스키마·역할·migration 이력과 기존 데이터 건수를 읽어 기준을 남깁니다. 코드 복구는 원격 초기화가 아닙니다.
2. 빈 로컬 PostgreSQL에서 migration과 기존 스키마 보존 검사를 통과시킵니다. migration은 앱 시작 때 실행하지 않습니다.
3. 원격에서 `dino_dev`와 전용 역할이 기존 용도로 사용되지 않는지 확인한 뒤 검토한 migration을 적용합니다.
4. 환경 보호 행에 정확한 환경·프로젝트·스키마와 합성 데이터 전용 상태를 지정합니다. 소유자 계정으로 `supabase/seed_dino_dev.sql`을 명시적으로 실행합니다. 이미 seed된 DB에는 재실행하지 않습니다.
5. 새 전용 역할의 접속 비밀번호를 생성합니다. 기존 계정의 비밀번호를 변경하지 않습니다. 비밀값은 비공개 설정에만 저장합니다.
6. Preview는 트랜잭션 풀러의 6543 포트와 전용 역할을 사용합니다. TLS 인증서·호스트 이름 검증을 유지합니다. 관리자·소유자·service_role 키를 게임 DB 연결에 사용하지 않습니다.
7. 앱 역할이 기존 `public`·`dino` 데이터와 관리자 멤버십 설정을 변경할 수 없는지 검사합니다. Auth·Storage·CPU·메모리·연결 풀은 프로젝트 안에서 공유합니다.

## 1차 후속 보완 migration

- `20260925125939_add_awaiting_claim_information_status.sql`은 수령 초기 상태를 `AWAITING_INFORMATION`으로 추가합니다. 기존 migration 파일은 변경하지 않습니다.
- 이전 `INFORMATION_RECEIVED` 중 제출 시각·연락 정보가 없고 담당자·검증·업무 처리 흔적도 없는 최초 버전 행만 입력 대기로 보정합니다. 이미 처리 중이거나 종결된 상태는 보존하며, 연락 정보만 있고 제출 시각이 없던 기존 행은 연락 정보 생성 시각으로 보정합니다.
- 새 코드는 이 migration 버전을 요구합니다. 기존 Preview DB에 새 코드를 먼저 연결하면 스키마 보호 검사로 요청이 실패합니다. 원격 반영 시에는 쓰기 중단·보정 대상 확인 → migration → 새 Preview 코드 → 수령/관리자 흐름 검증 순서가 필요합니다.
- 이번 보완에서는 로컬 검증만 수행합니다. 원격 DB와 현재 Preview는 기존 버전이며, 이 절차가 기록됐다고 원격 적용된 것은 아닙니다. 기존 부하 시험도 다시 실행하지 않습니다.

## 환경변수와 접근

`.env.example`은 로컬 템플릿입니다. `.env.local`, `.local/`, `.artifacts/`, 테스트 계정·참가자 쿠키 목록은 Git과 배포 업로드에서 제외합니다.

현재 Vercel 프로젝트에는 Git 저장소 연결이 없어서 브랜치별 환경변수 등록이 거부됩니다. 이 상태에서는 이번 Preview 배포에만 런타임 값을 전달합니다. CLI 59.23.2의 `deploy --env KEY`는 값이 없는 변수 이름에 대해 실행 프로세스의 환경값을 읽습니다. 비공개 `0600` 파일을 읽는 실행 래퍼가 프로세스 환경을 채우고, CLI 인수에는 변수 이름만 넣습니다. 기존 Preview 공통값과 Production 값은 덮어쓰지 않습니다. DB URL과 토큰 해시용 pepper는 명령줄 인자나 출력에 넣지 않습니다. 공개 설정 API에는 Supabase publishable/anon 키만 허용합니다.

사이트 표시 이름은 **구글 코리아 팀 제미나이**, 요청된 별도 주소는 `google-korea-team-gemini.vercel.app`입니다. 주소는 새 Preview가 준비된 뒤 실제 할당 성공 여부를 확인합니다. 현재 배포별 `VERCEL_URL`과 설정한 친화 주소만 정확한 Origin으로 허용합니다.

Vercel 보호 설정은 유지합니다. 자동 검증에는 승인된 임시 공유 접근 또는 공식 인증된 CLI 요청을 사용하며 공유 토큰과 보호 쿠키를 결과 보고서에 넣지 않습니다.

## Preview 검증 순서

1. Python 3.12 의존성 설치, API import, PostgreSQL 기능·동시성·권한 테스트와 프론트 테스트.
2. `vercel deploy --dry --json`으로 업로드 파일 확인. 환경 파일·기존 SQLite·개인정보·테스트 계정·피그마 렌더러 제외 확인.
3. 검토 가능한 커밋과 PR을 만들고 `--target=preview`로 배포.
4. READY 상태, 커밋, 실제 Python 빌드 버전, 헬스체크 환경·프로젝트·스키마·합성 guard 확인.
5. 실제 브라우저로 쿠키 복원→게임→검증→1회 추첨→합성 수령→실제 관리자 인증→수동 상태 변경→지표 흐름 확인.
6. 원격 실행 예산과 5,000명 합성 집단을 확인한 후 단계별 부하 실행. 중복 지급이나 재고 초과가 발견되면 중단하고 수정.
7. 접근 가능한 DB 연결·잠금·쿼리와 함수 로그를 함께 확인. 기존 데이터 건수를 다시 대조. 성공/실패·목표 미달과 미검증 항목을 보고서에 남김.

## 장애 대응과 복구

- DB 접속 실패: 요청을 실패로 반환합니다. 임시 DB로 대체하지 않습니다. 환경·대상·TLS·역할·풀러 연결부터 확인합니다.
- 게임 응답 유실: 소유자 인증으로 저장된 게임 결과를 먼저 조회합니다. 정상 완료 게임에 추가 환급하지 않습니다. 미완료 장애는 원래 게임권 종류와 세션에 연결해 판정·환급합니다.
- 배포 오류: 마지막으로 검증된 Preview 커밋과 설정을 기준으로 새 Preview를 준비합니다. 이전 불일치 스키마의 코드를 같은 DB에 연결하지 않습니다.
- DB 변경 오류: 새 쓰기를 멈추고 원인과 migration 이력을 확인합니다. 데이터를 삭제하는 down migration을 즉시 실행하지 않습니다. 가능한 경우 데이터를 보존하는 수정 migration을 준비합니다.
- 비밀 유출: 해당 전용 역할 비밀번호와 필요한 세션 비밀만 교체하고 Preview를 다시 연결합니다. 기존 다른 앱 계정·Auth 설정을 일괄 변경하지 않습니다.
- 로그: 요청 식별자, 배포, 경로 종류, 상태와 지연을 확인합니다. 쿠키·Authorization·전체 초대 URL·수령 연락처는 출력하지 않습니다.

## 공식 근거

- [Vercel Python 런타임](https://vercel.com/docs/functions/runtimes/python): 2026-09-25 확인, Python 3.12 지원.
- [Supabase 연결 방식](https://supabase.com/docs/guides/database/connecting-to-postgres): 서버리스 트랜잭션 풀러와 TLS 설정 참고.
- [Supabase 변경 기록](https://supabase.com/changelog): 2026-09-25 확인. 기존 `logs.all` 관리 API 제거에 주의하며 기존 데이터·Realtime 스키마를 변경하지 않음.

## DB 연결 재사용과 503 진단

- 서버 프로세스별 동시 DB 연결은 최대 8개이며 Supabase transaction pooler를 사용한다. 성공 후 트랜잭션이 종료된 연결만 재사용한다. 실행·대기 요청이 겹치는 동안만 유휴 연결 1개를 잠시 보유하고, 마지막 요청이 끝나면 모든 유휴 연결을 즉시 닫는다. 겹친 요청은 TLS 연결을 재사용하지만 완전히 순차적인 요청은 다시 연결한다.
- 연결 수명 300초·유휴 60초는 다음 checkout 때 검사한다. 시간만 흐르거나 서버리스 프로세스가 동결되면 정리된다고 보장하지 않는다. 따라서 후속 요청 없이도 실행·대기 요청이 0개가 되는 시점에 유휴 연결도 0개가 되도록 반환 경로에서 정리한다. 5초 넘게 유휴 상태였던 연결은 업무 처리 전에 확인한다. 업무 처리 도중 오류가 나면 연결을 폐기하며 변경 요청을 자동 재실행하지 않는다.
- statement/lock/idle transaction 제한은 `SET LOCAL`로 요청 트랜잭션에만 적용한다. 환경·스키마 버전·전용 역할 검사는 매 요청 수행한다.
- 안전한 요청 로그의 `database_failure`는 연결 대기 초과일 때 `pool_wait`, 설정 오류는 `configuration`, PostgreSQL 오류는 SQLSTATE 또는 `connection`이다. 비밀번호·SQL 원문·연락처는 로그에 넣지 않는다.
- 503이나 지연이 증가하면 Preview 요청 로그와 `pg_stat_activity`의 연결·잠금 대기를 함께 확인한다. 역할 연결 한도 또는 DB 규모를 자동 확대하지 않는다.
- Supavisor의 client 접속 수와 실제 Postgres backend 연결 수는 다르다. `pg_stat_activity`가 적어도 pooler client 한도에 도달할 수 있다. 관측된 `EMAXCONN limit: 200`과 프로세스별 유휴 보유량을 함께 검사한다. 프로세스당 상한은 전체 배포의 동시 연결 200개를 보장하는 전역 제한이 아니다.
- 새 연결을 만들기 전에 풀러가 `EMAXCONN`으로 거부한 경우만 50·100·200ms 간격으로 최대 3회 추가 시도한다. 추가 시도는 최초 연결 시도 후 0.75초 안에 시작해야 한다. 연결당 timeout은 5초이며 DNS·스케줄링까지 포함하는 전체 요청의 엄격한 5.75초 제한은 아니다. 잘못된 비밀번호·일반 네트워크 오류와 연결 후 쿼리·게임권 소비·추첨은 재실행하지 않는다. 이 처리는 순간적인 연결 경쟁을 완화할 뿐 전체 연결 한도를 늘리지 않는다.

공식 연결 한도 참고: [Supabase pooling limits](https://supabase.com/docs/guides/database/connecting-to-postgres/pooling-and-limits), [Vercel connection pooling and suspension](https://vercel.com/kb/guide/connection-pooling-with-functions). Postgres backend 연결과 Supavisor client 연결은 구분하며, Python에서 동결 후 백그라운드 정리가 실행된다고 가정하지 않는다.
