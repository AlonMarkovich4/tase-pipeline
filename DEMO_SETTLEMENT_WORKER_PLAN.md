# DEMO_SETTLEMENT_WORKER_PLAN — move demo settlement from web → worker

> **Spec / build plan only. Nothing built, nothing deployed.** Read-only diagnosis written
> 2026-06-28. Sensitive: touches the live worker pipeline (`main.py` / `strategy_engine.py`).
> See **NEXT_WEEK_PLAN.md §3.A** for the surrounding decision and **§2d** for deploy rules.

## Decision (the "why")
Demo settlement currently runs in **web** (`web/src/app/demo/actions.ts`, `425a893`; all-pages sweep
`88140d8`). The long-term home is the **worker**: settle demo trades **automatically, alongside the
real `settle_expiry`**, so settlement runs with **zero dependence on anyone opening a dashboard** (the
web sweep still only fires on a page load). **No Telegram for demo** — explicit decision not to mix the
demo book with the real pipeline's alerts; demo settlements are reviewed in the dashboard (open to
revisit).

**Key insight:** moving to the worker **inherently fixes the demo-balance lost-update race** — the
worker loop is the **single, serialized settler**, so the read-latest→add→insert that races under
Streamlit/web concurrency cannot race here (provided the worker is the *only* writer — see §e).

## Current state (evidence)
- **`settle_expiry`** — `strategy_engine.py:852-1035`. Called **once/day** from `main.py:539`, gated by
  `ok and now>=SETTLEMENT_AFTER(10:00) and settled_today!=today`, behind the `settlement_done:<date>`
  marker + `has_unsettled_strategies`. Price priority: TASE-open → Yahoo (`_fetch_settlement_price`)
  → live underlying; `≤0` → abort. Reads `result_status=is.null`; computes **iron-condor zone** P&L
  (points × `TASE_MULTIPLIER`); PATCHes per `id` (`return=minimal`); re-reads + `alert_settlement`.
  The single `index_close` is written to every strategy's `actual_index_close`.
- **web base (`425a893`)** — sweeps `demo_trades?status=eq.open&expiry_date=lt.today`; per trade reads
  `iron_condor_strategies.actual_index_close` for that expiry; **per-leg** P&L; **conditional PATCH**
  `trade_id=eq.X&status=eq.open` (`return=representation`, checks rows); credits balance only if a row
  flipped; HTTP failures surfaced.
- **Schema** — `supabase_setup.sql:227-264`. `demo_trades.trade_id TEXT UNIQUE`, `legs JSONB`,
  `status` (indexed); `demo_balance` is a ledger (`id, balance, change_amount, change_reason,
  updated_at`) with **no unique key on `change_reason`** (→ no on-conflict idempotent insert; an atomic
  RPC is the only multi-writer-safe option).

---

## Build plan

### a) Integration point
- **New standalone `settle_demo_trades()` in `strategy_engine.py`** (a sweep, no args — mirrors web's
  `settleDueDemoTrades`). **Not inside `settle_expiry`**: keep the real-money path untouched (lower
  risk), and `settle_expiry` only handles today's expiry whereas the demo sweep must also **catch up**
  (a demo trade whose expiry day the worker missed).
- **Settlement price = the real strategy's `actual_index_close`** for the trade's expiry (read like
  web) → demo and real settle at the **identical** price, no second price source. No reliable close →
  **leave the trade OPEN** (never guess).
- **Call site in `main.py`:** right **after** the real settlement block (after `:545`), **outside** the
  `settled_today`/`has_unsettled` gate so it also runs on non-expiry days. It is idempotent and cheap
  when nothing is due (one GET), so **call it every cycle after 10:00** — this is what delivers full
  visit-independence. (Alternative: a daily `demo_swept:<date>` marker for once-per-day.)
- **Rejected alternatives:** (A) inside `settle_expiry` using `index_close` — couples the money path,
  misses catch-up / non-expiry days. (B) pass `index_close` out of `settle_expiry` — changes its
  return and still misses catch-up.

### b) Atomicity + idempotency (Python) — do NOT copy the read-modify-insert bug
- **Per trade:** conditional `PATCH demo_trades?trade_id=eq.<id>&status=eq.open` with
  `Prefer: return=representation`; credit the balance **only if exactly one row was returned**. Mirrors
  web → a trade settles + credits **at most once**, even on re-runs or with a lingering web writer.
- **Balance:** in the worker, `read-latest → add → insert` is **race-free** because the worker loop is
  the **sole, serialized writer** (the Streamlit/web concurrency that caused the lost-update does not
  exist here). Process trades **sequentially** (await each settle→credit before the next).
- **This is the headline win:** single-writer worker = the balance race is gone *by construction*,
  **as long as the web sweep is removed** (see §e).
- **HTTP-failure handling:** surface a failed credit loudly (closed-without-credit window, same residual
  as web). **Optional future hardening:** a Postgres RPC `credit_demo_balance(delta)` for a truly
  atomic increment (needed only if multi-writer ever returns).

### c) P&L formula — per-leg (NOT the condor-zone math)
- `pnl_ils = Σ side · (intrinsic_₪ − entry_₪) · qty`, where
  `intrinsic_₪ = (call ? max(idx−strike,0) : max(strike−idx,0)) × 50`,
  `entry_₪` = web `entryPx` as-is / Streamlit `premium_pts × 50`, `side` = +1 buy / −1 sell.
- **Do NOT reuse `settle_expiry`'s zone P&L** — that is specific to 4-leg iron condors; demo legs are
  arbitrary (the simulator builds any position). The per-leg method equals web `payoffAt` /
  `settleDueDemoTrades` and dashboard `sandbox_trade_pnl` (`dashboard.py:994`) exactly.
- **`MULT` from the single source `config.TASE_MULTIPLIER`** (no new local constant). Normalize both
  leg shapes; a **malformed leg → skip the trade** (don't settle). Range-check `settlement_index`
  against `TA35_MIN/MAX`.

### d) No Telegram for demo (closed decision)
`settle_demo_trades` **writes to the DB only — no `telegram_bot` import/call.** Reviewed in the
dashboard. (Contrast: `settle_expiry` *does* call `alert_settlement`; demo deliberately does not.)

### e) Disposition of the web code (`425a893`, `88140d8`)
- After the worker version is verified in prod: **remove the web sweep trigger** — the root-layout
  `after` (`88140d8`) and the demo-page wiring — so there is a **single writer** (the worker),
  guaranteeing the balance-race fix from §b.
- The action file `demo/actions.ts` may be deleted, **or** kept *unwired* as a manual fallback. Two
  *wired* writers won't double-settle/double-credit (the PATCH guard), but they **reintroduce the
  balance race** — so don't keep it wired.
- **Recommendation:** keep web wired as a fallback only during the short verification window (both are
  PATCH-guarded → no double-count; balance race is low-probability for a personal demo), then remove
  the web trigger. **`dispatchToDemo` (opening demo trades) stays** — only *settlement* moves.

### f) Tests (pytest) + dry-run
- **Real pytest behavior tests** (mock `strategy_engine.httpx` + `_sc`, like the existing engine tests
  via `conftest`) — importable/testable, unlike the dashboard mirror tests:
  - P&L **parity** with web/dashboard (lock the formula); **leg-shape parity** (web vs Streamlit → same
    pnl).
  - **Idempotency:** PATCH returns 0 rows → no credit; re-run doesn't double-count.
  - **No price** → stays open, no credit. **Malformed leg** → skip + error. **Out-of-band index** →
    skip. **Balance** = base + pnl exactly once.
- **Dry-run harness:** in-memory stub of `demo_trades` / `demo_balance` / `iron_condor_strategies` +
  write-tripwire; run `settle_demo_trades()`; assert the PATCH/POST sequence, **zero Telegram, zero real
  writes** — mirroring the web scenarios already run (settle-once, idempotent re-run, stale-read guard,
  parity, skips).

### g) Risk + order of operations
- **Risk: Medium** — touches the live worker loop (`main.py`) and adds a DB writer; **not** touching
  `settle_expiry` keeps the money path safe. Deploy = worker restart.
- **Order:**
  1. Build `settle_demo_trades()` in `strategy_engine.py` (clean port of the web logic;
     `config.TASE_MULTIPLIER`) + full pytest suite + dry-run. **No `main.py` change yet → zero behavior
     change.**
  2. Wire one idempotent call in `main.py` after the settlement block, wrapped so a sweep failure can't
     break the cycle (it returns counts, never raises). Deploy the worker.
  3. **Verify in prod:** open a demo trade for an already-settled expiry → the next cycle settles it +
     credits balance, **zero Telegram**, visible in the dashboard.
  4. **Remove the web sweep trigger** (`88140d8` layout `after`; demo page) → single writer. Optionally
     delete `demo/actions.ts` (keep `dispatchToDemo`).
  5. *(Optional, future)* atomic-increment RPC for the balance if multi-writer ever returns.
- **Deploy gate:** not on the last trading day / not mid-dispatch (consistent with §2d worker rules).

**Where it must NOT live:** not in `tase_api`, not in `telegram_bot`, not in `dashboard.py` — the
function in `strategy_engine.py` + minimal wiring in `main.py`.
