"""
#10 — coverage for the pure scheduling/timing helpers in main.py and tase_api.py
(the loop's decision logic). These drove subtle past bugs (last-cycle timing,
trading-day detection), so they deserve locked behaviour.

main + tase_api import cleanly here (conftest stubs supabase_client/telegram_bot).
"""
import datetime as _dt

import main
import tase_api
from config import MARKET_OPEN, MARKET_CLOSE, TRADING_DAYS

# Anchor dates (verified): 2026-06-08 Mon … 2026-06-12 Fri, 2026-06-14 Sun.
MON, TUE, WED, THU, FRI = (_dt.date(2026, 6, d) for d in (8, 9, 10, 11, 12))
SUN = _dt.date(2026, 6, 14)


def _at(d: _dt.date, t: _dt.time) -> _dt.datetime:
    return _dt.datetime.combine(d, t)


# ── is_trading_hours ─────────────────────────────────────────────────────────
def test_trading_hours_open_and_close_inclusive():
    assert main.is_trading_hours(_at(MON, MARKET_OPEN)) is True
    assert main.is_trading_hours(_at(MON, MARKET_CLOSE)) is True


def test_outside_window_is_closed():
    before = (_dt.datetime.combine(MON, MARKET_OPEN) - _dt.timedelta(minutes=1)).time()
    after  = (_dt.datetime.combine(MON, MARKET_CLOSE) + _dt.timedelta(minutes=1)).time()
    assert main.is_trading_hours(_at(MON, before)) is False
    assert main.is_trading_hours(_at(MON, after)) is False


def test_sunday_always_closed():
    assert SUN.weekday() == 6 and 6 not in TRADING_DAYS
    assert main.is_trading_hours(_at(SUN, MARKET_OPEN)) is False


# ── seconds_until_next_open ──────────────────────────────────────────────────
def test_next_open_skips_weekend():
    # Friday after close -> next open is Monday (skips Sat/Sun).
    now = _at(FRI, (_dt.datetime.combine(FRI, MARKET_CLOSE)
                    + _dt.timedelta(hours=1)).time())
    secs = main.seconds_until_next_open(now)
    landing = now + _dt.timedelta(seconds=secs)
    assert landing.weekday() in TRADING_DAYS
    assert landing.weekday() == 0            # Monday
    assert landing.time() == MARKET_OPEN


def test_next_open_same_day_before_open():
    now = _at(MON, (_dt.datetime.combine(MON, MARKET_OPEN)
                    - _dt.timedelta(hours=1)).time())
    secs = main.seconds_until_next_open(now)
    landing = now + _dt.timedelta(seconds=secs)
    assert landing.date() == MON and landing.time() == MARKET_OPEN


# ── tase_api.is_last_cycle ───────────────────────────────────────────────────
def test_is_last_cycle_true_near_close():
    now = _dt.datetime.combine(WED, MARKET_CLOSE) - _dt.timedelta(minutes=5)
    assert tase_api.is_last_cycle(now, 15 * 60) is True     # next cycle (+15m) past close


def test_is_last_cycle_false_mid_session():
    now = _dt.datetime.combine(WED, MARKET_CLOSE) - _dt.timedelta(minutes=30)
    assert tase_api.is_last_cycle(now, 15 * 60) is False    # next cycle still before close


# ── tase_api.is_last_trading_day_of_week ─────────────────────────────────────
def test_last_trading_day_from_expiries():
    expiries = [WED, THU, FRI]               # this-week expiries
    assert tase_api.is_last_trading_day_of_week(_at(FRI, MARKET_OPEN), expiries) is True
    assert tase_api.is_last_trading_day_of_week(_at(WED, MARKET_OPEN), expiries) is False


def test_last_trading_day_calendar_fallback():
    # No expiry data: Friday is the last trading day of the Mon–Fri week.
    assert tase_api.is_last_trading_day_of_week(_at(FRI, MARKET_OPEN), []) is True
    assert tase_api.is_last_trading_day_of_week(_at(WED, MARKET_OPEN), []) is False
