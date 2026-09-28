# 3차 구현·검증 보고서

- 작성: 2026-09-29
- 작업 브랜치: `codex/phase3-launch`
- 기준: [통합 3차 지시서](phase3-work-instructions.md)
- 현재 상태: **3차 기능 베타 반영 완료·운영 준비 중. 본행사 오픈 완료 아님.**
- 원격 변경: 기존 Supabase `dino_dev`에 보존 migration을 적용했고, 기존 베타 주소를 검증한 새 Vercel Preview에 연결했다.
- GitHub: [초안 PR #8](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/8), 선행 PR #7 위에 쌓은 변경. 메인 병합은 하지 않았다.

## 구현 범위

| 요구사항 | 작업 내용 | 증거 상태 |
| --- | --- | --- |
| 결과 화면 | 배지·닉네임 수정·이번 판 제거, 점수 축소, 버튼 순서 유지 | 모바일 크기 검토 통과 |
| 점프 조작 | 점프 버튼에만 선택·길게 누르기 메뉴·드래그 방지 | JS 회귀 통과, 실제 휴대폰 미검증 |
| 공유 | 목적별 두 줄 문구·이미지·주소, 게임권/뽑기권/NONE 분리 | JS 통과, 새 경로의 실제 카톡 미검증 |
| 복주머니 | 최초 포함 최대 10회, 혜택 재도전·실상품 종료, 회차별 결과 | 서버·회차 경계 검증 통과 |
| 재시도 | 같은 회차·주머니·요청 ID 복원, 응답 유실로 다음 권리 소비 방지 | 동시 요청·회차 재시도 통과 |
| 재고 | 5,000자리 비복원 구조, 상품별 77개·랭킹 별도 3개 | 전체 소진·마지막 재고 경쟁 통과 |
| 기존 기록 | 기존 추첨 1회차·수령·배정 보존 migration | 로컬·원격 기존 행 보존 확인 |
| 기록·관리자 | 수령함 회차 목록, 관리자 추첨·상품·혜택·지급·뽑기권 집계 | JS DOM 회귀 및 로컬 수령함 확인 |
| 운영 설정 | 버전 있는 JSON·미정 항목·수량/예산 검사 | 설정 검사 7개 통과 |
| 운영 문서 | 최신 정책 연결·체크리스트·복구/수동 지급 절차 | 작성 완료, 승인·실제 운영값 미정 |

## 현재 확인한 증거

### 화면 및 JavaScript

- `node --test tests/*.test.cjs`: 최종 **220/220 통과**. 응답 유실 재시도·이미 받은 뽑기권 바로 사용·늦은 상태 갱신·긁기 저장 대기·관리자 및 수령함 회차 표시·공유 보상별 안내 회귀를 포함한다.
- 실제 Chrome의 `390×700` viewport로 로컬 TOP3 결과 시안 확인.
- 첫 검토에서 3개 버튼 하단 위치는 약 424/495/558px, 고정 하단 메뉴 시작은 636px로 모두 가리지 않았다.
- 같은 시안의 순위 없음 분기에는 수령 정보 입력란이 표시되지 않았다.
- 이 검사는 데스크톱 Chrome 크기 조절이며 iOS·Android 실제 카카오 인앱 검증을 대체하지 않는다.
- 실제 API에 연결한 `http://127.0.0.1:3109/`에서 게임 시작 가이드 → 게임 → 검증된 32점 결과를 확인했다. 기존 최고점 749점·4위·무제한 설정이 유지됐다.
- 같은 `390×700` 화면에서 재도전·카카오 공유·복주머니 버튼 하단은 약 398/469/532px로 모두 하단 메뉴 위에 표시됐다. 콘솔 오류는 0건이었다.
- 기존 상품 당첨 결과는 추가 뽑기 없이 수령함·자랑하기를 제공했고, 수령함은 기존 상품과 1회차 기록을 함께 표시했다.
- 점프 버튼의 실제 CSS `user-select:none`, `touch-action:manipulation` 및 접근성 이름을 확인했다. 실제 iOS의 길게 누르기 메뉴 차단은 별도 기기 검증 대상이다.

### 서버·DB

- Python **3.12** 전체 suite: 총 **235개 중 234개 통과, 선택형 실DB 코호트 1개 skip**. 별도 아래 5,000회 검증은 실제 로컬 PostgreSQL에서 수행했다.
- fresh DB에 11개 migration 적용·schema guard, 기존 수령 접수·게임·쿠키·웹훅 회귀 통과.
- 격리 풀 전체 소진: **PRIZE 77 / BENEFIT 4,923 / 서로 다른 결과 5,000 / 상품 수령 요청 77 / 예약 재고 77**. 5,001번째 추첨은 `DRAW_POOL_EXHAUSTED`, 전체 시험 트랜잭션은 rollback.
- 9회 사용 뒤 서로 다른 공유 웹훅 2개가 동시에 도착하면 **1개 적립 + 1개 상한 차단**. 10회차 동시 요청은 **신규 1개 + 동일 결과 재응답 1개**, 총 10회·잔액 0.
- 실제 상품 당첨 뒤 늦은 웹훅·남은 권리 차단, 마지막 상품 동시 요청 중 1명만 배정, 같은 회차의 다른 주머니 거부 확인.
- 수령 접수용 신규 공유는 계약 v2·`NONE`, 과거 v1 접수 기록은 보존. 복주머니와 랭킹 claim을 같은 사람이 동시에 보유하는 회귀 통과.
- 마지막 공유 목적 집계·배포 호환성 보완 후 관련 서버 테스트 **30/30 통과**. 게임 재도전·추가 뽑기·자랑·일반·수령 접수 공유를 분리하고, 소유가 확인된 요청의 카카오 인증 콜백 수를 클라이언트 공유 시도 수와 구분한다.
- migration 적용 뒤 구버전 앱이 만든 첫 추첨도 새 앱에서 사용 완료로 계산·원장 정산한다. 배포 교체 간격 때문에 무료 추가 추첨이 생기는 경로를 차단했다.

### 백업·보존

- 로컬 사용자 DB의 전용 백업을 임시 DB에 실제 복원해 9개 주요 테이블 건수가 일치함을 확인했다.
- 새 migration 전후 기존 9개 테이블의 모든 기존 컬럼을 해시 대조했다. 기존 행은 동일하고 추첨 4건은 1회차로 보존됐다.
- 원격 `dino_dev`는 기존 전용 역할·`verify-full` 연결로 읽기 전용 백업했다. 29개 테이블·4,293행을 별도 로컬 DB에 복원하고 UTC 기준 모든 행이 동일함을 확인했다.
- 그 원격 백업 복원본에 새 migration을 적용하는 리허설도 통과했다. 기존 28개 업무 테이블의 원래 컬럼은 동일했고, 추첨 8건·과거 공유 요청 87건을 보존했다. 과거 공유는 계약 v1/GAME을 유지하고, 추첨 원장 16행의 순증감은 0이었다.
- 검증한 migration SHA-256: `63a77f5654c282c1f0363e0120a240d372c41fc0058e698fff60066a0377452e`.
- 백업과 증거 원본은 배포·Git에서 제외되는 `.local/phase3/`에 보관한다. 보고서에 연락처나 인증 비밀을 복사하지 않았다.

### 운영 설정

- Python **3.12.13**, psycopg **3.3.6**로 `test_phase3_preflight.py` **7개 통과**.
- `scripts/phase3_preflight.py`: 수량·예산·추첨 설정 오류 0개.
- `--require-launch-ready`: 미정 정책·승인·증거가 있어 의도대로 종료 코드 1. 문서의 빈칸을 승인으로 간주하지 않음.
- `prepare_phase3_pool.py`: 별도 로컬 `dino_phase3_pool_test`에 PAUSED 합성 행사 준비, 5,000자리·77개 개별 재고·11종 대조.
- 동일 준비를 두 번 실행해 재고가 중복 생성되지 않고 기존 앱의 활성 행사 포인터가 유지됨을 확인.
- 위 풀은 가짜 시험 재고이며 실제 구매·지급·원격 적재가 아니다. 전체 소진 검증은 별도 결과를 기록한다.
- 같은 총수량을 유지하면서 상품 종류를 바꾼 잘못된 풀도 준비 도구가 거부하는지 확인했다. 시험 변경은 트랜잭션 롤백으로 보존했다.

### 외부 링크

- 사용자 지정 단축 링크가 Google 학생 혜택 페이지로 연결되는 것을 실제 Chrome에서 확인했다. 한국어 1년 무료 안내와 자격·기한·갱신 조건은 [외부 링크 확인](phase3-external-links.md)에 기록했다.
- Notion 공부법은 앱 이동 안내에서 본문 확인이 되지 않았다. 두 가이드의 익명 공개 접근과 내부 CTA는 미검증으로 유지한다.

### 원격 사전 확인

- Supabase guard는 `preview`, `synthetic_only=true`, 기존 행사 ACTIVE·실경품 OFF, schema version 10개였다. 기존 앱 외 `public`·Auth·Storage는 변경하지 않았다.
- Vercel은 기존 `dino-nanobanana` 프로젝트와 팀이 맞고 `ssoProtection:null`이었다. 현재 베타의 공개 접속 설정을 새로 약화시키는 작업은 하지 않았다.
- Supabase 사전 security advisor에는 기존 `public` 함수의 [search_path](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable), [anon SECURITY DEFINER 실행](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated 실행](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), [유출 비밀번호 보호 OFF](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection)가 보고됐다. 공룡 점프 전용 새 스키마의 점검과 기존 공용 영역 변경 범위는 구분하며, 이 사전 보고만으로 관련 설정을 변경하지 않았다.

### 원격 베타 반영 — 2026-09-29 KST

- 코드 `1e7975b63b244e5ec626f7a663e845aa93555498`를 기존 Vercel 프로젝트의 Preview로 배포했다. 배포 ID는 `dpl_AmrVdaQ8ASo2Wzwq4RR8n5dYpmHD`, 서울 `icn1`, READY다.
- 새 [Preview](https://dino-nanobanana-88z734ccm-henry-kils-projects.vercel.app/)를 빌드한 뒤 검증한 migration을 기존 `dino_dev`에 적용했다. schema version은 10개에서 11개로 늘었다.
- 백업 이후 변경된 테이블은 요청 제한용 `rate_limit_bucket`뿐이었다. 반영 직전 비교 기준을 따로 저장하고, migration 직후 기존 29개 테이블의 모든 기존 행·컬럼이 동일함을 확인했다. 기존 추첨 8개는 모두 1회차이며, 공유 87개는 v1/GAME을 유지한다. 새 추첨 원장 16행의 순증감은 0이다.
- 새 두 테이블은 RLS·FORCE RLS를 사용하며 `anon`·`authenticated`의 SELECT는 거부되고 공룡 점프 서버 전용 역할만 허용된다. 적용 뒤 security advisor 결과는 기존 4개 경고와 같고 새 `dino_dev` 경고는 없었다.
- 새 Preview에서 홈·랭킹·공유 버튼 준비와 콘솔 오류 0건을 확인한 뒤 [베타 고정 주소](https://google-korea-team-gemini.vercel.app/)만 전환했다. `/api/health`와 `/api/config`는 200, DB ready, 새 배포 ID, 카카오 웹훅 설정 활성 상태다.
- 기존 베타 브라우저를 새로고침해 같은 Gemini 혜택 결과가 `1/10회`로 복원되고 `카카오톡으로 공유하고 한 번 더 뽑기` 버튼이 표시되는 것을 확인했다. 무제한 표시도 유지됐다. 전송 버튼을 대신 누르거나 친구에게 메시지를 보내지는 않았다.
- 원래 `dino-nanobanana.vercel.app`은 기존 Production `dpl_2rTHbCNUGMLeA1nUMycDzLvBUFW8`에 그대로 연결되어 있다.
- 원격 추첨 풀 자리 수는 0이며 기존 25개 테스트 재고를 보존했다. 77개 실제 경품·랭킹 3개를 적재하거나 본행사를 활성화하지 않았다. 새 유료 프로젝트·서버 증설·원격 부하 시험도 수행하지 않았다.
- 실제 카카오 새 GAME/DRAW 전송·보상 검증은 **사용자 요청으로 나중에 확인**한다. 기존 전송 성공 기록이나 이번 버튼 표시를 새 DRAW 보상 성공 증거로 취급하지 않는다.
- 비공개 증거: `.local/phase3/remote-preservation-before.json`, `remote-preservation-after.json`, `cutover-before-rows.json.gz`, `phase3-preview-deploy.json`.

## 공개 전 남은 작업

1. 새 게임권/뽑기권의 실제 카카오 전송·적립 및 카드 확인. 사용자 요청으로 추후 진행한다.
2. 행사 날짜(사용자 확인: 미정)·동점·동일인 중복 ID·마감 경계·수령 기한·개인정보·운영자 정책 확정. 복주머니와 랭킹 상품 동시 당첨은 둘 다 지급으로 확정했다.
3. 본행사 환경 분리와 런타임 guard 구현/검증. 현재 `Settings`와 DB 제약은 synthetic local/test/preview만 허용한다. 이번 베타 반영만으로 Production 실행이 가능해진 것은 아니다.
4. 실기기 QA, 사용자가 보류한 최종 부하 시험의 별도 승인·수행.
5. 실제 재고 확인·승인된 적재, 혜택/브랜드/Notion·개인정보 안내·운영자·예산 알림 및 공개 승인.

현재 상태를 `오픈 준비 완료` 또는 `3차 완료`로 표시하지 않는다. [오픈 체크리스트](phase3-launch-checklist.md)의 미확정·미검증 항목을 유지한다.
