# Phase 2 Dino Jump v2 game rules

Effective 2026-09-25 for the local Preview/test implementation. The values below are the adopted and tested `2.0.0` replay contract. They are not approval of final event prizes, dates, eligibility, publicity, or production launch. The frozen machine-readable gameplay source is `shared/game_constants_v2.json`; the browser and server verifier must remain equivalent to its deterministic rules. Server lifecycle timing is defined by `server/operations.py`.

## Version and lifecycle

- Game version: `2.0.0`.
- Deterministic clock: 60 ticks per second.
- Play limit: 36,000 ticks, exactly 600 seconds.
- A reservation expires after 2 minutes if it is not started.
- Starting a v2 session replaces the expiry with 720 seconds from `started_at`: 600 seconds of playable time plus 120 seconds for pauses, countdown, replay verification, and result submission.
- A verified collision ends with `end_reason="COLLISION"`. Reaching tick 36,000 without a terminal collision is a valid `end_reason="TIME_LIMIT"` finish.
- Scores and ranks are scoped to the game version. v2 writes `versioned_best_score(game_version='2.0.0')`; it does not overwrite the legacy `1.2.0` best-score table.

The current and frozen v2 constants both set `ticketReservationTtlSec: 120`, matching the implemented 2-minute server reservation. Session creation still uses the authoritative server timestamp returned as `expires_at`.

## Physics and stages

The logical canvas is 960×600 with ground Y at 490. The dino starts at X 120, size 64×72, with hitbox offset `(10,8)` and size 44×58. Gravity is 2,200 px/s². A low jump starts at -680 px/s. A high jump applies -720 px/s at the sixth tick after jump start. The hold threshold is 6 ticks/100 ms and the input buffer is 100 ms.

| Stage | Time | Speed | Minimum ordinary interval |
|---|---:|---:|---:|
| 1 | 0–15 s | 390→450 px/s | 0.95 s |
| 2 | 15–30 s | 450→530 px/s | 0.88 s |
| 3 | 30–45 s | 530→620 px/s | 0.80 s |
| 4 | 45–60 s | 620→710 px/s | 0.74 s |
| 5 | 60–75 s | 710→800 px/s | 0.68 s |
| 6 | 75 s onward | +4 px/s² from 800, capped at 880 at 95 s | 0.62 s |

Obstacle availability is weighted by repeated indices. Before 15 seconds it is `[small,small,small,tall,double]`; from 15 to 30 seconds it is `[small,tall,double,small,tall]`; from 30 seconds it is `[small,tall,double,bird_low,bird_high,small,bird_low]`. Each obstacle spawn draws type, combo roll, then gap-extra from the obstacle PRNG. A nonconsecutive combo uses probability 0.35 and a gap of `0.68–0.80 s`, or `0.88–1.00 s` after tall/double cactus. An ordinary gap is the stage minimum plus `0–0.45 s`; the ordinary gap after a combo is at least 1.15 seconds.

## Coins, hearts, and repeated revives

- Base score: `floor(ticks / 60 × 10)`.
- Coin value: 10 points. Final score is base score plus `coins × 10`.
- The verifier and database accept scores from 0 through 9,000. With the adopted minimum coin interval, at most 299 coin spawns fit before the 36,000-tick limit, so the reachable formula remains below that defensive cap.
- First coin: tick 180 (3 seconds). Later coin intervals: an inclusive uniform integer from 120 through 240 ticks (2–4 seconds).
- First heart: tick 1,200 (20 seconds). Later heart intervals: an inclusive uniform integer from 1,500 through 2,100 ticks (25–35 seconds).
- Stored heart capacity: one. Collecting another heart while full increments the collected-heart summary, but neither stacks another revive nor awards bonus score.
- A collision with a stored heart consumes it and continues the same session. There is no per-session revive-count limit; another collected heart can enable another revive.
- Revive protection lasts 90 ticks (1.5 seconds). The visual revive overlay lasts 24 ticks (0.4 seconds) and has no scoring authority.
- A collision without a stored heart ends the game. Client-supplied coin, heart, or revive flags are ignored; the server derives the summary by replay.

The verified summary is `{coins, coin_score, hearts, revives}`. `hearts` is total hearts collected, while the transient stored-heart value remains 0 or 1.

## PRNG streams and exact tick order

All streams use the 32-bit LCG `state = state × 1664525 + 1013904223 (mod 2^32)` and return the high 24 bits divided by `2^24`.

- Obstacles use the session seed.
- Coins use `seed XOR 0xC01DC0DE`.
- Hearts use `seed XOR 0x1EA7BEEF`.

Each simulation tick runs in this order:

1. Read the jump input, apply buffered/high-jump state, then integrate dino velocity and position.
2. If the floating obstacle time is due, draw obstacle type, place the obstacle, then draw combo and gap values.
3. If `tick === nextCoinTick`, place one coin, then draw and add the next inclusive coin interval.
4. If `tick === nextHeartTick`, place one heart, then draw and add the next inclusive heart interval.
5. Move items, collect overlapping items, and remove offscreen items.
6. Move obstacles, then resolve collision, heart consumption, revive protection, or terminal collision.
7. Increment the tick only when there was no terminal collision; after the increment, tick 36,000 becomes `TIME_LIMIT`.
8. Recalculate score from the authoritative end/current tick and collected coins.

Spawn clearance is 24 logical pixels and is deterministic. A new obstacle is shifted right until it has at least 24 px horizontal clearance from every vertically overlapping live item. A coin or heart is then shifted right until it has the same clearance from every vertically overlapping live obstacle. Because obstacle spawning precedes coin and heart spawning, same-tick items see the newly spawned obstacle. Coins are processed before hearts. Items do not displace each other. New entities still move during that tick. Item collection precedes obstacle collision, so a heart collected on the collision tick can be consumed by that collision.

Changing any seed mask, draw order, spawn order, clearance rule, interval bound, physics value, hitbox, or scoring rule requires a new game version and matching browser/server fixtures.

## Finish verification

The finish request sends `version`, `end_reason`, `score`, `ticks`, `jump_ticks`, optional checkpoints, and the client summary. The server selects the verifier by the session's stored version and rejects a mismatched body version. For v2 it replays the stored seed and jump inputs, calculates items, revives, end reason, ticks, score, and summary, and stores only the server result. Submitted score is bounded to 0–9,000; submitted ticks are bounded to 0–36,000; jump input is bounded to 4,096 records. A finish also fails when its simulated duration exceeds observed wall-clock duration plus one second.

## Same-session resume

The browser stores a PII-free `sessionStorage` snapshot under `dino_snapshot_<session_id>`:

```json
{"sessionId":"gs_...","version":"2.0.0","seed":41,"tick":2200,"jumpTicks":[{"tick":120,"high":true}]}
```

It writes tick zero after reservation, then refreshes the snapshot at checkpoints, `pagehide`, and view cleanup. This is same-browser-session recovery, not cross-device persistence and not server authority.

Before showing resume, the client fetches the owner-only session and requires all of the following:

- server status is `ACTIVE` or `RESERVED`;
- server and snapshot versions are exactly `2.0.0`;
- session ID and seed match;
- snapshot tick is an integer from 0 through 35,999 and is at least `last_checkpoint_tick`;
- a `RESERVED` session has tick zero;
- jump ticks are sorted, unique integers below the snapshot tick and each `high` value is boolean;
- `expires_at` is present and still in the future.

The engine creates a fresh v2 simulation and replays without rendering until the saved tick. It restores score, stage, coins, total hearts, stored heart, revives, and the original server expiry, then resumes after the countdown. The final server verifier still replays the entire session.

If the snapshot is absent, malformed, stale, legacy, mismatched, expired, or cannot replay exactly, the client removes it and explicitly refuses to restart the active session at tick zero. It leaves the session to the existing expiry/fault recovery path. A stored finish response retry and a stored fault marker take precedence over ordinary resume.

## Ranking and provisional TOP3

- Ranking uses dense score rank within the active campaign and game version. Equal scores share a rank.
- Private leaderboard names are omitted from the public list, while their valid scores still participate in rank and the third-place threshold.
- `top3_gap.status` is `IN_TOP3`, `TOO_FEW`, `NO_SCORE`, or `CHASING`, with `third_score`, `score_needed`, `rank`, `tied`, and `participant_count`.
- `ranking_contact.game_version` is the latest-version pointer used by participant UI. A prior submitted contact keeps its submitted status; a later verified v2 TOP3 finish advances that pointer to `2.0.0` without requesting duplicate contact.
- `ranking_contact_version(participant_id,game_version,qualified_at)` independently retains every version for which the participant qualified. A `BEFORE INSERT OR UPDATE OF game_version` trigger records the association before the reusable contact pointer is inserted or advanced. This also captures a legacy Preview's attempted `1.2.0` insert even when its `ON CONFLICT DO NOTHING` leaves an existing v2 pointer unchanged. Metrics and ranking snapshots use the association table for version provenance.
- TOP3 is provisional. Final tie awards and winner settlement remain undecided and no ID/order tiebreak declares a winner.

## Share and retry-ticket rule

`record_share`, `prize_share`, and `retry_invite` create distinct public attribution/link purposes but use the same invitation qualification rule. A share action or preview fetch never grants a ticket. A valid participant visit must supply the invite code, pass active-time and interaction checks, and qualify through the normal invitation endpoint. The campaign+inviter+visitor pair is deduplicated across all share purposes; self-invites, balance cap 3, and the 10-hour cooldown remain common.

Public cards may use only an opted-in public nickname, the version-scoped score, and a revealed public prize name. Contact, claim, authentication, and private redemption data are never joined. Preview rendering is read-only and cannot create a visit, ledger entry, or reward.

## Phase 3 boundaries

The v2 mechanics and D14 reward behavior are adopted for this test implementation. Phase 3 still owns final campaign dates, real prizes/stock/odds/budget, tie and split-award policy, student/Gemini proof, deadlines and alternate-winner rules, personal-data retention/notice/consent, official content/benefit URLs, operator contacts, production enablement, and final public event approval.
