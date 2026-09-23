-- Query-driven indexes only. The remaining FK advisor INFO items are covered
-- by leading UNIQUE indexes, tiny immutable configuration tables, or have no
-- reverse lookup/delete path in Phase 1.

create index best_score_rank_idx
  on dino.best_score(score desc, achieved_at, participant_id);

create index claim_ready_expiry_idx
  on dino.claim(expires_at, id)
  include(participant_id, inventory_item_id)
  where status = 'READY';

create index prize_campaign_active_idx
  on dino.prize(campaign_id, is_active, is_test, id);
