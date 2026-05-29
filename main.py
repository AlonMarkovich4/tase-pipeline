"""
TASE Real-Time Put/Call Pipeline — Render Background Worker
============================================================
Fetches options data every 15 minutes during Israeli trading
hours (Mon-Fri 09:30-17:30) and syncs to Supabase.

Uses Playwright + page.evaluate(fetch()) to bypass Imperva WAF.
"""

import os
import sys
import signal
import logging
import time
import threading
import random
from datetime import datetime, timedelta, date
from playwright.sync_api import sync_playwright

import database as db
import strategy_engine
import telegram_bot
from config import (
    TZ_ISRAEL, TRADING_DAYS, MARKET_OPEN, MARKET_CLOSE, DAY_NAMES,
    STRATEGY_WINDOW_OPEN, STRATEGY_WINDOW_CLOSE,
    SETTLEMENT_AFTER, WEEKLY_SUMMARY_TIME,
    BROWSER_RESTART_SECONDS, FETCH_INTERVAL_MINUTES,
)

# ------------------------------------------------------------------
# Config (local to pipeline)
# ------------------------------------------------------------------
HEADLESS        = os.environ.get("HEADLESS", "true").lower() == "true"
FETCH_INTERVAL  = int(os.environ.get("FETCH_INTERVAL_MINUTES",
                                      str(FETCH_INTERVAL_MINUTES))) * 60
PAGE_TIMEOUT    = 45_000
RENDER_WAIT     = 6
BROWSER_RESTART = BROWSER_RESTART_SECONDS
WEEKLY_SUMMARY  = WEEKLY_SUMMARY_TIME

API_URL    = "https://api.tase.co.il/api/derivatives/putvscall"
EXPIRY_URL = "https://api.tase.co.il/api/derivatives/fltrputvscallexpdates"
TASE_PAGE  = (
    "https://market.tase.co.il/he/market_data/derivatives/01/"
    "major_data/putvscall"
    "?dType=2&updType=1&inQType=3&objId=01&qType=3"
)

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
# Health-check HTTP endpoint (Render pings PORT to verify liveness)
# ------------------------------------------------------------------
import json
from http.server import HTTPServer, BaseHTTPRequestHandler

_health_state: dict = {
    "status": "starting",
    "last_cycle": None,
    "last_ok": None,
    "consecutive_failures": 0,
    "cycles_today": 0,
}


class _HealthHandler(BaseHTTPRequestHandler):
    """Minimal JSON health endpoint — GET / or GET /health."""

    def do_GET(self):
        healthy = (_health_state["status"] in ("running", "sleeping")
                   and _health_state["consecutive_failures"] < 5)
        code = 200 if healthy else 503
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(json.dumps(_health_state, default=str).encode())

    def log_message(self, *_args):
        pass  # suppress access logs


def _start_health_server():
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _HealthHandler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info("Health-check server listening on :%d", port)

# ------------------------------------------------------------------
# Trading hours
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
# Browser lifecycle
# ------------------------------------------------------------------

def launch_browser(pw):
    browser = pw.chromium.launch(
        headless=HEADLESS,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        locale="he-IL",
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 (KHTML, like Gecko) "
            "Chrome/124.0.0.0 Safari/537.36"
        ),
    )
    page = context.new_page()
    navigate_tase(page)
    return browser, context, page


def navigate_tase(page):
    try:
        page.goto(TASE_PAGE, wait_until="networkidle",
                  timeout=PAGE_TIMEOUT)
        logger.info("TASE page loaded (networkidle)")
    except Exception:
        logger.warning("networkidle timeout — using domcontentloaded")
        page.goto(TASE_PAGE, wait_until="domcontentloaded",
                  timeout=PAGE_TIMEOUT)
        time.sleep(RENDER_WAIT + 4)
    time.sleep(RENDER_WAIT)


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
# TASE API helpers
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

        # Capture underlying asset value from top-level response
        if underlying_value is None:
            # Log all top-level keys on first page for debugging
            if page_num == 1:
                top_keys = [k for k in data.keys() if k != "Items"]
                logger.info("   API top-level keys: %s", top_keys)
                # Log values of non-Items keys (for finding base index)
                for k in top_keys:
                    v = data[k]
                    if isinstance(v, (int, float)) and v > 0:
                        logger.info("   API %s = %s", k, v)

            # Try common field names for underlying asset value
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

    # ── Fetch live TA-35 once per cycle from Yahoo (independent of TASE).
    # We inject this into every row so the underlingasset_* columns are
    # populated (TASE itself almost never returns this field).  This is
    # the live index value at cycle-start time.
    cycle_underlying = 0.0
    try:
        import strategy_engine as _se
        cycle_underlying = _se._fetch_index_from_yahoo()
    except Exception as ye:
        logger.warning("Live index fetch failed: %s", ye)

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

        # Inject underlying asset value into each item so it's
        # stored in Supabase and available for strategy_engine /
        # dashboard.  Priority: TASE-provided value, else Yahoo live.
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
    }


def is_last_cycle(now: datetime) -> bool:
    """Check if the next cycle would be outside trading hours."""
    next_cycle = now + timedelta(seconds=FETCH_INTERVAL)
    return next_cycle.time() > MARKET_CLOSE


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
# Main loop
# ------------------------------------------------------------------

def main():
    logger.info("=" * 55)
    logger.info("  TASE Pipeline — Render Background Worker")
    logger.info("  Interval : %d min", FETCH_INTERVAL // 60)
    logger.info("=" * 55)

    _start_health_server()

    if not db.test_connection():
        logger.critical("Cannot connect to Supabase — exiting")
        sys.exit(1)

    browser_born = time.monotonic()
    strategy_triggered_week = None   # track which week the strategy ran
    settled_today = None             # track which date we settled
    weekly_summary_week = None       # track which week got summary
    weekly_backup_week = None        # track which week got backup
    daily_summary_date = None        # track which date got daily summary
    history_copied_date = None       # track which date got copied to history
    current_day = None               # track current day for counter resets
    consecutive_failures = 0         # crash detection counter
    daily_cycles = 0                 # cycles completed today
    daily_rows = 0                   # rows collected today
    daily_errors = 0                 # errors today
    daily_expiries = 0               # expiry dates seen today
    last_known_expiries: list = []   # cache of TASE expiry dates this week
    weekly_summary_due_at = None     # datetime when post-close summary fires

    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw)
        logger.info("Browser ready")

        while not shutdown.is_set():
            now = datetime.now(TZ_ISRAEL)

            if not is_trading_hours(now):
                # ── Post-close weekly summary window ──
                # If today was the last trading day of this week and we
                # haven't sent the summary yet, wait until 1h after close.
                if (weekly_summary_due_at is not None
                        and now >= weekly_summary_due_at
                        and weekly_summary_week != current_week):
                    week_key = f"weekly_summary_sent:{now.isocalendar()[0]}-W{current_week:02d}"
                    if db.state_is_set(week_key):
                        logger.info(
                            "Weekly summary already sent (state marker %s) — skipping",
                            week_key)
                        weekly_summary_week = current_week
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
                            weekly_summary_week = current_week
                            weekly_summary_due_at = None
                        except Exception as we:
                            logger.error("Weekly summary error: %s",
                                         we, exc_info=True)
                            weekly_summary_due_at = None  # don't retry-loop

                # If summary is scheduled but not yet due, wake at that time
                if (weekly_summary_due_at is not None
                        and now < weekly_summary_due_at):
                    wait = max(int((weekly_summary_due_at - now).total_seconds()), 30)
                    logger.info(
                        "Outside trading hours — waiting %d min for "
                        "post-close weekly summary at %s",
                        wait // 60,
                        weekly_summary_due_at.strftime("%H:%M"))
                else:
                    wait = seconds_until_next_open(now)
                    en, _ = DAY_NAMES.get(now.weekday(), ("?", "?"))
                    logger.info(
                        "Outside trading hours (%s %s). "
                        "Sleeping %d min...",
                        en, now.strftime("%H:%M"), wait // 60,
                    )
                _health_state.update({
                    "status": "sleeping",
                    "last_cycle": _health_state.get("last_cycle"),
                    "last_ok": _health_state.get("last_ok"),
                    "consecutive_failures": 0,
                    "cycles_today": daily_cycles,
                })
                shutdown.wait(timeout=wait)
                continue

            # Reset daily counters on new day
            today_iso = now.strftime("%Y-%m-%d")
            if current_day != today_iso:
                daily_cycles = 0
                daily_rows = 0
                daily_errors = 0
                daily_expiries = 0
                current_day = today_iso

            # periodic browser restart (preserve cookies/session)
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
                browser, context, page = launch_browser(pw)
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
            # Check which ISO week we're in
            current_week = now.isocalendar()[1]

            try:
                cycle_result = run_cycle(page, now)
                ok = cycle_result["ok"]

                # Track daily stats
                if ok:
                    daily_cycles += 1
                    daily_rows += cycle_result["rows"]
                    daily_expiries = max(daily_expiries,
                                         cycle_result["expiries"])
                    # Cache TASE expiry dates — used to detect last trading day
                    cycle_expiries = cycle_result.get("expiry_dates") or []
                    if cycle_expiries:
                        last_known_expiries = cycle_expiries

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
                    strat_key = f"strategy_triggered:{now.isocalendar()[0]}-W{current_week:02d}"
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
                        # Mark in-memory so we don't re-check every cycle this week
                        strategy_triggered_week = current_week
                    else:
                        en, _ = DAY_NAMES.get(now.weekday(), ("?", "?"))
                        logger.info("*** %s %s — triggering Iron Condor strategy (week %d) ***",
                                    en, now.strftime("%H:%M"), current_week)
                        try:
                            result = strategy_engine.run_strategy()
                            if result:
                                db.state_set(strat_key)
                                strategy_triggered_week = current_week
                                logger.info("Strategy triggered successfully — "
                                            "won't retry this week")
                            else:
                                logger.warning("Strategy returned False — "
                                               "will retry next cycle in window")
                        except Exception as se:
                            logger.error("Strategy engine error: %s — "
                                         "will retry next cycle in window",
                                         se, exc_info=True)

                # Settlement: expiry day after 10:00 (opening price set)
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
                            # Quick check: do strategies exist for today's expiry?
                            has_strategies = strategy_engine.has_unsettled_strategies(today_iso)
                            if has_strategies:
                                logger.info("*** Settling expiry %s ***", today_iso)
                                result = strategy_engine.settle_expiry(today_iso)
                                if result:
                                    db.state_set(settle_key)
                                    settled_today = today_iso
                            else:
                                logger.info("No unsettled strategies for %s — skipping settlement", today_iso)
                                db.state_set(settle_key)  # mark "checked, nothing to settle"
                                settled_today = today_iso  # Don't retry today
                        except Exception as se:
                            logger.error("Settlement error: %s", se, exc_info=True)

                # Weekly summary: schedule 1 hour after market close
                # on the LAST trading day of the week (determined
                # dynamically from TASE expiry dates — works even
                # when Friday is a holiday and Thu is actually last).
                if (ok
                        and is_last_cycle(now)
                        and is_last_trading_day_of_week(now, last_known_expiries)
                        and weekly_summary_week != current_week
                        and weekly_summary_due_at is None):
                    close_dt = now.replace(
                        hour=MARKET_CLOSE.hour, minute=MARKET_CLOSE.minute,
                        second=0, microsecond=0)
                    weekly_summary_due_at = close_dt + timedelta(hours=1)
                    logger.info(
                        "*** Scheduled weekly summary for %s (1h after close) ***",
                        weekly_summary_due_at.strftime("%Y-%m-%d %H:%M"))

                if ok and is_last_cycle(now):
                    # Weekly backup — runs on the actual last trading day
                    if (is_last_trading_day_of_week(now, last_known_expiries)
                            and weekly_backup_week != current_week):
                        try:
                            logger.info("*** Weekly backup to storage ***")
                            if db.backup_to_storage():
                                weekly_backup_week = current_week
                        except Exception as be:
                            logger.error("Backup error: %s", be, exc_info=True)

                    # Daily summary to Telegram
                    if daily_summary_date != today_iso:
                        daily_key = f"daily_summary_sent:{today_iso}"
                        if db.state_is_set(daily_key):
                            logger.info(
                                "Daily summary already sent for %s — skipping",
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

                    if history_copied_date != today_iso:
                        logger.info("*** Last cycle of the day — saving to history ***")
                        if db.copy_to_history():
                            history_copied_date = today_iso
                if not ok:
                    daily_errors += 1
                    consecutive_failures += 1
                    logger.warning("Cycle empty (%d consecutive) — recovering session",
                                   consecutive_failures)
                    if consecutive_failures >= 3:
                        telegram_bot.alert_crash(
                            f"{consecutive_failures} consecutive failures"
                        )
                    browser, context, page = recover_session(
                        pw, browser, context, page
                    )
                else:
                    consecutive_failures = 0

                # Update health state
                _health_state.update({
                    "status": "running",
                    "last_cycle": now.isoformat(),
                    "last_ok": ok,
                    "consecutive_failures": consecutive_failures,
                    "cycles_today": daily_cycles,
                })

            except Exception as e:
                daily_errors += 1
                consecutive_failures += 1
                logger.error("Cycle error (%d consecutive): %s",
                             consecutive_failures, e, exc_info=True)
                if consecutive_failures >= 3:
                    telegram_bot.alert_crash(str(e))
                try:
                    browser, context, page = recover_session(
                        pw, browser, context, page
                    )
                except Exception as e2:
                    logger.critical("Recovery failed: %s", e2)
                    telegram_bot.alert_crash(f"Recovery failed: {e2}")

                _health_state.update({
                    "status": "error",
                    "last_cycle": now.isoformat(),
                    "last_ok": False,
                    "consecutive_failures": consecutive_failures,
                    "cycles_today": daily_cycles,
                })

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
