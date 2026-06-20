"""
strategy_engine.py -- Iron Condor Strategy Engine for TASE TA-35

Triggered every Monday at 12:00 PM (first fetch >= 12:00).
Reads the live Put/Call data from Supabase, calculates Short Iron Condor
variations for each expiry date and percentage interval, and saves results.

TASE Multiplier = 50
Wing Width = 20 points
Intervals: 0.5%, 1.0%, 1.5%, 2.0%, 2.5%, 3.0%, 3.5%, 4.0%
"""

import json
import logging
import os
from decimal import Decimal, ROUND_HALF_EVEN, getcontext, InvalidOperation
from datetime import datetime, date, timedelta
from typing import Optional

# 12 significant digits — well beyond what NIS options pricing requires and
# sufficient to represent exact ILS cent amounts up to ₪10B without loss.
getcontext().prec = 12

import httpx
import supabase_client as _sc
import telegram_bot
from config import (
    TZ_ISRAEL, TASE_MULTIPLIER, WING_WIDTH, INTERVALS,
    DAY_NAMES_EN, DAY_NAMES_HE, PRICE_SANITY_MAX_PTS,
    TA35_MIN, TA35_MAX,
)

logger = logging.getLogger("tase_pipeline")

_table: str = ""

# Columns the strategy engine actually needs — avoids pulling all ~40 cols
# per row on every strategy cycle (M-3: reduce SELECT * payload).
_STRATEGY_COLS = (
    "expiry_date,fetch_date,fetch_time,"
    "expirationprice_call,lastrate_call,baserate_call,delta_call,"
    "derivativeid_call,dealsno_call,underlingasset_call,"
    "expirationprice_put,lastrate_put,baserate_put,delta_put,"
    "derivativeid_put,dealsno_put,underlingasset_put"
)


def _init():
    global _table
    _sc.ensure_init()
    _table = os.environ.get("SUPABASE_TABLE", "tase_putcall")


def _ensure_init():
    if not _table:
        _init()


def _clean_numeric(val) -> float:
    """Clean numeric value — remove commas, handle None/empty."""
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    s = str(val).replace(",", "").strip()
    if not s or s == "-":
        return 0.0
    try:
        return float(s)
    except ValueError:
        return 0.0


def _to_decimal(val) -> Decimal:
    """Convert any numeric value to Decimal via string to avoid inheriting
    float imprecision.  Returns Decimal('0') for missing/invalid inputs."""
    if isinstance(val, Decimal):
        return val
    cleaned = _clean_numeric(val)
    try:
        return Decimal(str(cleaned))
    except InvalidOperation:
        return Decimal("0")


def _read_live_data() -> list:
    """Read required columns from tase_putcall (live table) with pagination."""
    _ensure_init()
    all_rows = []
    batch    = 1000
    offset   = 0

    while True:
        url = _sc.rest_url(
            f"{_table}?select={_STRATEGY_COLS}"
            f"&order=id&limit={batch}&offset={offset}"
        )
        try:
            r = httpx.get(url, headers=_sc.headers(), timeout=30)
            if r.status_code not in (200, 206):
                logger.error("Strategy: read live data failed: %d", r.status_code)
                break
            rows = r.json()
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < batch:
                break
            offset += batch
        except Exception as e:
            logger.error("Strategy: read live data error: %s", e)
            break

    return all_rows


_yahoo_cache:    dict  = {}
_yahoo_cache_ts: float = 0.0
_YAHOO_CACHE_TTL = 300  # 5 minutes


def _fetch_yahoo_meta() -> dict:
    """Fetch TA-35 meta from Yahoo Finance (price, open, etc.).
    Cached with 5-minute TTL to avoid stale data during long runs."""
    import time as _t
    global _yahoo_cache_ts

    now_ts = _t.monotonic()
    if _yahoo_cache and (now_ts - _yahoo_cache_ts) < _YAHOO_CACHE_TTL:
        return _yahoo_cache

    url = ("https://query1.finance.yahoo.com/v8/finance/chart/TA35.TA"
           "?interval=1d&range=1d")
    try:
        r = httpx.get(url, timeout=10, headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            data = r.json()
            meta = (data.get("chart", {})
                        .get("result", [{}])[0]
                        .get("meta", {}))
            _yahoo_cache.clear()
            _yahoo_cache.update(meta)
            _yahoo_cache_ts = now_ts
            return meta
    except Exception as e:
        logger.warning("Yahoo Finance fetch failed: %s", e)
    return _yahoo_cache if _yahoo_cache else {}


def _fetch_index_from_yahoo() -> float:
    """Fetch TA-35 live index value from Yahoo Finance API."""
    meta  = _fetch_yahoo_meta()
    price = meta.get("regularMarketPrice", 0)
    if price and price > 0:
        logger.info("TA-35 index from Yahoo Finance: %.2f", price)
        return float(price)
    return 0.0


def _fetch_settlement_price() -> float:
    """
    Fetch TA-35 opening price for settlement.
    TASE options settle on the opening price of expiry day.
    Yahoo Finance 'regularMarketOpen' is the closest available proxy.
    """
    meta       = _fetch_yahoo_meta()
    open_price = meta.get("regularMarketOpen", 0)
    if open_price and open_price > 0:
        logger.info("Settlement price (Yahoo open): %.2f", open_price)
        return float(open_price)
    price = meta.get("regularMarketPrice", 0)
    if price and price > 0:
        logger.warning("Settlement fallback to market price: %.2f", price)
        return float(price)
    return 0.0


def _get_base_index(rows: list) -> float:
    """
    Get the TA-35 base index value.

    Priority:
    1. underlingasset from the LATEST snapshot (filtered by fetch_date+fetch_time)
    2. Yahoo Finance API (real-time fallback)
    3. ATM delta inference (delta closest to 50)
    4. Strike range midpoint (last resort)

    Range-validated: rejects values outside 1000-10000 (TA-35 sane range).

    M-4: first pass collects latest_key, ATM-delta candidate, and sane strikes
    simultaneously, reducing total iterations from 4 down to 2 worst-case.
    """
    SANE_MIN, SANE_MAX = float(TA35_MIN), float(TA35_MAX)

    def _is_sane(v: float) -> bool:
        return SANE_MIN <= v <= SANE_MAX

    # Pass 1: find latest snapshot key, best ATM strike, and all sane strikes
    latest_key                      = None
    best_delta_diff, best_atm_strike = float("inf"), 0.0
    sane_strikes: list              = []

    for row in rows:
        fd, ft = row.get("fetch_date", ""), row.get("fetch_time", "")
        if fd and ft:
            key = (fd, ft)
            if latest_key is None or key > latest_key:
                latest_key = key

        delta  = _clean_numeric(row.get("delta_call"))
        strike = _clean_numeric(row.get("expirationprice_call"))
        if strike > 0 and 0 < delta < 100:
            diff = abs(delta - 50.0)
            if diff < best_delta_diff:
                best_delta_diff, best_atm_strike = diff, strike
        if _is_sane(strike):
            sane_strikes.append(strike)

    # Method 1: latest snapshot underlyingasset (pass 2 — filtered)
    if latest_key:
        for row in rows:
            if (row.get("fetch_date"), row.get("fetch_time")) != latest_key:
                continue
            for col in ("underlingasset_call", "underlingasset_put"):
                v = _clean_numeric(row.get(col))
                if _is_sane(v):
                    logger.info("Base index from %s (%s %s): %.2f",
                                col, latest_key[0], latest_key[1], v)
                    return v
        logger.warning("Latest snapshot (%s %s) has no valid underlying — falling back",
                       latest_key[0], latest_key[1])

    # Method 2: Yahoo Finance API
    val = _fetch_index_from_yahoo()
    if _is_sane(val):
        return val
    if val > 0:
        logger.warning("Yahoo returned out-of-range value: %.2f — skipping", val)

    # Method 3: ATM delta inference (pre-computed in pass 1)
    if _is_sane(best_atm_strike):
        logger.info("Base index from ATM delta: %.2f (diff=%.1f)",
                    best_atm_strike, best_delta_diff)
        return best_atm_strike

    # Method 4: midpoint of strike range (pre-computed in pass 1)
    if sane_strikes:
        midpoint = (min(sane_strikes) + max(sane_strikes)) / 2.0
        logger.warning("Base index from strike midpoint (last resort): %.2f", midpoint)
        return midpoint

    return 0.0


def _find_closest_option(rows: list, target_strike: float,
                         side: str,
                         exclude_strikes: Optional[set] = None,
                         min_strike: Optional[float] = None,
                         max_strike: Optional[float] = None) -> dict:
    """
    Find the option closest to target_strike with the best available price.

    Priority order (each tier falls back to the next):
      1. LIVE-traded today (dealsno > 0, lastrate > 0)  — most reliable
      2. Priced but not traded today (lastrate > 0, dealsno == 0) — stale
      3. baserate fallback (baserate > 0, lastrate == 0) — TASE-set price
      4. Closest strike regardless (unpriced) — last resort

    side: 'call' or 'put'
    exclude_strikes: strikes already used (prevents Short & Long
                     from selecting the same option)
    min_strike: if set, reject any candidate strictly below this value.
                Used for the long call to guarantee a minimum wing width.
    max_strike: if set, reject any candidate strictly above this value.
                Used for the long put to guarantee a minimum wing width.
    """
    if exclude_strikes is None:
        exclude_strikes = set()

    # Track four tiers of candidates: live > stale-priced > baserate > any
    best_live       = None;  best_live_diff       = float("inf")
    best_stale      = None;  best_stale_diff      = float("inf")
    best_base       = None;  best_base_diff       = float("inf")
    best_any        = None;  best_any_diff        = float("inf")

    strike_col  = f"expirationprice_{side}"
    price_col   = f"lastrate_{side}"
    base_col    = f"baserate_{side}"
    delta_col   = f"delta_{side}"
    id_col      = f"derivativeid_{side}"
    deals_col   = f"dealsno_{side}"

    def _candidate(strike, price, delta, opt_id, deals, source):
        return {"strike": strike, "price": price, "delta": delta,
                "id": opt_id, "deals": deals, "price_source": source}

    for row in rows:
        strike = _clean_numeric(row.get(strike_col))
        if strike <= 0:
            continue
        if strike in exclude_strikes:
            continue
        # Wing-width guard: skip candidates that would create a wing
        # narrower than required (long call below floor / long put above ceil)
        if min_strike is not None and strike < min_strike:
            continue
        if max_strike is not None and strike > max_strike:
            continue
        # TASE API returns lastrate/baserate in ₪ per contract (points × multiplier)
        price      = _clean_numeric(row.get(price_col)) / TASE_MULTIPLIER
        base_price = _clean_numeric(row.get(base_col)) / TASE_MULTIPLIER
        deals      = int(_clean_numeric(row.get(deals_col)))
        delta      = _clean_numeric(row.get(delta_col))
        opt_id     = row.get(id_col, "")
        diff       = abs(strike - target_strike)

        # ----------------------------------------------------------
        # Price sanity: reject prices above PRICE_SANITY_MAX_PTS
        # ----------------------------------------------------------
        if price > 0 and price > PRICE_SANITY_MAX_PTS:
            logger.debug(
                "Skipping %s strike %.0f: lastrate %.2f pts exceeds "
                "sanity limit (%.0f pts) — likely stale/theoretical",
                side, strike, price, PRICE_SANITY_MAX_PTS)
            price = 0  # treat as unpriced — may still have baserate
        if base_price > 0 and base_price > PRICE_SANITY_MAX_PTS:
            base_price = 0

        # Tier 1: live-traded today
        if price > 0 and deals > 0 and diff < best_live_diff:
            best_live_diff = diff
            best_live = _candidate(strike, price, delta, opt_id, deals, "live")

        # Tier 2: priced but not traded today (stale lastrate)
        if price > 0 and deals == 0 and diff < best_stale_diff:
            best_stale_diff = diff
            best_stale = _candidate(strike, price, delta, opt_id, deals, "stale")

        # Tier 3: baserate fallback (TASE-computed opening price)
        if price == 0 and base_price > 0 and diff < best_base_diff:
            best_base_diff = diff
            best_base = _candidate(strike, base_price, delta, opt_id, deals, "baserate")

        # Tier 4: closest strike regardless
        effective = price if price > 0 else base_price
        if diff < best_any_diff:
            best_any_diff = diff
            src = "none" if effective == 0 else "fallback"
            best_any = _candidate(strike, effective, delta, opt_id, deals, src)

    if best_live:
        return best_live
    if best_stale:
        logger.info("  %s strike %.0f: using stale lastrate (no trades today)",
                    side, best_stale["strike"])
        return best_stale
    if best_base:
        logger.info("  %s strike %.0f: using baserate fallback (no lastrate)",
                    side, best_base["strike"])
        return best_base
    if best_any:
        logger.warning("No priced %s option near strike %.0f — "
                       "using unpriced/baserate", side, target_strike)
        return best_any
    return {"strike": target_strike, "price": 0, "delta": 0,
            "id": "", "deals": 0, "price_source": "none"}


def _build_price_curve(rows: list, side: str):
    """
    Build a monotonic option-price curve from TODAY'S TRADED strikes only.

    Why: illiquid strikes carry a stale last-trade price (from a prior day,
    when the option was worth more). Using those stale prices for the long
    (protective) legs produces impossible net debits and inverted spreads.
    We anchor the curve only on strikes that traded today (dealsno > 0) with a
    sane price, then read every leg's price off the curve by linear
    interpolation. Untraded strikes get a clean, consistent, interpolated
    price instead of a stale one.

    Data is never mutated or deleted — we only choose which rows to trust as
    anchors; all raw rows remain in the DB unchanged.

    side: 'call' or 'put'
    Returns: a callable price_at(strike)->float (points), or None when no
             traded anchors exist (caller falls back to the matched price).
    """
    strike_col = f"expirationprice_{side}"
    price_col  = f"lastrate_{side}"
    deals_col  = f"dealsno_{side}"

    anchors: dict = {}   # strike -> price (points); dedupe keeps the last seen
    for row in rows:
        strike = _clean_numeric(row.get(strike_col))
        if strike <= 0:
            continue
        deals = int(_clean_numeric(row.get(deals_col)))
        if deals <= 0:
            continue
        price = _clean_numeric(row.get(price_col)) / TASE_MULTIPLIER
        if 0 < price <= PRICE_SANITY_MAX_PTS:
            anchors[strike] = price

    if not anchors:
        return None

    pts = sorted(anchors.items())            # [(strike, price), ...] ascending strike
    strikes = [s for s, _ in pts]
    prices  = [p for _, p in pts]

    def price_at(strike: float) -> float:
        # Flat extrapolation outside the traded range (conservative, monotone).
        if strike <= strikes[0]:
            return prices[0]
        if strike >= strikes[-1]:
            return prices[-1]
        # Linear interpolation between the two bracketing traded anchors.
        for i in range(1, len(strikes)):
            s0, s1 = strikes[i - 1], strikes[i]
            if s0 <= strike <= s1:
                if s1 == s0:
                    return prices[i - 1]
                t = (strike - s0) / (s1 - s0)
                return prices[i - 1] + t * (prices[i] - prices[i - 1])
        return prices[-1]

    return price_at


def _calculate_condor(base_index: float, interval_pct: float,
                      rows_for_expiry: list, expiry_date: str,
                      trigger_date: str, trigger_time: str) -> dict:
    """Calculate one Iron Condor variation using Decimal arithmetic throughout
    to eliminate floating-point accumulation in premium and P&L figures."""

    # All financial arithmetic happens in Decimal; convert to float only at
    # the final return dict (JSON / Supabase boundary).
    BASE    = _to_decimal(base_index)
    PCT     = _to_decimal(interval_pct)
    MULT    = Decimal(str(TASE_MULTIPLIER))
    WING    = Decimal(str(WING_WIDTH))
    ZERO    = Decimal("0")

    offset = BASE * (PCT / Decimal("100"))

    short_call_strike_target = float(BASE + offset)
    short_put_strike_target  = float(BASE - offset)
    long_call_strike_target  = short_call_strike_target + WING_WIDTH
    long_put_strike_target   = short_put_strike_target  - WING_WIDTH

    # ── 1. Short strikes: snap %-target to the nearest real (traded) strike ──
    short_call = _find_closest_option(rows_for_expiry, short_call_strike_target, "call")
    short_put  = _find_closest_option(rows_for_expiry, short_put_strike_target,  "put")

    sc_strike = _to_decimal(short_call["strike"])
    sp_strike = _to_decimal(short_put["strike"])

    # ── 2. Strike-order guard (run BEFORE pricing so prices match final strikes) ──
    if sp_strike >= sc_strike:
        logger.warning(
            "Invalid strike order: SP(%.0f) >= SC(%.0f) at %.1f%% — "
            "forcing symmetric from base %.0f",
            float(sp_strike), float(sc_strike), interval_pct, base_index)
        sp_strike = BASE - offset
        sc_strike = BASE + offset

    # ── 3. Long legs: EXACTLY WING_WIDTH from the short strikes (fixed wing) ──
    lc_strike = sc_strike + WING
    lp_strike = sp_strike - WING

    # ── 4. Price every leg off a curve built from TODAY'S traded strikes ──
    #    This eliminates stale last-trade prices on illiquid long legs (the
    #    cause of impossible net debits). Falls back to the matched price only
    #    when no strike traded today on that side.
    call_curve = _build_price_curve(rows_for_expiry, "call")
    put_curve  = _build_price_curve(rows_for_expiry, "put")

    def _leg_price(curve, strike_d, matched) -> Decimal:
        if curve is not None:
            return _to_decimal(curve(float(strike_d)))
        # Fallback: no traded anchors on this side — use the matcher's price.
        mp = matched["price"]
        return mp if isinstance(mp, Decimal) else _to_decimal(mp)

    sc_price = _leg_price(call_curve, sc_strike, short_call)
    sp_price = _leg_price(put_curve,  sp_strike, short_put)
    lc_price = _leg_price(call_curve, lc_strike, short_call)
    lp_price = _leg_price(put_curve,  lp_strike, short_put)

    # ── 5. No-arbitrage clamp: a further-OTM long can never cost more than the
    #    nearer-money short of the same type. Guarantees each vertical's credit
    #    is >= 0, so the condor can never be a net debit.
    if lc_price > sc_price:
        lc_price = sc_price
    if lp_price > sp_price:
        lp_price = sp_price

    # ── 6. Long-leg metadata (id / delta) — informational only. The long
    #    strikes are synthetic (short ± WING); look them up exactly if listed,
    #    otherwise report empty id / zero delta (honestly: no listed contract).
    def _exact_meta(side: str, strike_d: Decimal) -> dict:
        strike_col = f"expirationprice_{side}"
        id_col     = f"derivativeid_{side}"
        delta_col  = f"delta_{side}"
        target     = float(strike_d)
        for row in rows_for_expiry:
            if _clean_numeric(row.get(strike_col)) == target:
                return {"id": row.get(id_col, ""),
                        "delta": _clean_numeric(row.get(delta_col)),
                        "price_source": "curve"}
        return {"id": "", "delta": 0.0, "price_source": "synthetic"}

    long_call = _exact_meta("call", lc_strike)
    long_put  = _exact_meta("put",  lp_strike)

    actual_wing_put  = sp_strike - lp_strike
    actual_wing_call = lc_strike - sc_strike
    actual_wing_max  = max(actual_wing_put, actual_wing_call)

    # ── Net premium ─────────────────────────────────────────────────
    raw_net_premium = (sc_price + sp_price) - (lc_price + lp_price)

    premium_flag = ""

    if raw_net_premium > actual_wing_max:
        logger.warning(
            "   %.1f%% %s: IMPOSSIBLE premium %.4f pts > wing %.4f pts — "
            "capping to wing (TASE prices likely stale/theoretical). "
            "Legs: SC=%.0f@%.4f LC=%.0f@%.4f SP=%.0f@%.4f LP=%.0f@%.4f",
            interval_pct, expiry_date,
            float(raw_net_premium), float(actual_wing_max),
            float(sc_strike), float(sc_price),
            float(lc_strike), float(lc_price),
            float(sp_strike), float(sp_price),
            float(lp_strike), float(lp_price))
        total_net_premium = actual_wing_max
        premium_flag = "price_capped"
    elif raw_net_premium < ZERO:
        total_net_premium = raw_net_premium
        premium_flag = "negative_premium"
        logger.info(
            "   %.1f%% %s: negative premium %.4f — "
            "this interval costs money to enter (not tradeable)",
            interval_pct, expiry_date, float(raw_net_premium))
    else:
        total_net_premium = raw_net_premium

    if lp_price > sp_price and sp_price > ZERO:
        logger.warning(
            "   %.1f%% %s: Long Put %.0f@%.4f > Short Put %.0f@%.4f "
            "(inverted prices)", interval_pct, expiry_date,
            float(lp_strike), float(lp_price),
            float(sp_strike), float(sp_price))
        if not premium_flag:
            premium_flag = "inverted_prices"

    if lc_price > sc_price and sc_price > ZERO:
        logger.warning(
            "   %.1f%% %s: Long Call %.0f@%.4f > Short Call %.0f@%.4f "
            "(inverted prices)", interval_pct, expiry_date,
            float(lc_strike), float(lc_price),
            float(sc_strike), float(sc_price))
        if not premium_flag:
            premium_flag = "inverted_prices"

    # ------------------------------------------------------------------
    # Liquidity assessment: count how many of the 4 legs were actually
    # traded today (dealsno > 0).  When most legs use stale/baserate
    # pricing, the premium is less trustworthy.
    # ------------------------------------------------------------------
    legs_all = [short_call, long_call, short_put, long_put]
    live_legs = sum(1 for lg in legs_all
                    if lg.get("price_source") == "live")
    if not premium_flag and live_legs == 0:
        premium_flag = "low_liquidity"
        logger.info(
            "   %.1f%% %s: no legs traded today — flagging low_liquidity",
            interval_pct, expiry_date)
    elif not premium_flag and live_legs <= 1:
        premium_flag = "partial_liquidity"

    # ── P&L metrics ─────────────────────────────────────────────────
    max_profit_d = total_net_premium * MULT
    max_risk_d   = (actual_wing_max * MULT) - max_profit_d
    rr_ratio     = float((max_risk_d / max_profit_d).quantize(
        Decimal("0.0001"), rounding=ROUND_HALF_EVEN
    )) if max_profit_d > ZERO else 0.0

    breakeven_upper = sc_strike + total_net_premium
    breakeven_lower = sp_strike - total_net_premium

    def _q2(d: Decimal) -> float:
        """Round to 2 dp using banker's rounding and return as float."""
        return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))

    try:
        exp_d  = date.fromisoformat(expiry_date)
        trig_d = date.fromisoformat(trigger_date)
        dte    = (exp_d - trig_d).days
    except Exception:
        dte = 0

    exp_weekday = date.fromisoformat(expiry_date).weekday()

    return {
        "trigger_date":       trigger_date,
        "trigger_time":       trigger_time,
        "base_index_value":   _q2(BASE),
        "expiry_date":        expiry_date,
        "expiry_day_name":    DAY_NAMES_EN.get(exp_weekday, ""),
        "interval_pct":       interval_pct,

        "short_call_strike":  _q2(sc_strike),
        "long_call_strike":   _q2(lc_strike),
        "short_put_strike":   _q2(sp_strike),
        "long_put_strike":    _q2(lp_strike),

        "short_call_id":      short_call["id"],
        "long_call_id":       long_call["id"],
        "short_put_id":       short_put["id"],
        "long_put_id":        long_put["id"],

        "short_call_price":   _q2(sc_price),
        "long_call_price":    _q2(lc_price),
        "short_put_price":    _q2(sp_price),
        "long_put_price":     _q2(lp_price),

        "short_call_delta":   round(short_call["delta"], 4),
        "short_put_delta":    round(short_put["delta"],  4),
        "long_call_delta":    round(long_call["delta"],  4),
        "long_put_delta":     round(long_put["delta"],   4),

        "total_net_premium":  _q2(total_net_premium),
        "max_profit_ils":     _q2(max_profit_d),
        "max_risk_ils":       _q2(max_risk_d),
        "risk_reward_ratio":  rr_ratio,

        "breakeven_upper":    _q2(breakeven_upper),
        "breakeven_lower":    _q2(breakeven_lower),
        "days_to_expiry":     dte,
        "wing_width":         WING_WIDTH,
        "actual_wing_put":    _q2(actual_wing_put),
        "actual_wing_call":   _q2(actual_wing_call),
        "premium_flag":       premium_flag,
    }


def _strategies_exist_for_week(trigger_date: str) -> bool:
    """Check if strategies already exist for this ISO week."""
    _ensure_init()
    try:
        d      = date.fromisoformat(trigger_date)
        monday = d - timedelta(days=d.weekday())
        friday = monday + timedelta(days=4)
    except ValueError:
        return False

    url = _sc.rest_url(
        f"iron_condor_strategies"
        f"?trigger_date=gte.{monday.isoformat()}"
        f"&trigger_date=lte.{friday.isoformat()}"
        f"&select=id&limit=1"
    )
    try:
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206):
            return len(r.json()) > 0
    except Exception:
        pass
    return False


def has_unsettled_strategies(expiry_date_iso: str) -> bool:
    """Quick check: are there unsettled strategies for this expiry date?"""
    _ensure_init()
    url = _sc.rest_url(
        f"iron_condor_strategies"
        f"?expiry_date=eq.{expiry_date_iso}"
        f"&result_status=is.null"
        f"&select=id&limit=1"
    )
    try:
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206):
            return len(r.json()) > 0
    except Exception:
        pass
    return False


def _save_strategies(strategies: list) -> bool:
    """Save all strategy rows to Supabase with UPSERT.
    Gracefully handles missing columns by retrying without them.
    """
    url     = _sc.rest_url(
        "iron_condor_strategies"
        "?on_conflict=trigger_date,expiry_date,interval_pct"
    )
    headers = _sc.headers(Prefer="resolution=merge-duplicates")
    payload = json.dumps(strategies, ensure_ascii=False)

    try:
        r = httpx.post(url, headers=headers, content=payload, timeout=30)
        if r.status_code in (200, 201, 204):
            logger.info("Strategy: saved %d rows to iron_condor_strategies",
                        len(strategies))
            return True

        if r.status_code == 400 and "column" in r.text.lower():
            optional_cols = {"premium_flag", "actual_wing_put", "actual_wing_call"}
            stripped = [{k: v for k, v in s.items()
                         if k not in optional_cols} for s in strategies]
            logger.warning(
                "Strategy: retrying save without optional columns "
                "(%s) — run migration SQL to add them",
                ", ".join(optional_cols))
            r2 = httpx.post(url, headers=headers,
                            content=json.dumps(stripped, ensure_ascii=False),
                            timeout=30)
            if r2.status_code in (200, 201, 204):
                logger.info("Strategy: saved %d rows (without optional cols)",
                            len(strategies))
                return True
            logger.error("Strategy: retry also failed %d: %s",
                         r2.status_code, r2.text[:200])
        else:
            logger.error("Strategy: save failed %d: %s",
                         r.status_code, r.text[:200])
    except Exception as e:
        logger.error("Strategy: save error: %s", e)
    return False


# ------------------------------------------------------------------
# Main entry point — called from main.py on Monday >= 12:00
# ------------------------------------------------------------------

def run_strategy(tase_live_index: float = 0.0):
    """
    Read live data, calculate Iron Condor for all expiry dates
    and all percentage intervals, save to Supabase.

    tase_live_index: the TA-35 last-traded value from the direct TASE
    API, passed by main.py.  Used as the first-priority base index.
    """
    _init()
    now          = datetime.now(TZ_ISRAEL)
    trigger_date = now.strftime("%Y-%m-%d")
    trigger_time = now.strftime("%H:%M")

    logger.info("=" * 50)
    logger.info("IRON CONDOR STRATEGY ENGINE — START")
    logger.info("Trigger: %s %s", trigger_date, trigger_time)

    if _strategies_exist_for_week(trigger_date):
        logger.info("Strategy: already exists for %s — skipping (restart-safe)",
                    trigger_date)
        return True

    rows = _read_live_data()
    if not rows:
        logger.error("Strategy: no live data available — aborting")
        return False

    # 2. Get base index — priority: TASE direct → Supabase → Yahoo → ATM
    base_index = 0.0
    if tase_live_index and TA35_MIN <= tase_live_index <= TA35_MAX:
        base_index = tase_live_index
        logger.info("Base index from TASE direct API: %.2f", base_index)
    if base_index <= 0:
        base_index = _get_base_index(rows)
    if not (TA35_MIN <= base_index <= TA35_MAX):
        logger.error("Strategy: base index %.2f outside TA-35 sane range "
                     "[1000, 10000] — aborting to prevent corrupt strategies",
                     base_index)
        return False

    logger.info("Base TA-35 index: %.2f", base_index)

    expiry_groups: dict = {}
    for row in rows:
        exp = row.get("expiry_date", "")
        if exp:
            expiry_groups.setdefault(exp, []).append(row)

    # 4. Filter expiry dates: ONLY this week (Mon-Fri), future only.
    #    The data pipeline collects expiries up to 10 days ahead, but
    #    strategies must be limited to the CURRENT trading week —
    #    next-week expiries carry weekend risk (events, gaps) that
    #    makes Monday pricing unreliable for them.
    trigger_d = date.fromisoformat(trigger_date)
    monday = trigger_d - timedelta(days=trigger_d.weekday())  # Mon of this week
    friday = monday + timedelta(days=4)                        # Fri of this week

    future_expiries = sorted(
        e for e in expiry_groups
        if e > trigger_date
        and monday.isoformat() <= e <= friday.isoformat()
    )

    if not future_expiries:
        logger.warning("Strategy: no future expiry dates in current week "
                       "(Mon %s — Fri %s)", monday, friday)
        return False

    # Log what we kept vs what we filtered out
    all_future = sorted(e for e in expiry_groups if e > trigger_date)
    skipped = [e for e in all_future if e not in future_expiries]
    if skipped:
        logger.info("Strategy: skipped %d next-week expiries: %s",
                    len(skipped), skipped)
    logger.info("Expiry dates for strategy: %s", future_expiries)

    all_strategies = []
    for exp_date in future_expiries:
        exp_rows = expiry_groups[exp_date]
        for pct in INTERVALS:
            condor = _calculate_condor(
                base_index, pct, exp_rows,
                exp_date, trigger_date, trigger_time,
            )
            all_strategies.append(condor)
            logger.info(
                "   %s | %.1f%% | Premium=%.2f | Profit=%.2f | Risk=%.2f | RR=%.4f",
                exp_date, pct,
                condor["total_net_premium"],
                condor["max_profit_ils"],
                condor["max_risk_ils"],
                condor["risk_reward_ratio"],
            )

    if all_strategies:
        _save_strategies(all_strategies)
        telegram_bot.alert_strategy_launch(base_index, all_strategies, future_expiries)

    logger.info("IRON CONDOR STRATEGY ENGINE — DONE (%d variations)",
                len(all_strategies))
    logger.info("=" * 50)
    return True


# ------------------------------------------------------------------
# P&L Settlement — called on expiry days at market close
# ------------------------------------------------------------------

def settle_expiry(expiry_date_iso: str, tase_open_price: float = 0.0):
    """
    Check actual index close against all strategies for this expiry date.
    Update each strategy with actual P&L and result status.

    tase_open_price: the TASE opening price passed by main.py from the
    direct TASE index API (via Playwright). This is the most accurate
    settlement price — TASE options settle on the opening price of the
    expiry day.
    """
    _init()

    logger.info("=" * 50)
    logger.info("SETTLEMENT ENGINE — %s", expiry_date_iso)

    # 1. Get settlement price — priority chain:
    #    a) TASE direct opening price (passed by main.py)
    #    b) Yahoo Finance regularMarketOpen
    #    c) underlingasset from live Supabase data
    index_close = 0.0
    if tase_open_price and TA35_MIN <= tase_open_price <= TA35_MAX:
        index_close = tase_open_price
        logger.info("Settlement price (TASE direct open): %.2f", index_close)
    if index_close <= 0:
        index_close = _fetch_settlement_price()  # Yahoo fallback
    if index_close <= 0:
        rows = _read_live_data()
        for row in rows:
            v = _clean_numeric(row.get("underlingasset_call"))
            if v > 0:
                index_close = v
                logger.info("Settlement price from live data: %.2f", v)
                break
    if index_close <= 0:
        logger.error("Settlement: could not get settlement price — aborting")
        return False

    logger.info("Settlement price: %.2f", index_close)

    url = _sc.rest_url(
        f"iron_condor_strategies"
        f"?expiry_date=eq.{expiry_date_iso}"
        f"&result_status=is.null"
        f"&select=*"
    )
    try:
        r = httpx.get(url, headers=_sc.headers(), timeout=30)
        if r.status_code not in (200, 206):
            logger.error("Settlement: read strategies failed: %d", r.status_code)
            return False
        strategies = r.json()
    except Exception as e:
        logger.error("Settlement: read error: %s", e)
        return False

    if not strategies:
        logger.info("Settlement: no unsettled strategies for %s", expiry_date_iso)
        return False

    logger.info("Settling %d strategies...", len(strategies))

    update_url = _sc.rest_url("iron_condor_strategies")
    settled    = 0
    MULT       = Decimal(str(TASE_MULTIPLIER))
    WING_D     = Decimal(str(WING_WIDTH))
    ZERO       = Decimal("0")
    # Settlement price as Decimal — this is the most important number to get right
    index_close_d = _to_decimal(index_close)

    def _q2(d: Decimal) -> float:
        return float(d.quantize(Decimal("0.01"), rounding=ROUND_HALF_EVEN))

    for s in strategies:
        sp_d        = _to_decimal(s.get("short_put_strike"))
        lp_d        = _to_decimal(s.get("long_put_strike"))
        sc_d        = _to_decimal(s.get("short_call_strike"))
        lc_d        = _to_decimal(s.get("long_call_strike"))
        raw_prem_d  = _to_decimal(s.get("total_net_premium"))

        wing_put_d  = (_to_decimal(s.get("actual_wing_put"))
                       or (sp_d - lp_d) or WING_D)
        wing_call_d = (_to_decimal(s.get("actual_wing_call"))
                       or (lc_d - sc_d) or WING_D)

        wing_max_d = max(wing_put_d, wing_call_d)
        if raw_prem_d > wing_max_d:
            logger.warning(
                "Settlement: %.1f%% premium %.4f > wing %.4f — capping",
                _clean_numeric(s.get("interval_pct")),
                float(raw_prem_d), float(wing_max_d))
            net_premium_d = wing_max_d
        else:
            net_premium_d = raw_prem_d

        if sp_d <= index_close_d <= sc_d:
            pnl_points_d = net_premium_d
            status       = "max_profit"
        elif lp_d <= index_close_d < sp_d:
            pnl_points_d = net_premium_d - (sp_d - index_close_d)
            status       = "partial_loss_put"
        elif sc_d < index_close_d <= lc_d:
            pnl_points_d = net_premium_d - (index_close_d - sc_d)
            status       = "partial_loss_call"
        elif index_close_d < lp_d:
            pnl_points_d = net_premium_d - wing_put_d
            status       = "max_loss_put"
        else:
            pnl_points_d = net_premium_d - wing_call_d
            status       = "max_loss_call"

        pnl_ils_d = pnl_points_d * MULT

        s["_settled_pnl_ils"] = _q2(pnl_ils_d)
        s["_settled_status"]  = status

        patch_url  = f"{update_url}?id=eq.{s['id']}"
        patch_data = {
            "actual_index_close": _q2(index_close_d),
            "actual_pnl_points":  _q2(pnl_points_d),
            "actual_pnl_ils":     _q2(pnl_ils_d),
            "result_status":      status,
        }

        try:
            r = httpx.patch(
                patch_url,
                headers=_sc.headers(Prefer="return=minimal"),
                content=json.dumps(patch_data),
                timeout=15,
            )
            if r.status_code in (200, 204):
                settled += 1
                emoji = "✅" if pnl_points_d > ZERO else "❌"
                logger.info(
                    "   %s %.1f%% | Index=%.4f | P&L=%.4f pts (₪%.2f) | %s",
                    emoji, _clean_numeric(s.get("interval_pct")),
                    float(index_close_d), float(pnl_points_d),
                    float(pnl_ils_d), status,
                )
            else:
                logger.warning("Settlement update failed %d: %s",
                               r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Settlement update error: %s", e)

    logger.info("SETTLEMENT DONE: %d/%d strategies settled",
                settled, len(strategies))
    logger.info("=" * 50)

    if settled > 0:
        exp_weekday = date.fromisoformat(expiry_date_iso).weekday()
        day_name    = DAY_NAMES_HE.get(exp_weekday, "")

        report = []
        try:
            read_url = _sc.rest_url(
                f"iron_condor_strategies"
                f"?expiry_date=eq.{expiry_date_iso}"
                f"&result_status=not.is.null"
                f"&select=interval_pct,short_put_strike,short_call_strike,"
                f"actual_pnl_ils,result_status"
                f"&order=interval_pct"
            )
            rr = httpx.get(read_url, headers=_sc.headers(), timeout=15)
            if rr.status_code in (200, 206):
                report = rr.json()
        except Exception:
            pass

        if not report:
            logger.warning("Settlement: re-read failed — using in-memory data")
            for s in strategies:
                report.append({
                    "interval_pct":      _clean_numeric(s.get("interval_pct")),
                    "short_put_strike":  _clean_numeric(s.get("short_put_strike")),
                    "short_call_strike": _clean_numeric(s.get("short_call_strike")),
                    "actual_pnl_ils":    _clean_numeric(s.get("_settled_pnl_ils", 0)),
                    "result_status":     s.get("_settled_status", ""),
                })

        entry_base = _clean_numeric(strategies[0].get("base_index_value", 0))
        telegram_bot.alert_settlement(day_name, index_close, entry_base, report)

    return settled == len(strategies)


# ------------------------------------------------------------------
# Weekly stats for summary report
# ------------------------------------------------------------------

def _get_preferred_intervals() -> list:
    """Read the user's preferred trading intervals from pipeline_state."""
    _ensure_init()
    try:
        url = _sc.rest_url(
            "pipeline_state?key=eq.preferred_intervals&select=value&limit=1"
        )
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206) and r.json():
            raw = r.json()[0].get("value", "") or ""
            return [round(float(x), 1) for x in raw.split(",") if x.strip()]
    except Exception as e:
        logger.warning("_get_preferred_intervals error: %s", e)
    return []


def get_weekly_stats(iso_week: int, iso_year: int = 0) -> dict:
    """Gather stats for the given ISO week number for the weekly summary."""
    _init()

    if iso_year == 0:
        iso_year = datetime.now(TZ_ISRAEL).year
    jan4       = date(iso_year, 1, 4)
    week_start = jan4 - timedelta(days=jan4.weekday())
    week_start += timedelta(weeks=iso_week - 1)
    week_end   = week_start + timedelta(days=6)

    url = _sc.rest_url(
        f"iron_condor_strategies"
        f"?result_status=not.is.null"
        f"&trigger_date=gte.{week_start.isoformat()}"
        f"&trigger_date=lte.{week_end.isoformat()}"
        f"&select=trigger_date,expiry_date,expiry_day_name,interval_pct,"
        f"actual_pnl_ils,result_status"
        f"&order=trigger_date"
    )
    try:
        r = httpx.get(url, headers=_sc.headers(), timeout=15)
        if r.status_code not in (200, 206):
            logger.warning("get_weekly_stats: HTTP %d", r.status_code)
            return {}
        week_rows = r.json()
    except Exception as e:
        logger.error("get_weekly_stats error: %s", e)
        return {}

    if not week_rows:
        return {}

    # Potential profit (condor): read the best_condor_per_expiry VIEW — the
    # single source of truth shared with the dashboard — for this week's
    # expiries (each settles on its own date). Same View → same number in the
    # bot and the dashboard.
    potential_total = 0.0
    potential_breakdown = []
    try:
        view_url = _sc.rest_url(
            f"best_condor_per_expiry"
            f"?expiry_date=gte.{week_start.isoformat()}"
            f"&expiry_date=lte.{week_end.isoformat()}"
            f"&select=expiry_date,expiry_day_name,interval_pct,actual_pnl_ils"
            f"&order=expiry_date"
        )
        vr = httpx.get(view_url, headers=_sc.headers(), timeout=15)
        if vr.status_code in (200, 206):
            for row in vr.json():
                pnl = _clean_numeric(row.get("actual_pnl_ils", 0))
                potential_total += pnl
                potential_breakdown.append({
                    "expiry":   str(row.get("expiry_date", "")),
                    "day":      row.get("expiry_day_name", ""),
                    "interval": _clean_numeric(row.get("interval_pct", 0)),
                    "pnl":      pnl,
                })
    except Exception as e:
        logger.error("get_weekly_stats potential (View) error: %s", e)

    preferred = _get_preferred_intervals()
    if preferred:
        filtered = [r for r in week_rows
                    if round(_clean_numeric(r.get("interval_pct", 0)), 1) in preferred]
        if filtered:
            week_rows = filtered
            logger.info("Weekly stats restricted to preferred intervals: %s", preferred)

    trades    = len(week_rows)
    wins      = sum(1 for r in week_rows
                    if _clean_numeric(r.get("actual_pnl_ils", 0)) > 0)
    total_pnl = sum(_clean_numeric(r.get("actual_pnl_ils", 0)) for r in week_rows)

    by_interval: dict = {}
    for r in week_rows:
        pct = _clean_numeric(r.get("interval_pct", 0))
        pnl = _clean_numeric(r.get("actual_pnl_ils", 0))
        by_interval[pct] = by_interval.get(pct, 0) + pnl

    best_interval  = max(by_interval, key=by_interval.get) if by_interval else 0
    worst_interval = min(by_interval, key=by_interval.get) if by_interval else 0

    return {
        "trades":         trades,
        "wins":           wins,
        "total_pnl":      total_pnl,
        "best_interval":  best_interval,
        "best_pnl":       by_interval.get(best_interval, 0),
        "worst_interval": worst_interval,
        "worst_pnl":      by_interval.get(worst_interval, 0),
        # Per-interval P&L for the week (₪), sorted by interval ascending.
        "by_interval":    dict(sorted(by_interval.items())),
        # Potential: best-₪ interval per expiry + the weekly sum of those.
        "potential_total":     potential_total,
        "potential_breakdown": potential_breakdown,
    }
