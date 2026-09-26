# Design

## Latest refinements
- Place the official Antigravity icon to the left of the home creation credit. Use locally hosted Google Sans Medium and Google's blue/red/yellow/green letter colors for Google AI, as confirmed by the user's latest correction. Keep Korean text neutral.
- Reuse the actual draw screen's pouch and ticket CSS in the loading explanation.
- Use the compact six-product prize composition v2. Remove all amount cards.

## Source of truth
- Status: Active. Last refreshed: 2026-09-26.
- Primary surfaces: 공룡 점프 초기 로딩과 홈. 이후 화면은 기존 2차 명세를 유지한다.
- Evidence: `docs/phase2-ui-feedback.md`, `docs/phase2-screen-spec.md`, `public/index.html`, `public/js/views/home.js`, 기존 CSS·공룡/Smile/Heart·팀 로고 원본. 애니메이션 기준: https://dino-nanobanana.vercel.app/ (2026-09-26 사용자 지정).

## Brand
- 대학생이 가볍게 시작하는 추억의 게임. Google 색상과 팀의 종이 스티커 자산을 함께 사용한다.
- 기존 배포의 로고 등장·공룡 홉·4색 진행바를 기준으로 한다. 로딩은 흰 배경과 중앙 3장면 설명 애니메이션(게임·주머니 선택·복권 긁기)을 사용한다. 팀 제미나이·Google Gemini 로고는 상단 가로 배열로 유지한다. 제목은 “한 판 즐기고, 경품에 도전하세요.”이며 로딩 하단 부가 설명은 제거한다. 홈 로고 중복과 과한 새 장식은 피한다.

## Product goals
- Google AI로 만든 게임임을 첫 화면에서 알리고 게임 시작을 가장 쉽게 찾게 한다.
- 초기 로딩은 약 5초의 완결된 연출. 동영상 다운로드나 새 라이브러리는 추가하지 않는다.
- 기존 초대·게임권·복주머니 규칙은 유지한다. 부하 테스트·운영 배포는 이번 범위가 아니다.

## Personas and jobs
- 휴대폰으로 들어온 참가자: 게임 시작, 기록 재도전, 기존 복주머니 결과로 복귀.
- 게임은 누구나 가능하고 경품 자격은 대학생임을 간결하게 구분한다.

## Information architecture
- 상단 팀 로고 1개 → AI 제작 제목 → 행사 한 줄 → 공룡 → 권리/최고점 → 게임 시작.
- 홈의 중복 로고·일반 사용 가능 안내·복주머니 상태 설명·추가 설명 카드는 제거한다.
- 상태에 따른 실제 복주머니 버튼과 하단 내비게이션은 유지한다.

## Design principles
- 큰 제목, 적은 문장, 충분한 여백으로 우선순위를 만든다.
- 색과 움직임은 제작 주체와 참여 순서를 설명하는 데 사용한다.
- 미정 경품을 확정 지급처럼 표시하지 않는다.

## Visual language
- Color: 기존 Google 4색 토큰. 본문은 짙은 회색, 흰 배경, 작은 컬러 포인트.
- Typography: 로딩·홈은 한국어 시스템 글꼴, 600 이하 중심 굵기와 여유 있는 자간. 사용자 최종 선택에 따라 홈 Google AI는 Google Sans와 Google 4색 글자로 표시한다.
- Layout: 기존 440px 모바일 중심 폭과 카드·버튼 재사용. 홈 제목과 CTA 사이의 밀도를 줄인다.
- Shape/elevation: 기존 둥근 카드, 홈은 얕은 그림자. 새로운 디자인 시스템을 추가하지 않는다.
- Motion: 기존 로고 scale-in(.7/.8초), 공룡 홉(.45초 왕복), 그림자 축소, 4색 진행바와 .5초 fade/scale 퇴장을 재사용한다. 로딩은 5초이며 실제 준비 지연은 별도다.
- Imagery: 제공된 공룡·Smile·Heart·팀 로고 원본 보존.

## Components
- 유지: 앱 헤더·하단 메뉴·게임권 요약·가이드 모달·복주머니 버튼.
- 변경: 로딩 장면·타이포 전환·홈 제목·행사 문구·정상 시작 버튼.
- CSS 소유: 로딩은 `style.css`, 홈 상세는 `phase2-views.css`. API 계약은 변경하지 않는다.

## Accessibility
- 키보드 시작/가이드/복주머니 이동과 기존 초점 처리를 유지한다.
- 장식 이미지는 보조기술에서 제외하고 연출 전체를 간결한 텍스트로 제공한다.
- 모션 감소에서는 모든 참여 단계를 정적으로 보여준다. 색상만으로 상태를 구분하지 않는다.
- 작은 화면에서도 오류 설명과 다시 연결 버튼에 접근할 수 있어야 한다.

## Responsive behavior
- 320/390/440px 휴대폰과 데스크톱 중앙 440px 앱을 확인한다.
- 낮은 화면은 스크롤을 허용하고 글자·버튼을 잘라 숨기지 않는다.
- 터치 버튼 크기와 키보드 동작은 기존 기준 유지.

## Interaction states
- Loading: 5초 연출과 실제 준비 완료를 각각 기다린다. 일반 화면 이동에는 재생하지 않는다.
- Empty/disabled: 게임권 없음은 버튼 상태와 필요한 안내로 표현한다.
- Error/offline: 기존 참가자 기록을 유지하며 다시 연결을 제공한다.
- Success: 홈으로 전환, 준비가 늦으면 마지막 장면에서 대기한다.

## Content voice
- 짧고 친근한 한국어. 정상 CTA는 `게임 시작`.
- 제목은 `Google AI로 만든 공룡 게임`.
- 사용자 행사 문구의 `맞자`는 문맥에 맞게 `받자`로 표기한다.
- 정상 홈에서 내부 계측·연출 준비 같은 구현 설명은 노출하지 않는다.

## Implementation constraints
- Vanilla JavaScript/CSS. 의존성·새 영상 파일 없이 transform/opacity 중심 애니메이션.
- 로딩 준비와 연출 완료 이벤트, 실패 복구·상태 갱신 계약을 보존한다.
- 수정사항을 모아 반영한 뒤 기존 회귀와 실제 브라우저의 연출/홈/작은 화면/오류/모션 감소를 한 번에 확인한다.

## Game guide update — 2026-09-26
- 게임 안내는 터치 조작, 코인, 하트, 랭킹의 4장 슬라이드로 표시한다. PC 조작 설명을 화면에서 제거하고 다음/이전·스와이프·건너뛰기를 제공한다.
- 실제 게임 에셋을 재사용하고 장면별 CSS 모션을 적용한다. 모션 감소에서는 정적 설명을 유지한다.
- 마지막 장에는 최종 1/2/3위 보상 5/3/1만원과 현재 TOP3·내 순위를 표시한다. 빈 상태에서 가짜 순위를 만들지 않는다.

## Open questions
- 실제 경품 확보·운영 문구는 3차에서 확정한다. 이번 행사 문구는 Preview 시안이다.
