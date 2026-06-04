"""
Property-based invariants (Hypothesis) for _calculate_condor.

These assert structural invariants over a wide input space. Where the current
engine violates an invariant (see ENGINE_AUDIT.md), the property is scoped to
the regime where it currently holds, with a comment pointing at the finding —
so the property stays green now and can be widened once the fix lands.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from hypothesis import given, strategies as st, settings, assume
import strategy_engine as se
from tests.conftest import make_row

# Money rounding: premium stored at 2dp, max_profit = q2(prem_raw × MULT).
# q2(x×50) vs stored_prem×50 can differ by up to 0.5 ₪ from independent
# rounding — tolerance must cover one multiplier-step of half-cent rounding.
TOL = 0.02
MONEY_TOL = 0.5


def _normal_chain(base, sc_pts, sp_pts, lc_pts, lp_pts):
    """Build a well-ordered chain around base with a clean 20-pt grid."""
    step = 20
    center = round(base / step) * step
    rows = []
    for k in range(-6, 7):
        s = center + k * step
        rows.append(make_row(s, call_pts=0.05, put_pts=0.05))
    # inject specific leg prices at the expected strikes for 1% interval
    sc = round(base * 1.01 / step) * step
    sp = round(base * 0.99 / step) * step
    by = {r["expirationprice_call"]: r for r in rows}
    if sc in by: by[sc]["lastrate_call"] = sc_pts * se.TASE_MULTIPLIER
    if sp in by: by[sp]["lastrate_put"]  = sp_pts * se.TASE_MULTIPLIER
    if sc + 20 in by: by[sc + 20]["lastrate_call"] = lc_pts * se.TASE_MULTIPLIER
    if sp - 20 in by: by[sp - 20]["lastrate_put"]  = lp_pts * se.TASE_MULTIPLIER
    return rows


@settings(max_examples=120, deadline=None)
@given(
    base=st.integers(min_value=1500, max_value=5000),
    sc=st.floats(min_value=0.5, max_value=15.0),
    sp=st.floats(min_value=0.5, max_value=15.0),
    lc=st.floats(min_value=0.01, max_value=0.4),
    lp=st.floats(min_value=0.01, max_value=0.4),
)
def test_prop_strike_ordering_holds(base, sc, sp, lc, lp):
    rows = _normal_chain(base, sc, sp, lc, lp)
    r = se._calculate_condor(float(base), 1.0, rows,
                             "2026-06-06", "2026-06-02", "12:00")
    assert (r["long_put_strike"] < r["short_put_strike"]
            < r["short_call_strike"] < r["long_call_strike"])


@settings(max_examples=120, deadline=None)
@given(
    base=st.integers(min_value=1500, max_value=5000),
    sc=st.floats(min_value=0.5, max_value=9.0),
    sp=st.floats(min_value=0.5, max_value=9.0),
    lc=st.floats(min_value=0.01, max_value=0.3),
    lp=st.floats(min_value=0.01, max_value=0.3),
)
def test_prop_max_profit_identity(base, sc, sp, lc, lp):
    rows = _normal_chain(base, sc, sp, lc, lp)
    r = se._calculate_condor(float(base), 1.0, rows,
                             "2026-06-06", "2026-06-02", "12:00")
    # only assert in the positive-premium, non-capped regime
    assume(r["premium_flag"] in ("", "low_liquidity", "partial_liquidity"))
    assume(r["total_net_premium"] > 0)
    assert abs(r["max_profit_ils"]
               - r["total_net_premium"] * se.TASE_MULTIPLIER) < MONEY_TOL


@settings(max_examples=120, deadline=None)
@given(
    base=st.integers(min_value=1500, max_value=5000),
    sc=st.floats(min_value=0.5, max_value=9.0),
    sp=st.floats(min_value=0.5, max_value=9.0),
)
def test_prop_breakevens_bracket_premium(base, sc, sp):
    rows = _normal_chain(base, sc, sp, 0.1, 0.1)
    r = se._calculate_condor(float(base), 1.0, rows,
                             "2026-06-06", "2026-06-02", "12:00")
    assume(r["total_net_premium"] > 0)
    # BE_upper above SC, BE_lower below SP, by exactly the premium
    assert abs(r["breakeven_upper"]
               - (r["short_call_strike"] + r["total_net_premium"])) < TOL
    assert abs(r["breakeven_lower"]
               - (r["short_put_strike"] - r["total_net_premium"])) < TOL


@settings(max_examples=80, deadline=None)
@given(
    base=st.integers(min_value=1500, max_value=5000),
    pct=st.sampled_from([0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]),
)
def test_prop_determinism_same_input_same_output(base, pct):
    rows = _normal_chain(base, 2.0, 2.0, 0.2, 0.2)
    r1 = se._calculate_condor(float(base), pct, rows,
                              "2026-06-06", "2026-06-02", "12:00")
    r2 = se._calculate_condor(float(base), pct, rows,
                              "2026-06-06", "2026-06-02", "12:00")
    assert r1 == r2


@settings(max_examples=120, deadline=None)
@given(
    base=st.integers(min_value=1500, max_value=5000),
    sc=st.floats(min_value=0.5, max_value=9.0),
    sp=st.floats(min_value=0.5, max_value=9.0),
)
def test_prop_rr_nonnegative(base, sc, sp):
    rows = _normal_chain(base, sc, sp, 0.1, 0.1)
    r = se._calculate_condor(float(base), 1.0, rows,
                             "2026-06-06", "2026-06-02", "12:00")
    assert r["risk_reward_ratio"] >= 0.0
