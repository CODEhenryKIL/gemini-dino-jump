# Phase 2 화면 명세

작성 기준: 2026-09-25 로컬 구현. 이 문서는 실제 사용자 화면의 현재 계약을 기록한다. 운영 경품, 종료 시각, 동점 수상 기준, 학생 증빙 절차와 실제 지급은 Phase 3 확정 전이다.

## 공통 원칙

- 게임은 누구나 플레이할 수 있다. 경품 수령 대상만 대학생으로 제한한다.
- 최초 기본권과 초대권은 별도 수량으로 표시한다. 초대권 최대 잔액은 3장이고, 새 초대 보상으로 3장이 되면 10시간 적립 대기가 시작된다.
- 첫 정상 검증 게임 뒤 공유를 기다리지 않고 복주머니를 열 수 있다. 복주머니 추첨은 행사·참가자당 한 번이다.
- 닉네임, 점수, 공개 경품명 외 연락처·학교·주소·인증 토큰은 공유 링크나 카드에 넣지 않는다.
- 동적 서버·설정 문자열은 `textContent`로 출력한다. 외부 링크는 검증된 HTTPS URL만 활성화한다.
- 하단 메뉴는 실제 링크이며 Tab·Enter 이동과 새 탭 열기를 지원한다. 현재 화면은 `aria-current="page"`로 알리고 키보드 초점을 표시한다.

## 화면별 계약

| 화면 | 목적과 주요 상태 | 주요 CTA / 보조 CTA | 표시 데이터와 API | 화면 이벤트 |
| --- | --- | --- | --- | --- |
| 초기 로딩 | 브랜드 흐름과 실제 데이터 준비를 분리한다. 약 2.5초 연출, 준비 지연, 연결 실패, 모션 감소 상태를 처리한다. | 자동 진입 / 실패 시 다시 연결 | `POST /api/observations`, `GET /api/config`, `POST /api/participants/anonymous`, `GET /api/me` | `entry_viewed`, `loading_data_ready`, `loading_intro_completed`, `loading_checkpoint`, `participant_ready`, `loading_ready` |
| 홈 | 기본권·초대권·최고점·복주머니 상태를 한눈에 표시한다. 진행 세션, 권리 없음, 쿨다운, 캠페인 중단·종료 상태를 구분한다. | 게임 시작 또는 진행 게임 복원 / 사용 가능한 복주머니 열기·기존 결과 보기, 조작 가이드 | `GET /api/me`로 복원된 `tickets`, `best_score`, `draw`, `pending_game_session`; 캠페인 설정 | `screen_entered`, `game_cta_clicked`, `draw_cta_clicked`, `screen_left` |
| 게임 | 서버가 승인한 세션에서 점프, 코인, 하트, 반복 부활을 진행한다. 저장·검증·장애 복구를 구분한다. | 점프와 플레이 / 장애 상태 확인·재시도 | `POST /api/game-sessions`, `POST .../start`, `POST .../checkpoint`, `POST .../finish`, `POST .../fault`, `GET .../game-sessions/{id}` | `game_start_approved`, `game_checkpoint`, `game_coin_collected`, `game_heart_collected`, `game_revived`, `game_completed`, `game_fault_reported`, `game_recovered` |
| 결과 | 이번 점수, 최고점, 현재 순위, 서버 `top3_gap`을 표시한다. `IN_TOP3`, `TOO_FEW`, `NO_SCORE`, `CHASING`과 `tied`를 각각 처리한다. TOP3 입력은 복주머니를 막지 않는다. | 복주머니 확인 / 기록 공유, 닉네임 수정, 잠정 TOP3 정보 접수 | `GET /api/leaderboard`, `PATCH /api/me/profile`, `POST /api/ranking/profile` | `top3_profile_started`, `top3_profile_submitted`; 공유 화면에서 `share_attempted` |
| 랭킹 | 검증된 최고점과 dense rank를 표시한다. 동점자는 같은 순위와 동점 표시를 받는다. 기록 없음과 통신 실패를 처리한다. | 잠정 TOP3 정보 접수 / 하단 내비게이션 | `GET /api/leaderboard`; `leaderboard`, `me`, `top3_gap`, `tie_policy` | `ranking_viewed`, 자동 화면 진입·이탈 |
| 초대·공유 | 일반 재도전 초대, 기록 공유, 경품 결과 공유 문맥을 분리한다. 지급·사용·환급, 유효 방문, 잔액, 쿨다운을 표시한다. | 네이티브 공유 / 링크 복사, 친구를 기다리지 않고 복주머니 열기·기존 결과 보기 | `GET /api/referrals/me`; `ticket_totals {granted,used,refunded}`, `invitation_balance`, `valid_visits`, `cooldown_until` | `invite_cta_viewed`, `share_attempted`, `draw_cta_clicked` |
| 복주머니·긁기 | `LOCKED`, `AVAILABLE`, `DRAWN`을 처리한다. 세 주머니 중 하나를 고르면 서버가 결과를 고정한다. 복귀 시 저장된 주머니와 결과를 복원하며 재추첨하지 않는다. | 선택한 주머니 열기, 긁기 / 키보드 또는 보조 결과 확인 | `GET /api/draws/me`, `POST /api/draws`, `PATCH /api/draws/{id}/scratch-complete` | `draw_entered`, `pouch_selected`, `scratch_started`, `scratch_reveal_requested`, `scratch_completed`, `draw_result_viewed` |
| 수령함 | 복주머니·랭킹 경품의 정보 대기, 접수, 검토, 연락, 지급, 보류, 부적격, 미응답 상태를 구분한다. API 실패·검증 실패 때 입력 모달을 닫지 않는다. | 합성 Preview 수령 정보 접수 / 접수 후 Gemini 가이드, 경품 결과 공유 | `GET /api/claims`, `POST /api/claims/{id}/submit` | `claim_form_started`, `claim_form_submitted` |
| Gemini 혜택 | 공식 혜택 URL과 공개 가이드를 소비자 언어로 제공한다. 미가입자와 기존 사용자 모두 가이드를 볼 수 있다. 링크가 없거나 HTTPS 검증에 실패하면 준비 중 상태를 표시한다. | 공식 혜택 페이지 / 복사, 공유, 공개 가이드 | `GET /api/config`; `benefit_url` 또는 `official_url`, `content_guides [{id,title,description,url,available}]` | `benefit_viewed`, `gemini_cta_viewed`, `gemini_cta_clicked`, `content_viewed`(카드 노출), `content_clicked`(외부 링크 클릭), `share_attempted` |

## 복귀·실패 상태

- 홈과 초대에서는 `/api/me`의 `draw.status`가 `AVAILABLE`이면 복주머니 열기, `DRAWN`이면 기존 결과 보기 버튼을 표시한다. `LOCKED`이면 숨기며 초대 현황 API 실패도 이미 확보한 복주머니 동선을 막지 않는다. 버튼 클릭은 추첨을 새로 실행하지 않고 상태 조회 화면으로 이동한다.
- 앱 활성화와 `pageshow`, 다른 탭의 상태 변경 알림에서 `/api/me`를 다시 읽어 게임권·쿨다운·추첨·진행 세션 상태를 갱신한다. 홈의 시작/복원 버튼도 즉시 갱신하고 초대 화면은 `/api/referrals/me`로 현황만 갱신해 공유 목적을 유지한다.
- 만료된 쿨다운은 대기 중으로 표시하지 않는다. 새 쿨다운 안내는 게임·수령 폼을 방해하지 않는 화면에서 한 번 표시한다.
- 화면을 이동한 뒤 도착한 API 성공·실패가 현재 화면과 모달을 덮지 않는다. 같은 화면에 재진입해도 요청 당시 화면 토큰을 기준으로 판정한다.
- 진행 게임은 새 권리를 소비하지 않고 같은 세션으로 복원한다. 장애 환급은 정상 종료나 자발적 이탈에 적용하지 않는다.
- 긁기 완료 저장이 실패해도 서버가 확정한 당첨 결과는 바뀌지 않는다. 같은 이벤트 ID로 완료 저장을 재시도한다.
- 수령·TOP3 폼은 필수 이름·연락처·학교의 빈 값, 동의 누락, API 실패에서 현재 입력을 보존한다. 주소는 필요한 경우에만 입력한다. Preview에서는 합성 정보만 받는다.
- 네이티브 공유가 없으면 복사를 시도한다. 클립보드도 없으면 사용자가 직접 복사할 수 있는 공개 URL을 표시한다.

## 공유 링크와 공개 메타데이터

| 문맥 | URL | 사용자 문구 | 공개 가능 데이터 |
| --- | --- | --- | --- |
| 재도전 초대 | `/invite/{code}?link=retry_invite&share={opaque_id}` | 친구가 유효 방문하면 재도전권 적립 | 캠페인명, 일반 초대 문구 |
| 기록 공유 | `/invite/{code}?link=record_share&share={opaque_id}` | 내 최고 기록에 도전 | 공개 닉네임, 검증된 점수 |
| 경품 결과 공유 | `/invite/{code}?link=prize_share&share={opaque_id}` | 내 복주머니 결과 확인 | 공개 동의된 경품명, 일반 결과 문구 |

`share`는 8–128자의 불투명 식별자다. OG 조회는 읽기 전용이어야 하며 참가자 생성, 유효 방문 인정, 초대권 지급을 일으켜서는 안 된다. 연락처, 학교, 주소, 비공개 수령 URL, 쿠키·토큰은 메타데이터에서 제외한다.

## 아직 검증하지 않은 항목

- 320/390/768/1440px 실제 브라우저 잘림, 실제 iOS·Android·인앱 브라우저, 스크린리더 조작은 이 문서 작성 과정에서 실기기 검증하지 않았다.
- 최종 경품 재고·확률, 대학생 증빙 방식, 운영 기간, 동점 수상 규칙, 개인정보 운영 문구는 Phase 3 결정이 필요하다.
- Preview 전체 흐름과 실제 API를 연결한 브라우저 E2E, 원격 Preview, 실제 지급은 별도 검증 대상이다.
