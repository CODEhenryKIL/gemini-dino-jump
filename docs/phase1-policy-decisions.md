# Phase 1 policy decisions

Effective 2026-09-25. The user's latest annotations and follow-up answers override older draft/common/phase2/phase3 wording. The supplied original planning file source_user_plan.md is unavailable; no invented original is created.

## Fixed for implementation

| ID | Decision | Evidence/test obligation |
|---|---|---|
| D01 | Initial ticket exactly 1, once per campaign+participant; consume initial before invitation | duplicate initialization/lost response/concurrent tabs; two separate balances |
| Invite cap | Maximum owned invitation tickets 3, including an unresolved game's refund capacity | concurrency cap and refund/grant race |
| Cooldown | New invitation reward that brings spendable invitation balance to 3 starts 10h; spending allowed during delay, new rewards prohibited | actual DB transaction + controllable test clock boundary |
| Refill | After cooldown, retain remaining rights; a new valid visit can fill freed space; 2→3 begins a fresh 10h | no auto top-up, no lifetime/cumulative-three cap |
| D07 | Same visitor may reward different inviters; each campaign+inviter+visitor pair paid only once | A/B rewards + pair replay |
| D08 | No reward/queue for visits begun while full/cooling; evaluate a fresh visit after expiration, never reward an already-paid pair again | no retrospective qualification of a waiting-open tab |
| D09 | Verified game interruption from server/network/client fault returns original consumed right once; successful lost response restores result instead | fault evidence/reconciliation, no duplicate creation; no cooldown reset through refunds |
| Draw | One draw per campaign+participant after first verified finish; independent of sharing/retries | fixed result and last-inventory contention |
| Payout | Human operator contacts and delivers gifts; system holds permissions/status/inventory/audit only | contact!=paid; optimistic work ownership; replay-safe payment |
| Auth | Participant HttpOnly cookie, hashed server token; administrator real Supabase Auth plus DB membership | invalid cookie cannot silently mint a replacement; Origin checks |
| Environment | Existing Supabase project with private dino_dev and scoped role; no new paid project/branch | no changes to original public/dino/Auth/Storage data, shared-resource impact reported |

A browser cookie is not proof of a unique human. No device fingerprint, IMEI or private-mode detection is implemented. Participant count is pseudonymous cookie identity count.

## Deferred operating decisions

| ID | Deferred item | Phase 1 behavior |
|---|---|---|
| D02 | Actual gifts/stock/odds/budget | synthetic clearly labelled test inventory, no actual delivery |
| D03 | Exact campaign opening/closing | test schedule only, operational window unset; server status gates |
| D04 | Ties and split awards | preserve equal-score groups; no final award by arbitrary ID/order |
| D05 | Student/Gemini proof type | verification status/reference structure, no real proof upload |
| D06 | Deadline/no-response/ineligible/same-human/alternate-winner policy | manual hold/reason; no automatic real re-award |
| D10 | Started before closure, finished after closure | preserve timestamps, block final-winner settlement while undecided |
| D11 | Revival item and physics | Phase 2, OFF in Phase 1 |
| D12 | Cookie/session/PII retention, notice/consent | configurable synthetic test values; no legal assumptions or real personal data |
| D13 | Production domain/official benefits/content/Notion/operator contact | labelled test placeholders; no arbitrary outbound redirect tracking |
| D14 | Prize-result share earns retry tickets | measure link kind only; rewards through approved invitation links |

## Explicit operational boundaries

- Existing production deployment, DNS, original data and main are untouched.
- Preview and test users/data only; physical-device testing is a separate evidence item.
- New policy implementation is not complete just because this decision record exists. See phase1-report.md for proof and outstanding items.
