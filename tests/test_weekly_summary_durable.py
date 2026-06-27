"""
Bug 1 — durable, restart-safe weekly-summary scheduling.

The post-close weekly summary used to live in an in-memory `due_at` that a
restart between Friday's close and the firing time would drop, so the summary
was never sent (zero `weekly_summary_sent` markers W23–W26 in production).

These tests lock the durable behaviour: the schedule is persisted in
pipeline_state, the off-hours catch-up fires from it (surviving a restart),
and it never sends twice (idempotent via the 'sent' marker).
"""
import datetime as _dt

import main

FRI = _dt.date(2026, 6, 12)            # verified Friday
WEEK = FRI.isocalendar()[1]
YEAR = FRI.isocalendar()[0]
SCHED_KEY = f"weekly_summary:scheduled:{YEAR}-W{WEEK:02d}"
SENT_KEY  = f"weekly_summary_sent:{YEAR}-W{WEEK:02d}"

CLOSE = _dt.datetime.combine(FRI, main.MARKET_CLOSE)   # 17:30
DUE   = CLOSE + _dt.timedelta(hours=1)                 # 18:30


class FakeDB:
    """In-memory stand-in for the pipeline_state markers."""
    def __init__(self, initial=None):
        self.store = dict(initial or {})

    def state_is_set(self, key):
        return key in self.store

    def state_get(self, key):
        return self.store.get(key)

    def state_set(self, key, value="1"):
        self.store[key] = value
        return True


class FakeEngine:
    def __init__(self, stats):
        self._stats = stats
        self.calls = 0

    def get_weekly_stats(self, week, year=0):
        self.calls += 1
        return self._stats


class FakeBot:
    def __init__(self):
        self.sent = []

    def alert_weekly_summary(self, stats):
        self.sent.append(stats)


def _wire(monkeypatch, db, engine, bot):
    monkeypatch.setattr(main, "db", db)
    monkeypatch.setattr(main, "strategy_engine", engine)
    monkeypatch.setattr(main, "telegram_bot", bot)


# ── Scenario (a): normal path — schedule, then fire when due ────────────────
def test_normal_schedule_then_fire(monkeypatch):
    db = FakeDB(); eng = FakeEngine({"trades": 5}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)

    # Schedule at last Friday cycle (~17:16) → persists durable marker.
    due = main._schedule_weekly_summary(_dt.datetime.combine(FRI, _dt.time(17, 16)), WEEK)
    assert due == DUE
    assert db.state_is_set(SCHED_KEY)
    assert db.state_get(SCHED_KEY) == DUE.isoformat()

    # Off-hours, before due → not fired yet.
    assert main._fire_weekly_summary_if_due(CLOSE + _dt.timedelta(minutes=5), WEEK) is False
    assert bot.sent == []
    assert not db.state_is_set(SENT_KEY)

    # Off-hours, after due → fires and persists 'sent'.
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(minutes=1), WEEK) is True
    assert len(bot.sent) == 1 and bot.sent[0] == {"trades": 5}
    assert db.state_is_set(SENT_KEY)


# ── Scenario (b): RESTART — schedule survived in DB, in-memory lost ─────────
def test_restart_catchup_fires_from_durable_marker(monkeypatch):
    # Simulate a fresh process after a restart: only the durable scheduled
    # marker exists (no in-memory due_at, no 'sent' marker).
    db = FakeDB({SCHED_KEY: DUE.isoformat()})
    eng = FakeEngine({"trades": 3}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)

    # Post-restart off-hours pass, past the firing time → catch-up sends.
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(minutes=30), WEEK) is True
    assert len(bot.sent) == 1
    assert db.state_is_set(SENT_KEY)


# ── Scenario (c): idempotency — already sent, never sends again ─────────────
def test_idempotent_does_not_resend(monkeypatch):
    db = FakeDB({SCHED_KEY: DUE.isoformat(), SENT_KEY: "1"})
    eng = FakeEngine({"trades": 9}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)

    # Returns handled, but performs NO send and does not even read stats.
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(hours=2), WEEK) is True
    assert bot.sent == []
    assert eng.calls == 0


# ── Guard: nothing scheduled → no-op (e.g. a non-last-day off-hours pass) ───
def test_no_schedule_no_fire(monkeypatch):
    db = FakeDB(); eng = FakeEngine({"trades": 5}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(minutes=1), WEEK) is False
    assert bot.sent == [] and eng.calls == 0


# ── No settled trades → marks sent (no infinite retry), sends nothing ──────
def test_no_trades_marks_sent_without_sending(monkeypatch):
    db = FakeDB({SCHED_KEY: DUE.isoformat()})
    eng = FakeEngine({"trades": 0}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(minutes=1), WEEK) is True
    assert bot.sent == []                 # nothing to report
    assert db.state_is_set(SENT_KEY)      # but marked sent → won't retry forever


# ── Scheduling is idempotent (does not overwrite an existing due-at) ────────
def test_schedule_is_idempotent(monkeypatch):
    db = FakeDB({SCHED_KEY: DUE.isoformat()})
    eng = FakeEngine({"trades": 1}); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)
    # Even if called again later in the session, returns the existing due-at.
    again = main._schedule_weekly_summary(_dt.datetime.combine(FRI, _dt.time(17, 31)), WEEK)
    assert again == DUE


# ── Send failure leaves schedule intact for retry (no marker, returns False) ─
def test_send_failure_retries_next_pass(monkeypatch):
    db = FakeDB({SCHED_KEY: DUE.isoformat()})

    class BoomEngine:
        calls = 0
        def get_weekly_stats(self, week, year=0):
            BoomEngine.calls += 1
            raise RuntimeError("transient")

    eng = BoomEngine(); bot = FakeBot()
    _wire(monkeypatch, db, eng, bot)

    # First pass throws → not handled, scheduled marker still present.
    assert main._fire_weekly_summary_if_due(DUE + _dt.timedelta(minutes=1), WEEK) is False
    assert not db.state_is_set(SENT_KEY)
    assert db.state_is_set(SCHED_KEY)
