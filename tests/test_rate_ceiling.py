"""
Rate-ceiling (_RATE_MAX) leg-level handling tests (Bug #4).

A single over-ceiling leg must NOT reject its row / cascade to ITEMS_REJECTED.
The engine only uses strikes within ±max(INTERVALS)% (+wing) of spot, so:
  * deep-ITM over-ceiling leg          -> filter the leg silently, row survives
  * near-money over-ceiling leg (spot) -> filter the leg + flag (INFLATED_NEAR_MONEY)
  * over-ceiling leg with no spot       -> filter the leg + WARNING log
"""
import os
import json
import logging
from datetime import datetime
from zoneinfo import ZoneInfo

import option_schema as osch

_TODAY = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%d/%m/%Y")
_REPO = os.path.dirname(os.path.dirname(__file__))


def _codes(res):
    return {w.code for w in res.warnings}


def _diag_items():
    return json.load(open(os.path.join(_REPO, "diag_raw_response.json")))["Items"]


def _validate(items):
    return osch.validate_items(items, "2026-06-08", _TODAY, "2026-06-10")


def _item(strike, lr_call, lr_put, spot=None):
    d = {
        "rowType": "001", "drvType": "04",
        "ExpirationPrice_Call": str(strike), "ExpirationPrice_Put": str(strike),
        "LastRate_Call": str(lr_call), "LastRate_Put": str(lr_put),
        "Delta_Call": "30", "Delta_Put": "-30",   # put delta negative (TASE convention)
    }
    if spot is not None:
        d["UnderlingAsset_Call"] = str(spot)
        d["UnderlingAsset_Put"] = str(spot)
    return d


# ── 1. #4 proof at chain level: a deep-ITM chain now survives ─────────────
def test_deep_itm_chain_survives():
    # 8 distinct deep-ITM strikes (≥260 pts from spot 4200 > band ≈188),
    # each with an over-ceiling call + cheap OTM put + valid deltas.
    items = [_item(s, lr_call=20000, lr_put=5, spot=4200)
             for s in range(3800, 3960, 20)]
    res = _validate(items)
    assert "ITEMS_REJECTED" not in _codes(res)        # no cascade
    assert "INFLATED_NEAR_MONEY" not in _codes(res)   # deep-ITM = silent
    assert res.accepted_count == len(items)           # all rows survive
    assert all(it.get("LastRate_Call") is None for it in items)  # legs filtered


# ── 1b. After #4 AND #5: the diag passes validation (only the strike=1 header
#        row is dropped). Neither the ceiling nor the put-delta sign blocks now.
def test_diag_passes_after_ceiling_and_delta_fixes():
    items = _diag_items()
    res = osch.validate_items(items, "2026-06-08", "08/06/2026", "2026-06-10")  # fresh date
    assert res.accepted_count >= 28      # was 1/31; now ~30/31
    crit = {w.code for w in res.warnings if w.level == osch.DQLevel.CRITICAL}
    assert "ITEMS_REJECTED" not in crit  # dropped from CRITICAL(97%) to WARNING(3%)
    # neither ceiling nor delta is a rejection reason any more
    reasons = []
    for it in items:
        try:
            osch.OptionPair.model_validate(it)
        except Exception as e:
            reasons.append(str(e).lower())
    assert not any("ceiling" in r for r in reasons)
    assert not any("delta" in r for r in reasons)


def test_diag_delta_parity_sanity():
    """Documents the convention: |Δcall| + |Δput| ≈ 100 across the diag."""
    items = _diag_items()
    checked = 0
    for it in items:
        dc = osch._parse_number(it.get("Delta_call"))
        dp = osch._parse_number(it.get("Delta_put"))
        if dc is not None and dp is not None and (dc != 0 or dp != 0):
            assert abs(abs(dc) + abs(dp) - 100) <= 1   # parity within 1 pt
            checked += 1
    assert checked >= 10


# ── 2. Deep-ITM over-ceiling leg is filtered silently; row survives ───────
def test_deep_itm_filtered_silently():
    # spot 4200; strike 3800 is 400 pts away (> ±4%+wing band ≈188) -> deep-ITM
    items = [_item(3800, lr_call=20000, lr_put=5, spot=4200)]
    res = _validate(items)
    assert "INFLATED_NEAR_MONEY" not in _codes(res)   # no flag for deep-ITM
    assert res.accepted_count == 1                     # row survived
    assert items[0].get("LastRate_Call") is None       # inflated leg filtered


# ── 3. Near-money over-ceiling leg IS flagged (protection preserved) ──────
def test_near_money_inflated_flagged():
    # spot 4200; strike 4210 within band -> inflated near-money must be caught
    items = [_item(4210, lr_call=20000, lr_put=100, spot=4200)]
    res = _validate(items)
    assert "INFLATED_NEAR_MONEY" in _codes(res)
    flag = next(w for w in res.warnings if w.code == "INFLATED_NEAR_MONEY")
    assert flag.level == osch.DQLevel.WARNING
    assert items[0].get("LastRate_Call") is None       # inflated leg still filtered


# ── 4a. No-spot over-ceiling leg: filtered + WARNING log ──────────────────
def test_no_spot_filtered_with_warning(caplog):
    items = [_item(4210, lr_call=20000, lr_put=100, spot=None)]
    with caplog.at_level(logging.WARNING, logger="tase_pipeline"):
        res = _validate(items)
    assert res.accepted_count == 1
    assert items[0].get("LastRate_Call") is None
    assert any("no spot" in r.message.lower() or "ceiling check skipped" in r.message.lower()
               for r in caplog.records)


# ── 4b. Fully-valid row passes through unchanged ──────────────────────────
def test_valid_row_unchanged():
    items = [_item(4210, lr_call=120, lr_put=110, spot=4200)]
    res = _validate(items)
    assert "INFLATED_NEAR_MONEY" not in _codes(res)
    assert "ALL_PRICES_ZERO" not in _codes(res)
    assert items[0]["LastRate_Call"] == "120"          # untouched
    assert items[0]["LastRate_Put"] == "110"
