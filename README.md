# 공룡 점프 — 3차 개선 작업

JavaScript 게임과 Python API를 Vercel Preview·Supabase PostgreSQL에 연결한 공룡 점프입니다.

## 현재 작업 — 2026-09-29

- 브랜치: `codex/final-launch-preflight`, [초안 PR #9](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/9). 최종 오픈 준비와 실제 진행 현황은 [실행 계획](docs/final-launch-execution-plan.md)과 [실행 기록](docs/final-launch-execution-report.md)을 기준으로 확인합니다.
- 최신 기준: [통합 3차 지시서](docs/phase3-work-instructions.md), [공통 정책](docs/phase3-policy-decisions.md), [API 계약](docs/phase3-api-contract.md), [오픈 체크리스트](docs/phase3-launch-checklist.md).
- [현재 공개 베타](https://google-korea-team-gemini.vercel.app/)는 기존 Preview·`dino_dev` 연결·베타 무제한·기존 점수·추첨·수령 기록을 그대로 유지합니다. Production 후보는 친근 공개 별칭으로 전환하지 않았습니다.
- 같은 Supabase 프로젝트의 격리 `dino_prod`에 복주머니 실제 상품 77개·혜택 4,923자리, 별도 랭킹 경품 3개를 준비했습니다. 운영 캠페인은 `PAUSED`, `event_enabled=false`이며 참가 기록은 아직 없습니다.
- 행사 기간은 2026-09-29 19:00부터 2026-10-02 23:59까지, 수령 정보 접수는 2026-10-03 23:59까지입니다. 시간대는 모두 KST입니다.
- 관리자 실제 로그인·모바일 QA·최종 승인·롤백 대조가 남아 있습니다. 베타 삭제와 친근 공개 별칭 전환은 실행하지 않았고, 원격 부하·cohort 준비는 사용자 지시대로 계속 보류합니다.
- 직접 검증할 때: [전체 수동 테스트](docs/manual-test-cases.md), [서버 검증](docs/manual-test-server.md), [실행 기록 양식](docs/manual-test-results-template.md), [기존 테스트 전체 대응표](docs/manual-test-coverage.md), [2026-09-29 실행 결과](docs/test-run-2026-09-29.md).

## 이전 검토 배포 기록 — 2026-09-26

- **주소:** https://google-korea-team-gemini.vercel.app/
- 실행 코드: `8bc3ea2`. 기존 검토 주소를 최신 Preview로 갱신했습니다.
- 검증: Node **150/150**, 로컬 PostgreSQL 기반 Python **176/176**, 작은 화면·가이드·로딩 확인.
- 상태: Vercel READY, DB ready, `environment=preview`, `synthetic_only=true`.
- 접속: 기존 Vercel Preview 보호를 유지합니다. 인증된 브라우저 또는 별도 제공하는 만료형 검토 공유 링크로 접속합니다. 완전 공개 운영 전환은 아직 하지 않았습니다.
- 실경품 지급·Production 환경 활성화는 3차 범위이며 원격 부하 테스트는 보류 중입니다.
- 상세: [통합 배포 기록](docs/phase2-ui-release.md), [2차 전체 보고](docs/phase2-report.md), [UI 변경 기록](docs/phase2-ui-feedback.md).

## 기준과 범위

- 최초 개발 기준: 게이트러너 제거 완료 커밋 `f57c3d1`.
- 1차 운영 기반·F1–F3 및 추가 검토 보완은 PR #3·#4로 반영했습니다. 2차 전체 기능과 화면 개선은 PR #5에서 통합합니다.
- 최초 1차 개발 브랜치: `codex/phase1-clean-start`.
- 2차 통합 브랜치: `codex/phase2-ux-game-conversion`.
- 요구사항: [1차 지시서](docs/phase1-work-instructions.md).
- 확정 규칙과 운영 미정값: [정책 결정표](docs/phase1-policy-decisions.md).
- 정적 화면: Vercel. API: Python 3.12 Vercel Functions. 데이터: PostgreSQL.
- 기존 Supabase 프로젝트의 비공개 `dino_dev` 스키마와 제한된 `dino_dev_app` 계정을 사용합니다. 기존 `public`, `dino`, Auth, Storage를 초기화하지 않습니다.
- 1차는 합성 데이터와 테스트 경품만 사용합니다. Production 공개와 최종 운영값은 3차 범위입니다.

## 서비스 규칙

최초 기본권은 행사·참가자별 1장입니다. 초대권은 별도로 최대 3장 보유합니다. 새 초대 보상으로 잔액이 3장이 되는 순간 추가 적립을 10시간 제한합니다. 받은 권리는 대기 중에도 사용할 수 있습니다.

현재 게임 재도전 공유는 인증된 카카오 전송 성공으로 게임권을 지급합니다. 추가 뽑기 공유는 뽑기권만 지급하며, 일반 홍보·당첨 자랑·수령 접수용 공유에는 권리를 추가하지 않습니다. 링크 방문·공유창 열기·복사는 보상 근거가 아닙니다.

게임 결과는 서버에서 입력 로그로 검증합니다. 3차의 복주머니는 첫 무료 1회를 포함해 최대 10회입니다. Gemini 혜택 결과는 추가 뽑기가 가능하고, 실제 상품 당첨 뒤에는 종료합니다. 재접속·재요청은 같은 회차의 결과를 복원합니다. 미완료·100점 이하 환급은 원래 소비한 권리와 게임 세션에 연결합니다.

3차 복주머니 재고는 실제 상품 77개와 혜택 4,923자리, 총 5,000자리 비복원 추첨입니다. 랭킹 전용 무신사 5만원권·배민 2만원권·스타벅스 1만원권 각 1개는 추첨 재고와 분리합니다.

참가자는 HttpOnly 쿠키로 복원합니다. 관리자 로그인에는 실제 Supabase Auth와 별도의 관리자 권한을 사용합니다. 선물은 관리자 수동 연락·지급 방식입니다.

## 로컬 실행

Python **3.12**와 로컬 PostgreSQL이 필요합니다. SQLite 자동 초기화는 사용하지 않습니다.

```bash
python3.12 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env.local
```

`.env.local`에 로컬 전용 DB 접속값과 새 `SESSION_TOKEN_PEPPER`를 설정합니다. 파일 값은 문자열 그대로 읽으며 셸 명령이나 변수 치환을 실행하지 않습니다. 이미 설정된 프로세스 환경변수가 파일보다 우선합니다.

DB 소유자 계정으로 migration을 적용하고 환경 보호 행을 로컬 테스트 대상으로 설정한 뒤 명시적 합성 seed를 실행해야 합니다. 앱에는 소유자 계정 대신 `dino_dev_app` 접속값을 제공합니다. 분리·배포·복구 절차는 [운영 절차](docs/phase1-runbook.md)를 따릅니다.

```bash
./run.sh
```

기본 주소는 `http://127.0.0.1:3000`, 관리자 화면은 `/admin.html`입니다. 다른 Python 3.12 실행파일을 쓰려면 `DINO_PYTHON`을 설정합니다. 기존 Python 3.11 가상환경은 재사용하지 않습니다.

## 검증과 문서

- [1차 완료 결과·속도 미달 및 후속 개선](docs/phase1-report.md)
- [사용자 제공 기획안·쿨다운 확정 정정](docs/source_user_plan.md)
- [기획안 복원 후 1차 누락·정합성 검토](docs/phase1-source-plan-review.md)
- [1차 보완 구현·검증](docs/phase1-followup-report.md)
- [병합 후 자동 리뷰 추가 수정·검증](docs/phase1-review-followup.md)
- [첨부 0차 공통 원문](docs/00_scope_and_decisions.md): 보존용 사본. 충돌하는 규칙은 2026-09-25 개정 1차 지시서와 정책 결정표가 우선합니다.
- [구현·검증 계획](docs/phase1-implementation-plan.md)
- [API 계약](docs/phase1-api-contract.md)
- [이벤트 사전](docs/phase1-events.md)
- [원격 부하 계획과 상한](docs/phase1-load-plan.md)

원격 부하는 승인된 Preview와 테스트 스키마에만 실행합니다. 사용자 승인으로 누적 시간 상한을 40분으로 확대했고 API 30,000회 상한은 유지했습니다. 최종 200명 시험은 모두 완료·서버 오류 0건이며, 누적 25,065호출·36분 44초 예약에서 시험을 종료했습니다. 일반 API p95 1초 목표 미달과 스테이지 전환 끊김은 후속 개선으로 남깁니다. 로컬 결과, Preview 실행 결과, 실제 기기 성능은 별도로 기록합니다. 개인 쿠키·비밀번호·연락처가 포함된 원본은 Git에 저장하지 않습니다.

- [2026-09-29 행사 준비 후속 구현·검증·베타 배포](docs/phase3-launch-followup-2026-09-29.md)
