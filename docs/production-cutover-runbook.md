# Production cutover runbook

## 목적과 안전 경계

이 문서는 검토된 `DRAFT/OFF` manifest에서 별도로 승인된 `APPROVED/ON` manifest로 전환하고, 문제가 생기면 기록을 보존한 채 `OFF`로 복귀하는 절차다.

- 현재 manifest를 임의로 승인 상태로 바꾸거나 승인·검증 근거를 만들어 내지 않는다.
- 도구는 배포, 도메인 별칭 변경, Vercel 환경 변수 변경, 승인 생성, 데이터 초기화를 수행하지 않는다.
- `dino_prod`의 참가자·게임·추첨·수령·재고 기록을 삭제하지 않는다.
- `scripts/beta_reset.py` 같은 베타 초기화 도구를 `dino_prod`에 실행하지 않는다.
- 운영 전환과 복귀는 모두 `pg_advisory_xact_lock(hashtext('dino-prod-cutover'))`를 잡는다. 운영 쓰기는 같은 키의 shared lock을 잡고 같은 트랜잭션에서 guard를 다시 확인한다.
- 계획 파일은 생성 후 1시간 동안만 유효하다. DB 상태가 달라졌거나 시간이 지나면 새 snapshot과 계획을 만든다.

## 사전 조건

다음 항목이 모두 준비돼야 활성화를 진행한다.

1. 정확한 원본 바이트의 `OFF` manifest와 최종 승인된 `ON` manifest가 있다. 현재 `OFF` 원본은 `phase3-20260929-v6-preparation`, SHA-256 `5326e40f39189b9a91e4fe0fdfbc77a788c1526c71af4f26e4eaf9517b2886f9`이다.
2. 두 manifest에서 전환 메타데이터(`version`, `status`, `event_enabled`, `approvals`, `evidence`) 외의 행사 일정·상품·정책·캠페인 ID가 같다.
3. `ON` manifest의 모든 승인과 증빙이 실제 근거를 가리키며 preflight가 launch ready다.
4. 현재 DB campaign은 version `3`, `PAUSED`, `event_enabled=false`이며 guard의 manifest SHA-256이 1번 `OFF` 원본과 일치한다.
5. OFF 후보와 ON 후보 배포의 코드 SHA 및 deployment ID를 기록했다.
6. ON 후보의 고유 Vercel URL에서는 운영 guard가 ON이어도 공개 mutation이 canonical host 검사로 거부됨을 확인했다.
7. 베타 사이트는 별칭 전환 전에 격리한다.
8. 초기 활성화 시 `participant`, `game_session`, `draw`, `claim`이 모두 비어 있어야 한다.
9. draw pool은 5,000칸(실물 상품 63, 혜택 4,937), 재고는 복주머니 63개와 랭킹 3개를 합친 총 66개로 일치해야 한다.

현재 원격 상태가 `OFF`라는 확인만으로 활성화 승인이 되지는 않는다.

## 1. 로컬 manifest 검증

아래 경로와 version 값은 실제 검토본으로 바꾼다.

```bash
.venv/bin/python scripts/production_cutover.py \
  --source-manifest /private/tmp/dino-off.json \
  --target-manifest /private/tmp/dino-on.json \
  --mode activate \
  --expected-campaign-version 3 \
  --validate-only
```

`valid: true`와 두 manifest의 SHA-256, 일정, 수량을 검토 기록에 남긴다. 이 단계는 네트워크를 사용하지 않는다.

## 2. Supabase SQL connector로 계획 만들기

운영 maintenance DSN이 없는 기본 절차다.

### 2.1 읽기 전용 snapshot SQL 생성

```bash
.venv/bin/python scripts/production_cutover.py \
  --source-manifest /private/tmp/dino-off.json \
  --target-manifest /private/tmp/dino-on.json \
  --mode activate \
  --expected-campaign-version 3 \
  --print-state-sql > /private/tmp/dino-cutover-state.sql
```

승인된 Supabase SQL 실행 수단으로 이 쿼리를 한 번 실행한다. 쿼리는 읽기만 하며 maintenance role 여부와 guard, campaign, schema version, 기록 수, draw pool, 재고를 JSON으로 반환한다.

반환된 JSON 한 개를 비공개 파일에 다음 형태로 저장한다. 개인정보 행은 포함되지 않는다.

```json
{"snapshot": {"maintenance_role": "...", "maintenance_role_ok": true, "database_state": {}}}
```

### 2.2 snapshot에서 해시로 검증된 계획 생성

```bash
.venv/bin/python scripts/production_cutover.py \
  --source-manifest /private/tmp/dino-off.json \
  --target-manifest /private/tmp/dino-on.json \
  --mode activate \
  --expected-campaign-version 3 \
  --snapshot-input /private/tmp/dino-cutover-snapshot.json \
  --plan-output /private/tmp/dino-cutover-plan.json
```

계획의 manifest SHA, campaign version, 생성 시각, DB 상태 해시를 사람이 다시 확인한다.

### 2.3 실행 SQL 생성

```bash
.venv/bin/python scripts/production_cutover.py \
  --source-manifest /private/tmp/dino-off.json \
  --target-manifest /private/tmp/dino-on.json \
  --mode activate \
  --expected-campaign-version 3 \
  --render-apply-sql /private/tmp/dino-cutover-plan.json \
  --confirm ACTIVATE_DINO_PRODUCTION \
  > /private/tmp/dino-cutover-apply.sql
```

생성된 SQL을 검토한 뒤 승인된 Supabase SQL 실행 수단으로 정확히 한 번 실행한다. SQL은 실행 시각에도 계획 만료, maintenance role, schema version, guard, campaign version, 기록 수, draw pool, 재고를 다시 검사한다. 하나라도 달라지면 전체 트랜잭션이 실패한다.

## 3. 활성화와 별칭 전환 순서

1. 베타 진입 경로를 격리한다.
2. ON 후보를 고유 URL로 배포하되 공개 별칭은 아직 옮기지 않는다.
3. 고유 후보 URL의 mutation이 canonical host 검사로 거부되는지 확인한다.
4. 2절의 snapshot, 계획, 실행 SQL을 만든 뒤 운영 DB에 실행한다.
5. 아직 공개 쓰기가 불가능한 동안 최신 상태로 rollback snapshot·계획·SQL을 미리 만든다.
6. 친근한 공개 별칭을 ON 후보로 전환한다.
7. 공개 도메인에서 설정·health·읽기 API와 첫 실제 참가 흐름을 확인한다. 실제 경품을 소진하는 합성 검사는 하지 않는다.

guard가 먼저 ON이 되어도 후보 고유 URL은 canonical host가 아니므로 mutation을 받지 않아야 한다. 별칭이 ON 후보로 옮겨진 뒤에만 공개 쓰기가 시작된다.

## 4. 복귀

### 공개 별칭 전환 전

미리 만든 rollback 계획이 1시간 이내이고 DB 상태가 그대로라면 다음 확인 문구로 SQL을 생성해 실행한다.

```bash
--confirm ROLLBACK_DINO_PRODUCTION
```

### 공개 쓰기가 시작된 뒤

1. 공개 별칭을 먼저 검증된 OFF 후보로 돌린다.
2. 활성 후보 고유 URL은 canonical host가 아니므로 mutation이 계속 차단되는지 확인한다.
3. 현재 DB 상태를 다시 snapshot하여 새 rollback 계획과 SQL을 만든다. 기존 활성화 직후 계획을 재사용하지 않는다.
4. rollback SQL을 실행한다.
5. guard `event_enabled=false`, campaign `PAUSED`, OFF manifest SHA를 확인한다.
6. 참가자·게임·추첨·수령 기록 수와 draw pool·재고가 복귀 전과 같은지 확인한다.

rollback은 운영 기록이 있어도 허용하고 보존한다. 이후 재활성화는 기록이 남아 있는 초기화되지 않은 환경에서 거부된다.

## 5. Direct maintenance DSN 경로

승인된 maintenance DSN이 별도로 제공될 때만 `--snapshot-input` 없이 `--plan-output`을 사용할 수 있다. 도구는 다음 주소만 허용한다.

- 이 프로젝트의 정확한 Supabase direct DB 주소와 `postgres` maintenance 사용자
- 이 프로젝트의 정확한 Supabase pooler 주소와 `postgres.<project-ref>` maintenance 사용자
- 테스트용으로 제한된 로컬 격리 PostgreSQL fixture

원격 연결은 저장소의 Supabase CA 인증서를 사용해 `verify-full`로 검증한다. 앱 역할(`dino_dev_app`, `dino_prod_app`)은 거부한다. 계획 적용은 `--apply-plan`과 mode에 맞는 `--confirm`이 모두 필요하다.

## 6. 중단 기준

- `CUTOVER_PLAN_EXPIRED` 또는 `CUTOVER_PLAN_STALE`: 강제 진행하지 않고 새 snapshot부터 다시 만든다.
- guard, manifest hash, campaign version, 일정, schema version, 수량 불일치: 원인을 고치기 전까지 중단한다.
- advisory/table lock timeout: 진행 중인 쓰기 트랜잭션을 확인하고 전환을 재시도한다.
- 별칭 전환 실패: OFF 후보로 별칭을 돌리고 기록을 지우지 않은 채 rollback 절차를 수행한다.
- 실행 결과가 불명확함: 같은 SQL을 즉시 재실행하지 않고 guard와 campaign을 읽어 실제 상태부터 확인한다.

## 7. 보관할 증적

- OFF/ON manifest 원본과 SHA-256
- 코드 SHA, 배포 ID, 공개 별칭 변경 시각
- 검토된 snapshot과 계획 SHA
- SQL 실행 결과와 실행자, 시각
- 전환 전후 guard·campaign 상태
- 전환 전후 기록 수, draw pool, 재고 비교
- 복귀 여부와 원인

manifest와 계획 파일에는 비밀번호나 maintenance DSN을 넣지 않는다.
