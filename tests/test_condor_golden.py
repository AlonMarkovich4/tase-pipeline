"""
Golden / hand-computed characterization tests for _calculate_condor.

These lock the CURRENT behaviour (correct or not). Hand-computed values are
documented inline so any future change is visible in the diff.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import strategy_engine as se
from tests.conftest import make_row

TOL = 0.01


def _calc(base, pct, rows):
    return se._calculate_condor(base, pct, rows,
                                expiry_date="2026-06-06",
                                trigger_date="2026-06-02",
                                trigger_time="12:00")


# ── Golden 1: symmetric 1% condor, all legs live ──────────────────────────
def test_golden_symmetric_condor():
    """
    base=2000, 1% → SC target 2020, SP target 1980, LC 2040, LP 1960.
      net = (2.00 + 2.00) − (0.50 + 0.50) = 3.00 pts
      max_profit = 3.00 × 50 = 150
      max_risk   = 20×50 − 150 = 850
      BE_upper = 2020 + 3 = 2023 ; BE_lower = 1980 − 3 = 1977
      RR = 850/150 = 5.6667
    """
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2000, call_pts=1.00, put_pts=1.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    assert r["short_call_strike"] == 2020.0
    assert r["short_put_strike"]  == 1980.0
    assert r["long_call_strike"]  == 2040.0
    assert r["long_put_strike"]   == 1960.0
    assert abs(r["total_net_premium"] - 3.00) < TOL
    assert abs(r["max_profit_ils"]    - 150.0) < TOL
    assert abs(r["max_risk_ils"]      - 850.0) < TOL
    assert abs(r["breakeven_upper"]   - 2023.0) < TOL
    assert abs(r["breakeven_lower"]   - 1977.0) < TOL
    assert abs(r["risk_reward_ratio"] - round(850/150, 4)) < 1e-4
    assert r["premium_flag"] == ""
    assert r["days_to_expiry"] == 4   # 2026-06-06 − 2026-06-02 (migrated from the root benchmark)


# ── Golden 2: invariant — max_profit == net_premium × multiplier ──────────
def test_golden_max_profit_identity():
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    assert abs(r["max_profit_ils"]
               - r["total_net_premium"] * se.TASE_MULTIPLIER) < TOL


# ── Golden 3: invariant — max_risk == wing_max×mult − max_profit ──────────
def test_golden_max_risk_identity():
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    wing_max = max(r["actual_wing_put"], r["actual_wing_call"])
    expected_risk = wing_max * se.TASE_MULTIPLIER - r["max_profit_ils"]
    assert abs(r["max_risk_ils"] - expected_risk) < TOL


# ── Golden 4: breakevens lie inside the wings ─────────────────────────────
def test_golden_breakevens_within_wings():
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    assert r["long_put_strike"]  < r["breakeven_lower"] < r["short_put_strike"]
    assert r["short_call_strike"] < r["breakeven_upper"] < r["long_call_strike"]


# ── Golden 5: strike ordering invariant on a normal chain ─────────────────
def test_golden_strike_ordering():
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    assert (r["long_put_strike"] < r["short_put_strike"]
            < r["short_call_strike"] < r["long_call_strike"])


# ── Golden 6: wing-width guard (sparse chain, no 2030 strike) ─────────────
def test_golden_wing_guard_sparse_chain():
    """SC=2020, LC target 2040 absent → must pick 2050 (wing 30) not 2025."""
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2025, call_pts=1.50, put_pts=0.25),  # only 5 from SC
        make_row(2050, call_pts=0.40, put_pts=0.08),  # 30 from SC
    ]
    r = _calc(2000.0, 1.0, rows)
    assert r["long_call_strike"] >= r["short_call_strike"] + se.WING_WIDTH
