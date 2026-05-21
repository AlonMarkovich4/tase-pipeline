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
from datetime import datetime, timedelta, date, time as dt_time
from zoneinfo import ZoneInfo
from pathlib import Path

import pandas as pd
from playwright.sync_api import sync_playwright

import database as db
import strategy_engine

# ------------------------------------------------------------------
# Config
# ------------------------------------------------------------------
HEADLESS        = True
FETCH_INTERVAL  = int(os.environ.get("FETCH_INTERVAL_MINUTES", "15")) * 60
PAGE_TIMEOUT    = 45_000
RENDER_WAIT     = 6
BROWSER_RESTART = 6 * 3600  # restart browser every 6h
STRATEGY_TRIGGER = dt_time(12, 0)  # Monday 12:00 PM

API_URL    = "https://api.tase.co.il/api/derivatives/putvscall"
EXPIRY_URL = "https://api.tase.co.il/api/derivatives/fltrputvscallexpdates"
TASE_PAGE  = (
    "https://market.tase.co.il/he/market_data/derivatives/01/"
    "major_data/putvscall"
    "?dType=2&updType=1&inQType=3&objId=01&qType=3"
)

TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")

# Mon-Fri trading (Mon=0 .. Fri=4)
TRADING_DAYS  = {0, 1, 2, 3, 4}
MARKET_OPEN   = dt_time(9, 30)
MARKET_CLOSE  = dt_time(17, 30)

DAY_NAMES = {
    0: ("Monday",    "שני"),
    1: ("Tuesday",   "שלישי"),
    2: ("Wednesday", "רביעי"),
    3: ("Thursday",  "חמישי"),
    4: ("Friday",    "שישי"),
    5: ("Saturday",  "שבת"),
    6: ("Sunday",    "ראשון"),
}

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
    try:
        browser.close()
    except Exception:
        pass
    return launch_browser(pw)


# ------------------------------------------------------------------
# TASE API helpers
# ------------------------------------------------------------------

def _get_expiry_dates(page) -> list:
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
    result = page.evaluate(js, EXPIRY_URL)
    if result.get("error"):
        logger.warning("Expiry-dates API: %s", result["error"])
        return []

    items = (result.get("data") or {}).get(
        "DerivativeExpirationDateItems", []
    )

    today = date.today()
    monday = today - timedelta(days=today.weekday())
    friday = monday + timedelta(days=4)

    dates = []
    for it in items:
        if it.get("ExpirationDateType") != "01":
            continue
        raw = it.get("Date", "")
        try:
            d = date(int(raw[6:10]), int(raw[3:5]), int(raw[0:2]))
            if monday <= d <= friday:
                dates.append(d)
        except (ValueError, IndexError):
            continue
    return sorted(dates)


def _fetch_all_pages(page, expr_date_iso: str):
    all_items = []
    page_num = 1
    trade_date = None
    asset_name = None

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
        result = page.evaluate(js, {
            "url":      API_URL,
            "exprDate": expr_date_iso,
            "totalRec": 1 if page_num == 1 else len(all_items),
            "pageNum":  page_num,
        })

        if result.get("error"):
            logger.warning("putvscall page %d: %s",
                           page_num, result["error"])
            break

        data  = result.get("data", {})
        items = data.get("Items", [])
        total = data.get("TotalRec", 0)
        trade_date = trade_date or data.get("TradeDate")
        asset_name = asset_name or data.get("AssetName")

        if not items:
            break

        all_items.extend(items)
        logger.info("   page %d: %d records (%d/%d)",
                     page_num, len(items), len(all_items), total)

        if len(all_items) >= total:
            break
        page_num += 1
        time.sleep(0.5)

    return all_items, trade_date, asset_name


# ------------------------------------------------------------------
# Single fetch cycle
# ------------------------------------------------------------------

def run_cycle(page, cycle_time: datetime):
    date_str = cycle_time.strftime("%Y-%m-%d")
    time_str = cycle_time.strftime("%H:%M")

    expiry_dates = _get_expiry_dates(page)
    if not expiry_dates:
        logger.warning("No expiry dates — skipping cycle")
        return False

    logger.info("Expiry dates: %s",
                [d.isoformat() for d in expiry_dates])

    success_count = 0

    for idx, exp_date in enumerate(expiry_dates):
        exp_iso = exp_date.isoformat()
        wd = exp_date.weekday()
        en, he = DAY_NAMES.get(wd, (f"Day{wd}", f"Day{wd}"))

        logger.info(">> %s (%s) %s", en, he, exp_iso)

        items, trade_dt, asset = _fetch_all_pages(page, exp_iso)

        if items:
            if db.upsert_items(date_str, time_str, exp_iso,
                               trade_dt, items):
                success_count += 1
            logger.info("   [OK] %d records", len(items))
        else:
            db.upsert_no_trading(date_str, time_str, exp_iso)
            logger.info("   [EMPTY] no trading")

        if idx < len(expiry_dates) - 1:
            time.sleep(random.uniform(3, 5))

    return success_count > 0


def is_last_cycle(now: datetime) -> bool:
    """Check if the next cycle would be outside trading hours."""
    next_cycle = now + timedelta(seconds=FETCH_INTERVAL)
    return next_cycle.time() > MARKET_CLOSE


# ------------------------------------------------------------------
# Main loop
# ------------------------------------------------------------------

def main():
    logger.info("=" * 55)
    logger.info("  TASE Pipeline — Render Background Worker")
    logger.info("  Interval : %d min", FETCH_INTERVAL // 60)
    logger.info("=" * 55)

    if not db.test_connection():
        logger.critical("Cannot connect to Supabase — exiting")
        sys.exit(1)

    browser_born = time.monotonic()
    strategy_triggered_today = False  # prevent multiple triggers

    with sync_playwright() as pw:
        browser, context, page = launch_browser(pw)
        logger.info("Browser ready")

        while not shutdown.is_set():
            now = datetime.now(TZ_ISRAEL)

            if not is_trading_hours(now):
                wait = seconds_until_next_open(now)
                en, _ = DAY_NAMES.get(now.weekday(), ("?", "?"))
                logger.info(
                    "Outside trading hours (%s %s). "
                    "Sleeping %d min...",
                    en, now.strftime("%H:%M"), wait // 60,
                )
                shutdown.wait(timeout=wait)
                continue

            # periodic browser restart
            if time.monotonic() - browser_born > BROWSER_RESTART:
                logger.info("Restarting browser (age limit)")
                try:
                    browser.close()
                except Exception:
                    pass
                browser, context, page = launch_browser(pw)
                browser_born = time.monotonic()

            logger.info("-" * 50)
            logger.info("Cycle start: %s", now.strftime("%Y-%m-%d %H:%M"))
            # Reset strategy flag at start of each day
            if now.time() < dt_time(9, 45):
                strategy_triggered_today = False

            try:
                ok = run_cycle(page, now)

                # Monday 12:00 strategy trigger
                if (ok and now.weekday() == 0
                        and now.time() >= STRATEGY_TRIGGER
                        and not strategy_triggered_today):
                    logger.info("*** Monday 12:00 — triggering Iron Condor strategy ***")
                    try:
                        strategy_engine.run_strategy()
                        strategy_triggered_today = True
                    except Exception as se:
                        logger.error("Strategy engine error: %s", se, exc_info=True)

                if ok and is_last_cycle(now):
                    logger.info("*** Last cycle of the day — saving to history ***")
                    db.copy_to_history()
                if not ok:
                    logger.warning("Cycle empty — recovering session")
                    browser, context, page = recover_session(
                        pw, browser, context, page
                    )
            except Exception as e:
                logger.error("Cycle error: %s", e, exc_info=True)
                try:
                    browser, context, page = recover_session(
                        pw, browser, context, page
                    )
                except Exception as e2:
                    logger.critical("Recovery failed: %s", e2)

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
