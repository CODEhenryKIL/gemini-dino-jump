# Team Gemini 공룡 점프

Python API·JavaScript 게임·Supabase PostgreSQL로 구성한 이벤트 사이트입니다.
현재 Phase 1 개발 중이며 합성 데이터와 테스트 경품만 사용합니다.

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
