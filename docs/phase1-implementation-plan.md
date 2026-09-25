# Phase 1 implementation and evidence plan

Started 2026-09-25 from `58b1e14` on `codex/phase1-clean-start`; application baseline `f57c3d1`. The latest phase1-work-instructions.md and subsequent user decisions are authoritative. Production and main changes are excluded.

## Responsibility

- Backend: schema/migrations, scoped role, cookie transport, transactional rules, verified game physics, private claims, real administrator Auth, analytics queries and backend tests.
- Frontend: existing minimal screens, API contract integration, lifecycle/recovery, complete privacy-safe event capture and administrator UI.
- Load tooling: real physics/waits, normal cookie APIs, persistent 30 min/30,000 request budget across executions, private synthetic cohort and measurements.
- Integration: live access verification, untouched-resource baseline, local PG setup, Preview-only settings/deploy, browser verification, remote load, independent review and report/PR.

## Required evidence gates

1. Access and baseline: actual GitHub permissions, Supabase project/status/schema/roles/public rows/Auth/storage, Vercel project/target; preserve existing dino and public resources.
2. Local DB: blank migration plus upgrade/non-destructive existing schema checks; FORCE RLS and per-role denial of unrelated data; explicit synthetic seed and environment guard.
3. Cookie identity: initial one-time 1 ticket, restore/lost-response/multitab/no duplicate, expiry invalid-cookie, Origin/CSRF/input/rate limits and failure behavior.
4. Games: genuine version/seed/input replay; initial-first consumption; reservation/refund cap <=3; duplicate start/finish, ownership, invalid result exclusion, abandonment/expiry/fault recovery.
5. Invitations: visible >=3s+interaction nonce, no GET reward, multi-inviter allowed/pair replay blocked, held slots+balance max3, reaches3 starts 10h, grants blocked during cooldown, new visits only afterward, no auto replenishment; 100 concurrent attempts.
6. Draw/claims/ranking: one draw per campaign+participant; same result across sessions, last inventory race/lock distinction, synthetic recipient checks, persistent provisional TOP3 contact, undecided ties/close rules cannot award final winners, manual contact versus paid, member permissions/assignee/version/audit.
7. Measurement: pre-auth observation and explicit unlinked, first/session attribution, all required loading/game/invite/draw/scratch/claim/Gemini/content events, active time checkpoints and observation windows, unique denominators and ordered exposure-click intersection/union, test filters, no PII in events/Vercel.
8. Local browser: full loop, reload/recovery/network faults, administrator actual Auth, desktop and mobile emulation; distinguish missing physical-device evidence.
9. Preview: safe upload inspection, Python3.12 dependency/build, scoped DB SSL verification, valid target/env/guard, static+API smoke, real browser E2E and analytics.
10. Remote load: 5000 synthetic participants + genuine game records, actual 10/50/100/200 VU +200burst within cumulative cap, measured endpoint/stage latency/errors/RPS and DB/function observations, concurrency/replay invariants, production data untouched; failures remain open.
11. Delivery: updated README/runbook, migration/seed/.env.example, event/metric dictionary, raw sanitized test/load reports, phase1-report.md, undecided-policy table, commits/PR and ready Preview URL.

## Work and audit log

The entries below are chronological notes, not the latest state. Use [phase1-report.md](phase1-report.md) for current deployment, permissions and test results. Subsequent acceptance review identified additional replay authorization, refund response, concurrent draw and measurement gaps; those fixes must be tested before final acceptance.

- Live access verified: GitHub public repo admin/push; Supabase selected Seoul project active PG17.6; Vercel dino-nanobanana latest previous Preview is ERROR.
- Before writes: old `dino`20 tables and dino_app LOGIN exist; `dino_dev` and dino_dev_app absent. Existing public11 counts match prior inventory; Auth5, Storage47. New work must preserve those resources.
- Local PG previously in /tmp is absent; rebuilding an isolated loopback PG17.6 for actual DB tests. Python3.12.13 with pinned psycopg3.3.6 available in isolated verification environment.
- All gates still pending implementation/verification unless separately marked by concrete evidence.

- User requested a separate friendly URL during implementation: prepare `google-korea-team-gemini.vercel.app` if available, pointing only to the new Preview; preserve existing deployment links and Production. Availability and assignment are pending actual verification.

## Integration evidence (2026-09-25, in progress)

- Current local migration + explicit synthetic seed applied to isolated `dino_phase1_v2_browser` on loopback PostgreSQL17.6: 23 tables initially, 25 test inventory items. Forward fault-review fields and screen_view_id added during review; final schema audit still in progress.
- Local Python3.12 launcher tested for literal env parsing, shell-substitution rejection by non-evaluation, process-env precedence and malformed assignments. `.env.local` previous contents preserved privately.
- Actual CUA browser: initial cookie restored; zero-ticket pending session is accessible; resumed game collided normally and stored FINISHED / VERIFIED / score32 / ticks194. Result displayed best32 and rank1. DB recorded client events after fixing missing event-batch Idempotency-Key.
- Real PostgreSQL metrics regressions7 PASS: ordered same-position bounded CTR, environment isolation, zero denominator, guide exclusion, active-time checkpoint deduplication and reentry, open-window exclusion, stage replay deduplication.
- Node regression tests16 PASS at last integrated frontend run; load guards16 PASS. Backend/security/concurrency evidence is being incorporated from isolated DB test runs; final full-suite rerun remains required.
- Created two synthetic Supabase Auth users for actual administrator login tests; credentials private only. Existing Auth5 preserved (expected count7 after these additions). No original public/dino row mutations or Storage changes requested.
- Vercel live read: existing Preview protection retained, Web Analytics already enabled, eight old Preview-global variables present; no new branch variables or deployment yet.
- Requested friendly alias `google-korea-team-gemini.vercel.app`: account-scoped lookup returned404. This does not establish global availability; actual assignment remains pending Preview readiness.
- Remote dino_dev migration, cohort5000, Preview deployment, administrator browser flow and remote load remain open gates. No complete-implementation claim yet.

### Subsequent integration updates

- Site metadata now reads `구글 코리아 팀 제미나이 | 공룡 점프`; requested alias is still pending assignment.
- Metrics regressions9 PASS, Node23 PASS. A full-suite run identified a stale concurrency-test schema; updated the isolated database with the additive migration. Final owner-scoped cohort test run remains pending.
- Local browser reload restored the same NO_PRIZE draw without another completion action. Persistent TOP3 form remained reachable from rankings, submitted synthetic contact information, and the actual authenticated administrator displayed the separate contact record. Splash/login hidden states now leave the accessibility tree.
- Remote migrations applied successfully to previously absent `dino_dev`:25 tables, both schema versions, all tables FORCE RLS, scoped role has no elevated attributes or memberships. Exact project/environment/empty-data preflight preceded explicit synthetic seed25. A `verify-full` pooler connection as `dino_dev_app` succeeded; unrelated accessible tables0.
- Remote administrator membership insertion was rejected by automatic approval review. User approval requested for the two new synthetic accounts and exact test-only permissions; no membership rows applied while pending.
- Branch-specific Vercel env registration failed because the project has no Git connection; no variable was created. Deployment-scoped runtime environment is the verified alternative, preserving global Preview/Production settings.
- Security advisor reports pre-existing public function warnings and disabled leaked-password protection; no dino_dev findings. These shared-project settings were not changed.
