-- RecoveryPact demo database initialization
-- Separate least-privilege roles for app, observation, and remediation.

CREATE EXTENSION IF NOT EXISTS pg_stat_statements;

DO $$
BEGIN
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'checkout') THEN
    CREATE ROLE checkout LOGIN PASSWORD 'checkout';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'observer') THEN
    CREATE ROLE observer LOGIN PASSWORD 'observer';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'remediator') THEN
    CREATE ROLE remediator LOGIN PASSWORD 'remediator';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'batch_worker') THEN
    CREATE ROLE batch_worker LOGIN PASSWORD 'batch_worker';
  END IF;
  IF NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'settlement_worker') THEN
    CREATE ROLE settlement_worker LOGIN PASSWORD 'settlement_worker';
  END IF;
END
$$;

GRANT CONNECT ON DATABASE checkout TO checkout, observer, remediator, batch_worker, settlement_worker;

-- Application schema
CREATE TABLE IF NOT EXISTS products (
  product_id   SERIAL PRIMARY KEY,
  sku          TEXT UNIQUE NOT NULL,
  name         TEXT NOT NULL,
  price_cents  INTEGER NOT NULL CHECK (price_cents > 0),
  stock        INTEGER NOT NULL CHECK (stock >= 0)
);

CREATE TABLE IF NOT EXISTS inventory_locks (
  sku          TEXT PRIMARY KEY REFERENCES products(sku),
  reserved     INTEGER NOT NULL DEFAULT 0,
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS orders (
  order_id     UUID PRIMARY KEY,
  customer_id  TEXT NOT NULL,
  sku          TEXT NOT NULL REFERENCES products(sku),
  qty          INTEGER NOT NULL CHECK (qty > 0),
  total_cents  INTEGER NOT NULL,
  status       TEXT NOT NULL DEFAULT 'PENDING',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS checkout_events (
  event_id     BIGSERIAL PRIMARY KEY,
  order_id     UUID,
  customer_id  TEXT,
  sku          TEXT,
  outcome      TEXT NOT NULL,
  latency_ms   DOUBLE PRECISION,
  error        TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE IF NOT EXISTS batch_jobs (
  job_id       SERIAL PRIMARY KEY,
  job_name     TEXT NOT NULL,
  workload_class TEXT NOT NULL DEFAULT 'BATCH_REPLAYABLE',
  status       TEXT NOT NULL DEFAULT 'PENDING',
  started_at   TIMESTAMPTZ,
  finished_at  TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS settlement_ledger (
  settlement_id UUID PRIMARY KEY,
  amount_cents  INTEGER NOT NULL,
  status        TEXT NOT NULL DEFAULT 'IN_PROGRESS',
  protected     BOOLEAN NOT NULL DEFAULT TRUE,
  started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at   TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS audit_log (
  audit_id     BIGSERIAL PRIMARY KEY,
  actor        TEXT NOT NULL,
  action       TEXT NOT NULL,
  details      JSONB NOT NULL DEFAULT '{}',
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Seed catalog
INSERT INTO products (sku, name, price_cents, stock) VALUES
  ('SKU-WIDGET-01', 'Continuity Widget', 2499, 1000),
  ('SKU-GADGET-02', 'Recovery Gadget', 4999, 500),
  ('SKU-RELAY-03', 'Pact Relay', 1299, 2000)
ON CONFLICT (sku) DO NOTHING;

INSERT INTO inventory_locks (sku, reserved)
SELECT sku, 0 FROM products
ON CONFLICT (sku) DO NOTHING;

-- Privileges
GRANT USAGE ON SCHEMA public TO checkout, observer, remediator, batch_worker, settlement_worker;

GRANT SELECT, INSERT, UPDATE ON products, inventory_locks, orders, checkout_events, batch_jobs
  TO checkout;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO checkout;

GRANT SELECT ON ALL TABLES IN SCHEMA public TO observer;
GRANT SELECT ON pg_stat_activity TO observer;
-- observer needs pg_locks / activity visibility
GRANT pg_read_all_stats TO observer;

-- remediator: ONLY terminate backends belonging to allowlisted roles (enforced in app + grants)
GRANT pg_signal_backend TO remediator;
GRANT SELECT ON pg_stat_activity TO remediator;
GRANT SELECT ON products, inventory_locks, orders, batch_jobs, settlement_ledger TO remediator;
GRANT INSERT ON audit_log TO remediator;
GRANT USAGE, SELECT ON SEQUENCE audit_log_audit_id_seq TO remediator;

GRANT SELECT, INSERT, UPDATE ON batch_jobs, inventory_locks, products TO batch_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO batch_worker;

GRANT SELECT, INSERT, UPDATE ON settlement_ledger, inventory_locks, products TO settlement_worker;
GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO settlement_worker;

-- Mark application_name conventions used by workload classification
COMMENT ON TABLE batch_jobs IS 'Replayable batch workloads; eligible for TERMINATE_BACKEND when allowlisted';
COMMENT ON TABLE settlement_ledger IS 'Protected financial settlements; NEVER eligible for autonomous termination';
