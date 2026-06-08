"""
Characterization tests for option_schema.validate_items and OptionPair.
Locks current validation behaviour, including gaps flagged in ENGINE_AUDIT.md.
"""
import sys, os
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import option_schema as osch
from option_schema import OptionPair, validate_items, DQLevel


def _item(strike_c="2100", strike_p="2100", lr_c="1.5", lr_p="1.5",
          delta_c="30", delta_p="30", base_c=None, base_p=None):
    d = {
        "ExpirationPrice_Call": strike_c,
        "ExpirationPrice_Put":  strike_p,
        "LastRate_Call": lr_c, "LastRate_Put": lr_p,
        "Delta_Call": delta_c, "Delta_Put": delta_p,
    }
    if base_c is not None:
        d["BaseRate_Call"] = base_c
    if base_p is not None:
        d["BaseRate_Put"] = base_p
    return d


# ── Accepts a clean row ───────────────────────────────────────────────────
def test_clean_row_accepted():
    res = validate_items([_item()], "2026-06-04", "04/06/2026", "2026-06-06")
    assert res.accepted_count == 1
    assert res.rejected_count == 0


# ── Strike out of range rejected ──────────────────────────────────────────
def test_strike_out_of_range_rejected():
    res = validate_items([_item(strike_c="500")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


# ── Negative LastRate rejected ────────────────────────────────────────────
def test_negative_lastrate_rejected():
    res = validate_items([_item(lr_c="-5")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


# ── LastRate above ceiling: row SURVIVES, leg filtered (Bug #4 fix) ───────
def test_lastrate_above_ceiling_leg_filtered_not_rejected():
    """
    Was: an over-ceiling leg rejected the whole row. Now the row survives and
    only the offending leg is nulled (here: no spot in the fixture -> no-spot
    filter path). Single-strike batch can't trigger DUPLICATE_STRIKES (>5 gate),
    so we assert the row was NOT rejected and the inflated leg was nulled.
    """
    item = _item(lr_c="20000")
    res = validate_items([item], "2026-06-04", "04/06/2026", "2026-06-06")
    assert res.rejected_count == 0          # row no longer rejected
    assert item.get("LastRate_Call") is None  # inflated leg filtered


# ── Delta out of [0,100] rejected ─────────────────────────────────────────
def test_delta_out_of_range_rejected():
    res = validate_items([_item(delta_c="150")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


def test_negative_put_delta_rejected_BUG():
    """
    LOCKS M-3 (audit): a negative put delta (standard quant convention) is
    currently REJECTED. If TASE ever sends signed deltas, all puts drop.
    """
    res = validate_items([_item(delta_p="-30")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


# ── NaN LastRate is correctly REJECTED by the schema (H-2 correction) ─────
def test_nan_lastrate_rejected():
    """
    Verified: NaN LastRate is rejected because Decimal('NaN') < 0 raises
    InvalidOperation (caught → row rejected). The schema layer is safe for
    non-finite; the engine's _clean_numeric is the exposed path (H-2).
    """
    res = validate_items([_item(lr_c="nan")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


def test_inf_lastrate_rejected():
    """
    Infinity LastRate is still rejected — now by Pydantic's non-finite Decimal
    rule (not the ceiling, which is leg-level post-fix). Garbage stays out.
    """
    res = validate_items([_item(lr_c="inf")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.rejected_count == 1


# ── Negative BaseRate currently SLIPS THROUGH (H-3) ───────────────────────
def test_negative_baserate_accepted_BUG():
    """LOCKS H-3: BaseRate has no sign/range validation."""
    res = validate_items([_item(base_c="-5")], "2026-06-04",
                         "04/06/2026", "2026-06-06")
    assert res.accepted_count == 1   # BUG: negative baserate accepted


# ── Batch gate: all-zero as STRINGS is now CAUGHT (H-4 fixed) ─────────────
def test_zero_price_gate_catches_string_zero():
    """
    Was H-4 (string "0" prices slipped past the zero check via a truthiness
    bug). The casing fix routed the zero check through _parse_number, so the
    string "0" is now recognised as zero.
    OLD: no ALL_PRICES_ZERO emitted. NEW: ALL_PRICES_ZERO fires.
    """
    items = [_item(lr_c="0", lr_p="0", strike_c=str(s), strike_p=str(s))
             for s in range(2000, 2120, 20)]
    res = validate_items(items, "2026-06-04", "04/06/2026", "2026-06-06")
    assert any(w.code == "ALL_PRICES_ZERO" for w in res.warnings)


def test_zero_price_gate_fires_for_int_zero():
    """Control: with numeric 0 the gate DOES fire — proving the type sensitivity."""
    items = [{"ExpirationPrice_Call": s, "ExpirationPrice_Put": s,
              "LastRate_Call": 0, "LastRate_Put": 0,
              "Delta_Call": 30, "Delta_Put": 30}
             for s in range(2000, 2120, 20)]
    res = validate_items(items, "2026-06-04", "04/06/2026", "2026-06-06")
    assert res.has_critical
    assert any(w.code == "ALL_PRICES_ZERO" for w in res.warnings)


# ── Batch gate: duplicate strikes → CRITICAL ──────────────────────────────
def test_duplicate_strikes_critical():
    items = [_item(strike_c="2100", strike_p="2100", lr_c="1.0", lr_p="1.0")
             for _ in range(6)]
    res = validate_items(items, "2026-06-04", "04/06/2026", "2026-06-06")
    assert any(w.code == "DUPLICATE_STRIKES" for w in res.warnings)


# ── Trade-date staleness ──────────────────────────────────────────────────
def test_missing_trade_date_warns():
    w = osch.check_trade_date(None, "2026-06-04")
    assert w is not None and w.code == "MISSING_TRADE_DATE"
    assert w.level == DQLevel.WARNING


def test_unparseable_trade_date_warns():
    w = osch.check_trade_date("not-a-date", "2026-06-04")
    assert w is not None and w.code == "UNPARSEABLE_TRADE_DATE"


# ── Rejection ratio escalates to CRITICAL at >= 50% ───────────────────────
def test_majority_rejection_critical():
    items = [_item(),                       # valid
             _item(strike_c="500"),         # invalid
             _item(strike_c="600")]         # invalid → 2/3 rejected
    res = validate_items(items, "2026-06-04", "04/06/2026", "2026-06-06")
    assert any(w.code == "ITEMS_REJECTED" and w.level == DQLevel.CRITICAL
               for w in res.warnings)
