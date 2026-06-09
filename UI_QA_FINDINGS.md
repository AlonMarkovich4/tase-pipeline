# UI_QA_FINDINGS.md — Dashboard pre-release review

> Senior-QA pass over `dashboard.py` (2994 lines) from a real-user perspective.
> Scope: interface behaviour, edge states, usability — NOT data correctness
> (verified separately). Review only — nothing fixed. Severity: Critical / High
> / Medium / Low. Line numbers are at time of review (2026-06-09).
>
> Cross-layer contract VERIFIED against the live DB: the engine writes every
> leg-price / leg-delta column the dashboard reads (`short_call_price`,
> `short_put_delta`, …) — so legs table, recommendation score, and the demo
> bridge all have real values. No missing-column class of bugs.
>
> Validity filter VERIFIED working end-to-end: `load_strategies` drops
> `is_valid = false`, so the 06-01 garbage batch is excluded from every screen,
> the sidebar counts, AND the week selector (the W23 garbage week is not even
> navigable). Mandate item #6 ✅.
>
> The known loose threads (06-12 duplicate intervals, spot-source drift, Sunday
> expiry, recovery/alert noise) are already documented in FORENSIC_TIMELINE.md;
> where they surface in the UI they are noted as "already documented" and skipped.

---

## CRITICAL

### C1 — Option Chain tab crashes (NameError) when there is no option data
- **Where:** Demo Trading → tab "⛓️ שרשרת אופציות". `dashboard.py:2298–2306`.
- **What breaks:** the `else:` at line 2298 wraps ONLY line 2299
  (`chain_header = st.columns(...)`). Lines 2300+ (`with chain_header[1]:` …)
  are dedented OUT of the else. When `get_available_expiries()` returns empty,
  the `if not expiry_dates:` branch shows the empty-state, the else is skipped,
  `chain_header` is never assigned, and `with chain_header[1]:` raises
  **`NameError: name 'chain_header' is not defined`**.
- **Condition:** empty option data — empty DB, before the first scrape of a
  fresh deploy, or Supabase/network down. Verified by indentation inspection
  (else body = 1 line; rest at indent 8).
- **User experience:** the "אין נתוני אופציות זמינים" card renders and is
  immediately followed by a red Streamlit traceback. The tab is unusable in
  exactly the state the empty-state message was meant to handle gracefully.

---

## HIGH

### H1 — Demo auto-settlement can permanently close a trade at a wrong price, silently
- **Where:** Demo Trading auto-settlement block. `dashboard.py:1998–2004`.
- **What breaks:** for an expired open demo trade it tries the strategy's
  `actual_index_close`; if that's missing it falls back to `live_index`, and if
  that's also 0 it falls back to **`entry_index`** (line 1999). It then closes
  the trade and adjusts the balance irreversibly (`close_demo_trade` +
  `_update_demo_balance`), and marks it in `settled_ids` so it never re-settles.
- **Condition:** a demo trade expires on a day when settlement hasn't run yet
  AND there's no live index (market closed / Yahoo+Supabase both empty) — a
  realistic weekend/holiday visit.
- **User experience:** the demo trade is settled at the ENTRY index (P&L based
  on "price never moved"), the balance changes, and it cannot be undone or
  re-settled at the true price. Silent — only a dialog showing the (wrong)
  number. Corrupts the demo track record.

---

## MEDIUM

### M1 — History shows expired-but-unsettled strategies as ₪0 "settled" (inconsistent with Performance)
- **Where:** global prep `dashboard.py:1538–1539`; Performance `1588`; History `2806+`.
- **What breaks:** `_is_expired` rows (expiry past, never settled) are forced
  `_is_settled = True`. Performance excludes them (`actual_index_close > 0`), but
  History does NOT — they appear in the History list with `actual_pnl_ils = 0`,
  empty result badge ("—"), and no settlement zone.
- **Condition:** settlement failed/skipped for an expiry (e.g. the 8 unsettled
  06-10 condors if tomorrow's settlement fails).
- **User experience:** a strategy that was never settled looks like a settled
  break-even (₪0). Two screens disagree on whether it "counts". Misleading.

### M2 — Sandbox "delete leg" uses positional widget keys → value bleed on middle delete
- **Where:** Demo → Strategy Builder. `dashboard.py:2226–2262` (keys
  `sb_lt_{idx}`, `sb_ls_{idx}`, …).
- **What breaks:** leg-editor widgets are keyed by list position. Deleting a
  middle leg (`🗑️`, the `continue` at 2256–2257) shortens the list; on rerun the
  remaining legs reindex, so Streamlit's position-keyed widget state can carry a
  leg's Type/Action/Strike/Premium onto the wrong row.
- **Condition:** delete a non-last leg from a multi-leg custom strategy.
- **User experience:** after deleting one leg, another leg's values may appear
  changed. **Needs manual test** (open Demo, load Iron Condor, delete the 2nd
  leg, observe whether legs 3–4 keep their own values).

### M3 — Success toast discarded by immediate `st.rerun()`
- **Where:** 4 sites — Home "שגר לדמו" `1850–1851`; Demo execute `2174–2178`;
  Demo close `2596–2598`; Open Positions "שגר לדמו" `2795–2796`.
- **What breaks:** `st.success(...)` is immediately followed by `st.rerun()`,
  which re-runs the script before the toast is shown.
- **User experience:** the green confirmation flashes for a frame or not at all;
  the user isn't sure the action succeeded (only indirect cues — e.g. the button
  going disabled — confirm it). Low-risk but affects trust in every "send to
  demo" / "execute" action.

---

## LOW

### L1 — Mixed delta sign in the legs table has no legend
- `render_legs_table` (`1198`) shows call deltas positive (e.g. 20) and put
  deltas negative (e.g. -2) in one "Delta" column. Correct convention, but with
  no legend a user may read the put's "-2" as an error. Cosmetic.

### L2 — Degenerate zero-premium condor shows Max Profit ₪0 / "1:0.0" with no hint
- `render_expiry_metrics` (`1226–1246`). A far-OTM interval whose credit rounds
  to ~0 displays Max Profit ₪0 and RR "1:0.0". Valid but not tradeable; only
  flagged if `premium_flag == "negative_premium"`, which a 0 (not negative)
  premium doesn't trigger. The 4.0% interval can land here. Minor confusion.

### L3 — "At Risk Now" scans all active weeks, not just the current one
- Home `1873` iterates `df[~_is_settled]` across all weeks. Currently masked
  because the is_valid filter leaves only the current week active, but if two
  weeks are ever active at once, stale-week positions would appear under "בסיכון
  עכשיו". Latent.

### L4 — "Add to graph" strike index assumes 1:1 strikes↔rows
- Tab 2 `2432–2435`: `index=len(display_df)//2` against `display_df["strike"].unique()`.
  Safe while strikes are unique per snapshot (they are); would raise an index
  error only if duplicate strikes ever appear in one snapshot. Very low prob.

---

## Empty-state coverage summary (per screen)

| Screen | No data | Partial / no-live-index | Verdict |
|--------|---------|--------------------------|---------|
| 📈 Performance | graceful empty-state (`1592`) | n/a | ✅ |
| 🏠 Home | rec empty-state (`1860`); at-risk caption (`1910`) | handled | ✅ |
| 🕹️ Demo · Builder | empty-state (`2184`); no-premium warning (`2182`) | ok | ✅ |
| 🕹️ Demo · Chain | **CRASHES (C1)** | — | ❌ |
| 🕹️ Demo · Portfolio | empty-state (`2600`) | ₪0 cards if no live index | ✅ (minor) |
| 🔵 Open Positions | empty-state (`2717`); no-strategies warning (`2982`) | PROXY label when no live px (`2771`) ✅ | ✅ |
| 📜 History | empty-state (`2807`) | M1 (expired-unsettled = ₪0) | ⚠️ |

---

## Recommended fix order (for discussion — nothing changed yet)
1. **C1** — one-line indentation fix (the whole chain block under the `else`).
   Highest impact, smallest change, hides a visible crash.
2. **H1** — don't auto-settle a demo trade when no real settlement price exists;
   defer instead of falling back to entry index.
3. **M1** — make History exclude (or clearly mark) expired-unsettled rows, to
   match Performance.
4. **M3** — drop the toast-then-rerun pattern (or use `st.toast`).
5. **M2** — manual-test the leg-delete; if confirmed, key widgets by leg id.
6. **L1–L4** — cosmetic / latent, batch later.
