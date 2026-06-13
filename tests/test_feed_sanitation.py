"""
Feed sanitation locks (#6 placeholder row, #5 non-trading-day expiry).

#6: TASE appends one constant placeholder row (strike "1", no put) to every
chain response. It was reaching the validation gate and firing ITEMS_REJECTED
every cycle, drowning out any REAL rejection. tase_api now drops it at the
fetch boundary via _is_real_option_row.

#5: TASE may list a Sunday expiry (e.g. 2026-06-14); the market is closed Sun
under the Mon–Fri calendar, so get_expiry_dates now filters expiries to
TRADING_DAYS.
"""
import os
import json
import datetime as _dt

import tase_api
from config import TRADING_DAYS

_REPO = os.path.dirname(os.path.dirname(__file__))


# ── #6: placeholder detection ────────────────────────────────────────────────
def test_real_call_row_kept():
    assert tase_api._is_real_option_row({"ExpirationPrice_call": "4200"}) is True


def test_real_put_only_row_kept():
    assert tase_api._is_real_option_row({"ExpirationPrice_put": 4200}) is True


def test_placeholder_strike_one_dropped():
    # the exact junk row shape (verified live): strike 1, no put, absurd rate
    junk = {"ExpirationPrice_call": 1, "ExpirationPrice_put": None,
            "LastRate_call": 211571, "rowType": None}
    assert tase_api._is_real_option_row(junk) is False


def test_casing_variants_handled():
    assert tase_api._is_real_option_row({"ExpirationPrice_Call": "4,200"}) is True
    assert tase_api._is_real_option_row({"ExpirationPrice_Put": "1"}) is False


def test_diag_fixture_drops_junk_rows():
    """
    On the real captured feed, sanitation removes BOTH junk rows:
      1. the strike="1" placeholder (validation already rejected this), and
      2. an all-empty row (no strikes/prices) that validation was SILENTLY
         ACCEPTING and storing — so the filter also fixes a latent data leak.
    Every kept row carries a real strike.
    """
    path = os.path.join(_REPO, "diag_raw_response.json")
    items = json.load(open(path))["Items"]
    kept = [it for it in items if tase_api._is_real_option_row(it)]
    assert len(items) - len(kept) == 2            # placeholder + empty row
    assert all(tase_api._is_real_option_row(it) for it in kept)
    # none of the kept rows is the all-None junk
    for it in kept:
        assert any(it.get(k) not in (None, "") for k in
                   ("ExpirationPrice_call", "ExpirationPrice_Call",
                    "ExpirationPrice_put", "ExpirationPrice_Put"))


# ── #6 on the PRODUCTION path: main.py applies the SAME shared filter ─────────
def test_main_production_path_filters_header_rows():
    """main.py's fetch->write path drops TASE header/placeholder rows via the
    SHARED tase_api._is_real_option_row, so neither the live table nor the EOD
    history copy (taken from it) stores them. Mirrors the real junk shape:
    rowtype 001, empty strikes + empty derivativeids, only a series name."""
    import main
    header = {"RowType": "001",
              "ExpirationPrice_Call": "", "ExpirationPrice_Put": "",
              "DerivativeId_Call": "", "DerivativeId_Put": "",
              "DerivativeName_Put": "14/06/2026 - שבועי"}
    real_call = {"ExpirationPrice_Call": "4200", "DerivativeId_Call": "123"}
    real_put  = {"ExpirationPrice_Put": "4000", "DerivativeId_Put": "456"}
    kept = main._keep_real_option_rows([header, real_call, real_put])
    assert kept == [real_call, real_put]   # only the real rows survive
    assert header not in kept              # the empty header row is filtered


def test_main_filter_wired_before_write():
    """Guard: run_cycle applies the filter to the fetched page, and the helper
    delegates to the shared predicate (no duplicated filter logic)."""
    src = open(os.path.join(_REPO, "main.py"), encoding="utf-8").read()
    assert "_keep_real_option_rows(items)" in src        # applied in run_cycle
    assert "tase_api._is_real_option_row(it)" in src     # delegates to the shared filter


# ── #5: non-trading-day expiry filter ────────────────────────────────────────
def test_sunday_is_not_a_trading_day():
    assert _dt.date(2026, 6, 14).weekday() == 6      # Sunday
    assert 6 not in TRADING_DAYS                      # excluded
    # the weekdays we DO keep
    for d in (_dt.date(2026, 6, 10),   # Wed
              _dt.date(2026, 6, 11),   # Thu
              _dt.date(2026, 6, 12)):  # Fri
        assert d.weekday() in TRADING_DAYS


def test_expiry_filter_wired():
    src = open(os.path.join(_REPO, "tase_api.py"), encoding="utf-8").read()
    assert "d.weekday() in TRADING_DAYS" in src       # the #5 filter
    assert "_is_real_option_row(it)" in src           # the #6 filter applied
