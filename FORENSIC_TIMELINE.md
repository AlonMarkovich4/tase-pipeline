# FORENSIC_TIMELINE.md — "Where did we fall?"

> Forensic reconstruction of how the live pipeline broke and was repaired.
> Built from git history + observed data evidence (Supabase history table,
> Render logs, and `diag_raw_response.json` raw API captures). Dates are commit
> dates (Asia/Jerusalem). Documentation only — no code changed by this file.

---

## TL;DR

- **Inflection point: `d87e0f0` (2026-06-01) "Harden pipeline for production".**
  It introduced the validation gate (`option_schema`). The gate read option
  fields in **CamelCase** (`LastRate_Call`) while TASE returns **lowercase**
  suffixes (`LastRate_call`). From 2026-06-01 the gate was blind → it flagged
  `ALL_PRICES_ZERO` / `DUPLICATE_STRIKES` every cycle → every expiry was
  skipped. The same commit also added a (correct) `STALE_TRADE_DATE` check.
- **Effect:** the live `tase_putcall` table stopped updating; `tase_putcall_history`
  stops at 2026-05-29; the June strategies were built from stale/degraded data
  → the debit / asymmetric‑wing / duplicate‑interval garbage that was reported.
- **Repair (2026-06-08):** forward-fix, not revert — make the gate read TASE's
  real keys (case-insensitive) and correct three downstream rules, while
  keeping the protections. Reverting would restore data flow but reintroduce
  the original unvalidated garbage and lose the staleness protection.
- **Still open (not a regression):** TASE's API serves the **previous trading
  day's EOD** in the morning (`curr_Hour="סוף יום"`, `TradeDate`=yesterday);
  today's intraday data (`dType=1`) is empty until later. `STALE_TRADE_DATE`
  correctly flags this. Decision pending (afternoon re-probe).

---

## Timeline of code vs. data

| Date | Commit / event | Effect on the live pipeline |
|------|----------------|------------------------------|
| 2026-05-25 | `812079a` production hardening (health, telegram, DB) | running |
| 2026-05-27 | `563c980` config.py + dashboard rewrite + first data validation | running; data flowing |
| ≤ 2026-05-29 (Fri) | last trading day with stored data | **`tase_putcall_history` has data through 05-29** |
| 2026-05-30/31 | weekend (Sat; Sun closed under Mon–Fri calendar) | no trading |
| **2026-06-01 (Mon)** | **`d87e0f0` "Harden pipeline … validation"** — adds `option_schema` gate (CamelCase field reads) + `STALE_TRADE_DATE` | **🔴 gate goes blind to TASE's lowercase keys → rejects every expiry from here on** |
| 2026-06-02 … 06-05 | weekly strategies settle on degraded data | the debit / asymmetric‑wing / duplicate‑interval outputs that were reported |
| 2026-06-08 (Mon) | live incident surfaces (deploy rebuild) | crash-loop + alert flood expose the state |

**Cross-check:** history ends 05-29; the gate hardened 06-01; the next trading
day (06-01) is exactly where storage stops. The June garbage and the
history-stop have a **single common cause** — the blind gate from `d87e0f0`.

---

## The chain of bugs found & fixed on 2026-06-08

| # | Bug | Origin | Fix commit | Status |
|---|-----|--------|-----------|--------|
| 1 | Worker crash-loop `ModuleNotFoundError: browser` | Dockerfile `COPY` listed 5 of the modules; modular split added more | `3e4089e` (`COPY *.py`) | ✅ deployed |
| 2 | Telegram flood (≈15 msgs/cycle) | data-quality alerts had no throttle | `51fffa2` (1/code/day, persisted) | ✅ deployed |
| 3 | **Validation blind to TASE casing** (the d87e0f0 bug) | `option_schema` read `_Call`; TASE sends `_call` | `a5fc7c5` (case-insensitive read + model key-normaliser) | ✅ deployed |
| 4 | Rate ceiling rejected whole rows | `_RATE_MAX` (near-money ceiling) raised on any leg, incl. legit deep-ITM → ITEMS_REJECTED | `99a9871` (leg-level filter; engine-band classification) | ✅ deployed |
| 5 | Negative put delta rejected (audit M-3) | model required `0≤delta≤100` for puts; TASE put delta is negative | `da1591e` (Δput ∈ [-100,0], signed) | ✅ deployed |

Bugs 3→4→5 were a **chain**: fixing the casing (3) let the model finally READ
values, which exposed the ceiling over-rejection (4); fixing that exposed the
negative-put-delta rejection (5). After all three, the captured snapshot parses
30/31 rows (only a `strike=1` header row dropped), no parsing-driven CRITICAL.

---

## Why we did NOT revert

| Option | Outcome |
|--------|---------|
| Revert to **before `d87e0f0`** | Data flows again, BUT: no validation → the original debit/asymmetric/duplicate garbage returns; **no STALE check → trades on yesterday's data silently**; loses ~6 weeks of dashboard + engine work. |
| Revert to **any recent commit** | Same casing rejection (still reads `_Call`) → rejects current TASE data → no gain. |
| **Forward-fix (chosen)** | Gate reads TASE's real keys, keeps every protection, corrects the ceiling & delta rules. Data parses; garbage stays out. |

The "it worked before" state was partly an **illusion of correctness**: pre-gate
the pipeline accepted whatever it got (including stale/garbage), which is the
source of the very problems first reported.

---

## Still open (source-side, NOT a code regression)

TASE's `putvscall` API in the morning returns the **previous trading day's
EOD**:
- `TradeDate` = yesterday; `curr_Hour` = `"סוף יום"` (end of day) on every row.
- Probed param variants: `dType=2` → yesterday EOD (populated); `dType=1`
  ("today") → **0 rows** at ~10:00.
- Confirmed on both the API (probe) and the TASE website ("נכון ל-08/06").

`STALE_TRADE_DATE` correctly refuses to build strategies on yesterday's data.
No code version can produce data TASE hasn't published. **Open decision:** does
`dType=1` populate intraday (→ a timing fix: run later / switch param), or is it
a T-1 EOD feed (→ decide whether trading on prior-day EOD is acceptable)?
Resolve via an afternoon re-probe of `dType=1`.

---

## Verification status

- Fixes 3/4/5 verified against the real `diag_raw_response.json` fixture and a
  synthetic full chain; 68 tests pass; legacy engine script green.
- **Not yet verified** against a live *traded* snapshot (`DealsNo>0` intraday),
  because none has been available during the incident window — every capture so
  far is the previous day's EOD.
