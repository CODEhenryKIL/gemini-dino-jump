# 카카오 전송 웹훅·게임권 베타 배포 검증

검증일: 2026-09-27. 브랜치: `codex/ranking-ticket-ui`.

## 배포와 DB

- 고정 베타 주소: https://google-korea-team-gemini.vercel.app/
- 배포 ID: `dpl_EzcZeH2E7w58SNc8nnmcdfvgDW99`, READY, Preview.
- 고유 주소: https://dino-nanobanana-5hkzauwl4-henry-kils-projects.vercel.app
- 기존 Supabase 프로젝트 `igfrnexknwtiljdqjrbp`의 공룡 점프 전용 `dino_dev`만 사용했다.
- 마이그레이션 `20260927090000`, `20260927091037`, `20260927140000` 적용 성공.
- 신규 공유 테이블 강제 RLS, anon/authenticated 읽기 권한 없음, 전용 서버 역할 쓰기 권한 확인.
- 기존 베타 별칭을 새 배포로 연결했다. 원래 `dino-nanobanana.vercel.app` 운영 별칭은 변경하지 않았다.
- 새 유료 프로젝트 생성, 데이터 초기화, 부하 테스트 없음. 무제한 베타 플레이 유지.

## 적용 기능

- 미완료 게임 무효·실제 차감권 1회 복구. 무제한 게임에는 가짜 환급을 만들지 않음.
- 검증 점수 100점 이하 게임권 복구, 결과 재도전 버튼, TOP3 효과.
- 초대 게임권은 카카오 전송 성공 웹훅 기준. 공유창 열기·친구 방문·최초 2회 예외는 지급 근거에서 제외.
- 수령 정보 공유 확인도 해당 접수 건에 연결된 서버 전송 확인을 사용.
- 공유 경품 이미지와 혜택 하단 당첨 상품별 문구.

## 검증 증거

- Node 전체 회귀 201개 통과. 이번 배포 전 설정·보안·스키마 검사 10개 통과, `git diff --check` 통과.
- 고유 배포 및 고정 베타 `/api/health`: `database=ready`, `environment=preview`, 새 배포 ID 확인.
- `/api/config`: `share.webhook_enabled=true`, JavaScript 키 구성 완료. 비밀 키 값은 공개 API/문서에 기록하지 않음.
- 비인증 방문자가 Vercel 로그인 없이 앱에 접근 가능. 실제 브라우저 홈에서 무제한 표시 확인.
- 카카오 앱 1588671의 공식 웹훅 테스트 도구에서 DirectChat 콜백 전송: 전용 테스트 참가자의 초대권 0→1, 공유 상태 confirmed, reward_status granted.
- 같은 공유 요청을 공식 도구로 다시 전송: 초대권 1 유지, 지급 원장 1건 유지.
- 인증 없는 웹훅 요청: HTTP 401 WEBHOOK_UNAUTHORIZED.
- 테스트 참가자는 개인정보·게임 점수·추첨 없이 생성했으며 Preview 합성 집계로 관리한다.
- 위 테스트는 카카오가 보낸 테스트 콜백이다. 실제 친구에게 메시지를 보낸 모바일 종단 검증과 구분한다.

## 남은 항목

- 실제 카카오톡 친구 전송 → 웹훅 → 사용자 화면의 적립 확인. 사용자에게 실제 전송을 요청했다.
- 사용자가 맡은 Notion 내부 CTA 게시 여부 확인.
- 실제 iOS/Android·인앱 공유 최종 검증, 사용자 요청으로 보류한 최신 버전 부하 테스트.
- 본행사 운영값·실재고·기간·마감/동점 정책·개인정보 운영·오픈 승인은 3차 작업 범위다.
- 현재 코드/문서 대조에서는 별도의 큰 미구현 요구사항을 추가로 발견하지 않았으나 전체 실기기 검증 완료를 뜻하지 않는다.
