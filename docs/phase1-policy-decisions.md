# Phase 1 policy decisions

Effective 2026-09-25. The user's latest annotations and follow-up answers override older draft/common/phase2/phase3 wording. The previously missing source_user_plan.md was supplied and saved on 2026-09-25. The user reconfirmed that a new invitation reward bringing the balance to 3 starts the cooldown; the supplied plan now reflects this correction.

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

## Phase 2 adopted decisions

Effective 2026-09-25 for the Phase 2 Preview/test implementation. These decisions replace the Phase 1 deferrals for D11 and D14. Adoption fixes the behavior that the client and verifier test against; it does not constitute final public-event, prize, eligibility, legal, or production approval.

| ID | Phase 2 adopted decision | Evidence/test obligation |
|---|---|---|
| D11 | Enable deterministic v2 coins, hearts, and repeated revives under game version `2.0.0`. Coin is +10 points; first coin is tick 180 and later interval is 120–240 ticks. First heart is tick 1,200 and later interval is 1,500–2,100 ticks. Stored heart capacity is 1; extra hearts while full give no bonus. Each heart can absorb one collision, protection lasts 90 ticks, and later hearts can enable later revives. Play ends on an unprotected collision or at the valid 36,000-tick `TIME_LIMIT`. | Frozen constants; browser/Python replay parity; multi-seed spawn-clearance fixtures; repeated-revive and time-limit tests; versioned score/rank storage. Exact rules are in `phase2-game-rules.md`. |
| D14 | `record_share` and `prize_share`, like `retry_invite`, may earn the inviter +1 only after the friend completes the normal valid-visit qualification. Share/copy/preview actions alone never reward. Campaign+inviter+visitor deduplication is common across purposes, as are self-invite rejection, maximum balance 3, active-time/interaction proof, and cooldown. | Cross-purpose pair replay grants once; preview is read-only; opaque share attribution stays separate from reward identity; public cards exclude private contact/authentication data. |

The adopted tuning values are test numbers. A later mechanics change must use a new game version and matching verifier rather than silently modifying `2.0.0` or mixing its leaderboard with `1.2.0`.

TOP3 contact details remain reusable, while qualification provenance is append-only by participant and game version. `ranking_contact.game_version` is the current UI pointer; `ranking_contact_version` retains every qualified version for metrics and snapshots, including a legacy Preview's `1.2.0` insert attempt that reaches the `BEFORE INSERT` trigger but is later ignored by `ON CONFLICT DO NOTHING` against an existing contact row.

## Phase 3 decisions still pending

| ID | Pending approval | Current Phase 2 boundary |
|---|---|---|
| D02 | Real gifts, inventory, odds, and budget | synthetic labelled test inventory only |
| D03 | Public opening and closing timestamps | test schedule/status gates only |
| D04 | Tie handling and split awards | dense ties preserved; `tie_policy="UNDECIDED"`; no arbitrary final winner |
| D05 | Student/Gemini proof and evidence | synthetic verification fields only; no real upload |
| D06 | Deadlines, no-response, ineligibility, same-human, and alternate-winner policy | manual hold/reason; no automatic real re-award |
| D10 | Sessions crossing the campaign closing boundary | timestamps retained; final settlement remains blocked |
| D12 | Cookie/session/PII retention, notice, and consent | configurable synthetic test values; no legal assumption |
| D13 | Production domain, official benefit/content URLs, Notion publication, and operator contact | labelled/local placeholders and allowlisted links only |
| Launch | Final public event approval, production enablement, physical-device acceptance, and real fulfillment | Preview/test evidence only |

D11 and D14 are no longer feature-policy deferrals for Phase 2. Phase 3 may approve publication of the adopted build or approve a newly versioned rule set; it must not relabel untested tuning as the existing `2.0.0` contract.
