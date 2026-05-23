"""
telegram_bot.py -- Telegram notifications for TASE Pipeline.

Sends alerts for:
1. Emergency crashes (3 consecutive failures)
2. Weekly strategy launch (Monday 12:00)
3. Daily expiry settlement reports
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
# Pre-built alert messages
# ------------------------------------------------------------------

def alert_crash(error_msg: str = ""):
    """Emergency alert — system crashed or 3 consecutive failures."""
    text = (
        "\U0001F6A8 *התרעת מערכת"
        " קריטית!*\n\n"
        "המערכת הפסיקה"
        " לעבוד או קרסה."
        " נא לבדוק את"
        " ה־Logs ברנדר בהקדם."
    )
    if error_msg:
        text += f"\n\n`{error_msg[:200]}`"
    send_message(text)


def alert_strategy_launch(num_strategies: int, expiry_dates: list):
    """Monday 12:00 — strategy calculated and saved."""
    dates_str = ", ".join(expiry_dates)
    text = (
        "\U0001F680 *מערכת אסטרטגיות"
        " TASE - שבוע חדש החל!*\n\n"
        "נתוני יום שני"
        " בשעה 12:00 נקלטו"
        " בהצלחה.\n"
        f"חושבו {num_strategies}"
        " וריאציות"
        " ונשמרו במסד"
        " הנתונים.\n\n"
        f"פקיעות: {dates_str}"
    )
    send_message(text)


def alert_settlement(day_name: str, settlement_index: float,
                     results: list):
    """Daily expiry settlement report."""
    header = (
        f"\U0001F3C1 *סיכום פקיעה"
        f" יומי - יום {day_name}*\n\n"
        f"מדד הפקיעה"
        f" בפועל: `{settlement_index:.2f}`\n\n"
        "להלן ביצועי"
        " 8 הוריאציות:\n"
    )

    lines = []
    for r in results:
        pct = r.get("interval_pct", 0)
        short_put = r.get("short_put_strike", 0)
        short_call = r.get("short_call_strike", 0)
        pnl = r.get("actual_pnl_ils", 0)
        status = r.get("result_status", "")

        status_map = {
            "max_profit":        "✅ רווח מקסימלי",
            "partial_loss_put":  "⚠️ הפסד חלקי (Put)",
            "partial_loss_call": "⚠️ הפסד חלקי (Call)",
            "max_loss_put":      "❌ הפסד מקסימלי (Put)",
            "max_loss_call":     "❌ הפסד מקסימלי (Call)",
        }
        status_text = status_map.get(status, status)

        line = (
            f"• מרווח {pct}%"
            f" | סטרייקים:"
            f" {short_put:.0f}-{short_call:.0f}"
            f" | *{status_text}*"
            f" | *{pnl:+.2f} ₪*"
        )
        lines.append(line)

    text = header + "\n".join(lines)
    send_message(text)
