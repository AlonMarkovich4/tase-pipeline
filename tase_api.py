"""
tase_api.py -- TASE API interaction layer.

Handles expiry-date discovery, paginated options fetching, and the
per-cycle data collection + Supabase write logic.  Extracted from
main.py so the orchestration loop stays thin and this layer can be
tested independently.
"""
import logging
import random
import time
from datetime import date, datetime, timedelta

import database as db
import option_schema as _schema
import strategy_engine
import telegram_bot
from config import (
    TZ_ISRAEL, TRADING_DAYS, MARKET_CLOSE, DAY_NAMES,
)

logger = logging.getLogger("tase_pipeline")

API_URL    = "https://api.tase.co.il/api/derivatives/putvscall"
EXPIRY_URL = "https://api.tase.co.il/api/derivatives/fltrputvscallexpdates"

# Lowest plausible TA-35 option strike. TASE appends one constant placeholder/
# summary row per response (strike "1", no put) that is not a real contract;
# we drop it at the source so the validation gate's ITEMS_REJECTED warning
# stays a meaningful signal for a GENUINELY bad row instead of firing every
# cycle on this known junk.
_MIN_VALID_STRIKE = 1000.0


def _is_real_option_row(item: dict) -> bool:
    """True if either side carries a plausible TA-35 strike (>= _MIN_VALID_STRIKE).
    Drops TASE's placeholder/summary row (strike '1') case-insensitively."""
    for key in ("ExpirationPrice_call", "ExpirationPrice_Call",
                "ExpirationPrice_put", "ExpirationPrice_Put"):
        v = item.get(key)
        if v in (None, ""):
            continue
        try:
            if float(str(v).replace(",", "")) >= _MIN_VALID_STRIKE:
                return True
        except (ValueError, TypeError):
            continue
    return False


def get_expiry_dates(page, max_retries: int = 3) -> list:
    """Fetch active weekly expiry dates from TASE.
    Returns a sorted list of ``date`` objects, or [] on failure."""
    js = """
    async (url) => {
        try {
            const r = await fetch(url + "?objId=01&lang=0&dType=2&date=", {
                headers: {
                    "Accept": "application/json, text/plain, */*",
                    "Content-Type": "application/json;charset=UTF-8"
                }
            });
            if (r.status !== 200) return { error: "status_" + r.status };
            return { data: await r.json() };
        } catch(e) { return { error: e.message }; }
    }
    """
    result = None
    for attempt in range(1, max_retries + 1):
        result = page.evaluate(js, EXPIRY_URL)
        if not result.get("error"):
            break
        wait = min(5 * (2 ** (attempt - 1)), 45)
        logger.warning(
            "Expiry-dates API (attempt %d/%d): %s — retry in %ds",
            attempt, max_retries, result["error"], wait,
        )
        if attempt < max_retries:
            time.sleep(wait)

    if result.get("error"):
        logger.warning("Expiry-dates API failed after %d attempts: %s",
                       max_retries, result["error"])
        return []

    items = (result.get("data") or {}).get("DerivativeExpirationDateItems", [])

    # Sliding 10-day window from today handles end-of-week edge cases
    # (e.g. Friday after settlement when only next week's expiries remain).
    today      = datetime.now(TZ_ISRAEL).date()
    window_end = today + timedelta(days=10)

    dates = []
    for it in items:
        if it.get("ExpirationDateType") != "01":
            continue
        raw = it.get("Date", "")
        try:
            d = date(int(raw[6:10]), int(raw[3:5]), int(raw[0:2]))
            # Skip expiries on non-trading weekdays. TASE may list a Sunday
            # expiry (e.g. 2026-06-14), but the market is closed Sun (Mon–Fri
            # calendar), so it never trades or settles here — don't scrape it.
            if today <= d <= window_end and d.weekday() in TRADING_DAYS:
                dates.append(d)
        except (ValueError, IndexError):
            continue
    return sorted(dates)


def _fetch_all_pages(page, expr_date_iso: str):
    """Paginate through all option rows for a given expiry date.
    Returns (items, trade_date, asset_name, underlying_value)."""
    all_items        = []
    page_num         = 1
    trade_date       = None
    asset_name       = None
    underlying_value = None

    while True:
        js = """
        async (p) => {
            try {
                const r = await fetch(p.url, {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json;charset=UTF-8",
                        "Accept": "application/json, text/plain, */*",
                        "Accept-Language": "he-IL"
                    },
                    body: JSON.stringify({
                        inQType:  1,
                        dType:    "2",
                        updType:  "1",
                        d:        "",
                        exprDate: p.exprDate,
                        qType:    "3",
                        objId:    "01",
                        TotalRec: p.totalRec,
                        pageNum:  p.pageNum,
                        lang:     "0"
                    })
                });
                if (r.status !== 200) return {error: "status_" + r.status};
                return {data: await r.json()};
            } catch(e) { return {error: e.message}; }
        }
        """
        result = None
        for attempt in range(1, 4):
            result = page.evaluate(js, {
                "url":      API_URL,
                "exprDate": expr_date_iso,
                "totalRec": 1 if page_num == 1 else len(all_items),
                "pageNum":  page_num,
            })
            if not result.get("error"):
                break
            wait = min(5 * (2 ** (attempt - 1)), 30)
            logger.warning("putvscall page %d (attempt %d/3): %s — retry in %ds",
                           page_num, attempt, result["error"], wait)
            if attempt < 3:
                time.sleep(wait)

        if result.get("error"):
            logger.warning("putvscall page %d failed after 3 attempts: %s",
                           page_num, result["error"])
            break

        data  = result.get("data", {})
        items = data.get("Items", [])
        total = data.get("TotalRec", 0)
        trade_date = trade_date or data.get("TradeDate")
        asset_name = asset_name or data.get("AssetName")

        if underlying_value is None:
            if page_num == 1:
                top_keys = [k for k in data.keys() if k != "Items"]
                logger.info("   API top-level keys: %s", top_keys)
                for k in top_keys:
                    v = data[k]
                    if isinstance(v, (int, float)) and v > 0:
                        logger.info("   API %s = %s", k, v)

            for field in ("UnderlyingAssetValue", "UnderlyingAsset",
                          "UnderlingAsset", "BaseValue", "IndexValue",
                          "AssetValue", "BaseRate"):
                val = data.get(field)
                if val and isinstance(val, (int, float)) and val > 0:
                    underlying_value = float(val)
                    logger.info("   Underlying asset from '%s': %.2f",
                                field, underlying_value)
                    break

        if not items:
            break

        all_items.extend(items)
        logger.info("   page %d: %d records (%d/%d)",
                    page_num, len(items), len(all_items), total)

        if len(all_items) >= total:
            break
        page_num += 1
        # Minimal pause between pages — TASE WAF tolerates intra-expiry pagination.
        time.sleep(0.15)

    # Drop TASE's constant placeholder row (strike "1") before it leaves the
    # fetch boundary, so the validation gate only ever rejects REAL bad rows.
    real_items = [it for it in all_items if _is_real_option_row(it)]
    dropped = len(all_items) - len(real_items)
    if dropped:
        logger.debug("Dropped %d placeholder row(s) from %s feed",
                     dropped, expr_date_iso)

    return real_items, trade_date, asset_name, underlying_value


def run_cycle(page, cycle_time: datetime) -> dict:
    """Execute one full data collection cycle: fetch all expiry dates,
    pull all option rows, inject underlying value, and upsert to Supabase."""
    date_str = cycle_time.strftime("%Y-%m-%d")
    time_str = cycle_time.strftime("%H:%M")

    expiry_dates = get_expiry_dates(page)
    if not expiry_dates:
        # Couldn't even fetch the expiry list — the browser/WAF/network path is
        # down. This is a TRANSPORT failure (transport_ok=False) → main recovers
        # the session. Distinct from "got data but it was stale/empty".
        logger.warning("No expiry dates — skipping cycle")
        return {"ok": False, "rows": 0, "expiries": 0, "transport_ok": False}

    logger.info("Expiry dates: %s", [d.isoformat() for d in expiry_dates])

    cycle_underlying = 0.0
    try:
        cycle_underlying = strategy_engine._fetch_index_from_yahoo()
    except Exception as ye:
        logger.warning("Live index fetch failed: %s", ye)

    success_count = 0
    total_rows    = 0
    had_critical  = False

    for idx, exp_date in enumerate(expiry_dates):
        exp_iso = exp_date.isoformat()
        wd      = exp_date.weekday()
        en, he  = DAY_NAMES.get(wd, (f"Day{wd}", f"Day{wd}"))

        logger.info(">> %s (%s) %s", en, he, exp_iso)

        items, trade_dt, asset, underlying = _fetch_all_pages(page, exp_iso)

        effective_underlying = underlying or cycle_underlying
        if effective_underlying and items:
            for item in items:
                if not item.get("UnderlingAsset_Call"):
                    item["UnderlingAsset_Call"] = effective_underlying
                if not item.get("UnderlingAsset_Put"):
                    item["UnderlingAsset_Put"] = effective_underlying

        if items:
            if len(items) > 500:
                logger.warning("   Unusually large response: %d items", len(items))

            # ── Validation gate ──────────────────────────────────────
            vr = _schema.validate_items(items, date_str, trade_dt, exp_iso)

            if vr.has_critical:
                had_critical = True
                for w in vr.warnings:
                    if w.level == _schema.DQLevel.CRITICAL:
                        logger.error(
                            "DATA QUALITY CRITICAL [%s] expiry %s: %s",
                            w.code, exp_iso, w.detail,
                        )
                        # Throttle Telegram: at most ONE alert per code per day.
                        # TASE serves a stale morning snapshot across all
                        # expiries every 15-min cycle; without this the user
                        # gets ~15 messages per cycle. The daily marker lives in
                        # pipeline_state so it also survives worker restarts.
                        dq_key = f"dq_alert:{w.code}:{date_str}"
                        if not db.state_is_set(dq_key):
                            telegram_bot.alert_crash(
                                f"Data Quality CRITICAL [{w.code}]\n{w.detail}"
                            )
                            db.state_set(dq_key)
                logger.error(
                    "   Skipping upsert for expiry %s — %d/%d items accepted "
                    "but CRITICAL quality issue(s) detected",
                    exp_iso, vr.accepted_count, len(items),
                )
                # Treat this expiry as failed so _clear_old_snapshots won't run
                total_rows += len(items)
                continue

            items_to_store = vr.accepted
            if vr.rejected_count:
                logger.warning(
                    "   Storing %d/%d items after rejecting %d invalid rows",
                    vr.accepted_count, len(items), vr.rejected_count,
                )
            # ── End validation gate ──────────────────────────────────

            if db.upsert_items(date_str, time_str, exp_iso, trade_dt, items_to_store):
                success_count += 1
            total_rows += len(items_to_store)
            logger.info("   [OK] %d records", len(items_to_store))
        else:
            db.upsert_no_trading(date_str, time_str, exp_iso)
            logger.info("   [EMPTY] no trading")

        if idx < len(expiry_dates) - 1:
            time.sleep(random.uniform(3, 5))

    # Only clean up old snapshots when ALL expiries succeeded.
    if success_count == len(expiry_dates) and success_count > 0:
        db._clear_old_snapshots(date_str, time_str)
    elif 0 < success_count < len(expiry_dates):
        logger.warning(
            "Partial cycle (%d/%d expiries) — skipping cleanup to preserve "
            "previous complete snapshot",
            success_count, len(expiry_dates),
        )

    return {
        "ok":           success_count > 0,
        "rows":         total_rows,
        "expiries":     len(expiry_dates),
        "expiry_dates": expiry_dates,
        "full_success": success_count == len(expiry_dates),
        # We fetched the expiry list (and reached here), so the browser/WAF/
        # network path works → transport is OK even if nothing was stored.
        "transport_ok": True,
        # True if the data was fetched but blocked by a CRITICAL quality issue
        # (e.g. stale feed) — a DATA condition, not a transport failure.
        "had_critical": had_critical,
    }


def is_last_cycle(now: datetime, fetch_interval_seconds: int) -> bool:
    """True if the next cycle would start after market close."""
    return (now + timedelta(seconds=fetch_interval_seconds)).time() > MARKET_CLOSE


def is_last_trading_day_of_week(now: datetime, expiry_dates: list) -> bool:
    """
    True if today is the LAST trading day of the current ISO week.

    Two-tier detection:
      1. PRIMARY: TASE expiry dates as ground truth — the last expiry
         of the week is the last trading day.  Robust to one-off holidays.
      2. FALLBACK (no expiry data cached yet): scan the calendar.
    """
    today     = now.date()
    this_week = (now.isocalendar()[0], now.isocalendar()[1])

    if expiry_dates:
        week_expiries = [
            d for d in expiry_dates
            if (d.isocalendar()[0], d.isocalendar()[1]) == this_week
        ]
        if week_expiries:
            return today == max(week_expiries)
        return False

    if today.weekday() not in TRADING_DAYS:
        return False
    for days_ahead in range(1, 8):
        future = today + timedelta(days=days_ahead)
        if (future.isocalendar()[0], future.isocalendar()[1]) != this_week:
            break
        if future.weekday() in TRADING_DAYS:
            return False
    return True
