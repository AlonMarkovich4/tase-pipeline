"""
STALE_TRADE_DATE tests — trading-day distance, not calendar days.

The TASE putvscall feed (qType=3) serves the PREVIOUS trading day's EOD (no
intraday on this endpoint — verified by probe). So one trading day of lag is the
normal, legitimate input. The old check counted CALENDAR days and rejected every
morning (Fri→Mon = 3 calendar days → false CRITICAL). The fix measures distance
in TRADING days (config.TRADING_DAYS — single source of truth):

  * TradeDate == today            -> fresh, no flag
  * 1 trading day stale (T-1 EOD) -> accepted, no flag   (the main fix)
  * >= 2 trading days stale       -> CRITICAL (genuinely stuck feed; preserved)
  * TradeDate on a closed weekday -> WARNING (source anomaly, not staleness)

`check_trade_date` reads the wall clock via datetime.now(); each test freezes
"today" by monkeypatching option_schema.datetime with a datetime subclass (so
strptime/strftime still work).
"""
import datetime as _dt

import option_schema as osch
from option_schema import DQLevel


def _freeze(monkeypatch, y, m, d, hh=12, mm=0):
    """Pin datetime.now() inside option_schema to a fixed instant."""
    fixed = _dt.datetime(y, m, d, hh, mm)

    class _Frozen(_dt.datetime):
        @classmethod
        def now(cls, tz=None):
            return fixed if tz is None else fixed.replace(tzinfo=tz)

    monkeypatch.setattr(osch, "datetime", _Frozen)


# ── 1. T-1 EOD on the real diag fixture's date: no flag (the main fix) ────────
def test_t_minus_one_eod_accepted(monkeypatch):
    # today = Tue 09/06/2026; diag TradeDate = Mon 08/06/2026 -> 1 trading day.
    _freeze(monkeypatch, 2026, 6, 9)
    assert osch.check_trade_date("08/06/2026", "2026-06-09") is None


# ── 2. Two trading days stale -> CRITICAL preserved (protection intact) ───────
def test_two_trading_days_stale_critical(monkeypatch):
    # today = Tue 09/06; TradeDate = Fri 05/06 -> (Mon 08, Tue 09) = 2 trading days.
    _freeze(monkeypatch, 2026, 6, 9)
    w = osch.check_trade_date("05/06/2026", "2026-06-09")
    assert w is not None
    assert w.code == "STALE_TRADE_DATE"
    assert w.level == DQLevel.CRITICAL
    assert "2 trading day(s) stale" in w.detail


# ── 3. Weekend gap Fri->Mon: 3 calendar days but 1 trading day -> no flag ─────
#      This is the regression the old calendar-day logic got wrong.
def test_weekend_gap_no_flag(monkeypatch):
    # today = Mon 08/06; TradeDate = Fri 05/06 -> Sat/Sun skipped -> 1 trading day.
    _freeze(monkeypatch, 2026, 6, 8)
    assert osch.check_trade_date("05/06/2026", "2026-06-08") is None


# ── 4. TradeDate on a closed weekday (Sunday) -> WARNING, not CRITICAL ────────
def test_trade_date_on_closed_day_warns(monkeypatch):
    # today = Mon 08/06; TradeDate = Sun 07/06 (weekday 6, not in TRADING_DAYS).
    _freeze(monkeypatch, 2026, 6, 8)
    w = osch.check_trade_date("07/06/2026", "2026-06-08")
    assert w is not None
    assert w.code == "TRADE_DATE_ON_CLOSED_DAY"
    assert w.level == DQLevel.WARNING


# ── 5. Same-day data is always fresh ──────────────────────────────────────────
def test_same_day_fresh(monkeypatch):
    _freeze(monkeypatch, 2026, 6, 9)
    assert osch.check_trade_date("09/06/2026", "2026-06-09") is None


# ── 6. Lag is measured in TRADING days even late at night (no in-market gate) ─
#      Previously T-1 during market hours was CRITICAL; now T-1 is always fine.
def test_t_minus_one_accepted_regardless_of_time(monkeypatch):
    _freeze(monkeypatch, 2026, 6, 9, hh=23, mm=30)   # after hours
    assert osch.check_trade_date("08/06/2026", "2026-06-09") is None
    _freeze(monkeypatch, 2026, 6, 9, hh=11, mm=0)    # mid-market
    assert osch.check_trade_date("08/06/2026", "2026-06-09") is None
