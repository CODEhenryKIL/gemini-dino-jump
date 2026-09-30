# 공유 재도전·101점 추첨 조건 운영 배포 — 2026-09-30

- 사용자 배포 승인 후 검증한 소스 `2df680bfc9fb48f92d9d2e3341a3f8ad57e73dcc`를 정확한 Git 아카이브로 배포했다.
- 브랜치: `fix/share-retry-score-gate-20260930`
- 배포 ID: `dpl_9EZQA44zs9bwmQk5wjPmEFtBJKvF` (`READY`, production, icn1)
- 정식 주소: https://google-korea-team-gemini.vercel.app/
- 고유 배포: https://dino-nanobanana-bnkuxs4mg-henry-kils-projects.vercel.app/
- 정식 주소 연결: 2026-09-30 11:27:38 KST
- 정식 파일·API 확인 완료: **2026-09-30 11:28:13 KST**
- 운영 manifest SHA-256: `9de34dafb14aaa0e45e78887293df6196e6710a5b3213ea67f5fd5ddd5dcfbea` 유지

## 반영 내용

- 재도전 공유 문구: `공유하고 한 판 더`
- Gemini 이후 새 재도전 공유의 GAME-only 경로를 BOTH로 정규화
- 보상 확인 후 `한 번 더 뽑기`와 `한 판 더 하기` 제공
- 게임권 3장·쿨다운·뽑기 10회 규칙 각각 유지
- 이번 판 100점 이하: 게임권 환급 및 재도전 안내
- 현재 행사에서 VERIFIED·FINISHED·101점 이상 이력이 있어야 새 추첨 허용
- 기존 101점 이상 자격·뽑기권·당첨·수령 정보 보존. 기존 저점수 참가자는 새 추첨만 101점 달성 후 해제

## 배포 및 검증

- 배포 전 자동 검사: JavaScript 319개, Python/PostgreSQL 65개 통과. 수정 JS 문법 검사·diff 검사·별도 릴리즈 검토 통과.
- 추가 DB migration 없음. 기존 BOTH 계약 v3 스키마 사용. 운영 게임·추첨·재고 데이터를 변경하지 않음.
- 후보 배포에서 홈과 수정 JS 9개(총 10개 파일)의 소스 바이트 일치·HTTP 200·로그인 리다이렉트 없음 확인.
- 후보 health에서 운영 Supabase 프로젝트·`dino_prod`·스키마 정상·ACTIVE 캠페인·테스트 모드 비활성·새 deployment ID 확인.
- 후보 확인 후 정식 alias만 연결. 기존 legacy alias 두 개의 연결은 보존.
- 전환 직후 최초 검사에서 이전 JS 파일이 반환됐으나, 11:28:13 KST 재검사에서는 캐시 우회용 URL 변경 없이 동일 정식 URL의 10개 파일이 모두 일치했고 health도 새 배포로 응답함.
- 새 배포의 배포 직후 runtime 5xx 조회 결과 0건. 짧은 관찰 구간이며 지속적인 무오류 보장은 아님.
- 30분 자동 보고에 이 시각 이후 B안 집계가 공유 수정·101점 조건까지 포함한다는 주석 추가.
- 백업·비밀 설정·로컬 가상 데모·iCloud 중복 파일은 배포/Git에 포함하지 않음.

## 남은 실사용 확인

- 새로고침 후 실제 카카오 친구/단톡 전송 → 두 보상 적립 → 재추첨 흐름 확인.
- 배포 전에 생성된 공유 intent는 최대 30분 동안 저장된 기존 GAME/DRAW 계약으로 처리될 수 있음. 해당 행을 강제 변환하거나 만료하지 않음.
- 서버 score gate는 새 서버가 즉시 적용하지만, 열어 둔 이전 화면은 새로고침해야 새 문구·버튼을 사용함.
