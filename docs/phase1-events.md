# Phase 1 event and metric dictionary

Client observations use `POST /api/events/batch`. Business outcomes such as ticket grant/consume/refund, verified finish, draw creation, inventory reservation, claim creation and administrator state transition are server events written inside their business transaction. A browser cannot forge those outcomes.

## Envelope

Every client event contains `event_id`, `name`, `occurred_at`, logical `screen`, per-entry `screen_view_id`, `visit_session_id`, and the pre-auth `observation_id`. `game_session_id` is present only when relevant, while `active_ms` is the cumulative visible time for the current screen view. Participant linkage is derived from the HttpOnly cookie on the server. The browser payload never contains participant IDs, invite codes, authentication values, contact data, full URLs, arbitrary query strings, or prize secrets.

Allowed dimensions are: `previous_screen`, `source`, `link_kind`, `channel`, `campaign_code`, `content`, `position`, `action`, `status`, `reason`, `stage`, `bucket`, `result_type`, `prize_kind`, `share_method`, `checkpoint`, `is_new`, `is_synthetic`, `connected`, `observed`, `score`, `rank`, `game_version`, `draw_status`, `claim_type`, `share_id`.

`share_id` is an opaque attribution identifier, 8–128 characters from `[A-Za-z0-9:_-]`, also stored on observations and invitation visits. It is not a credential or an invitation code. Invitation reward deduplication remains campaign + inviter + visitor; a new share identifier cannot earn the same reward twice.

The landing parser accepts only the named attribution query values used by this campaign: `invite`, `share`, `link=initial|prize_share`, `channel`, and `campaign`. It validates each value, records only the mapped fields, and removes the query from the visible address before participant initialization. It never copies an arbitrary URL or query string into analytics.

`visit_session_id` identifies the browser visit. The envelope `screen_view_id` changes on each logical screen entry, including repeated visits to the same screen. Screen-scoped events carry cumulative visible `active_ms` for that view so step durations can be derived without counting hidden time.

## Client event names

| Event | Meaning |
| --- | --- |
| `entry_viewed` | Script began before participant initialization. |
| `participant_ready` | Cookie participant initialization or restore finished. This is not the visible loading completion time. |
| `loading_ready` | Participant state refresh and the first logical screen render finished, immediately before the splash leaves. A following `screen_entered` is also a fallback ready signal. |
| `loading_checkpoint` | Bounded active time checkpoint during loading/non-game screens. |
| `screen_entered`, `screen_left` | Logical screen entry/exit and active time. |
| `game_cta_clicked`, `game_start_approved` | Start intent and server-approved game start. |
| `game_checkpoint`, `game_completed` | Bounded game progress and stage observation, followed by a verified completion shown in browser. |
| `game_fault_reported`, `game_recovered` | Client fault request and reconnect recovery result. A small session-only marker preserves only session ID, reason, tick and retry ID; normal exit does not create it. |
| `ranking_viewed` | Ranking displayed/requested. |
| `top3_profile_started`, `top3_profile_submitted` | Provisional TOP3 contact funnel. |
| `invite_cta_viewed`, `share_attempted` | Invite CTA exposure and share/copy status. Copy success is recorded only after the clipboard write succeeds. Native share records attempted, cancelled, failed, or share-sheet-closed and never claims that a message was delivered. |
| `invite_visit_interacted`, `invite_visit_qualified`, `invite_visit_rejected` | Visible 3-second visit interaction and server decision shown to the visitor. |
| `draw_entered`, `pouch_selected` | Draw funnel entry and presentation choice. Choice does not determine probability. |
| `scratch_started`, `scratch_completed`, `draw_result_viewed` | Browser reveal funnel, separate from the earlier server draw decision. `scratch_completed` is emitted only after the server accepts the stable retry key; revisiting an already revealed result emits only the view event for that screen entry. |
| `claim_form_started`, `claim_form_submitted` | Synthetic Preview claim contact funnel. |
| `benefit_viewed`, `gemini_cta_viewed`, `gemini_cta_clicked` | Ordered Gemini exposure and click funnel. Click is not registration. Benefit link copy/native-share observations reuse `share_attempted` with `source=gemini`; actual delivery remains unknown. |
| `content_clicked`, `notion_redirect_requested` | Approved content/outbound intent. The Notion redirect remains disabled until approved. |

## Metric definitions

- Loading drop estimate: observations with no later `loading_ready` or next-screen event after the observation window. `participant_ready` remains an earlier API milestone. Browser termination can omit the final event, so the dashboard labels this estimated.
- Game completion rate: unique approved game starts with a verified finish divided by unique approved game starts. Normal collision is completion; fault, expiration and verification rejection have distinct server statuses.
- Draw selection rate: participants with `pouch_selected` divided by participants with `draw_entered`. Server draw creation and actual result remain authoritative.
- Claim submission rate: unique submitted claim forms divided by eligible winning claims, excluding non-winners.
- Invite validity: rewarded server decisions divided by fresh qualification attempts. Cooldown/full/duplicate/self/invalid nonce are separate reasons.
- Gemini CTR: unique participant set `V` with `gemini_cta_viewed` and set `C` that clicked after exposure during the observation window; rate is `|V∩C| / |V|`. When `|V|=0`, the rate is null and the UI displays “계산 대상 없음.”
- Direct Gemini clicks are deduplicated by participant. An approved routed path would require its own accepted click event and ordered exposure contract before it may join the union; the unapproved Notion path remains disabled and contributes zero. Guide clicks alone are not conversion.
- Every dashboard metric displays numerator, denominator, unique participant count, event count, observation window, refresh time and whether it is an original count or estimate. A field that has no meaningful unit is shown as “해당 없음” rather than a fabricated count.
- Sharing reports the selected method and the last client-observable status. `actual_delivery` remains `unknown`; closing a native share sheet does not prove delivery to a recipient.
- Invitation performance reports server ticket grants and later invitation-ticket use inside the selected period. Its use/grant ratio is a same-period operational ratio, not a per-person causal conversion rate. Cooldown reacquisition and later participation remain separate counts.
- Game progress groups owned sessions by the last observed stage and active screen time. Missing active checkpoints are shown as unknown and are not replaced with wall-clock duration. Unlinked checkpoint events remain a separate count.
- Content rows separate approved guide clicks from outbound redirect requests and show linked participants and unlinked events separately. No external page view or dwell is inferred.

Synthetic and Preview data carry `is_synthetic=true` or the environment dimension and are excluded from later Production reporting by default.

The dashboard's `won` filter is explicitly a campaign-lifetime draw-prize cohort filter. The selected period still scopes displayed events and state changes; it does not redefine whether that participant has ever received a winning draw in the campaign.
