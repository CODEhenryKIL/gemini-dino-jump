# Phase 1 implementation plan

Source of scope: `phase1-work-instructions.md`. Production deployment, production data changes, paid resources without approval, real prizes, and main merges are excluded from authorization. Preview deployment and bounded remote tests are authorized once an isolated development DB is available.

## Baseline and preservation

- Branch: `codex/phase1-operating-foundation`, based on `f57c3d1`.
- Baseline: 3 Dino-only Node tests and 8 legacy Python tests pass. Those tests do not establish production readiness.
- Preserve the current Dino engine, shared physics constants, artwork, controls, and difficulty. Capture deterministic physics vectors before tightening verifier input limits.
- Preserve the supplied work instructions verbatim and existing user changes. Figma renderers remain outside this task.

## Architecture decision

Reuse Python HTTP handlers and vanilla JavaScript. Use PostgreSQL transactions through Supabase's transaction pooler (port 6543 remotely), with psycopg prepared statements disabled, bounded per-process concurrent connections, connection/statement/lock timeouts, and no persistent application connection pool. Native PostgreSQL is the local fallback only when the preferred Supabase CLI cannot start because Docker is absent. There is no SQLite or memory persistence fallback.

Business tables live in the unexposed `dino` schema. All tables enable RLS, anonymous/authenticated Data API roles have no business-table grants, and a dedicated non-superuser `dino_app` role has the precise backend permissions. Private recipient and delivery data are separate from ranking data. Admin identity is validated with Supabase Auth and checked against an explicit database admin membership table.

Transactions protect ticket consumption, game finalization, referral reward, stock reservation, claim submission and simulated delivery. Ownership is checked before any existing result is returned. The transport commits before returning success. No request creates schema, campaign configuration, prize rows or seed data.

## Work sequence and ownership

1. Read-only account and code audit; establish baseline tests and branch.
2. Database lane: migrations, explicitly guarded development seed, business service, row locks, unique constraints, durable events and aggregation.
3. HTTP lane: PostgreSQL adapter, configuration validation, Supabase Auth, request validation/rate limits, no-store responses, bounded verifier, deployment configuration.
4. Frontend lane: server ticket counts, recovery and lifecycle cleanup, safe rendering, analytics, authenticated admin and metrics UI.
5. Test lane: actual PostgreSQL empty migration, HTTP integration, concurrency/security/failure recovery, game parity, load generator and safety budget.
6. Integrate and review, run local browser flows, then authorized Preview and remote tests on the approved existing development project.
7. Open a draft PR and keep `phase1-readiness-report.md` current with evidence and explicit remaining gaps.

## Acceptance evidence

The readiness report must map each work-order section to implementation, local tests, remote evidence, and any unresolved approval or verification. Local concurrency is not remote 200-user validation. Mobile emulation is not a physical phone. Page exits are estimates, share-open is not successful sharing, and Gemini clicks are not external signup confirmations.

## Current access findings

2026-09-23: GitHub repository access includes push/admin; repository was initially private and was changed to public after the user’s explicit request. Vercel team `team_BhbQ5LTcQ0r7hANiiKA2PmoR` is active Pro with seven projects, including `dino-nanobanana` (`prj_U9Wi3VyA46EpOdOyrq0P3RRHwMSX`). Its Preview has no environment variables and the project has no Git integration. Supabase organization `dbppzfbgzsspgzyrztus` is Pro with two projects.

The user explicitly approved reusing active Seoul project `igfrnexknwtiljdqjrbp` for development/Preview because no other app currently operates there. This supersedes the proposed additional paid development project. No new project will be created. Existing public/auth/storage data must be preserved; only a new private `dino` schema and narrowly scoped application role are added. The project is not a approved Dino production environment. Production needs a separately decided environment, with no automatic copying of synthetic records.

Before mutation: 11 public tables, 3 Auth users, 47 Storage objects; public column-definition fingerprint `6e5c0a823cd05c44fac1fd502b76874c`. Exact existing public row counts: questions 33, score_results 1, analysis_jobs 2, cost_logs 45, profiles 3, question_sets 3, test_sessions 5, answers 26, transcripts 22, audio_analyses 22, feedbacks 22. Neither the `dino` schema nor `dino_app` role exists. Compare after provisioning. Do not alter existing auth providers, global auth URLs, exposed schemas, or existing table privileges.

Sources: https://supabase.com/docs/guides/database/connecting-to-postgres and https://www.psycopg.org/psycopg3/docs/advanced/prepare.html .
