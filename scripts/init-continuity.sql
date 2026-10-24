-- Business system of record ("continuity" database), separate from the checkout
-- database. RecoveryPact never reads it directly in live mode: Zetaris federates it
-- together with the change-calendar CSV and the checkout event stream.

CREATE DATABASE continuity;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'zetaris_reader') THEN
    CREATE ROLE zetaris_reader LOGIN PASSWORD 'zetaris_reader';
  END IF;
END
$$;
ALTER ROLE zetaris_reader SET default_transaction_read_only = on;
ALTER ROLE zetaris_reader SET statement_timeout = '5s';

-- The federation login may read live checkout signals, nothing else.
GRANT CONNECT ON DATABASE checkout TO zetaris_reader;
GRANT SELECT ON checkout_events, settlement_ledger TO zetaris_reader;

\connect continuity

-- Which workload owns a database session, and what interrupting it costs the business.
CREATE TABLE workload_registry (
  application_name    TEXT PRIMARY KEY,
  job_name            TEXT NOT NULL,
  owner_team          TEXT NOT NULL,
  workload_class      TEXT NOT NULL,
  replayable          BOOLEAN NOT NULL,
  replay_cost_minutes INTEGER,
  typical_runtime_s   INTEGER,
  interrupt_policy    TEXT NOT NULL,
  business_purpose    TEXT NOT NULL
);

INSERT INTO workload_registry VALUES
  ('batch_replayable_inventory', 'inventory_reconcile', 'inventory-platform', 'BATCH_REPLAYABLE',
   TRUE, 4, 900, 'may_interrupt',
   'Nightly stock reconciliation. Idempotent; resumes from its last checkpoint.'),
  ('batch_replayable_price_sync', 'price_sync', 'pricing', 'BATCH_REPLAYABLE',
   TRUE, 2, 600, 'may_interrupt',
   'Syncs supplier prices into the catalog. Idempotent.'),
  ('batch_replayable_month_end_close', 'inventory_month_end_close', 'finance-ops', 'BATCH_REPLAYABLE',
   TRUE, 95, 3600, 'may_interrupt',
   'Inventory valuation feeding the financial close. Restart recomputes from scratch.'),
  ('protected_settlement', 'card_settlement', 'payments', 'PROTECTED_SETTLEMENT',
   FALSE, NULL, 45, 'never_interrupt',
   'Card settlement batch. Interrupting mid-flight risks double charges or lost settlements.'),
  ('checkout_api', 'checkout', 'storefront', 'CHECKOUT',
   FALSE, NULL, NULL, 'never_interrupt',
   'Customer-facing checkout.');

-- What "the business is back" means for each customer-facing service.
CREATE TABLE service_slo (
  service                  TEXT PRIMARY KEY,
  slo_success_rate         NUMERIC(5,4) NOT NULL,
  slo_p95_ms               INTEGER NOT NULL,
  verification_window_s    INTEGER NOT NULL,
  revenue_per_minute_cents INTEGER NOT NULL,
  -- How long the business tolerates degraded checkout while waiting for a blocker.
  max_degradation_s        INTEGER NOT NULL,
  tier                     TEXT NOT NULL
);

INSERT INTO service_slo VALUES
  ('checkout', 0.9500, 1500, 10, 1840000, 60, 'tier-1');

CREATE TABLE escalation_contacts (
  owner_team TEXT PRIMARY KEY,
  oncall     TEXT NOT NULL,
  channel    TEXT NOT NULL
);

INSERT INTO escalation_contacts VALUES
  ('inventory-platform', 'inventory on-call', '#inv-oncall'),
  ('pricing', 'pricing on-call', '#pricing-oncall'),
  ('finance-ops', 'finance close lead', '#finance-close'),
  ('payments', 'payments on-call', '#payments-oncall'),
  ('storefront', 'storefront on-call', '#storefront-oncall');

-- Held-out round (evals/heldout/README.md); also in scripts/heldout-seed.sql for live databases.
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

GRANT CONNECT ON DATABASE continuity TO zetaris_reader;
GRANT USAGE ON SCHEMA public TO zetaris_reader;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO zetaris_reader;
-- The local fallback reads through the observer role.
GRANT CONNECT ON DATABASE continuity TO observer;
GRANT USAGE ON SCHEMA public TO observer;
GRANT SELECT ON ALL TABLES IN SCHEMA public TO observer;
