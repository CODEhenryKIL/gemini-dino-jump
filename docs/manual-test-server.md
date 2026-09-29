# 공룡 점프 서버 수동 검증표

작성 기준: 2026-09-29

대상: 서버 개발자와 운영 검증 담당자가 함께 수행하는 API·DB·보안 검증

자동 검증 기준: `tests/test_*.py`의 파일별 검증 범위

## 1. 실행 원칙

- 이 문서는 **수동 검증 절차**다. 현재 247개 Python 테스트 정의의 모든 내부 분기와 입력 조합을 1:1로 옮긴 문서가 아니며 자동 테스트를 대체하지 않는다. 49개 수동 시나리오가 각 테스트 파일의 사용자 관찰 가능 범위를 묶어 검증한다. 동시성, 5,000자리 소진, 연결 장애처럼 사람이 정확히 재현하기 어려운 항목은 자동 테스트 결과를 함께 확인한다.
- 데이터 생성·상태 변경·위조·재고 소진·부하 관련 검증은 로컬 전용 또는 매번 새로 만든 **격리 테스트 DB와 테스트 서버**에서만 수행한다.
- 공개 베타와 원격 Supabase에는 가짜 카카오 웹훅, 5,000회 소진, 강제 재고 경쟁, 대량 익명 참가자 생성, 부하 요청을 보내지 않는다.
- 운영 비밀, 쿠키 원문, 연락처, 학교, 주소, 카카오 콜백 토큰은 화면 캡처·터미널 기록·결과 문서에 남기지 않는다. 참가자와 요청은 앞 6자리만 마스킹해 기록한다.
- DB 확인은 아래에 적은 `SELECT`만 사용한다. 수동 `INSERT`, `UPDATE`, `DELETE`, 전체 초기화와 down migration은 금지한다.
- 상태 변경 요청에는 서로 다른 `Idempotency-Key`를 임의 생성하지 않는다. 재시도 검증에서는 **같은 키와 같은 본문**을 사용한다.
- 2026-09-29 실제 카카오 친구·단체방 GAME/DRAW/NONE과 수령 접수 결과는 [실행 보고서](test-run-2026-09-29.md)에 기록했다. 부하는 계속 보류한다. 행사 일정과 동점 선달성 정책은 확정됐으며, 종료 경계 게임·늦은 웹훅·수령 기한 등은 미정이다.

### 공통 준비

1. 격리 서버의 `/api/health`가 정상이고 `/api/config`의 환경이 의도한 로컬·테스트 환경인지 확인한다.
2. 브라우저 A와 B는 쿠키 저장소가 분리된 프로필을 사용한다.
3. API 요청은 브라우저 개발자 도구 또는 비밀을 출력하지 않는 로컬 클라이언트로 보낸다.
4. 관리자 검증은 테스트 관리자 계정과 필요한 최소 권한만 사용한다.
5. 아래 결과 칸은 실제 수행 뒤 `통과`, `실패`, `보류` 중 하나와 증거 위치를 기록한다.

### 요청 fixture 작성 기준

- 임의의 운영 ID나 개발자 도구에서 복사한 오래된 요청을 재사용하지 않는다. 격리 DB에서 새 참가자·session·claim을 만들고, 해당 응답의 opaque ID를 다음 단계에 전달한다.
- 익명 시작은 `POST /api/observations`의 `{event_id, observation_id, link_kind, channel_code}`와 32자 이상 `Idempotency-Key`로 받은 `{bootstrap_token}`을 `POST /api/participants/anonymous`의 `{bootstrap_token, observation_id, link_kind, channel, invite_code?, share_id?}`에 전달한다.
- 게임 완료 fixture는 `tests/test_backend_security_regression.py`의 HTTP helper와 `tests/js_v2_fixture_runner.cjs`가 만드는 `{score, ticks, jump_ticks}` 형식을 따른다. 점수·tick을 손으로 맞춰 검증 성공을 가장하지 않는다.
- 수령 정보 fixture는 일반 claim 초안의 `{name, contact, school, address?, consent:true, notice_version:"claim-contact-v1"}`와 TOP3의 `{name, contact, school, consent:true, notice_version:"top3-contact-v1"}`를 구분한다.
- claim·fault·campaign 관리자 변경은 해당 조회 응답의 최신 `version`을 `expected_version`에 넣는다. 참가자 차단·세션 폐기는 숫자 version 대신 현재 `status`를 `expected_status`에 넣는다. 참가자 상태·claim ID·연락처·쿠키·토큰을 결과 문서에 그대로 복사하지 않는다.
- 카카오 웹훅 body와 헤더는 `tests/test_backend_phase1.py`와 `tests/test_backend_kakao_webhook_security.py`의 합성 fixture를 격리 서버에서만 사용한다. 공개 베타 요청을 캡처해 재전송하지 않는다.

---

## 2. 환경·설정·연결 보호

### SV-001 헬스체크와 공개 설정의 비밀 비노출

- **준비:** 격리 서버 기동, 비밀 환경 변수는 서버에만 설정한다.
- **동작:** `GET /api/health`, `GET /api/config`, `GET /api/shared/game_constants.json`을 호출하고 응답 본문·헤더를 확인한다.
- **예상 결과:** 헬스체크는 정상 상태를 반환한다. 공개 설정에는 환경, 공개 URL, 공개용 카카오 JavaScript 키처럼 허용된 값만 있고 DB 비밀번호, 서비스 역할 키, 쿠키 비밀, 카카오 어드민 키·웹훅 비밀은 없다.
- **결과:** ☐ 미실행

### SV-002 Origin·HTTPS·쿠키·혜택 URL 설정 경계

- **준비:** 허용 Origin 1개와 유사하지만 다른 Origin 1개를 준비한다.
- **동작:** 허용 Origin과 비허용 Origin에서 각각 쿠키가 필요한 API를 호출한다. 설정 로더에서 HTTP 혜택 주소, 와일드카드 Preview Origin, 범위를 벗어난 쿠키 수명, 요청만으로 켜지는 무제한 옵션을 각각 시도한다.
- **예상 결과:** Preview는 정확히 허용한 HTTPS Origin만 통과한다. 로컬·테스트 환경은 `localhost`, `127.0.0.1`, `::1`의 HTTP Origin을 허용한다. 와일드카드·유사 도메인·HTTP 혜택 주소·부적절한 쿠키 설정은 서버 시작 또는 요청 단계에서 거부된다. Preview 무제한은 명시된 비공개 설정에서만 켜지고 요청 헤더로 바뀌지 않는다.
- **결과:** ☐ 미실행

### SV-003 카카오 설정 조합의 fail-closed 동작

- **준비:** 격리 환경에서 공개 JavaScript 키만 있는 설정, 웹훅 자격 두 값이 모두 있는 설정, 한 값만 빠진 설정을 각각 준비한다. 실제 운영 키는 사용하지 않는다.
- **동작:** 각 설정으로 서버 설정 검증과 `GET /api/config`를 확인한다.
- **예상 결과:** JavaScript 키는 선택 사항이다. 공식 웹훅 처리는 필요한 자격이 모두 있을 때만 활성화된다. 일부만 있거나 형식이 잘못된 비밀·사설 설정은 거부되며 공개 응답에는 비밀이 나오지 않는다.
- **결과:** ☐ 미실행

### SV-004 DB 연결 풀·트랜잭션 격리·재시도 한계

- **준비:** 격리 DB, 작은 연결 풀, 정상 요청 2개와 의도적으로 끊을 테스트 연결을 준비한다.
- **동작:** 병렬 읽기 요청을 보내고 한 연결을 중간에 종료한다. 연결 admission 실패와 요청 처리 중 연결 실패를 구분해 관찰한다.
- **예상 결과:** 트랜잭션과 커서는 요청 간 공유되지 않는다. 만료·끊긴 연결은 재사용되지 않는다. 연결 admission 단계의 제한된 오류만 bounded retry 대상이며, 본문을 이미 처리한 쓰기 요청은 자동 재실행되지 않는다. 풀 종료 후 연결이 남지 않는다.
- **결과:** ☐ 미실행

### SV-005 요청 속도 제한 버킷

- **준비:** 같은 테스트 IP의 익명 부트스트랩, 일반 참가자, 관리자 요청을 준비한다.
- **동작:** 각 종류를 정해진 한도까지 연속 호출한 뒤 한 번 더 호출한다. 다른 참가자 쿠키로도 같은 IP에서 확인한다.
- **예상 결과:** IP 공유 버킷과 주체별 버킷이 의도대로 분리된다. 초과 요청은 재시도 가능한 `429`와 제한 정보를 반환하며, 속도 제한 때문에 참가자 소유권이나 관리자 권한이 섞이지 않는다.
- **결과:** ☐ 미실행

### SV-006 스키마·환경 guard와 전용 역할

- **준비:** 최신 migration을 적용한 격리 DB와 필수 전제 버전이 빠진 새 DB를 각각 준비한다.
- **동작:** 앱 역할로 서버를 연결하고 스키마 검사를 수행한다. 빠진 DB에도 같은 검사를 수행한다.
- **예상 결과:** 최신 버전과 전용 `dino_dev` 스키마·`dino_dev_app` 역할은 통과한다. 전제 migration이 빠졌거나 환경·캠페인·역할이 다른 연결은 시작 전에 거부된다. `environment_guard`·`admin_member` 변경과 `ticket_ledger` 기존 행 UPDATE는 DB 권한으로 거부된다. 원장·이력은 backend 역할에 SELECT/INSERT만 허용된다. `inventory_item`은 backend 역할이 트랜잭션 안에서 갱신하도록 권한이 있으므로, 이 항목을 DB 역할 자체가 재고를 변경할 수 없다는 보장으로 해석하지 않는다.
- **확인용 SELECT:** `SELECT version FROM dino_dev.schema_version ORDER BY applied_at;`
- **결과:** ☐ 미실행

---

## 3. 익명 참가자·쿠키·소유권

### SV-007 익명 참가자 최초 생성과 bootstrap 재사용

- **준비:** 쿠키가 없는 브라우저 A, 32자 이상 고정 `Idempotency-Key`, 새 `event_id`·`observation_id`.
- **동작:** 먼저 `POST /api/observations`를 같은 키·같은 본문으로 두 번 호출한다. 응답의 같은 `bootstrap_token`과 `observation_id`를 사용해 `POST /api/participants/anonymous`를 두 번 호출한 뒤 `GET /api/me`를 호출한다.
- **예상 결과:** observation과 참가자는 각각 하나만 생성되고 최초 게임권도 한 번만 지급된다. 같은 bootstrap proof 재사용은 같은 참가자를 반환한다. 쿠키는 `HttpOnly; SameSite=Lax`이고 Preview에서만 `Secure`가 추가된다. 로컬 HTTP 검증에서는 `Secure`가 붙지 않는다.
- **결과:** ☐ 미실행

### SV-008 잘못된·만료된·차단된 쿠키 처리

- **준비:** 변조 쿠키, 만료 참가자 쿠키, 관리자가 차단한 참가자 쿠키를 격리 DB에 준비한다.
- **동작:** 각 쿠키로 `GET /api/me`와 이전에 성공했던 쓰기 요청 재시도를 호출한다. 참가자 행만 삭제된 테스트 초기화 사례에서는 새 observation과 아직 유효한 fresh bootstrap proof를 사용해 `POST /api/participants/anonymous`를 호출한다.
- **예상 결과:** 잘못됐거나 만료된 쿠키는 `401 SESSION_INVALID`, 유효하지만 차단된 참가자의 active 요청은 `403 PARTICIPANT_BLOCKED`다. fresh bootstrap이 있어도 DB에 기존 차단·만료 참가자 행이 남아 있으면 새 신원으로 교체하지 않는다. 테스트 초기화로 쿠키가 가리키는 참가자 행 자체가 사라진 경우에만 fresh bootstrap proof로 새 참가자를 만들 수 있다.
- **결과:** ☐ 미실행

### SV-009 참가자·게임·초대·수령 정보 소유권

- **준비:** 브라우저 A와 B, A 소유의 game session·share intent·claim draft를 준비한다.
- **동작:** B 쿠키로 `GET /api/game-sessions/{id}`, `GET /api/referrals/share-intents/{id}`, `GET /api/claims/{id}/draft`, A의 observation을 사용하는 게임 시작을 시도한다.
- **예상 결과:** 모두 소유권 오류로 거부되며 데이터 존재 여부나 개인정보를 노출하지 않는다. B의 상태·게임권·원장에는 변화가 없다.
- **결과:** ☐ 미실행

### SV-010 관리자 권한과 캐시 재검사

- **준비:** 읽기 전용 관리자와 `claims:write` 관리자를 준비하고, 성공한 관리자 요청의 멱등 키를 보관한다.
- **동작:** 권한이 없는 계정으로 변경 API를 호출한다. 쓰기 권한 계정의 권한을 회수한 뒤 같은 요청을 재시도한다.
- **예상 결과:** 읽기 전용 계정은 변경하지 못한다. 권한 회수 후에는 과거 성공 캐시가 있어도 현재 권한을 다시 확인해 거부한다.
- **결과:** ☐ 미실행

---

## 4. 게임 검증·게임권·장애 복구

### SV-011 게임 예약의 멱등성과 동시 요청

- **준비:** 게임권 1장인 참가자, 같은 `Idempotency-Key`를 쓰는 두 요청 창.
- **동작:** `POST /api/game-sessions`를 같은 참가자·같은 `Idempotency-Key`로 거의 동시에 두 번 보낸다. 소유한 `observation_id`와 타인의 `observation_id`도 각각 본문에 넣어 비교한다.
- **예상 결과:** session은 하나만 생성되고 게임권 예약도 한 번만 반영된다. 응답 유실 뒤 같은 키 재시도는 같은 session을 반환한다.
- **결과:** ☐ 미실행

### SV-012 시작·체크포인트·완료의 검증 순서

- **준비:** 본인 session과 유효한 게임 리플레이 이벤트를 준비한다.
- **동작:** `POST /api/game-sessions/{id}/start`, `POST /api/game-sessions/{id}/checkpoint`, `POST /api/game-sessions/{id}/finish` 순으로 호출한다. 완료 요청은 같은 키로 재시도한다.
- **예상 결과:** 유효한 상태 전이만 허용되고 완료 결과는 안정적으로 재생된다. 점수·랭킹·추첨 가능 상태가 한 트랜잭션 결과와 일치한다.
- **결과:** ☐ 미실행

### SV-013 서버 판정 권한과 입력 형식

- **준비:** 충돌이 없는 리플레이, 충돌이 있는 리플레이, 숫자처럼 보이는 문자열·불리언·소수 입력을 준비한다.
- **동작:** 각 리플레이로 완료를 요청하고 클라이언트가 점수·아이템·부활 횟수를 직접 주장해 본다.
- **예상 결과:** 서버가 충돌·점수·아이템·부활을 다시 계산한다. legacy `1.2.0`의 충돌 없는 미완료 리플레이와 v2/v2.1의 끝나지 않은 tick은 순위·추첨 조건을 만들 수 없다. v2/v2.1이 정확한 최대 tick에 도달한 `TIME_LIMIT` 종료는 충돌이 없어도 정상 완료다. 숫자 문자열·불리언·소수는 강제 변환하지 않고 거부한다.
- **결과:** ☐ 미실행

### SV-014 검증 버전 v2와 v2.1 분리

- **준비:** 동일한 seed와 동작을 v2, v2.1 형식으로 준비하고 부활 사용 사례를 포함한다.
- **동작:** 두 버전의 게임을 완료하고 `GET /api/leaderboard`에서 버전별 결과를 조회한다.
- **예상 결과:** 각 버전의 고정 상수·속도·간격·부활 감점 규칙이 재현된다. 알 수 없는 버전·비정수 입력은 거부된다. v2와 v2.1 기록은 같은 랭킹으로 섞이지 않는다.
- **결과:** ☐ 미실행

### SV-015 100점 이하 환급과 정상 소비

- **준비:** 각각 검증 점수 100 이하와 100 초과가 되는 session.
- **동작:** 두 게임을 완료하고 `GET /api/me`의 게임권 및 session 결과를 확인한다.
- **예상 결과:** 100점 이하 게임은 사용권이 정확히 한 번 복구된다. 100점 초과 게임은 소비된다. 완료 재시도로 추가 환급·소비가 생기지 않는다.
- **결과:** ☐ 미실행

### SV-016 이탈·장애·만료 복구

- **준비:** 시작 전 예약, 진행 중 session, 완료 session, 초대권으로 만든 session을 각각 준비한다.
- **동작:** `POST /api/game-sessions/{id}/abandon`과 `POST /api/game-sessions/{id}/fault`를 상태별로 호출하고 반복한다. 만료 뒤 `GET /api/game-sessions/{id}`도 조회한다.
- **예상 결과:** 미완료 장애·허용된 이탈은 원래 권리를 한 번만 복구한다. 정상 완료는 환급되지 않는다. 네트워크 장애는 필요 시 검토 대기로 남고, 두 번째 호출도 이중 환급하지 않는다. 초대권 환급 이력과 쿨다운도 보존된다.
- **결과:** ☐ 미실행

### SV-017 관리자 장애 검토의 버전 충돌

- **준비:** 검토 대기 fault 1건과 `faults:write` 관리자.
- **동작:** `GET /api/admin/game-faults?status=PENDING`로 현재 version을 확인한다. 같은 `{decision:"APPROVE", reason:"합성 장애 확인", expected_version, event_id}`로 `PATCH /api/admin/game-faults/{id}`를 두 번 호출한다. 별도 fixture에서는 `decision:"DENY"`도 확인한다.
- **예상 결과:** 첫 변경만 반영되고 두 번째는 version conflict다. 게임권 원장과 환급은 한 번만 바뀌며, 거부된 시도는 상태를 되돌리지 않는다.
- **결과:** ☐ 미실행

---

## 5. 초대 추적·공유·카카오 웹훅

### SV-018 친구 방문 추적과 중복 방지

- **준비:** 초대자 A, 방문자 B, 다른 초대자 C의 정상 invite code.
- **동작:** B의 익명 생성에 A의 `invite_code`를 넣어 받은 `visit_nonce`를 사용한다. 최소 3초가 실제로 지난 뒤 `POST /api/referrals/qualify`에 `{visit_nonce, code, active_ms:3000, interacted:true}`를 반복 호출하고 C 코드에도 새 방문을 만든다. 자기 코드, 잘못된 코드, 3초 미만, `interacted:false`도 시도한다.
- **예상 결과:** 방문은 분석용으로만 기록되고 게임권·뽑기권을 지급하지 않는다. 같은 추천인·방문자 쌍은 중복되지 않으며 자기 초대·잘못된 코드는 거부된다. 한 방문자가 서로 다른 정상 초대자를 방문한 사실은 각각 추적할 수 있다.
- **결과:** ☐ 미실행

### SV-019 공유 목적별 보상 계약

- **준비:** 본인 참가자와 필요 시 본인 소유 DRAW/RANKING claim.
- **동작:** `POST /api/referrals/share-intents`에 `{kind}` 또는 수령 접수용 `{kind, claim_id}`를 사용해 `retry_invite`, `record_share`, `draw_retry`, `prize_share`, `general_share`를 각각 보낸다. claim이 있을 때 허용되지 않는 kind도 시도한다.
- **예상 결과:** `retry_invite`·일반 `record_share`는 `GAME`, `draw_retry`는 `DRAW`, `prize_share`·`general_share`는 `NONE`이다. claim 접수용 공유는 항상 `NONE`이며 claim 종류와 허용 kind가 맞지 않으면 거부된다. 응답은 `share_id`, `status`, `reward_type`, `reward_status`, 만료·확인 시각과 카카오 전달용 `callback_args`를 구분한다.
- **결과:** ☐ 미실행

### SV-020 웹훅 인증·위조·나에게 보내기 예외·중복

- **준비:** **격리 서버 전용 합성 카카오 자격**과 SV-019의 share intent. 공개 베타와 실제 키를 사용하지 않는다.
- **동작:** `POST /api/webhooks/kakao-share`에 정확한 인증 헤더, 누락·오류·비ASCII 헤더, 만료 callback, `GAME`·`DRAW` 나에게 보내기, 본인 소유 `claim_id` 결합 `NONE` 수령 접수용 나에게 보내기, 같은 `X-Kakao-Resource-ID` 중복 요청을 각각 보낸다.
- **예상 결과:** 정확히 인증된 전송 콜백만 confirmed 처리된다. 위조·누락·만료·다른 환경과 `GAME`·`DRAW` 나에게 보내기는 보상하지 않는다. 소유 `claim_id` 결합 `NONE` 수령 접수용 나에게 보내기는 confirmed되어 접수 흐름에 사용할 수 있으나 `NO_REWARD`다. 같은 공유 요청을 여러 번 보내도 최대 한 번만 지급된다. `GET /api/referrals/share-intents/{id}`에서 본인만 최종 `reward_status`를 확인한다.
- **결과:** ☐ 미실행

### SV-021 게임권 3장 상한·쿨다운·동시 웹훅

- **준비:** 게임권 잔액 2장인 참가자와 서로 다른 GAME share intent 여러 개.
- **동작:** 두 인증 콜백을 동시에 처리하고 `GET /api/referrals/me`를 확인한다. 쿨다운 중 추가 콜백, 쿨다운 종료 후 새 콜백도 확인한다.
- **예상 결과:** 보유·예약분 합계는 3장을 넘지 않는다. 3장이 되는 순간 10시간 쿨다운이 시작된다. 쿨다운 종료만으로 자동 지급되지 않고 새 전송이 필요하다. 차단된 요청도 확인 여부와 보상 여부가 구분된다.
- **결과:** ☐ 미실행

### SV-022 뽑기권 10회 경계의 동시 콜백

- **준비:** 사용 9회, 미사용 뽑기권 0인 참가자와 서로 다른 DRAW share intent 2개.
- **동작:** 두 인증 콜백을 동시에 처리한 뒤 `GET /api/draws/me`를 조회한다.
- **예상 결과:** 하나만 `GRANTED`, 다른 하나는 draw limit으로 차단된다. `used_count + available_credits`는 10을 넘지 않는다. GAME 권리는 함께 지급되지 않는다.
- **결과:** ☐ 미실행

### SV-023 실제 카카오 1:1·단체방 전송 확인

- **준비:** 본행사 전 별도 승인된 실제 카카오 설정, 테스트 전용 참가자, 비용·전송 범위 합의.
- **동작:** 실제 친구 1:1과 단체방에 각 목적별 카드를 보내고 공식 콜백·intent 상태를 대조한다.
- **예상 결과:** 공식 콜백이 확인된 전송만 목적별 권리를 한 번 지급한다. 공유창 열기만으로 지급하지 않는다. 서버는 읽음·수신 여부까지 확인했다고 표현하지 않는다.
- **현재 실행:** 2026-09-29 사용자가 실제 친구·단체방에 전송했고, GAME/DRAW/NONE 원장을 대조했다. 위치별 카드·예외 조합은 [실행 보고서](test-run-2026-09-29.md)에서 별도로 구분한다.
- **결과:** ☐ 미실행

---

## 6. 랭킹·이벤트·분석 집계

### SV-024 랭킹 버전·동점·개인정보 표시

- **준비:** 서로 다른 점수·플레이 시간, 동점, 비공개 닉네임 참가자를 격리 DB에서 정상 게임으로 만든다.
- **동작:** `GET /api/leaderboard`와 `GET /api/ranking/profile`을 버전별로 조회한다.
- **예상 결과:** 점수·게임 버전·비공개 닉네임 보호를 유지하고, 최신 사용자 결정인 동점 선달성 우선이 순위와 TOP3 대상에 일관되게 적용된다. 현재 코드는 `dense_rank` 공동 순위이므로 기존 회귀 통과만으로 이 새 기준을 통과 처리하지 않는다. 달성 시각 정의·최종 스냅샷 구현을 함께 대조한다.
- **결과:** ☐ 미실행

### SV-025 TOP3 연락처·동의·기록 출처

- **준비:** 검증된 TOP3 참가자와 TOP3가 아닌 참가자, 현재 profile version.
- **동작:** `POST /api/ranking/profile`에 `{name, contact, school, consent:true, notice_version:"top3-contact-v1"}`을 제출한다. 동의·notice version 누락, 잘못된 연락처, TOP3가 아닌 참가자도 시도한다. 이 API에는 `expected_version` 필드가 없다.
- **예상 결과:** 서버가 이미 `REQUESTED`로 표시한 현재 잠정 TOP3만 접수되고 출처 게임·규칙 버전이 보존된다. 잘못된 요청은 부분 저장되지 않는다. 같은 제출 재시도는 기존 claim을 반환한다. 과거 유효 요청은 현재 순위 변동 때문에 임의 삭제되지 않지만 최종 수상 확정으로 표시되지 않는다.
- **결과:** ☐ 미실행

### SV-026 분석 이벤트의 소유권·PII·시간 경계

- **준비:** 본인 observation, 다른 참가자 observation, 허용 event catalog와 link kind.
- **동작:** `POST /api/events/batch`에 정상 이벤트, 연락처·학교 등 PII가 포함된 이벤트, 타인 observation, 미래 시각·naive 시각, 알 수 없는 dimension을 각각 보낸다.
- **예상 결과:** 본인의 허용 이벤트만 저장된다. PII, 타인 소유, 잘못된 시각·catalog·dimension은 거부된다. 재시도는 중복 고유 사용자 수를 만들지 않는다.
- **결과:** ☐ 미실행

### SV-027 퍼널·CTR·공유 목적별 집계

- **준비:** 로딩→화면 노출→클릭, 재진입, 열린 observation, share intent가 연결된 이벤트를 만든다.
- **동작:** `GET /api/admin/overview?from=&to=&environment=&link_kind=&channel=&content=&won=`를 기간·환경·유입·콘텐츠 필터로 조회한다. 원시 진단 행이 필요할 때만 별도로 `GET /api/admin/analytics/events`를 조회한다.
- **예상 결과:** 노출과 고유 사용자, 발생 횟수, 완료·이탈·pending, 활성 시간이 구분된다. 같은 위치의 순서와 관측 창이 적용된다. `retry_invite`·보상 가능한 일반 `record_share`, claim-bound 무보상 공유, `draw_retry`, `prize_share`, `general_share`, 혜택·가이드가 근거 있는 intent로 각각 집계된다. 공유창 관측은 실제 전달 성공으로 계산되지 않는다.
- **결과:** ☐ 미실행

### SV-028 초대 원장·쿨다운 후 재참여 집계

- **준비:** 기간 안팎 GAME share intent, 지급·한도 차단·쿨다운 종료 후 새 지급 사례.
- **동작:** 관리자 분석을 기간별로 조회하고 실제 share intent 및 ticket ledger 건수와 대조한다.
- **예상 결과:** 전송 확인, 실제 지급, 차단이 구분된다. 쿨다운 후 새 전송 재참여가 별도 집계되고 단순 방문·클라이언트 관측은 지급률에 포함되지 않는다.
- **확인용 SELECT:** `SELECT reward_status, count(*) FROM dino_dev.kakao_share_intent GROUP BY reward_status ORDER BY reward_status;`
- **결과:** ☐ 미실행

---

## 7. 복주머니·5,000자리 풀·재고

### SV-029 최초 추첨과 회차 멱등 재시도

- **준비:** 정상 게임을 마쳐 최초 추첨권이 있는 참가자. `event_id`, `pouch_index`, `expected_round_number: 1`을 고정한다.
- **동작:** `POST /api/draws`를 같은 본문·같은 키로 두 번 호출한다. 이어서 같은 회차의 다른 `pouch_index`로 호출한다.
- **예상 결과:** 처음 두 요청은 같은 `draw_id`, `round_number`, 결과를 반환하고 권리·풀 자리를 추가 소비하지 않는다. 다른 주머니는 `409 DRAW_ROUND_CONFLICT`다. `PATCH /api/draws/{id}/scratch-complete`는 공개 상태만 바꾸고 결과를 바꾸지 않는다.
- **결과:** ☐ 미실행

### SV-030 응답 유실·다음 회차 방지

- **준비:** 2회차 권리가 있는 참가자와 최신 draw 상태.
- **동작:** `expected_round_number: 2` 요청의 응답을 클라이언트에서 버린 뒤 같은 요청을 재시도한다. 그 전에 새 event ID로 3회차를 시도하지 않는다. 잘못된 예상 회차와 회차 생략 요청도 보낸다.
- **예상 결과:** 재시도는 저장된 2회차를 반환한다. 잘못된 다음 회차는 충돌이고, 기존 추첨이 있는 구형 요청의 회차 생략은 `DRAW_ROUND_REQUIRED`다. 응답 유실로 추가 권리·재고를 소비하지 않는다.
- **결과:** ☐ 미실행

### SV-031 혜택 반복과 실제 상품 당첨 종료

- **준비:** DRAW 권리가 여러 장인 합성 참가자. 결과가 BENEFIT인 격리 풀과 실제 PRIZE가 배정되는 격리 풀을 각각 준비한다.
- **동작:** BENEFIT 뒤 새 DRAW share 보상을 받아 다음 회차를 진행한다. 실제 PRIZE 뒤 남은 권리 조회와 추가 share·draw를 시도한다.
- **예상 결과:** BENEFIT은 화면상 혜택 결과지만 내부 `outcome_kind: BENEFIT`, `is_actual_prize: false`이며 최대 10회 안에서 반복 가능하다. 실제 상품은 `WON`, `is_actual_prize: true`이고 남은 권리도 더 사용할 수 없으며 새 DRAW 보상도 지급하지 않는다.
- **결과:** ☐ 미실행

### SV-032 마지막 재고·같은 참가자 동시 추첨

- **준비:** 특정 상품 재고 1개인 격리 풀, 서로 다른 참가자 2명, 그리고 한 참가자의 같은 회차 동시 요청 2개.
- **동작:** 마지막 재고를 노리는 두 참가자의 요청을 동시에 보내고, 같은 참가자의 동일 회차 요청도 동시에 보낸다.
- **예상 결과:** 마지막 실제 상품은 한 사람에게만 배정된다. 다른 요청은 남은 풀의 다른 자리 또는 정의된 소진 상태를 받는다. 같은 참가자의 동일 회차는 한 결과만 만들고 claim·재고·권리를 중복 생성하지 않는다.
- **결과:** ☐ 미실행

### SV-033 5,000자리 전체 소진 정합성

- **준비:** 새로 만든 전용 로컬 DB, 본행사와 같은 **합성** 5,000자리 풀. 다른 검증과 공유하지 않는다.
- **동작:** 자동화된 로컬 도구로 서로 독립된 유효 참가자의 추첨을 정확히 5,000회 처리한다. 사람이 베타 UI에서 반복 클릭하지 않는다. 5,001번째 요청을 보낸다.
- **예상 결과:** 실제 상품 77개와 BENEFIT 4,923개가 중복 없이 한 번씩 소비된다. 상품별 배정 수량이 manifest와 일치한다. 5,001번째는 소진 오류이며 과거 확률 방식으로 대체되지 않는다.
- **확인용 SELECT:** `SELECT outcome_kind, count(*) FROM dino_dev.draw GROUP BY outcome_kind ORDER BY outcome_kind;`
- **현재 제한:** 공개 베타에서는 실행 금지. 자동 테스트 증거를 우선한다.
- **결과:** ☐ 미실행

### SV-034 잘못된 풀 설정의 fail-closed

- **준비:** finite pool 표시가 있지만 자리 또는 재고가 빠진 격리 캠페인.
- **동작:** 새 추첨을 요청한다.
- **예상 결과:** `503 DRAW_CONFIG_INVALID`로 거부된다. legacy 가중치 추첨으로 대체되지 않으며 권리·회차·재고·claim이 바뀌지 않는다.
- **결과:** ☐ 미실행

### SV-035 구버전 단일 추첨 호환 정산

- **준비:** 최신 migration 직후 구버전 앱 형식으로 생성된 첫 draw가 있으나 3차 권리 원장이 아직 없는 격리 fixture.
- **동작:** 새 서버로 `GET /api/draws/me`를 조회하고 다음 draw 가능 상태를 확인한다.
- **예상 결과:** 기존 draw는 1회차로 보존되고 최초 권리 지급·소비가 net 0이 되도록 한 번만 정산된다. 공유 없이 공짜 2회차가 생기지 않으며 기존 claim·결과는 바뀌지 않는다.
- **결과:** ☐ 미실행

---

## 8. 수령 접수·관리자 지급

### SV-036 수령 초안의 저장·소유권·제출 선행 조건

- **준비:** 실제 상품 DRAW claim 또는 RANKING claim, 소유자 A와 타인 B.
- **동작:** A가 `POST /api/claims/{id}/draft`로 필수 정보를 저장하고 `GET /api/claims/{id}/draft`로 복원한다. B가 조회를 시도한다. 저장된 초안 없이 제출, 확인되지 않은 공유로 제출도 시도한다.
- **예상 결과:** 초안은 최종 contact를 만들지 않고 A에게만 복원된다. 타인은 접근할 수 없다. 제출은 유효한 초안과 본인 소유·확인된 claim-bound 무보상 공유가 있어야 하며 실패 시 부분 저장되지 않는다.
- **결과:** ☐ 미실행

### SV-037 접수 완료의 동시성·상태 보존

- **준비:** 유효 초안과 accepted share result가 있는 claim.
- **동작:** 확인된 claim-bound 공유의 ID를 넣은 `{share_intent_id}`로 `POST /api/claims/{id}/submit`을 같은 `Idempotency-Key`로 반복하고 두 창에서 거의 동시에 보낸다. 진행된 상태와 종료 상태 claim에 늦은 제출도 시도한다.
- **예상 결과:** contact는 한 번만 생성되고 반복은 같은 완료 상태를 반환한다. 이미 진행·종료된 상태를 이전 단계로 되돌리지 않는다. 배송형 초안은 주소 등 해당 필수 필드를 검사한다.
- **결과:** ☐ 미실행

### SV-038 관리자 수령 상태 전이와 version 보호

- **준비:** 정보 접수된 DRAW claim, `claims:write` 관리자, 현재 `expected_version`.
- **동작:** `GET /api/admin/claims?type=DRAW`로 확인하고 `PATCH /api/admin/claims/{id}`에 `{status, assignee_user_id?, reason?, expected_version, event_id}`를 사용해 담당자 지정·검토·연락 상태를 순서대로 변경한다. 같은 version을 다시 보낸다.
- **예상 결과:** 정상 전이만 허용된다. 정보가 없는 신규 claim은 관리자 변경이 차단된다. 오래된 version은 `VERSION_CONFLICT`이고 기존 contact·claim·재고는 변하지 않는다. RANKING 지급 완료는 정책 미정으로 차단된다.
- **결과:** ☐ 미실행

### SV-039 지급 완료 증거와 원자적 재고 처리

- **준비:** `CONTACTED`인 실제 상품 DRAW claim, 현재 version, 테스트용 `TEST_REF_...` 참조.
- **동작:** 먼저 verification 누락, reference 누락, `external_delivery` 누락·문자열 `"true"`, 3자 미만 reason으로 각각 `PAID`를 요청한다. 이후 `verification_status: VERIFIED`, 유효 참조, `external_delivery: true`, 3자 이상 비PII reason으로 요청한다.
- **예상 결과:** 누락별로 `CLAIM_VERIFICATION_REQUIRED`, `DELIVERY_CONFIRMATION_REQUIRED`, `DELIVERY_EVIDENCE_REQUIRED`의 `409`가 구분되고 상태·version·재고·원장·감사는 불변이다. 정상 요청은 claim과 RESERVED→PAID 재고, 재고 이력, 전후 증거와 관리자 감사가 한 번만 반영된다. 이 API 자체가 실제 상품을 발송하지는 않는다.
- **결과:** ☐ 미실행

### SV-040 지급 완료 후 증거 철회·중복 지급 차단

- **준비:** SV-039에서 `PAID`가 된 claim.
- **동작:** verification을 낮추거나 reference를 지우거나 `external_delivery: false`로 바꾸는 PATCH, 과거 version의 PAID 재시도를 보낸다.
- **예상 결과:** 필수 증거 철회와 stale 요청은 거부된다. 재고·지급 이력·감사 기록이 중복 생성되지 않고 기존 지급 완료 기록은 유지된다.
- **결과:** ☐ 미실행

---

## 9. migration·시간 경계·본행사 guard

### SV-041 migration의 신규 적용·재적용·기존 데이터 보존

- **준비:** 빈 격리 DB와 기존 단일 draw·claim·contact·지급 기록이 있는 migration 직전 스냅샷 복제본.
- **동작:** 전체 migration을 순서대로 적용한다. 허용된 idempotent migration은 재적용 검사를 수행하고, foundation migration의 무분별한 재적용도 별도 복제본에서 시도한다.
- **예상 결과:** 빈 DB는 최신 schema가 된다. 기존 draw는 1회차, 기존 claim·contact·지급·공유 v1은 보존된다. 허용된 재적용은 중복 데이터를 만들지 않는다. 위험한 foundation 재적용은 손상 없이 거부된다.
- **확인용 SELECT:** `SELECT version, applied_at FROM dino_dev.schema_version ORDER BY applied_at;`
- **결과:** ☐ 미실행

### SV-042 행사 시작·종료 시각의 신규 진입 경계

- **준비:** 격리 캠페인의 `opens_at`, `closes_at`을 짧은 시험 구간으로 설정하고 기존 session과 기존 draw 회차도 준비한다.
- **동작:** 시작 직전, 시작 시각, 종료 직전, 종료 시각에 **새** `POST /api/game-sessions`와 **새** `POST /api/draws`를 호출한다. 종료 뒤 기존 session·동일 draw 회차 재시도와 조회도 수행한다.
- **예상 결과:** 신규 예약·신규 draw는 `[opens_at, closes_at)`에서만 허용되고 차감 전에 거부된다. 기존 session 조회와 동일 회차 멱등 재응답은 유지된다. 날짜가 null인 현재 베타는 기존 동작을 유지하며, 잘못된 시간 형식은 fail-closed다.
- **현재 제한:** 종료 전 예약 게임의 시작·완료, 늦은 웹훅, 종료 후 접수 정책은 미정이며 이 케이스로 확정하지 않는다.
- **결과:** ☐ 미실행

### SV-043 운영 manifest와 사전 점검 guard

- **준비:** `config/phase3-launch.json` 복사본. 실제 파일은 변경하지 않는다.
- **동작:** DRAFT 완성본, 필수 결정 누락, 일부 날짜만 입력, naive/역전 시간, 잘못된 수량 배분, 테스트 기능 ON, 잘못된 bool·status·version·ID를 각각 사전 점검기에 넣는다.
- **예상 결과:** 값이 모두 있어도 DRAFT는 준비 완료가 아니다. 필수 결정·승인·정확한 5,000/77 분배·랭킹 3개 분리·유효한 날짜·테스트 기능 OFF가 없으면 본행사 준비 완료로 판정하지 않는다.
- **결과:** ☐ 미실행

### SV-044 베타·본행사 데이터 및 기능 분리

- **준비:** 현재 베타 연결 정보와 본행사 초안 manifest를 비밀 없이 대조한다.
- **동작:** `/api/config`, 캠페인 상태, 테스트 무제한 flag, 전용 schema·role, 도메인·환경 ID를 확인한다.
- **예상 결과:** 베타 무제한과 합성 재고는 유지되며 본행사 실제 77개 풀로 간주되지 않는다. 승인된 manifest·운영 guard·데이터 영역이 없으면 ACTIVE 본행사로 전환되지 않는다. 기존 Supabase 프로젝트 재사용 결정은 새 유료 프로젝트 생성을 뜻하지 않는다.
- **결과:** ☐ 미실행

---

## 10. 부하·안전 경계

### SV-045 부하 도구 dry-run과 대상 보호

- **준비:** 부하 도구의 dry-run, 승인되지 않은 원격 URL, 허용된 전용 로컬 URL을 준비한다.
- **동작:** 기본값으로 실행 계획만 생성하고 target preflight를 수행한다. 원격·프로젝트·schema·campaign·deployment 불일치도 확인한다.
- **예상 결과:** 기본은 쓰기 없는 dry-run이다. 정확한 대상 증명, 비공개 쿠키 cohort, 요청·시간 예산, 승인 없이는 원격 실행하지 않는다. 보고서·원장 파일은 비공개 권한이며 헤더·쿠키·opaque ID를 노출하지 않는다.
- **결과:** ☐ 미실행

### SV-046 요청·시간 예산과 재개 원장

- **준비:** 작은 로컬 예산과 합성 cohort, 중단 후 재개 가능한 비공개 ledger.
- **동작:** 일부 stage를 실행해 예산을 소비한 뒤 중단·재개한다. 배포 target이 바뀐 재개도 시도한다.
- **예상 결과:** admission 시점에 예산이 차감되고 실패해도 임의 환급되지 않는다. 재개는 기존 소비·참가자 cursor를 보존한다. 명시적 target proof가 없으면 다른 배포로 이어서 실행하지 않는다. 실패 보고서는 비밀을 제거한다.
- **결과:** ☐ 미실행

### SV-047 bounded 합성 부하와 정합성 관찰

- **준비:** 전용 로컬 DB·서버, 승인된 소규모 worker·stage·요청·시간 상한. 실제 베타는 대상에서 제외한다.
- **동작:** 익명 생성→게임 예약·시작·체크포인트·완료→추첨의 실제 흐름을 상한 안에서 실행하고 종료 후 연결·worker·원장 상태를 확인한다.
- **예상 결과:** stage와 전체 흐름 성공률, 일반·finish·draw 지연, 실패 원인이 분리된다. timeout 뒤 worker와 연결이 남지 않는다. 게임 리플레이는 실제 물리 규칙을 따르며, 보안 probe는 checkpointed fault와 복구를 사용한다.
- **현재 제한:** 사용자가 최종 부하 시험을 보류했다. 실행 전 비용·시간·요청 상한을 다시 확정한다.
- **결과:** ☐ 미실행

### SV-048 HTTP body·URL·쿠키·오류 로그 경계

- **준비:** 격리 서버와 로그를 볼 수 있는 개발자, PII가 아닌 합성 marker 문자열. 운영 쿠키·Authorization 값은 사용하지 않는다.
- **동작:** 길이 2,048자를 넘는 URL, 65,536바이트를 넘는 body, `Transfer-Encoding` body, JSON이 아닌 Content-Type, 깨진 JSON, 배열 최상위 JSON, 4,096자를 넘는 Cookie, 형식이 잘못됐거나 8,200자를 넘는 Authorization을 각각 보낸다. 응답 헤더와 서버의 한 줄 요청 로그를 확인한다. query field 21개도 별도 호출한다.
- **예상 결과:** 긴 URL은 `414 URL_TOO_LONG`, 큰 body는 `413 BODY_TOO_LARGE`, Transfer-Encoding·배열 body는 `400 INVALID_BODY`, 잘못된 JSON은 `400 INVALID_JSON`, JSON이 아닌 요청은 `415 JSON_REQUIRED`, 큰 Cookie는 `401 SESSION_INVALID`, 잘못된 관리자 토큰 형식은 `401 ADMIN_AUTH_REQUIRED`다. 오류 응답은 일반 메시지와 request ID만 포함한다. 로그는 method, ID가 마스킹된 route template, status, duration, request ID, deployment, error code, DB 실패 분류만 남기며 body·query·Cookie·Authorization·PII를 남기지 않는다. 모든 JSON 응답에는 `no-store`, `nosniff`, frame·권한 제한 보안 헤더가 있다.
- **현재 구현 확인점:** query field가 20개를 넘으면 `parse_qs`의 `ValueError`가 현재 `500 INTERNAL_ERROR`로 일반화된다. 비밀은 노출하지 않지만 클라이언트 입력을 4xx로 분류하지 않는 hardening 이슈로 별도 기록한다.
- **결과:** ☐ 미실행

### SV-049 숨겨진 프로필 API의 공개 여부 보존

- **준비:** 격리 참가자 1명. 공개 화면에는 닉네임 변경 버튼이 없으므로 개발자가 직접 API로만 검증한다.
- **동작:** 현재 `GET /api/me`의 `participant.is_public`을 기록한다. 같은 쿠키로 `PATCH /api/me/profile`에 `{nickname:"새닉네임"}`만 보내고 다시 조회한다. 다음 요청에는 `{nickname:"새닉네임2", is_public:true}`를 명시한다. 마지막으로 `is_public:"false"` 문자열을 보낸다. 각 PATCH는 새 `Idempotency-Key`를 사용한다.
- **예상 결과:** 닉네임만 보낸 첫 요청은 기존 `is_public`을 그대로 보존한다. 불리언을 명시한 요청만 공개 여부를 바꾼다. 문자열 `"false"`는 `400 VALIDATION_ERROR`이며 값이 바뀌지 않는다. 현재 서버가 검사하는 닉네임 경계는 문자열 길이 1–24자다.
- **현재 구현 확인점:** 이 endpoint에는 수령 정보 입력과 같은 제어문자 거부 검사가 없다. 화면에서 기능을 숨긴 것과 별개인 입력 hardening 이슈로 기록한다.
- **결과:** ☐ 미실행

---

## 11. 현재 보류·미정 항목

아래 항목은 결함이 아니라 운영 결정 또는 별도 실제 검증이 필요한 상태다.

- 실제 카카오 친구·단체방 GAME/DRAW/NONE·접수용 공유 및 나에게 보내기 제외: 확인 완료. 이는 당시 실행 결과이며, 현재 규칙은 SV-020의 GAME/DRAW 제외와 소유 `claim_id` 결합 NONE 예외를 따른다. 모든 위치별 수신 카드·취소·복귀 조합은 추가 검증 대상.
- 최종 200명 등 부하 시험: 보류. 실행 전 요청·시간·비용 상한 필요.
- 행사 일정: 2026-09-29 19:00~2026-10-02 23:59 KST 확정. 원격 베타에는 미반영. 종료 경계 게임·늦은 웹훅·마감 후 수령 접수는 미정.
- 동점: 먼저 달성한 참가자 우선으로 정책 확정, 구현 미완료. 미등록·부적격·차순위 처리는 미정이며 최종 랭킹 지급 완료는 계속 차단.
- 5,000자리 소진 뒤 운영, 남은 재고, 베타와 본행사 데이터 분리: 미정.
- 재학생 자격 기준·증빙, 수령 기한·미응답·오기재, 개인정보 보관·삭제: 미정.
- Gemini 실제 혜택 조건과 외부 가입 완료는 이 서버에서 확인할 수 없음.

---

## 12. Python 자동 테스트 파일 대응표

수동 케이스는 자동 테스트의 사용자 관찰 가능한 계약을 묶어 표현한다. 경쟁 조건·연결 장애·5,000회 소진은 대응 자동 테스트도 반드시 통과해야 한다.

| 자동 테스트 파일 | 대응 수동 케이스 |
| --- | --- |
| `tests/test_acceptance_boundaries.py` | SV-016, SV-017, SV-018, SV-021 |
| `tests/test_acceptance_regressions.py` | SV-008, SV-009, SV-010, SV-029, SV-032 |
| `tests/test_backend_concurrency.py` | SV-011, SV-018, SV-021, SV-032 |
| `tests/test_backend_config.py` | SV-001, SV-002, SV-044 |
| `tests/test_backend_kakao_config.py` | SV-003 |
| `tests/test_backend_kakao_webhook_security.py` | SV-020 |
| `tests/test_backend_phase1.py` | SV-007–SV-010, SV-011–SV-013, SV-015–SV-021, SV-024–SV-026, SV-029, SV-032, SV-049 |
| `tests/test_backend_phase2.py` | SV-012, SV-014, SV-024–SV-027, SV-036–SV-038 |
| `tests/test_backend_phase3.py` | SV-019, SV-022, SV-029–SV-035 |
| `tests/test_backend_security_regression.py` | SV-009, SV-013, SV-020, SV-024–SV-026, SV-039, SV-048, SV-049 |
| `tests/test_claim_status_followup.py` | SV-036–SV-038, SV-041 |
| `tests/test_cohort_guards.py` | SV-044–SV-046 |
| `tests/test_database_connections.py` | SV-004 |
| `tests/test_game_verifier_safety.py` | SV-013 |
| `tests/test_game_verifier_v2.py` | SV-012–SV-014 |
| `tests/test_game_verifier_v21.py` | SV-014 |
| `tests/test_load_guards.py` | SV-045–SV-047 |
| `tests/test_metrics.py` | SV-026–SV-028 |
| `tests/test_metrics_acceptance.py` | SV-024, SV-026, SV-027 |
| `tests/test_migration_acceptance.py` | SV-035, SV-041 |
| `tests/test_phase2_load.py` | SV-045–SV-047 |
| `tests/test_phase2_metrics.py` | SV-026–SV-028 |
| `tests/test_phase3_campaign_window.py` | SV-042 |
| `tests/test_phase3_claim_payment.py` | SV-038–SV-040 |
| `tests/test_phase3_pool_depletion.py` | SV-033 |
| `tests/test_phase3_preflight.py` | SV-043, SV-044 |
| `tests/test_rate_limit_buckets.py` | SV-005 |
| `tests/test_schema_guard.py` | SV-006, SV-041 |

## 13. 수행 기록 요약

| 항목 | 값 |
| --- | --- |
| 수행 환경 | 미실행 |
| 서버 커밋 | 미실행 |
| schema version | 미실행 |
| manifest version | 미실행 |
| 수행자·검토자 | 미실행 |
| 통과 / 실패 / 보류 | 미실행 |
| 발견 이슈 링크 | 미실행 |
