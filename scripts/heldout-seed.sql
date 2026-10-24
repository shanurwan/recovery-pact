-- Held-out round: the business records for the new workloads (evals/heldout/README.md).
-- Idempotent: safe to run on a live continuity database.
\connect continuity

INSERT INTO workload_registry VALUES
  ('batch_replayable_search_reindex', 'search_reindex', 'search-platform', 'BATCH_REPLAYABLE',
   TRUE, 3, 1200, 'may_interrupt',
   'Rebuilds the product search index. Resumes from its last checkpoint.'),
  ('protected_payout_batch', 'merchant_payout', 'payments', 'PROTECTED_SETTLEMENT',
   FALSE, NULL, 40, 'never_interrupt',
   'Merchant payout batch. Interrupting mid-flight risks paying merchants twice or not at all.'),
  ('batch_replayable_loyalty_accrual', 'loyalty_accrual', 'loyalty', 'BATCH_REPLAYABLE',
   TRUE, 30, 1800, 'may_interrupt',
   'Accrues loyalty points from yesterday''s orders. A restart recomputes the day.'),
  ('batch_replayable_order_export', 'order_export', 'order-ops', 'BATCH_REPLAYABLE',
   TRUE, 1, 600, 'may_interrupt',
   'Exports new orders to the fulfilment partner. Idempotent.')
ON CONFLICT (application_name) DO NOTHING;

INSERT INTO escalation_contacts VALUES
  ('search-platform', 'search on-call', '#search-oncall'),
  ('loyalty', 'loyalty programme lead', '#loyalty'),
  ('order-ops', 'order operations on-call', '#order-ops')
ON CONFLICT (owner_team) DO NOTHING;
