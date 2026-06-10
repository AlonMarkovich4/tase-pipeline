"""
#8 lock — health observability. The /health state exposes the last time each
major action succeeded (cycle rows, strategy, settlement, EOD archive), so the
whole pipeline's health is visible at a glance, and main wires those updates.
"""
import os

import health_server

_REPO = os.path.dirname(os.path.dirname(__file__))


def test_new_signal_fields_present():
    snap = health_server.snapshot()
    for k in ("last_rows", "last_expiries", "last_strategy_at",
              "last_settlement_at", "last_archive_date"):
        assert k in snap


def test_update_roundtrip():
    health_server.update(last_archive_date="2026-06-10",
                         last_rows=452, last_expiries=5)
    snap = health_server.snapshot()
    assert snap["last_archive_date"] == "2026-06-10"
    assert snap["last_rows"] == 452
    assert snap["last_expiries"] == 5


def test_snapshot_is_a_copy():
    snap = health_server.snapshot()
    snap["status"] = "mutated"
    assert health_server.snapshot()["status"] != "mutated"   # internal state untouched


def test_main_wires_health_signals():
    src = open(os.path.join(_REPO, "main.py"), encoding="utf-8").read()
    assert "last_strategy_at=datetime.now(TZ_ISRAEL).isoformat()" in src
    assert "last_settlement_at=datetime.now(TZ_ISRAEL).isoformat()" in src
    assert "last_archive_date=today_iso" in src
    assert 'health_update["last_rows"]' in src
