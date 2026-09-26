# Phase 2 Preview 혼합 부하 계획

상태: **2026-09-26 사용자 지시로 보류. 화면·기능 개선을 우선하며 사용자가 재개를 요청하기 전에는 부하용 참가자 준비나 원격 부하를 실행하지 않는다.** 아래 한도는 미승인 계획값이다. 2차 부하 실행은 하지 않았다.

이 계획은 `scripts/phase2_load.py`의 유일한 원격 사용 범위를 정의한다. Phase 1의 40분·30,000요청 예산, ledger, 참가자 cursor와 실행 증거는 그대로 보존한다. Phase 2는 별도 승인과 별도 ledger를 쓰며 이전 예산을 초기화하거나 이어 쓰지 않는다.

## 안전 한도

| 항목 | Phase 2 한도 |
| --- | ---: |
| 누적 예약 시간 | 12분 / 720초 |
| 누적 HTTP admission | 10,000회 |
| 실제 프로필 실행 | 1회 |
| 100 VU 단계 | 1회 |
| 200 VU 동시 burst | 1회 |
| 게임 버전 | 정확히 `2.0.0` |
| 환경 | local/test 또는 승인된 Vercel Preview; Production 금지 |

한 번의 `full` 실행은 100 VU admission 180초와 cleanup 90초, 200 VU admission 30초와 cleanup 90초를 합친 **390초**를 ledger에 먼저 예약한다. 예약은 실패·중단 시 환급하지 않는다. HTTP 호출도 네트워크 전 ledger에 먼저 기록하며 결과를 모르는 호출은 사용량에서 빼지 않는다.

Phase 2 ledger에는 최상위 `phase: 2`가 있어야 한다. 기존 파일에 이 값이 없거나 다른 값이면 runner가 쓰기 전에 거절한다. 따라서 Phase 1 ledger를 Phase 2 경로로 전달해도 초기화·변경하지 않는다. 한 번이라도 실행 예약이 생긴 Phase 2 ledger는 두 번째 실행을 거절한다.

## 트래픽 모양

| 순서 | 단계 | VU | admission window | 형태 | 최대 flow |
| --- | --- | ---: | ---: | --- | ---: |
| 1 | `100-stage` | 100 | 180초 | flow 종료 뒤 기본 45초 think time | 400 |
| 2 | `200-burst` | 200 | 30초 | 200 worker barrier 동시 시작, 각 worker 정확히 1 flow | 200 |

최대 600개 합성 참가자를 한 번씩 사용한다. 보수적 상한은 preflight 2회 + flow당 11회 + 선택적 claim 30회 = **6,632 HTTP 호출**이다. 이는 10,000회 한도보다 작다. 실제 retry나 알 수 없는 네트워크 결과도 ledger admission을 소비하므로 실행 전 잔여량이 전체 보수 상한보다 적으면 시작하지 않는다.

200 VU burst는 `--think-time`이 허용 최솟값인 10초여도 worker마다 정확히 한 번만 flow를 실행한다. think time은 반복 admission이 있는 100 VU 단계의 flow 간격에만 영향을 준다.

## 혼합 사용자 flow

각 합성 참가자는 다음 순서를 한 번만 수행한다.

1. `GET /api/me`로 기본권 1장, 초대권 0장 확인
2. 게임 세션 생성과 시작
3. 서버가 발급한 무작위 seed로 로컬 `2.0.0` 결정론 fixture 계산
4. 실제 tick 시간만큼 기다린 뒤 `score`, `ticks`, `jump_ticks` 제출
5. 복주머니 상태 조회, 3개 중 하나 선택, scratch 완료
6. 랭킹, 추천 현황, 수령함 조회
7. 당첨이고 20번째 flow이면 합성 수령 정보 접수
8. `page_view`와 `share_attempted`를 한 batch로 기록

흐름은 entry, game start, finish, draw, claim read/write, share-state read, ranking, tracking을 함께 섞는다. 공유 이벤트의 `share_sheet_closed`나 실제 전달을 만들지 않으며 `attempted`만 보낸다. 모든 개인정보 입력은 `TEST_` 합성값이다.

## v2 물리 fixture

- 일반 flow는 Python `game_verifier_v2.simulate()`로 해당 seed의 정상 collision 결과를 계산하고 같은 서버 verifier로 다시 검증한다.
- 매 100번째 flow, 최대 6회만 기존 JS fixture bot을 subprocess로 시도한다. rich fixture는 75초·4,500 tick 안에 정상 collision으로 끝나고 코인 1개 이상·부활 2회 이상을 서버 verifier가 재현할 때만 사용한다. 이 조건을 만족하지 못하면 tick을 자르거나 결과를 꾸미지 않고 같은 seed의 실제 no-jump collision fixture로 돌아간다. seed `4` 회귀값은 68.8초·코인 14개·부활 2회이고, seed `5`는 genuine no-jump fallback을 검증한다. 원격 seed는 서버가 무작위로 발급하므로 각 원격 flow에서 rich 결과가 나온다고 미리 주장하지 않는다.
- 200개 worker마다 Node subprocess를 만들지 않는다. rich fixture 6개만 별도 계산해 CPU·프로세스 폭증을 막는다.
- 서버 세션의 wall-clock 검증을 우회하지 않는다. fixture tick에 해당하는 실제 시간을 기다리고 v2 활성 세션 TTL인 12분 안에서 완료한다.
- 클라이언트가 주장하는 코인·하트·부활 수는 제출하지 않는다. 서버가 seed와 `jump_ticks`로 summary를 재현한다.

## 원격 실행 승인 게이트

기본 실행은 항상 network-free dry-run이다.

```bash
python3 scripts/phase2_load.py
```

원격 실행은 향후 별도 승인 뒤 `--execute --mode remote`와 mode `0600` 승인 marker가 모두 필요하다. marker 예시는 다음과 같으며 값은 실제 immutable Preview와 합성 캠페인에 정확히 일치해야 한다.

```json
{
  "phase": 2,
  "approved_remote": true,
  "base_url": "https://exact-preview.vercel.app",
  "deployment_id": "dpl_exact",
  "campaign_id": "synthetic-phase2-campaign",
  "max_api_calls": 10000,
  "max_duration_seconds": 720,
  "stages": ["100-stage", "200-burst"]
}
```

승인 후 명령 형태만 다음과 같이 준비한다. 현재 작업에서는 실행하지 않는다.

```bash
.venv/bin/python scripts/phase2_load.py \
  --execute --mode remote \
  --base-url https://exact-preview.vercel.app \
  --expected-deployment-id dpl_exact \
  --expected-project-ref igfrnexknwtiljdqjrbp \
  --cohort .local/phase2/remote-cohort.json \
  --ledger .local/phase2/remote-load-budget.json \
  --report .local/phase2/remote-load-report.json \
  --approval-marker .local/phase2/remote-approval.json
```

runner는 원격 URL이 명시적 HTTPS `*.vercel.app` origin인지 확인하고 `/api/health`와 `/api/config`에서 deployment, Preview 환경, Supabase project ref, `dino_dev`, synthetic/test seed, 캠페인, `2.0.0`을 모두 대조한다. Production 또는 버전 불일치는 즉시 중단한다.

## 중단 조건

- HTTP 5xx, prepared participant 인증 거절, inventory 오류
- 10,000 HTTP admission 또는 720초 누적 예약 초과
- 두 번째 실행 예약 시도
- 참가자 cohort 부족 또는 cohort 정체성 변경
- Production, deployment, project, schema, campaign, synthetic/test seed, 게임 버전 불일치
- v2 fixture 로컬 교차 검증 실패, 서버 finish 거절, rich summary 소실
- worker가 각 단계의 admission 시간과 90초 cleanup 범위를 초과

429, timeout, 예상하지 못한 응답과 예외는 즉시 전체 실행을 멈추고 최종 실패로 판정한다. 알 수 없는 네트워크 결과를 성공으로 간주하지 않는다.

## 결과와 비용

실행 시 report에는 원본 쿠키·참가자 ID 없이 cohort fingerprint, deployment ID, 단계별 endpoint 지연, 상태 코드, timeout, 완료 flow, 예약·실제 시간, admission·completion 수만 기록한다. 파일은 mode `0600`이다.

성능 목표는 일반 API p95 1초 이하, finish/draw p95 2초 이하, unexpected failure 1% 미만을 Phase 1과 같은 비교 기준으로 제안한다. 실행 전 수치이므로 통과로 표시하지 않는다.

### 1회 실행의 추가 비용 추정

아래 금액은 **기존 Vercel Pro 프로젝트와 기존 Supabase Pro 프로젝트를 그대로 사용**하고, 6,632 HTTP 호출·390초 예약 프로필을 한 번 실행할 때의 한계비용 추정이다. 현재 결제 주기의 남은 Vercel 월 크레딧과 Supabase egress 포함량은 CLI 프로젝트 조회에서 확인되지 않았으므로, 실제 청구 추가액은 `US$0`일 수도 있고 아래 사용량 금액만큼 늘어날 수도 있다. 세금과 환율은 포함하지 않는다.

Vercel은 Fluid Compute에서 Active CPU, Provisioned Memory, Invocation을 따로 계산한다. 서울 `icn1` 공식 단가는 Active CPU `US$0.169/시간`, Provisioned Memory `US$0.014/GB-시간`, Invocation `US$0.60/백만 회`다. 공식 기본값은 Standard `2 GB / 1 vCPU`지만 프로젝트 대시보드에서 4 GB로 변경할 수 있으므로, 실행 직전 배포의 Resources 화면에서 실제 값을 확인한다. 저장소 `vercel.json`은 Function region을 `icn1`로 지정하고, 읽기 전용 CLI 조회는 연결된 프로젝트가 Pro임을 확인했다. 참고: [Vercel Fluid Compute 가격](https://vercel.com/docs/functions/usage-and-pricing), [Function 메모리 설정](https://vercel.com/docs/functions/configuring-functions/memory), [Pro 월 크레딧](https://vercel.com/docs/plans/pro-plan), [CDN 전송 가격](https://vercel.com/docs/manage-cdn-usage).

| Vercel 항목 | 계산 가정 | 6,632회 예상 사용량 비용 |
| --- | --- | ---: |
| Invocation | 모든 요청이 과금 대상이라고 가정 | `6,632 / 1,000,000 × $0.60 = 약 $0.004` |
| Active CPU | 요청당 실제 CPU 25~100ms 가정; DB 대기 시간 제외 | 약 `$0.008~$0.031` |
| Provisioned Memory | 2 GB, 390초 동안 평균 10~50개 instance-equivalent가 유지된다고 가정 | 약 `$0.030~$0.152` |
| Fast Origin Transfer | 요청·응답 합계 평균 10~50KB, 읽기 전용 결제 조회의 서울 계정 단가 `$0.24/GB` 적용; 실제 payload 미측정 | 약 `$0.016~$0.080` |

따라서 Vercel 사용량만 보면 약 **`US$0.06~$0.27`** 범위다. 이 요청은 Edge Request 사용량에도 포함되지만 Pro의 월 1,000만 회 포함량보다 매우 작다. 현재 결제 주기의 남은 포함량은 미확인이므로 승인 직전에 함께 확인한다. Fluid Compute는 한 인스턴스가 여러 요청을 동시에 처리하므로 VU 수가 그대로 인스턴스 수가 되지는 않는다. 반대로 실제 메모리가 4 GB이거나 응답 지연으로 인스턴스 생존 시간이 길어지면 Provisioned Memory 비용이 커진다.

Supabase는 새 프로젝트를 만들거나 Compute 크기를 바꾸지 않는다. 공식 문서상 프로젝트 Compute는 요청 수가 아니라 실행 중인 전용 인스턴스 시간으로 과금되므로, 이미 계속 실행 중인 같은 프로젝트에서 6.5분 테스트를 추가해도 별도의 새 Compute 프로젝트 비용은 생기지 않는다. 다만 Shared Pooler/Database 응답 egress는 월 포함량을 소진한다. Pro의 uncached egress 포함량은 250 GB이고 초과분은 `US$0.09/GB`다. 이 실행이 Supabase egress `0.1~0.5 GB`를 만든다고 가정하면 포함량 소진 후 한계비용은 약 **`US$0.009~$0.045`**다. 참고: [Supabase Compute 과금](https://supabase.com/docs/guides/platform/manage-your-usage/compute), [Supabase Egress 과금](https://supabase.com/docs/guides/platform/manage-your-usage/egress).

두 서비스를 합친 **실행 전 계획 범위는 약 `US$0.07~$0.32`**이다. 월 크레딧과 포함량이 남아 있으면 실제 추가 청구액은 더 작아질 수 있다. 이 범위는 다음 미측정값을 명시적으로 가정한 값이며 가격 보장이 아니다.

- 배포 Function이 Standard 2 GB라는 가정
- 요청당 Active CPU 25~100ms
- 390초 동안 평균 10~50개 Fluid instance-equivalent
- Vercel 요청·응답 10~50KB, Supabase egress 총 0.1~0.5GB
- 현재 Vercel 월 크레딧과 Supabase 250GB 포함량의 남은 값은 미확인

비용 민감도 확인용 보수 시나리오로 200개 2GB 인스턴스가 390초 내내 유지되고, 6,632회 모두 요청당 CPU 100ms를 쓰며, 전송량과 Supabase egress가 위 범위 상단이라고 놓으면 약 **`US$0.77`**다. 이는 예상 인보이스가 아니라 Fluid 동시성 절감이 전혀 없다고 보는 과대 산정이다. 10,000-call·720초 안전 한도는 실행 중단 장치이며 비용 상한이 아니다. 응답 크기, CPU 시간, 실제 인스턴스 수가 가정을 넘으면 비용도 이 수치를 넘을 수 있다.

실행 승인 직전에는 Vercel Usage에서 이번 결제 주기의 Active CPU, Provisioned Memory, Invocations, Edge Requests, Fast Origin Transfer와 남은 월 크레딧을 확인하고, 배포 Resources에서 실제 메모리를 확인한다. Supabase Usage에서는 Compute 크기 변경이 없는지와 Unified Egress 잔여량을 확인한다. 이 확인 전에는 `US$0.07~$0.32`를 예산 계획값으로만 사용한다.

## 준비 단계 검증

- dry-run 기본값이 네트워크와 fixture subprocess를 호출하지 않는지 테스트
- Phase 2 호출 예산 소진 시 fail-closed 테스트
- Phase 1 ledger 전달 시 byte-for-byte 보존과 거절 테스트
- `1.2.0` 등 버전 불일치 거절 테스트
- Production 환경 거절 테스트
- exact Phase 2 원격 승인 marker 일치·불일치 테스트
- seed `4`의 68.8초·코인 14개·부활 2회 rich fixture와 seed `5`의 genuine no-jump fallback을 Python verifier와 교차 검증
- 실제 원격 호출, DB 쓰기와 부하는 이번 준비 범위에서 수행하지 않음
