# Preview 실제 브라우저 검증

검증일: 2026-09-25. Codex In-app Browser에서 합성 데이터만 사용했다.

## 전체 흐름 — b3d404a

- 실제 공룡 엔진 충돌로 32점 완료, 서버 검증 통과 및 기본권 1→0 확인.
- 잠정 TOP3 합성 연락 정보 접수, 관리자 업무 표에서 확인.
- 참가자당 복주머니 한 번 확정, NO_PRIZE 결과·스크래치 완료·재접속 결과 유지 확인.
- 초대 링크 복사 성공, Gemini 혜택 버튼의 실제 외부 페이지 이동 및 서버 이벤트 확인.
- 390×844 화면에서 문서·본문 너비 390px, 가로 넘침 없음.
- 새로고침 뒤 쿠키 참여자·게임권 0장·최고 점수 32점 복원.
- 관리자 1: 실제 Supabase Auth 로그인, 장애 환급 승인 및 대기 목록 제거.
- 관리자 2: 실제 Supabase Auth 로그인, 상세 지표, TOP3 접수 업무 확인.
- 관리자 2: 합성 DRAW 수령 건을 정보 접수→확인 대기→연락 완료→지급 완료로 변경. 버전 4와 외부 전달 표시 유지 확인. 실제 연락·경품 발송 없음.

## 화면 상태 수정 — da3fbf4

배포 `dpl_GneVTuefhMAZp4wv6JZEvaUAwgWS`에서 확인했다. 서버 성능 판정과 별개다.

- 실제 게임 종료 32점 및 검증 완료 확인.
- 합성 TOP3 접수 직후 결과 화면이 비활성 ‘정보 접수 완료’ 버튼으로 갱신됨.
- 홈으로 이동하면 기본권 0장·초대권 0장·최고 점수 32점과 비활성 ‘게임권이 필요해요’ 버튼 표시.
- 이미 종료된 게임에 대한 ‘진행 중 게임 복원’ 버튼이 남지 않음.

실제 기기의 프레임 속도와 모든 모바일 브라우저 호환성 검증은 포함하지 않는다.

## 2026-09-25 acceptance follow-up (local)

- Fresh Python server on localhost:3004, existing isolated browser DB.
- Actual browser loaded the saved participant and rendered the draw result, then navigated to the benefit screen.
- Official-link copy displayed `공식 혜택 링크를 복사했어요.`.
- Read-only database inspection confirmed `loading_ready` on loading, `gemini_cta_viewed`, and `share_attempted` with source=gemini and statuses attempted/copied.
- These are local UI/event checks, separate from remote load results.

## User co-test on 78ce9be Preview

- The 200-VU burst was gated until the start announcement was sent.
- User explicitly reported: “화면과 게임이 정상으로 보였어.”
- Load runner separately observed 17 HTTP 503 responses at game creation/start and stopped after 2.45 seconds of the burst.
- A normal user observation does not override the load failure; see phase1-remote-load-burst-pool.json.

## 최종 사용자 공동 확인 — 4fd36f4

- 배포: `dpl_2FdJVqEqL3Hw169mS1ADkjBj5m1w`, `https://dino-nanobanana-3uflg1xa6-henry-kils-projects.vercel.app/`.
- 시작 알림 뒤 200명 burst를 수행했고 200명 모두 게임·추첨 흐름 완료, 2,000호출 중 서버 오류·timeout·429는 0건이었다.
- 사용자가 이 Preview를 직접 플레이하고 “게임 못할 정도는 아니고 스테이지 넘어갈 때마다 약간 멈춤있는데 200명 동시 접속이 흔한 건 아니니까 이정도면 괜찮을 듯”이라고 평가했다.
- 이어서 실제 최종 브라우저 결과 화면에서 `기록 검증 완료`, 이번 판 250점, 최고 250점, 현재 2위, 게임권 0장, 잠정 TOP3 정보 요청과 복주머니 확인 버튼을 읽어 확인했다. 사용자 게임을 재실행하거나 결과를 변경하지 않았다.
- 사용자 체감과 자동 시험 결과를 근거로 1차 테스트를 마무리한다. 원래 일반 API p95 1초 목표 미달은 그대로 기록한다.
- 코드 확인상 `public/js/game/engine.js`의 스테이지 전환은 게임 루프 안에서 동기적으로 실행되며 의도된 pause는 없다. `public/js/views/game_view.js`의 스테이지 콜백은 배지/flash 표시를 변경하고 API 응답을 기다리지 않는다. 별도 체크포인트 요청은 5초 interval이다.
- 따라서 사용자가 느낀 끊김을 서버 부하 때문이라고 확정하지 않는다. 실제 기기 FPS와 전환 지연 계측은 2차 후속 점검 항목이다.
- 이전 참가자·관리자 전체 브라우저 E2E 기록과 최종 사용자 플레이 확인을 구분한다. 최종 후보의 관리자 E2E 전체를 다시 수행했다는 의미는 아니다.
