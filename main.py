"""
TASE Real-Time Put/Call Pipeline — Render Background Worker
============================================================
Fetches options data every 15 minutes during Israeli trading
hours (Mon-Fri 09:30-17:30) and syncs to Supabase.

Uses Playwright + page.evaluate(fetch()) to bypass Imperva WAF.
"""

import logging
import os
import signal
import sys
import threading
import time
from datetime import datetime, timedelta

from playwright.sync_api import sync_playwright

import browser as _browser
import database as db
import health_server
import strategy_engine
import tase_api
import telegram_bot
from config import (
    TZ_ISRAEL, TRADING_DAYS, MARKET_OPEN, MARKET_CLOSE, DAY_NAMES,
    STRATEGY_WINDOW_OPEN, STRATEGY_WINDOW_CLOSE, SETTLEMENT_AFTER,
    BROWSER_RESTART_SECONDS, FETCH_INTERVAL_MINUTES,
    TA35_MIN, TA35_MAX,
)

# ------------------------------------------------------------------
# Local config
# ------------------------------------------------------------------
HEADLESS        = os.environ.get("HEADLESS", "true").lower() == "true"
FETCH_INTERVAL  = int(os.environ.get("FETCH_INTERVAL_MINUTES",
                                      str(FETCH_INTERVAL_MINUTES))) * 60
BROWSER_RESTART = BROWSER_RESTART_SECONDS

# ------------------------------------------------------------------
# Logging  (stdout only — Render captures it automatically)
# ------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger("tase_pipeline")

# ------------------------------------------------------------------
# Graceful shutdown
# ------------------------------------------------------------------
shutdown = threading.Event()


def _on_signal(signum, _frame):
    logger.info("Shutdown signal received (%s)", signum)
    shutdown.set()


signal.signal(signal.SIGINT,  _on_signal)
signal.signal(signal.SIGTERM, _on_signal)


# ------------------------------------------------------------------
# Trading-hours helpers
# ------------------------------------------------------------------

def is_trading_hours(now: datetime) -> bool:
    if now.weekday() not in TRADING_DAYS:
        return False
    return MARKET_OPEN <= now.time() <= MARKET_CLOSE


def seconds_until_next_open(now: datetime) -> int:
    candidate = now
    for _ in range(8):
        opening = candidate.replace(
            hour=MARKET_OPEN.hour, minute=MARKET_OPEN.minute,
            second=0, microsecond=0,
        )
        if opening > now and opening.weekday() in TRADING_DAYS:
            return max(int((opening - now).total_seconds()), 60)
        candidate += timedelta(days=1)
    return 3600


# ------------------------------------------------------------------
# Async strategy runner (M-2: runs in a daemon thread so the scrape
# cycle is never blocked by strategy computation)
# ------------------------------------------------------------------

def _run_strategy_thread(strat_key: str, tase_live_index: float = 0.0) -> None:
    try:
        result = strategy_engine.run_strategy(tase_live_index=tase_live_index)
        if result:
            db.state_set(strat_key)
            logger.info("Strategy saved — state marker set")
        else:
            logger.warning("Strategy returned False")
    except Exception as se:
        logger.error("Strategy engine error: %s", se, exc_info=True)
def recover_session(pw, browser, context, page):
    try:
        page.reload(wait_until="networkidle", timeout=PAGE_TIMEOUT)
        time.sleep(RENDER_WAIT)
        if _get_expiry_dates(page):
            logger.info("Session recovered via reload")
            return browser, context, page
    except Exception:
        pass

    logger.warning("Full browser restart...")
    saved_cookies = []
    try:
        saved_cookies = context.cookies()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass
    browser, context, page = launch_browser(pw)
    if saved_cookies:
        try:
            context.add_cookies(saved_cookies)
            logger.info("Restored %d cookies after recovery",
                        len(saved_cookies))
        except Exception:
            pass
    return browser, context, page


# ------------------------------------------------------------------
# TASE index API — TA-35 live data fetched via Playwright (same
# session that already passed the Imperva WAF).  This gives us the
# REAL opening price for settlement and the live last-traded value,
# directly from the exchange — no Yahoo proxy needed.
# ------------------------------------------------------------------
def _get_tase_last_rate(page=None) -> float:
    """Get the live TA-35 index value from the latest Supabase snapshot.

    TASE embeds the live index inside the Put/Call data (UnderlingAsset_call),
    which run_cycle injects into every row.  Reading it back from Supabase
    gives us the authoritative TASE value without a separate API call
    (the standalone TASE index endpoint is blocked by Imperva WAF).

    `page` is accepted for signature compatibility but unused.
    Returns 0.0 on failure.
    """
    try:
        base = os.environ.get("SUPABASE_URL", "").rstrip("/")
        key = os.environ.get("SUPABASE_KEY", "")
        if not base or not key:
            return 0.0
        import httpx as _httpx
        url = (f"{base}/rest/v1/tase_putcall"
               f"?select=underlingasset_call&order=id.desc&limit=20")
        r = _httpx.get(url, headers={"apikey": key,
                                     "Authorization": f"Bearer {key}"},
                       timeout=10)
        if r.status_code in (200, 206):
            for row in r.json():
                raw = row.get("underlingasset_call")
                if raw in (None, "", 0):
                    continue
                try:
                    v = float(str(raw).replace(",", ""))
                    if TA35_MIN <= v <= TA35_MAX:
                        return v
                except (ValueError, TypeError):
                    continue
    except Exception as e:
        logger.warning("_get_tase_last_rate error: %s", e)
    return 0.0


# ------------------------------------------------------------------
# TASE API helpers — Put/Call data
# ------------------------------------------------------------------

def _get_expiry_dates(page, max_retries: int = 3) -> list:
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
        wait = min(5 * (2 ** (attempt - 1)), 45)  # 5s, 10s, 20s
        logger.warning("Expiry-dates API (attempt %d/%d): %s — retry in %ds",
                       attempt, max_retries, result["error"], wait)
        if attempt < max_retries:
            time.sleep(wait)

    if result.get("error"):
        logger.warning("Expiry-dates API failed after %d attempts: %s",
                       max_retries, result["error"])
        return []

    items = (result.get("data") or {}).get(
        "DerivativeExpirationDateItems", []
    )

    # Accept any weekly expiry from today through the next ~10 days.
    # This handles the LAST-TRADING-DAY case (e.g. Friday after 09:30)
    # where this week's expiries already settled and TASE only returns
    # next week's.  A sliding window from today (instead of fixed
    # Mon-Fri of the current ISO week) prevents the "empty list" bug
    # that caused 4 consecutive failures on Fri 29/05.
    today = datetime.now(TZ_ISRAEL).date()
    window_end = today + timedelta(days=10)

    dates = []
    for it in items:
        if it.get("ExpirationDateType") != "01":
            continue
        raw = it.get("Date", "")
        try:
            d = date(int(raw[6:10]), int(raw[3:5]), int(raw[0:2]))
            if today <= d <= window_end:
                dates.append(d)
        except (ValueError, IndexError):
            continue
    return sorted(dates)


def _fetch_all_pages(page, expr_date_iso: str):
    all_items = []
    page_num = 1
    trade_date = None
    asset_name = None
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

        # Capture underlying asset value.  TASE embeds the live TA-35
        # index inside EACH item as "UnderlingAsset_call"/"_put" — this
        # is the authoritative exchange value (e.g. "4423.44"), present
        # on every row.  We read it from the first item that has it.
        if underlying_value is None and items:
            for it in items:
                for field in ("UnderlingAsset_call", "UnderlingAsset_put",
                              "UnderlingAsset_Call", "UnderlingAsset_Put"):
                    raw = it.get(field)
                    if raw in (None, "", 0):
                        continue
                    try:
                        v = float(str(raw).replace(",", ""))
                        if TA35_MIN <= v <= TA35_MAX:
                            underlying_value = v
                            logger.info(
                                "   TA-35 from TASE item field '%s': %.2f",
                                field, v)
                            break
                    except (ValueError, TypeError):
                        continue
                if underlying_value is not None:
                    break

        if not items:
            break

        # Log ALL keys from the first item (once) so we know exactly
        # what TASE returns — especially bid/ask fields we might be
        # discarding.  This is a diagnostic log, not a code change.
        if page_num == 1 and len(all_items) == 0 and items:
            item_keys = sorted(items[0].keys())
            logger.info("   ITEM KEYS (%d fields): %s", len(item_keys), item_keys)

        all_items.extend(items)
        logger.info("   page %d: %d records (%d/%d)",
                     page_num, len(items), len(all_items), total)

        if len(all_items) >= total:
            break
        page_num += 1
        # Minimal pause between pages of SAME expiry — TASE WAF is
        # tolerant of intra-expiry pagination. Inter-expiry delay is
        # still 3-5s (random) in run_cycle.
        time.sleep(0.15)

    return all_items, trade_date, asset_name, underlying_value


# ------------------------------------------------------------------
# Single fetch cycle
# ------------------------------------------------------------------

def run_cycle(page, cycle_time: datetime):
    date_str = cycle_time.strftime("%Y-%m-%d")
    time_str = cycle_time.strftime("%H:%M")

    expiry_dates = _get_expiry_dates(page)
    if not expiry_dates:
        logger.warning("No expiry dates — skipping cycle")
        return {"ok": False, "rows": 0, "expiries": 0}

    logger.info("Expiry dates: %s",
                [d.isoformat() for d in expiry_dates])

    # ── Live TA-35 index.
    # TASE's putvscall API exposes an UnderlingAsset_call field, but in
    # practice it arrives empty — so Yahoo Finance is the working source.
    # We fetch it ONCE up front so it's always available to inject into
    # every row (the column must never be null for the dashboard/engine).
    # If a future TASE response DOES contain a real underlying, the
    # per-expiry loop below overrides the cycle value with it.
    cycle_index_source = "yahoo_fallback"
    cycle_underlying = 0.0
    try:
        import strategy_engine as _se
        cycle_underlying = _se._fetch_index_from_yahoo()
    except Exception as ye:
        logger.warning("Yahoo index fetch failed: %s", ye)

    success_count = 0
    total_rows = 0

    for idx, exp_date in enumerate(expiry_dates):
        exp_iso = exp_date.isoformat()
        wd = exp_date.weekday()
        en, he = DAY_NAMES.get(wd, (f"Day{wd}", f"Day{wd}"))

        logger.info(">> %s (%s) %s", en, he, exp_iso)

        items, trade_dt, asset, underlying = _fetch_all_pages(
            page, exp_iso,
        )

        # If TASE actually provided a real underlying, prefer it (it's
        # the authoritative exchange value).
        if underlying and underlying > 0:
            if cycle_index_source != "tase":
                logger.info("TA-35 from TASE (authoritative): %.2f", underlying)
            cycle_underlying = underlying
            cycle_index_source = "tase"

        # Inject underlying into every row so the column is populated
        # for strategy_engine / dashboard.
        effective_underlying = underlying or cycle_underlying
        if effective_underlying and items:
            for item in items:
                if not item.get("UnderlingAsset_Call"):
                    item["UnderlingAsset_Call"] = effective_underlying
                if not item.get("UnderlingAsset_Put"):
                    item["UnderlingAsset_Put"] = effective_underlying

        if items:
            # Sanity checks — warn on suspicious data
            bad = 0
            for item in items:
                sc = item.get("ExpirationPrice_Call")
                sp = item.get("ExpirationPrice_Put")
                if sc is not None and (not isinstance(sc, (int, float)) or sc <= 0):
                    bad += 1
                if sp is not None and (not isinstance(sp, (int, float)) or sp <= 0):
                    bad += 1
            if bad:
                logger.warning("   ⚠ %d items with invalid strike prices", bad)
            if len(items) > 500:
                logger.warning("   ⚠ Unusually large response: %d items", len(items))

            if db.upsert_items(date_str, time_str, exp_iso,
                               trade_dt, items):
                success_count += 1
            total_rows += len(items)
            logger.info("   [OK] %d records", len(items))
        else:
            db.upsert_no_trading(date_str, time_str, exp_iso)
            logger.info("   [EMPTY] no trading")

        if idx < len(expiry_dates) - 1:
            time.sleep(random.uniform(3, 5))

    # Only clean up old snapshots when ALL expiries succeeded.  A partial
    # cycle would otherwise erase older complete snapshots and leave the
    # strategy engine with an incomplete view.
    if success_count == len(expiry_dates) and success_count > 0:
        db._clear_old_snapshots(date_str, time_str)
    elif 0 < success_count < len(expiry_dates):
        logger.warning(
            "Partial cycle (%d/%d expiries) — skipping cleanup to preserve "
            "previous complete snapshot",
            success_count, len(expiry_dates))

    return {
        "ok": success_count > 0,
        "rows": total_rows,
        "expiries": len(expiry_dates),
        "expiry_dates": expiry_dates,  # actual TASE trading days this week
        "full_success": success_count == len(expiry_dates),
        "index_value": cycle_underlying,
        "index_source": cycle_index_source,  # "tase" | "yahoo_fallback"
    }


def is_last_trading_day_of_week(now: datetime, expiry_dates: list) -> bool:
    """
    True if today is the LAST trading day of the current ISO week.

    Two-tier detection:
      1. PRIMARY: TASE expiry dates as ground truth — the last expiry
         of the week is the last trading day.  Robust to one-off holidays
         (e.g., Pesach week with no Friday expiry).
      2. FALLBACK (no expiry data cached yet): scan the calendar — today
         is the last trading day iff today is a trading day AND no later
         day in this ISO week is a trading day per TRADING_DAYS.
    """
    today = now.date()
    this_week = (now.isocalendar()[0], now.isocalendar()[1])

    # ── PRIMARY: TASE expiry dates ──
    if expiry_dates:
        week_expiries = [
            d for d in expiry_dates
            if (d.isocalendar()[0], d.isocalendar()[1]) == this_week
        ]
        if week_expiries:
            return today == max(week_expiries)
        # expiry list exists but none in this week → no trading this week
        return False

    # ── FALLBACK: calendar scan based on TRADING_DAYS ──
    if today.weekday() not in TRADING_DAYS:
        return False
    # Walk forward day by day; if any later day in this ISO week is a
    # trading day, today is NOT the last.
    for days_ahead in range(1, 8):
        future = today + timedelta(days=days_ahead)
        if (future.isocalendar()[0], future.isocalendar()[1]) != this_week:
            break  # crossed into next ISO week
        if future.weekday() in TRADING_DAYS:
            return False
    return True


# ------------------------------------------------------------------
# Data-quality monitoring
# ------------------------------------------------------------------

def assess_cycle_quality(cycle_result: dict, recent_rows: list) -> list:
    """Inspect a cycle result and recent history; return a list of
    human-readable Hebrew issue strings (empty = healthy).

    Detects:
      • Partial expiry collection (not all expiries succeeded)
      • Row-count anomaly (this cycle collected far fewer rows than
        the recent average — possible truncated/blocked response)

    Note: the TA-35 index normally comes from Yahoo (TASE's putvscall
    API returns an empty UnderlingAsset field), so Yahoo usage is NOT
    treated as an anomaly.
    """
    issues = []

    # 1. Partial expiry collection
    if not cycle_result.get("full_success", True):
        issues.append(
            f"איסוף חלקי — לא כל הפקיעות נקלטו "
            f"({cycle_result.get('expiries', 0)} פקיעות)")

    # 2. Row-count anomaly vs recent average
    rows_now = cycle_result.get("rows", 0)
    if recent_rows and rows_now > 0:
        avg = sum(recent_rows) / len(recent_rows)
        if avg > 0 and rows_now < avg * 0.6:
            issues.append(
                f"ירידה חדה בכמות נתונים — {rows_now} שורות "
                f"(ממוצע אחרון {avg:.0f})")

    return issues


# ------------------------------------------------------------------
# EOD archival — idempotent, restart-safe
# ------------------------------------------------------------------

def _archive_eod_snapshot(today_iso: str) -> None:
    """
    Archive the day's last (EOD) option-chain snapshot to the history table,
    for knowledge retention. Idempotent and restart-safe: guarded by a
    persistent pipeline_state marker (`history_copied:<date>`), so it can fire
    from EITHER the last in-market cycle OR the off-hours block after close —
    a single missed/failed cycle no longer loses the day. copy_to_history reads
    the live table, which still holds the EOD snapshot until the next morning's
    first successful cycle, so the evening window is a safe catch-up.
    """
    marker = f"history_copied:{today_iso}"
    try:
        if db.state_is_set(marker):
            return
        if db.copy_to_history():
            db.state_set(marker)
            logger.info("*** EOD snapshot archived to history (%s) ***", today_iso)
    except Exception as e:
        logger.error("EOD archive error (%s): %s", today_iso, e)


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def main():
    logger.info("=" * 55)
    logger.info("  TASE Pipeline — Render Background Worker")
    logger.info("  Interval : %d min", FETCH_INTERVAL // 60)
    logger.info("=" * 55)

    health_server.start()

    if not db.test_connection():
        logger.critical("Cannot connect to Supabase — exiting")
        sys.exit(1)

    browser_born = time.monotonic()
    strategy_triggered_week = None   # track which week the strategy ran
    settled_today = None             # track which date we settled
    weekly_summary_week = None       # track which week got summary
    weekly_backup_week = None        # track which week got backup
    daily_summary_date = None        # track which date got daily summary
    current_day = None               # track current day for counter resets
    consecutive_failures = 0         # crash detection counter
    crash_alerted = False            # True once a crash alert was sent for
                                     # the current failure streak (prevents
                                     # re-alerting every cycle)
    daily_cycles = 0                 # cycles completed today
    daily_rows = 0                   # rows collected today
    daily_errors = 0                 # errors today
    daily_expiries = 0               # expiry dates seen today
    last_known_expiries: list = []   # cache of TASE expiry dates this week
    weekly_summary_due_at = None     # datetime when post-close summary fires
    current_week = datetime.now(TZ_ISRAEL).isocalendar()[1]  # init before loop
                                     # so the off-hours weekly-summary block can
                                     # reference it even on a fresh off-hours start
    recent_row_counts: list = []     # rolling window of last N cycles' row counts
    quality_alert_date = None        # date we last sent a data-quality alert
                                     # (rate-limit: at most one per day)

    with sync_playwright() as pw:
        browser, context, page = _browser.launch(pw, HEADLESS)
        logger.info("Browser ready")

        while not shutdown.is_set():
            now = datetime.now(TZ_ISRAEL)

            # ── Off-hours block ──────────────────────────────────────
            if not is_trading_hours(now):
                # EOD archival catch-up: on a trading day, once the market has
                # closed, archive the day's EOD snapshot if it wasn't archived
                # by the last in-market cycle (missed/failed cycle, restart…).
                # Idempotent via the persistent marker; the live table still
                # holds the EOD snapshot until tomorrow's first cycle.
                if now.weekday() in TRADING_DAYS and now.time() > MARKET_CLOSE:
                    _archive_eod_snapshot(now.strftime("%Y-%m-%d"))

                # Fire post-close weekly summary if due
                if (weekly_summary_due_at is not None
                        and now >= weekly_summary_due_at
                        and weekly_summary_week != current_week):
                    week_key = (f"weekly_summary_sent:"
                                f"{now.isocalendar()[0]}-W{current_week:02d}")
                    if db.state_is_set(week_key):
                        logger.info(
                            "Weekly summary already sent (state marker %s) — skipping",
                            week_key)
                        weekly_summary_week   = current_week
                        weekly_summary_due_at = None
                    else:
                        try:
                            logger.info(
                                "*** Sending post-close weekly summary "
                                "(week %d, %d min after close) ***",
                                current_week,
                                int((now - weekly_summary_due_at).total_seconds() / 60),
                            )
                            stats = strategy_engine.get_weekly_stats(
                                current_week, now.isocalendar()[0])
                            if stats and stats.get("trades", 0) > 0:
                                telegram_bot.alert_weekly_summary(stats)
                            else:
                                logger.info("Weekly summary: no settled trades")
                            db.state_set(week_key)
                            weekly_summary_week   = current_week
                            weekly_summary_due_at = None
                        except Exception as we:
                            logger.error("Weekly summary error: %s", we, exc_info=True)
                            weekly_summary_due_at = None  # don't retry-loop

                # Decide how long to sleep
                if weekly_summary_due_at is not None and now < weekly_summary_due_at:
                    wait = max(int((weekly_summary_due_at - now).total_seconds()), 30)
                    logger.info(
                        "Outside trading hours — waiting %d min for "
                        "post-close weekly summary at %s",
                        wait // 60,
                        weekly_summary_due_at.strftime("%H:%M"))
                else:
                    wait    = seconds_until_next_open(now)
                    en, _   = DAY_NAMES.get(now.weekday(), ("?", "?"))
                    logger.info("Outside trading hours (%s %s). Sleeping %d min...",
                                en, now.strftime("%H:%M"), wait // 60)

                health_server.update(
                    status="sleeping",
                    consecutive_failures=0,
                    cycles_today=daily_cycles,
                )
                shutdown.wait(timeout=wait)
                continue

            # ── Reset daily counters on new day ──────────────────────
            today_iso = now.strftime("%Y-%m-%d")
            if current_day != today_iso:
                daily_cycles = daily_rows = daily_errors = daily_expiries = 0
                current_day  = today_iso

            # ── Periodic browser restart (preserve cookies/session) ──
            if time.monotonic() - browser_born > BROWSER_RESTART:
                logger.info("Restarting browser (age limit)")
                saved_cookies = []
                try:
                    saved_cookies = context.cookies()
                except Exception:
                    pass
                try:
                    browser.close()
                except Exception:
                    pass
                browser, context, page = _browser.launch(pw, HEADLESS)
                if saved_cookies:
                    try:
                        context.add_cookies(saved_cookies)
                        logger.info("Restored %d cookies after restart",
                                    len(saved_cookies))
                    except Exception:
                        pass
                browser_born = time.monotonic()

            logger.info("-" * 50)
            logger.info("Cycle start: %s", now.strftime("%Y-%m-%d %H:%M"))
            current_week = now.isocalendar()[1]

            try:
                cycle_result = tase_api.run_cycle(page, now)
                ok           = cycle_result["ok"]

                if ok:
                    daily_cycles  += 1
                    daily_rows    += cycle_result["rows"]
                    daily_expiries = max(daily_expiries, cycle_result["expiries"])
                    cycle_expiries = cycle_result.get("expiry_dates") or []
                    if cycle_expiries:
                        last_known_expiries = cycle_expiries

                    # ── Data-quality monitoring ──
                    # Assess this cycle BEFORE adding it to the rolling
                    # window (so the anomaly check compares against the
                    # prior baseline, not itself).
                    quality_issues = assess_cycle_quality(
                        cycle_result, recent_row_counts)
                    if quality_issues and quality_alert_date != today_iso:
                        logger.warning("Data-quality issues: %s", quality_issues)
                        try:
                            telegram_bot.alert_data_quality(quality_issues)
                            quality_alert_date = today_iso  # at most 1/day
                        except Exception as qe:
                            logger.error("Quality alert failed: %s", qe)
                    # Update rolling window (keep last 10 cycles)
                    rows_now = cycle_result.get("rows", 0)
                    if rows_now > 0:
                        recent_row_counts.append(rows_now)
                        if len(recent_row_counts) > 10:
                            recent_row_counts.pop(0)

                # Weekly heartbeat: first successful cycle of the week
                # after 10:00, on the first trading day.  A quick
                # "system alive" Telegram so the user knows data is
                # flowing before the strategy fires at 12:00.
                if (ok
                        and now.time() >= SETTLEMENT_AFTER  # 10:00
                        and strategy_triggered_week != current_week):
                    hb_key = f"weekly_heartbeat:{now.isocalendar()[0]}-W{current_week:02d}"
                    if not db.state_is_set(hb_key):
                        if not db.has_history_earlier_this_week(today_iso):
                            logger.info("*** Sending weekly heartbeat ***")
                            _hb_index = _get_tase_last_rate(page)
                            if _hb_index <= 0:
                                try:
                                    _hb_index = strategy_engine._fetch_index_from_yahoo()
                                except Exception:
                                    pass
                            telegram_bot.alert_weekly_heartbeat(
                                today_iso, cycle_result["rows"],
                                cycle_result["expiries"],
                                index_value=_hb_index,
                            )
                            db.state_set(hb_key)

                # Weekly strategy trigger: first cycle with data
                # inside the 12:00-13:00 window, on the FIRST trading
                # day of the week.  We must verify day-of-week because
                # `strategy_triggered_week` is in-memory and clears on
                # restart, and `_strategies_exist_for_week` is False
                # any time the table was wiped.  Without this gate,
                # a Friday restart re-fires the strategy with Friday
                # prices instead of Monday's.
                if (ok
                        and STRATEGY_WINDOW_OPEN <= now.time() <= STRATEGY_WINDOW_CLOSE
                        and strategy_triggered_week != current_week):
                    strat_key = (f"strategy_triggered:"
                                 f"{now.isocalendar()[0]}-W{current_week:02d}")
                    if db.state_is_set(strat_key):
                        logger.info(
                            "Strategy already triggered this week "
                            "(state marker %s) — skipping", strat_key)
                        strategy_triggered_week = current_week
                    elif db.has_history_earlier_this_week(today_iso):
                        logger.info(
                            "Not the first trading day of week %d "
                            "(history has earlier rows) — skipping strategy trigger",
                            current_week)
                        strategy_triggered_week = current_week
                    else:
                        en, _ = DAY_NAMES.get(now.weekday(), ("?", "?"))
                        logger.info(
                            "*** %s %s — triggering Iron Condor strategy "
                            "(week %d) ***", en, now.strftime("%H:%M"), current_week)
                        _tase_idx = _get_tase_last_rate(page)
                        threading.Thread(
                            target=_run_strategy_thread,
                            args=(strat_key, _tase_idx),
                            daemon=True,
                            name="strategy",
                        ).start()
                        strategy_triggered_week = current_week

                # ── Settlement ────────────────────────────────────────
                if (ok
                        and now.time() >= SETTLEMENT_AFTER
                        and settled_today != today_iso):
                    settle_key = f"settlement_done:{today_iso}"
                    if db.state_is_set(settle_key):
                        logger.info(
                            "Settlement already done for %s (state marker) — skipping",
                            today_iso)
                        settled_today = today_iso
                    else:
                        try:
                            if strategy_engine.has_unsettled_strategies(today_iso):
                                logger.info("*** Settling expiry %s ***", today_iso)
                                # Settlement uses the opening price. The standalone
                                # TASE index API (with openRate) is WAF-blocked, so
                                # settle_expiry falls back to Yahoo's regularMarketOpen.
                                result = strategy_engine.settle_expiry(today_iso)
                                if result:
                                    db.state_set(settle_key)
                                    settled_today = today_iso
                            else:
                                logger.info("No unsettled strategies for %s — skipping",
                                            today_iso)
                                db.state_set(settle_key)
                                settled_today = today_iso
                        except Exception as se:
                            logger.error("Settlement error: %s", se, exc_info=True)

                # ── End-of-day & end-of-week actions ─────────────────
                last_cycle = tase_api.is_last_cycle(now, FETCH_INTERVAL)
                last_day   = tase_api.is_last_trading_day_of_week(
                    now, last_known_expiries)

                # Schedule weekly summary 1 hour after close
                if (ok and last_cycle and last_day
                        and weekly_summary_week != current_week
                        and weekly_summary_due_at is None):
                    close_dt = now.replace(
                        hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute,
                        second=0, microsecond=0)
                    weekly_summary_due_at = close_dt + timedelta(hours=1)
                    logger.info("*** Scheduled weekly summary for %s ***",
                                weekly_summary_due_at.strftime("%Y-%m-%d %H:%M"))

                if ok and last_cycle:
                    # Weekly backup
                    if last_day and weekly_backup_week != current_week:
                        try:
                            logger.info("*** Weekly backup to storage ***")
                            if db.backup_to_storage():
                                weekly_backup_week = current_week
                        except Exception as be:
                            logger.error("Backup error: %s", be, exc_info=True)

                    # Daily summary
                    if daily_summary_date != today_iso:
                        daily_key = f"daily_summary_sent:{today_iso}"
                        if db.state_is_set(daily_key):
                            logger.info("Daily summary already sent for %s — skipping",
                                        today_iso)
                            daily_summary_date = today_iso
                        else:
                            try:
                                logger.info("*** Sending daily summary ***")
                                telegram_bot.alert_daily_summary(
                                    today_iso, daily_cycles, daily_rows,
                                    daily_expiries, daily_errors,
                                )
                                db.state_set(daily_key)
                                daily_summary_date = today_iso
                            except Exception as de:
                                logger.error("Daily summary error: %s", de)

                    # Copy to history (EOD) — idempotent + restart-safe; the
                    # off-hours block also catches this if the cycle is missed.
                    _archive_eod_snapshot(today_iso)

                # ── Failure handling & recovery ───────────────────────
                # Distinguish failure types (don't treat a stale/empty feed like
                # a dead browser):
                #   • transport failure (couldn't fetch the expiry list) →
                #     recover the session + escalate to a crash alert.
                #   • data-quality / empty (got the list but data was stale,
                #     CRITICAL, or no-trading) → transport is healthy, so DON'T
                #     recover the browser and DON'T crash-alert. The throttled
                #     data-quality alert already fired inside run_cycle.
                transport_ok = cycle_result.get("transport_ok", ok)
                if ok or transport_ok:
                    consecutive_failures = 0
                    crash_alerted        = False
                    if not ok:
                        reason = ("data-quality CRITICAL"
                                  if cycle_result.get("had_critical")
                                  else "no data stored (stale/empty/no-trading)")
                        logger.info(
                            "Cycle stored nothing (%s) — transport healthy, "
                            "no session recovery", reason)
                else:
                    daily_errors        += 1
                    consecutive_failures += 1
                    logger.warning("Transport failure (%d consecutive) — recovering session",
                                   consecutive_failures)
                    if consecutive_failures >= 3 and not crash_alerted:
                        telegram_bot.alert_crash(
                            f"{consecutive_failures} consecutive transport failures")
                        crash_alerted = True
                    browser, context, page = _browser.recover(
                        pw, browser, context, page, HEADLESS)

                health_server.update(
                    status="running",
                    last_cycle=now.isoformat(),
                    last_ok=ok,
                    consecutive_failures=consecutive_failures,
                    cycles_today=daily_cycles,
                )

            except Exception as e:
                daily_errors        += 1
                consecutive_failures += 1
                logger.error("Cycle error (%d consecutive): %s",
                             consecutive_failures, e, exc_info=True)
                if consecutive_failures >= 3 and not crash_alerted:
                    telegram_bot.alert_crash(str(e))
                    crash_alerted = True
                try:
                    browser, context, page = _browser.recover(
                        pw, browser, context, page, HEADLESS)
                except Exception as e2:
                    # H-1: recovery itself failed — shut down cleanly so
                    # Render restarts the container rather than spinning
                    # forever on a dead Playwright session.
                    logger.critical("Recovery failed: %s", e2)
                    telegram_bot.alert_crash(f"Recovery failed: {e2}")
                    shutdown.set()
                    break

                health_server.update(
                    status="error",
                    last_cycle=now.isoformat(),
                    last_ok=False,
                    consecutive_failures=consecutive_failures,
                    cycles_today=daily_cycles,
                )

            logger.info("Sleeping %d min...", FETCH_INTERVAL // 60)
            shutdown.wait(timeout=FETCH_INTERVAL)

    logger.info("Shutting down...")
    try:
        browser.close()
    except Exception:
        pass
    logger.info("Pipeline stopped.")


if __name__ == "__main__":
    main()
