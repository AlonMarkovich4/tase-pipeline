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

def _run_strategy_thread(strat_key: str) -> None:
    try:
        result = strategy_engine.run_strategy()
        if result:
            db.state_set(strat_key)
            logger.info("Strategy saved — state marker set")
        else:
            logger.warning("Strategy returned False")
    except Exception as se:
        logger.error("Strategy engine error: %s", se, exc_info=True)


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

    browser_born             = time.monotonic()
    strategy_triggered_week  = None
    settled_today            = None
    weekly_summary_week      = None
    weekly_backup_week       = None
    daily_summary_date       = None
    history_copied_date      = None
    current_day              = None
    consecutive_failures     = 0
    crash_alerted            = False
    daily_cycles             = 0
    daily_rows               = 0
    daily_errors             = 0
    daily_expiries           = 0
    last_known_expiries: list = []
    weekly_summary_due_at    = None
    current_week             = datetime.now(TZ_ISRAEL).isocalendar()[1]

    with sync_playwright() as pw:
        browser, context, page = _browser.launch(pw, HEADLESS)
        logger.info("Browser ready")

        while not shutdown.is_set():
            now = datetime.now(TZ_ISRAEL)

            # ── Off-hours block ──────────────────────────────────────
            if not is_trading_hours(now):
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

                # ── Strategy trigger (async — does not block scraping) ─
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
                        threading.Thread(
                            target=_run_strategy_thread,
                            args=(strat_key,),
                            daemon=True,
                            name="strategy",
                        ).start()
                        # Optimistic — strategy_engine deduplicates via
                        # _strategies_exist_for_week on restart.
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

                    # Copy to history
                    if history_copied_date != today_iso:
                        logger.info("*** Last cycle of the day — saving to history ***")
                        if db.copy_to_history():
                            history_copied_date = today_iso

                # ── Failure handling & recovery ───────────────────────
                if not ok:
                    daily_errors        += 1
                    consecutive_failures += 1
                    logger.warning("Cycle empty (%d consecutive) — recovering session",
                                   consecutive_failures)
                    if consecutive_failures >= 3 and not crash_alerted:
                        telegram_bot.alert_crash(
                            f"{consecutive_failures} consecutive failures")
                        crash_alerted = True
                    browser, context, page = _browser.recover(
                        pw, browser, context, page, HEADLESS)
                else:
                    consecutive_failures = 0
                    crash_alerted        = False

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
