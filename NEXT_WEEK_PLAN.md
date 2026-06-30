# NEXT_WEEK_PLAN — execution plan for after Monday (2026‑06‑22)

> Centralizing everything that is **built locally but not yet pushed/deployed**, the
> exact steps to roll it out after Monday's strategy launch, the bigger non‑urgent
> projects, and the traps we found so they aren't forgotten.
>
> Generated 2026‑06‑20; updated 2026‑06‑27. The earlier work in §1 is now **on `origin/main`**
> (pushed; deploy‑state unknown). The current **ready‑to‑deploy** set is the **5 local commits in §2d**
> — built + tested, **not pushed, not deployed**.

---

## 1. Current state

### Local commits (historical — now pushed)
> **Update 2026‑06‑27:** the commits below are **already on `origin/main`** (its tip `4e966dc`
> includes them). Kept here for history. The **current ready‑to‑deploy set** (5 local commits not yet
> pushed) is in **§2d**.

These were the QA'd commits at the time of writing:

| hash | what |
|---|---|
| `7319adf` | **bot** — `get_weekly_stats` reads the `best_condor_per_expiry` View (single source shared with the dashboard) |
| `2e05b0c` | **dashboard condor** — "פוטנציאל פר פקיעה" pager on `/strategies` (₪/RR/max‑risk per expiry + historical paging), reads the View |
| `6815f65` | **web (accumulated, NOT re‑verified tonight)** — VTA35, light mode, interactive index chart, home option chain, simulator dropdowns, demo/strategies filters, Node `engines >=20.9` pin |
| `763680d` | **root fix** — pipeline auto‑marks `is_valid=false` for non‑positive‑premium condors (premium ≤ 0). Tests green. **(Now on `origin/main`.)** |

Plus **7 earlier commits (now pushed)**: `8c67a6d` (Telegram alert redesign — launch/settlement/weekly), `95b2196`, `aa9483d`, `5978de3`, `a95a447`, `f731ebc`, `d6c1a36` (the whole `web/` build‑out).

### Verified locally (QA + dry‑run)
- `pytest`: **125 passed**. `npm run build`: clean (Node‑server app, all routes `ƒ Dynamic`).
- Dry‑run (write‑tripwire + telegram no‑op): bot reads the View, fallback graceful, 3 Telegram messages generate correctly, **zero DB writes, zero Telegram sent**.

### Degenerate rows — cleaned and verified ✅
- The **11 degenerate rows** (ids 144–154, expiries 06‑18/06‑19, premium=0) were **cleaned**: the UPDATE was run by the user in Supabase and verified end‑to‑end. All 11 are now `is_valid=false`, `invalid_reason='zero_premium'` (confirmed 2026‑06‑20: `SELECT … WHERE invalid_reason='zero_premium'` → 11 rows, all `is_valid=false`).
- Effect verified: expiry **06‑19 dropped out of the View** (was fully degenerate); **06‑18** now shows only its valid best (**₪545.5**).
- The root fix (`763680d`) prevents *future* degenerates; this UPDATE handled the existing ones. **No further action needed for these rows.**

### Deploy status
- The §1 commits are **on `origin/main`** (pushed). The **5 new ready commits (§2d)** are **not
  pushed**. Render has **no auto‑deploy** → even pushed code deploys nothing until a Manual Deploy.
- The Next.js dashboard **is deployed** on Render (`ta35-FinalDashboard`); the 2 web commits (`726bba5`, `425a893`) just need a redeploy. (No vercel config in the repo.)

---

## 2. Execution order after Monday — step by step

> Strategy generation is **weekly (Monday ~12:00)**. The plan: let Monday's launch run, confirm it's healthy, then push + deploy.

### Step 1 — Push + deploy the worker (after a successful Monday launch)
- **Who:** me (git) + you (Render UI).
- Push:
  ```bash
  git push origin main
  ```
- **Render — manual deploy of the Python *worker* service** (the one running the pipeline via the `Dockerfile` → `python main.py`). This is what picks up the bot fix + Telegram redesign + `is_valid` root fix.
  - Render → the worker service → **Manual Deploy → Deploy latest commit**.
- ⚠️ The **dashboard is not deployed by this** — it has no Render service yet (that's §3).

### Step 2 — Live verification of the root fix
- **Who:** you (Supabase SQL Editor or a read query).
- **Timing:** the fix shows on the **first strategy‑generation run on the new code**. If deployed *before* Monday 12:00 → Monday's batch; if *after* → the following Monday (weekly cadence).
- Verify `is_valid` matches premium sign on the freshly‑generated batch:
  ```sql
  SELECT id, interval_pct, total_net_premium, max_profit_ils,
         is_valid, invalid_reason, premium_flag
  FROM iron_condor_strategies
  WHERE trigger_date = '2026-06-22'        -- the trigger date of the new batch
  ORDER BY interval_pct;
  ```
  - **Expect:** `total_net_premium > 0` → `is_valid=true`; `total_net_premium <= 0` → `is_valid=false`, `invalid_reason='non_positive_premium'`.

### Step 3 — Contingency only: if a NEW degenerate appears
> The existing 11 degenerate rows are **already cleaned and verified** (see §1) — **no action needed for them.** This step applies **only** if Monday's batch runs on the OLD code (before the root fix is deployed) and produces a *new* degenerate.
- **Who:** you (Supabase SQL Editor). **Run the SELECT first; only UPDATE if it returns rows.**
- Verify (criterion‑based — can never touch a valid row, since valid condors have premium > 0):
  ```sql
  SELECT id, expiry_date, interval_pct, total_net_premium, is_valid
  FROM iron_condor_strategies
  WHERE is_valid = true AND total_net_premium <= 0
  ORDER BY id;
  ```
- Clean (only after confirming the SELECT):
  ```sql
  UPDATE iron_condor_strategies
  SET is_valid = false, invalid_reason = 'zero_premium'
  WHERE is_valid = true AND total_net_premium <= 0;
  ```
- Reversible: `UPDATE ... SET is_valid = true WHERE id IN (...);`

### Step 4 — Telegram daily RR / max_risk — ✅ DONE locally (`a6d031e`, not pushed/deployed)
> Full write‑up + evidence in §2c (Bug 2).
- **Fixed (`a6d031e`):** `settle_expiry`'s SELECT now carries `risk_reward_ratio, max_risk_ils`
  (`strategy_engine.py:1011‑1012`) + the in‑memory fallback dict; the message code already renders them.
- **Live verification:** at the next settlement after the worker deploy the daily settlement message
  shows `· RR <x.xx> · מקס׳ סיכון <y> ₪`.

### Step 5 — Remove the daily‑summary Telegram message (user decision 2026‑06‑22)
- **Why:** the user no longer wants the end‑of‑day **"📋 סיכום יומי"** message — "no longer serves me." Keep the **settlement** and **weekly summary** messages; only the daily summary goes.
- **Change (single self‑contained block):** delete the *Daily summary* block in `main.py:510‑527`
  (the `if daily_summary_date != today_iso:` block that calls `telegram_bot.alert_daily_summary`).
  Independent of the settlement/weekly path — touches no shared state.
- **Optional cleanup (only if it leaves them unused):** the `daily_summary_date` tracker and the
  `daily_cycles/daily_rows/daily_expiries/daily_errors` accumulators feed *only* this message —
  remove them too if nothing else reads them (grep first). `alert_daily_summary` in
  `telegram_bot.py:249` can stay (harmless) or be removed.
- **Timing gate:** code edit is harmless, but **deploy = worker restart** → ship it bundled with
  the post‑settlement deploy, **not** before tomorrow's (Tue 2026‑06‑23) settlement is verified.

---

## 2b. QA findings — sequenced after tomorrow's settlement

> A full read-only QA pass (2026-06-23) is written up in **[QA_ASSESSMENT.md](QA_ASSESSMENT.md)**
> — project map, dimension-by-dimension ratings (with file:line evidence), systemic root causes,
> and a 5-phase action plan. **As of that read‑only pass nothing was fixed**; since then several
> items have been **fixed locally** — `dispatchToDemo` validation (`726bba5`), Bug 1 delivery
> (`65c05d8`+`096edc7`) and Bug 2 (`a6d031e`); see §2c/§2d. Remaining items still wait for the
> settlement gate / deploy — **don't fix the rest without that gate.**

**Phase 0 priorities (money & data integrity):**
1. **`dispatchToDemo` — service-role write** *(web, security)* — `web/src/app/simulator/actions.ts`.
   **✅ Validation hardened (`726bba5`, local):** every field + leg is now strictly validated
   (types/ranges), the row is rebuilt from validated values only, and a coarse rate‑limit (20/min) is
   in place — invalid payloads are rejected before any DB write. **Still open (follow‑up):** the deeper
   fix — **require auth + drop to the anon key + RLS** so the service key is no longer exposed to public
   writes — is documented inline and remains a separate task.
2. **Demo settlement idempotency + atomicity** *(dashboard)* — `dashboard.py:676-732,1865-1904`.
   No DB-level `status=eq.open` guard + read-modify-insert balance → double-count / lost-update /
   settled-but-uncredited. → conditional PATCH, server-side increment RPC, check the HTTP response.
3. **Canonical "settled" / "capital" definition.** The **weekly‑summary percentage** slice is now
   **done** — `PORTFOLIO_CAPITAL = 20_000` exists as the single capital constant and drives the weekly
   summary % (`1c85217`; see §2c sequencing). **Still open:** the broader unification — one canonical
   "settled strategies" View + one capital constant shared across **all** consumers (§3.B / QA action
   item 9). "Settled" is still defined ~4 ways across bot/dashboard/web (`strategy_engine.py:685` vs
   `data.ts:121` vs `data.ts:319` vs `dashboard.py:1440-1450`).
4. **Range-check the settlement price** *(worker; QA Phase 0 #4)* — `strategy_engine.py:871-887`.
   - **Gap:** in `settle_expiry`'s price chain the TASE-open branch already clamps to `TA35_MIN/MAX`
     (`:872`), but the **Yahoo** branch (`_fetch_settlement_price`, `:160-175`) and the **live-data**
     branch (`:881`) accept any `>0`, and the final gate (`:885`) only rejects `≤0`. A bogus Yahoo value
     (e.g. `5` or `50000`) settles **every** strategy of the week at a wrong index → all max-loss. Every
     other index path already clamps (`_get_base_index:188,193`; base-index `:773,778`) — these two
     branches are the lone exception.
   - **Fix (3 spots, all in `strategy_engine.py`):** (a) inside `_fetch_settlement_price` accept only
     in-range, else try `regularMarketPrice`, else return `0` (so a bogus value falls through to
     live-data); (b) live-data `if v>0` → `if TA35_MIN<=v<=TA35_MAX`; (c) final gate `if index_close<=0`
     → `if not (TA35_MIN<=index_close<=TA35_MAX)`.
   - **Behavior:** reject the bad value, try the next source, else **abort → leave unsettled**
     (`result_status` stays null). **Self-heals:** `main.py:540` writes `settlement_done:<date>` only when
     `settle_expiry` returns True, so an abort **retries every cycle** until a sane price returns
     (idempotent — settles only `result_status=is.null`); never stuck forever. **Damage asymmetry:** a
     *missed* settlement is recoverable (retry); a *wrong* one corrupts the week's P&L **irreversibly** →
     "reject & leave" is the safe side. Optional: a throttled CRITICAL alert (separate decision); at
     minimum sharpen the abort log.
   - **Indirectly protects the demo book**, which settles off the `actual_index_close` this writes.
   - **Tests (pytest):** `_fetch_settlement_price` (in-range pass / bogus open→price fallback / both
     bad→`0`); `settle_expiry` **invariant** — a bogus price ⇒ **zero PATCH**, `result_status` unwritten,
     returns False; boundaries `1000`/`10000` inclusive, `999`/`10001` rejected; the 132 existing tests
     stay green.
   - **Risk: Low–Medium** — touches `settle_expiry` (real-money path) but only tightens an existing
     `>0` check to in-range (mirrors `:872`); can only make settlement *more conservative*, never settle
     what it wouldn't have. False-reject is implausible (`1000–10000` ≫ TA-35 ~4100). **No `main.py`
     change** — the whole price chain is internal to `settle_expiry`.

Other phases (silent worker failures, data-correctness, parse robustness, tests) are detailed in
QA_ASSESSMENT.md and are **not** urgent relative to the three above.

---

## 2c. Verified delivery bugs — Telegram (diagnosed 2026‑06‑27, read‑only)

> Two **confirmed** bugs found by a read‑only diagnosis (code + live DB markers). **Both have since
> been FIXED locally** (see the per‑bug ✅ Status lines; not pushed/deployed). Both sit on the **live
> pipeline** path — verify after deploy, one at a time, with the normal gate. These supersede/upgrade
> the earlier hypotheses (QA systemic #1, Phase 1 item 5; and §2 Step 4 above).

### 🔴 Bug 1 — the weekly summary has **never** been sent
- **Evidence (live DB, `pipeline_state`, 2026‑06‑27):** **zero `weekly_summary_sent:*` markers for
  ANY week — W23, W24, W25, W26 all missing.** By contrast every `settlement_done:*` and
  `daily_summary_sent:*` for those weeks is present, and W26's 32 strategies are all fully settled
  (`result_status` populated). So it is **not** a one‑off Friday miss — the weekly path has never
  completed. Friday 26/06's last recorded activity was 17:16 IL (`history_copied`/`daily_summary`);
  nothing at the ~18:30 IL firing time.
- **Root cause:** `weekly_summary_due_at` is **in‑memory only** (`main.py:247`). It is set
  in‑market at the last Friday cycle (~17:16 IL) to fire in the off‑hours block at close+1h
  (~18:30 IL) — `main.py:490‑498` schedules, `main.py:273‑303` fires. The whole 74‑minute gap is
  held in RAM. A worker **restart/redeploy** (or any process loss) in that window drops it, and
  **nothing reschedules after close** (scheduling needs trading‑hours + `last_cycle`). The marker
  is written **only after a successful send** (`main.py:298`); the exception path (`main.py:301‑303`)
  clears `due_at`, writes **no marker, and never retries**. Either failure mode (restart **or**
  send‑exception) leaves exactly this trace — distinguishing them needs Render logs ~15:00–15:45 UTC
  Friday (look for redeploy or a `Weekly summary error` line).
- **This is QA systemic #1 / Phase 1 item 5, now empirically confirmed** (the "single most concrete
  silent‑failure", QA line 160).
- **Planned fix (NOT done):** make the schedule **durable in `pipeline_state`** — a
  `weekly_summary:scheduled:<year>-W<ww>` marker written at scheduling time + the existing
  `weekly_summary_sent:<…>` written after send, plus an **off‑hours catch‑up** that fires from the
  durable "scheduled but not sent" state — mirroring what `_archive_eod_snapshot` already does for
  the EOD archive (idempotent, restart‑safe, catches a missed cycle).
- **Touches `main.py` (scheduling/firing) — live pipeline.** Deploy = worker restart.
- **Verification: only possible the following Friday** (weekly cadence). Confirm a
  `weekly_summary_sent:<year>-W<ww>` marker appears **and** the Telegram message arrives.
- **✅ Status (2026‑06‑27): FIXED locally (not pushed/deployed).**
  - `65c05d8` — durable scheduling + off‑hours catch‑up (markers
    `weekly_summary:scheduled:<…>` / `weekly_summary_sent:<…>`, idempotent, restart‑safe);
    added `database.state_get`. Tests: `tests/test_weekly_summary_durable.py` (7).
  - `096edc7` — **decoupled scheduling from cycle `ok`** (stale‑feed resilience): the
    summary reports already‑settled DB strategies, so it now schedules on the last trading day
    even when the feed is stale (`ok=False`). Also caches the expiry list regardless of `ok` so
    last‑trading‑day detection stays accurate on a stale day. Closes **gap #3** from the
    last‑trading‑day diagnosis.
  - **Still open → see §3.C** (the holiday/short‑session calendar — gaps #1 & #2): last‑day
    detection is still delegated to TASE's expiry feed, and the fallback is weekday‑hardcoded.

### 🟡 Bug 2 — daily settlement message omitted **RR + max_risk** — ✅ FIXED locally (`a6d031e`)
- **Evidence:** `settle_expiry`'s settlement‑report SELECT (`strategy_engine.py:1011‑1012`) fetches
  only `interval_pct, short_put_strike, short_call_strike, actual_pnl_ils, result_status` — **no
  `risk_reward_ratio`, no `max_risk_ils`** — and the in‑memory fallback dict (`:1024‑1029`) omits
  them too. So `alert_settlement` receives no RR/max_risk and skips them (`telegram_bot.py:230‑235`,
  guarded on `best.get(...)` → None). **The data exists** in `iron_condor_strategies` (verified
  populated for all 32 W26 rows) — it is simply not selected.
- **Fix (DONE — `a6d031e`):** added `risk_reward_ratio, max_risk_ils` to the SELECT at
  `strategy_engine.py:1011‑1012` (and to the fallback dict). The message code already renders them.
- **Touches `strategy_engine.py` (`settle_expiry`) — live pipeline.** Same item as **§2 Step 4**
  and the **§4 trap**.
- **✅ Status (2026‑06‑27): FIXED locally (`a6d031e`) — not pushed/deployed; live‑verifiable at the
  next settlement after deploy.**
- **Verification:** the next settlement after deploy — RR + max‑risk appear in the daily message.

### Sequencing vs. the percentages plan (potential‑% / `PORTFOLIO_CAPITAL`) — ✅ DONE (`1c85217`)
The sequencing held: Bug 1 (durable + decoupled delivery) was fixed **first**, then the percentage was
added on top. **`1c85217`** adds `PORTFOLIO_CAPITAL = 20_000` (config) and a `potential_pct` line to
the weekly summary on a **single‑lot basis** (`pct = potential_total / 20_000 × 100`, worded
"לוט בודד · תיק 20,000 ₪"). It is **no longer blocked**. Live confirmation still rides on Bug 1
delivery — the % first appears in the **first weekly summary actually sent** post‑deploy. *(Scope note:
this resolves the weekly‑summary % only; the broader cross‑consumer "capital/settled" unification —
§2b item 3 / §3.B / QA #9 — is still open.)* Bug 2 (daily RR/max_risk) was independent and shipped on
its own (`a6d031e`).

---

## 2d. Deployment plan — ready commits

> **6 local commits**, built + tested (`pytest` 132 green; `web` `npm run build` clean; dry‑runs
> clean). **Nothing pushed, nothing deployed.** **4 are worker‑only** (Python pipeline) and **2 are
> web‑only** (`726bba5`, `425a893`). Render has **no auto‑deploy** → a `git push` deploys nothing; each
> service is deployed separately: **Manual Deploy of the worker** for the 4 worker commits, and a
> **Manual Deploy of the existing Next.js web service (`ta35-FinalDashboard`)** for the 2 web commits.

### 1. Ready‑to‑deploy commits

| commit | what | target | files | risk |
|---|---|---|---|---|
| `a6d031e` | **Bug 2** — RR + max_risk in the daily settlement message | worker | `strategy_engine.py` (settle_expiry SELECT + fallback) | **Low** — two columns added to one read; message code already rendered them defensively |
| `65c05d8` | **Bug 1a** — durable weekly‑summary scheduling + off‑hours catch‑up | worker | `main.py`, `database.py` (+`state_get`), `tests/…durable.py` | **Medium** — touches the main loop's off‑hours block; covered by 7 tests + dry‑run |
| `096edc7` | **Bug 1b** — decouple scheduling from cycle `ok` (stale‑feed resilience) | worker | `main.py` (scheduling gate + expiry cache) | **Medium** — touches the scheduling gate; dry‑run incl. stale‑feed scenario |
| `726bba5` | **Security** — validate + harden `dispatchToDemo` (validation + rate‑limit) | **web** | `web/src/app/simulator/actions.ts` | **Low** — input validation + rebuild + coarse rate‑limit; legit dispatch unchanged; `npm run build` clean |
| `1c85217` | **Feature** — portfolio % in the weekly summary (single‑lot, 20K) | worker | `config.py`, `strategy_engine.py`, `telegram_bot.py` | **Low** — one extra summary line; defensive on missing `potential_pct` |
| `425a893` | **Feature** — demo trade settlement in web (atomic, idempotent) | **web** | `web/src/app/demo/actions.ts`, `web/src/app/demo/page.tsx` | **Low‑Med** — new settle sweep (conditional `status=eq.open` PATCH guard + balance credit); idempotency verified locally; `npm run build` clean |

**State (git‑verifiable):** these **6** are the **only** commits ahead of `origin/main` (`4e966dc`),
in order `a6d031e → 65c05d8 → 096edc7 → 726bba5 → 1c85217 → 425a893`. Everything earlier (root `is_valid` fix
`763680d`, bot `get_weekly_stats`, the `web/` build‑out, etc.) is **already on `origin/main`** — i.e.
pushed. **But "pushed ≠ deployed":** the *running* commit on each Render service is **not knowable from
git** — confirm in the Render dashboard. If earlier QA'd work was never manually deployed, the worker
deploy below picks **all of it** up at once (review §2 first).

### 2. Recommended order + timing

- **Step A — Push (safe anytime):**
  ```bash
  git push origin main   # pushes a6d031e, 65c05d8, 096edc7, 726bba5, 1c85217, 425a893; no effect until a deploy
  ```
- **Step B — Deploy the WORKER (4 worker commits: `a6d031e`, `65c05d8`, `096edc7`, `1c85217`)**
  (Render → Python *worker* service → Manual Deploy → Deploy latest commit). All four are worker‑only
  and independent → a single restart ships them together.
  - **When (Bug 1 touches the scheduling loop):** deploy = worker restart, so pick a **quiet
    window** — ideally **off‑hours** (e.g. Sunday, worker sleeping) or a trading day **after that
    day's settlement (~10:00 IL) and outside the 12:00–13:00 strategy window**.
  - **Not on the last trading day of the week**, and **not mid‑dispatch** — so the weekly‑summary
    schedule+fire gets a full clean run on the new code, and "deploy after a successful dispatch,
    not on a day the loop is dispatching" holds.
  - Net: deploy **early/mid‑week after Monday's launch is confirmed healthy**, so the *upcoming*
    last trading day runs the new durable path end‑to‑end.
- **Step C — Deploy the WEB commits (`726bba5`, `425a893`) separately.** They touch **only** `web/`
  and ship via the **existing Next.js web service (`ta35-FinalDashboard`, already deployed on Render)**
  — **not** the worker. Manual‑deploy that service to pick them up (`726bba5` = dispatch hardening;
  `425a893` = demo settlement). The worker deploy (Step B) does **not** include them. ⚠️ Confirm the
  web service has `SUPABASE_URL`/`SUPABASE_KEY` set (the settlement action writes with the service key).
- **Rollback (clean):** Render → worker → Deploy previous commit (`4e966dc`) → restart restores
  prior behavior. The new key `weekly_summary:scheduled:*` is **additive**; `weekly_summary_sent:*`
  is the **same key the old code already wrote and honors** — old code ignores `scheduled`, so a
  roll‑back won't double‑send and needs no DB cleanup.

### 3. Verification (with when it's possible)

- **Bug 2 (RR/max_risk)** — at the **next settlement** (settlements run ~10:00 IL on each expiry
  day). The "🏁 פקיעת Iron Condor" message should now show `· RR <x.xx> · מקס׳ סיכון <y> ₪`.
  Verifiable as early as the next trading day that has an unsettled expiry.
- **Bug 1 (weekly summary)** — at the **next *last trading day* of the week** after deploy:
  1. At that day's last cycle (~17:16 IL): a **`weekly_summary:scheduled:<year>-W<ww>`** marker
     appears in `pipeline_state` (value = firing time ~18:30).
  2. ~1 h after close (~18:30 IL): **`weekly_summary_sent:<year>-W<ww>`** appears **and** the
     "📊 סיכום שבועי" Telegram arrives.
  - **Stale‑feed check (Bug 1b):** even if `STALE_TRADE_DATE` fires that day, step 1's marker must
    still be written (scheduling no longer gated on `ok`).
  - **Restart check (optional):** a deliberate worker restart between 17:16 and 18:30 should still
    end with the summary sent (off‑hours catch‑up).
  - First real confirmation is therefore **one week out** (weekly cadence).
- **Percentages (`1c85217`)** — appears in the **first weekly summary actually sent** post‑worker‑deploy:
  a line `≈ <±x.xx>% מהתיק (לוט בודד · תיק 20,000 ₪)` right under the ₪ total, where
  `% = potential_total / 20,000 × 100`. Rides on Bug 1 delivery → first confirmable on the next last
  trading day.
- **`dispatchToDemo` hardening (`726bba5`)** — confirmable after redeploying the **existing web
  service** (`ta35-FinalDashboard`, §3.A): a valid simulator dispatch still writes a `demo_trades` row;
  a malformed payload (bad qty / strike out of range / missing fields) is rejected with a Hebrew error
  and **no** DB write. Locally verified now (transpile + stubbed fetch: valid passes, all invalid
  shapes rejected, rate‑limit caps at 20/min).
- **Demo settlement (`425a893`)** — after the web redeploy: open a demo trade for an already‑settled
  expiry, load the demo page → it flips to `closed` with `pnl_ils` and the balance is credited once;
  reloading does **not** settle again or double‑count. Locally verified now (transpile + stubbed
  Supabase: settle‑once, idempotent re‑run, PATCH‑guard under stale read, leg‑shape parity, no‑price
  skip, malformed skip).

### 4. NOT in this deploy — still open (future)

- **`dispatchToDemo` auth + RLS** — `726bba5` shipped *validation + rate‑limit*; the deeper fix
  (**require auth, switch to the anon key + RLS** so the service key isn't exposed) is **still open**
  (§2b item 1). Separate, larger change.
- **Holiday / short‑session calendar** — **§3.C**. Bug 1b closed the stale‑feed coupling (gap #3),
  but last‑trading‑day detection is still delegated to TASE's expiry feed (gap #1) and the fallback
  is weekday‑hardcoded (gap #2). Big, not urgent; touches `config.py`/`tase_api.py`/`main.py`.
- **Cross‑consumer "capital/settled" unification** — the weekly‑summary % is **done** (`1c85217`),
  but one canonical View + one capital constant across **all** consumers is still open (§2b item 3 /
  §3.B / QA #9).
- **QA action plan** — later phases in **§2b / QA_ASSESSMENT.md**. Phase 0 #1 (`dispatchToDemo`
  validation, `726bba5`) and demo‑settlement idempotency/atomicity (`425a893`) are now done; a
  **residual cross‑trade balance race** remains (server‑side atomic increment / RPC — see §3.A).
- **Streamlit → Next.js cutover** — **§3.A**. The Next.js service already exists & is deployed
  (`ta35-FinalDashboard`); remaining cutover work (repoint domain, retire Streamlit, decide the C/D
  write controls) lives there. Not part of the worker deploy.

---

## 3. Bigger projects (not urgent)

### A. Dashboard migration: Streamlit → Next.js  ([[dashboard-migration-pending]])
**Ready:** `web/` builds clean (Node‑server, Node ≥20.9 pinned). Env it needs: `SUPABASE_URL` + `SUPABASE_KEY` (server‑side only, **no** `NEXT_PUBLIC_`).
**Missing display views** (data exists — same tables — just not rendered yet):
1. Cumulative **equity curve** (running P&L by expiry; Next has per‑expiry bars only).
2. **"ההמלצה השבועית"** — this week's active condor (strikes/legs).
3. **"בסיכון עכשיו"** — open positions vs breakevens vs live index.
4. **"דופק השבוע"** — this week's P&L + leader.
5. **"מרווחים מועדפים"** — ⚠️ a **WRITE** control (writes `pipeline_state`). *May be obsolete* now that the weekly summary is potential‑based (all intervals). Decide before replicating.
6. **Per‑interval comparison** (util%) and **per‑expiry payoff + legs** in the detail view.

**✅ Demo settlement — ported to web (`425a893`).** Previously `close_demo_trade` + `_update_demo_balance` lived **only in `dashboard.py`**, so killing Streamlit meant demo positions would never settle (web only *dispatched*). Now `web/src/app/demo/actions.ts` `settleDueDemoTrades()` settles expired demo trades + credits the balance — **atomic + idempotent** (conditional `status=eq.open` PATCH; balance credited only when a row was flipped), triggered on the **demo page load**. P&L matches Streamlit's `sandbox_trade_pnl` and handles both stored leg shapes (web `{kind,side,entryPx}` and Streamlit `{type,action,premium_pts}`). **Decision: built in web (server action), not the worker.** Residual: the absolute‑balance read‑modify‑insert can lose an update only if two page‑loads settle *different* trades simultaneously — true fix is a server‑side atomic increment (RPC); tracked as a follow‑up.

**Streamlit shutdown — blockers & conditions (from the 2026‑06‑27 diagnosis).** Shutdown was blocked on demo‑settlement living only in Streamlit; the worker has **zero** demo logic and web only *dispatched* + *read*. Status by condition:
- **A (was blocker) — `close_demo_trade`:** ✅ **DONE in web** (`425a893`). Also fixes the old "visit‑dependent" settlement (Streamlit only settled when someone opened its Demo page) — the web sweep is idempotent so it can safely run on any visit / a cron.
- **B (was blocker) — `_update_demo_balance` atomic/idempotent:** ✅ **DONE in web** (`425a893`) — conditional‑PATCH guard, no read‑modify‑insert double‑count; one residual cross‑trade race (above).
- **C/D — `set_portfolio_capital` + `set_preferred_intervals`:** ⬜ **OPEN — decide build‑in‑web vs freeze.** Both are Streamlit‑only `pipeline_state` write controls. `preferred_intervals` is read by the worker to filter the weekly summary; `portfolio_capital` is the dashboard's configurable capital (distinct from the worker's hard‑coded `PORTFOLIO_CAPITAL = 20K`). If not rebuilt in web, the last‑stored values persist and the worker keeps working — acceptable if you won't change them.
- **E — one‑click auto‑strategy→demo push + the missing display views (1–6 above):** ⬜ convenience/parity, not blockers.

**Safe‑shutdown gate:** A+B are done → demo positions opened in web now settle & credit the balance. Remaining before retiring Streamlit: (1) deploy the web commits to `ta35-FinalDashboard` and verify a real demo settle end‑to‑end; (2) decide C/D (build in web or freeze); (3) E optional.

**Planned (future, NOT done) — move demo settlement to the worker.** The web settlement above (`425a893` + the all‑pages sweep `88140d8`) is the working base, but the long‑term home is the **worker**: settle demo trades **automatically alongside `settle_expiry`** (when the real expiry settles), so settlement runs with **zero dependence on anyone opening a dashboard** — the web sweep, even all‑pages, still only fires on a page load (full visit-independence would otherwise need a cron). This **refines the "built in web, not the worker" note above**: web was the deliverable that unblocked retiring Streamlit; the worker is the intended destination. The web logic is portable (pure P&L + idempotent conditional‑PATCH settle + balance credit). **No Telegram alert for demo settlements** — explicit decision to **not mix the demo book with the real pipeline's alerts**; demo settlements are reviewed in the dashboard. (Open to revisit.) **Sensitive — touches the live pipeline (`main.py` / `strategy_engine.py`); planned, not done.** **Full build spec: [DEMO_SETTLEMENT_WORKER_PLAN.md](DEMO_SETTLEMENT_WORKER_PLAN.md)** (integration point, atomicity/idempotency + single-writer fix, per-leg P&L, no-Telegram, web fallback→removal, tests/dry-run, risk + ordered steps).

**Cutover steps (the Next.js service already exists & is deployed: `ta35-FinalDashboard`):** redeploy `ta35-FinalDashboard` to pick up the web commits (`726bba5`, `425a893`) → verify on its `*.onrender.com` (confirm `SUPABASE_URL`/`SUPABASE_KEY` env; settlement writes with the service key) → decide/build the remaining write controls (C/D) if still wanted → repoint the domain from `ta35-dashboard-front` (Streamlit) → suspend the Streamlit service. **Run both in parallel** until verified (easy rollback).

### B. "Everyone speaks the same language" (unify calculations)
**Already unified (single source = Views):** `best_condor_per_expiry` + `condor_weekly_potential` → the **bot** (`get_weekly_stats`) and the **dashboard** (`getBestCondorPerExpiry`) read the same number.
**Still duplicated (each consumer computes its own — inconsistency risk):**
- "**settled**" definition — Streamlit (`result_status` present, +expired‑past), Next.js `getKpis` (`result_status & close>0`) vs `getStrategiesData` (`actual_pnl != null`), bot legacy (`result_status not null`). *Mostly moot today* (0 rows differ) **except** the 11 degenerates.
- **Win rate**, **outcome distribution** (Streamlit `max_profit_ils>0` vs Next `result_status` category — the **11 degenerates** classify differently), **cumulative P&L** — each computed independently.
**To unify:** a canonical "settled strategies" View; derive win‑rate / outcomes / cumulative from it; align `getKpis` and `getStrategiesData` to it.

### C. TASE holiday / short‑session calendar  *(big, not urgent)*
**Why:** the worker has **no holiday or short‑Friday awareness** (`config.py:21` Mon–Fri only,
`is_trading_hours` at `main.py:76`). Consequences, from the last‑trading‑day diagnosis (2026‑06‑27):
- **Gap #1 — holiday awareness is fully delegated to TASE's expiry feed.** `is_last_trading_day_of_week`
  (`tase_api.py:345‑374`) PRIMARY = `today == max(this‑week expiry dates)`. If TASE keeps listing a
  Friday expiry that doesn't actually trade (Friday is a holiday), the system waits for a Friday that
  never settles and **mis‑detects Thursday** as not‑last → the summary may never schedule. Only works
  if TASE itself drops/moves the Friday expiry. The code can't independently know it's a holiday.
- **Gap #2 — the FALLBACK is weekday‑hardcoded** (`tase_api.py:366‑374`): when the expiry list is
  empty it scans Mon–Fri and always picks Friday — fully holiday‑blind.
- Plus the worker **churns empty 15‑min cycles on holidays** (thinks the market is open) and can fire
  spurious `STALE_TRADE_DATE` on the first session after a mid‑week holiday
  (`option_schema.py:279‑283`). Already noted in **QA_ASSESSMENT.md:207‑208**.

**Note — gap #3 (stale‑feed coupling) is already fixed** (scheduling decoupled from cycle `ok`, see
§2c Bug 1 status). What remains here is the genuine calendar work.

**Fix (when tackled):** introduce a real TASE trading calendar (holidays + short sessions) and use it
in **both** `is_trading_hours` (don't run on closed days) **and** last‑trading‑day detection (don't
delegate to the expiry feed; don't assume Friday). Touches `config.py` + `tase_api.py` + `main.py` —
**live pipeline**, so gate behind a real verification on a known short week.

---

## 4. Warnings / traps we found (do not forget)

- **`is_valid` was manual‑only.** The pipeline never set it — the old `is_valid=false` rows were a one‑time manual UPDATE; new rows defaulted to `true`. Fixed in `763680d` (now pipeline‑managed). The known degenerates (the 11) are **already cleaned (§1)**; the only residual risk is a *new* batch generated **before** the fix is deployed (handled by §2 step 3).
- **No validation for premium = 0.** The old flag logic caught `< 0` but not `= 0` → degenerate (no‑price) condors saved as valid. Fixed (`<= 0` → `non_positive_premium` + `is_valid=false`).
- **Demo settlement lives ONLY in Streamlit** (`dashboard.py`). Will be lost on cutover — port it first.
- **Render has no auto‑deploy** and **no config‑in‑repo** (only the Python `Dockerfile`). Service config (root dir, build, start, Node, env) lives in the **Render UI**. A push deploys nothing automatically.
- **Next.js dashboard is deployed** on Render (`ta35-FinalDashboard`) — web commits need a redeploy to ship.
- **Strategy generation is weekly (Monday).** Live verification of strategy‑gen changes is only possible on a Monday trigger.
- **The Views read live DB state** (the worker updates every ~15 min) → displayed numbers shift between reads. Expected, not a bug.
- **`tase_putcall_history`** exists but **neither** dashboard reads it — no data lost in the migration, just noting.
- **Telegram daily RR/max_risk** — ✅ **fixed locally (`a6d031e`)**: `settle_expiry` now selects
  `risk_reward_ratio, max_risk_ils`; the daily settlement message shows them (§2c Bug 2).
- **Weekly summary had NEVER been sent** (no `weekly_summary_sent` marker W23–W26; in‑memory schedule
  lost between close and firing) — ✅ **fixed locally (`65c05d8` durable + `096edc7` decoupled from
  `ok`)**; full write‑up §2c Bug 1. The percentages plan it blocked is now also **done** (`1c85217`).
- **`dispatchToDemo` was an unauthenticated service‑role write** — ✅ **validation + rate‑limit added
  (`726bba5`, web)**; the row is rebuilt from validated fields only. **Follow‑up still open:** auth +
  anon key + RLS (§2b item 1).
- **Web vs worker deploy:** `726bba5` and `425a893` are **web‑only** → they deploy with the existing
  Next.js service (`ta35-FinalDashboard`, §3.A), **not** with the worker deploy. The other 4 are worker‑only.

---

*This file is local and not pushed. Update it as steps complete.*
