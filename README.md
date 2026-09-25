# 공룡 점프 — 1차 운영 기반

기존 JavaScript 게임과 Python API를 유지하면서 Vercel Preview와 Supabase PostgreSQL에 연결하는 작업 브랜치입니다. 이 문서는 배포 완료 보고가 아닙니다. 완료 여부는 실제 테스트·배포 기록으로 판단합니다.

## 기준과 범위

- 최초 개발 기준: 게이트러너 제거 완료 커밋 `f57c3d1`.
- 이번 코드 기준: 1차 운영 기반과 F1–F3 보완 완료. 사용자 요청에 따라 PR을 통해 `main`에 반영하는 대상입니다. 원격 DB·Preview 배포 상태는 아래 보고서와 별개로 확인합니다.
- 최초 1차 개발 브랜치: `codex/phase1-clean-start`.
- 현재 보완 브랜치: `codex/phase1-followup-fixes` (`e84ec67`에서 분기). 보완 코드는 로컬 검증 범위이며 원격 DB·Preview에는 아직 반영하지 않았습니다.
- 요구사항: [1차 지시서](docs/phase1-work-instructions.md).
- 확정 규칙과 운영 미정값: [정책 결정표](docs/phase1-policy-decisions.md).
- 정적 화면: Vercel. API: Python 3.12 Vercel Functions. 데이터: PostgreSQL.
- 기존 Supabase 프로젝트의 비공개 `dino_dev` 스키마와 제한된 `dino_dev_app` 계정을 사용합니다. 기존 `public`, `dino`, Auth, Storage를 초기화하지 않습니다.
- 1차는 합성 데이터와 테스트 경품만 사용합니다. Production 공개와 최종 운영값은 3차 범위입니다.

## 서비스 규칙

최초 기본권은 행사·참가자별 1장입니다. 초대권은 별도로 최대 3장 보유합니다. 새 초대 보상으로 잔액이 3장이 되는 순간 추가 적립을 10시간 제한합니다. 받은 권리는 대기 중에도 사용할 수 있습니다.

초대 링크 방문자는 화면이 보이는 상태로 3초 이상 머물고 클릭 또는 터치해야 합니다. 같은 친구가 서로 다른 초대자를 도울 수 있지만 같은 초대자–방문자 쌍은 한 번만 보상합니다. 대기 중 방문은 자동 이월하지 않습니다.

게임 결과는 서버에서 입력 로그로 검증합니다. 정상 완료 후 복주머니는 행사·참가자당 1회입니다. 재접속·재요청에도 같은 결과를 복원하며 공유 여부와 독립입니다. 장애 환급은 원래 소비한 권리와 게임 세션에 연결합니다.

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
- [첨부 0차 공통 원문](docs/00_scope_and_decisions.md): 보존용 사본. 충돌하는 규칙은 2026-09-25 개정 1차 지시서와 정책 결정표가 우선합니다.
- [구현·검증 계획](docs/phase1-implementation-plan.md)
- [API 계약](docs/phase1-api-contract.md)
- [이벤트 사전](docs/phase1-events.md)
- [원격 부하 계획과 상한](docs/phase1-load-plan.md)

원격 부하는 승인된 Preview와 테스트 스키마에만 실행합니다. 사용자 승인으로 누적 시간 상한을 40분으로 확대했고 API 30,000회 상한은 유지했습니다. 최종 200명 시험은 모두 완료·서버 오류 0건이며, 누적 25,065호출·36분 44초 예약에서 시험을 종료했습니다. 일반 API p95 1초 목표 미달과 스테이지 전환 끊김은 후속 개선으로 남깁니다. 로컬 결과, Preview 실행 결과, 실제 기기 성능은 별도로 기록합니다. 개인 쿠키·비밀번호·연락처가 포함된 원본은 Git에 저장하지 않습니다.
