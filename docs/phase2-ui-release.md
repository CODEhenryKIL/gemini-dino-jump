# 2차 화면 개선 통합 배포 기록

기록일: 2026-09-26. 작업 브랜치: `codex/phase2-ux-game-conversion`.

## 반영 범위

- 기존 2차 게임·쿠키·초대·복주머니·수령·트래킹 구현 위에 최신 화면 수정 통합.
- 5초 참여 설명 애니메이션, 상단 로고 가로 배열, 실제 주머니·복권 디자인, 6종 제품 경품 구성.
- 홈 상단 행사 배지, Antigravity 왼쪽 배치, Google Sans와 Google 4색 제작 문구.
- 터치/코인/하트/랭킹 4장 가이드, 이전/다음·스와이프·우측 상단 닫기·건너뛰기.
- TOP3 보상 5/3/1만원과 서버 현재 랭킹·내 순위, 오류 재시도, 닫힌 화면의 지연 응답 보호.
- 실제 랭킹 화면과 동일하게 동점자 공동 순위 및 추후 수상 기준 안내.
- 경품 PNG 원본 1,960,753바이트를 투명 WebP 341,606바이트로 변환해 로딩 전송량 약 83% 감소. 제품 구성·해상도 유지.

## 통합 검증

- Node 전체 화면·게임 회귀 **150/150 통과**. 새로운 가이드 동선·빈 랭킹·조회 실패·늦은 응답·안전한 닉네임 출력 포함.
- Python 전체 회귀 **176/176 통과**, 건너뛴 검사 없음. 로컬 전용 PostgreSQL에서 실행했으며 원격 부하를 발생시키지 않음.
- 분석 개인정보 거절 테스트를 기존 구현의 응답별 오류 코드 계약에 맞춰 갱신. 거절 건수·사유·DB 내 개인정보 미저장을 함께 검사.
- 실제 브라우저: 320px 가이드 가로 넘침 없음, 낮은 화면 내부 스크롤, 이전 및 첫 장 비활성화, Escape 닫기, 390px 홈과 WebP 자산 로드 확인.
- JavaScript 문법 및 `git diff --check` 통과. 코드 검토에서 발견한 이미지 용량·동점 안내·디자인 문서 불일치 보완.

## 배포 경계

- 기존 Vercel `dino-nanobanana` 프로젝트의 Preview와 `google-korea-team-gemini.vercel.app` 검토 주소를 갱신한다.
- 기존 개발 DB와 합성 데이터 설정을 유지한다. 실경품 활성화·운영 환경 전환·새 유료 프로젝트 생성은 포함하지 않는다.
- `.local` 샘플 랭킹·비밀 설정 및 `.omx` 실행 기록은 Git·배포에서 제외한다.
- 원격 부하 테스트는 계속 보류한다. 실기기·인앱·네이티브 공유 및 실제 행사 오픈 검증은 3차 범위다.

## 배포 결과

- 실행 코드: `8bc3ea2776658f71bf8c60dcf4a637eba05c1d4e`.
- Vercel 배포: `dpl_HJ4J76mdR2gWfq5aVwtsJtfaBD7B`, **READY**, Preview.
- 고유 URL: https://dino-nanobanana-oyf8682n8-henry-kils-projects.vercel.app
- 고정 검토 URL: https://google-korea-team-gemini.vercel.app/
- 빌드: Python 3.12, Vercel 빌드 완료 2초.
- `/api/health`: `ok=true`, `database=ready`, `environment=preview`, `synthetic_only=true`.
- 원격 JS 3개·CSS 2개·최종 경품 WebP를 로컬 파일과 바이트 단위 대조해 모두 일치 확인.
- 고정 검토 주소도 새 배포로 연결했다. 인증된 실제 브라우저에서 새 홈·4장 가이드·원격 랭킹 표시를 확인했다.
- 기존 Vercel Preview 보호(`all_except_custom_domains`)를 유지한다. 인증 없는 요청은 Vercel 로그인으로 이동하므로 완전 공개 사이트로 간주하지 않는다. 사용자 검토를 위해 23시간짜리 공유 링크를 발급했다. 공유 접근 토큰은 Git에 저장하지 않는다.
- PR #5의 검증된 작업 브랜치를 main에 병합한다. 이후 문서 갱신 커밋은 실행 코드 변경이 없어 재배포하지 않는다.
