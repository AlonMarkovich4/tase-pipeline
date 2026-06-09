"""
Contract-multiplier lock — TA-35 options multiplier = 50 (contract value).

Domain decision (owner-confirmed): the TA-35 option multiplier is 50. This is
the single source of truth in config.TASE_MULTIPLIER and every ₪ figure derives
from it. These tests are the safety net: if anyone changes the multiplier by
mistake, the hand-computed ₪ values below stop matching and the suite fails.

Covered ₪ paths (all with the literal 50 baked into the expected numbers):
  * the constant itself
  * engine: net premium, max profit, max loss  (_calculate_condor, pure)
  * settlement P&L: max-profit zone and max-loss zone  (settle_expiry, real
    money math exercised with the network calls stubbed out)
"""
import sys, os, json
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import config
import strategy_engine as se
from tests.conftest import make_row

TOL = 0.01


# ── 0. The constant is pinned to 50 ───────────────────────────────────────
def test_multiplier_is_fifty():
    assert config.TASE_MULTIPLIER == 50
    assert se.TASE_MULTIPLIER == 50


# ── 1. Engine money path: literal ₪ values encode ×50 ─────────────────────
def test_engine_money_values_lock_multiplier():
    """
    base=2000, 1% → SC 2020 / SP 1980 / LC 2040 / LP 1960, wings 20.
      net = (2.00 + 2.00) − (0.50 + 0.50) = 3.00 pts
      max_profit = 3.00 × 50 = 150          (← locks the multiplier)
      max_risk   = 20 × 50 − 150 = 850      (← locks the multiplier)
    If the multiplier became 100 these would be 300 / 1700 and the test fails.
    """
    rows = [
        make_row(1960, call_pts=0.10, put_pts=0.50),
        make_row(1980, call_pts=0.30, put_pts=2.00),
        make_row(2000, call_pts=1.00, put_pts=1.00),
        make_row(2020, call_pts=2.00, put_pts=0.30),
        make_row(2040, call_pts=0.50, put_pts=0.10),
    ]
    r = se._calculate_condor(2000.0, 1.0, rows,
                             expiry_date="2026-06-06",
                             trigger_date="2026-06-02",
                             trigger_time="12:00")
    assert abs(r["total_net_premium"] - 3.00) < TOL
    assert abs(r["max_profit_ils"]    - 150.0) < TOL   # 3.00 × 50
    assert abs(r["max_risk_ils"]      - 850.0) < TOL   # 20×50 − 150


# ── Settlement harness: run the REAL settle_expiry with network stubbed ───
def _run_settlement(strategy: dict, index_close: float) -> dict:
    """
    Exercise settle_expiry's real P&L math (incl. pnl_ils = pnl_points × MULT)
    by stubbing _init/_sc/httpx. Returns the patch payload that would be sent.
    """
    captured = {}

    class _Resp:
        status_code = 200
        def __init__(self, payload=None): self._p = payload
        def json(self): return self._p

    def _get(url, headers=None, timeout=None):
        return _Resp([dict(strategy)])           # one unsettled strategy

    def _patch(url, headers=None, content=None, timeout=None):
        captured.update(json.loads(content))
        return _Resp()

    import pytest
    mp = pytest.MonkeyPatch()
    mp.setattr(se, "_init", lambda: None)
    mp.setattr(se, "_sc", SimpleNamespace(
        rest_url=lambda *a, **k: "http://stub",
        headers=lambda *a, **k: {}))
    mp.setattr(se, "httpx", SimpleNamespace(get=_get, patch=_patch))
    try:
        # tase_open_price in [1000,10000] is used directly as the settlement price
        se.settle_expiry("2026-06-06", tase_open_price=index_close)
    finally:
        mp.undo()
    return captured


_STRATEGY = {
    "id": 1, "interval_pct": 1.0,
    "short_put_strike": 1980.0, "long_put_strike": 1960.0,
    "short_call_strike": 2020.0, "long_call_strike": 2040.0,
    "total_net_premium": 3.00,
    "actual_wing_put": 20.0, "actual_wing_call": 20.0,
}


# ── 2. Settlement max-profit zone: ₪ = net × 50 ───────────────────────────
def test_settlement_max_profit_locks_multiplier():
    # index closes between the short strikes → keep full premium.
    patch = _run_settlement(_STRATEGY, index_close=2000.0)
    assert patch["result_status"] == "max_profit"
    assert abs(patch["actual_pnl_points"] - 3.00) < TOL
    assert abs(patch["actual_pnl_ils"]    - 150.0) < TOL   # 3.00 × 50


# ── 3. Settlement max-loss zone: ₪ = (net − wing) × 50 ────────────────────
def test_settlement_max_loss_locks_multiplier():
    # index closes below the long put → max loss on the put side.
    patch = _run_settlement(_STRATEGY, index_close=1950.0)
    assert patch["result_status"] == "max_loss_put"
    assert abs(patch["actual_pnl_points"] - (3.00 - 20.0)) < TOL   # −17 pts
    assert abs(patch["actual_pnl_ils"]    - (-850.0)) < TOL        # −17 × 50
