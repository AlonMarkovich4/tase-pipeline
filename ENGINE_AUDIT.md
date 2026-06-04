# ENGINE_AUDIT.md — Strategy Engine & Validation Audit

> Audit date: 2026-06-04
> Scope: `strategy_engine.py`, `option_schema.py` (+ supporting `config.py`).
> Method: audit-first. Behaviour mapped and locked by characterization tests
> **before** any fix. No behaviour changed in Step 1.
> Baseline coverage (pre-audit): `strategy_engine.py` 32%, `option_schema.py` 0%.
> After Step 1 characterization suite: `option_schema.py` **91%**,
> `strategy_engine.py` 33% (pure money-math fully covered; the remaining
> uncovered lines are network/I/O wrappers — see *Testability* below).
> 42 tests pass; legacy `test_strategy_engine.py` still green.

---

## How to run the tests

```bash
pip install -r requirements-dev.txt
python3 -m pytest tests/ -v
python3 -m pytest tests/ --cov=strategy_engine --cov=option_schema --cov-report=term-missing
```

The legacy `test_strategy_engine.py` (hand-run script) is preserved and still
passes; the new suite under `tests/` supersedes and extends it.

---

## Severity legend

- **Critical** — produces a wrong money number that can be acted on, silently.
- **High** — wrong number in a reachable edge case, or a correctness landmine.
- **Medium** — degraded correctness / hygiene that can mask bad data.
- **Low** — cosmetic, labelling, or defensive-depth nit.

---

## Findings

### C-1 (Critical) — Strike-order "repair" desyncs strikes from their prices
**Location:** `strategy_engine.py:419-432` (`_calculate_condor`).

When the matched short put ≥ short call, the code overwrites the **strikes**
with synthetic `BASE ± offset`:
```python
if sp_strike >= sc_strike:
    sp_strike = BASE - offset
    sc_strike = BASE + offset
if lp_strike >= sp_strike:
    lp_strike = sp_strike - WING
if lc_strike <= sc_strike:
    lc_strike = sc_strike + WING
```
But `sc_price / sp_price / lc_price / lp_price` still hold the prices of the
**originally matched** options. Net premium, breakevens, max profit/loss and
the stored `*_strike` fields then describe a position that was never priced:
the strikes are synthetic, the prices belong to different strikes.

**Why it matters:** every downstream number (premium, BE, P&L, the strike
fields shown to the user and used at settlement) is internally inconsistent.
This is the most dangerous class — a quiet wrong number in the money path.

**Repro:** feed a chain where the closest call to `SC_target` lands below the
closest put to `SP_target` (sparse/!inverted chain). Strikes get rewritten,
prices do not.

**Proposed fix (needs human sign-off on policy):** either (a) **reject** the
interval with a `premium_flag="unbuildable"` and zeroed metrics, or
(b) re-match prices at the synthetic strikes. Do **not** keep mismatched
strike/price pairs. See *Questions for human* #4.

---

### C-2 (Critical) — `max_loss_*` can report a **profit** when premium ≥ wing
**Location:** `strategy_engine.py:867-872` (`settle_expiry`).

```python
elif index_close_d < lp_d:
    pnl_points_d = net_premium_d - wing_put_d      # max_loss_put
else:
    pnl_points_d = net_premium_d - wing_call_d     # max_loss_call
```
If `net_premium_d > wing_side_d` the result is **positive** while `status`
is `max_loss_*`. With the asymmetric wings that the sparse chain produced
(e.g. real 2026-06-02: wing_call=10, premium=9.86 → max_loss_call = −0.14;
had premium been 11 → **+1.0 pt profit labelled max_loss_call**).

It also breaks the stated invariant *settlement P&L ∈ [−max_loss, +max_profit]*:
the per-side max loss can be smaller than `max_risk` (which uses `wing_max`),
so a "max loss" outcome can exceed the reported max profit envelope sign.

**Why it matters:** P&L and result_status disagree; weekly win-rate and
utilisation stats consume both. The wing-width fix (already merged) prevents
*new* asymmetric condors, but settlement of any historical/edge row is still
exposed, and `net_premium > wing` is reachable independent of wing symmetry.

**Repro:** settle a row with `total_net_premium=11, actual_wing_call=10`,
index above `long_call_strike`.

**Proposed fix:** clamp per-side P&L so `max_loss_*` ≤ 0
(`pnl = min(net_premium − wing_side, 0)` is wrong — rather, cap premium to the
**side** wing when computing that side's loss), and/or assert the invariant.
Needs human sign-off (rounding/clamp policy) — *Questions for human* #2.

---

### H-1 (High) — Negative-premium (debit) condors emit nonsensical P&L numbers
**Location:** `strategy_engine.py:456-462, 500-505`.

When `raw_net_premium < 0` the engine keeps the negative value, flags
`negative_premium`, then computes:
- `max_profit_ils = net_premium × 50` → **negative "max profit"**
- `max_risk_ils  = wing×50 − max_profit` → **risk > wing notional**
- `rr_ratio = 0.0` (guarded)

The flag is correct but the derived fields are garbage and are still stored
and displayed.

**Why it matters:** a credit Iron Condor with negative net premium is a data
error (inverted/stale prices). Showing a negative "max profit" and an inflated
"max risk" is misleading. Question for human: reject outright or zero the
metrics? — *Questions for human* #3.

**Repro:** chain where long legs price higher than short legs.

---

### H-2 (High) — `_clean_numeric` (engine) accepts `inf` / `nan`
**Location:** `strategy_engine.py:57-69`.

`_clean_numeric("inf")` → `inf`, `_clean_numeric("nan")` → `nan`.
`Decimal(str(float("nan")))` → `Decimal("NaN")`; `Decimal("inf")` →
`Decimal("Infinity")`. These poison premium / P&L silently in the engine,
which reads DB values through `_clean_numeric` / `_to_decimal`.

**Correction after verification:** the **option_schema** layer is *not*
affected — a NaN `LastRate` is **rejected** there because
`Decimal('NaN') < 0` raises `InvalidOperation` (caught → row rejected), and
`Decimal('Infinity') > _RATE_MAX` is `True` → rejected by the ceiling. So the
validation gate is safe for non-finite; the **engine entry path** is not.

**Why it matters:** the engine reads settlement strategies and live rows
through `_clean_numeric`; a non-finite that bypasses validation (e.g. a value
introduced in the DB, or a future non-validated path) propagates as NaN/Inf
with no log.

**Repro:** `se._clean_numeric("nan")` → `nan` (locked by
`test_clean_numeric_accepts_nonfinite_BUG`).

**Proposed fix:** reject non-finite in `_clean_numeric`
(`if not math.isfinite(f): return 0.0`).

---

### H-4 (High) — Zero-price quality gate silently misses string `"0"` prices
**Location:** `option_schema.py:298-328` (`_check_zero_prices`).

```python
if (not item.get("LastRate_Call") or item.get("LastRate_Call") == 0)
and (not item.get("LastRate_Put")  or item.get("LastRate_Put")  == 0)
```
Raw TASE items deliver prices as **strings**. `not "0"` is `False` (a non-empty
string is truthy) and `"0" == 0` is `False`. So a row priced `"0"` / `"0"` is
**not** counted as zero. The `ALL_PRICES_ZERO` (CRITICAL) and
`MAJORITY_PRICES_ZERO` gates therefore never fire on a real dead-feed snapshot
where prices are string zeros — exactly the case they exist to catch.

**Verified:** with int `0` the gate fires (`has_critical=True`); with string
`"0"` it does not (`has_critical=False`).

**Why it matters:** the headline data-quality protection against a dead feed is
inert against the most common representation of "no price".

**Repro:** `validate_items([{... "LastRate_Call":"0","LastRate_Put":"0" ...}]×6)`
→ no `ALL_PRICES_ZERO` warning. (Locked by
`test_zero_price_gate_misses_string_zero_BUG`.)

**Proposed fix:** normalise via `_parse_number` before the zero test
(`v = _parse_number(item.get("LastRate_Call")); v is None or v == 0`).

---

### H-3 (High) — `BaseRate` is coerced but never range-/sign-validated
**Location:** `option_schema.py:121-123, 160-201`.

`LastRate_Call/Put` get negative + ceiling checks; `BaseRate_Call/Put` get
neither. BaseRate is the **Tier-3 pricing fallback** in
`_find_closest_option`, so a corrupt baserate (negative, or absurdly large)
flows straight into premium when lastrate is absent. The `PRICE_SANITY_MAX_PTS`
cap in the engine catches *large* baserate, but not negative baserate.

**Why it matters:** the validation gate claims to protect pricing inputs but
leaves a priced fallback path unchecked.

**Proposed fix:** apply the same `< 0` and `> _RATE_MAX` checks to BaseRate.

---

### M-1 (Medium) — Settlement wing fallback trusts a negative stored wing
**Location:** `strategy_engine.py:843-848`.

```python
wing_put_d = (_to_decimal(s.get("actual_wing_put")) or (sp_d - lp_d) or WING_D)
```
`Decimal('0')` is falsy → falls through correctly. But a **negative** stored
wing (`Decimal('-5')`, from inverted strikes in the DB) is *truthy* and is used
as-is, producing a wrong max-loss. Same for `wing_call_d`.

**Proposed fix:** guard `if wing <= 0: fall back`.

---

### M-2 (Medium) — `max_risk` uses `wing_max`, settlement uses per-side wing
**Location:** `strategy_engine.py:502` vs `857-872`.

`max_risk_ils` is computed from `actual_wing_max` (the wider wing), while
settlement uses the **side-specific** wing. For asymmetric condors the reported
`max_risk` overstates the loss achievable on the narrow side. Not wrong as a
"worst case", but the two code paths use different definitions of "max loss",
which is a consistency trap (and interacts with C-2).

**Proposed fix:** document the intended definition; consider storing both
`max_risk_put` and `max_risk_call`, or assert `|settlement P&L| ≤ max_risk`.

---

### M-3 (Medium) — `delta` sign/scale convention is enforced asymmetrically
**Location:** `option_schema.py:177-200`; `strategy_engine.py:211, 546-549`.

Schema enforces `0 ≤ delta ≤ 100` for **both** sides. If TASE ever returns a
signed put delta (negative, the standard quant convention), **every put row is
rejected**. The engine stores raw delta and `_get_base_index` assumes
`0 < delta < 100`. The legacy test fixtures use fractional/signed deltas
(`0.3`, `-0.3`), disagreeing with the real integer-0..100 contract.

**Why it matters:** a TASE-side convention change silently drops all rows
(CRITICAL feed outage presented as validation rejections). Needs human
confirmation of the real contract — *Questions for human* #5.

---

### M-4 (Medium) — Whole-batch quality checks read raw camelCase, engine reads snake_case
**Location:** `option_schema.py:298-348` vs `strategy_engine.py` columns.

`_check_zero_prices` / `_check_strike_diversity` key on `LastRate_Call`,
`ExpirationPrice_Call` (raw API names). The engine reads `lastrate_call`,
`expirationprice_call` (DB names). This is correct *by stage* (validation runs
pre-DB on raw items), but there is no test locking the contract, so a future
rename on either side would silently disable the gate.

**Proposed fix:** characterization test pinning both key spaces.

---

### L-1 (Low) — Boundary labels say "partial" at exact wing strikes
**Location:** `strategy_engine.py:861-872`.

At `index == long_put_strike` the branch `lp ≤ index < sp` labels
`partial_loss_put` though P&L equals the full max loss. Math is correct; label
is imprecise. Cosmetic.

---

### L-2 (Low) — DTE may be negative if `_calculate_condor` is called directly
**Location:** `strategy_engine.py:514-519`.

`run_strategy` filters `expiry > trigger`, so in production DTE ≥ 1. Called
directly (tests, future reuse) a past expiry yields negative DTE, stored
without complaint.

---

### L-3 (Low) — Tie-break in `_find_closest_option` is "first row wins", not "nearest then lowest"
**Location:** `strategy_engine.py:329-348` (strict `diff < best_diff`).

On an exact distance tie the first row in DB-id order wins. Deterministic given
DB order, but not a documented financial rule. The wing-width guard handles the
dangerous long-leg case; documenting for completeness.

---

## Invariants verified (and now locked by tests)

| Invariant | Status |
|-----------|--------|
| `net_premium = (SC+SP) − (LC+LP)` | ✓ holds |
| `max_profit = net_premium × 50` | ✓ holds (credit case) |
| `max_risk = wing_max × 50 − max_profit` | ✓ holds (see M-2 nuance) |
| `BE_upper = SC + premium`, `BE_lower = SP − premium` | ✓ holds |
| `long_put < short_put < short_call < long_call` | ⚠ violated by C-1 path |
| settlement P&L ∈ [−max_loss, +max_profit] | ⚠ violated by C-2 path |
| `result_status` consistent with index vs strikes | ⚠ C-2 (label vs sign) |
| R:R zero-division guarded | ✓ holds |
| Decimal in money path | ✓ mostly (entry via `_clean_numeric` float — H-2) |

---

## Testability note

`strategy_engine.py` line coverage is 33% because the money math
(`_calculate_condor`, `_find_closest_option`, the settlement formula) is
tightly coupled to network I/O wrappers (`_read_live_data`, `_fetch_yahoo_*`,
`_save_strategies`, `run_strategy`, the `settle_expiry` DB loop,
`get_weekly_stats`). The pure formulas ARE fully exercised — the settlement
math is tested via a faithful in-test mirror (`_settle_one`) because the real
function interleaves the calculation with `httpx.patch` calls per row.

**Recommendation (future, not this pass):** extract the per-strategy
settlement calculation into a pure `_settle_pnl(strategy, index_close) ->
(pnl_pts, status)` function so it can be tested directly and reused by the
dashboard's duplicate logic. This would also let C-2's fix be unit-locked
against the real function rather than a mirror.

---

## Questions for human (do NOT fix until answered)

1. **Contract multiplier.** Code uses `TASE_MULTIPLIER = 50`. TA-35 weekly
   options are widely quoted at **₪100 per index point**, monthlies at ₪100 as
   well; ₪50 was an older convention. Is 50 correct for the instruments you
   trade, or should it be 100? Every ₪ figure scales linearly with this.

2. **Settlement clamp (C-2).** When `net_premium > wing_side`, should the
   per-side P&L be clamped so a `max_loss_*` outcome can never be positive, and
   should we assert `settlement P&L ∈ [−max_risk, +max_profit]` (raising/logging
   on violation)?

3. **Negative-premium policy (H-1).** When the computed net premium is a debit
   (< 0): reject the interval (store zeroed metrics + flag), or keep the raw
   negative numbers as today?

4. **Strike-order repair policy (C-1).** When matched strikes are inverted:
   reject the interval, or re-price at synthetic strikes? (Keeping mismatched
   strike/price pairs is not acceptable — confirm which replacement.)

5. **Delta convention (M-3).** Does TASE return delta as an unsigned integer
   0–100 for both call and put? If put delta can be negative, the schema must
   allow it (currently rejects → drops all puts).

6. **Settlement convention.** Confirmed assumption: TASE options settle on the
   **opening** price of expiry day (`regularMarketOpen`), and the index is the
   TA-35 spot. Correct?

7. **Rounding policy.** Money is quantised to 2dp with `ROUND_HALF_EVEN`
   (banker's). R:R to 4dp. Premium stored at 2dp then re-used for BE. Is
   banker's rounding the intended convention for reporting ₪, or should it be
   `ROUND_HALF_UP`?
