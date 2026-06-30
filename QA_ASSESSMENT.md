# TASE Pipeline — QA Assessment (read-only)

> Generated 2026-06-23. Read-only assessment — **nothing was fixed.** Documentation only.
> Evidence gathered from a full-project pass (7 component deep-reads + the test suite).
> Tests at time of writing: **125 passed in 0.73s** (the sub-second runtime is itself a
> signal — every IO boundary is stubbed; no integration coverage).
>
> ⚠️ No fix in here is to be applied until tomorrow's (2026-06-23) settlement is verified
> on the already-deployed code (`4e966dc`), then one-at-a-time with approval. Do not touch
> the pipeline / DB / web to "fix" any of this without that gate. See NEXT_WEEK_PLAN.md.

---

## Project map

**What it is.** An automated pipeline that scrapes the Tel Aviv Stock Exchange (TASE) TA-35
index option chain, builds **Iron Condor** option strategies weekly, settles them daily, and
reports via Telegram and two dashboards. Money figures are index-points × `TASE_MULTIPLIER`
(50) × lots.

**Three subsystems, one Supabase database:**

1. **Worker** (Python, Dockerized, runs continuously on Render) — `main.py:219` is the loop:
   `browser.py` (Playwright Chromium) → `tase_api.py` (fetch + paginate raw JSON) →
   `option_schema.py` (pydantic validate/normalize) → `database.py` + `supabase_client.py`
   (PostgREST upsert) → `strategy_engine.py` (build/settle condors) → `telegram_bot.py`
   (alerts). `health_server.py` serves `/health`. Shared constants in `config.py`.
2. **Streamlit dashboard** (`dashboard.py`, ~139 KB) — reads Supabase; **uniquely owns
   demo-trade settlement and the demo balance** (`close_demo_trade`, `_update_demo_balance`,
   `get_portfolio_capital`).
3. **Next.js app** (`web/`, App Router, server-rendered) — a replacement-in-progress; reads
   Supabase via `web/src/lib/data.ts`; has one privileged write path
   `web/src/app/simulator/actions.ts` (`dispatchToDemo`).

**Data flow.** Playwright scrapes the chain every ~15 min during trading hours → validated
rows upserted into the live snapshot table `tase_putcall` (keyed
`fetch_date,fetch_time,expiry_date,derivativeid_call,derivativeid_put`) → previous snapshot
cleared only when *all* expiries succeed. Weekly (Monday ~12:00) `run_strategy` builds condors
into `iron_condor_strategies`; daily `settle_expiry` writes results. SQL Views
`best_condor_per_expiry` / `condor_weekly_potential` aggregate "best per expiry"; the bot and
dashboards read those Views. Demo paper-trades live in `demo_trades` / `demo_balance`.

**Scheduling (config.py).** Trading days Mon–Fri (`TRADING_DAYS={0..4}`), 09:30–17:30
Asia/Jerusalem. Heartbeat + strategy on the *first* trading day; settlement after 10:00; daily
summary on the last cycle; weekly summary ~1 h after Friday close. Dedup via `pipeline_state`
key/value flags.

**Secrets/env.** `.env` (gitignored, present) and `web/.env.local` (gitignored, present, holds
a Supabase service-role JWT — **not committed**, verified). Env vars: `SUPABASE_URL/KEY/TABLE/
HISTORY_TABLE`, `TELEGRAM_BOT_TOKEN/CHAT_ID`, `HEADLESS`, `PORT`, `FETCH_INTERVAL_MINUTES`.

---

## Dimension-by-dimension assessment

### Correctness & logic — **Needs work**

- **Settlement accepts an unrange-checked external price.** `_fetch_settlement_price`
  (`strategy_engine.py:160`) takes Yahoo `regularMarketOpen` with only a `>0` check;
  `settle_expiry` then only guards `index_close <= 0` (`strategy_engine.py:877`), skipping the
  `TA35_MIN/MAX` sanity used elsewhere (`:778`). A junk open (e.g. 5 or 50000) settles *every*
  strategy that week at a garbage price → all marked max-loss. **Broken-class blast radius.**
- **`price_capped` condors are stored as risk-free yet stay `is_valid=true`.** When premium is
  forced to the wing max (`strategy_engine.py:536`), breakevens collapse onto the long strikes
  (`:589-590`) and `max_risk_ils` becomes 0 — a stale/theoretical-priced condor presents as
  zero-risk. Not excluded downstream.
- **Negative-premium rows carry nonsensical money fields.** For `raw_net_premium < 0`,
  `max_profit_ils` goes negative and `max_risk_ils` exceeds wing notional
  (`strategy_engine.py:583-584`). Correctly flagged `is_valid=false`, so safe *only if every
  consumer filters on `is_valid`* (they don't all — see project-wide).
- **`is_last_cycle` is fragile to clock drift** (`tase_api.py:340`, called `main.py:485`).
  Cycles aren't on a fixed grid (sleep *after* variable work); if no cycle's `now+15min`
  straddles 17:30, the "last cycle" never fires — silently dropping daily summary, weekly
  backup, weekly-summary *scheduling*, and EOD archive for the day. *(Found independently by
  the main.py and tase_api reviewers.)*
- **changePct semantics silently shift** in the web home page: `getIndexData` computes
  `(live − previous-expiry-close)/previous-expiry-close` (`data.ts:59-62`) but renders it as a
  generic "▲ X%". When live data is absent it becomes expiry-over-expiry — a different meaning,
  same badge.
- **OK:** condor PnL sign/unit math is correct and consistent across engine
  (`strategy_engine.py:521-546`), dashboard (`dashboard.py:994-1007`), and simulator
  (`Simulator.tsx:65-73`); premium summed in Decimal then rounded once (no round-then-sum);
  ISO-week anchoring in `get_weekly_stats` (`:1064-1067`) is correct.

### Edge cases & boundaries — **Needs work**

- **Empty input treated as success → can wipe good data.** `upsert_items` with `items==[]`
  returns `True` (`database.py:155`); the caller counts it a success (`tase_api.py:304`), which
  can satisfy the all-expiries-succeeded gate and trigger `_clear_old_snapshots` (`:316`),
  deleting the prior snapshot while nothing was written. **Broken-class data-loss path.**
- **Full-table read with no snapshot dedup.** `_read_live_data` pages the entire `tase_putcall`
  table with no `fetch_date` filter (`strategy_engine.py:94-97`); curve/closest-strike
  selection then picks by strike distance, not recency (`:392`, `:365`), so a stale historical
  row can win. Likely root cause the price-curve workarounds paper over.
- **Win/loss don't sum to "settled" on a zero-PnL settlement** (web `data.ts:125-126,320-321`;
  dashboard win-rate strict `>` at `dashboard.py:1514`).
- **`get_demo_balance` falls back to 100 000 on a malformed row** (`dashboard.py:669-671`, bare
  except) — a transient bad row silently jumps the balance to the seed value, off which
  subsequent deltas compute.
- **OK:** most empty-result paths in dashboard/web return empty containers and are guarded;
  `Math.min/max` spreads are guarded by non-empty fallback series.

### Error handling & failure modes — **Needs work**

- **State markers fail *open*.** `state_is_set` returns `False` on any DB error
  (`database.py:384`); callers read that as "not done yet" and re-run — `main.py:458`
  re-settles, `:513` re-sends daily summary, `:278` re-sends weekly summary, `tase_api.py:282`
  re-sends the data-quality alert. A transient Supabase blip → **duplicate settlements /
  duplicate Telegram alerts.** *(Found by both main.py and persistence reviewers.)*
- **Side-effect-then-marker with the marker write ignored.** Every dedup does the action, then
  `db.state_set(...)` whose return is discarded (`main.py:413,472,524,298`). If the action
  succeeds but the marker write fails, a restart re-does it.
- **`_update_demo_balance` has no try/except and ignores the HTTP response**
  (`dashboard.py:676-685`). With `close_demo_trade` already PATCHed to closed (`:716`), a
  failed balance POST leaves the trade settled but the balance never credited — permanent
  silent divergence. `save_demo_trade`/`close_demo_trade` likewise wrap no exception handling.
- **Bare excepts that conflate "no data" with "failure".** `has_unsettled_strategies` /
  `_strategies_exist_for_week` `except: return False` (`strategy_engine.py:674,692`) — a DB
  error can cause settlement to be *skipped*. Stacked `except: pass` around browser
  close/cookies (`browser.py:96-111`) can leak Chromium processes on the 6 h-restart worker
  with zero logging.
- **All web Supabase failures collapse to `[]`** (`data.ts:16-20`) — a 401/500/outage is
  indistinguishable from "no data"; the page renders the `100000`/`4292.94` fallbacks as a
  healthy dashboard.
- **OK:** `telegram_bot.py` retry/backoff is correct (5xx/429 retried, 4xx≠429 permanent,
  backoff guarded). All `httpx` calls have explicit timeouts (verified every site in
  `database.py`, `dashboard.py`, `strategy_engine.py`, `main.py`).

### Input & data validation — **Needs work / one Broken**

- **`dispatchToDemo` is an unauthenticated, unvalidated, service-role write**
  (`web/src/app/simulator/actions.ts:20-43`). Only checks env present and `legs.length>0`;
  everything else (`expiryDate`, `qty`, premiums, leg shapes) is taken from the client and
  written with the bypass-RLS key — no auth, no rate limit, no shape check. Pollutes the same
  `demo_trades` that drives calendar P&L and demo KPIs. **Broken (security + integrity).**
- **External JSON cast without shape checks.** `data.ts:17` `as T[]`; a 200-with-error-object
  makes `.map/.filter` throw an unhandled rejection. Engine/DB read raw lowercase keys while
  the pydantic model normalizes to CamelCase and is then *discarded* (`option_schema.py:552-553`)
  — validation and storage share no key path.
- **Underlying-value extraction is dead against the live feed.** `tase_api.py:184-192` scans
  top-level keys that don't exist (the value is per-item `UnderlingAsset_*`, always null in
  `diag_raw_response.json`), so it always silently falls back to Yahoo.
- **Put-delta convention unverified.** `option_schema.py:243` asserts puts ∈ [−100,0], but the
  engine uses positive deltas (`strategy_engine.py:212`) and the only captured sample shows
  `Delta_put: 0`. A real ITM put with positive delta would reject the whole row.
- **OK:** option price range-checks (`PRICE_SANITY_MAX_PTS`) are applied in both matcher and
  curve; `set_portfolio_capital` validates and the UI clamps.

### State & concurrency — **Needs work / Broken (demo)**

- **Demo settlement has no DB-level idempotency or atomicity** (`dashboard.py`).
  `close_demo_trade` PATCHes by `trade_id` with no `status=eq.open` guard (`:716-732`); the only
  re-settlement guard is the *in-memory, per-session* `settled_ids` set (`:1319`). Balance is
  read-modify-insert (`get_demo_balance()` → `_bal += pnl` → insert, `:1870-1899`) with no
  compare-and-swap. Two tabs, or a worker race, or a fresh session within the 30 s
  `@st.cache_data` window (`:701`) → **double-count or lost-update on real balance.** **Broken.**
- **Weekly-summary schedule is in-memory only.** `weekly_summary_due_at` is set in-hours
  (`main.py:496`) and consumed off-hours (`:273-303`); there is a "sent" marker but **no
  durable "scheduled" marker and no catch-up.** A Render restart between ~17:30 and ~18:30 drops
  the weekly summary silently with no recovery. **The single most concrete silent-failure in
  the worker.**
- **Cross-process read consistency:** dashboards/bot can read `tase_putcall` mid-cycle (after
  partial upsert, before `_clear_old_snapshots`) — no "snapshot complete" flag.
- **Lower-confidence:** `current_week` is only re-derived inside the in-hours branch
  (`main.py:357`) while off-hours readers use it (`:275-293`); exposure is narrow because the
  off-hours block is gated on the in-memory `weekly_summary_due_at`, but it couples correctness
  to "the in-hours branch ran this session."
- **OK:** `health_server` state is lock-guarded; DB writes are idempotent upserts;
  `pipeline_state` markers survive restarts (the gap is *fail-open*, above).

### Tests — **Needs work** (passes, but coverage is shallow and partly self-referential)

- **125 passed in 0.73s** — sub-second because every IO boundary is stubbed:
  `conftest.py:15-24` stubs `supabase_client`/`telegram_bot`; `database.py`, `browser.py`,
  `telegram_bot.py` have **zero** tests; `dashboard.py` and `web/` are tested only by
  source-substring grep / hand-copied mirrors.
- **Mirror tests that cannot catch a real regression** (highest concern):
  - `test_condor_edge_cases.py:160-184` re-implements settlement as a local `_settle_one` and
    asserts against *that*; the real `partial_loss_put/call` branches
    (`strategy_engine.py:949-954`) are never executed.
  - `test_failure_taxonomy.py:16-39` re-implements the main-loop recovery decision as `_decide`
    and tests the copy.
  - `test_demo_settlement_h1.py` / `test_history_settlement_m1.py` mirror dashboard logic; the
    real `dashboard.py` is only grep-checked.
  - `test_condor_edge_cases.py:135-150` **pins a known money bug** (`pnl_pts > 0` for a "max
    loss") against the duplicate — fixing the real code wouldn't even flip it.
- **Structural grep tests** (`test_eod_archive.py:87-95`, `test_config_constants.py`,
  `test_health_server.py:35-40`) assert source substrings — change-detectors, not behavior.
- **Hypothesis properties** `assume()` away the capped/zero-premium regimes where the bugs live
  (`test_properties.py:71`); only `test_prop_never_debit` is genuinely load-bearing.
- **Highest-risk untested paths:** the entire `main()` scheduling/dedup loop; `settle_expiry`
  partial-loss + price-priority; `get_weekly_stats`; all live boundaries
  (DB/Telegram/Playwright); demo settlement; all of `web/`.
- **Stale doc:** `pytest.ini` documents a root `test_strategy_engine.py` that no longer exists.

### Config & environment — **Needs work**

- **Three different capital constants** for what is conceptually one number:
  `DEMO_INITIAL_BALANCE = 100_000` (`dashboard.py:54`), `?? 100000` (`data.ts:117`), and the
  planned `PORTFOLIO_CAPITAL = 20_000`. Used as % denominators that don't reconcile to the book
  baseline (`dashboard.py:1827,2374`).
- **Duplicated Supabase header construction** in three places (`supabase_client.py:28`,
  `main.py:133`, `dashboard.py:314`); `MULTIPLIER=50` re-hardcoded in `dashboard.py:48` despite
  `config.TASE_MULTIPLIER`.
- **Hardcoded "healthy-looking" fallbacks** mask outages in web (`4292.94`, `FALLBACK_SERIES`,
  `[1000,10000]` band, `?? 100000`).
- **No holiday/short-session calendar** — the worker churns empty 15-min cycles on TASE
  holidays and assumes a full Friday session (`config.py:21`, `main.py:76`).
- **OK:** `config.py` is a real single source for most constants; `Dockerfile` copies `*.py`
  (resilient); env vars are consistent.

### Security basics — **Needs work** (one real exposure)

- **Service-role write reachable by any visitor** — `dispatchToDemo` (above). The real headline
  security item.
- **Unencoded interpolation into PostgREST filters** in several state-mutating calls —
  `database.py:85,378`, `dashboard.py:720,1879`, `data.ts:197`. Not exploitable *today* (values
  are constants/DB-sourced), but it's unparameterized query construction on mutating calls —
  defense-in-depth gap.
- **Using the service-role (bypass-RLS) key for a read-mostly public dashboard** is heavier than
  needed; an anon key + RLS would cap blast radius.
- **OK / verified:** no secrets committed (`.env`, `web/.env.local` both gitignored and
  untracked); no client key leak (`service_role` not found in `.next/static`); Telegram token
  scrubbed from exception logs (`telegram_bot.py:77`); health server exposes no secrets.

### Dead / duplicated code & inconsistencies — **Needs work**

- **"Settled" is defined ~four ways:** Python `result_status IS NOT NULL`
  (`strategy_engine.py:685,894,1071`); web `getKpis` requires
  `result_status && actual_index_close>0` (`data.ts:121`); web `getStrategiesData`/table use
  `actual_pnl_ils != null` (`data.ts:319`, `StrategiesTable.tsx:81`); dashboard overloads
  `_is_settled` vs `_is_actually_settled` (`dashboard.py:1440-1450`). Home, strategies page, and
  bot can each report a different settled count and win-rate from the same rows.
- **Condor economics diverge:** simulator adds ₪2.5/contract commission and samples the payoff
  curve (`Simulator.tsx:137-147`) vs the engine's analytic, commission-free max-profit/risk
  (`strategy_engine.py:583-584`) — trades dispatched from the simulator carry numbers the engine
  would never produce.
- **Dead code:** underlying-value scan (`tase_api.py:184-192`); CamelCase ceiling-null branch
  never matches the lowercase feed (`option_schema.py:382`); `actual_wing_*` is always exactly
  `WING`, making settlement's asymmetric-wing branches (`strategy_engine.py:931-960`) unreachable
  with engine data.

---

## Project-wide systemic issues (and the root-cause fixes)

Five recurring root causes generate most of the individual findings:

1. **Dedup/idempotency lives in volatile memory, and DB markers fail open.** Symptoms: dropped
   weekly summary on restart (`main.py:496`), duplicate alerts/settlements on a DB blip
   (`database.py:384`), demo double-count/lost-update (`dashboard.py:1870-1899`). **Root fix:**
   make every side-effect idempotent at the DB — conditional writes (`status=eq.open`,
   rows-affected checks), a durable "scheduled"/"complete" flag for the weekly summary, and make
   `state_is_set` failures *fail closed*. Resolves findings across `main.py`, `database.py`,
   `dashboard.py`.
2. **No canonical "settled" / "valid" / "capital" definition.** Each consumer recomputes its
   own, so the same DB yields different numbers in three UIs and the bot, and
   `is_valid`/`price_capped`/negative-premium rows leak into some aggregates. **Root fix:** one
   SQL View (or shared module) for "settled strategies" + "valid condor" + the capital
   denominator; point bot, dashboard, web at it.
3. **Failures are silent and disguised as health.** Bare excepts returning `[]`/`False`/`0`,
   hardcoded plausible fallbacks, ignored HTTP responses → outages render as a normal dashboard
   and bad data flows downstream. **Root fix:** log every swallowed exception, surface a
   DB-error/staleness state in both UIs, distinguish "empty" from "failed" (notably
   `upsert_items([]) → True`).
4. **The worker reads unbounded history as if it were a single snapshot.** Full-table
   pagination + recency-blind strike selection is the engine's deepest correctness risk. **Root
   fix:** filter `_read_live_data` to the latest `(fetch_date,fetch_time)` and select by
   recency.
5. **Tests assert against copies of the code, not the code.** Green suite, but the riskiest
   paths are untested or mirror-tested. **Root fix:** delete the `_settle_one`/`_decide`/
   `_resolve_*` mirrors, call the real functions with injected fakes for IO, add behavioral
   tests for the main-loop gates and `settle_expiry` partial-loss branches.

---

## Prioritized action plan (by risk × likelihood, phased for one-at-a-time approval)

> **None of this should touch the live pipeline before tomorrow's settlement is verified on the
> deployed code** (`4e966dc`). Phase 0 worker items stage behind that gate; the web/dashboard
> items are independent of the settlement path.

### Phase 0 — Money & data integrity (do first)
1. **Demo settlement: make idempotent + atomic.** *What:* PATCH with `&status=eq.open`, check
   rows-affected before crediting; replace read-modify-insert balance with a server-side
   increment RPC; wrap `_update_demo_balance` in try/except and check the response. *Why:* real
   balance double-count / lost-update / settled-but-uncredited. *Verify:* two tabs settle the
   same expired trade; bad-DB insert leaves balance unchanged. *Effort:* M. *Where:*
   `dashboard.py:676-732,1865-1904`.
2. **`dispatchToDemo`: authenticate + validate + drop service-role.** *What:* require an auth
   token, validate every field/leg shape, rate-limit, use an anon key + RLS for writes. *Why:*
   any visitor can write arbitrary rows with the bypass-RLS key. *Verify:* POST a malformed
   payload — it currently inserts. *Effort:* M. *Where:* `web/src/app/simulator/actions.ts:20-43`.
3. **`upsert_items([])` must not report success.** *What:* return `False`/skip on empty rows so
   the cleanup gate can't wipe the prior snapshot. *Why:* silent data-loss of a good snapshot.
   *Verify:* call with `items=[]`, trace `_clear_old_snapshots`. *Effort:* S. *Where:*
   `database.py:155`, gate at `tase_api.py:304,316`.
4. **Range-check the settlement price.** *What:* apply `TA35_MIN/MAX` to the Yahoo open in
   `settle_expiry`, not just `>0`. *Why:* one junk quote settles a whole week as max-loss.
   *Verify:* mock `regularMarketOpen: 5`. *Effort:* S. *Where:*
   `strategy_engine.py:160-175,876-877`.

### Phase 1 — Silent worker failures
5. **Durable weekly-summary scheduling + catch-up.** *What:* persist the "due" state (or
   recompute on any off-hours start) and add an off-hours catch-up like EOD archive has. *Why:*
   a restart between 17:30–18:30 drops the summary with no recovery. *Verify:* set due, restart
   before fire, confirm no summary. *Effort:* M. *Where:* `main.py:237,273-303,496`.
6. **Make `state_is_set` fail closed; check `state_set` return.** *What:* on DB error, don't
   treat as "not done"; verify marker writes after side-effects. *Why:* duplicate
   settlements/alerts on transient blips. *Verify:* kill DB between send and marker, restart.
   *Effort:* M. *Where:* `database.py:384,405`; callers `main.py:413,458,472,513,278`.
7. **Harden `is_last_cycle` against drift.** *What:* trigger last-cycle actions on the first
   cycle at/after a cutoff (not an exact straddle), or move them to the off-hours catch-up.
   *Why:* drift silently drops daily summary, backup, weekly scheduling, EOD. *Verify:* simulate
   drifting timestamps near close. *Effort:* S–M. *Where:* `tase_api.py:340`,
   `main.py:485,500-531`.

### Phase 2 — Data correctness & consistency
8. **Filter `_read_live_data` to the latest snapshot; select strikes by recency.** *Why:*
   unbounded-history reads feed stale prices. *Verify:* confirm `tase_putcall` accumulates rows;
   check curve picks. *Effort:* M. *Where:* `strategy_engine.py:94-97,365,392`.
9. **One canonical "settled"/"valid"/"capital" source.** *What:* a settled-strategies View + a
   single capital constant; repoint bot, dashboard, web. *Why:* divergent KPIs/win-rates; the
   planned `PORTFOLIO_CAPITAL` work folds in here. *Verify:* same numbers on `/`, `/strategies`,
   and the bot. *Effort:* M–L. *Where:* `data.ts:121,319`, `dashboard.py:1440-1450`,
   `strategy_engine.py:685,1128`.
10. **Exclude/repair `price_capped` (risk=0) condors; never let negative-premium money fields
    leak.** *Why:* stale-priced condors present as risk-free; aggregates that don't filter
    `is_valid` get corrupt `max_risk`. *Verify:* construct legs with premium ≥ wing. *Effort:*
    S–M. *Where:* `strategy_engine.py:536,583-590`.

### Phase 3 — Validation & parse robustness
11. **Fix/confirm the underlying-value source and put-delta convention; make the pydantic model
    and storage share a key path.** *Effort:* M. *Where:* `tase_api.py:184-192`,
    `option_schema.py:243,552-553`.
12. **Log swallowed exceptions; surface DB-error/staleness in both UIs; remove "healthy"
    hardcoded fallbacks (or badge them stale).** *Effort:* M. *Where:* `browser.py:96-111`,
    `data.ts:16-20,57,59,117`, `dashboard.py` read helpers.
13. **Add timeouts/abort + fix the N+1 query pattern in the web SSR path.** *Effort:* S–M.
    *Where:* `data.ts:12,195-216`, `actions.ts:24`.

### Phase 4 — Tests (do alongside whatever you change above, not last)
14. **Replace mirror tests with real-code tests.** Delete `_settle_one`/`_decide`/`_resolve_*`;
    call the production functions with injected fakes. Add behavioral coverage for: the `main()`
    first/last-day + restart-dedup gates, `settle_expiry` partial-loss branches and price
    priority, and `get_weekly_stats` week math. Retire the bug-pinning test once the underlying
    money bug is fixed. *Effort:* L. *Where:* `tests/test_condor_edge_cases.py:135-184`,
    `test_failure_taxonomy.py:16-39`, `test_demo_settlement_h1.py`,
    `test_history_settlement_m1.py`.

---

**Headline:** the worker's *correctness-on-the-happy-path* is reasonably solid and well
unit-tested, but **money/state integrity under failure and concurrency is the weak spine** —
demo settlement (no idempotency), the unauthenticated service-role write, empty-upsert
data-loss, fail-open dedup, and the in-memory weekly schedule are the items most likely to cause
a real, silent, user-visible failure. The four-way "settled" definition and the unbounded-history
read are the systemic correctness risks underneath the dashboards.

*This file is local and not pushed. Read-only assessment — no code was changed.*
