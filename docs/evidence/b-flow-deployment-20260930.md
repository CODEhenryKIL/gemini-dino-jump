# B안 운영 배포 확인 — 2026-09-30

- 사용자 최종 승인 후 DB → Vercel 배포 → 정식 주소 연결 순서로 실행.
- 정식 주소: https://google-korea-team-gemini.vercel.app/
- 배포 소스: `35ada9c549924144cb07dc99d93e8d1977c0e33a`.
- 배포 ID: `dpl_8jfsjVZMR7bqPrqJgwgPNjk2SPpf` (`READY`, production).
- 고유 주소: https://dino-nanobanana-rgxdjcpg5-henry-kils-projects.vercel.app/
- 공개 주소 확인 시각: 2026-09-30 10:42:59 KST.

## DB와 데이터 보존

- 운영 스키마 `dino_prod`에 `20260929235536` 마이그레이션 적용. 필수 버전 13개, 새 보상 결과 컬럼 4개 확인.
- 기존 계약 v1/v2의 신규 결과 필드는 모두 `NOT_APPLICABLE`로 호환됨.
- 적용 전 10:33:32 KST 운영 32개 테이블을 읽기 전용 트랜잭션으로 별도 백업하고 해시·압축 해제를 검증.
- 백업에 있던 참가자 384건, 게임 664건, 추첨 343건, 접수 10건, 재고 66건, 랭킹 경품 3건, 공유 2,126건의 키가 모두 유지됨. 이는 적용 전 기록 보존 검사이며 현재 누적 집계가 아님.
- 이전 스냅샷의 격리 로컬 DB 복원과 같은 마이그레이션 리허설도 완료. 최신 스냅샷 자체를 다시 복원한 것은 아님.
- 백업·비밀 설정·개인정보 원본은 Git 및 배포에서 제외.

## 배포 확인

- 정확한 Git 소스 아카이브로 배포. iCloud 중복 ` 2.*` 파일은 포함하지 않음.
- 배포 dry run 통과. 실제 manifest SHA는 `9de34dafb14aaa0e45e78887293df6196e6710a5b3213ea67f5fd5ddd5dcfbea` 유지.
- 고유 주소와 정식 주소에서 홈·draw/prize/benefit_retry JS 파일의 소스 일치 및 HTTP 200 확인. 정식 주소는 로그인 화면으로 전환되지 않음.
- 운영 API health: `ok=true`, `database=ready`, `schema_valid=true`, `campaign_status=ACTIVE`, 실제 운영 스키마 및 새 배포 ID 확인.
- 정식 주소 이외 기존 두 legacy alias는 이전 배포 연결을 유지.
- 새 배포의 배포 직후 runtime 5xx 조회 결과 0건. 지속적인 무오류 보장은 아님.

## 검증 범위와 남은 확인

- 배포 전 Python 3.12 + PostgreSQL 17: backend/metrics 62개, migration/claim 13개, schema guard 2개 통과.
- 프런트 282개 및 실제 소스 모바일 화면 검사 통과.
- 실제 카카오 전송으로 새 v3 복합 보상(게임권+뽑기권)이 적립되는 최종 실사용 확인은 남아 있음. 테스트를 위해 운영 공유/추첨/경품 데이터를 임의 생성하지 않음.
- 새 v3 intent가 생긴 뒤에는 DB 컬럼 삭제 또는 v3 미지원 서버로 무조건 되돌리지 말 것.
