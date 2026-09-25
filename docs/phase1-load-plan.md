# Phase 1 Preview load and measurement plan

This plan defines the only approved use of `scripts/phase1_load.py`. It prepares an auditable test; it does not authorize a remote run. Production, real prizes, real contact data, and a non-test Supabase schema are rejected by the runner.

## Latest authorization — 2026-09-25

The user approved one additional 200-VU burst with “한번 더 해줘”. Only the cumulative time cap increases from 30 to **32 minutes (1,920 seconds)**; the **30,000 API-call cap**, existing ledger, and participant cursor remain intact. Before this run the ledger contains 22,116 admitted/completed calls, 1,724 reserved seconds, and cursor 2,424/5,000. The burst reserves 120 seconds, bringing reserved time to 1,844 seconds. No new paid resource or compute upgrade is authorized. Historical 1,800-second references below describe the earlier runs.

## Test shape

The required `full` profile opens flows for exactly these stage windows:

| Stage | Virtual users | Admission window | Purpose |
| --- | ---: | ---: | --- |
| 1 | 10 | 60 s | low-concurrency entry and end-to-end baseline |
| 2 | 50 | 120 s | normal concurrent verified play |
| 3 | 100 | 180 s | finish, draw, ranking, and tracking concentration |
| 4 | 200 | 300 s | sustained peak target |
| 5 | 200 | 30 s | simultaneous burst |

The windows total 690 seconds. The durable time ledger reserves another 90 seconds for health checks and in-flight worker cleanup, so one full run reserves 780 of the cumulative 1,800-second cap. A participant is admitted only before its stage deadline; an admitted game may finish during the cleanup reserve.

Each flow uses one fresh synthetic participant with exactly one initial ticket. It calls `/api/me`, creates and starts a session, derives a no-jump collision from the unchanged server physics simulator, waits the real collision duration, submits the exact score/ticks, opens the participant's one campaign draw, replays the same draw request to verify idempotency, completes scratch, reads ranking, and writes one allowlisted `page_view` event. Every twentieth winning flow may submit synthetic claim data twice with one idempotency key. Participants are never reused, so the one-draw rule and ticket limit are not bypassed.

The burst stage starts 200 workers on one barrier. Their deterministic games naturally concentrate valid finish/draw requests a few seconds later. The ordinary stages retain the configured 45-second think time after both success and failure. This is 200 VU, not 200 RPS.

## Private cohort contract

The cohort is prepared outside the load runtime and is untracked with mode `0600`:

```json
{
  "schema_version": 1,
  "environment": "preview",
  "project_ref": "igfrnexknwtiljdqjrbp",
  "base_url": "https://exact-preview.vercel.app",
  "deployment_id": "dpl_exact",
  "campaign_id": "synthetic-campaign",
  "preparation_api_calls": 0,
  "created_at": "2026-09-25T00:00:00Z",
  "participants": [
    {
      "cookie": "dj_session=<private raw token>",
      "participant_id": "<opaque synthetic id>",
      "referral_code": "<synthetic referral code>"
    }
  ]
}
```

Remote runs require exactly 5,000 unique entries; the maximum is also 5,000. Raw cookies and participant IDs are never copied to stdout or reports. Reports contain only a SHA-256 cohort fingerprint, aggregate metrics, safe deployment identifiers, and normalized endpoint paths.

`preparation_api_calls` is `0` when the cohort was inserted directly by the approved synthetic seed transaction. If normal HTTP APIs prepared it, record every preparation, retry, and smoke call there. The durable `0600` ledger charges that value once per cohort fingerprint, then applies all scripted runs to the same 30,000-call phase cap.

The ledger locks before any run. It reserves the full time budget before preflight, permanently advances the participant cursor before a flow, admits each API call before network I/O, and records completion only after an HTTP response. A crash therefore consumes budget and participants conservatively. There is intentionally no reset command. Use a new ledger only for a genuinely new approved phase budget, preserving the old ledger as evidence.

### Audited redeployment resume

When a code fix creates a new immutable Vercel deployment, keep the original cohort manifest and cumulative ledger unchanged and use the explicit resume flags. The runner first validates the manifest against its original immutable URL and deployment ID. It then validates the new immutable `*.vercel.app` URL through `/api/health` and `/api/config`, requiring the new deployment ID and the same Supabase project, `dino_dev` schema, campaign, and participant identity digest. Only after those checks does it atomically move the existing participant cursor to the new cohort fingerprint.

The ledger records both immutable URLs and deployment IDs, the project/schema/campaign proof, the participant identity digest, and the cursor at migration. The original fingerprint is retired so it cannot restart at participant zero. Admitted/completed calls, prior run records, and reserved seconds are retained; there is no budget reset or refund. Actual runtime remains a separate report field and never reduces the cumulative reserved duration.

The current resume invocation is:

```bash
.venv/bin/python scripts/phase1_load.py \
  --mode remote \
  --profile full \
  --base-url https://dino-nanobanana-1aacrhim0-henry-kils-projects.vercel.app \
  --expected-deployment-id dpl_DtuPX3jMcdSm3juRS6wU7aZ6fEjw \
  --resume-from-base-url https://dino-nanobanana-hvpbyc6w6-henry-kils-projects.vercel.app \
  --resume-from-deployment-id dpl_3zhwHtPzAdSvx9mBY7JfPerpK1zN \
  --expected-project-ref igfrnexknwtiljdqjrbp \
  --cohort .local/phase1/remote-cohort.json \
  --ledger .local/phase1/remote-load-budget.json \
  --report .local/phase1/remote-load-report-rerun.json \
  --deployment-auth-cookie-file .local/phase1/deployment-auth-cookie
```

The first attempt reserved 784 seconds, including the separate invitation probe. This full rerun reserves 780 seconds, bringing the immutable cumulative reservation to 1,564 of 1,800 seconds and leaving 236 seconds. The report records its measured runtime separately. An in-progress run is not evidence that the stages or performance targets passed; completion and reconciliation must be read from the final report and database checks.

For a second redeployment, derive a new private manifest from the original without changing either source file. The derivation must recreate the audited OLD1→OLD2 retarget in memory, require its cohort fingerprint to equal the ledger's single active cohort, require its participant identity digest to equal the first migration audit, and verify the ledger bytes and cursor are unchanged before and after writing. The resulting `.local/phase1/remote-cohort-resumed.json` is mode `0600`, contains the same 5,000 private identities, and identifies OLD2:

- URL: `https://dino-nanobanana-1aacrhim0-henry-kils-projects.vercel.app`
- deployment: `dpl_DtuPX3jMcdSm3juRS6wU7aZ6fEjw`
- active cohort fingerprint: `53dbe5284a3bfaad83b15048ec7c2bba8fbf15969c18a728d60733a39b83776e`
- participant identity digest: `11640ea6dd6426270bcbe7ae4a7adfdd93cf55a8dfe8e853a0a8137ebe69e113`
- preserved cursor: `2222 / 5000`

The next performance-fix run can therefore migrate OLD2→NEW3 and execute only the required 200-VU burst:

```bash
.venv/bin/python scripts/phase1_load.py \
  --mode remote \
  --profile burst \
  --base-url "$NEW3_IMMUTABLE_VERCEL_URL" \
  --expected-deployment-id "$NEW3_DEPLOYMENT_ID" \
  --resume-from-base-url https://dino-nanobanana-1aacrhim0-henry-kils-projects.vercel.app \
  --resume-from-deployment-id dpl_DtuPX3jMcdSm3juRS6wU7aZ6fEjw \
  --expected-project-ref igfrnexknwtiljdqjrbp \
  --cohort .local/phase1/remote-cohort-resumed.json \
  --ledger .local/phase1/remote-load-budget.json \
  --report .local/phase1/remote-load-report-burst-new3.json \
  --deployment-auth-cookie-file .local/phase1/deployment-auth-cookie
```

Before NEW3, the durable totals are 21,778 completed/admitted calls and 1,564 reserved seconds. The burst reserves another 120 seconds and has a conservative 2,439-call envelope, so it fits the remaining 236 seconds and 8,222 calls without lowering traffic or resetting the ledger. A successful admission would bring reserved time to 1,684 seconds, leaving 116 seconds. Its actual runtime is reported separately and does not alter those reservations.

## Fail-closed Preview checks

Before load, `/api/health`, `/api/config`, the cohort, and command arguments must agree on:

- `environment=preview`, the exact Vercel deployment ID, and an exact `.vercel.app` origin;
- Supabase project `igfrnexknwtiljdqjrbp` and private schema `dino_dev`;
- `synthetic_only=true`, `test_seed=true`, database `ready`;
- the active synthetic campaign and game version `1.2.0`.

Any Production marker, public schema, other project/deployment, invalid prepared cookie, 5xx, prepared-cookie 401/403, inventory error, response redirect, or exhausted budget stops the run. Rate-limit responses are reported separately. Deliberate negative checks (unauthenticated `/api/me`, cross-owner recovery, idempotency conflict) are also reported separately from unexpected failures.

If Vercel Deployment Protection is enabled, pass its sanctioned bypass token through a `0600` file and `--protection-token-file`. For an official temporary share URL session, store its single `name=value` authentication cookie in another `0600` file and use `--deployment-auth-cookie-file`. The runner combines that platform cookie with each participant's distinct `dj_session` cookie. It neither disables protection nor stores either secret in a report. IP allowlisting remains a platform setting and is not modified by this tool.

## Request and cost envelope

Run the network-free estimate first:

```bash
python3 scripts/phase1_load.py --dry-run --profile full
```

With the default 45-second think time, the current full envelope is:

- 2,170 flow attempts and 2,172 fresh participants including security probes;
- 21,935 calls for the scripted path;
- 26,275 conservative admitted calls after retry headroom, under the hard 30,000 cap;
- 15,417 mutating HTTP requests, 2,170 client tracking events, and 13,135 server domain-event attempts;
- 53,004 as a deliberately broad database write-statement envelope.

These are upper bounds for planning, not measured database rows or a monetary quote. The report records admitted and completed API calls separately. Supabase/Vercel usage and shared project health must be checked in their dashboards before and after the run.

## Separate scenarios

The normal profile already separates endpoint and business-phase metrics for entrance, start, genuine-play wait, finish, draw, duplicate replay, claim, ranking, and tracking.

The security preflight uses a fresh participant to produce real server-time evidence: it starts a game, waits 1.05 seconds, records tick 60, reports a network fault, waits the 10.2-second reconciliation interval, and requires one `AUTO_APPROVED` refund. It then repeats the same evidence with that participant and requires the second fault to remain `PENDING` with `REVIEW_REQUIRED`, proving the 24-hour automatic-refund boundary instead of treating client claims as unlimited refund proof.

Invitation qualification is optional and separate: `--invitation-probe` consumes two fresh participants, creates a server nonce, waits 3.05 active seconds, qualifies after an interaction, and verifies the inviter balance increased exactly once. It adds four seconds to the time reservation and four calls. It does not mix invitation latency into normal game metrics.

Last-stock competition is also separate. Prepare exactly one synthetic item in the test campaign and expose `test_inventory_remaining: 1` through the safe Preview health response, then add `--require-last-stock` to a burst run. The runner refuses this scenario without that guard. It never edits inventory or seeds data itself. Afterward, compare inventory and draw aggregates to prove one reservation and zero overallocation. An inventory error is a safety stop, not a passing expected negative.

## Execution gate and reporting

Only after Preview deployment, migration/seed verification, 5,000-participant cohort creation, dashboard baseline capture, and explicit target review should an operator run the remote command. Example placeholders are intentionally non-runnable:

```bash
python3 scripts/phase1_load.py \
  --mode remote \
  --profile full \
  --base-url https://exact-preview.vercel.app \
  --expected-deployment-id dpl_exact \
  --cohort /private/path/cohort.json \
  --ledger /private/path/phase1-ledger.json \
  --report /private/path/phase1-report.json
```

The report includes p50/p95/p99 by normalized endpoint and business phase, each stage's VU/window/actual cleanup time, RPS, timeouts, rate limits, expected negatives, unexpected failures, remaining cohort, target guards, and cumulative budgets. Success targets are general API p95 at or below 1 second, finish/draw p95 at or below 2 seconds, unexpected failure rate below 1%, and database reconciliation showing zero duplicate rewards and zero inventory overallocation. API results do not prove device FPS; 2차 UI changes require a new device performance pass.
