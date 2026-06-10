"""
#7 lock — failure taxonomy. A stale/empty feed (data condition) must NOT be
treated like a dead browser (transport failure): no pointless session recovery,
no false "consecutive failures" crash alert.

run_cycle now reports transport_ok (did we fetch the expiry list = is the
browser/WAF path alive) and had_critical. main recovers/escalates ONLY on a
transport failure.
"""
import os

_REPO = os.path.dirname(os.path.dirname(__file__))


# ── Simulation mirroring main.py's new decision branch ───────────────────────
def _decide(ok: bool, transport_ok: bool):
    """Returns (recover_browser, increment_crash_counter)."""
    if ok or transport_ok:
        return (False, False)          # healthy transport → never recover/escalate
    return (True, True)                # transport failure → recover + escalate


def test_success_no_recovery():
    assert _decide(ok=True, transport_ok=True) == (False, False)


def test_stale_data_is_not_a_transport_failure():
    # got the expiry list (transport_ok) but all expiries CRITICAL/stale → ok False
    assert _decide(ok=False, transport_ok=True) == (False, False)


def test_empty_no_trading_is_not_a_transport_failure():
    # list fetched, nothing stored, no critical (holiday/empty) → still benign
    assert _decide(ok=False, transport_ok=True) == (False, False)


def test_transport_failure_recovers_and_escalates():
    # couldn't even fetch the expiry list → real transport problem
    assert _decide(ok=False, transport_ok=False) == (True, True)


# ── Contract: run_cycle reports transport_ok in BOTH return paths ────────────
def test_run_cycle_reports_transport_ok():
    src = open(os.path.join(_REPO, "tase_api.py"), encoding="utf-8").read()
    # early return (no expiry list) is a transport failure
    assert '"transport_ok": False' in src
    # normal return reports transport_ok (True) + had_critical
    assert '"transport_ok": True' in src
    assert '"had_critical": had_critical' in src


# ── Structural: main branches on transport_ok, not a blanket `not ok` ────────
def test_main_branches_on_transport():
    src = open(os.path.join(_REPO, "main.py"), encoding="utf-8").read()
    assert 'transport_ok = cycle_result.get("transport_ok", ok)' in src
    assert "if ok or transport_ok:" in src
    assert "consecutive transport failures" in src      # alert wording updated
