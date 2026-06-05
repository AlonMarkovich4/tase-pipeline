# QA_INTEGRATION_AUDIT.md — Correctness & Integration Review

> Review date: 2026-06-05. **Review only — no code changed.**
> Weight: engine-heavy, with the engine↔dashboard data boundary as the second
> focus. Scope per mandate; design/UX explicitly excluded.
> Method: every file read in full or at the relevant boundary; field flow traced
> statically (a live cross-process engine→DB→dashboard run needs Supabase +
> Streamlit and was not executed — see Smoke §4).

---

## ⚠️ Blocking discrepancy (resolve before acting on any ₪ finding)

The agreed invariant in this mandate says **multiplier = 100**. The code says
**`TASE_MULTIPLIER = 50`** (`config.py:41`), and earlier in this engagement the
owner stated *"the multiplier will be 50."* These conflict. **Every ₪ figure in
the system scales linearly with this constant.** This review verifies the
structural invariant *"multiplier applied exactly once"* independent of the
value, and records the value conflict as **Question for human #1**. I did not
assume either value.

---

## 1. Field-level data-flow map (end to end)

```
TASE API (api.tase.co.il)                 CamelCase keys; rates in ₪; strikes in pts
  │  tase_api._fetch_all_pages
  │   • injects UnderlingAsset_Call/Put = underlying or cycle Yahoo value
  ▼
option_schema.validate_items              Pydantic OptionPair; _parse_number→Decimal
  │   • range/sign checks on strike, LastRate, Delta, Underlying
  │   • accepted[] (raw dicts, unchanged) / rejected[]; CRITICAL gate
  ▼
database.upsert_items                     keys.lower(); filtered to VALID_COLUMNS
  │   • writes tase_putcall (NUMERIC cols; underlingasset_call/put = TEXT)
  ▼
strategy_engine._read_live_data           snake_case cols (_STRATEGY_COLS)
  │  _calculate_condor (Decimal)
  │   • price = lastrate / MULT          ₪→points (MULT applied here, once)
  │   • _build_price_curve: traded-only anchors, interpolated leg prices
  │   • premium (points) = (SC+SP)−(LC+LP); no-arb clamp ⇒ ≥0
  │   • max_profit_ils = premium × MULT   points→₪ (MULT applied here, once)
  │   • _q2(...) → float at the return-dict boundary (Decimal ends here)
  ▼
strategy_engine._save_strategies          iron_condor_strategies (NUMERIC; 2dp floats)
  │  settle_expiry  (on expiry day)
  │   • index_close = TASE open → Yahoo open → live underlying  (see H-1)
  │   • actual_pnl_points (points), actual_pnl_ils (₪), result_status
  ▼
dashboard.load_strategies                 pd.to_numeric(...).fillna(0)  → float64
  │   • RE-CAPS premium > wing and RE-COMPUTES max_profit_ils/max_risk_ils  (H-INT-1)
  ▼
dashboard display + compute_unrealized_pnl (last-trade prices, not curve — H-INT-2)
            + build_payoff_curve (re-validates premium, re-applies MULT — duplicate)
```

### Unit / type / sign at each boundary

| Field | DB column / type | Unit | Engine writes | Dashboard reads | Match? |
|-------|------------------|------|---------------|-----------------|--------|
| strike (SC/SP/LC/LP) | `*_strike` NUMERIC | index points | `_q2(Decimal)` | `pd.to_numeric` | ✓ |
| leg price (`*_price`) | NUMERIC | **points** (lastrate/MULT) | points | ×MULT for ₪ display | ✓ (units understood) |
| `total_net_premium` | NUMERIC | **points** | points | shown as pts; ×MULT in payoff | ✓ |
| `max_profit_ils` / `max_risk_ils` | NUMERIC | **₪** | premium×MULT | displayed; **recomputed when capped** | ⚠ H-INT-1 |
| `breakeven_upper/lower` | NUMERIC | index points | SC±premium | displayed as-is | ✓ |
| `actual_pnl_ils` | NUMERIC | ₪ | points×MULT | displayed as-is | ✓ |
| `actual_pnl_points` | NUMERIC | points | points | (read on Performance) | ✓ |
| `interval_pct` | NUMERIC | percent (0.5=0.5%) | float | `f"{x:.1f}%"` | ✓ |
| `delta` (`*_delta`) | NUMERIC | TASE absolute 0–100 | round(…,4) | int display | ✓ (see M-INT-5) |
| `result_status` | TEXT | enum string | see §below | mapped (History ✓ / Perf ✗) | ⚠ M-INT-4 |
| `underlingasset_*` | **TEXT** | index points | string | parsed via float(str().replace(',','')) | ⚠ M-INT-1 |
| `lastrate_*` | NUMERIC | ₪ | from API | /MULT → points | ✓ |

`result_status` vocabulary actually emitted by `settle_expiry`:
`max_profit`, `partial_loss_put`, `partial_loss_call`, `max_loss_put`,
`max_loss_call` (NULL until settled).

---

## 2. Findings (graded)

### CRITICAL

**C-INT-1 — Two sources of truth for the multiplier (+ value conflict).**
`dashboard.py:40-49` imports `TASE_MULTIPLIER` from config **but** hard-codes
`MULTIPLIER = 50` and `WING_WIDTH = 20` in an `except ImportError` fallback. If
config ever fails to import in the Streamlit process (path/env差), the dashboard
silently prices at 50 while the engine prices at config's value — every ₪ figure
diverges with no error. Compounded by the unresolved 50-vs-100 question.
*Why it matters:* a silent ₪ divergence between what was computed/settled and
what is shown. *Repro:* run dashboard with `config.py` unimportable → MULTIPLIER
falls to 50. *Fix:* fail loudly if config import fails (no numeric fallback), and
resolve the canonical multiplier value in one place.

### HIGH

**H-INT-1 — Dashboard overwrites engine `max_profit_ils` / `max_risk_ils`.**
`dashboard.py:467-486` (`load_strategies`): when `total_net_premium > wing_max`
it re-caps premium and **recomputes** `max_profit_ils` and `max_risk_ils` from
`wing_max = max(actual_wing_put, actual_wing_call)`. For historical asymmetric
rows (e.g. the June rows: wing_put 260, wing_call 70) this DISPLAYS numbers that
differ both from what the engine stored and from what `settle_expiry` actually
used (settlement uses the **per-side** wing). *Why it matters:* the displayed
max profit/risk for a settled row can contradict the realized P&L shown beside
it. *Repro:* load any row with `total_net_premium > max(wing)`; compare card vs
stored vs `actual_pnl_ils`. *Fix:* display engine values; do not recompute in the
view layer (single source of truth). Needs sign-off (Question #2).

**H-INT-2 — Unrealized P&L uses raw last-trade prices, not the engine curve.**
`dashboard.py:946-981` (`compute_unrealized_pnl`) prices current legs from
`_fetch_option_prices_for_expiry` (raw `lastrate`/MULT, capped at
`PRICE_SANITY_MAX_PTS`). The **entry** premium it subtracts was produced by the
engine's new curve pricing (no debit), but the **current** premium uses the very
stale-last-trade method the engine fix removed. Mixing two pricing methods can
yield a misleading live P&L (including pseudo-debit swings on illiquid legs).
*Why it matters:* the "Unrealized P&L (LIVE)" number is not on the same basis as
entry. *Repro:* open position whose long legs didn't trade today → current_premium
built from stale longs. *Fix:* price current legs from the same traded-only curve,
or label the estimate's basis. Needs sign-off (Question #3).

**H-INT-3 — Settlement falls back to a Yahoo proxy, violating the stated invariant.**
Invariant: *settlement = official TASE opening price, not a Yahoo proxy.*
`settle_expiry` (`strategy_engine.py:861-866` → `_fetch_settlement_price`
`:159-174`) uses `tase_open_price` when passed, else **Yahoo `regularMarketOpen`**,
else live `underlingasset`. When `main.py` does not supply the official open, the
settled P&L is based on a Yahoo proxy — silently. *Why it matters:* the settlement
print is the single most important number; a proxy can differ from the official
opening auction. *Repro:* call `settle_expiry(exp)` with `tase_open_price=0` →
Yahoo open used. *Fix:* if the official open is unavailable, do not settle on a
proxy — defer + alert. Needs sign-off (Question #4).

### MEDIUM

**M-INT-1 — `underlingasset_call/put` typed TEXT, not NUMERIC** (`supabase_setup.sql:42,60`).
Every consumer string-parses it (`float(str(v).replace(",",""))` in
`_get_base_index`, `get_live_index`). Works, but it is the one price-like field
that bypasses NUMERIC validation and invites silent parse-to-0 on a bad value.

**M-INT-2 — Triple implementation of the condor payoff formula.** The same
points→₪ payoff/branch logic exists in `settle_expiry` (engine),
`compute_unrealized_pnl` expiry_proxy branch (dashboard), and `build_payoff_curve`
(dashboard). Three copies that must stay byte-identical to avoid the chart /
live-P&L / settlement disagreeing. See §3.

**M-INT-3 — `_validate_premium` cap duplicated in three places.** Engine
`_calculate_condor` (cap to wing), dashboard `load_strategies` (cap+recompute),
dashboard `_validate_premium`/`build_payoff_curve` (cap for the chart). After the
engine fix, premium is already ≤ wing at write time, so the dashboard caps are
largely dead for new rows but still fire on historical rows — producing H-INT-1.

**M-INT-4 — Performance result-status chart uses the wrong vocabulary.**
`dashboard.py:1673-1681` maps `{max_profit, partial, max_loss, zero}`, but the
engine emits `partial_loss_put/call` and `max_loss_put/call`. Unmapped statuses
fall back to the raw English string (shown in a Hebrew chart) and to grey
(`C_DIM`) — so losses are not coloured red on the distribution chart. The History
badge map (`:2915`) is correct; only the Performance chart is wrong. *Fix:* use the
engine vocabulary (or collapse `*_put/*_call` into put/call buckets deliberately).

**M-INT-5 — Decimal precision ends at the engine boundary (by design — confirm).**
`_q2` converts every money figure to a 2dp float before storage; DB is NUMERIC;
dashboard reads float64. So no Decimal survives past the engine. This is intended
(quantize-then-store), but it means "Decimal hygiene" is engine-internal only —
any future consumer doing further arithmetic on the stored 2dp floats has no
exactness guarantee. Document, not necessarily fix.

### LOW

**L-INT-1 — Dashboard constants duplicate config** (`MULTIPLIER`, `WING_WIDTH`,
`PRICE_SANITY_MAX_PTS`, `INTERVALS` fallback) — drift risk if config changes and
the fallback path is ever taken (see C-INT-1).

**L-INT-2 — `db.upsert_items` silently drops any API field not in `VALID_COLUMNS`**
(`database.py:121-124`). Intended whitelist, but a renamed/added TASE field
vanishes with no warning.

**L-INT-3 — Missed-window empty display is honest but unlabelled.** If the Monday
12:00 strategy window is missed, `iron_condor_strategies` has no rows for the week;
`load_strategies` returns empty → empty-state card (good, not misleading). The
"week pulse" KPIs then show 0 ₪ / 0% — truthful but indistinguishable from a real
flat week. Minor.

---

## 3. Duplicate / conflicting calculations (engine ↔ dashboard)

| Quantity | Engine (authoritative) | Dashboard re-implementation | Risk |
|----------|------------------------|------------------------------|------|
| Premium cap to wing | `_calculate_condor` | `load_strategies:475-478`, `_validate_premium` | M-INT-3 |
| `max_profit_ils` / `max_risk_ils` | `_calculate_condor:582-583` | `load_strategies:480-486` (overwrites) | **H-INT-1** |
| Condor P&L vs index (payoff) | `settle_expiry:858-872` | `compute_unrealized_pnl:971-981` + `build_payoff_curve:996-1020` | **M-INT-2** (3 copies) |
| points→₪ (× multiplier) | once, engine | re-applied for display/live/sandbox | OK *if* same MULT (C-INT-1) |
| Breakevens | `_calculate_condor` (stored) | not recomputed (read-only) ✓ | none |
| Settled `actual_pnl_ils` | `settle_expiry` (stored) | displayed as-is ✓ | none |
| Sandbox max profit/loss/BE | n/a (user-built) | `sandbox_compute_metrics` | OK (separate domain) |

**Headline:** `max_profit_ils`/`max_risk_ils` and the condor payoff formula each
exist in ≥2 places. Any future change to the engine formula must be mirrored in
the dashboard or the displayed/charted numbers will silently diverge from the
settled reality.

---

## 4. Smoke results

| Check | Result |
|-------|--------|
| Import all backend modules (config, supabase_client, option_schema, strategy_engine, database, tase_api, telegram_bot, health_server, browser, main) | ✅ all import clean |
| `dashboard.py` parses (AST) | ✅ (not imported — Streamlit/network side effects) |
| Engine test suite `tests/` | ✅ 45 passed |
| Legacy `test_strategy_engine.py` | ✅ 10 passed |
| End-to-end cross-process (TASE→DB→dashboard) | ⚠ **not run** — requires live Supabase + Streamlit; flow traced statically instead |

No crashes surfaced on fixture-level engine/validation paths. The realistic
failure paths identified are documented above (H-INT-2 stale-price live P&L,
H-INT-3 Yahoo settlement fallback, C-INT-1 multiplier fallback).

---

## 5. Questions for human

1. **Multiplier = 50 or 100?** Code and an earlier instruction say 50; this
   mandate's invariant says 100. Canonical value? (Blocks all ₪ correctness.)
2. **H-INT-1:** Should the dashboard stop recomputing `max_profit_ils`/
   `max_risk_ils` and display the engine's stored values verbatim?
3. **H-INT-2:** Should live unrealized P&L use the engine's traded-only curve
   pricing (consistent with entry), or is a last-trade estimate acceptable if
   labelled?
4. **H-INT-3:** When the official TASE opening price is unavailable at settlement,
   defer + alert (never settle on Yahoo), or keep the Yahoo fallback?
5. **M-INT-4:** On the Performance distribution chart, keep five buckets
   (`max_profit`, `partial_loss_put/call`, `max_loss_put/call`) or collapse to
   profit / partial / max-loss?
6. Confirm `underlingasset_*` should remain TEXT (M-INT-1), or be migrated to
   NUMERIC for validation parity.
