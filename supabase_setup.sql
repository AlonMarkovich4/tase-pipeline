-- =====================================================================
-- TASE TA-35 Iron Condor Pipeline — Supabase Schema (IDEMPOTENT)
-- =====================================================================
-- This file is SAFE to run multiple times.  Never drops existing tables.
-- All column names are lowercase to match the Python code expectations.
--
-- Run it in Supabase Dashboard → SQL Editor when:
--   - Setting up a new Supabase project from scratch
--   - Adding new columns/indexes after a code update
-- =====================================================================


-- ---------------------------------------------------------------------
-- TABLE 1: tase_putcall  (live snapshot — current cycle only)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tase_putcall (
    id                                  BIGSERIAL PRIMARY KEY,
    fetch_date                          TEXT,
    fetch_time                          TEXT,
    expiry_date                         TEXT,
    trade_date                          TEXT,

    rowtype                             TEXT,
    drvtype                             TEXT,

    derivativeid_call                   TEXT,
    derivativename_call                 TEXT,
    expirationprice_call                NUMERIC,
    expirationdate_call                 TEXT,
    delta_call                          NUMERIC,
    lastrate_call                       NUMERIC,
    baserate_call                       NUMERIC,
    lowrate_call                        NUMERIC,
    highrate_call                       NUMERIC,
    dealsno_call                        INTEGER,
    overallturnoverunits_call           NUMERIC,
    turnovervolume_derivative_call      NUMERIC,
    overallturnovervalue_shekel_call    NUMERIC,
    openpositions_call                  NUMERIC,
    positionchange_call                 NUMERIC,
    curr_hour_call                      TEXT,
    underlingasset_call                 NUMERIC,

    derivativeid_put                    TEXT,
    derivativename_put                  TEXT,
    expirationprice_put                 NUMERIC,
    expirationdate_put                  TEXT,
    delta_put                           NUMERIC,
    lastrate_put                        NUMERIC,
    baserate_put                        NUMERIC,
    lowrate_put                         NUMERIC,
    highrate_put                        NUMERIC,
    dealsno_put                         INTEGER,
    overallturnoverunits_put            NUMERIC,
    turnovervolume_derivative_put       NUMERIC,
    overallturnovervalue_shekel_put     NUMERIC,
    openpositions_put                   NUMERIC,
    positionchange_put                  NUMERIC,
    curr_hour_put                       TEXT,
    underlingasset_put                  NUMERIC,

    fetched_at                          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_tase_fetch_date
    ON tase_putcall (fetch_date);
CREATE INDEX IF NOT EXISTS idx_tase_expiry_date
    ON tase_putcall (expiry_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_tase_upsert
    ON tase_putcall (fetch_date, fetch_time, expiry_date,
                     derivativeid_call, derivativeid_put);


-- ---------------------------------------------------------------------
-- TABLE 2: tase_putcall_history  (archive — copy of live at end of day)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS tase_putcall_history (
    id                                  BIGSERIAL PRIMARY KEY,
    fetch_date                          TEXT,
    fetch_time                          TEXT,
    expiry_date                         TEXT,
    trade_date                          TEXT,

    rowtype                             TEXT,
    drvtype                             TEXT,

    derivativeid_call                   TEXT,
    derivativename_call                 TEXT,
    expirationprice_call                NUMERIC,
    expirationdate_call                 TEXT,
    delta_call                          NUMERIC,
    lastrate_call                       NUMERIC,
    baserate_call                       NUMERIC,
    lowrate_call                        NUMERIC,
    highrate_call                       NUMERIC,
    dealsno_call                        INTEGER,
    overallturnoverunits_call           NUMERIC,
    turnovervolume_derivative_call      NUMERIC,
    overallturnovervalue_shekel_call    NUMERIC,
    openpositions_call                  NUMERIC,
    positionchange_call                 NUMERIC,
    curr_hour_call                      TEXT,
    underlingasset_call                 NUMERIC,

    derivativeid_put                    TEXT,
    derivativename_put                  TEXT,
    expirationprice_put                 NUMERIC,
    expirationdate_put                  TEXT,
    delta_put                           NUMERIC,
    lastrate_put                        NUMERIC,
    baserate_put                        NUMERIC,
    lowrate_put                         NUMERIC,
    highrate_put                        NUMERIC,
    dealsno_put                         INTEGER,
    overallturnoverunits_put            NUMERIC,
    turnovervolume_derivative_put       NUMERIC,
    overallturnovervalue_shekel_put     NUMERIC,
    openpositions_put                   NUMERIC,
    positionchange_put                  NUMERIC,
    curr_hour_put                       TEXT,
    underlingasset_put                  NUMERIC,

    fetched_at                          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_history_fetch_date
    ON tase_putcall_history (fetch_date);
CREATE INDEX IF NOT EXISTS idx_history_expiry_date
    ON tase_putcall_history (expiry_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_history_upsert
    ON tase_putcall_history (fetch_date, fetch_time, expiry_date,
                             derivativeid_call, derivativeid_put);


-- ---------------------------------------------------------------------
-- TABLE 3: iron_condor_strategies  (calculated strategies + settlements)
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS iron_condor_strategies (
    id                      BIGSERIAL PRIMARY KEY,
    trigger_date            TEXT,
    trigger_time            TEXT,
    base_index_value        NUMERIC,
    expiry_date             TEXT,
    expiry_day_name         TEXT,
    interval_pct            NUMERIC,

    short_call_strike       NUMERIC,
    long_call_strike        NUMERIC,
    short_put_strike        NUMERIC,
    long_put_strike         NUMERIC,

    short_call_id           TEXT,
    long_call_id            TEXT,
    short_put_id            TEXT,
    long_put_id             TEXT,

    short_call_price        NUMERIC,
    long_call_price         NUMERIC,
    short_put_price         NUMERIC,
    long_put_price          NUMERIC,

    short_call_delta        NUMERIC,
    short_put_delta         NUMERIC,
    long_call_delta         NUMERIC,
    long_put_delta          NUMERIC,

    total_net_premium       NUMERIC,
    max_profit_ils          NUMERIC,
    max_risk_ils            NUMERIC,
    risk_reward_ratio       NUMERIC,

    breakeven_upper         NUMERIC,
    breakeven_lower         NUMERIC,
    days_to_expiry          INTEGER,
    wing_width              NUMERIC DEFAULT 20,

    -- Pricing validation columns (corrupted TASE data defense)
    premium_flag            TEXT     DEFAULT '',
    actual_wing_put         NUMERIC  DEFAULT 0,
    actual_wing_call        NUMERIC  DEFAULT 0,

    status                  TEXT DEFAULT 'calculated',

    -- Settlement results (filled on expiry day)
    actual_index_close      NUMERIC,
    actual_pnl_points       NUMERIC,
    actual_pnl_ils          NUMERIC,
    result_status           TEXT,

    created_at              TIMESTAMPTZ DEFAULT now()
);

-- Idempotent column additions (for tables created before these existed)
ALTER TABLE iron_condor_strategies
    ADD COLUMN IF NOT EXISTS premium_flag      TEXT     DEFAULT '',
    ADD COLUMN IF NOT EXISTS actual_wing_put   NUMERIC  DEFAULT 0,
    ADD COLUMN IF NOT EXISTS actual_wing_call  NUMERIC  DEFAULT 0;

CREATE INDEX IF NOT EXISTS idx_ic_trigger_date
    ON iron_condor_strategies (trigger_date);
CREATE INDEX IF NOT EXISTS idx_ic_expiry_date
    ON iron_condor_strategies (expiry_date);
CREATE UNIQUE INDEX IF NOT EXISTS idx_ic_upsert
    ON iron_condor_strategies (trigger_date, expiry_date, interval_pct);


-- ---------------------------------------------------------------------
-- TABLE 4: pipeline_state  (restart-safe markers for notification flags)
-- ---------------------------------------------------------------------
-- Stores small key/value markers so the pipeline survives restarts
-- without re-sending daily/weekly summaries.  Keys look like:
--   daily_summary_sent:2026-05-29
--   weekly_summary_sent:2026-W22
--   strategy_triggered:2026-W22
--   settlement_done:2026-05-29
-- ---------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS pipeline_state (
    key         TEXT PRIMARY KEY,
    value       TEXT NOT NULL DEFAULT '1',
    updated_at  TIMESTAMPTZ DEFAULT now()
);
