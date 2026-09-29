# 수령 개인정보 정리 절차

## 담당·기한

- 담당자: **행사 운영자(사용자 본인)** — 2026-09-29 사용자 확정.
- 문의: sea42471@naver.com.
- 지급 완료 후 **30일 이내 삭제**. 매일 확인할 수 있도록 도구는 지급 **29일 경과**부터 대상으로 잡는다. 30일 초과는 overdue_count로 구분한다.
- 미지급·부적격·미응답·최종 비수상자의 정보는 **전체 경품 지급 종료 후 30일 이내 삭제**한다(2026-09-29 사용자 확정). 도구는 운영자가 기록한 전체 지급 종료일 29일 경과부터 대상으로 잡는다.
- 자동 스케줄러는 없다. 운영자가 지급 내역을 확인하고 매일 기한을 관리한다. 코드 보완 과정에서 실제 개인정보 삭제는 실행하지 않았다.

## 삭제 범위와 보존

삭제 대상은 지정 행사에서 위 기한에 도달한 요청의 claim_contact와 claim_contact_draft다. 이름·연락처·학교·주소가 포함된 두 행을 제거한다. PAID지만 지급일이 누락된 건은 자동 계산하지 않고 수동 확인 대상으로 남긴다.

수령 요청 자체, 당첨·랭킹·재고·지급 상태, 기존 감사 기록은 보존한다. 삭제 후 지급 완료 요청의 연락처를 다시 열거나 수정하는 기능은 제공하지 않는다. 삭제 이력은 개인정보 원문 없이 남긴다.

백업·수동 CSV·별도 대학생 증빙 파일은 이 DB 도구가 지우지 않는다. 운영자는 같은 기한에 해당 사본의 보관·삭제도 확인하고, 오래된 백업을 복원할 때 삭제 이력을 재적용한다. 공유 문서·감사 사유에 개인정보를 복사하지 않는다.

## 접속 준비

도구: `scripts/claim_retention.py`.

- 기존 유지보수용 DB 자격증명을 비공개 환경 변수 RETENTION_DATABASE_URL로 제공한다. 명령 인자·Git·문서에 비밀번호를 넣지 않는다.
- 웹 서버용 dino_dev_app/dino_prod_app 계정은 사용할 수 없다. 삭제 권한을 새로 부여하지 않는다.
- 활성 claims:write 관리자의 UUID를 실행 주체로 기록한다.
- production은 승인된 Supabase 프로젝트·운영 스키마·guard·migration 버전·실경품 환경 여부를 확인하며 TLS 인증서를 검증한다.
- preview도 같은 프로젝트만 허용한다. test는 127.0.0.1:55433의 dino_phase1_audit_ 접두사 DB로 제한한다.
- 특정 행사 ID로 범위를 고정한다. 현재 guard가 새 행사를 가리켜도 같은 스키마 안의 이전 행사 개인정보를 정리할 수 있다.

## 1. 전체 경품 지급 종료 기록

개인별 지급 완료 건은 이 단계 없이도 자신의 지급일 기준으로 정리할 수 있다. 미지급 건의 기산일을 정할 때는 운영자가 전체 지급 내역을 확인한 뒤 아래 명령을 실행한다.

```sh
python scripts/claim_retention.py \
  --environment production \
  --campaign gemini_dino_campus_2026 \
  --admin-user '<관리자 UUID>' \
  --record-fulfillment-complete \
  --evidence-reference REF_FULFILLMENT_2026
```

- 행사와 수령 정보 접수 기한이 모두 지났고, 랭킹 경품이 있으면 최종 순위가 FINAL로 확정되어야 한다.
- 상품이 배정된 수령 건을 모두 PAID / INELIGIBLE / NO_RESPONSE로 처리한 뒤 기록한다. ON_HOLD·확인 대기·연락 완료만 된 건은 종료로 간주하지 않는다.
- 정보를 제출하지 않은 사람은 접수 기한 이후 관리자 화면에서 사유를 남겨 NO_RESPONSE로 마감할 수 있다. 자동 마감·자동 차순위 선정·재고 재배정은 하지 않는다.
- 완료 시점은 DB 현재 시각으로 기록한다. 날짜를 소급하거나 수정하는 옵션은 없다. 실제 전체 지급을 마치는 날 기록해야 30일 기한이 늦춰지지 않는다.
- 감사 기록 PRIZE_FULFILLMENT_COMPLETE에 담당자·기준일·참조를 남긴다. 같은 참조의 재실행은 기존 기록을 응답하고, 다른 참조로 덮어쓰지 않는다.
- 전체 지급 종료를 기록한 뒤에는 NO_RESPONSE 건을 PENDING_REVIEW로 다시 열 수 없다. 최종 종료 전에 미응답 처리 내역을 확인한다. 유지보수로 지급 상태를 바꾸면 미지급 삭제 대상의 조건을 다시 확인해야 한다.
- preview/test의 참조는 TEST_REF_로 시작한다. 실제 개인정보·증빙 본문은 참조값에 넣지 않는다.

## 2. 읽기 전용 계획 만들기

```sh
python scripts/claim_retention.py \
  --environment production \
  --campaign gemini_dino_campus_2026 \
  --admin-user '<관리자 UUID>' \
  --plan-output .local/privacy/retention-plan.json
```

계획 생성은 DB에 쓰지 않는다. 계획 파일은 0600 권한으로 새로 만들며 기존 파일을 덮어쓰지 않는다.

출력에서 다음을 확인한다.

- due_paid_count / due_nonpaid_count / due_count: 각 기준일 29일 이상 지난 지급자·미지급자·전체 정리 대상
- overdue_count: 해당 기준일 30일 이상 지난 지연 대상
- paid_not_due_count / nonpaid_not_due_count: 기준일이 있으나 정리 시점 전
- nonpaid_waiting_for_completion_count: 전체 지급 종료 기록이 없어 기다리는 미지급 건
- manual_issue_count: 지급 완료 상태지만 지급일 누락으로 별도 확인할 건
- nonpaid_blocked_count / fulfillment_state_error: 종료 기록 뒤 상태 불일치로 미지급 정리를 보류한 건과 원인. 개인별 기한에 도달한 지급 완료 건은 별도로 정리한다.
- sha256: 검토한 계획 식별값

파일에는 대상 요청 ID와 상태·시각만 들어가며 이름·연락처·주소는 없다. 요청 ID도 내부 자료이므로 공개하지 않는다.

## 3. 검토한 계획 적용하기

실제 삭제는 대상 행사·관리자·계획 해시를 다시 지정했을 때만 수행된다.

```sh
python scripts/claim_retention.py \
  --environment production \
  --campaign gemini_dino_campus_2026 \
  --admin-user '<관리자 UUID>' \
  --apply-plan .local/privacy/retention-plan.json \
  --confirm-plan-sha256 '<계획에 표시된 SHA-256>'
```

- 계획은 24시간 이내여야 한다. 오래된 계획은 새로 생성한다.
- DB·환경·관리자·기한을 재확인하고 해당 요청과 개인정보 행을 잠근다.
- 검토 후 상태·지급일·버전·임시 입력본 시각이 바뀌면 전체 작업을 취소한다. 새 계획으로 재검토한다.
- 미지급 정보는 전체 지급 종료 기록과 마감·최종 순위·미해결 지급 건도 다시 확인한다. 기준이 바뀌면 삭제하지 않고 중단한다.
- 삭제와 CLAIM_PII_RETENTION_DELETE / RETENTION_BATCH_COMPLETE 감사 기록은 한 트랜잭션이다. 기록 실패 시 삭제도 취소된다.
- 같은 계획 재실행은 결과를 재응답한다. 수동 복원 등으로 개인정보가 다시 생겼으면 성공으로 오인하지 않고 중단한다. 새 계획을 만들고 복원 원인을 확인한다.
- 웹앱의 임시 저장을 포함하여 이번 계획 밖의 정보는 삭제하지 않는다.

## 4. 완료 확인

도구의 삭제 건수·완료 시각·계획 해시와 DB 감사 기록을 대조한다. 새로운 읽기 전용 계획에서 남은 대상·지연 대상이 있는지 확인한다. 완료 기록에는 연락처 원문을 넣지 않는다.

개인별 지급일과 전체 지급 종료일을 구분해 기한을 관리한다. 도구와 문서가 준비됐다는 사실은 실제 삭제 완료를 뜻하지 않는다. 운영자가 대상 확인·실행·사본 정리·완료 기록을 남긴다.
