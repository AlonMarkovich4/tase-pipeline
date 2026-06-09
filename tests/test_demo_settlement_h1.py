"""
H1 lock — demo auto-settlement must NOT fall back to the entry index.

Bug: an expired demo trade with no real settlement price and no live index was
auto-closed at the ENTRY index. For a centered iron condor that books a fake
MAX-PROFIT win, irreversibly, on mere page visit. Fix: priority is
strategy actual_index_close -> live index -> DO NOT settle (leave open, don't
touch balance).

dashboard.py can't be imported (it runs Streamlit at import), so this test
combines (a) structural assertions against the real source and (b) a simulation
of the exact settlement-price logic.
"""
import os
import re

_DASH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard.py")


def _settlement_block() -> str:
    """The auto-settlement region of dashboard.py (text)."""
    src = open(_DASH, encoding="utf-8").read()
    start = src.index("Background: Auto-Settlement")
    end = src.index("_settlement_dialog(_results, _bal)")
    return src[start:end]


# ── (a) Structural: the entry-index fallback is gone, the don't-settle guard is in
def test_no_entry_index_fallback_in_settlement():
    block = _settlement_block()
    assert "et_entry" not in block, "entry-index fallback must be removed"
    # live-index fallback kept, then a hard 'leave open' guard
    assert "settle_idx <= 0 and live_index > 0" in block
    assert re.search(r"if settle_idx <= 0:\s*\n\s*continue", block), \
        "must `continue` (leave trade open) when no reliable price"


def test_balance_touch_only_after_guard():
    """close_demo_trade / balance update must come AFTER the `continue` guard."""
    block = _settlement_block()
    guard = block.index("continue")
    assert block.index("close_demo_trade") > guard
    assert block.index("_update_demo_balance") > guard


# ── (b) Logic simulation mirroring the patched priority chain ────────────────
def _resolve_settle_index(strategy_close, live_index):
    """Exact mirror of the patched logic. Returns price, or None = don't settle."""
    settle_idx = 0.0
    if strategy_close and strategy_close > 0:
        settle_idx = float(strategy_close)
    if settle_idx <= 0 and live_index > 0:
        settle_idx = live_index
    if settle_idx <= 0:
        return None
    return settle_idx


def test_case1_real_strategy_close():
    assert _resolve_settle_index(4300.0, 0.0) == 4300.0


def test_case2_live_index_when_no_strategy():
    assert _resolve_settle_index(0.0, 4250.0) == 4250.0


def test_case3_neither_leaves_open():
    # No reliable price -> None -> the loop `continue`s -> trade stays open,
    # balance untouched. (This is the bug case.)
    assert _resolve_settle_index(0.0, 0.0) is None


def test_case4_entry_index_never_used():
    """Even with an entry index available, the resolver ignores it (no param)."""
    entry = 4258.0
    # The fake-max-profit the OLD code would have booked, for the record:
    MULT = 50
    legs = [("Put", "SELL", 4190, 9), ("Put", "BUY", 4170, 4),
            ("Call", "SELL", 4300, 8), ("Call", "BUY", 4320, 3)]
    old_pnl = 0.0
    for typ, act, k, prem in legs:
        sign = 1 if act == "BUY" else -1
        intr = max(entry - k, 0) if typ == "Call" else max(k - entry, 0)
        old_pnl += sign * (intr - prem) * MULT
    assert old_pnl == 500.0                       # the fake MAX-PROFIT win
    assert _resolve_settle_index(0.0, 0.0) is None  # new code refuses to book it
