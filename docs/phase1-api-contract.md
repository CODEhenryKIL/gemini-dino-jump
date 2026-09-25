# Dino Jump Phase 1 API contract

This contract is the frontend/backend boundary for `codex/phase1-clean-start`. All JSON responses use UTF-8. Private responses send `Cache-Control: no-store`. Timestamps are ISO 8601 UTC strings. IDs are opaque strings.

## Common rules

- Participant authentication is the `dj_session` cookie. It is `HttpOnly; Secure; SameSite=Lax; Path=/` in Preview and Production. Local HTTP omits only `Secure`.
- JavaScript cannot read the participant token; the browser stores and sends it only as an HttpOnly cookie. A present but invalid/expired cookie returns `401 {"error":"SESSION_INVALID"}`; it never creates a replacement participant implicitly.
- Every mutating request accepts an `Idempotency-Key` header (8–128 printable ASCII characters). The same authenticated actor, route and key returns the original status/body after current authentication, participant status and required administrator permissions are revalidated. Reusing a key with another payload returns `409 IDEMPOTENCY_CONFLICT`.
- JSON request bodies are limited to 64 KiB; analytics batches to 32 events. Unknown analytics fields are rejected; other unrecognized fields are ignored and never stored. Invalid fields return a bounded `400` error.
- Browser mutations require an allowed `Origin`. CORS credentials are enabled only for configured origins; `*` is never used with cookies.
- Expected errors use `{ "error": "CODE", "message": "safe text", "retryable": false }`. Rate limiting is `429 RATE_LIMITED` plus `Retry-After`.

## Public/bootstrap

### `GET /api/health`

Returns `{ok, service, environment, deployment, database}`. `database` is `ready` or `unavailable`; no secret or server detail is returned.

### `GET /api/config`

Safe public configuration:

```json
{"campaign":{"id":"...","title":"...","status":"ACTIVE","game_version":"...","opens_at":null,"closes_at":null},"benefit_url":"https://...","auth":{"supabase_url":"https://<ref>.supabase.co","publishable_key":"..."},"limits":{"participant_cookie_max_age_seconds":2592000,"invite_active_ms":3000}}
```

The publishable Supabase key is public by design. Secret/service-role keys are never returned.

### `POST /api/observations`

Starts loading measurement before participant initialization. Body: `{observation_id,event_id,link_kind?,channel_code?,campaign_code?,share_id?,referrer_origin?}`. `share_id` is an opaque 8–128 character attribution ID; it never changes invitation reward deduplication. Returns `201 {observation_id,accepted:true,bootstrap_token}` or the original response on replay. It never creates a participant. `bootstrap_token` is a short-lived, high-entropy creation proof (not participant authentication); the frontend may coordinate it through an ephemeral in-memory/BroadcastChannel flow, then must discard it after the participant cookie is set. Only its hash is stored.

This endpoint requires a 32–128 character URL-safe random `Idempotency-Key`. The proof is bound to both the event ID and that key. Reusing an observation/event ID under another key is rejected with `409` and never returns the prior proof.

### `POST /api/participants/anonymous`

Body: `{bootstrap_token,observation_id?,invite_code?,share_id?}` when no cookie is present. The proof deterministically recovers the same participant/token after response loss or concurrent initialization, grants exactly one `INITIAL` ticket, sets the cookie and returns `201` (or `200` on replay). With a valid cookie, the body may be empty and restore returns `200`; if a second tab includes its matching bootstrap proof and observation ID, that observation is linked to the same participant. An invalid invite returns `invite_visit.status="INVALID_CODE"`; self invite returns `SELF_INVITE`; both have a null nonce and explicit reason. With an invalid cookie, returns `401 SESSION_INVALID` and does not create or grant. An observation ID alone can never recover or set another participant's cookie.

Response:

```json
{"participant":{"id":"...","nickname":"...","is_public":true,"referral_code":"..."},"tickets":{"initial":1,"invitation":0,"invitation_reserved":0,"available_total":1,"cooldown_until":null,"cooldown_notice_pending":false},"invite_visit":{"visit_nonce":"...","status":"PENDING"}}
```

`invite_visit` appears only when a valid, non-self invitation code was supplied. Merely opening an invite URL never grants a ticket.

### `GET /api/me`

Returns participant, ticket balances, `best_score`, `rank`, `pending_game_session`, the single campaign draw state (`LOCKED|AVAILABLE|DRAWN`), pending TOP3 profile state, and claim counts.

### `PATCH /api/me/profile`

Body `{nickname,is_public}`. Returns the updated public participant. This is unrelated to private TOP3 or claim contact data.

## Invitations

### `GET /api/referrals/me`

Returns `{invite_url, referral_code, invitation_balance, invitation_reserved, cooldown_until, cooldown_notice_pending, rewarded_pairs, valid_visits, rejected_visits}`.

### `POST /api/referrals/qualify`

Body `{code,visit_nonce,active_ms,interacted,event_id}`. `active_ms` must be at least the server-configured 3000 ms and `interacted` must be true. The nonce is server issued, short lived, participant bound and single use.

Returns:

```json
{"status":"REWARDED|ALREADY_REWARDED|SELF_INVITE|COOLDOWN|BALANCE_FULL|NOT_QUALIFIED|INVALID_NONCE","reason":"...","granted":1,"inviter_balance":3,"cooldown_until":"..."}
```

The inviter/visitor pair is unique. One visitor may reward multiple different inviters. Cooldown/full visits are not queued; a new visit after cooldown is required. Grant, balance lock and possible 10-hour cooldown start occur atomically.

### `POST /api/referrals/cooldown-notice/ack`

Body `{cooldown_until}`. Acknowledges only the current cooldown notice.

## Game lifecycle

### `POST /api/game-sessions`

Body `{event_id,observation_id?,visit_session_id?}`. Optional attribution IDs must belong to the authenticated participant; the current visit is used for game-start attribution. Atomically reserves and consumes one ticket (initial first, then invitation) and creates a session. Returns `201 {session_id,seed,version,status:"RESERVED",ticket_kind,expires_at}`. A pending refund slot counts toward the invitation capacity while refund reconciliation is outstanding.

### `POST /api/game-sessions/{id}/start`

Body `{event_id}`. Returns `{session_id,status:"ACTIVE",started_at}`. Replay safe.

### `POST /api/game-sessions/{id}/finish`

Body `{event_id,score,ticks,jump_ticks,checkpoints?,client_finished_at?}`. The server verifies the preserved game physics and bounded input. Returns:

```json
{"session_id":"...","status":"FINISHED","verification":"VERIFIED","score":123,"best_score":123,"rank":4,"draw":{"status":"AVAILABLE","draw_id":null},"top3_profile":{"required":false,"status":"NOT_REQUIRED"}}
```

Rejected verification is `422 GAME_VERIFICATION_FAILED` and never refunds a ticket.

### `POST /api/game-sessions/{id}/fault`

Body `{event_id,reason:"SERVER_ERROR|NETWORK_ERROR|CLIENT_ERROR",last_tick?}`. This reports an unfinished fault as `REVIEW_REQUIRED`; a client reason alone never grants a refund. A server reconciliation step checks that no verified/rejected finish exists, the session was active, bounded monotonic checkpoint evidence exists, and the grace period elapsed. A participant's first qualifying `NETWORK_ERROR` in 24 hours may be auto-approved; later network reports and all client-reported client/server errors remain `PENDING` for administrator review. Returns `{session_id,status:"FAULT_REPORTED",refund:{status:"REVIEW_REQUIRED",ticket_kind},fault_review:{status:"PENDING",version:1}}`. Normal collision, voluntary exit, and verification rejection are not refundable faults. An expired reservation that never started is safely auto-refunded; an expired active session becomes a pending fault review.

### `POST /api/game-sessions/{id}/checkpoint`

Body `{event_id,tick,stage}`. Stores a bounded monotonic checkpoint at a low frequency. It cannot finish a game or issue a refund.

### `GET /api/game-sessions/{id}`

Owner-only recovery. Returns lifecycle state, accepted result when present, and refund state. A lost finish/fault response is recovered here without repeating side effects.

## Ranking and TOP3 contact

### `GET /api/leaderboard?limit=100`

Returns `{leaderboard:[{rank,nickname,score,tied,is_me}],me:{rank,best_score},tie_policy:"UNDECIDED"}`. Equal scores remain tied; the API never declares a final winner by ID ordering.

### `GET /api/ranking/profile`

Returns `{required,status:"NOT_REQUIRED|REQUESTED|SUBMITTED",submitted_at}`. Private contact values are never returned after submission.

### `POST /api/ranking/profile`

Body `{name,contact,school,event_id}`. Available only while the participant is a provisional TOP3 entrant. Creates a `RANKING` manual claim whose private synthetic contact is stored once in the claim contact area, then returns `{status:"SUBMITTED",submitted_at,claim_id}`; replay updates nothing and returns the original result.

## One draw per campaign/participant

### `GET /api/draws/me`

Returns `{status:"LOCKED|AVAILABLE|DRAWN",eligible_session_id?,draw?}`. `draw` includes `{draw_id,pouch_index,is_won,prize:{id,name,category,image_url},revealed,scratch_completed,claim_id?}`.

### `POST /api/draws`

Body `{pouch_index,event_id}` where pouch is 0–2. Requires one verified finish. Atomically creates or returns the campaign/participant draw, fixes the result once, and reserves inventory. Returns the same `draw` object with `201` or `200` on replay/previous draw.

### `PATCH /api/draws/{id}/scratch-complete`

Body `{event_id}`. Marks reveal completion idempotently and returns `{draw_id,scratch_completed:true,claim_id?}`.

## Claims and manual payout

### `GET /api/claims`

Returns participant-owned claim summaries only: `{claims:[{id,type:"DRAW|RANKING",prize_name,category,status,created_at,contact_submitted}]}`. No coupon codes are generated or exposed.

### `POST /api/claims/{id}/submit`

Body `{name,contact,school?,address?,event_id}`. Stores private contact separately from analytics and returns `{id,status:"INFORMATION_RECEIVED",submitted_at}`.

Manual states are `INFORMATION_RECEIVED`, `PENDING_REVIEW`, `CONTACTED`, `PAID`, `ON_HOLD`, `INELIGIBLE`, `NO_RESPONSE`. Contact and actual payment are distinct transitions.

## Analytics

### `POST /api/events/batch`

Body `{events:[{event_id,name,occurred_at,screen,screen_view_id?,visit_session_id?,game_session_id?,observation_id?,active_ms?,dimensions?}]}`. `screen_view_id` is a fresh opaque ID for each screen entry, so repeated visits to the same screen remain distinct. Returns `{accepted,duplicates,rejected}`. Allowed names/dimensions are server allowlisted. Tokens, contact data, coupon data, full URLs/query strings, arbitrary payload keys and free-form PII are rejected. Participant linkage comes only from the cookie; pre-auth observations remain explicitly unlinked until server-side linking.

Server-domain events (grant, consume, refund, verified finish, draw, claim/admin transition) are written by their business transaction and cannot be forged through this endpoint.

## Administrator APIs

The frontend signs into Supabase Auth directly using `/api/config` public Auth values. Administrator requests send `Authorization: Bearer <Supabase access token>`. Each request calls the real Supabase `/auth/v1/user` endpoint, then opens a new DB connection and checks `dino_dev.admin_member`. The server must not hold a DB connection during the external Auth call.

### `GET /api/admin/session`

Returns `{authenticated:true,admin:{user_id,display_name,permissions}}` after Auth and membership checks.

### `GET /api/admin/overview?from=&to=&environment=&link_kind=&channel=&content=&won=`

Returns refreshed-at/observation-window metadata, numerator, denominator, unique participants, event count and `estimated` flags for each metric. Includes loading pre-auth/unlinked cohorts, game/referral/draw/claim funnels, active-time buckets, and ordered exposure CTR. CTR is `|V∩C_after_exposure| / |V|`; zero exposure returns `rate:null`.

### `GET /api/admin/claims?status=&type=&assignee=&limit=&cursor=`

Returns private claim work items only to `claims:read` members, including assignee, hold reason, contact/paid timestamps and optimistic `version`.

### `PATCH /api/admin/claims/{id}`

Body `{status?,assignee_user_id?,reason?,external_delivery?,verification_status?,verification_reference?,expected_version,event_id}`. `verification_reference` is an opaque synthetic `TEST_REF_*` reference only; Phase 1 accepts no real proof upload. Claim, inventory and audit updates are atomic. Version mismatch returns `409 VERSION_CONFLICT`; replay never increments payout/inventory counts twice.

`RANKING` claims may progress through review and contact, but `PAID` returns `409 FINAL_RANKING_UNDECIDED` while the only available ranking snapshot is `DRAFT` with `tie_policy:"UNDECIDED"`. `DRAW` claims keep the normal manual payment transition.

### `GET /api/admin/analytics/events?...`

Returns allowlisted diagnostic event rows without contact data or authentication secrets. Requires `analytics:read`.

### `GET /api/admin/game-faults?status=PENDING`

Returns bounded fault review work items. Requires `faults:read`.

### `PATCH /api/admin/game-faults/{session_id}`

Body `{decision:"APPROVE|DENY",reason,expected_version,event_id}`. Requires `faults:write`. Approval refunds the original ticket kind exactly once; denial closes the unfinished session without a refund. Version mismatch returns `409 VERSION_CONFLICT`, and every decision is audited.

### `PATCH /api/admin/campaign`

Body `{status:"ACTIVE|PAUSED|ENDED",expected_version,event_id}`. Returns updated status/version. Production enablement is rejected by configuration in Phase 1.

### `GET /api/admin/ranking-contacts`

Requires `claims:read`. Returns requested and submitted provisional TOP3 work items, with synthetic contact values only for submitted `RANKING` claims. It does not declare final winners.

### `GET|POST /api/admin/ranking-snapshots`

Requires `ranking:read` or `ranking:write`. POST captures an immutable `DRAFT` score/tie/contact-status snapshot with `tie_policy:"UNDECIDED"` and `final_awards_created:false`. Phase 1 exposes no finalization operation while D03/D04/D10 remain undecided.

### `PATCH /api/admin/participants/{id}`

Body `{status:"ACTIVE|BLOCKED",expected_status,revoke_session,reason,event_id}`. Requires `participants:write`. Blocking and token expiry are independently explicit and every change is audited; an expired token is not silently reissued.
