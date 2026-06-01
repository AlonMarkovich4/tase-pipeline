"""
telegram_bot.py -- Telegram notifications for TASE Pipeline.

All messages are concise, professional, Hebrew RTL.
"""

import os
import time
import logging

import httpx

logger = logging.getLogger("tase_pipeline")

_token:   str = ""
_chat_id: str = ""
_initialized: bool = False

# Retry policy — Telegram is mission-critical for alerts so we retry
# with exponential backoff up to 3 attempts.  Total worst-case latency
# is bounded by (1 + 2 + 4) = 7 seconds of sleep + 3 × timeout.
_MAX_RETRIES = 3
_TIMEOUT = 15


def _init():
    global _token, _chat_id, _initialized
    _token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    _chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")
    _initialized = True


def _ensure_init():
    # Use flag instead of truthy check — avoids re-init when token is
    # legitimately missing (avoids env-var reads on every send_message)
    if not _initialized:
        _init()


def send_message(text: str) -> bool:
    """Send a Markdown message via Telegram Bot API.

    Retries up to _MAX_RETRIES times with exponential backoff.
    Returns True on success, False if all attempts failed.
    """
    _ensure_init()
    if not _token or not _chat_id:
        logger.warning("Telegram not configured — skipping notification")
        return False

    url = f"https://api.telegram.org/bot{_token}/sendMessage"
    payload = {
        "chat_id":    _chat_id,
        "text":       text,
        "parse_mode": "Markdown",
    }

    last_err = ""
    for attempt in range(1, _MAX_RETRIES + 1):
        try:
            r = httpx.post(url, json=payload, timeout=_TIMEOUT)
            if r.status_code == 200:
                if attempt > 1:
                    logger.info("Telegram message sent (attempt %d)", attempt)
                else:
                    logger.info("Telegram message sent")
                return True
            # 4xx (other than 429) = permanent client error — don't retry
            if 400 <= r.status_code < 500 and r.status_code != 429:
                logger.error("Telegram permanent failure %d: %s — not retrying",
                             r.status_code, r.text[:200])
                return False
            last_err = f"HTTP {r.status_code}: {r.text[:200]}"
        except Exception as e:
            # Strip token from exception message before logging — some network
            # errors include the request URL which contains the bot token.
            last_err = f"exception: {str(e).replace(_token, '<token>')}"

        if attempt < _MAX_RETRIES:
            wait = 2 ** (attempt - 1)  # 1s, 2s, 4s
            logger.warning("Telegram send failed (attempt %d/%d): %s — "
                           "retrying in %ds",
                           attempt, _MAX_RETRIES, last_err, wait)
            time.sleep(wait)

    logger.error("Telegram send FAILED after %d attempts: %s",
                 _MAX_RETRIES, last_err)
    return False


# ------------------------------------------------------------------
# 1. CRASH ALERT
# ------------------------------------------------------------------

def alert_crash(error_msg: str = ""):
    """3+ consecutive failures or unrecoverable error."""
    text = (
        "\U0001F6A8 *TASE Pipeline — קריסה*\n"
        "━━━━━━━━━━━━━━━\n"
        "המערכת זיהתה כשל חוזר.\n"
        "נא לבדוק Render Logs."
    )
    if error_msg:
        text += f"\n`{error_msg[:200]}`"
    send_message(text)


# ------------------------------------------------------------------
# 2. STRATEGY LAUNCH (weekly, with entry details)
# ------------------------------------------------------------------

def alert_strategy_launch(base_index: float, strategies: list,
                          expiry_dates: list):
    """
    Weekly strategy entry report.
    Shows base index + compact table of intervals for the nearest expiry.
    """
    dates_str = ", ".join(expiry_dates)
    num_expiries = len(expiry_dates)
    num_total = len(strategies)

    text = (
        f"\U0001F680 *Iron Condor — כניסה שבועית*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4CA TA-35: `{base_index:,.2f}`\n"
        f"\U0001F4C5 {num_expiries} פקיעות: {dates_str}\n\n"
    )

    # Show intervals for the nearest expiry only (keep it compact)
    if strategies:
        nearest_exp = min(s["expiry_date"] for s in strategies)
        nearest = [s for s in strategies
                   if s["expiry_date"] == nearest_exp]
        nearest.sort(key=lambda s: s["interval_pct"])

        text += f"*פקיעה קרובה ({nearest_exp}):*\n"
        for s in nearest:
            pct = s["interval_pct"]
            sp = s["short_put_strike"]
            sc = s["short_call_strike"]
            prem = s["total_net_premium"]
            profit = s["max_profit_ils"]
            risk = s["max_risk_ils"]
            text += (
                f"`{pct:>4.1f}%`"
                f" | `{sp:.0f}`—`{sc:.0f}`"
                f" | פרמיה `{prem:,.1f}` נק׳"
                f" | +`{profit:,.0f}`₪"
                f" / -`{risk:,.0f}`₪\n"
            )

    text += (
        f"\n✅ {num_total} וריאציות נשמרו"
    )
    send_message(text)


# ------------------------------------------------------------------
# 3. SETTLEMENT (daily expiry result)
# ------------------------------------------------------------------

def alert_settlement(day_name: str, settlement_index: float,
                     base_index: float, results: list):
    """Daily expiry settlement — shows P&L per interval."""
    def _n(v):
        try:
            return float(v) if v is not None else 0
        except (ValueError, TypeError):
            return 0

    text = (
        f"\U0001F3C1 *פקיעה — יום {day_name}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4CA סגירה: `{settlement_index:,.2f}`"
        f" | כניסה: `{base_index:,.2f}`\n\n"
    )

    for r in sorted(results, key=lambda x: _n(x.get("interval_pct", 0))):
        pct = _n(r.get("interval_pct", 0))
        pnl = _n(r.get("actual_pnl_ils", 0))
        status = r.get("result_status", "")

        icon = {
            "max_profit":        "✅",
            "partial_loss_put":  "⚠️",
            "partial_loss_call": "⚠️",
            "max_loss_put":      "❌",
            "max_loss_call":     "❌",
        }.get(status, "❓")

        text += f"{icon} `{pct:.1f}%` | `{pnl:+,.0f} ₪`\n"

    send_message(text)


# ------------------------------------------------------------------
# 4. DAILY SUMMARY (end of trading day)
# ------------------------------------------------------------------

def alert_daily_summary(date_str: str, cycles: int,
                        rows_collected: int, expiry_count: int,
                        errors: int, index_value: float = 0):
    """Brief end-of-day status report."""
    status = "✅" if errors == 0 else f"⚠️ {errors} שגיאות"

    text = (
        f"\U0001F4CB *סיכום יומי — {date_str}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F504 סייקלים: {cycles}\n"
        f"\U0001F4C4 שורות: {rows_collected:,}\n"
        f"\U0001F4C5 פקיעות: {expiry_count}\n"
    )
    if index_value > 0:
        text += f"\U0001F4CA TA-35: `{index_value:,.2f}`\n"
    text += f"סטטוס: {status}"

    send_message(text)


# ------------------------------------------------------------------
# 5. WEEKLY SUMMARY (last trading day)
# ------------------------------------------------------------------

def alert_weekly_summary(week_stats: dict):
    """Friday end-of-week summary."""
    trades = week_stats.get("trades", 0)
    wins = week_stats.get("wins", 0)
    losses = trades - wins
    wr = (wins / trades * 100) if trades > 0 else 0
    best_interval = week_stats.get("best_interval", 0)
    worst_interval = week_stats.get("worst_interval", 0)

    text = (
        f"\U0001F4CA *סיכום שבועי — TA-35*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F3AF הצלחה: `{wr:.0f}%`"
        f" ({wins}W/{losses}L"
        f" מתוך {trades})\n\n"
        f"\U0001F3C6 מרווח מוביל: {best_interval}%\n"
        f"\U0001F480 מרווח חלש: {worst_interval}%"
    )
    send_message(text)
