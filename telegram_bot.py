"""
telegram_bot.py -- Telegram notifications for TASE Pipeline.

All messages are concise, professional, Hebrew RTL.
"""

import os
import logging

import httpx

logger = logging.getLogger("tase_pipeline")

_token:   str = ""
_chat_id: str = ""


def _init():
    global _token, _chat_id
    _token   = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    _chat_id = os.environ.get("TELEGRAM_CHAT_ID", "")


def _ensure_init():
    if not _token:
        _init()


def send_message(text: str) -> bool:
    """Send a Markdown message via Telegram Bot API."""
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

    try:
        r = httpx.post(url, json=payload, timeout=15)
        if r.status_code == 200:
            logger.info("Telegram message sent")
            return True
        logger.warning("Telegram send failed %d: %s",
                       r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Telegram send error: %s", e)
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
            text += (
                f"`{pct:>4.1f}%`"
                f" | `{sp:.0f}`—`{sc:.0f}`"
                f" | ₪`{prem:,.0f}`"
                f" | +₪`{profit:,.0f}`\n"
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
    total_pnl = sum(r.get("actual_pnl_ils", 0) for r in results)
    pnl_emoji = "\U0001F4C8" if total_pnl >= 0 else "\U0001F4C9"

    text = (
        f"\U0001F3C1 *פקיעה — יום {day_name}*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4CA סגירה: `{settlement_index:,.2f}`"
        f" | כניסה: `{base_index:,.2f}`\n\n"
    )

    for r in sorted(results, key=lambda x: x.get("interval_pct", 0)):
        pct = r.get("interval_pct", 0)
        pnl = r.get("actual_pnl_ils", 0)
        status = r.get("result_status", "")

        icon = {
            "max_profit":        "✅",
            "partial_loss_put":  "⚠️",
            "partial_loss_call": "⚠️",
            "max_loss_put":      "❌",
            "max_loss_call":     "❌",
        }.get(status, "❓")

        text += f"{icon} `{pct:.1f}%` | `{pnl:+,.0f} ₪`\n"

    text += (
        f"\n{pnl_emoji} *סה\"כ:* `{total_pnl:+,.0f} ₪`"
    )
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
    """Friday end-of-week P&L summary."""
    total_pnl = week_stats.get("total_pnl", 0)
    trades = week_stats.get("trades", 0)
    wins = week_stats.get("wins", 0)
    losses = trades - wins
    wr = (wins / trades * 100) if trades > 0 else 0
    best_interval = week_stats.get("best_interval", 0)
    best_pnl = week_stats.get("best_pnl", 0)
    worst_interval = week_stats.get("worst_interval", 0)
    worst_pnl = week_stats.get("worst_pnl", 0)
    cum_total = week_stats.get("cumulative_total", 0)

    pnl_emoji = "\U0001F4C8" if total_pnl >= 0 else "\U0001F4C9"

    text = (
        f"\U0001F4CA *סיכום שבועי — TA-35*\n"
        f"━━━━━━━━━━━━━━━\n"
        f"{pnl_emoji} P&L: `{total_pnl:+,.0f} ₪`\n"
        f"\U0001F3AF הצלחה: `{wr:.0f}%`"
        f" ({wins}W/{losses}L"
        f" מתוך {trades})\n\n"
        f"\U0001F3C6 מרווח מוביל: {best_interval}%"
        f" (`{best_pnl:+,.0f} ₪`)\n"
        f"\U0001F480 מרווח חלש: {worst_interval}%"
        f" (`{worst_pnl:+,.0f} ₪`)\n\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4B0 *מצטבר:* `{cum_total:+,.0f} ₪`"
    )
    send_message(text)
