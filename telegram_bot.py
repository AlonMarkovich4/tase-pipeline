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
        "parse_mode": "HTML",
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


def _esc(s) -> str:
    """Escape the three HTML-special characters for Telegram's HTML parse
    mode. Apply to every DYNAMIC value put into a message — error strings,
    dates, data-quality issues — so a stray <, > or & can't break the
    formatting or get the whole message rejected (HTTP 400) by the Bot API.
    Static template text and pre-formatted numbers don't need it."""
    return (str(s).replace("&", "&amp;")
                  .replace("<", "&lt;")
                  .replace(">", "&gt;"))


# ------------------------------------------------------------------
# 1. CRASH ALERT
# ------------------------------------------------------------------

def alert_crash(error_msg: str = ""):
    """3+ consecutive failures or unrecoverable error."""
    text = (
        "\U0001F6A8 <b>TASE Pipeline — קריסה</b>\n"
        "━━━━━━━━━━━━━━━\n"
        "המערכת זיהתה כשל חוזר.\n"
        "נא לבדוק Render Logs."
    )
    if error_msg:
        text += f"\n<code>{_esc(error_msg[:200])}</code>"
    send_message(text)


# ------------------------------------------------------------------
# 1c. DATA QUALITY DEGRADATION ALERT
# ------------------------------------------------------------------

def alert_data_quality(issues: list):
    """Sent when data-quality degradation is detected (not a hard crash).
    `issues` is a list of human-readable Hebrew strings."""
    if not issues:
        return
    body = "\n".join(f"• {_esc(s)}" for s in issues[:6])
    text = (
        "⚠️ <b>Pipeline — ירידה באיכות נתונים</b>\n"
        "━━━━━━━━━━━━━━━\n"
        f"{body}\n\n"
        "המערכת ממשיכה לרוץ — לבדיקה."
    )
    send_message(text)


# ------------------------------------------------------------------
# 1b. WEEKLY HEARTBEAT (first trading day, ~10:00)
# ------------------------------------------------------------------

def alert_weekly_heartbeat(date_str: str, rows: int, expiries: int,
                           index_value: float = 0):
    """First-trading-day 'system alive' notification.
    Sent once per week after the first successful cycle."""
    idx_line = (f"\U0001F4CA TA-35: <code>{index_value:,.2f}</code>\n"
                if index_value > 0 else "")
    text = (
        f"✅ <b>Pipeline — תחילת שבוע</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"המערכת פעילה ואוספת נתונים.\n"
        f"\U0001F4C5 {_esc(date_str)}\n"
        f"{idx_line}"
        f"\U0001F4C4 {rows:,} שורות | {expiries} פקיעות\n"
        f"\U0001F680 אסטרטגיות ישוגרו ב-12:00"
    )
    send_message(text)


# ------------------------------------------------------------------
# 2. STRATEGY LAUNCH (weekly, with entry details)
# ------------------------------------------------------------------

def alert_strategy_launch(base_index: float, strategies: list,
                          expiry_dates: list):
    """Weekly condor launch confirmation — simplified.

    Acknowledges that every variation was dispatched, with counts and the
    expiry list. No per-interval strikes/premium table.
    """
    num_total    = len(strategies)
    num_expiries = len(expiry_dates)
    dates_fmt = " · ".join(
        _esc(f"{str(d)[8:10]}/{str(d)[5:7]}" if len(str(d)) >= 10 else str(d))
        for d in sorted(expiry_dates)
    )
    per = (num_total // num_expiries) if num_expiries else 0
    breakdown = (f" ({per} מרווחים × {num_expiries} פקיעות)"
                 if per and per * num_expiries == num_total else "")

    text = (
        f"\U0001F680 <b>Iron Condor — שיגור שבועי</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4CA TA-35: <code>{base_index:,.2f}</code>\n"
        f"\U0001F4C5 {num_expiries} פקיעות: {dates_fmt}\n"
        f"✅ כל האסטרטגיות שוגרו — <b>{num_total}</b> וריאציות{breakdown}"
    )
    send_message(text)


# ------------------------------------------------------------------
# 3. SETTLEMENT (daily expiry result)
# ------------------------------------------------------------------

def alert_settlement(day_name: str, settlement_index: float,
                     base_index: float, results: list):
    """Daily condor settlement — single line: the interval with the highest
    actual ₪ among all of the expiry's intervals, with its ₪, risk/reward
    ratio and max risk.

    If EVERY interval lost money, the wording switches from "הכי רווחי" to
    "התוצאה הטובה ביותר".

    NOTE: ``risk_reward_ratio`` / ``max_risk_ils`` are shown only when present
    in ``results``. settle_expiry does not SELECT them yet (Step 2), so they
    are omitted until that one-line addition is made.
    """
    def _n(v):
        try:
            return float(v) if v is not None else 0.0
        except (ValueError, TypeError):
            return 0.0

    text = (
        f"\U0001F3C1 <b>פקיעת Iron Condor — יום {_esc(day_name)}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F4CA סגירה: <code>{settlement_index:,.2f}</code>"
        f" | כניסה: <code>{base_index:,.2f}</code>"
    )

    if results:
        best = max(results, key=lambda r: _n(r.get("actual_pnl_ils")))
        pct = _n(best.get("interval_pct"))
        pnl = _n(best.get("actual_pnl_ils"))
        all_negative = all(_n(r.get("actual_pnl_ils")) < 0 for r in results)
        label = "התוצאה הטובה ביותר" if all_negative else "הכי רווחי"
        icon  = "\U0001F4B0" if pnl >= 0 else "\U0001F53B"   # 💰 / 🔻

        extra = ""
        rr = best.get("risk_reward_ratio")
        if rr is not None:
            extra += f" · RR <code>{_n(rr):.2f}</code>"
        mr = best.get("max_risk_ils")
        if mr is not None:
            extra += f" · מקס׳ סיכון <code>{_n(mr):,.0f} ₪</code>"

        text += (
            f"\n\n{icon} {label}: מרווח <code>{pct:.1f}%</code>"
            f" · <code>{pnl:+,.0f} ₪</code>{extra}"
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
        f"\U0001F4CB <b>סיכום יומי — {_esc(date_str)}</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F504 סייקלים: {cycles}\n"
        f"\U0001F4C4 שורות: {rows_collected:,}\n"
        f"\U0001F4C5 פקיעות: {expiry_count}\n"
    )
    if index_value > 0:
        text += f"\U0001F4CA TA-35: <code>{index_value:,.2f}</code>\n"
    text += f"סטטוס: {status}"

    send_message(text)


# ------------------------------------------------------------------
# 5. WEEKLY SUMMARY (last trading day)
# ------------------------------------------------------------------

_DAY_HE = {
    "Sunday": "א׳", "Monday": "ב׳", "Tuesday": "ג׳", "Wednesday": "ד׳",
    "Thursday": "ה׳", "Friday": "ו׳", "Saturday": "ש׳",
}


def alert_weekly_summary(week_stats: dict):
    """End-of-week condor summary — POTENTIAL profit.

    Potential = the sum of the best-₪ interval per expiry that settled this
    week (not the sum of every interval). Framed as potential, not realized.
    """
    breakdown = week_stats.get("potential_breakdown", []) or []
    # Sum the rounded per-expiry values so the total equals the shown lines
    # (avoids a round-then-sum vs sum-then-round 1₪ discrepancy).
    total = sum(round(float(b.get("pnl", 0))) for b in breakdown)
    n = len(breakdown)

    def _fmt_ils(v: float) -> str:
        return f"+{v:,.0f}" if v >= 0 else f"{v:,.0f}"

    lines = []
    for b in breakdown:
        e = str(b.get("expiry", ""))
        d = _DAY_HE.get(b.get("day", ""), "")
        dm = f"{e[8:10]}/{e[5:7]}" if len(e) >= 10 else _esc(e)
        lines.append(
            f"   • {d} <code>{dm}</code> — מרווח <code>{float(b.get('interval', 0)):.1f}%</code>"
            f" → <code>{_fmt_ils(b.get('pnl', 0))} ₪</code>"
        )
    body = "\n".join(lines) if lines else "—"
    total_icon = "\U0001F4C8" if total >= 0 else "\U0001F4C9"

    text = (
        f"\U0001F4CA <b>סיכום שבועי — TA-35</b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"\U0001F3C1 {n} פקיעות נסלקו השבוע\n\n"
        f"\U0001F4A1 רווח פוטנציאלי כולל: {total_icon} <code>{_fmt_ils(total)} ₪</code>\n"
        f"{body}\n\n"
        f"<i>פוטנציאלי — אילו פעלנו לפי המרווח הטוב בכל פקיעה; לא רווח ממומש.</i>"
    )
    send_message(text)
