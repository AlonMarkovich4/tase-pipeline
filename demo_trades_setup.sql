-- Demo Paper Trading tables for TA-35 Arena
-- Run this in Supabase SQL Editor

-- Each demo trade = one strategy (multiple legs stored as JSONB)
CREATE TABLE IF NOT EXISTS demo_trades (
    id              BIGSERIAL PRIMARY KEY,
    trade_id        TEXT NOT NULL UNIQUE,          -- UUID-style identifier
    created_at      TIMESTAMPTZ DEFAULT now(),
    strategy_name   TEXT,                          -- e.g. "Iron Condor", "Custom"
    expiry_date     TEXT,                          -- YYYY-MM-DD
    status          TEXT DEFAULT 'open',           -- open / closed
    legs            JSONB NOT NULL,                -- array of leg objects
    entry_index     NUMERIC,                       -- TA-35 index at entry
    net_premium_pts NUMERIC,                       -- net premium in points
    max_profit_ils  NUMERIC,
    max_risk_ils    NUMERIC,
    settlement_index NUMERIC,                      -- filled on close
    pnl_ils         NUMERIC DEFAULT 0,             -- filled on close
    close_reason    TEXT,                           -- 'expiry_settlement' / 'manual_close'
    closed_at       TIMESTAMPTZ
);

-- Running balance tracker
CREATE TABLE IF NOT EXISTS demo_balance (
    id              BIGSERIAL PRIMARY KEY,
    updated_at      TIMESTAMPTZ DEFAULT now(),
    balance         NUMERIC NOT NULL DEFAULT 100000,  -- start with 100,000 ₪
    change_amount   NUMERIC DEFAULT 0,
    change_reason   TEXT                              -- 'trade_open', 'trade_close', 'reset'
);

-- Insert initial balance if table is empty
INSERT INTO demo_balance (balance, change_reason)
SELECT 100000, 'initial_balance'
WHERE NOT EXISTS (SELECT 1 FROM demo_balance LIMIT 1);

CREATE INDEX IF NOT EXISTS idx_demo_trades_status ON demo_trades (status);
CREATE INDEX IF NOT EXISTS idx_demo_trades_expiry ON demo_trades (expiry_date);
