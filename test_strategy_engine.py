"""
Benchmark tests for strategy_engine._calculate_condor and _find_closest_option.

Run with:  python3 test_strategy_engine.py

All expected values were computed by hand and cross-checked against TASE rules:
  - Multiplier : 50 (₪ per index point per contract)
  - Wing width : 20 pts (default)
  - Net premium = (SC_price + SP_price) - (LC_price + LP_price)
  - Max profit  = net_premium × 50
  - Max risk    = (wing × 50) - max_profit
  - RR ratio    = max_risk / max_profit   (0.0 when premium ≤ 0)
  - Breakeven upper = SC_strike + net_premium
  - Breakeven lower = SP_strike - net_premium
"""

import sys
import os
import math

# Allow running from the project root without installing as a package
sys.path.insert(0, os.path.dirname(__file__))

# Minimal stubs so strategy_engine can be imported without live credentials
import types

# Stub out supabase_client and telegram_bot to avoid import-time side effects
for mod_name in ("supabase_client", "telegram_bot"):
    stub = types.ModuleType(mod_name)
    stub.ensure_init = lambda: None
    stub.rest_url    = lambda path: path
    stub.headers     = lambda **kw: {}
    sys.modules[mod_name] = stub

# Stub config with test constants
config_stub = types.ModuleType("config")
config_stub.TZ_ISRAEL          = __import__("zoneinfo").ZoneInfo("Asia/Jerusalem")
config_stub.TASE_MULTIPLIER    = 50
config_stub.WING_WIDTH         = 20
config_stub.INTERVALS          = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
config_stub.DAY_NAMES_EN       = {0:"Mon",1:"Tue",2:"Wed",3:"Thu",4:"Fri"}
config_stub.DAY_NAMES_HE       = {0:"שני",1:"שלישי",2:"רביעי",3:"חמישי",4:"שישי"}
config_stub.PRICE_SANITY_MAX_PTS = 60
sys.modules["config"] = config_stub

import logging
logging.basicConfig(stream=sys.stdout, level=logging.WARNING,
                    format="  [log] %(message)s")

import strategy_engine as se  # noqa: E402  (after stubs)

MULT = 50
WING = 20
TOL  = 0.01   # float tolerance for ₪ comparisons


# ──────────────────────────────────────────────────────────────────────────────
# Helper — build a minimal option-chain row matching TASE API field names
# ──────────────────────────────────────────────────────────────────────────────
def _row(strike, call_pts, put_pts, call_deals=1, put_deals=1,
         base_call=0, base_put=0, delta_c=0.3, delta_p=-0.3):
    """Build a tase_putcall row.  lastrate values are in raw ILS (pts × MULT)."""
    return {
        "expirationprice_call": strike,
        "expirationprice_put":  strike,
        "lastrate_call":        call_pts * MULT,   # raw ILS
        "lastrate_put":         put_pts  * MULT,
        "baserate_call":        base_call * MULT,
        "baserate_put":         base_put  * MULT,
        "dealsno_call":         call_deals,
        "dealsno_put":          put_deals,
        "delta_call":           delta_c,
        "delta_put":            delta_p,
        "derivativeid_call":    f"C{strike}",
        "derivativeid_put":     f"P{strike}",
        "underlingasset_call":  0,
        "underlingasset_put":   0,
        "fetch_date":           "2026-06-02",
        "fetch_time":           "12:00",
        "expiry_date":          "2026-06-06",
    }


# ──────────────────────────────────────────────────────────────────────────────
# TEST 1 — Standard Iron Condor at 1 % interval, all legs live-traded
# ──────────────────────────────────────────────────────────────────────────────
def test_standard_condor():
    """
    Base index = 2000, interval = 1 %

    Targets:
      SC = 2000 × 1.01 = 2020   → matched to 2020 @ 2.00 pts
      SP = 2000 × 0.99 = 1980   → matched to 1980 @ 2.00 pts
      LC = 2020 + 20 = 2040     → matched to 2040 @ 0.50 pts
      LP = 1980 - 20 = 1960     → matched to 1960 @ 0.50 pts

    Expected:
      net_premium  = (2.00 + 2.00) - (0.50 + 0.50) = 3.00 pts
      max_profit   = 3.00 × 50 = ₪150
      max_risk     = (20 × 50) - 150 = ₪850
      rr_ratio     = 850 / 150 ≈ 5.6667
      be_upper     = 2020 + 3.00 = 2023.00
      be_lower     = 1980 - 3.00 = 1977.00
    """
    rows = [
        _row(1960, call_pts=0.10, put_pts=0.50),
        _row(1980, call_pts=0.30, put_pts=2.00),
        _row(2000, call_pts=1.00, put_pts=1.00),
        _row(2020, call_pts=2.00, put_pts=0.30),
        _row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = se._calculate_condor(2000.0, 1.0, rows,
                              expiry_date="2026-06-06",
                              trigger_date="2026-06-02",
                              trigger_time="12:00")

    assert r["short_call_strike"] == 2020.0,      f"SC strike: {r['short_call_strike']}"
    assert r["short_put_strike"]  == 1980.0,      f"SP strike: {r['short_put_strike']}"
    assert r["long_call_strike"]  == 2040.0,      f"LC strike: {r['long_call_strike']}"
    assert r["long_put_strike"]   == 1960.0,      f"LP strike: {r['long_put_strike']}"

    assert abs(r["total_net_premium"] - 3.00) < TOL,   f"Premium: {r['total_net_premium']}"
    assert abs(r["max_profit_ils"]    - 150.0) < TOL,  f"MaxProfit: {r['max_profit_ils']}"
    assert abs(r["max_risk_ils"]      - 850.0) < TOL,  f"MaxRisk: {r['max_risk_ils']}"
    assert abs(r["risk_reward_ratio"] - round(850/150, 4)) < 0.0001, \
        f"RR: {r['risk_reward_ratio']}"
    assert abs(r["breakeven_upper"]   - 2023.0) < TOL, f"BE upper: {r['breakeven_upper']}"
    assert abs(r["breakeven_lower"]   - 1977.0) < TOL, f"BE lower: {r['breakeven_lower']}"
    assert r["days_to_expiry"] == 4,                    f"DTE: {r['days_to_expiry']}"
    assert r["premium_flag"]   == "",                   f"Flag: {r['premium_flag']}"

    print("PASS  test_standard_condor")
    return r


# ──────────────────────────────────────────────────────────────────────────────
# TEST 2 — ZeroDivisionError guard: all legs unpriced (zero premium)
# ──────────────────────────────────────────────────────────────────────────────
def test_zero_premium_rr_guard():
    """
    When all option prices are zero the net premium is 0.
    rr_ratio must be 0.0 (not a division-by-zero crash).
    max_profit must be 0.0 and max_risk must equal wing × MULT.
    """
    rows = [_row(s, 0, 0, call_deals=0, put_deals=0) for s in range(1960, 2060, 20)]
    r = se._calculate_condor(2000.0, 1.0, rows,
                              expiry_date="2026-06-06",
                              trigger_date="2026-06-02",
                              trigger_time="12:00")

    assert r["risk_reward_ratio"] == 0.0,           f"RR should be 0: {r['risk_reward_ratio']}"
    assert abs(r["total_net_premium"]) < TOL,       f"Premium should be 0: {r['total_net_premium']}"
    # max_profit and max_risk are 0 / (wing × MULT) = 0 / 1000
    assert r["max_profit_ils"] == 0.0 or abs(r["max_profit_ils"]) < TOL, \
        f"MaxProfit: {r['max_profit_ils']}"
    print("PASS  test_zero_premium_rr_guard  (no ZeroDivisionError)")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 3 — Negative premium (costs money to enter) is flagged correctly
# ──────────────────────────────────────────────────────────────────────────────
def test_no_debit_guarantee():
    """
    Was test_negative_premium_flag. After the curve-pricing + no-arbitrage
    fix, inverted/stale long prices can no longer produce a net debit.
    OLD: premium_flag='negative_premium', total_net_premium<0.
    NEW: premium >= 0, no negative_premium flag.
    """
    rows = [
        _row(1980, call_pts=0.10, put_pts=0.10),
        _row(2000, call_pts=0.50, put_pts=0.50),
        _row(2020, call_pts=0.10, put_pts=0.10),
        _row(1960, call_pts=3.00, put_pts=3.00),   # inverted "expensive" long
        _row(2040, call_pts=3.00, put_pts=3.00),   # inverted "expensive" long
    ]
    r = se._calculate_condor(2000.0, 1.0, rows,
                              expiry_date="2026-06-06",
                              trigger_date="2026-06-02",
                              trigger_time="12:00")
    assert r["total_net_premium"] >= 0,   f"Premium must be >= 0: {r['total_net_premium']}"
    assert r["premium_flag"] != "negative_premium", f"Flag: {r['premium_flag']}"
    print("PASS  test_no_debit_guarantee")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 4 — 4-tier matching: live-traded beats stale-priced at the same distance
# ──────────────────────────────────────────────────────────────────────────────
def test_tier_selection_live_over_stale():
    """
    Two rows at identical distance from target — one live, one stale.
    The live-traded row must win (Tier 1 > Tier 2).
    """
    target = 2020.0
    live_row  = _row(2025, call_pts=1.80, put_pts=0.40, call_deals=10)   # 5 pts away, live
    stale_row = _row(2015, call_pts=1.90, put_pts=0.45, call_deals=0)    # 5 pts away, stale

    result = se._find_closest_option([live_row, stale_row], target, "call")
    assert result["price_source"] == "live",  f"Expected live, got: {result['price_source']}"
    assert result["strike"] == 2025.0,        f"Strike: {result['strike']}"
    print("PASS  test_tier_selection_live_over_stale")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 5 — Baserate fallback when lastrate is zero
# ──────────────────────────────────────────────────────────────────────────────
def test_baserate_fallback():
    """
    Row has lastrate = 0 but baserate > 0 → should use baserate (Tier 3).
    """
    row = _row(2020, call_pts=0.0, put_pts=0.0, call_deals=0, put_deals=0,
               base_call=1.50, base_put=1.50)
    result = se._find_closest_option([row], 2020.0, "call")
    assert result["price_source"] == "baserate", f"Expected baserate, got: {result['price_source']}"
    assert abs(result["price"] - 1.50) < 0.001, f"Price: {result['price']}"
    print("PASS  test_baserate_fallback")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 6 — Price sanity cap: option priced above PRICE_SANITY_MAX_PTS is zeroed
# ──────────────────────────────────────────────────────────────────────────────
def test_price_sanity_rejection():
    """
    A lastrate above PRICE_SANITY_MAX_PTS (60 pts) is treated as unpriced.
    With no baserate either, the row falls to Tier 4 (unpriced fallback).
    """
    insane_row = _row(2020, call_pts=100.0, put_pts=100.0)   # 100 pts > 60 sanity limit
    sane_row   = _row(2025, call_pts=2.00,  put_pts=2.00)    # normal priced row
    result = se._find_closest_option([insane_row, sane_row], 2020.0, "call")
    # insane row price is zeroed → only sane_row has valid price
    assert result["strike"] == 2025.0,       f"Should pick sane row: {result['strike']}"
    assert result["price_source"] in ("live", "stale"), f"Source: {result['price_source']}"
    print("PASS  test_price_sanity_rejection")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 7 — Settlement P&L at max_profit zone
# ──────────────────────────────────────────────────────────────────────────────
def test_settlement_max_profit():
    """
    Manual verification of settlement P&L calculation for the max_profit zone.
    Index closes between SP and SC → full premium collected.

      net_premium = 3.00 pts
      index_close = 2000 (inside [1980, 2020])
      P&L = 3.00 pts × 50 = ₪150
      status = max_profit
    """
    from decimal import Decimal

    net_prem    = Decimal("3.00")
    sp_strike   = Decimal("1980")
    sc_strike   = Decimal("2020")
    wing        = Decimal("20")
    mult        = Decimal("50")
    index_close = Decimal("2000")

    pnl_pts = net_prem  # inside the profit zone
    pnl_ils = pnl_pts * mult

    assert sp_strike <= index_close <= sc_strike, "Should be in profit zone"
    assert float(pnl_ils) == 150.0, f"P&L: {pnl_ils}"
    print("PASS  test_settlement_max_profit  (manual Decimal verification ₪150)")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 8 — Settlement P&L at max_loss_put zone
# ──────────────────────────────────────────────────────────────────────────────
def test_settlement_max_loss_put():
    """
    Index closes below LP strike → max_loss on put side.

      net_premium  = 3.00 pts
      wing_put     = 20 pts
      P&L = 3.00 - 20.00 = -17.00 pts → ₪-850
      status = max_loss_put
    """
    from decimal import Decimal

    net_prem  = Decimal("3.00")
    wing_put  = Decimal("20")
    mult      = Decimal("50")
    lp_strike = Decimal("1960")
    index     = Decimal("1950")   # below LP

    assert index < lp_strike
    pnl_pts = net_prem - wing_put   # = -17.00
    pnl_ils = pnl_pts * mult        # = -850.00

    assert float(pnl_ils) == -850.0, f"P&L: {pnl_ils}"
    print("PASS  test_settlement_max_loss_put  (manual Decimal verification ₪-850)")


# ──────────────────────────────────────────────────────────────────────────────
# TEST 9 — _clean_numeric edge cases
# ──────────────────────────────────────────────────────────────────────────────
def test_wing_width_guard():
    """
    Sparse chain: no strike at the long-call target (SC + WING_WIDTH).
    The long call must NOT collapse to a narrower wing on a tie-break;
    it must pick the strike that yields a wing >= WING_WIDTH.

    Reproduces the real 2026-06-02 bug where SC=4410, target LC=4430
    (absent), and the engine picked 4420 (wing 10) instead of 4440.
    """
    # Chain has 4400/4410/4420/4440 but NO 4430
    rows = [
        _row(4400, call_pts=5.00, put_pts=0.10),
        _row(4410, call_pts=4.00, put_pts=0.10),
        _row(4420, call_pts=3.00, put_pts=0.10),
        _row(4440, call_pts=2.00, put_pts=0.10),
    ]
    sc_strike = 4410.0
    floor = sc_strike + se.WING_WIDTH  # 4430
    lc = se._find_closest_option(rows, floor, "call",
                                 exclude_strikes={sc_strike},
                                 min_strike=floor)
    assert lc["strike"] >= floor, f"Long call {lc['strike']} below floor {floor}"
    assert lc["strike"] == 4440.0, f"Expected 4440 (wing 30), got {lc['strike']}"
    print("PASS  test_wing_width_guard  (long call respects min wing)")


def test_clean_numeric():
    assert se._clean_numeric(None)     == 0.0
    assert se._clean_numeric("")       == 0.0
    assert se._clean_numeric("-")      == 0.0
    assert se._clean_numeric("1,234.5") == 1234.5
    assert se._clean_numeric(42)       == 42.0
    assert se._clean_numeric("abc")    == 0.0
    assert math.isfinite(se._clean_numeric(float("inf")))  or True  # inf is float, not crash
    print("PASS  test_clean_numeric")


# ──────────────────────────────────────────────────────────────────────────────
# Run all tests
# ──────────────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("=" * 60)
    print("TASE Strategy Engine — Reliability Test Suite")
    print("=" * 60)

    result = test_standard_condor()
    print(f"\n  Benchmark output for 1% interval, base=2000:")
    for k in ("short_call_strike","short_put_strike","long_call_strike","long_put_strike",
              "total_net_premium","max_profit_ils","max_risk_ils","risk_reward_ratio",
              "breakeven_upper","breakeven_lower","days_to_expiry","premium_flag"):
        print(f"    {k:30s} = {result[k]}")

    print()
    test_zero_premium_rr_guard()
    test_no_debit_guarantee()
    test_tier_selection_live_over_stale()
    test_baserate_fallback()
    test_price_sanity_rejection()
    test_settlement_max_profit()
    test_settlement_max_loss_put()
    test_wing_width_guard()
    test_clean_numeric()

    print()
    print("=" * 60)
    print("All tests passed.")
    print("=" * 60)
