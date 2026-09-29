# 기존 테스트 전체 대응표

작성: 2026-09-29 · 소스 기준 `928d335` · 실행 결과가 아닌 검증 범위 색인.

**55개 파일, 461개 테스트 정의**를 추출했다: JavaScript 27개 파일/214개 정의, Python 28개 파일/247개 정의. 반복문·`subTest`로 여러 입력을 넣는 정의는 1개로 계산했으므로 테스트 실행기가 보고하는 실행 건수와 다를 수 있다. 템플릿 이름의 `${...}`도 원본 그대로 보존했다.

[화면 수동 테스트](manual-test-cases.md) · [서버 수동 테스트](manual-test-server.md) · [결과 양식](manual-test-results-template.md)

## 읽는 방법

- 파일별로 관련 수동 케이스를 연결했다. **파일 범위의 대응이지 각 자동 assertion과 수동 항목이 일대일이라는 뜻은 아니다.** 내부 상수·연결 정리·정확한 동시성은 개발자와 원본의 입력 변형을 함께 대조한다.
- 각 원본 검증 이름을 펼쳐 볼 수 있도록 아래에 모두 적었다. 자동 테스트가 다루는 과거 버전/숨겨진 helper도 삭제하지 않았다. 공개 UI에서 제거한 기능은 없는 버튼을 찾지 말고 격리된 API·개발자 도구 검증으로 확인한다.
- 수동 케이스 한 행에 여러 조건이 있으면 각 조건을 결과 양식의 하위 변형 칸에 기록한다. 자동 정의에 추가 경계값이 있으면 그 변형도 같은 ID 아래 별도로 남긴다.
- 코드가 바뀌면 새 테스트 파일·정의가 이 목록에 추가됐는지 확인한다. 이 목록 작성은 자동 테스트를 재실행하거나 수동으로 통과시킨 기록이 아니다.

## 파일별 대응

| 파일 | 정의 수 | 관련 수동 케이스 |
| --- | ---: | --- |
| [dino_only.test.cjs](../tests/dino_only.test.cjs) | 4 | HM-01, HM-03, HM-04, HM-07, GU-03 |
| [jump_button_touch_regression.test.cjs](../tests/jump_button_touch_regression.test.cjs) | 3 | GM-01, GM-02, NV-09 |
| [frontend_analytics_delivery.test.cjs](../tests/frontend_analytics_delivery.test.cjs) | 7 | AN-08, AN-09 |
| [frontend_phase1_contract.test.cjs](../tests/frontend_phase1_contract.test.cjs) | 19 | EN-07, EN-09, EN-10, IV-05, SH-13, TK-06, TK-07, SH-04, DR-03, DR-06, CL-03, AD-01, AD-07, NV-07, AN-08, AN-09 |
| [frontend_phase1_followup.test.cjs](../tests/frontend_phase1_followup.test.cjs) | 12 | AD-02, AD-03, AD-05, AD-06, AD-08, AD-09, CL-02, CL-09, CL-11, AN-05, AN-07, AN-10 |
| [frontend_phase2_admin_recovery.test.cjs](../tests/frontend_phase2_admin_recovery.test.cjs) | 8 | AD-11, AD-12, AD-13 |
| [frontend_phase2_benefit_visibility.test.cjs](../tests/frontend_phase2_benefit_visibility.test.cjs) | 3 | AN-03 |
| [frontend_phase2_claim_empty.test.cjs](../tests/frontend_phase2_claim_empty.test.cjs) | 3 | CL-01, IV-03 |
| [frontend_phase2_game_async.test.cjs](../tests/frontend_phase2_game_async.test.cjs) | 8 | TK-05, TK-06, TK-07, NV-02, NV-04 |
| [frontend_phase2_navigation_failures.test.cjs](../tests/frontend_phase2_navigation_failures.test.cjs) | 9 | CL-09, CL-12, RS-06, RS-08, DR-06, DR-15, NV-02 |
| [frontend_phase2_recovery.test.cjs](../tests/frontend_phase2_recovery.test.cjs) | 6 | TK-03, TK-04, TK-05, TK-06, GM-09, SV-014 |
| [frontend_phase2_share_async.test.cjs](../tests/frontend_phase2_share_async.test.cjs) | 5 | SH-10, BN-06, BN-09 |
| [frontend_phase2_shell.test.cjs](../tests/frontend_phase2_shell.test.cjs) | 21 | EN-02, EN-03, EN-04, EN-05, EN-06, EN-10, HM-02, HM-05, HM-08, TK-12, NV-01, NV-02, NV-03, NV-08, AN-01 |
| [frontend_phase2_top3.test.cjs](../tests/frontend_phase2_top3.test.cjs) | 22 | RS-02, RS-03, RS-04, RS-05, RS-06, RS-07, RS-08, RK-04, RK-05, RK-06, CL-05, CL-06, CL-08, SH-06, SH-10, NV-08 |
| [frontend_phase2_views.test.cjs](../tests/frontend_phase2_views.test.cjs) | 10 | HM-06, HM-07, HM-08, CL-01, CL-04, RS-03, RS-05, DR-05, NV-07, AN-04 |
| [frontend_phase3_draw.test.cjs](../tests/frontend_phase3_draw.test.cjs) | 10 | GM-03, GM-04, DR-03, DR-07, DR-08, DR-09, DR-10, DR-12, SH-05 |
| [frontend_referral_share.test.cjs](../tests/frontend_referral_share.test.cjs) | 20 | SH-01, SH-02, SH-04, SH-05, SH-06, SH-07, SH-08, SH-09, SH-10, SH-11, SH-12, CL-05 |
| [frontend_review_safety.test.cjs](../tests/frontend_review_safety.test.cjs) | 4 | RS-01, EN-10, SH-04, SH-08, BN-07, SV-024, SV-049 |
| [frontend_tracking_acceptance.test.cjs](../tests/frontend_tracking_acceptance.test.cjs) | 3 | AN-01, AN-04, AN-06 |
| [game_guide.test.cjs](../tests/game_guide.test.cjs) | 4 | GU-01, GU-02, GU-03, GU-04, GU-05, GU-06 |
| [game_rank_target.test.cjs](../tests/game_rank_target.test.cjs) | 4 | GM-10, GM-11 |
| [game_v2.test.cjs](../tests/game_v2.test.cjs) | 9 | GM-06, GM-07, GM-12, GM-14, NV-03, SV-013, SV-014 |
| [game_v21.test.cjs](../tests/game_v21.test.cjs) | 6 | GM-07, GM-09, SV-014 |
| [phase2_metrics.test.cjs](../tests/phase2_metrics.test.cjs) | 4 | AD-13, AN-04, AN-05, AN-10 |
| [scratch_card_lifecycle.test.cjs](../tests/scratch_card_lifecycle.test.cjs) | 4 | DR-04, DR-05, DR-06, NV-07 |
| [test_acceptance_boundaries.py](../tests/test_acceptance_boundaries.py) | 5 | SV-016, SV-017, SV-018, SV-021 |
| [test_acceptance_regressions.py](../tests/test_acceptance_regressions.py) | 6 | SV-008, SV-009, SV-010, SV-029, SV-032 |
| [test_backend_concurrency.py](../tests/test_backend_concurrency.py) | 6 | SV-011, SV-018, SV-021, SV-032 |
| [test_backend_config.py](../tests/test_backend_config.py) | 5 | SV-001, SV-002, SV-044 |
| [test_backend_kakao_config.py](../tests/test_backend_kakao_config.py) | 4 | SV-003 |
| [test_backend_kakao_webhook_security.py](../tests/test_backend_kakao_webhook_security.py) | 3 | SV-020 |
| [test_backend_phase1.py](../tests/test_backend_phase1.py) | 42 | SV-007–SV-010, SV-011–SV-013, SV-015–SV-021, SV-024–SV-026, SV-029, SV-032, SV-049 |
| [test_backend_phase2.py](../tests/test_backend_phase2.py) | 13 | SV-012, SV-014, SV-024–SV-027, SV-036–SV-038 |
| [test_backend_phase3.py](../tests/test_backend_phase3.py) | 8 | SV-019, SV-022, SV-029–SV-035 |
| [test_backend_security_regression.py](../tests/test_backend_security_regression.py) | 10 | SV-009, SV-013, SV-020, SV-024–SV-026, SV-039, SV-048, SV-049 |
| [test_claim_status_followup.py](../tests/test_claim_status_followup.py) | 12 | SV-036–SV-038, SV-041 |
| [test_cohort_guards.py](../tests/test_cohort_guards.py) | 8 | SV-044–SV-046 |
| [test_database_connections.py](../tests/test_database_connections.py) | 16 | SV-004 |
| [test_game_verifier_safety.py](../tests/test_game_verifier_safety.py) | 4 | SV-013 |
| [test_game_verifier_v2.py](../tests/test_game_verifier_v2.py) | 8 | SV-012–SV-014 |
| [test_game_verifier_v21.py](../tests/test_game_verifier_v21.py) | 5 | SV-014 |
| [test_load_guards.py](../tests/test_load_guards.py) | 22 | SV-045–SV-047 |
| [test_metrics.py](../tests/test_metrics.py) | 18 | SV-026–SV-028 |
| [test_metrics_acceptance.py](../tests/test_metrics_acceptance.py) | 4 | SV-024, SV-026, SV-027 |
| [test_migration_acceptance.py](../tests/test_migration_acceptance.py) | 5 | SV-035, SV-041 |
| [test_phase2_load.py](../tests/test_phase2_load.py) | 14 | SV-045–SV-047 |
| [test_phase2_metrics.py](../tests/test_phase2_metrics.py) | 4 | SV-026–SV-028 |
| [test_phase3_campaign_window.py](../tests/test_phase3_campaign_window.py) | 3 | SV-042 |
| [test_phase3_claim_payment.py](../tests/test_phase3_claim_payment.py) | 3 | SV-038–SV-040 |
| [test_phase3_pool_depletion.py](../tests/test_phase3_pool_depletion.py) | 1 | SV-033 |
| [test_phase3_preflight.py](../tests/test_phase3_preflight.py) | 10 | SV-043, SV-044 |
| [test_rate_limit_buckets.py](../tests/test_rate_limit_buckets.py) | 5 | SV-005 |
| [test_schema_guard.py](../tests/test_schema_guard.py) | 3 | SV-006, SV-041 |
| [ui_modal_lifecycle.test.cjs](../tests/ui_modal_lifecycle.test.cjs) | 4 | NV-05, NV-06, CL-07 |
| [vercel_analytics.test.cjs](../tests/vercel_analytics.test.cjs) | 2 | AN-09 |

## 전체 검증 정의

원본 링크는 각 파일의 코드를 연다. 표의 줄 번호는 위 기준 커밋 시점이며 이후 편집으로 달라질 수 있다.

### dino_only.test.cjs

관련 수동 케이스: HM-01, HM-03, HM-04, HM-07, GU-03

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-001 | home presents only Dino Jump and starts it after the guide | 46 |
| AT-002 | returning players see the tutorial on every new game | 61 |
| AT-003 | Dino Jump runtime has no Gate Runner navigation or port dependency | 71 |
| AT-004 | zero-ticket CTA opens invite, while unlimited starts a game and pause still blocks | 89 |

### frontend_analytics_delivery.test.cjs

관련 수동 케이스: AN-08, AN-09

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-005 | an anonymous event rejected during participant linking waits for the authenticated context and keeps its identity | 40 |
| AT-006 | a late partial rejection retries only the rejected item after participant initialization has already finished | 59 |
| AT-007 | a repeated participant rejection is reported once and cannot loop forever | 73 |
| AT-008 | permanent rejection diagnostics contain only allowed names and reason codes | 86 |
| AT-009 | unknown or invalid rejection metadata cannot trigger a retry or leak a response payload | 99 |
| AT-010 | network failures still retain the same events for a later bounded retry | 113 |
| AT-011 | partial rejection recovery respects the 40-event queue bound and reports an event it cannot retain | 127 |

### frontend_phase1_contract.test.cjs

관련 수동 케이스: EN-07, EN-09, EN-10, IV-05, SH-13, TK-06, TK-07, SH-04, DR-03, DR-06, CL-03, AD-01, AD-07, NV-07, AN-08, AN-09

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-012 | participant API uses HttpOnly cookie transport and never browser token storage | 40 |
| AT-013 | analytics batch transport retries a lost request with the exact generated idempotency key | 55 |
| AT-014 | rebatching the same first event gets a fresh request key and relies on event IDs for deduplication | 71 |
| AT-015 | lost finish retries retain an exact key and a PII-free payload | 93 |
| AT-016 | verified finish clears only its pending reservation and accepts authoritative ticket state | 106 |
| AT-017 | invite qualification requires both active time and interaction and GET cannot reward | 139 |
| AT-018 | draw is participant-scoped, resumes from server, and scratch listeners are cleaned up | 155 |
| AT-019 | claim UI uses the server claim_type field for DRAW and RANKING records | 166 |
| AT-020 | admin uses real Supabase Auth and optimistic manual claim transitions | 172 |
| AT-021 | client event envelope is allowlisted and excludes private arbitrary payloads | 193 |
| AT-022 | blocked web storage cannot crash participant or game bootstrap | 212 |
| AT-023 | a consumed ticket does not block access to an existing game or fault recovery | 221 |
| AT-024 | fault recovery persists only non-PII evidence and reconciles rejected checkpoints | 228 |
| AT-025 | scratch completion keeps a stable retry key and does not claim completion after failure | 236 |
| AT-026 | share attribution uses an opaque approved parameter and records outcomes separately | 247 |
| AT-027 | admin isolates contact operations and renders metric definitions and full breakdowns | 258 |
| AT-028 | hidden views leave the accessibility tree and Gemini exposure requires visibility | 290 |
| AT-029 | submitted TOP3 state wins over a stale requested result when result screen rerenders | 299 |
| AT-030 | public metadata uses the deployment site name while retaining Dino Jump | 334 |

### frontend_phase1_followup.test.cjs

관련 수동 케이스: AD-02, AD-03, AD-05, AD-06, AD-08, AD-09, CL-02, CL-09, CL-11, AN-05, AN-07, AN-10

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-031 | unsubmitted winner sees information waiting and the administrator cannot process it | 45 |
| AT-032 | submitted claims remove the entry form and preserve ranking and read-only restrictions | 63 |
| AT-033 | legacy claim without real contact cannot be processed even if its status progressed | 80 |
| AT-034 | administrator must confirm eligibility, delivery and evidence before recording payment | 94 |
| AT-035 | paid evidence cannot be unchecked and verification remains disabled for read-only administrators | 133 |
| AT-036 | claim forms are not offered for finalized claims with missing legacy contact information | 148 |
| AT-037 | legacy nonterminal claims can submit missing contact without showing an incorrect new status | 156 |
| AT-038 | dashboard renders invitation, Gemini and unknown shares from separate purpose totals | 171 |
| AT-039 | dashboard keeps open observations out of final nonclick counts and handles no closed cohort | 196 |
| AT-040 | dashboard exposes draw outcomes and credits and stays safe for a legacy response | 210 |
| AT-041 | claims load ordered draw history and links an actual prize claim to its round | 227 |
| AT-042 | claims history does not expose an unrevealed result | 244 |

### frontend_phase2_admin_recovery.test.cjs

관련 수동 케이스: AD-11, AD-12, AD-13

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-043 | a metrics failure keeps the authenticated operations available and retry clears the notice | 127 |
| AT-044 | a 401 response expires the admin session, removes private data, and returns to login | 166 |
| AT-045 | a late successful private response cannot repopulate the DOM after expiry | 182 |
| AT-046 | a forbidden admin session is recovered as an expired login | 218 |
| AT-047 | a temporary session outage keeps the token and offers retry instead of treating it as expiry | 232 |
| AT-048 | a successful filtered metrics query clears only the recovered section failure | 245 |
| AT-049 | filter retry hides the notice when metrics was the only failed section | 267 |
| AT-050 | an older metrics response cannot overwrite the latest filter result or restore its old error | 283 |

### frontend_phase2_benefit_visibility.test.cjs

관련 수동 케이스: AN-03

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-051 | foreground return rechecks hidden intersections once and cleanup rejects stale callbacks | 30 |
| AT-052 | missing IntersectionObserver does not fabricate measured exposure | 96 |
| AT-053 | foreground return discards queued positive snapshots and waits for a fresh 50 percent measurement | 117 |

### frontend_phase2_claim_empty.test.cjs

관련 수동 케이스: CL-01, IV-03

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-054 | empty claims send a locked participant home to finish the first game without draw tracking | 38 |
| AT-055 | empty claims distinguish available and drawn pouch actions | 48 |
| AT-056 | empty claims recheck the latest draw state at click time | 62 |

### frontend_phase2_game_async.test.cjs

관련 수동 케이스: TK-05, TK-06, TK-07, NV-02, NV-04

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-057 | current game completion clears its durable pending finish and navigates | 69 |
| AT-058 | late game completion cannot clear or navigate over a newer session | 80 |
| AT-059 | late pending-result recovery keeps durable data for the next current render | 99 |
| AT-060 | late pending-result failure cannot delete durable recovery data | 118 |
| AT-061 | checkpoint completions cannot regress storage or resurrect an old session | 136 |
| AT-062 | late fault completion preserves a newer session marker and emits no old analytics | 164 |
| AT-063 | current fault recovery reconciles a 409 checkpoint before reporting the fault | 178 |
| AT-064 | late abandon response cannot start a new game after leaving the screen | 200 |

### frontend_phase2_navigation_failures.test.cjs

관련 수동 케이스: CL-09, CL-12, RS-06, RS-08, DR-06, DR-15, NV-02

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-065 | returning to claims shows contact and payment changes without collecting information again | 59 |
| AT-066 | a claims refresh failure preserves the cards and can be retried in place | 98 |
| AT-067 | an older claims response cannot overwrite a newer refresh in the same screen | 119 |
| AT-068 | ${scenario.name} load failure cannot replace a newer screen | 136 |
| AT-069 | TOP3 submission preserves version provenance and does not navigate from a stale result | 160 |
| AT-070 | claim submission completion does not navigate away from a newer screen | 207 |
| AT-071 | an old pouch request cannot pass after leaving and re-entering draw | 257 |
| AT-072 | a newly committed draw updates current state before rendering scratch | 291 |
| AT-073 | an old scratch save cannot complete after draw is re-entered | 315 |

### frontend_phase2_recovery.test.cjs

관련 수동 케이스: TK-03, TK-04, TK-05, TK-06, GM-09, SV-014

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-074 | ${version} resume replay restores deterministic score, items, held heart, and revival penalties | 40 |
| AT-075 | ${status} is automatically invalidated and refunded before a new game | 91 |
| AT-076 | a concurrently finished game shows its result instead of being restarted | 106 |
| AT-077 | failed abandon retains pending session and offers retry without spending another ticket | 117 |
| AT-078 | cleanup persists a PII-free active snapshot for the same session | 127 |
| AT-079 | new game engine shows ten stages and caps the final speed | 137 |

### frontend_phase2_share_async.test.cjs

관련 수동 케이스: SH-10, BN-06, BN-09

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-080 | invite deferred copy keeps its originating context, ignores duplicates, and cannot toast into a rerender | 148 |
| AT-081 | invite deferred native cancellation is recorded on the originating attempt without touching the new render | 177 |
| AT-082 | benefit deferred copy failure keeps its context and cannot rewrite a replacement screen | 202 |
| AT-083 | benefit deferred native success invokes once and keeps share_sheet_closed on the original view | 227 |
| AT-084 | benefit bottom Kakao share promotes the game with the prize image and game destination | 252 |

### frontend_phase2_shell.test.cjs

관련 수동 케이스: EN-02, EN-03, EN-04, EN-05, EN-06, EN-10, HM-02, HM-05, HM-08, TK-12, NV-01, NV-02, NV-03, NV-08, AN-01

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-085 | entry parsing accepts record_share once and removes invite and attribution values from browser history | 73 |
| AT-086 | entry parsing preserves draw_retry attribution without keeping it in browser history | 83 |
| AT-087 | initial brand flow has the required copy and a static reduced-motion presentation | 91 |
| AT-088 | five-second intro completion stays separate from data readiness, including reduced motion | 105 |
| AT-089 | router writes public screen-only history and popstate renders without creating a duplicate entry | 128 |
| AT-090 | a synchronous result redirect keeps the destination URL and render promise | 140 |
| AT-091 | navigation exposes the current page and preserves modified link clicks | 155 |
| AT-092 | initial loading_ready and splash dismissal wait for the actual initial view render | 183 |
| AT-093 | retry keeps focus on the loading status, then the page or the retry button | 208 |
| AT-094 | render promises are race guarded and an older route cannot become current after a newer route | 235 |
| AT-095 | overlapping resume refreshes share one server read | 256 |
| AT-096 | a server refresh updates the visible view without navigation or replacing its controls | 272 |
| AT-097 | a newly reached cooldown is announced once on a safe screen and never interrupts a game or form | 291 |
| AT-098 | loading milestones are independently deduplicated and remain attributed to loading | 319 |
| AT-099 | view exposure, draw CTA, and scratch accessibility events survive client filtering and match the server contract | 345 |
| AT-100 | game completion forwards verifier version, terminal reason, and item summary | 377 |
| AT-101 | leaving during countdown resolves the pending start and clears timers | 416 |
| AT-102 | header logo uses home navigation and keeps native modified-link behavior | 435 |
| AT-103 | server unlimited flag controls header and disappears when test mode ends | 448 |
| AT-104 | home refresh stays home with saved draw state ${JSON.stringify(draw)} | 462 |
| AT-105 | refresh preserves an explicitly opened ${view} screen | 475 |

### frontend_phase2_top3.test.cjs

관련 수동 케이스: RS-02, RS-03, RS-04, RS-05, RS-06, RS-07, RS-08, RK-04, RK-05, RK-06, CL-05, CL-06, CL-08, SH-06, SH-10, NV-08

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-106 | TOP3 request renderer replaces stale content and represents requested, submitted, and hidden states | 140 |
| AT-107 | leaving TOP3 hides a historical contact request and reentry restores it | 161 |
| AT-108 | ranking shows prizes without old TOP3 information request cards | 179 |
| AT-109 | ranking failure retries in place once and shows recovered results | 196 |
| AT-110 | ranking ignores reverse-order responses and a retry that finishes after leaving | 233 |
| AT-111 | result keeps the completed game but hides an old TOP3 request while ranking retries | 268 |
| AT-112 | result ignores reverse-order supplemental responses and completion after leaving | 312 |
| AT-113 | result passive updates replace TOP3 state and ignore stale render tokens | 345 |
| AT-114 | TOP3 direct form starts blank, accepts ordinary values, broadcasts and blocks double submission | 378 |
| AT-115 | TOP3 inline failure preserves entered values and allows retry | 398 |
| AT-116 | passive TOP3 refresh preserves in-progress contact values | 414 |
| AT-117 | result sharing opens the prepared share action in place above the pouch | 427 |
| AT-118 | ranking claims explain the final cutoff and use record sharing | 445 |
| AT-119 | draw claims retain prize-result copy and prize sharing | 462 |
| AT-120 | ranking uses score-equivalent seconds consistently despite longer elapsed play | 479 |
| AT-121 | claim draft resumes, cancelled share stays pending, and only a confirmed Kakao intent finalizes | 502 |
| AT-122 | claim save click launches Kakao immediately but waits for saved data and webhook confirmation | 554 |
| AT-123 | a late webhook check cannot submit a claim after the share step is closed | 583 |
| AT-124 | ranking bottom share button uses retry copy and opens sharing in place | 610 |
| AT-125 | replay visibility respects 100-point boundary, balances, unlimited mode and campaign pause | 625 |
| AT-126 | TOP3 celebration runs once per result and respects reduced motion and rank | 641 |
| AT-127 | replay opens the game guide and ignores stale clicks | 654 |

### frontend_phase2_views.test.cjs

관련 수동 케이스: HM-06, HM-07, HM-08, CL-01, CL-04, RS-03, RS-05, DR-05, NV-07, AN-04

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-128 | home enables a newly earned ticket and uses the latest pending game after a passive refresh | 32 |
| AT-129 | home distinguishes expired cooldown from current waiting and explains an ended campaign accurately | 62 |
| AT-130 | home restores a draw route without requiring another ticket or another game | 77 |
| AT-131 | result and empty claims draw buttons track their own source before entering the draw screen | 108 |
| AT-132 | prize claim preserves the form and rejects an empty school before sending the request | 133 |
| AT-133 | TOP3 gap copy handles server states without promising a prize | 173 |
| AT-134 | record sharing uses the prepared public share and preserves authoritative ticket totals | 183 |
| AT-135 | restored scratched draw reveals the same server result without another draw or completion request | 254 |
| AT-136 | scratch result enters the accessibility tree only when revealed and canvas leaves keyboard order | 287 |
| AT-137 | guide card exposure and outbound click use distinct events and stop after cleanup | 342 |

### frontend_phase3_draw.test.cjs

관련 수동 케이스: GM-03, GM-04, DR-03, DR-07, DR-08, DR-09, DR-10, DR-12, SH-05

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-138 | Gemini benefit result prepares draw_retry and confirmed webhook exposes a direct next action | 48 |
| AT-139 | actual prize result prepares an unrewarded two-line prize boast and never opens another draw | 65 |
| AT-140 | the tenth benefit result ends repeat draws without preparing a new share intent | 76 |
| AT-141 | jump callout suppression stays scoped to the jump button and preserves press/release handlers | 85 |
| AT-142 | an AVAILABLE credit does not hide its latest unrevealed result | 98 |
| AT-143 | a lost draw response keeps one durable key and reconciles before manual retry | 115 |
| AT-144 | draw API carries an explicit reusable idempotency key and expected round guard | 162 |
| AT-145 | an existing draw credit renders a direct next draw action without preparing another share | 170 |
| AT-146 | a passive state refresh replaces the share action with a direct draw action without reload | 181 |
| AT-147 | an unrevealed benefit waits for scratch persistence before exposing the next draw action | 200 |

### frontend_referral_share.test.cjs

관련 수동 케이스: SH-01, SH-02, SH-04, SH-05, SH-06, SH-07, SH-08, SH-09, SH-10, SH-11, SH-12, CL-05

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-148 | configured Kakao share initializes once and opens sendDefault with an attributed invite URL | 62 |
| AT-149 | unconfigured Kakao opens native share directly and blocks duplicate clicks while pending | 94 |
| AT-150 | native fallback describes DRAW and NONE purposes without claiming a game ticket | 112 |
| AT-151 | Kakao invocation failure falls through to native share without claiming message delivery | 123 |
| AT-152 | no sharing API copies the attributed invite URL without navigating away | 143 |
| AT-153 | copy fallback describes DRAW and NONE purposes without claiming a game ticket | 158 |
| AT-154 | ranking share copy includes participant count when the server provides it | 170 |
| AT-155 | general and non-winning prize shares never imply that the participant won | 180 |
| AT-156 | winning prize share names the prize and always uses the requested Samtanbimi line | 187 |
| AT-157 | general share preserves its distinct no-reward attribution in analytics and URL | 194 |
| AT-158 | draw retry uses general promotion copy but keeps its distinct reward purpose | 203 |
| AT-159 | fresh SDK exposes Share only after init and still prepares Kakao sharing | 223 |
| AT-160 | image preparation failure preserves native sharing and a later preparation retries | 237 |
| AT-161 | native sharing never requests or grants an invitation ticket | 250 |
| AT-162 | Kakao launch sends only server-issued callback args and remains pending until webhook | 259 |
| AT-163 | a rejected Kakao self-share never awards a ticket | 277 |
| AT-164 | unconfigured webhook never opens an untracked Kakao invitation | 286 |
| AT-165 | claim share is bound before click and polling belongs to the claim modal | 294 |
| AT-166 | claim-bound ranking record share trusts intent NONE and never promises a game ticket | 306 |
| AT-167 | claimId falls back to NONE when an older intent omits reward_type | 315 |

### frontend_review_safety.test.cjs

관련 수동 케이스: RS-01, EN-10, SH-04, SH-08, BN-07, SV-024, SV-049

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-168 | editing a nickname preserves the participant leaderboard privacy setting | 19 |
| AT-169 | unsupported native sharing falls back to copy without fabricating a native attempt | 108 |
| AT-170 | copy failure and native cancellation record the actual attempted method and outcome | 121 |
| AT-171 | Vercel invite routes require the same 12 to 64 character code as the app and server | 138 |

### frontend_tracking_acceptance.test.cjs

관련 수동 케이스: AN-01, AN-04, AN-06

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-172 | game session creation carries the exact observation and visit context | 10 |
| AT-173 | loading ready remains attached to the loading view after the first screen renders | 34 |
| AT-174 | Gemini benefit copy and native share record observable outcomes only | 75 |

### game_guide.test.cjs

관련 수동 케이스: GU-01, GU-02, GU-03, GU-04, GU-05, GU-06

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-175 | guide uses concise touch instructions, previous navigation, and a top X close | 80 |
| AT-176 | skip starts the game without suppressing future tutorials | 99 |
| AT-177 | final slide shows rewards and safely renders live ranking data | 109 |
| AT-178 | ranking failure offers retry, and closing during a pending request is safe | 125 |

### game_rank_target.test.cjs

관련 수동 케이스: GM-10, GM-11

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-179 | current run advances bronze to silver to gold at tied thresholds and reverses after a penalty | 14 |
| AT-180 | empty or sparse ranking has no invented target score | 21 |
| AT-181 | ranking loads once without blocking game and uses the score at response time | 26 |
| AT-182 | late, failed or different-version rankings cannot update a new game HUD | 36 |

### game_v2.test.cjs

관련 수동 케이스: GM-06, GM-07, GM-12, GM-14, NV-03, SV-013, SV-014

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-183 | shared v2 constants match the browser simulation contract | 20 |
| AT-184 | seeded live items keep deterministic clearance from present and future obstacles | 51 |
| AT-185 | seeded item schedules use the draft 3s/2-4s and 20s/25-35s windows | 69 |
| AT-186 | collecting another heart while full stays at one and gives no bonus score | 77 |
| AT-187 | revive consumes the heart and collision resumes exactly at the 90 tick boundary | 92 |
| AT-188 | time limit is an explicit successful terminal reason | 114 |
| AT-189 | engine exposes v2 item and repeat-revive callbacks without a revive game-over | 123 |
| AT-190 | engine starts and advances the real v2 simulation, then removes its resize listener | 132 |
| AT-191 | item art stays inside the hitbox and falls back when an image is unavailable | 160 |

### game_v21.test.cjs

관련 수동 케이스: GM-07, GM-09, SV-014

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-192 | current and frozen v2.1 constants exactly match the exported browser contract | 60 |
| AT-193 | v2.1 stages 8 through 10 apply the specified speed ramps and obstacle gaps | 69 |
| AT-194 | v2.1 collision revives deduct 100 points each and report the cumulative penalty | 86 |
| AT-195 | v2.1 score never falls below zero after repeated revives | 101 |
| AT-196 | the frozen v2.0 contract and default replay remain penalty-free | 109 |
| AT-197 | simulateV2 accepts v2.1 as its optional fourth version argument | 134 |

### phase2_metrics.test.cjs

관련 수동 케이스: AD-13, AN-04, AN-05, AN-10

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-198 | metrics scope leaderboard and histogram to the active game version | 10 |
| AT-199 | gameplay totals come from trusted stored game summaries | 18 |
| AT-200 | loading milestones content CTR and all share purposes stay distinct | 26 |
| AT-201 | admin labels observed actions without claiming enrollment | 45 |

### scratch_card_lifecycle.test.cjs

관련 수동 케이스: DR-04, DR-05, DR-06, NV-07

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-202 | instant reveal starts a fresh scratch once before exposing the result | 49 |
| AT-203 | keyboard and pointer starts are not counted twice by instant reveal | 58 |
| AT-204 | restoring an already revealed result does not report a new scratch or celebrate again | 70 |
| AT-205 | leaving the screen cancels a queued reveal and removes input listeners | 77 |

### test_acceptance_boundaries.py

관련 수동 케이스: SV-016, SV-017, SV-018, SV-021

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-206 | test_qualified_visit_is_tracking_only_and_pair_dedups_after_expiry | 307 |
| AT-207 | test_admin_fault_approve_and_deny_require_current_version | 352 |
| AT-208 | test_client_and_server_faults_stay_pending_until_eventual_admin_refund | 384 |
| AT-209 | test_finished_response_replay_is_stable_and_has_no_duplicate_effects | 406 |
| AT-210 | test_invitation_fault_refund_preserves_cooldown_and_grant_history | 445 |

### test_acceptance_regressions.py

관련 수동 케이스: SV-008, SV-009, SV-010, SV-029, SV-032

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-211 | test_revoked_participant_cannot_replay_cached_mutation_response | 145 |
| AT-212 | test_admin_permission_removal_blocks_cached_claim_replay | 183 |
| AT-213 | test_denied_fault_remains_not_due_on_repeated_fault_request | 227 |
| AT-214 | test_concurrent_same_participant_draws_return_one_fixed_result | 267 |
| AT-215 | test_game_start_event_uses_only_owned_observation_attribution | 319 |
| AT-216 | test_entry_codes_and_new_tracking_catalogue_are_bounded | 382 |

### test_backend_concurrency.py

관련 수동 케이스: SV-011, SV-018, SV-021, SV-032

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-217 | test_one_hundred_concurrent_valid_invites_are_tracking_only | 170 |
| AT-218 | test_same_visitor_can_qualify_two_different_inviters_concurrently | 212 |
| AT-219 | test_visits_started_while_full_remain_tracking_only | 238 |
| AT-220 | test_last_inventory_concurrent_draw_allocates_once_and_lock_is_not_fake_no_prize | 326 |
| AT-221 | test_parallel_same_idempotency_key_consumes_one_ticket_once | 388 |
| AT-222 | test_concurrent_grant_and_refund_reservation_never_exceeds_cap | 421 |

### test_backend_config.py

관련 수동 케이스: SV-001, SV-002, SV-044

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-223 | test_cookie_period_is_bounded_and_public_config_safe | 11 |
| AT-224 | test_legacy_service_role_key_and_secret_key_are_rejected | 16 |
| AT-225 | test_benefit_url_requires_exact_allowlisted_https_destination | 21 |
| AT-226 | test_preview_allows_exact_friendly_and_immutable_vercel_origins_without_wildcard | 25 |
| AT-227 | test_preview_unlimited_flag_is_explicit_and_private | 32 |

### test_backend_kakao_config.py

관련 수동 케이스: SV-003

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-228 | test_optional_public_javascript_key | 11 |
| AT-229 | test_webhook_is_publicly_enabled_only_with_both_keys_and_secrets_stay_private | 19 |
| AT-230 | test_rejects_non_javascript_key_shapes | 25 |
| AT-231 | test_rejects_invalid_private_webhook_configuration | 30 |

### test_backend_kakao_webhook_security.py

관련 수동 케이스: SV-020

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-232 | test_exact_headers_are_accepted | 14 |
| AT-233 | test_missing_wrong_and_non_ascii_authorization_fail_closed | 17 |
| AT-234 | test_absent_server_secret_disables_webhook | 23 |

### test_backend_phase1.py

관련 수동 케이스: SV-007–SV-010, SV-011–SV-013, SV-015–SV-021, SV-024–SV-026, SV-029, SV-032, SV-049

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-235 | test_anonymous_replay_grants_exactly_one_initial_ticket | 62 |
| AT-236 | test_verified_score_at_or_below_100_refunds_initial_ticket_exactly_once | 76 |
| AT-237 | test_verified_score_above_100_consumes_ticket | 89 |
| AT-238 | test_low_score_invitation_refund_preserves_cap_and_cooldown | 99 |
| AT-239 | test_low_score_unlimited_session_does_not_mint_ticket | 113 |
| AT-240 | test_rejected_low_score_does_not_refund_ticket | 124 |
| AT-241 | test_abandon_unfinished_initial_ticket_refunds_once | 132 |
| AT-242 | test_concurrent_abandon_refunds_only_once | 144 |
| AT-243 | test_abandon_finished_preserves_result_and_does_not_refund | 155 |
| AT-244 | test_abandon_unlimited_session_does_not_mint_ticket | 163 |
| AT-245 | test_abandon_fault_reported_invitation_restores_balance_without_review | 173 |
| AT-246 | test_expired_active_session_can_be_abandoned_and_refunded | 187 |
| AT-247 | test_each_confirmed_friend_share_grants_until_balance_cap | 199 |
| AT-248 | test_legacy_share_reward_is_disabled_and_memo_chat_never_grants | 209 |
| AT-249 | test_share_intent_proof_is_owned_unforgeable_and_resource_id_is_single_use | 216 |
| AT-250 | test_claim_submit_requires_confirmed_owned_claim_bound_share | 226 |
| AT-251 | test_concurrent_webhooks_grant_at_most_three | 238 |
| AT-252 | test_invalid_cookie_is_not_replaced | 249 |
| AT-253 | test_old_top3_request_requires_current_rank_before_collection | 253 |
| AT-254 | test_reset_cookie_recovers_with_fresh_bootstrap_only | 280 |
| AT-255 | test_fresh_bootstrap_does_not_replace_blocked_or_expired_account | 293 |
| AT-256 | test_all_participants_can_replay_without_ticket_or_ledger_changes | 302 |
| AT-257 | test_preview_unlimited_applies_to_multiple_unlisted_participants_only_in_test_environments | 317 |
| AT-258 | test_disabled_preview_cannot_spoof_unlimited_play_in_request_body | 330 |
| AT-259 | test_free_session_fault_review_does_not_mint_ticket_or_refund_ledger | 338 |
| AT-260 | test_disabling_unlimited_keeps_reserved_session_but_blocks_next_free_session | 353 |
| AT-261 | test_valid_cookie_links_second_tab_only_with_matching_bootstrap_proof | 365 |
| AT-262 | test_qualified_visits_are_tracking_only_and_never_grant_tickets | 374 |
| AT-263 | test_same_visitor_rewards_two_inviters_but_each_pair_only_once | 386 |
| AT-264 | test_invalid_and_self_invites_return_explicit_rejections_and_share_attribution | 400 |
| AT-265 | test_one_hundred_concurrent_visits_never_grant_tickets | 411 |
| AT-266 | test_visit_issue_ignores_ticket_cap_and_cooldown_because_it_is_analytics_only | 423 |
| AT-267 | test_fault_refunds_original_ticket_once | 428 |
| AT-268 | test_second_network_fault_in_24h_remains_pending_for_review | 437 |
| AT-269 | test_expired_reserved_refunds_but_expired_active_requires_review | 447 |
| AT-270 | test_one_draw_per_campaign_participant | 457 |
| AT-271 | test_other_participant_cannot_read_game_session | 472 |
| AT-272 | test_top3_contact_persists_after_rank_drop_and_snapshot_never_finalizes_winner | 478 |
| AT-273 | test_admin_can_block_participant_and_revoke_cookie_session | 501 |
| AT-274 | test_last_inventory_item_is_never_allocated_twice | 508 |
| AT-275 | test_analytics_rejects_pii_urls_stale_time_and_foreign_session | 528 |
| AT-276 | test_app_role_cannot_change_guard_membership_or_append_only_ledger | 548 |

### test_backend_phase2.py

관련 수동 케이스: SV-012, SV-014, SV-024–SV-027, SV-036–SV-038

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-277 | test_verified_summary_versioned_rank_and_draw_are_atomic | 64 |
| AT-278 | test_v21_finish_uses_penalized_score_and_separate_leaderboard | 81 |
| AT-279 | test_expired_active_game_cannot_submit_or_rank | 122 |
| AT-280 | test_submitted_top3_contact_survives_rank_drop_and_verified_reentry | 133 |
| AT-281 | test_top3_contact_rejects_missing_consent_invalid_phone_controls_and_oversize_values | 196 |
| AT-282 | test_dense_rank_ties_private_name_and_gap_use_same_rules | 215 |
| AT-283 | test_old_top3_request_provenance_preserved_and_upgraded_without_reset | 252 |
| AT-284 | test_legacy_preview_conflict_still_records_its_contact_version | 283 |
| AT-285 | test_share_preview_is_read_only_and_escapes_public_text | 291 |
| AT-286 | test_new_events_accept_safe_dimensions_and_reject_personal_text | 310 |
| AT-287 | test_event_batch_rejections_distinguish_retryable_participant_linking | 330 |
| AT-288 | test_share_kinds_do_not_bypass_tracking_pair_deduplication | 407 |
| AT-289 | test_each_share_kind_tracks_a_distinct_visitor_without_reward | 420 |

### test_backend_phase3.py

관련 수동 케이스: SV-019, SV-022, SV-029–SV-035

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-290 | test_reward_purpose_is_server_fixed_and_draw_credit_is_separate | 66 |
| AT-291 | test_actual_prize_is_terminal_and_late_draw_share_is_not_replayed | 90 |
| AT-292 | test_first_draw_plus_nine_verified_shares_caps_at_ten | 123 |
| AT-293 | test_concurrent_last_credit_webhooks_and_draw_requests_stop_at_ten | 145 |
| AT-294 | test_one_pool_slot_is_allocated_once_under_concurrency | 197 |
| AT-295 | test_expected_round_replays_same_result_without_spending_next_credit | 220 |
| AT-296 | test_rolling_old_app_draw_is_reconciled_as_consumed_first_credit | 246 |
| AT-297 | test_marked_finite_pool_never_falls_back_to_legacy_probability | 274 |

### test_backend_security_regression.py

관련 수동 케이스: SV-009, SV-013, SV-020, SV-024–SV-026, SV-039, SV-048, SV-049

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-298 | test_no_collision_cannot_finish_rank_or_unlock_draw | 178 |
| AT-299 | test_finish_rejects_coerced_json_numbers_before_state_changes | 198 |
| AT-300 | test_nickname_edit_preserves_privacy_and_explicit_changes_still_work | 216 |
| AT-301 | test_invite_redirect_keeps_only_valid_attribution | 234 |
| AT-302 | test_vercel_function_destination_serves_share_card_without_cookie | 256 |
| AT-303 | test_zero_tick_submission_cannot_finish_or_unlock_draw | 266 |
| AT-304 | test_verifier_rejection_is_persisted_after_error_response | 288 |
| AT-305 | test_paid_claim_is_terminal_and_assignee_must_be_active_admin | 319 |
| AT-306 | test_known_observation_ids_cannot_recover_existing_identity | 376 |
| AT-307 | test_analytics_dimensions_reject_pii_and_preserve_frontend_catalogue | 416 |

### test_claim_status_followup.py

관련 수동 케이스: SV-036–SV-038, SV-041

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-308 | test_migration_backfills_only_unsubmitted_information_received_claims | 209 |
| AT-309 | test_claim_draft_resumes_without_creating_final_contact | 341 |
| AT-310 | test_claim_draft_is_private_to_claim_owner | 372 |
| AT-311 | test_submit_requires_saved_draft_and_accepted_share_result | 388 |
| AT-312 | test_accepted_share_finalizes_once_and_repeat_is_idempotent | 410 |
| AT-313 | test_shipping_draft_requires_address_and_closed_claim_rejects_new_data | 439 |
| AT-314 | test_new_claim_waits_for_information_and_blocks_every_admin_patch | 461 |
| AT-315 | test_submission_is_concurrent_safe_and_enables_review | 499 |
| AT-316 | test_new_submission_requires_school_without_partial_mutation_and_replay_stays_idempotent | 526 |
| AT-317 | test_late_submission_never_rolls_back_progressed_or_terminal_status | 580 |
| AT-318 | test_ranking_submission_sets_information_received_without_state_regression | 621 |
| AT-319 | test_missing_contact_nonterminal_states_accept_information_then_continue | 654 |

### test_cohort_guards.py

관련 수동 케이스: SV-044–SV-046

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-320 | test_cli_does_not_accept_plaintext_dsn_or_pepper_arguments | 71 |
| AT-321 | test_remote_and_local_target_guards_are_distinct_and_fail_closed | 78 |
| AT-322 | test_manifest_is_private_exact_unique_and_load_runner_compatible | 95 |
| AT-323 | test_existing_prepared_manifest_recovers_without_rotating_identities | 120 |
| AT-324 | test_private_secret_file_rejects_group_or_world_permissions | 137 |
| AT-325 | test_remote_dsn_requires_exact_scoped_pooler_role | 147 |
| AT-326 | test_destructive_postgres_test_dsn_requires_local_dedicated_owner_database | 161 |
| AT-327 | test_real_postgres_resume_is_idempotent_and_does_not_reset_balance | 211 |

### test_database_connections.py

관련 수동 케이스: SV-004

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-328 | test_sequential_connections_close_at_quiescence_and_reopen_tls | 29 |
| AT-329 | test_completed_concurrent_wave_leaves_no_idle_connection_without_checkout | 38 |
| AT-330 | test_waiting_borrower_reuses_returned_connection_during_overlap | 64 |
| AT-331 | test_failed_semaphore_acquire_drains_idle_and_borrower_count | 103 |
| AT-332 | test_failure_is_not_replayed_and_discards_connection | 112 |
| AT-333 | test_open_transaction_is_never_shared_with_next_request | 122 |
| AT-334 | test_different_database_or_environment_never_reuses_connection | 129 |
| AT-335 | test_stale_socket_is_checked_before_business_code | 136 |
| AT-336 | test_expired_connection_is_closed | 145 |
| AT-337 | test_concurrent_requests_have_exclusive_connections_and_bounded_count | 152 |
| AT-338 | test_failed_connect_releases_capacity_for_later_requests | 183 |
| AT-339 | test_emaxconn_admission_retries_twice_then_yields_business_body_once | 191 |
| AT-340 | test_emaxconn_exhausts_four_attempts_without_yield_and_releases_capacity | 206 |
| AT-341 | test_non_emaxconn_connection_errors_are_not_retried | 219 |
| AT-342 | test_business_body_emaxconn_error_is_never_replayed | 229 |
| AT-343 | test_emaxconn_retry_start_deadline_stops_late_attempts | 240 |

### test_game_verifier_safety.py

관련 수동 케이스: SV-013

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-344 | test_absent_collision_cannot_be_replaced_by_the_submitted_finish | 11 |
| AT-345 | test_real_collision_still_verifies | 17 |
| AT-346 | test_numeric_fields_require_integers_without_coercion | 24 |
| AT-347 | test_high_jump_flag_requires_boolean | 31 |

### test_game_verifier_v2.py

관련 수동 케이스: SV-012–SV-014

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-348 | test_javascript_and_python_match_with_two_revives | 23 |
| AT-349 | test_javascript_and_python_match_after_clearance_for_multiple_seeds | 34 |
| AT-350 | test_v2_dispatch_uses_frozen_constants_even_if_current_constants_change | 49 |
| AT-351 | test_submitted_score_and_ticks_cannot_claim_items_or_revives | 61 |
| AT-352 | test_client_item_and_revive_flags_have_no_authority | 74 |
| AT-353 | test_time_limit_is_legitimate_but_other_unfinished_ticks_are_rejected | 82 |
| AT-354 | test_legacy_dispatch_preserves_v1_no_collision_rejection | 90 |
| AT-355 | test_unknown_versions_and_non_integer_fields_are_rejected | 97 |

### test_game_verifier_v21.py

관련 수동 케이스: SV-014

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-356 | test_stage_speed_and_gap_are_driven_by_frozen_version_constants | 23 |
| AT-357 | test_score_sources_keep_v2_and_v21_leaderboards_separate | 37 |
| AT-358 | test_v21_browser_replay_matches_server_and_applies_linear_revive_penalty | 41 |
| AT-359 | test_frozen_v2_browser_replay_keeps_old_score_and_summary_contract | 54 |
| AT-360 | test_version_dispatch_rejects_unknown_version | 63 |

### test_load_guards.py

관련 수동 케이스: SV-045–SV-047

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-361 | test_required_profiles_are_exact_and_total_690_seconds | 97 |
| AT-362 | test_remote_target_and_preflight_fail_closed | 105 |
| AT-363 | test_last_stock_probe_requires_one_synthetic_item | 143 |
| AT-364 | test_budget_ledger_is_locked_0600_and_charges_admission_before_completion | 164 |
| AT-365 | test_approved_time_extension_preserves_consumption_and_enforces_cap | 180 |
| AT-366 | test_budget_and_fresh_participant_cursor_persist | 198 |
| AT-367 | test_cohort_preparation_calls_are_charged_once_to_same_cap | 213 |
| AT-368 | test_remote_cohort_requires_exactly_5000_private_cookie_identities | 224 |
| AT-369 | test_cohort_fingerprint_is_stable_but_changes_with_identity | 255 |
| AT-370 | test_redeployment_retarget_requires_explicit_ids_and_preserves_identities | 262 |
| AT-371 | test_redeployment_cursor_migration_is_audited_idempotent_and_keeps_spend | 298 |
| AT-372 | test_failed_redeployment_cursor_write_leaves_original_ledger_intact | 355 |
| AT-373 | test_redeployment_target_proof_rejects_project_schema_campaign_or_deployment_change | 382 |
| AT-374 | test_remote_redeployment_resume_moves_existing_cursor_after_new_preflight | 403 |
| AT-375 | test_no_jump_payload_uses_real_physics_and_wait_duration | 497 |
| AT-376 | test_stage_and_overall_flow_counts_are_both_recorded | 509 |
| AT-377 | test_performance_targets_separate_general_finish_draw_and_failures | 519 |
| AT-378 | test_security_probe_uses_checkpointed_fault_and_recovery | 535 |
| AT-379 | test_dry_run_is_bounded_and_has_write_tracking_cost_envelopes | 612 |
| AT-380 | test_http_client_uses_cookie_idempotency_and_protection_headers | 628 |
| AT-381 | test_network_failure_writes_sanitized_private_report | 669 |
| AT-382 | test_endpoint_metrics_never_include_opaque_ids | 704 |

### test_metrics.py

관련 수동 케이스: SV-026–SV-028

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-383 | test_ordered_same_position_window_and_environment_ctr | 85 |
| AT-384 | test_ctr_closes_windows_deduplicates_and_keeps_pending_separate | 100 |
| AT-385 | test_ctr_window_ending_at_report_end_stays_pending_until_next_report | 136 |
| AT-386 | test_loading_last_active_no_checkpoint_double_count_and_unknown | 149 |
| AT-387 | test_zero_exposure_null_rate_and_guide_not_a_conversion | 160 |
| AT-388 | test_reentered_screen_active_time_is_added_without_checkpoint_overlap | 166 |
| AT-389 | test_stage_replays_do_not_count_completed_person_as_an_exit | 178 |
| AT-390 | test_scratch_start_progresses_to_both_visible_result_and_saved_completion | 187 |
| AT-391 | test_visible_scratch_with_failed_save_is_not_a_visibility_exit | 202 |
| AT-392 | test_restored_visible_result_adds_dwell_without_a_new_scratch_stage | 214 |
| AT-393 | test_open_observation_window_is_not_abandonment | 227 |
| AT-394 | test_future_report_and_naive_times_are_rejected | 233 |
| AT-395 | test_completed_recent_screen_remains_in_exit_denominator | 238 |
| AT-396 | test_source_cohort_new_return_and_conversion_are_unique | 249 |
| AT-397 | test_sharing_and_content_report_observed_actions_without_delivery_inference | 263 |
| AT-398 | test_share_purposes_require_owned_intents_and_game_rewards_exclude_claim_shares | 298 |
| AT-399 | test_invitation_ledger_reports_period_ratio_and_post_cooldown_reparticipation | 331 |
| AT-400 | test_game_last_checkpoint_and_stage_active_dwell_keep_unknown_explicit | 348 |

### test_metrics_acceptance.py

관련 수동 케이스: SV-024, SV-026, SV-027

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-401 | test_first_and_current_visit_server_conversion_are_separate | 64 |
| AT-402 | test_loading_ready_next_screen_fallback_exit_rate_and_unlinked | 74 |
| AT-403 | test_abandoned_active_dwell_and_gemini_stages_are_observed | 86 |
| AT-404 | test_filters_scope_real_rows_and_leaderboard_masks_private_nickname | 105 |

### test_migration_acceptance.py

관련 수동 케이스: SV-035, SV-041

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-405 | test_full_migration_stack_applies_to_database_without_dino_schema | 129 |
| AT-406 | test_additions_apply_to_foundation_only_and_are_idempotent | 167 |
| AT-407 | test_v21_extends_version_constraints_without_mixing_v2_scores | 222 |
| AT-408 | test_real_top3_contact_requires_consent_metadata_but_keeps_synthetic_rows_compatible | 248 |
| AT-409 | test_foundation_reapply_fails_without_damaging_existing_data | 273 |

### test_phase2_load.py

관련 수동 케이스: SV-045–SV-047

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-410 | test_dry_run_is_default_and_never_touches_network_or_fixture_subprocess | 40 |
| AT-411 | test_phase2_budget_exhaustion_is_fail_closed | 51 |
| AT-412 | test_phase1_ledger_cannot_be_reused_or_overwritten | 69 |
| AT-413 | test_version_mismatch_is_rejected | 87 |
| AT-414 | test_remote_approval_is_phase2_and_exactly_bounded | 94 |
| AT-415 | test_platform_auth_files_require_private_permissions_and_exact_formats | 121 |
| AT-416 | test_platform_auth_headers_are_sent_but_never_enter_metrics_or_output | 149 |
| AT-417 | test_known_v2_fixture_has_server_verifiable_coin_and_repeat_revive_path | 186 |
| AT-418 | test_long_rich_path_falls_back_to_a_real_bounded_collision | 193 |
| AT-419 | test_burst_workers_attempt_exactly_one_flow_even_at_minimum_think_time | 203 |
| AT-420 | test_default_envelope_and_per_stage_cleanup_reservation_remain_bounded | 229 |
| AT-421 | test_rate_limit_timeout_and_unexpected_response_fail_the_stage | 238 |
| AT-422 | test_failure_metrics_cannot_produce_a_successful_final_status | 263 |
| AT-423 | test_production_environment_is_rejected | 273 |

### test_phase2_metrics.py

관련 수동 케이스: SV-026–SV-028

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-424 | test_v2_score_and_server_game_summary_are_version_scoped | 60 |
| AT-425 | test_loading_content_ordered_ctr_and_ungrounded_shares_are_unknown | 91 |
| AT-426 | test_ranking_contact_counts_are_game_version_scoped | 145 |
| AT-427 | test_draw_cta_metric_counts_events_and_unique_participants_with_readable_label | 155 |

### test_phase3_campaign_window.py

관련 수동 케이스: SV-042

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-428 | test_window_helper_uses_inclusive_open_and_exclusive_close | 35 |
| AT-429 | test_closed_window_rejects_new_game_before_ticket_use_but_allows_replay | 94 |
| AT-430 | test_closed_window_rejects_new_draw_without_credit_pool_or_inventory_mutation_and_allows_replay | 117 |

### test_phase3_claim_payment.py

관련 수동 케이스: SV-038–SV-040

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-431 | test_paid_rejects_each_missing_evidence_without_mutation | 147 |
| AT-432 | test_paid_updates_claim_inventory_history_and_audit_once | 168 |
| AT-433 | test_paid_claim_cannot_withdraw_required_evidence | 210 |

### test_phase3_pool_depletion.py

관련 수동 케이스: SV-033

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-434 | test_all_5000_slots_are_consumed_once_with_exact_inventory_mix | 21 |

### test_phase3_preflight.py

관련 수동 케이스: SV-043, SV-044

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-435 | test_confirmed_inventory_and_pending_policies_are_distinct | 17 |
| AT-436 | test_launch_with_missing_decisions_is_rejected | 24 |
| AT-437 | test_complete_draft_still_requires_explicit_approved_state | 28 |
| AT-438 | test_invalid_launch_control_types_and_status_are_rejected | 37 |
| AT-439 | test_ranking_stock_cannot_be_accidentally_added_to_draws | 44 |
| AT-440 | test_only_one_campaign_date_is_a_configuration_error | 48 |
| AT-441 | test_equal_total_cannot_hide_wrong_prize_distribution | 55 |
| AT-442 | test_invalid_event_window_and_naive_time_are_rejected | 60 |
| AT-443 | test_deleted_checks_or_placeholder_cannot_pass_readiness | 67 |
| AT-444 | test_test_flags_cannot_be_marked_production_ready | 74 |

### test_rate_limit_buckets.py

관련 수동 케이스: SV-005

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-445 | test_every_participant_on_an_ip_uses_one_shared_12000_request_bucket | 24 |
| AT-446 | test_anonymous_and_admin_use_the_same_shared_ip_bucket | 28 |
| AT-447 | test_participant_requests_keep_the_same_shared_ip_bucket | 34 |
| AT-448 | test_route_subjects_and_existing_limits_are_unchanged | 41 |
| AT-449 | test_database_rejection_remains_a_retryable_429 | 54 |

### test_schema_guard.py

관련 수동 케이스: SV-006, SV-041

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-450 | test_latest_present_but_claim_status_migration_absent_is_rejected | 56 |
| AT-451 | test_all_required_versions_pass_and_schema_version_remains_latest | 66 |
| AT-452 | test_missing_prerequisite_is_rejected_and_rollback_restores_full_stack | 94 |

### ui_modal_lifecycle.test.cjs

관련 수동 케이스: NV-05, NV-06, CL-07

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-453 | an old submission finishing cannot close a newer modal or move focus back to the removed form | 42 |
| AT-454 | a named form dialog focuses its first field and contains forward and backward keyboard navigation | 65 |
| AT-455 | Escape cancels a cancellable form and restores its opener without submitting | 84 |
| AT-456 | pending confirmation is single flight and failure keeps the same form available | 95 |

### vercel_analytics.test.cjs

관련 수동 케이스: AN-09

| 정의 ID | 원본 검증 이름 | 소스 줄 |
| --- | --- | ---: |
| AT-457 | Vercel pageviews remove invite codes, query strings, fragments and extra payload | 10 |
| AT-458 | Vercel rejects private/unknown routes, offsite URLs and custom events | 18 |
