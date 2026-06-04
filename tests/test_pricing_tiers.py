"""
Characterization tests for _find_closest_option's 4-tier pricing and the
wing-width guard. Locks tier precedence, sanity capping, and exclusion logic.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import strategy_engine as se
from tests.conftest import make_row


def test_tier1_live_beats_stale_at_equal_distance():
    live  = make_row(2025, call_pts=1.80, call_deals=10)
    stale = make_row(2015, call_pts=1.90, call_deals=0)
    r = se._find_closest_option([live, stale], 2020.0, "call")
    assert r["price_source"] == "live"
    assert r["strike"] == 2025.0


def test_tier3_baserate_when_lastrate_zero():
    row = make_row(2020, call_pts=0.0, call_deals=0, base_call=1.50)
    r = se._find_closest_option([row], 2020.0, "call")
    assert r["price_source"] == "baserate"
    assert abs(r["price"] - 1.50) < 1e-6


def test_price_sanity_rejects_above_cap():
    """lastrate above PRICE_SANITY_MAX_PTS treated as unpriced → falls to closest."""
    insane = make_row(2020, call_pts=100.0)      # > 60 cap
    sane   = make_row(2025, call_pts=2.00)
    r = se._find_closest_option([insane, sane], 2020.0, "call")
    # insane strike's price zeroed; sane row priced → live wins despite distance
    assert r["strike"] == 2025.0
    assert r["price_source"] == "live"


def test_exclude_strikes_prevents_reuse():
    rows = [make_row(2020, call_pts=2.0), make_row(2040, call_pts=0.5)]
    r = se._find_closest_option(rows, 2020.0, "call", exclude_strikes={2020.0})
    assert r["strike"] == 2040.0


def test_min_strike_floor_enforced():
    """Wing guard: long call must be >= floor even if a nearer strike exists."""
    rows = [make_row(2420, call_pts=3.0),
            make_row(2440, call_pts=2.0)]
    r = se._find_closest_option(rows, 2430.0, "call",
                                exclude_strikes={2410.0}, min_strike=2430.0)
    assert r["strike"] == 2440.0


def test_max_strike_ceiling_enforced():
    """Wing guard: long put must be <= ceiling."""
    rows = [make_row(1580, put_pts=3.0),
            make_row(1560, put_pts=2.0)]
    r = se._find_closest_option(rows, 1570.0, "put",
                                exclude_strikes={1590.0}, max_strike=1570.0)
    assert r["strike"] == 1560.0


def test_no_candidate_returns_synthetic_target():
    """Empty chain → synthetic target strike, unpriced."""
    r = se._find_closest_option([], 2030.0, "call")
    assert r["strike"] == 2030.0
    assert r["price"] == 0
    assert r["price_source"] == "none"


def test_clean_numeric_basics():
    assert se._clean_numeric(None) == 0.0
    assert se._clean_numeric("") == 0.0
    assert se._clean_numeric("-") == 0.0
    assert se._clean_numeric("1,234.5") == 1234.5
    assert se._clean_numeric(42) == 42.0
    assert se._clean_numeric("abc") == 0.0


def test_clean_numeric_accepts_nonfinite_BUG():
    """
    LOCKS H-2 (audit): _clean_numeric currently accepts inf/nan.
    This is the CURRENT (buggy) behaviour.
    """
    import math
    assert math.isinf(se._clean_numeric("inf"))
    assert math.isnan(se._clean_numeric("nan"))
