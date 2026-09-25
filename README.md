# Team Gemini 공룡 점프

Python API·JavaScript 게임·Supabase PostgreSQL로 구성한 이벤트 사이트입니다.
현재 작업 브랜치는 기존 Phase 1 구현을 보관하고 있으며, 합성 데이터와 테스트 경품만 사용합니다.

## 현재 상태 — 2026-09-25

**새 1차 지시서 대기 중이며, 복구는 아직 실행하지 않았습니다.**

- 사용자는 게이트러너 제거 완료 시점(`f57c3d1`)을 기준으로 Supabase·Vercel 연결 작업을 다시 시작할 예정입니다.
- 기존 Phase 1에서는 DB 연결·테스트 데이터·Preview 환경변수까지 준비했습니다. Preview 배포는 Python 3.11 빌드 오류로 실패했습니다.
- 정상 Preview·전체 E2E·원격 동시 접속 성능은 미검증입니다. Production 배포와 main 병합은 하지 않았습니다.
- [초안 PR #1](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/1)과 작업 브랜치를 유지합니다.
- 서비스 상태는 9월 23일 마지막 확인 기록입니다. 세부 내역과 복구 대상은 [최신 상태 보고서](docs/phase1-readiness-report.md)를 확인하세요.

아래 실행 안내는 보관 중인 기존 구현 기준입니다. 새 지시서 없이 기존 연결·배포 작업을 재개하지 않습니다.

## 로컬 실행

Python 3.11과 PostgreSQL 17이 필요합니다. Supabase CLI + Docker를 우선 사용합니다.

1. [운영 런북](docs/phase1-operations-runbook.md)에 따라 migration → 환경 guard → seed를 적용합니다.
2. 승인된 전용 DB 계정의 접속 정보를 준비합니다.
3. 다음 명령으로 Python 환경과 로컬 설정 파일을 만듭니다.

```bash
python3.11 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
cp .env.example .env.local
chmod 600 .env.local
```

`.env.local` 예시를 실제 **로컬** 값으로 바꾼 뒤 `./run.sh`를 실행합니다.
게임은 <http://127.0.0.1:3000>, 관리자는 <http://127.0.0.1:3000/admin.html>입니다.
DB 없이 기록을 저장하거나 관리자 인증을 생략하는 실행 모드는 없습니다.

## 구성

- `public/`: 공룡 점프 화면·엔진·관리자 화면
- `api/index.py`, `server/`: Vercel Python Function과 로컬 서버
- `supabase/migrations/`: 테이블·제약·권한·RLS
- `supabase/seed.sql`, `supabase/preview_seed.sql`: 환경을 검사하는 합성 seed
- `tests/`, `scripts/phase1_load.py`: 기능·보안·부하 검사

기본 게임권·추천 보상·경품 확률은 테스트 설정입니다. 기존 사양 문서의 수치를 확정 운영 정책으로 사용하지 않습니다.

## 문서

- [원본 작업 지시서](docs/phase1-work-instructions.md)
- [API 계약](docs/phase1-api-contract.md)
- [실행·관리자·배포·백업·복구](docs/phase1-operations-runbook.md)
- [구현 및 실제 검증 결과](docs/phase1-readiness-report.md)
