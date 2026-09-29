# 2026-09-29 수동 테스트 실행 매핑

작성 기준: `manual-test-cases.md` 168개 + `manual-test-server.md` 49개 = 217개 ID.

**판정 방법:** 아래에는 관련 회귀 파일과 이번 직접 확인 범위를 함께 기록한다. 파일 전체 통과가 각 행의 모든 기기·입력·운영 조건의 통과를 뜻하지 않는다. 직접 확인하지 못한 조건은 대기로 남긴다. 종합 결과·증거는 [실행 보고서](test-run-2026-09-29.md)를 참조한다. 부하 테스트는 보류한다.

## 현재 알려진 차단·실패

- `RK-02`: 동점 선달성 우선이 현재 `dense_rank`에 미구현.
- `AD-09`: 최종 랭킹 스냅샷·지급 생성 미구현.
- `AN-*` 관련: 가이드 공유의 `source: content`가 서버 허용값과 불일치해 `INVALID_DIMENSIONS` 발생 가능.
- `SV-048`: 입력 검증 경계 실패가 현재 실패 목록에 있음.
- `SV-049`: 닉네임 개행 허용 회귀가 현재 실패 목록에 있음.
- `SV-047` 및 `OP-08`: 부하 관련 항목은 사용자 지시대로 보류.

## 화면·운영 수동 시나리오

| ID | 자동 회귀 근거 | 남은 수동/운영 조건 |
| --- | --- | --- |
| EN-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 부분 확인: 기존 참가자 Chrome 공개 진입·이미지·홈 정상. 새 참가자는 사용자 Safari 공유까지 확인. 로딩 모든 실패 변형은 회귀 근거. |
| EN-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 수정 필요 QA-05: 로딩 소개가 표시되지만 복권에 옛 행사당 1회 문구. 장면별 촬영 시간 측정은 미실행. |
| EN-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| EN-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| EN-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 직접 확인: 기존 베타 새로고침 후 홈·894점·초대권2장 유지, 수령함 강제 이동 없음. 탭 완전 종료 조합은 미실행. |
| EN-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 부분 확인: 직접 혜택 진입·메뉴 이동 정상. 모든 deep link 재시작 조합은 회귀 근거. |
| EN-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| EN-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실기기 관찰: 시크릿 카카오 공유에서 다운로드 안내, 일반 Safari는 성공. 시크릿 전체 종료 후 신규 ID 검사는 미실행. |
| EN-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| EN-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| EN-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_shell.test.cjs, frontend_phase2_navigation_failures.test.cjs` | 직접 확인: 공개 베타 브라우저 진입과 비인증 health/config 200, Vercel 로그인 벽 없음. |
| HM-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 직접 확인: Chrome 390px·PC 홈 이미지 정상, 게이트러너 메뉴 없음. |
| HM-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 직접 확인: 하단 5개 메뉴 및 중앙 로고 홈 이동. 링크 새탭 변형은 별도 대기. |
| HM-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 직접 확인: 게임 시작에서 가이드 먼저 열림. |
| HM-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| HM-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 부분 확인: 베타 무제한 유지. 제한/무제한 전환은 격리 서버 회귀. |
| HM-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| HM-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| HM-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_views.test.cjs, frontend_phase2_shell.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GU-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 부분 확인: 4장 설명·실제TOP3 표시, 건너뛰기 시작 완료. 마지막 장 시작 버튼 경로는 회귀 근거. |
| GU-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 부분 확인: 첫 이전 비활성·이전 이동 정상. 물리 스와이프는 대기. |
| GU-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 직접 확인: X 닫기→재열기 1장→건너뛰기 게임→다음 게임에도 가이드. |
| GU-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 부분 확인: 실제TOP3 1266/1093/894와 내3위 정상. 빈 랭킹·동점 fixture는 회귀 근거. |
| GU-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GU-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_guide.test.cjs` | 개선 QA-06: 390/320px 경품명 줄바꿈 어색함. 좁은 화면 modal 스크롤 필요. 전체 실기기·키보드 대기. |
| GM-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 부분 확인: 실제 베타 게임·32점 정상 완료. 전체 입력 방식·스테이지는 회귀 근거. |
| GM-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 부분 확인: pointer 점프 입력 경로·버튼 CSS 확인. 실제 길게 누르기 반복 선택은 QA-10 실패. |
| GM-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실기기 실패 QA-10: 점프 더블탭 선택 발생. jump_button_touch_regression.test.cjs 3개 포함 JS 225개 통과한 로컬 보완본 준비. 미배포·실기기 재확인 대기. |
| GM-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-13 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-14 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| GM-15 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_v2.test.cjs, game_v21.test.cjs, dino_only.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 부분 확인: 베타 게임 준비 중 새로고침 후 홈 복구·다시 시작. 유료권 아닌 무제한 조건이며 환급 원장은 격리 테스트. |
| TK-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| TK-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 부분 확인: 무제한 베타 실제짧은게임·재시작 후 기존 초대권2장 유지. 정확한 원장 변형은 서버 회귀. |
| TK-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, frontend_phase1_followup.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 직접 확인(Chrome390px): 이번판/배지/닉네임 변경 없음, 점수32·최고894·3위 유지. |
| RS-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 부분 확인: 무제한32점 결과에서 재도전→카톡→복주머니, 재도전시 가이드. 제한100/101은 서버/화면회귀. |
| RS-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 부분 확인: TOP3 안내가 수령폼보다 앞. 기존최고기록상태이며 신규TOP3 폭죽 실기기는 대기. |
| RS-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RS-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_top3.test.cjs, frontend_phase2_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RK-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 부분 확인: 실제 랭킹과 경품3개 조회. 최신 선달성 동점은 QA-01. |
| RK-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 실패 QA-01: 현재 dense_rank 공동 순위. 새 선달성 정책 미구현. |
| RK-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 부분 확인: 베타 내894점·3위·참가15명 표시. 모든 순위/시간차 변형은 회귀 근거. |
| RK-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RK-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| RK-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `game_rank_target.test.cjs, frontend_phase2_top3.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| IV-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_referral_share.test.cjs, frontend_phase2_views.test.cjs` | 직접 확인: 초대·랭킹 모두 내3위 TOP3, 초대2장·누적2·전송2 표시. |
| IV-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_referral_share.test.cjs, frontend_phase2_views.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| IV-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_referral_share.test.cjs, frontend_phase2_views.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| IV-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_referral_share.test.cjs, frontend_phase2_views.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| IV-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_referral_share.test.cjs, frontend_phase2_views.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 부분 확인: 사용자 DRAW→테스트커피 자랑 카드 잘 나옴 보고. 전 위치 수신카드 캡처 대조는 미실행. |
| SH-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 직접 확인: 친구 전송 GAME 잔액3 cap차단; 새Safari MultiChat GAME+1/DRAW0. 원장 일치. |
| SH-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 부분 확인: 사용자 실제 MultiChat GAME+1/DRAW0. 단톡 DRAW·여러 방 동시선택은 실제 미실행. |
| SH-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 부분 확인: 실제 claim MemoChat REJECTED/NOT_ELIGIBLE·접수미완료·보상0 확인. 취소/방문/복사는 회귀 근거. |
| SH-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 직접 확인: DirectChat DRAW+1/GAME0, 사용자가 이어2회차 추첨·테스트커피PRIZE 공개 완료. |
| SH-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 확인: 일반·상품 자랑·claim 친구 전송 모두 게임권/뽑기권 0. claim은 친구 전송 후 접수 완료. |
| SH-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| SH-13 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_share_async.test.cjs, frontend_referral_share.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 부분 확인: 기존 공개완료 결과1/10회 재접속 복원. 실제 긁기/대체버튼 새결과는 사용자 테스트 및 회귀 근거. |
| DR-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 직접 확인: Gemini혜택 수령폼없음·적용하기·DRAW공유 가능, 실제DRAW +1 검증. |
| DR-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 직접 확인(사용자): 공유로받은권리 사용→2회차 테스트커피, 추가뽑기소비1. 원장 결과 대조. |
| DR-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 부분 확인(사용자): 테스트커피PRIZE 공개·자랑정상, 보상0. 남은권리차단/재접속은 서버회귀. |
| DR-13 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-14 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-15 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| DR-16 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase3_draw.test.cjs, scratch_card_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 부분 확인: 기존Gemini1회차 수령함과결과보기 정상. 완전신규/권리보유형은대기. |
| CL-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 확인: 저장 후 나에게 보내기는 2단계 유지, 친구 전송 후 3단계. 서버 INFORMATION_RECEIVED·연락처 제출 시각 존재·권리 추가 0. |
| CL-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 부분 확인: 자기 전송 제외 후 다시 친구 전송하여 접수 완료. 공유창 취소 후 닫기·재진입의 전체 초안 복원 조건은 미확인. |
| CL-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| CL-13 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_claim_empty.test.cjs, frontend_phase2_admin_recovery.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| BN-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 직접 확인: 혜택배지·링크상자·복사공유·접속버튼·가이드두개 정상. |
| BN-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 직접 확인: 단축주소→Google공식학생페이지, 캠페인값유지. 가입/결제하지않음. |
| BN-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 부분 확인: 혜택주소복사성공·완료알림. 링크옆실제공유카드별도대기. |
| BN-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 부분 실패 QA-03: 가이드두주소복사성공. source content 분석거절 재현; 실제외부본문 QA-04. |
| BN-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 준비 대기 QA-04: 두Notion주소앱안내에서브라우저사용눌러도본문미확인. 비공개단정아님. |
| BN-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 부분 확인: 사용자의general DirectChat NO_REWARD. 위치별카드캡처없음. |
| BN-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| BN-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| BN-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_benefit_visibility.test.cjs, frontend_phase3_draw.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 최종 스냅샷·지급 구현 및 운영 승인 필요 |
| AD-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AD-13 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_admin_recovery.test.cjs, ui_modal_lifecycle.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 부분 확인: 모든메뉴·뒤로가기·홈새로고침정상. 전체앞으로/히스토리조합회귀. |
| NV-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 직접 확인: 베타카운트다운도중홈이동후홈유지. 사용한권리환급은무제한외별도회귀. |
| NV-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| NV-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 부분 확인/개선 QA-06: 320/390/1280px 가로넘침없음, 가이드경품줄바꿈어색함. 200%글꼴대기. |
| NV-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실기기 일부 확인: Safari 단톡 공유와 접수 완료 복귀 성공. 점프 더블탭 선택 QA-10은 로컬 수정 후 배포·재확인 대기. Android 미검증. |
| NV-11 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 부분 확인: Chrome1280px 정상·이미지깨짐0. SafariPC·키보드전체대기. |
| NV-12 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_phase2_navigation_failures.test.cjs, frontend_phase2_game_async.test.cjs` | 실제 UI·모바일·네트워크 조건 수동 대기 |
| AN-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 실패 QA-03: 두가이드copy/share source content 거절, consolewarn2건 및서버함수202 rejected재현. |
| AN-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 부분 확인: 실제GAME/DRAW/NONE+원장대조성공. 관리자퍼널전체는자동/격리근거. |
| AN-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| AN-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `frontend_analytics_delivery.test.cjs, frontend_tracking_acceptance.test.cjs` | 분석 집계·브라우저 이동·배치 rejection 수동 대기 |
| OP-01 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 설정 기록·자동 경계검사: 새KST일정설정초안반영. 원격베타null·본행사OFF; 실제운영환경활성전대기. |
| OP-02 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 결정 대기: 마감전시작후완료·늦은웹훅·접수마감. |
| OP-03 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 정책확정/구현대기: 동점선달성. 자격·차순위·미응답미정. |
| OP-04 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 준비 대기: 77+3은설계수량, 실재고확보·적재미검증. |
| OP-05 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 결정/구현 대기: 베타와본행사데이터처리, productionguard. |
| OP-06 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 결정 대기: 개인정보보관삭제·증빙·담당문의처. |
| OP-07 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 부분 확인: Google링크열림, Notion본문미확인·표현승인별도. |
| OP-08 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 보류: 사용자지시로실제부하미실행. |
| OP-09 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 운영 정책·환경·승인 또는 부하 조건 필요 |
| OP-10 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py, test_phase3_preflight.py, test_load_guards.py` | 오픈미완료: 실패·미정·실기기·부하보류항목유지. |

## 서버·운영 수동 시나리오

| ID | 자동 회귀 근거 | 남은 수동/운영 조건 |
| --- | --- | --- |
| SV-001 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_config.py` | 자동 확인: health/config 비밀 비노출 및 설정 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-002 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_config.py` | 자동 확인: Origin, HTTPS, Secure 쿠키, 로컬 HTTP 예외 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-003 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_kakao_config.py` | 자동 확인: 카카오 설정 조합 fail-closed 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-004 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_database_connections.py` | 자동 확인: DB pool, transaction, retry 경계 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-005 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_rate_limit_buckets.py` | 자동 확인: rate-limit bucket 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-006 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_schema_guard.py` | 자동 확인: schema/environment guard와 역할 권한 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-007 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py` | 자동 확인: observation/bootstrap/anonymous 멱등 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-008 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_regressions.py`, `test_backend_phase1.py` | 자동 확인: 잘못된·만료·차단 쿠키 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-009 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_regressions.py`, `test_backend_phase1.py`, `test_backend_security_regression.py` | 자동 확인: 참가자별 소유권 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-010 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_regressions.py`, `test_backend_phase1.py` | 자동 확인: 관리자 권한·캐시 재검사 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-011 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_concurrency.py`, `test_backend_phase1.py` | 자동 확인: 예약 멱등·동시 요청 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-012 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_phase2.py`, `test_game_verifier_v2.py` | 자동 확인: 시작·체크포인트·완료 순서 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-013 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_security_regression.py`, `test_game_verifier_safety.py`, `test_game_verifier_v2.py` | 자동 확인: 서버 점수 검증과 TIME_LIMIT 종료 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-014 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase2.py`, `test_game_verifier_v2.py`, `test_game_verifier_v21.py` | 자동 확인: 검증기 2.0.0/2.1.0 분리 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-015 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py` | 자동 확인: 100점 이하 환급과 정상 소비 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-016 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_boundaries.py`, `test_backend_phase1.py` | 자동 확인: 이탈·장애·만료 복구 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-017 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_boundaries.py`, `test_backend_phase1.py` | 자동 확인: 장애 검토 expected_version 충돌 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-018 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_boundaries.py`, `test_backend_concurrency.py`, `test_backend_phase1.py` | 자동 확인: 추천 방문 중복·자기초대 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-019 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_phase3.py` | 자동 확인: GAME/DRAW/NONE 목적별 공유 원장 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-020 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_kakao_webhook_security.py`, `test_backend_phase1.py`, `test_backend_security_regression.py` | 자동 확인: 웹훅 서명·위조·중복·나에게 보내기 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-021 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_boundaries.py`, `test_backend_concurrency.py`, `test_backend_phase1.py` | 자동 확인: 게임권 상한·쿨다운·동시 콜백 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-022 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py` | 자동 확인: 10회 경계에서 DRAW 콜백 경쟁 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-023 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_kakao_webhook_security.py`, `test_backend_phase1.py` | 실제 확인: GAME 단톡 +1/DRAW 0, DRAW 친구 +1/GAME 0, 일반·상품 NONE, 자기 전송 제외, claim 친구 전송 접수 완료. 모든 종류×방 조합은 미실행. |
| SV-024 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_phase2.py`, `test_backend_security_regression.py`, `test_metrics_acceptance.py` | 새 정책 실패 QA-01: 현재dense_rank; 기존버전/비공개보호회귀통과와구분. |
| SV-025 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_phase2.py`, `test_backend_security_regression.py` | 자동 확인: TOP3 연락처·동의·출처·소유권 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-026 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_phase2.py`, `test_backend_security_regression.py`, `test_metrics.py`, `test_metrics_acceptance.py`, `test_phase2_metrics.py` | 서버 분석 검증 회귀 통과. 실제 화면 가이드 복사 source:content는 INVALID_DIMENSIONS 거절을 별도 재현(QA-03). |
| SV-027 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase2.py`, `test_metrics.py`, `test_metrics_acceptance.py`, `test_phase2_metrics.py` | 자동 확인: 퍼널/CTR/공유 목적 분리 집계 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-028 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_metrics.py`, `test_phase2_metrics.py` | 자동 확인: 추천 원장·쿨다운 집계 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-029 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_regressions.py`, `test_backend_phase1.py`, `test_backend_phase3.py` | 자동 확인: 최초 추첨·회차 멱등 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-030 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py` | 자동 확인: 응답 유실 후 같은 회차 재시도 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-031 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py` | 자동 확인: 혜택 반복·실제 상품 후 종료 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-032 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_acceptance_regressions.py`, `test_backend_concurrency.py`, `test_backend_phase1.py`, `test_backend_phase3.py` | 자동 확인: 마지막 재고·동일 참가자 동시 추첨 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-033 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py`, `test_phase3_pool_depletion.py` | 자동 확인: 별도 DB에서 5,000칸 전량 소진 정합성 검증. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-034 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py` | 자동 확인: 잘못된/누락 풀의 fail-closed 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-035 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase3.py`, `test_migration_acceptance.py` | 자동 확인: 구버전 단일 추첨 원장 정산 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-036 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase2.py`, `test_claim_status_followup.py` | 자동 확인: 수령 초안 저장·소유권·제출 선행 조건 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-037 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase2.py`, `test_claim_status_followup.py` | 자동 확인: 접수 완료 동시성·상태 보존 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-038 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase2.py`, `test_claim_status_followup.py`, `test_phase3_claim_payment.py` | 자동 확인: 관리자 상태 전이·version 보호 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-039 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_security_regression.py`, `test_phase3_claim_payment.py` | 자동 확인: VERIFIED/reference/delivery/reason과 재고 원자성 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-040 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_claim_payment.py` | 자동 확인: PAID 증거 철회·중복 지급 차단 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-041 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_claim_status_followup.py`, `test_migration_acceptance.py`, `test_schema_guard.py` | 자동 확인: 최신 11개 migration 신규 적용·보존·재적용 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-042 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_campaign_window.py` | 자동 확인: DB 시계 기준 시작 포함·종료 제외 경계 테스트. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-043 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_phase3_preflight.py` | 일정 반영 후 preflight 10/10 통과, 형식 오류 0. 미완료 조건이 남아 --require-launch-ready 종료 코드 1로 정상 차단. |
| SV-044 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_config.py`, `test_cohort_guards.py`, `test_phase3_preflight.py` | 자동 확인: environment/campaign/synthetic guard 분리 검사. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-045 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_cohort_guards.py`, `test_load_guards.py`, `test_phase2_load.py` | 자동 확인: load 도구 dry-run 대상 보호, 네트워크 호출 0. 모든 수동 입력·운영 조합 완료와는 구분. |
| SV-046 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_cohort_guards.py`, `test_load_guards.py`, `test_phase2_load.py` | 예산·재개 단위 회귀 통과. 고정 DB 이름과 기존 DB 충돌로 코호트 재개 opt-in 1건 미실행. |
| SV-047 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_load_guards.py`, `test_phase2_load.py` | 보류: 사용자지시로로컬/원격실부하시나리오미실행. 단위guard검사는실행. |
| SV-048 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_security_regression.py` | 실패 QA-07: 쿼리21개 파싱예외가500. 나머지보안회귀는backend보고서. |
| SV-049 | 관련 자동 회귀(개별 수동 합격 증거 아님) · `test_backend_phase1.py`, `test_backend_security_regression.py` | 실패 QA-08: 숨겨진프로필API 개행닉네임허용. UI변경하지않음. |

## 실행 증거 범위

- JavaScript: 수정 후 `.local/phase3/qa-20260929-frontend-after-touch.tap`의 225개 통과. 실기기 선택 UI 해결을 증명하는 결과는 아니다.
- Python: 기본 245개 통과 후 별도 격리 풀 1개 통과. 총 246/247 실행 통과, 기존 DB와 이름이 충돌하는 코호트 재개 1개 미실행.
- 이 문서는 결과를 선통과로 기재하지 않으며, root가 실제 UI/K 검증 후 각 ID 결과를 갱신한다.
