"""
Casing regression tests for option_schema.validate_items.

Bug: TASE shipped lowercase-suffix API keys (ExpirationPrice_call / LastRate_call
/ LastRate_put) while the validation layer read CamelCase (_Call/_Put), so the
quality gate went blind and flagged ALL_PRICES_ZERO + DUPLICATE_STRIKES on every
cycle regardless of the real data. Verified against diag_raw_response.json.

These tests pin:
  * the gate now reads values under EITHER casing (the fix),
  * a genuinely empty / all-zero feed is STILL rejected (no false-clear),
  * both casings produce identical results.
"""
import os
import json
from datetime import datetime
from zoneinfo import ZoneInfo

import option_schema as osch

# Fresh trade-date so STALE_TRADE_DATE never contaminates has_critical here.
_TODAY = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y")
_REPO = os.path.dirname(os.path.dirname(__file__))


def _codes(res):
    return {w.code for w in res.warnings}


# ── Synthetic fixtures ────────────────────────────────────────────────────
def _full_item(strike, call_rate, put_rate, suffix):
    """One populated put/call row. suffix='call'/'put' (TASE) or 'Call'/'Put'."""
    c = suffix  # 'call' or 'Call'
    p = "put" if suffix.islower() else "Put"
    return {
        "rowType": "001", "drvType": "04",
        f"ExpirationPrice_{c}": str(strike),
        f"ExpirationPrice_{p}": str(strike),
        f"LastRate_{c}": str(call_rate),
        f"LastRate_{p}": str(put_rate),
        f"Delta_{c}": "30", f"Delta_{p}": "-30",   # put delta negative (TASE convention)
        f"ExpirationDate_{c}": "10/06/2026",
    }


def _chain(suffix, call_rate=120.0, put_rate=110.0):
    # 8 DISTINCT strikes, non-zero prices → should pass the gate cleanly.
    return [_full_item(s, call_rate, put_rate, suffix)
            for s in range(4100, 4260, 20)]


FULL_LOWER = _chain("call")                       # TASE's current casing
FULL_CAMEL = _chain("Call")                       # legacy casing
ZEROS_LOWER = _chain("call", call_rate=0, put_rate=0)   # real zero prices


def _validate(items):
    return osch.validate_items(items, _TODAY.replace("/", "-"), _TODAY, "2026-06-10")


# ── 1. The fix: populated lowercase chain passes the gate ─────────────────
def test_full_lowercase_passes():
    res = _validate(FULL_LOWER)
    assert "ALL_PRICES_ZERO" not in _codes(res)
    assert "DUPLICATE_STRIKES" not in _codes(res)
    assert res.accepted_count == len(FULL_LOWER)


# ── 2. Legacy CamelCase still works (no regression) ───────────────────────
def test_full_camelcase_passes():
    res = _validate(FULL_CAMEL)
    assert "ALL_PRICES_ZERO" not in _codes(res)
    assert "DUPLICATE_STRIKES" not in _codes(res)


# ── 3. Both casings read identically ──────────────────────────────────────
def test_both_casings_equivalent():
    assert _codes(_validate(FULL_LOWER)) == _codes(_validate(FULL_CAMEL))


# ── 4. Real zero prices are STILL rejected (didn't break empty detection) ──
def test_real_zeros_still_rejected():
    res = _validate(ZEROS_LOWER)
    assert "ALL_PRICES_ZERO" in _codes(res)


# ── 5. The real diag fixture (live problematic snapshot) is rejected ──────
def test_diag_snapshot_now_parses():
    """
    End-state after the casing + ceiling + delta fixes: the real snapshot now
    PARSES — nearly all rows accepted, only the strike=1 header row dropped, and
    no parsing-driven CRITICAL (with a fresh trade-date). Today's only legitimate
    block would be STALE_TRADE_DATE (data is genuinely Friday's), which is
    isolated here by passing a fresh date.
    """
    data = json.load(open(os.path.join(_REPO, "diag_raw_response.json")))
    items = data.get("Items", [])
    assert items, "diag fixture should contain Items"
    res = _validate(items)
    assert res.accepted_count >= 28
    crit = {w.code for w in res.warnings if w.level == osch.DQLevel.CRITICAL}
    assert not crit                     # no parsing-driven CRITICAL any more


# ── 6. Proof the model now READS lowercase values (not just stops ignoring) ─
def test_model_reads_lowercase_value():
    """A single populated lowercase row validates and round-trips its strike."""
    item = _full_item(4200, 120.0, 110.0, "call")
    m = osch.OptionPair.model_validate(item)
    assert m.ExpirationPrice_Call == 4200
    assert m.LastRate_Call == 120
    assert m.LastRate_Put == 110
