-- Run this in Supabase SQL Editor
-- Flat structure: one row per option, column names are all lowercase

DROP TABLE IF EXISTS tase_putcall;

CREATE TABLE tase_putcall (
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
    underlingasset_call                 TEXT,

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
    underlingasset_put                  TEXT,

    fetched_at                          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_tase_fetch_date  ON tase_putcall (fetch_date);
CREATE INDEX idx_tase_expiry_date ON tase_putcall (expiry_date);
CREATE UNIQUE INDEX idx_tase_upsert
    ON tase_putcall (fetch_date, fetch_time, expiry_date, derivativeid_call, derivativeid_put);

-- =============================================================
-- History table: end-of-day snapshot saved from last cycle
-- =============================================================

CREATE TABLE tase_putcall_history (
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
    underlingasset_call                 TEXT,

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
    underlingasset_put                  TEXT,

    fetched_at                          TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_history_fetch_date  ON tase_putcall_history (fetch_date);
CREATE INDEX idx_history_expiry_date ON tase_putcall_history (expiry_date);

-- =============================================================
-- Iron Condor strategies: Monday 12:00 PM trigger
-- =============================================================

CREATE TABLE iron_condor_strategies (
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

    status                  TEXT DEFAULT 'calculated',
    created_at              TIMESTAMPTZ DEFAULT now()
);

CREATE INDEX idx_ic_trigger_date ON iron_condor_strategies (trigger_date);
CREATE INDEX idx_ic_expiry_date ON iron_condor_strategies (expiry_date);
