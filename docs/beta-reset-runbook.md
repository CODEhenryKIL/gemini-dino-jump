# 베타 참여 데이터 초기화 실행서

## 목적과 고정 범위

이 절차는 Supabase 프로젝트 `igfrnexknwtiljdqjrbp`의 Preview 스키마 `dino_dev`, 캠페인 `gemini_dino_phase1_test`에 속한 참여 기록만 초기화한다.

삭제 범위는 참가자, 게임·점수, 게임권·뽑기권 원장, 추천·카카오 공유 요청, 추첨, 베타 상품·재고, 수령 정보와 임시 입력, 서버 분석 기록, 랭킹 스냅숏 및 관련 베타 관리자 감사 기록이다.

다음 항목은 유지한다.

- `dino_dev` 스키마와 함수·정책·migration 이력
- `environment_guard` 행 전체
- 베타 `campaign` 행 전체와 PAUSED/ENDED 상태
- `admin_member`
- 다른 캠페인과 다른 스키마·앱의 모든 기록
- 캠페인 코드가 없거나 다른 캠페인 코드인 미연결 관측·bootstrap 기록
- 전체 IP 속도 제한 기록과 외부 GA4·Datadog 기록

초기화 도구는 `DROP`, `TRUNCATE`, `CASCADE`를 사용하지 않는다.

## 강제 안전 조건

1. 베타 캠페인은 `PAUSED` 또는 `ENDED`여야 한다.
2. 앱 역할 `dino_dev_app`의 대상 테이블 INSERT·UPDATE·DELETE 권한을 DB에서 회수해야 한다. 화면 표시나 환경 변수만으로는 쓰기 차단으로 인정하지 않는다.
3. 권한 회수 트랜잭션을 먼저 커밋한 뒤 모든 변경 대상 테이블의 `ACCESS EXCLUSIVE` 잠금을 얻고 해제하는 배수 장벽을 통과해야 한다. 이전 연결의 쓰기가 남아 잠금 제한 시간을 넘으면 계획을 만들지 않는다.
4. 계획 시점과 적용 시점의 건수 및 정렬된 식별값 다이제스트가 같아야 한다.
5. 참가자·상품이 다른 캠페인의 행에서 참조되면 적용을 중단한다.
6. 캠페인·guard·관리자·다른 캠페인은 적용 전후가 같아야 한다.
7. 계획과 결과에는 참가자 ID, 토큰 해시, 이름, 연락처, 학교를 출력하지 않는다.

## 실행 순서

### 1. 비공개 복구 자료 확인

적용 전에 접근이 제한된 베타 복구 자료가 존재하고 복호화 검증이 끝났는지 확인한다. 복구 자료를 Git, 공개 배포, 채팅에 넣지 않는다.

### 2. 베타 DB 격리

다음 명령은 검토 가능한 격리 SQL을 출력한다. 출력 SQL은 베타 캠페인을 PAUSED로 바꾸고 `dino_dev_app`의 쓰기 권한을 회수한다.

```bash
.venv/bin/python scripts/beta_reset.py \
  --environment preview \
  --print-quarantine-sql
```

직접 DB 관리자 DSN이 없을 때는 출력 SQL을 승인된 Supabase 관리자 SQL 실행 경로로 실행한다. 격리 후 이전 베타 주소·API·카카오 웹훅이 새 행을 만들지 못하는지 확인한다.

### 3. 읽기 전용 계획 생성

Supabase 관리자 SQL 실행 경로에서는 아래 명령으로 출력한 배수 잠금 트랜잭션과 최종 SELECT를 한 번에 실행한다.

```bash
.venv/bin/python scripts/beta_reset.py \
  --environment preview \
  --print-mcp-plan-sql
```

계획 SQL은 영구 데이터를 바꾸지 않지만, 먼저 모든 변경 대상 테이블을 잠갔다 해제해 격리 전에 열린 쓰기 트랜잭션이 남지 않았음을 확인한다. 결과에서 다음 다섯 값을 모두 확인한다.

- `guard_ok = true`
- `campaign_frozen = true`
- `schema_complete = true`
- `database_quarantined = true`
- `plan_token`: 64자리 SHA-256 16진수

`counts_and_digests`는 대상별 건수와 정렬된 식별값 SHA-256만 포함한다. direct DSN 계획과 Supabase 관리자 SQL 계획은 같은 범위에 같은 `plan_token`을 만든다. 원본 식별값이나 개인정보는 포함하지 않는다.

관리자 DSN을 안전하게 사용할 수 있는 경우 파일 계획도 지원한다.

```bash
DINO_BETA_RESET_DATABASE_URL='관리자 DSN' \
.venv/bin/python scripts/beta_reset.py \
  --environment preview \
  --plan-output /private/tmp/dino-beta-reset-plan.json
```

계획 파일은 한 시간 동안만 유효하며 공개 저장소에 추가하지 않는다.

### 4. 적용 SQL 생성 및 검토

3단계에서 받은 `plan_token`으로 한 트랜잭션짜리 적용 SQL을 출력한다.

```bash
.venv/bin/python scripts/beta_reset.py \
  --environment preview \
  --print-mcp-apply-sql PLAN_TOKEN \
  --confirm-ingress-disabled BETA_INGRESS_DISABLED
```

출력 SQL은 잠금·guard·캠페인 상태·권한 회수·교차 캠페인 참조·계획 토큰을 다시 확인한 뒤 삭제한다. 어느 한 단계라도 달라지면 전체 트랜잭션이 롤백된다. 이 SQL을 승인된 Supabase 관리자 SQL 실행 경로에서 한 번 실행한다.

관리자 DSN 방식은 다음과 같다.

```bash
DINO_BETA_RESET_DATABASE_URL='관리자 DSN' \
.venv/bin/python scripts/beta_reset.py \
  --environment preview \
  --apply-plan /private/tmp/dino-beta-reset-plan.json \
  --confirm-ingress-disabled BETA_INGRESS_DISABLED
```

### 5. 적용 후 확인

- 대상 캠페인의 참가자·게임·추첨·수령·분석·상품·재고가 0건인지 확인한다.
- `environment_guard`, 베타 `campaign`, `admin_member`, `schema_version`가 적용 전과 같은지 확인한다.
- 다른 캠페인과 다른 스키마의 기준 집계가 변하지 않았는지 확인한다.
- 초기화 후 베타 URL·지연된 카카오 콜백으로 새 베타 행이 생기지 않는지 확인한다.
- 운영 `dino_prod` 참가·점수·추첨·수령 및 실제 재고가 변하지 않았는지 확인한다.

## 실패 처리

- 계획 토큰 불일치: 적용하지 말고 신규 계획을 만든다.
- DB 격리 미완료: 이전 배포·API·웹훅 쓰기 경로를 먼저 닫고 권한을 다시 확인한다.
- 교차 캠페인 참조: 삭제 범위를 넓히지 않는다. 참조 행의 원인을 조사한다.
- 잠금 실패: 진행 중인 요청을 확인하고 종료된 뒤 계획부터 다시 만든다.
- 트랜잭션 오류: 전체 삭제가 롤백된다. 원인을 수정한 뒤 건수와 다이제스트를 다시 확인한다.
- 적용 후 베타 행 재생성: 오픈 완료로 처리하지 않고 베타 쓰기 차단부터 복구한다.

## 자동 검증

`tests/test_beta_reset.py`는 다음을 격리 PostgreSQL에서 확인한다.

- 계획 모드 무변경 및 개인정보 비출력
- 베타 행만 삭제하고 guard·campaign·관리자·migration·다른 캠페인 보존
- 계획 이후 변경 감지와 교차 캠페인 참조 차단
- 캠페인을 증명할 수 없는 미연결 관측·bootstrap 및 다른 타입의 관리자 감사 기록 보존
- 권한 회수 뒤 기존 쓰기 트랜잭션 배수 실패 차단
- direct DSN과 Supabase 관리자 SQL의 SHA-256 범위 토큰 일치
- DB 오류 시 전체 롤백
- 빈 상태에서의 안전한 반복 실행
- Supabase 관리자 SQL 경로용 계획·적용 SQL의 실제 실행
