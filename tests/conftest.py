"""
Shared pytest fixtures and import stubs for the engine test suite.

strategy_engine imports supabase_client, telegram_bot and config at module
load. We stub the first two (network/credential side effects) and load the
REAL config so the multiplier / wing / intervals match production.
"""
import os
import sys
import types

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

# ── Stub network-touching modules before strategy_engine imports them ──
for _mod in ("supabase_client", "telegram_bot"):
    if _mod not in sys.modules:
        stub = types.ModuleType(_mod)
        stub.ensure_init = lambda: None
        stub.rest_url    = lambda path: path
        stub.headers     = lambda **kw: {}
        # telegram alert functions used by the engine — make them no-ops
        stub.alert_strategy_launch = lambda *a, **k: None
        stub.alert_settlement      = lambda *a, **k: None
        sys.modules[_mod] = stub

# Real config (production constants) — do NOT stub, we want true values.
import config  # noqa: E402,F401

import strategy_engine as se   # noqa: E402
import option_schema as osch   # noqa: E402


import pytest


@pytest.fixture
def MULT():
    return se.TASE_MULTIPLIER


@pytest.fixture
def WING():
    return se.WING_WIDTH


def make_row(strike, call_pts=0.0, put_pts=0.0,
             call_deals=1, put_deals=1,
             base_call=0.0, base_put=0.0,
             delta_c=30, delta_p=30,
             expiry="2026-06-06", fetch_date="2026-06-02", fetch_time="12:00"):
    """Build one tase_putcall row (snake_case, lastrate in raw ₪ = pts × MULT)."""
    m = se.TASE_MULTIPLIER
    return {
        "expirationprice_call": strike,
        "expirationprice_put":  strike,
        "lastrate_call":        call_pts * m,
        "lastrate_put":         put_pts  * m,
        "baserate_call":        base_call * m,
        "baserate_put":         base_put  * m,
        "dealsno_call":         call_deals,
        "dealsno_put":          put_deals,
        "delta_call":           delta_c,
        "delta_put":            delta_p,
        "derivativeid_call":    f"C{strike}",
        "derivativeid_put":     f"P{strike}",
        "underlingasset_call":  0,
        "underlingasset_put":   0,
        "fetch_date":           fetch_date,
        "fetch_time":           fetch_time,
        "expiry_date":          expiry,
    }
