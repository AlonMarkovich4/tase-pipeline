"""
M1 lock — History must distinguish "actually settled" from "expired but not
settled", and never show the latter as a ₪0 settled break-even.

dashboard.py can't be imported (runs Streamlit at import), so this combines
(a) structural assertions against the real source and (b) a simulation of the
"actually settled" classification used to split History.
"""
import os

_DASH = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dashboard.py")


def _src() -> str:
    return open(_DASH, encoding="utf-8").read()


# ── (a) Structural ───────────────────────────────────────────────────────────
def test_actually_settled_flag_defined():
    s = _src()
    assert '_is_actually_settled' in s
    assert 'df["actual_index_close"] > 0' in s  # real flag requires a settle price


def test_history_aggregates_use_settled_only():
    s = _src()
    assert 'hist_settled = all_history[all_history["_is_actually_settled"]]' in s
    # comparison is built from hist_settled, not all_history
    assert 'idf = hist_settled[hist_settled["interval_pct"] == pct]' in s


def test_detail_has_pending_branch_not_zero_settled():
    s = _src()
    assert '_row_settled' in s
    assert 'ממתין לסליקה' in s              # the pending state label is shown
    # the pending notice for the aggregate section
    assert 'פקעו וטרם סולקו' in s


# ── (b) Logic simulation: the "actually settled" classification ───────────────
def _is_actually_settled(result_status, actual_index_close) -> bool:
    has_result = bool(result_status) and str(result_status) != ""
    has_price = float(actual_index_close or 0) > 0
    return has_result and has_price


def test_real_settlement_is_settled():
    assert _is_actually_settled("max_profit", 4300.0) is True
    assert _is_actually_settled("max_loss_put", 4500.0) is True


def test_expired_unsettled_is_not_settled():
    # expired & forced into History but with no result / no price -> pending
    assert _is_actually_settled("", 0) is False
    assert _is_actually_settled(None, 0) is False
    # result present but no settlement price (engine wrote status, price missing)
    assert _is_actually_settled("max_profit", 0) is False


def test_pending_excluded_from_settled_subset():
    rows = [
        {"result_status": "max_profit",   "actual_index_close": 4300, "pnl": 150},
        {"result_status": "",             "actual_index_close": 0,    "pnl": 0},   # pending
        {"result_status": "max_loss_put", "actual_index_close": 4500, "pnl": -800},
    ]
    settled = [r for r in rows
               if _is_actually_settled(r["result_status"], r["actual_index_close"])]
    pending = [r for r in rows
               if not _is_actually_settled(r["result_status"], r["actual_index_close"])]
    assert len(settled) == 2 and len(pending) == 1
    # the ₪0 pending row does NOT dilute the settled aggregate
    assert sum(r["pnl"] for r in settled) == -650
