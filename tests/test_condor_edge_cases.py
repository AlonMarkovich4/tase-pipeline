"""
Characterization tests for edge cases in _calculate_condor and pricing tiers.
These LOCK current behaviour — including behaviour the audit flags as wrong.
Each test documents whether it pins correct or buggy behaviour (see ENGINE_AUDIT.md).
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import strategy_engine as se
from tests.conftest import make_row

TOL = 0.01


def _calc(base, pct, rows, expiry="2026-06-06",
          trigger="2026-06-02", ttime="12:00"):
    return se._calculate_condor(base, pct, rows, expiry, trigger, ttime)


# ── Zero / missing premium → no ZeroDivision, RR == 0 ─────────────────────
def test_zero_premium_rr_guard():
    rows = [make_row(s, call_pts=0, put_pts=0, call_deals=0, put_deals=0)
            for s in range(1960, 2060, 20)]
    r = _calc(2000.0, 1.0, rows)
    assert r["risk_reward_ratio"] == 0.0
    assert r["max_profit_ils"] <= 0.0


# ── price_capped: premium impossibly larger than wing ─────────────────────
def test_premium_capped_to_wing():
    """Short legs absurdly expensive, longs cheap → premium > wing → cap."""
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.10),
        make_row(1980, call_pts=0.10, put_pts=50.0),   # SP huge
        make_row(2020, call_pts=50.0, put_pts=0.10),   # SC huge
        make_row(2040, call_pts=0.10, put_pts=0.10),
    ]
    r = _calc(2000.0, 1.0, rows)
    # premium capped to wing (20); flag set
    assert r["premium_flag"] == "price_capped"
    assert abs(r["total_net_premium"] - 20.0) < TOL


# ── negative premium (debit) — H-1: numbers are currently nonsensical ─────
def test_negative_premium_keeps_raw_numbers_BUG():
    """
    LOCKS H-1 (audit): debit condor keeps a negative max_profit and
    inflated max_risk. This is the CURRENT (buggy) behaviour.
    """
    rows = [
        make_row(1960, call_pts=0.10, put_pts=5.00),   # LP expensive
        make_row(1980, call_pts=0.30, put_pts=0.10),   # SP cheap
        make_row(2020, call_pts=0.10, put_pts=0.30),   # SC cheap
        make_row(2040, call_pts=5.00, put_pts=0.10),   # LC expensive
    ]
    r = _calc(2000.0, 1.0, rows)
    assert r["premium_flag"] == "negative_premium"
    assert r["total_net_premium"] < 0        # negative credit
    assert r["max_profit_ils"] < 0           # BUG: negative "max profit"
    assert r["max_risk_ils"] > se.WING_WIDTH * se.TASE_MULTIPLIER  # BUG: risk > wing notional


# ── settlement exactly on a strike boundary ───────────────────────────────
def test_settlement_boundary_on_short_put():
    """
    index == short_put → max_profit branch (sp <= index <= sc inclusive).
    Locks the inclusive-boundary behaviour.
    """
    # Build a single strategy dict as settle_expiry consumes from DB
    strat = {
        "id": 1, "interval_pct": 1.0,
        "short_put_strike": 1980, "long_put_strike": 1960,
        "short_call_strike": 2020, "long_call_strike": 2040,
        "total_net_premium": 3.0,
        "actual_wing_put": 20, "actual_wing_call": 20,
        "base_index_value": 2000,
    }
    pnl_pts, status = _settle_one(strat, index_close=1980.0)
    assert status == "max_profit"
    assert abs(pnl_pts - 3.0) < TOL


def test_settlement_max_loss_put():
    strat = {
        "id": 1, "interval_pct": 1.0,
        "short_put_strike": 1980, "long_put_strike": 1960,
        "short_call_strike": 2020, "long_call_strike": 2040,
        "total_net_premium": 3.0,
        "actual_wing_put": 20, "actual_wing_call": 20,
        "base_index_value": 2000,
    }
    pnl_pts, status = _settle_one(strat, index_close=1900.0)
    assert status == "max_loss_put"
    assert abs(pnl_pts - (3.0 - 20.0)) < TOL  # = -17 pts


def test_settlement_pnl_within_envelope():
    """Invariant: for a SYMMETRIC condor, settlement P&L ∈ [−max_loss, +max_profit]."""
    strat = {
        "id": 1, "interval_pct": 1.0,
        "short_put_strike": 1980, "long_put_strike": 1960,
        "short_call_strike": 2020, "long_call_strike": 2040,
        "total_net_premium": 3.0,
        "actual_wing_put": 20, "actual_wing_call": 20,
        "base_index_value": 2000,
    }
    max_profit = 3.0
    max_loss   = 3.0 - 20.0  # -17
    for idx in (1900, 1960, 1970, 1980, 2000, 2020, 2030, 2040, 2100):
        pnl_pts, _ = _settle_one(strat, float(idx))
        assert max_loss - TOL <= pnl_pts <= max_profit + TOL, \
            f"index {idx}: pnl {pnl_pts} outside [{max_loss}, {max_profit}]"


# ── C-2 reproduction: asymmetric wing + premium ≥ narrow wing ─────────────
def test_settlement_max_loss_call_can_be_positive_BUG():
    """
    LOCKS C-2 (audit): with wing_call < premium, a 'max_loss_call' settlement
    yields a POSITIVE P&L. This is the CURRENT (buggy) behaviour.
    """
    strat = {
        "id": 1, "interval_pct": 0.5,
        "short_put_strike": 4330, "long_put_strike": 4310,
        "short_call_strike": 4410, "long_call_strike": 4420,
        "total_net_premium": 11.0,          # > wing_call (10)
        "actual_wing_put": 20, "actual_wing_call": 10,
        "base_index_value": 4355,
    }
    pnl_pts, status = _settle_one(strat, index_close=4500.0)  # above LC
    assert status == "max_loss_call"
    assert pnl_pts > 0   # BUG: a "max loss" that is actually a profit


# ──────────────────────────────────────────────────────────────────────────
# Helper: run the settlement math for ONE strategy without network.
# Mirrors settle_expiry's per-strategy block exactly (Decimal path).
# ──────────────────────────────────────────────────────────────────────────
from decimal import Decimal, ROUND_HALF_EVEN


def _settle_one(s, index_close):
    MULT = Decimal(str(se.TASE_MULTIPLIER))
    WING_D = Decimal(str(se.WING_WIDTH))
    ZERO = Decimal("0")
    icd = se._to_decimal(index_close)
    sp_d = se._to_decimal(s["short_put_strike"])
    lp_d = se._to_decimal(s["long_put_strike"])
    sc_d = se._to_decimal(s["short_call_strike"])
    lc_d = se._to_decimal(s["long_call_strike"])
    raw_prem = se._to_decimal(s["total_net_premium"])
    wing_put = se._to_decimal(s["actual_wing_put"]) or (sp_d - lp_d) or WING_D
    wing_call = se._to_decimal(s["actual_wing_call"]) or (lc_d - sc_d) or WING_D
    wing_max = max(wing_put, wing_call)
    net = wing_max if raw_prem > wing_max else raw_prem
    if sp_d <= icd <= sc_d:
        pnl = net; status = "max_profit"
    elif lp_d <= icd < sp_d:
        pnl = net - (sp_d - icd); status = "partial_loss_put"
    elif sc_d < icd <= lc_d:
        pnl = net - (icd - sc_d); status = "partial_loss_call"
    elif icd < lp_d:
        pnl = net - wing_put; status = "max_loss_put"
    else:
        pnl = net - wing_call; status = "max_loss_call"
    return float(pnl), status
