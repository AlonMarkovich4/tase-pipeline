"""
strategy_engine.py -- Iron Condor Strategy Engine for TASE TA-35

Triggered every Monday at 12:00 PM (first fetch >= 12:00).
Reads the live Put/Call data from Supabase, calculates Short Iron Condor
variations for each expiry date and percentage interval, and saves results.

TASE Multiplier = 50
Wing Width = 20 points
Intervals: 0.5%, 1.0%, 1.5%, 2.0%, 2.5%, 3.0%, 3.5%, 4.0%
"""

import os
import json
import logging
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

import httpx
import telegram_bot

logger = logging.getLogger("tase_pipeline")

TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")
TASE_MULTIPLIER = 50
WING_WIDTH = 20
INTERVALS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

DAY_NAMES = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday",
}

_base_url: str = ""
_api_key:  str = ""


def _init():
    global _base_url, _api_key
    _base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    _api_key  = os.environ.get("SUPABASE_KEY", "")


def _headers() -> dict:
    return {
        "apikey":        _api_key,
        "Authorization": f"Bearer {_api_key}",
        "Content-Type":  "application/json",
    }


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


def _read_live_data() -> list:
    """Read all rows from tase_putcall (live table)."""
    url = f"{_base_url}/rest/v1/tase_putcall?select=*"
    try:
        r = httpx.get(url, headers=_headers(), timeout=30)
        if r.status_code in (200, 206):
            return r.json()
        logger.error("Strategy: read live data failed: %d", r.status_code)
    except Exception as e:
        logger.error("Strategy: read live data error: %s", e)
    return []


def _get_base_index(rows: list) -> float:
    """Extract the TA-35 base index value from the data."""
    for row in rows:
        val = _clean_numeric(row.get("underlingasset_call"))
        if val > 0:
            return val
        val = _clean_numeric(row.get("underlingasset_put"))
        if val > 0:
            return val
    return 0.0


def _find_closest_option(rows: list, target_strike: float,
                         side: str) -> dict:
    """
    Find the option closest to target_strike.
    side: 'call' or 'put'
    """
    best = None
    best_diff = float("inf")

    strike_col = f"expirationprice_{side}"
    price_col  = f"lastrate_{side}"
    delta_col  = f"delta_{side}"
    id_col     = f"derivativeid_{side}"

    for row in rows:
        strike = _clean_numeric(row.get(strike_col))
        if strike <= 0:
            continue
        diff = abs(strike - target_strike)
        if diff < best_diff:
            best_diff = diff
            best = {
                "strike":  strike,
                "price":   _clean_numeric(row.get(price_col)),
                "delta":   _clean_numeric(row.get(delta_col)),
                "id":      row.get(id_col, ""),
            }

    return best or {"strike": target_strike, "price": 0, "delta": 0, "id": ""}


def _calculate_condor(base_index: float, interval_pct: float,
                      rows_for_expiry: list, expiry_date: str,
                      trigger_date: str, trigger_time: str) -> dict:
    """Calculate one Iron Condor variation."""

    offset = base_index * (interval_pct / 100.0)

    # Short strikes
    short_call_strike = base_index + offset
    short_put_strike  = base_index - offset

    # Long (protection) strikes — 20 points away
    long_call_strike = short_call_strike + WING_WIDTH
    long_put_strike  = short_put_strike - WING_WIDTH

    # Find closest real options
    short_call = _find_closest_option(rows_for_expiry, short_call_strike, "call")
    long_call  = _find_closest_option(rows_for_expiry, long_call_strike, "call")
    short_put  = _find_closest_option(rows_for_expiry, short_put_strike, "put")
    long_put   = _find_closest_option(rows_for_expiry, long_put_strike, "put")

    # Net premium
    total_net_premium = (
        (short_call["price"] + short_put["price"])
        - (long_call["price"] + long_put["price"])
    )

    max_profit = total_net_premium * TASE_MULTIPLIER
    max_risk   = (WING_WIDTH * TASE_MULTIPLIER) - max_profit
    rr_ratio   = round(max_risk / max_profit, 4) if max_profit > 0 else 0

    # Break-even points
    breakeven_upper = short_call["strike"] + total_net_premium
    breakeven_lower = short_put["strike"] - total_net_premium

    # Days to expiry
    try:
        exp_d = date.fromisoformat(expiry_date)
        trig_d = date.fromisoformat(trigger_date)
        dte = (exp_d - trig_d).days
    except Exception:
        dte = 0

    exp_weekday = date.fromisoformat(expiry_date).weekday()

    return {
        "trigger_date":       trigger_date,
        "trigger_time":       trigger_time,
        "base_index_value":   round(base_index, 2),
        "expiry_date":        expiry_date,
        "expiry_day_name":    DAY_NAMES.get(exp_weekday, ""),
        "interval_pct":       interval_pct,

        "short_call_strike":  round(short_call["strike"], 2),
        "long_call_strike":   round(long_call["strike"], 2),
        "short_put_strike":   round(short_put["strike"], 2),
        "long_put_strike":    round(long_put["strike"], 2),

        "short_call_id":      short_call["id"],
        "long_call_id":       long_call["id"],
        "short_put_id":       short_put["id"],
        "long_put_id":        long_put["id"],

        "short_call_price":   round(short_call["price"], 2),
        "long_call_price":    round(long_call["price"], 2),
        "short_put_price":    round(short_put["price"], 2),
        "long_put_price":     round(long_put["price"], 2),

        "short_call_delta":   round(short_call["delta"], 4),
        "short_put_delta":    round(short_put["delta"], 4),
        "long_call_delta":    round(long_call["delta"], 4),
        "long_put_delta":     round(long_put["delta"], 4),

        "total_net_premium":  round(total_net_premium, 2),
        "max_profit_ils":     round(max_profit, 2),
        "max_risk_ils":       round(max_risk, 2),
        "risk_reward_ratio":  rr_ratio,

        "breakeven_upper":    round(breakeven_upper, 2),
        "breakeven_lower":    round(breakeven_lower, 2),
        "days_to_expiry":     dte,
        "wing_width":         WING_WIDTH,
    }


def _save_strategies(strategies: list) -> bool:
    """Save all strategy rows to Supabase."""
    url = f"{_base_url}/rest/v1/iron_condor_strategies"
    payload = json.dumps(strategies, ensure_ascii=False)

    try:
        r = httpx.post(url, headers=_headers(),
                       content=payload, timeout=30)
        if r.status_code in (200, 201, 204):
            logger.info("Strategy: saved %d rows to iron_condor_strategies",
                        len(strategies))
            return True
        logger.error("Strategy: save failed %d: %s",
                     r.status_code, r.text[:200])
    except Exception as e:
        logger.error("Strategy: save error: %s", e)
    return False


# ------------------------------------------------------------------
# Main entry point — called from main.py on Monday >= 12:00
# ------------------------------------------------------------------

def run_strategy():
    """
    Read live data, calculate Iron Condor for all expiry dates
    and all percentage intervals, save to Supabase.
    """
    _init()
    now = datetime.now(TZ_ISRAEL)
    trigger_date = now.strftime("%Y-%m-%d")
    trigger_time = now.strftime("%H:%M")

    logger.info("=" * 50)
    logger.info("IRON CONDOR STRATEGY ENGINE — START")
    logger.info("Trigger: %s %s", trigger_date, trigger_time)

    # 1. Read live data
    rows = _read_live_data()
    if not rows:
        logger.error("Strategy: no live data available — aborting")
        return False

    # 2. Get base index
    base_index = _get_base_index(rows)
    if base_index <= 0:
        logger.error("Strategy: could not determine base index — aborting")
        return False

    logger.info("Base TA-35 index: %.2f", base_index)

    # 3. Group rows by expiry date
    expiry_groups = {}
    for row in rows:
        exp = row.get("expiry_date", "")
        if exp:
            expiry_groups.setdefault(exp, []).append(row)

    # 4. Filter only future expiry dates (Tue-Fri of this week)
    today = date.today()
    future_expiries = sorted(
        e for e in expiry_groups if e > trigger_date
    )

    if not future_expiries:
        logger.warning("Strategy: no future expiry dates found")
        return False

    logger.info("Expiry dates for strategy: %s", future_expiries)

    # 5. Calculate all variations
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

    # 6. Save to Supabase
    if all_strategies:
        _save_strategies(all_strategies)
        telegram_bot.alert_strategy_launch(len(all_strategies), future_expiries)

    logger.info("IRON CONDOR STRATEGY ENGINE — DONE (%d variations)",
                len(all_strategies))
    logger.info("=" * 50)
    return True


# ------------------------------------------------------------------
# P&L Settlement — called on expiry days at market close
# ------------------------------------------------------------------

def settle_expiry(expiry_date_iso: str):
    """
    Check actual index close against all strategies for this expiry date.
    Update each strategy with actual P&L and result status.
    """
    _init()

    logger.info("=" * 50)
    logger.info("SETTLEMENT ENGINE — %s", expiry_date_iso)

    # 1. Get current index value from live data
    rows = _read_live_data()
    if not rows:
        logger.error("Settlement: no live data — aborting")
        return False

    index_close = _get_base_index(rows)
    if index_close <= 0:
        logger.error("Settlement: could not get index close — aborting")
        return False

    logger.info("Index close: %.2f", index_close)

    # 2. Read all strategies for this expiry date
    url = (
        f"{_base_url}/rest/v1/iron_condor_strategies"
        f"?expiry_date=eq.{expiry_date_iso}"
        f"&result_status=is.null"
        f"&select=*"
    )
    try:
        r = httpx.get(url, headers=_headers(), timeout=30)
        if r.status_code not in (200, 206):
            logger.error("Settlement: read strategies failed: %d", r.status_code)
            return False
        strategies = r.json()
    except Exception as e:
        logger.error("Settlement: read error: %s", e)
        return False

    if not strategies:
        logger.info("Settlement: no unsettled strategies for %s", expiry_date_iso)
        return True

    logger.info("Settling %d strategies...", len(strategies))

    # 3. Calculate actual P&L for each strategy
    update_url = f"{_base_url}/rest/v1/iron_condor_strategies"
    settled = 0

    for s in strategies:
        short_put  = _clean_numeric(s.get("short_put_strike"))
        long_put   = _clean_numeric(s.get("long_put_strike"))
        short_call = _clean_numeric(s.get("short_call_strike"))
        long_call  = _clean_numeric(s.get("long_call_strike"))
        net_premium = _clean_numeric(s.get("total_net_premium"))

        # Determine result
        if short_put <= index_close <= short_call:
            # Index inside short strikes — max profit
            pnl_points = net_premium
            status = "max_profit"

        elif long_put <= index_close < short_put:
            # Index between long put and short put — partial loss on put side
            intrusion = short_put - index_close
            pnl_points = net_premium - intrusion
            status = "partial_loss_put"

        elif short_call < index_close <= long_call:
            # Index between short call and long call — partial loss on call side
            intrusion = index_close - short_call
            pnl_points = net_premium - intrusion
            status = "partial_loss_call"

        elif index_close < long_put:
            # Index below long put — max loss
            pnl_points = net_premium - WING_WIDTH
            status = "max_loss_put"

        else:
            # Index above long call — max loss
            pnl_points = net_premium - WING_WIDTH
            status = "max_loss_call"

        pnl_ils = round(pnl_points * TASE_MULTIPLIER, 2)

        # 4. Update row in Supabase
        patch_url = f"{update_url}?id=eq.{s['id']}"
        patch_data = {
            "actual_index_close": round(index_close, 2),
            "actual_pnl_points":  round(pnl_points, 2),
            "actual_pnl_ils":     pnl_ils,
            "result_status":      status,
        }

        try:
            headers = _headers()
            headers["Prefer"] = "return=minimal"
            r = httpx.patch(patch_url, headers=headers,
                            content=json.dumps(patch_data),
                            timeout=15)
            if r.status_code in (200, 204):
                settled += 1
                emoji = "✅" if pnl_points > 0 else "❌"
                logger.info(
                    "   %s %.1f%% | Index=%.2f | P&L=%.2f pts (₪%.2f) | %s",
                    emoji, _clean_numeric(s.get("interval_pct")),
                    index_close, pnl_points, pnl_ils, status,
                )
            else:
                logger.warning("Settlement update failed %d: %s",
                               r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Settlement update error: %s", e)

    logger.info("SETTLEMENT DONE: %d/%d strategies settled",
                settled, len(strategies))
    logger.info("=" * 50)

    # Send Telegram settlement report
    if settled > 0:
        exp_weekday = date.fromisoformat(expiry_date_iso).weekday()
        day_he = {
            0: "שני", 1: "שלישי", 2: "רביעי",
            3: "חמישי", 4: "שישי",
        }
        day_name = day_he.get(exp_weekday, "")

        # Build results list for telegram
        report = []
        for s in strategies:
            report.append({
                "interval_pct":     _clean_numeric(s.get("interval_pct")),
                "short_put_strike": _clean_numeric(s.get("short_put_strike")),
                "short_call_strike": _clean_numeric(s.get("short_call_strike")),
                "actual_pnl_ils":   _clean_numeric(s.get("actual_pnl_ils", 0)),
                "result_status":    s.get("result_status", ""),
            })
        # Re-read updated rows to get actual_pnl_ils
        try:
            read_url = (
                f"{_base_url}/rest/v1/iron_condor_strategies"
                f"?expiry_date=eq.{expiry_date_iso}"
                f"&result_status=neq.null"
                f"&select=interval_pct,short_put_strike,short_call_strike,"
                f"actual_pnl_ils,result_status"
                f"&order=interval_pct"
            )
            rr = httpx.get(read_url, headers=_headers(), timeout=15)
            if rr.status_code in (200, 206):
                report = rr.json()
        except Exception:
            pass

        telegram_bot.alert_settlement(day_name, index_close, report)

    return settled == len(strategies)
