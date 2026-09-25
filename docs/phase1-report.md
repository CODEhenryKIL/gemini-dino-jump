# 공룡 점프 1차 작업 결과 보고서

작성일: 2026-09-25

상태: 구현 및 기능 검증 수행, **성능 목표 미달·추가 순간 부하 1회 수행 및 연결 한도 확인**

작업 브랜치: `codex/phase1-clean-start`

## 1. 현재 판정

게이트러너 제거 기준에서 다시 시작한 공룡 점프 1차 범위는 코드 구현, 원격 Supabase 전용 영역, 관리자 권한, 보호된 Vercel Preview, 참가자·관리자 실제 브라우저 흐름까지 구현하고 검증했다.

그러나 1차 작업 전체를 완료로 판정할 수는 없다.

- OLD2(`b3d404a`) 전체 부하 재실행은 10→50→100→200 VU와 burst를 모두 끝냈고 예기치 않은 실패와 timeout은 없었다. 다만 `/api/me`와 게임 시작 p95가 1초 목표를 넘었다.
- NEW3(`da3fbf4`) burst 재검증은 503 오류 57건으로 serious stop 조건에 도달했다. 연결 단계 오류였으며 SQLSTATE가 기록되지 않은 연결 오류로 분류됐지만, 어느 자원 한도가 직접 원인이었는지는 아직 확정하지 않았다.
- 최신 `a4a8606` 추가 burst는 247호출 중 503 15건으로 자동 중단됐다. 같은 시간대 Supavisor 로그에 `(EMAXCONN) max client connections reached, limit: 200`이 확인됐다. 연결 한도에 도달한 증거이며, Vercel 인스턴스별 연결 분포는 아직 측정하지 않았다.
- 따라서 **기능 구현과 주요 운영 검증은 수행됐지만 성능 인수 기준은 실패한 상태**다. 연결 수 관리 개선과 재검증이 필요하다. 사용자가 누적 시험 한도를 40분으로 늘렸다. 다음 부하 시작 전에 신호를 알려 직접 접속을 함께 확인한다.
- Draft PR은 검토 상태로 유지하고 Production은 변경하지 않는다.

## 2. 구현 범위

### 참여자·게임권·초대

- 참여자는 `HttpOnly`, `SameSite=Lax` 쿠키로 복원하고 브라우저 저장소에 참여자 인증 토큰을 저장하지 않는다.
- 최초 기본권은 1장이고, 초대권은 최대 3장까지 보유한다.
- 초대권 잔액이 3장이 되는 순간 10시간 추가 적립 대기를 시작한다. 대기 중 방문은 이후 자동 이월하지 않는다.
- 초대 방문은 화면이 보이는 상태에서 3초 이상 활동하고 클릭 또는 터치가 있어야 서버 판정을 요청한다.
- 잘못된 초대 코드, 자기 초대, 잔액 가득 참, 대기 중, 중복 관계를 서버 판정 사유로 구분한다.
- 공유 식별자는 인증값과 분리한 불투명한 `share_id`를 사용하고, 초대 보상 중복은 행사·초대자·방문자 관계로 방지한다.

### 게임·장애 복구

- 기존 공룡 점프 물리 엔진과 조작 안내를 유지하면서 서버가 세션, seed, tick과 입력 결과를 검증한다.
- 정상 충돌과 자발적 이탈, 네트워크·클라이언트·서버 장애를 구분한다.
- 결과 응답이 유실되면 개인정보와 인증값이 없는 최소 결과 payload와 같은 재시도 키로 서버 결과를 먼저 조회한다.
- 장애 신고는 세션 ID, 사유, tick, 재시도 ID와 서버 체크포인트를 대조한 뒤 자동 또는 관리자 심사로 처리한다.
- 기본권과 초대권의 소비·예약·환급은 서버 원장으로 처리한다.

### 복주머니·수령·랭킹

- 정상 검증 게임을 완료한 참가자는 행사당 복주머니를 한 번만 연다.
- 서버가 결과를 한 번 확정하며 새로고침·재접속 뒤에도 같은 결과를 돌려준다.
- 스크래치 완료는 서버 저장 성공 뒤 기록하고, 응답 유실 시 같은 키로 재시도한다.
- 실제 쿠폰 자동 발급 없이 관리자가 연락 및 지급 상태를 수동 관리한다.
- 잠정 TOP3 연락 요청은 순위가 내려가거나 결과 화면을 벗어나도 유지하며 최종 수상 확정과 구분한다.

### 관리자·지표

- 관리자는 실제 Supabase Auth로 로그인하고 서버가 별도 관리자 멤버십과 권한을 다시 검사한다.
- 개인정보는 `claims:read` 권한이 있는 운영 업무 화면에서만 표시하고 분석 표와 이벤트에는 포함하지 않는다.
- 수령 상태, 담당자, 버전, 사유, 외부 전달 여부는 낙관적 잠금과 감사 기록으로 관리한다.
- 장애 환급은 서버 증거와 체크포인트를 바탕으로 자동 승인 또는 관리자 승인·거절 상태를 구분한다.
- 로딩, 화면 체류, 게임 단계, 초대, 공유, 복주머니, 스크래치, 수령, TOP3, Gemini 노출·클릭을 개인정보 없이 집계한다.
- 지표에는 분자·분모, 고유 참가자, 이벤트 수, 관찰 구간, 원 집계·추정 구분, 합성 데이터 여부와 정의를 표시한다.

## 3. 자동 검증

| 항목 | 최종 확인 결과 |
| --- | --- |
| Python 전체 검사 | **110개 통과** |
| Node 프론트 회귀 검사 | **28개 통과** |
| JavaScript 구문 검사 | 통과 |
| Python compileall | 임시 pycache 경로에서 통과 |
| Git whitespace 검사 | 통과 |

Python 검사에는 PostgreSQL 기능·동시성·권한, 5,000명 합성 데이터, 지표, 관리자 상태 변경과 부하 도구 보호 검사가 포함된다. 자동 검증 통과는 아래 원격 성능 실패를 대체하지 않는다.

- [Python 검사 원본](evidence/phase1-local-python.txt)
- [Node 검사 원본](evidence/phase1-local-node.txt)
- 최신 기능 수정 전체에 대해 Python 110개, Node 28개를 다시 실행했다. 쿠키/관리자 권한 취소 뒤 캐시 재생 차단, 환급 거절 상태 보존, 동일 참가자 동시 추첨, 쿨다운 경계, 실제 빈 DB migration 및 지표 필터 검사를 포함한다.
- 로딩 완료와 이번 방문의 게임 시작 귀속, Gemini 복사·공유 관측, 관리자 순위·이탈 체류 표시를 보완했다. 게임 물리 엔진은 `f57c3d1`과 diff가 없다.

## 4. 실제 브라우저 검증

### OLD2에서 완료한 참가자·관리자 흐름

- 쿠키 참여자 복원과 새로고침 뒤 동일 참가자 복원을 확인했다.
- 실제 게임을 충돌까지 실행했고 서버가 `score=32`, `ticks=194`, `FINISHED`, `VERIFIED`로 저장했다.
- 결과 화면의 최고 점수·랭킹과 잠정 TOP3 연락 정보 접수를 확인했다.
- `NO_PRIZE` 복주머니 결과와 스크래치 완료가 새로고침·재접속 뒤에도 동일하게 복원되는 것을 확인했다.
- 초대 링크 복사 상태와 Gemini 콘텐츠 이동 흐름을 확인했다.
- 390px 모바일 화면에서 가로 넘침이 없음을 확인했다.
- 실제 Supabase Auth 관리자로 로그인해 지표, 수령 원장, TOP3 연락 정보와 장애 환급 심사를 확인했다.

### NEW3에서 재확인한 화면 수정

- 합성 TOP3 정보 제출 직후 버튼이 비활성화된 `정보 접수 완료` 상태로 표시되어 중복 제출 진입이 사라진 것을 확인했다.
- 정상 게임 완료 뒤 홈에서 완료된 세션을 `진행 중 게임 복원`으로 잘못 표시하지 않는 것을 확인했다.
- 이때 기본권 0장, 초대권 0장, 최고 점수 32점과 비활성화된 `게임권이 필요해요` 상태가 일치했다.

[실제 브라우저 검증 기록](evidence/phase1-browser-verification.md)

## 5. 원격 Supabase 적용·보존

| 항목 | 결과 |
| --- | --- |
| 대상 | 기존 Supabase 프로젝트 재사용 |
| 전용 스키마 | `dino_dev` |
| migration | 2개 적용 |
| 전용 테이블 | 25개 |
| 합성 seed 재고 | 25개 |
| 전용 접속 역할 | `dino_dev_app` |
| TLS·호스트 검증 | `verify-full` 성공 |
| 기존 데이터 | 보존 확인 |

- 새 Supabase 프로젝트를 만들지 않고 기존 프로젝트 안에 공룡 점프 전용 스키마를 구성했다.
- 전용 역할은 필요한 `dino_dev` 범위에만 접근하며 기존 `public`, 기존 `dino`, Auth, Storage 데이터를 초기화하지 않았다.
- 기존 `public` 11개 테이블, 기존 Auth 사용자, 합성 관리자 2명, Storage 객체 47개와 기존 `dino` 5,000행을 보존했다.
- 원격 참가자 5,005명, 게임 세션 2,303개, 검증 완료 2,212개, 추첨 2,163개를 재확인했다.
- 중복 추첨 0건, 중복 보상 0건, 잘못된 게임권 잔액 0건이었다.
- 재고는 총 25개이며 예약 24개, 지급 1개, 할당 25개, 중복 할당 0건이었다.
- 이 최종 대조 결과는 [원격 최종 reconciliation](evidence/phase1-remote-final-reconciliation.json)에 보존했다.

관련 근거:

- [원격 자원 보존 검사](evidence/phase1-remote-preservation.json)
- [원격 수령 권한·멱등성 smoke](evidence/phase1-remote-claim-smoke.json)

## 6. 원격 관리자·운영 원장 검증

- 합성 관리자 2명을 멤버십에 등록했다.
- 각 관리자는 `analytics:read`, `claims:read`, `claims:write`, `faults:read`, `faults:write`, `campaign:write`의 정확한 여섯 권한만 가진다.
- 관리자 1 계정으로 실제 장애 환급 승인 흐름을 완료했다.
- 관리자 2 계정으로 합성 DRAW 수령 건을 `INFORMATION_RECEIVED → PENDING_REVIEW → CONTACTED → PAID` 순서로 변경했다.
- 해당 건은 버전 4, 외부 전달 표시 `true`로 저장됐고 원격 DB에서 지급 완료 1건, 예약 재고 24개, 수령 감사 기록 4건을 확인했다.
- 이 수령 건은 운영 절차 검증용 합성 데이터이며 실제 연락이나 경품 전달은 하지 않았다.
- 수령 API의 동일 요청·동일 키 재전송은 같은 결과를 반환했고, 다른 참가자의 수령 정보 제출 시도는 404로 차단됐다.
- 최신 재확인 시 관리자 멤버십 2명과 관리자 감사 기록 5건을 확인했다.
- 잠정 RANKING 수령 건은 최종 수상 확정 전 `PAID`로 바꿀 수 없고, DRAW 수동 지급 흐름만 실제 지급 완료로 검증했다.

## 7. 원격 부하 검증

최초 실행은 2,056호출 뒤 100 VU에서 503 14건으로 중단됐다. 요청마다 새 TLS 연결을 만들던 구조를 최대 8개 재사용 연결로 바꾼 뒤 OLD2 전체 재실행을 수행했다.

### 7.1 OLD2 전체 재실행

OLD2(`b3d404a`)에서 10→50→100→200 VU와 burst를 모두 수행했다.

| 항목 | 결과 |
| --- | --- |
| 총 API 호출 | 19,718회 |
| 실제 경과 시간 | 715.64초 |
| 예기치 않은 실패 | 0건 |
| timeout | 0건 |
| `/api/me` p95 | 1,045.97ms |
| 게임 시작 p95 | 1,597.36ms |
| 게임 완료 p95 | 925.35ms |
| 추첨 p95 | 1,043.82ms |
| serious stop | 발생하지 않음 |

- 게임 완료와 추첨은 2초 목표 안에 들어왔다.
- 참가자 조회와 게임 시작은 1초 목표를 넘었다.
- 모든 단계를 오류 없이 끝냈다는 안정성 근거는 확보했지만, 성능 인수 전체 통과로 판정하지 않는다.

[OLD2 원격 부하 재실행 원본](evidence/phase1-remote-load-rerun.json)

### 7.2 NEW3 burst 재검증

NEW3(`da3fbf4`)의 별도 burst 재검증은 **실패**했다.

| 항목 | 결과 |
| --- | --- |
| 총 호출 | 336회 |
| 503 오류 | 57건 |
| 실제 경과 시간 | 27.64초 |
| serious stop | `true` |
| 판정 | 실패, 원인 분석 중 |

- 오류가 serious stop 조건에 도달해 이후 결과를 성능 승인 근거로 사용하지 않는다.
- 해당 실행 원본은 [NEW3 burst 원본](evidence/phase1-remote-load-burst-new3.json)에 보존했다.
- 현재까지 원격 부하 누적은 22,114호출, 예약 실행 시간 1,684초다.
- 연결 단계 오류였고 SQLSTATE는 기록되지 않았다. 직접적인 자원 한도 원인은 아직 확정하지 않았다.
- `fe4fe13`에서 IP 제한 실험을 되돌렸다. 서버 코드는 OLD2와 동일하고 화면에는 `333c7c5`에서 확인한 수정이 포함된다. 추측에 기반한 pool limit 또는 TTL 변경은 넣지 않았다.
- burst 직후 남은 예약 가능 시간은 116초로 burst 예약 120초보다 적었다. 최종 Preview 읽기 전용 smoke 2회·40초 예약을 더해 최종 누적은 **22,116호출·1,724초**, 남은 예약 시간은 76초다. 추가 부하 실행은 하지 않았다.

Vercel의 연결 오류 분류와 같은 시간대 Supavisor handshake/connecting 오류를 [진단 근거](evidence/phase1-burst-diagnostics.json)에 기록했다. 로그 집계 시간대와 부하 실행 요청 집합은 같지 않으므로 오류 건수를 일대일 대응하지 않는다.

### 7.3 사용자 승인 추가 burst — 최신 a4a8606

사용자가 추가 시험 1회와 시간 한도 30→32분 확대를 승인했다. 요청 30,000회 한도와 기존 원장·참가자 커서는 보존했다.

| 항목 | 결과 |
| --- | --- |
| 배포 | `dpl_9jvaU7ja7sPZW3BJdQtyQvhFEfJo` |
| 총 호출 / 503 | 247회 / 15건 |
| 실제 경과 / timeout | 27.87초 / 0건 |
| 입장 p95 / 게임 생성 p95 | 1,833.97ms / 1,725.16ms |
| 완료된 게임 흐름 | 0건, 자동 중단 |
| 누적 API 호출 | 22,363 / 30,000회 |
| 누적 예약 시간 | 1,844 / 1,920초 |
| 남은 합성 참가자 | 2,374명 |

- **실패**다. 완료·추첨 표본이 없으므로 해당 지표의 자동 true를 통과 근거로 사용하지 않는다.
- 같은 시간대 Supavisor에서 접속 한도 관련 로그 56건 및 `(EMAXCONN) max client connections reached, limit: 200` 메시지를 확인했다. Vercel 표본의 오류 분류도 DB connection이었다. 로그 건수와 부하 요청 15건은 일대일 대응하지 않는다.
- DB 재고·추첨·초대 보상 중복과 잘못된 게임권 잔액은 0건이다. 원격 스냅샷은 별도 브라우저 테스트도 포함할 수 있다.
- 이전 실행보다 오류 수가 적다는 사실만으로 개선 또는 안정성을 확정하지 않는다. 연결 한도에 도달한 원인은 확인했지만 인스턴스별 연결 수와 해제 동작을 더 검토해야 한다.
- 새 유료 자원·DB 크기 변경은 없었다. 200명 추가 실행은 자동 반복하지 않는다.

[추가 burst 원본](evidence/phase1-remote-load-burst-audit.json) · [연결 한도 진단](evidence/phase1-burst-audit-diagnostics.json)

성능 인수는 계속 **미통과**다. 작업 지시서의 실패 보고 규칙에 따라 코드와 측정 증거를 납품하며 성능 목표 달성을 주장하지 않는다.

### 7.4 자원·비용 관측 범위

- 부하 실행 중 관측한 프로젝트 DB 연결은 23~31개, 공룡 점프 연결은 9~16개였고 해당 표본의 lock wait는 0이었다. 순간 최대치를 보장하는 연속 측정은 아니다.
- 새 유료 프로젝트·유료 Branch·상위 DB 규격은 만들지 않았다. Web Analytics는 사용자 승인에 따라 켜져 있다.
- 2026-09-25 조회 기준 Vercel 공룡 점프 프로젝트 사용량 금액은 약 $0.02133, 청구액은 반올림 $0.00이다. Supabase 현재 비용은 기존 Pro $25이고 Micro compute $0.74는 크레딧 −$0.74로 상쇄됐다. 비용 상한은 켜져 있다. 대시보드 예상 비용은 $27.50이며 차액의 세금 여부는 별도로 확인하지 않았다.
- 이는 추가 burst 직전의 [비용 스냅샷](evidence/phase1-cost-snapshot.json)이다. 반영 지연과 기존 기본요금이 있으므로 최종 무료 또는 향후 추가요금 없음으로 보장하지 않는다. CPU 연속 측정값은 확보하지 못했다.
- 부하 도구와 별도 API smoke 호출은 위 누적 원장에 기록했다. 실제 브라우저 조작·플랫폼 관리 API는 별도 검증이며 원장 수치를 서비스 전체 트래픽으로 해석하지 않는다.

### 7.5 연결 반환 개선 후보

- 프로세스당 동시 연결 8개는 유지하고, 성공 요청 뒤 유휴 연결은 1개까지만 보유한다. 나머지는 즉시 닫는다. 다음 요청이나 백그라운드 타이머를 기다리지 않는다.
- 로컬 검사에서 8개 동시 요청 완료 후 후속 checkout 없이 열린 연결 1개, 순차 요청 TLS 재사용, 동시 활성/실제 열린 연결 8개 이하를 검증했다. Python 전체 110개 통과.
- 이는 유휴 연결 누적을 줄이는 후보이며, 전체 배포의 동시 client 200개 미만을 보장하는 전역 제한은 아니다. 원격 성능은 다음 실행 결과로 판정한다.

### 7.6 78ce9be 공동 시험 및 후속 후보

- 사용자에게 시작을 알린 뒤 200명을 동시에 투입했다. 사용자는 “화면과 게임이 정상으로 보였어”라고 직접 확인했다.
- 별도 부하 도구는 383호출 중 503 17건, timeout 0건, 완료 흐름 0건으로 중단됐다. 입장 200건은 성공했지만 게임 생성/시작에서 실패했다. 누적 22,746호출·1,964초 예약이며 확대 승인 한도는 40분이다.
- 같은 시간대 Supavisor client 한도 로그 38건을 확인했다. 유휴 1개 보유만으로 전체 접속 한도 문제가 해결되지 않았다.
- 후속 후보는 실행·대기 요청이 겹칠 때만 연결을 재사용하고 마지막 요청 종료 시 열린 유휴 연결을 모두 닫는다. 완전 순차 요청은 TLS를 다시 연결하므로 원격 지연도 재확인해야 한다.
- 로컬 11개 연결 검사: 9개 겹친 요청이 연결 8개만 사용하고 마지막에 0개로 정리됨; 실패 시 슬롯·borrower 회복; 후속 checkout/백그라운드 타이머 불필요.

[공동 시험 원본](evidence/phase1-remote-load-burst-pool.json)

### 7.7 b2f2eed 연결 정리 후보와 후속 보완

- 시작을 알린 뒤 실행한 200명 동시 시험은 301호출 중 503 39건, timeout 0건, 완료 흐름 0건으로 중단됐다. 부하 구간은 1.95초, 준비와 공동 시작 대기를 포함한 실제 실행은 54.9초였다. 연결 정리만으로 통과하지 못했다.
- 누적 23,047호출·2,084초 예약이다. 승인된 30,000호출·40분 한도와 참가자 집단을 보존한다.
- 후속 보완은 새 DB 연결이 EMAXCONN으로 거부된 경우에만 최대 3회 재시도한다. 추가 시도 시작 시한은 0.75초이며 쿼리·게임권·추첨 처리를 재실행하지 않는다. 연결 검사 16개와 Python 전체 115개가 통과했다. 원격 통과 판정은 별도 측정이 필요하다.

[연결 정리 후보 시험 원본](evidence/phase1-remote-load-burst-drain.json)

## 8. 배포·주소 상태

- Production 배포와 기존 Production 링크는 변경하지 않았다.
- 보호된 Preview의 별도 주소는 [google-korea-team-gemini.vercel.app](https://google-korea-team-gemini.vercel.app)이다.
- 최종 기능 검토 Preview는 `a4a8606`, 배포 ID `dpl_9jvaU7ja7sPZW3BJdQtyQvhFEfJo`이며 READY다.
- [최종 불변 Preview 주소](https://dino-nanobanana-ntvhvzhmq-henry-kils-projects.vercel.app)의 환경·프로젝트·스키마·합성 guard·방문 통계 설정을 확인했다.
- 별도 주소는 이 최종 Preview에 연결됐다. 비로그인 HEAD 요청의 Vercel 인증 페이지 302 이동으로 접근 보호 유지를 확인했다.
- 별도 주소는 기능 수정 검토용이며 성능 승인 또는 Production 공개가 아니다. 최신 버전에는 추가 burst만 실행했고 전체 단계 결과는 OLD2 기록과 구분한다.
- 사이트 메타데이터에는 `구글 코리아 팀 제미나이`를 반영했고 게임명 `공룡 점프`는 유지했다.
- 검토용 변경은 [Draft PR #2](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/2)에 유지한다.

## 9. Production 적용 전 결정·입력 필요 항목

아래 항목은 합성값이나 비활성 상태로 검증했으며 실제 Production 값은 아직 확정하지 않았다.

| 결정 ID | 필요한 결정 |
| --- | --- |
| D03 | 캠페인 실제 시작·종료 시각 |
| D04 | 동점자 처리와 상품 분배 규칙 |
| D05 | 학생 인증 및 Gemini 이용 증빙 방식 |
| D10 | 마감 전에 시작하고 마감 뒤 완료한 게임의 인정 규칙 |
| D12 | 개인정보 보관 기간, 고지문, 동의 문구 |
| Notion·공식 링크 | 승인된 Notion 안내 URL, Gemini 공식 이동 URL, 실제 혜택 문구 |

- 승인되지 않은 Notion 및 외부 콘텐츠 이동은 비활성 상태와 사유를 표시한다.
- 임의 URL을 코드에 넣지 않고 승인된 공식 링크만 공개 설정으로 주입하는 방식을 유지한다.

## 10. 별도 보안 관찰과 권고

- 기존 `public` 영역 함수에서 `search_path` 또는 `SECURITY DEFINER` 관련 경고가 관측됐다.
- Supabase Auth의 유출 비밀번호 보호 설정이 꺼져 있는 상태가 관측됐다.
- 두 항목은 공룡 점프 전용 `dino_dev` 구현 이전부터 존재한 기존 영역이며 기존 서비스 범위를 임의로 변경하지 않기 위해 이번 작업에서는 수정하지 않았다.
- Production 오픈 전 기존 함수의 소유자·실행 권한·고정 `search_path`를 별도 검토하고, 관리자 계정 정책과 함께 유출 비밀번호 보호 활성화를 검토해야 한다.
- 운영 링크는 전체 URL이나 임의 query를 분석 이벤트에 저장하지 않고 승인된 콘텐츠 키와 상태만 기록해야 한다.

공식 후속 근거: [고정 search_path](https://supabase.com/docs/guides/database/database-linter?lint=0011_function_search_path_mutable), [anon SECURITY DEFINER 실행 권한](https://supabase.com/docs/guides/database/database-linter?lint=0028_anon_security_definer_function_executable), [authenticated SECURITY DEFINER 실행 권한](https://supabase.com/docs/guides/database/database-linter?lint=0029_authenticated_security_definer_function_executable), [유출 비밀번호 보호](https://supabase.com/docs/guides/auth/password-security#password-strength-and-leaked-password-protection).

## 11. 증거·검토 링크

| 산출물 | 위치 |
| --- | --- |
| Python 115개 검사 | [phase1-local-python.txt](evidence/phase1-local-python.txt) |
| Node 28개 검사 | [phase1-local-node.txt](evidence/phase1-local-node.txt) |
| 최초 부하 실패 | [phase1-remote-load-initial.json](evidence/phase1-remote-load-initial.json) |
| 최종 Preview smoke | [phase1-final-preview-smoke.json](evidence/phase1-final-preview-smoke.json) |
| OLD2 원격 전체 부하 | [phase1-remote-load-rerun.json](evidence/phase1-remote-load-rerun.json) |
| 최신 추가 burst | [phase1-remote-load-burst-audit.json](evidence/phase1-remote-load-burst-audit.json) |
| 비용 스냅샷 | [phase1-cost-snapshot.json](evidence/phase1-cost-snapshot.json) |
| NEW3 burst 실패 | [phase1-remote-load-burst-new3.json](evidence/phase1-remote-load-burst-new3.json) |
| 실제 브라우저 검증 | [phase1-browser-verification.md](evidence/phase1-browser-verification.md) |
| 원격 최종 대조 | [phase1-remote-final-reconciliation.json](evidence/phase1-remote-final-reconciliation.json) |
| 원격 수령 smoke | [phase1-remote-claim-smoke.json](evidence/phase1-remote-claim-smoke.json) |
| 원격 자원 보존 | [phase1-remote-preservation.json](evidence/phase1-remote-preservation.json) |
| 업로드 manifest | [phase1-upload-manifest.json](evidence/phase1-upload-manifest.json) |
| 코드 검토 | [Draft PR #2](https://github.com/CODEhenryKIL/gemini-dino-jump/pull/2) |

## 12. 후속 검증 및 운영 오픈 조건

성능 통과 판정에는 1~4번의 후속 확인이 필요하다. 5번은 3차 운영 오픈 전에 확정할 항목이며 1차 합성 테스트의 선행 조건은 아니다.

1. 확인된 Supavisor client connection 200 한도에 맞춰 서버리스 인스턴스별 연결 수·반납 정책을 개선한다. DB 서버 연결 수와 pooler client 연결 수는 별개로 측정한다.
2. 같은 보호 대상과 기준으로 필요한 원격 부하를 재실행한다.
3. 입장·게임 시작 목표와 게임 완료·추첨 목표를 모두 충족하고 serious stop이 발생하지 않는다.
4. 결과 원본을 `docs/evidence`에 보존하고 Draft PR 보고서를 갱신한다.
5. D03·D04·D05·D10·D12와 Notion·공식 링크의 Production 값을 확정한다.

현재 결론은 **운영 기반과 기능 구현·검증 수행, 성능 인수 실패, Production 미변경**이다.
