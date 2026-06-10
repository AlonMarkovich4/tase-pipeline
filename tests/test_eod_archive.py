"""
EOD archival lock — _archive_eod_snapshot must be idempotent and restart-safe.

Past bug: the EOD option-chain archive fired only on the single last in-market
cycle AND only if that cycle succeeded (`ok and last_cycle`), so a missed/failed
cycle (Fri 05-29) or a run of rejected cycles (casing bug, 06-01..06-08) lost
the day forever. Fix: a persistent pipeline_state marker drives an idempotent
archive callable from either the last in-market cycle or the off-hours block.

conftest stubs supabase_client + telegram_bot, so main imports cleanly here.
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import main  # noqa: E402


class FakeDB:
    def __init__(self, copy_result=True):
        self.markers = set()
        self.copies = 0
        self.copy_result = copy_result

    def state_is_set(self, k):
        return k in self.markers

    def state_set(self, k):
        self.markers.add(k)

    def copy_to_history(self):
        self.copies += 1
        return self.copy_result


# ── 1. Archives once, then is idempotent (no duplicate copy / re-fire) ───────
def test_archives_once_then_idempotent(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(main, "db", fake)
    main._archive_eod_snapshot("2026-06-10")
    assert fake.copies == 1
    assert "history_copied:2026-06-10" in fake.markers
    # called again (e.g. last-cycle then off-hours, or a restart) -> no re-copy
    main._archive_eod_snapshot("2026-06-10")
    assert fake.copies == 1


# ── 2. Failed copy does NOT set the marker -> it retries next chance ─────────
def test_failed_copy_leaves_unmarked_for_retry(monkeypatch):
    fake = FakeDB(copy_result=False)
    monkeypatch.setattr(main, "db", fake)
    main._archive_eod_snapshot("2026-06-10")
    assert fake.copies == 1
    assert "history_copied:2026-06-10" not in fake.markers   # will retry
    # next chance (e.g. off-hours): now it succeeds -> marked
    fake.copy_result = True
    main._archive_eod_snapshot("2026-06-10")
    assert fake.copies == 2
    assert "history_copied:2026-06-10" in fake.markers


# ── 3. Exception in copy is swallowed (worker never crashes on archive) ──────
def test_exception_swallowed(monkeypatch):
    fake = FakeDB()

    def boom():
        raise RuntimeError("network down")

    fake.copy_to_history = boom
    monkeypatch.setattr(main, "db", fake)
    main._archive_eod_snapshot("2026-06-10")          # must not raise
    assert "history_copied:2026-06-10" not in fake.markers


# ── 4. Distinct days get distinct markers (one archive per trading day) ──────
def test_per_day_markers(monkeypatch):
    fake = FakeDB()
    monkeypatch.setattr(main, "db", fake)
    main._archive_eod_snapshot("2026-06-10")
    main._archive_eod_snapshot("2026-06-11")
    assert fake.copies == 2
    assert fake.markers == {"history_copied:2026-06-10", "history_copied:2026-06-11"}


# ── 5. Structural: both call sites + the off-hours after-close guard exist ───
def test_wired_at_both_sites():
    src = open(os.path.join(os.path.dirname(os.path.dirname(__file__)), "main.py"),
               encoding="utf-8").read()
    # off-hours catch-up guarded by trading-day + after-close
    assert "now.weekday() in TRADING_DAYS and now.time() > MARKET_CLOSE" in src
    # the fragile in-memory tracker is gone
    assert "history_copied_date" not in src
    # helper invoked (at least the two intended sites)
    assert src.count("_archive_eod_snapshot(") >= 3   # 1 def-call in off-hours, 1 in-market, +definition usage
