# NEXT_WEEK_PLAN — execution plan for after Monday (2026‑06‑22)

> Centralizing everything that is **built locally but not yet pushed/deployed**, the
> exact steps to roll it out after Monday's strategy launch, the bigger non‑urgent
> projects, and the traps we found so they aren't forgotten.
>
> Generated 2026‑06‑20. **Nothing here has been pushed or deployed.**

---

## 1. Current state

### Local commits NOT pushed (`origin/main` is 11 behind)
The **4 recent commits** (this session's QA'd work):

| hash | what |
|---|---|
| `7319adf` | **bot** — `get_weekly_stats` reads the `best_condor_per_expiry` View (single source shared with the dashboard) |
| `2e05b0c` | **dashboard condor** — "פוטנציאל פר פקיעה" pager on `/strategies` (₪/RR/max‑risk per expiry + historical paging), reads the View |
| `6815f65` | **web (accumulated, NOT re‑verified tonight)** — VTA35, light mode, interactive index chart, home option chain, simulator dropdowns, demo/strategies filters, Node `engines >=20.9` pin |
| `763680d` | **root fix** — pipeline auto‑marks `is_valid=false` for non‑positive‑premium condors (premium ≤ 0). Tests green. **Ready to deploy after Monday.** |

Plus **7 earlier unpushed commits**: `8c67a6d` (Telegram alert redesign — launch/settlement/weekly), `95b2196`, `aa9483d`, `5978de3`, `a95a447`, `f731ebc`, `d6c1a36` (the whole `web/` build‑out).

### Verified locally (QA + dry‑run)
- `pytest`: **125 passed**. `npm run build`: clean (Node‑server app, all routes `ƒ Dynamic`).
- Dry‑run (write‑tripwire + telegram no‑op): bot reads the View, fallback graceful, 3 Telegram messages generate correctly, **zero DB writes, zero Telegram sent**.

### Degenerate rows — cleaned and verified ✅
- The **11 degenerate rows** (ids 144–154, expiries 06‑18/06‑19, premium=0) were **cleaned**: the UPDATE was run by the user in Supabase and verified end‑to‑end. All 11 are now `is_valid=false`, `invalid_reason='zero_premium'` (confirmed 2026‑06‑20: `SELECT … WHERE invalid_reason='zero_premium'` → 11 rows, all `is_valid=false`).
- Effect verified: expiry **06‑19 dropped out of the View** (was fully degenerate); **06‑18** now shows only its valid best (**₪545.5**).
- The root fix (`763680d`) prevents *future* degenerates; this UPDATE handled the existing ones. **No further action needed for these rows.**

### NOT pushed / NOT deployed
- No `git push` done. No Render/Vercel deploy. Render has **no auto‑deploy** → a push deploys nothing on its own.
- The Next.js dashboard is **not deployed anywhere** (no Render web service / no vercel config in the repo) — local only.

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

### Step 4 — (pending, separate) Telegram daily RR / max_risk
- The daily settlement message is coded to show **RR + max_risk** but only if `settle_expiry`'s report carries them. **It does not yet** — `settle_expiry`'s SELECT needs `risk_reward_ratio, max_risk_ils` added (+ the in‑memory fallback dict).
- **Sensitive (touches `settle_expiry`)** — do only after a settlement is verified. Until then the daily shows `מרווח · ₪` without RR/max‑risk (code is defensive, no crash).

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

**🔴 Critical migration gap — demo settlement.** `close_demo_trade` (settle demo positions → P&L → update `demo_balance`) lives **only in `dashboard.py`**. Killing Streamlit means demo positions **never settle** (Next.js only *dispatches*). Decide before cutover: port settlement to the worker or to a web server‑action.

**Migration steps:** new Render **Web Service** (Runtime Node, Root Directory `web`, Build `npm ci && npm run build`, Start `npm start`, Node 20+, env `SUPABASE_URL`/`SUPABASE_KEY`) → test on its `*.onrender.com` → repoint the domain from `ta35-dashboard-front` → suspend the Streamlit service. **Run both in parallel** until verified (easy rollback).

### B. "Everyone speaks the same language" (unify calculations)
**Already unified (single source = Views):** `best_condor_per_expiry` + `condor_weekly_potential` → the **bot** (`get_weekly_stats`) and the **dashboard** (`getBestCondorPerExpiry`) read the same number.
**Still duplicated (each consumer computes its own — inconsistency risk):**
- "**settled**" definition — Streamlit (`result_status` present, +expired‑past), Next.js `getKpis` (`result_status & close>0`) vs `getStrategiesData` (`actual_pnl != null`), bot legacy (`result_status not null`). *Mostly moot today* (0 rows differ) **except** the 11 degenerates.
- **Win rate**, **outcome distribution** (Streamlit `max_profit_ils>0` vs Next `result_status` category — the **11 degenerates** classify differently), **cumulative P&L** — each computed independently.
**To unify:** a canonical "settled strategies" View; derive win‑rate / outcomes / cumulative from it; align `getKpis` and `getStrategiesData` to it.

---

## 4. Warnings / traps we found (do not forget)

- **`is_valid` was manual‑only.** The pipeline never set it — the old `is_valid=false` rows were a one‑time manual UPDATE; new rows defaulted to `true`. Fixed in `763680d` (now pipeline‑managed). The known degenerates (the 11) are **already cleaned (§1)**; the only residual risk is a *new* batch generated **before** the fix is deployed (handled by §2 step 3).
- **No validation for premium = 0.** The old flag logic caught `< 0` but not `= 0` → degenerate (no‑price) condors saved as valid. Fixed (`<= 0` → `non_positive_premium` + `is_valid=false`).
- **Demo settlement lives ONLY in Streamlit** (`dashboard.py`). Will be lost on cutover — port it first.
- **Render has no auto‑deploy** and **no config‑in‑repo** (only the Python `Dockerfile`). Service config (root dir, build, start, Node, env) lives in the **Render UI**. A push deploys nothing automatically.
- **Next.js dashboard not deployed yet** — local only.
- **Strategy generation is weekly (Monday).** Live verification of strategy‑gen changes is only possible on a Monday trigger.
- **The Views read live DB state** (the worker updates every ~15 min) → displayed numbers shift between reads. Expected, not a bug.
- **`tase_putcall_history`** exists but **neither** dashboard reads it — no data lost in the migration, just noting.
- **Telegram daily RR/max_risk** pending the `settle_expiry` SELECT addition (§2 step 4).

---

*This file is local and not pushed. Update it as steps complete.*
