"""
fix_historical_premiums.py — One-time migration script.

Fixes historical iron_condor_strategies rows where premiums were stored
in ₪/contract instead of index points.  Divides all premium fields by
TASE_MULTIPLIER (50) and recalculates derived fields.

Safe to run multiple times — skips rows that look already converted
(total_net_premium < 50, a reasonable upper bound for points).

Usage:
    python fix_historical_premiums.py          # dry-run (shows changes)
    python fix_historical_premiums.py --apply  # actually update Supabase
"""

import os
import sys
import json
import httpx

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
MULTIPLIER = 50

# Threshold: if total_net_premium is already below this,
# the row was likely already converted — skip it.
ALREADY_CONVERTED_THRESHOLD = 50


def headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


def fetch_all_strategies():
    """Read all rows from iron_condor_strategies."""
    rows = []
    batch = 1000
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/iron_condor_strategies"
            f"?select=*&order=id&limit={batch}&offset={offset}"
        )
        r = httpx.get(url, headers=headers(), timeout=30)
        if r.status_code not in (200, 206):
            print(f"ERROR reading: HTTP {r.status_code}")
            sys.exit(1)
        chunk = r.json()
        if not chunk:
            break
        rows.extend(chunk)
        if len(chunk) < batch:
            break
        offset += batch
    return rows


def needs_fix(row) -> bool:
    """Check if this row still has unconverted (₪) premiums."""
    net = abs(float(row.get("total_net_premium") or 0))
    # If net premium > threshold, it's still in ₪ and needs conversion
    return net > ALREADY_CONVERTED_THRESHOLD


def fix_row(row) -> dict:
    """Calculate corrected values for one row."""
    row_id = row["id"]

    # Convert leg prices from ₪ to index points
    sc_price = float(row.get("short_call_price") or 0) / MULTIPLIER
    sp_price = float(row.get("short_put_price") or 0) / MULTIPLIER
    lc_price = float(row.get("long_call_price") or 0) / MULTIPLIER
    lp_price = float(row.get("long_put_price") or 0) / MULTIPLIER

    # Recalculate derived fields
    net_premium = (sc_price + sp_price) - (lc_price + lp_price)
    max_profit = net_premium * MULTIPLIER

    # Wing widths from strikes
    sp_strike = float(row.get("short_put_strike") or 0)
    lp_strike = float(row.get("long_put_strike") or 0)
    sc_strike = float(row.get("short_call_strike") or 0)
    lc_strike = float(row.get("long_call_strike") or 0)
    wing_put = sp_strike - lp_strike if sp_strike > lp_strike else 20
    wing_call = lc_strike - sc_strike if lc_strike > sc_strike else 20
    actual_wing_max = max(wing_put, wing_call)

    max_risk = (actual_wing_max * MULTIPLIER) - max_profit
    rr_ratio = round(max_risk / max_profit, 4) if max_profit > 0 else 0

    be_upper = sc_strike + net_premium
    be_lower = sp_strike - net_premium

    # Also fix settled P&L if it exists
    actual_pnl_pts = float(row.get("actual_pnl_points") or 0)
    actual_pnl_ils = float(row.get("actual_pnl_ils") or 0)
    result_status = row.get("result_status")

    # If settled: recalculate P&L from settlement data
    if result_status:
        idx_close = float(row.get("actual_index_close") or 0)
        if idx_close > 0:
            if sp_strike <= idx_close <= sc_strike:
                pnl_pts = net_premium
            elif lp_strike <= idx_close < sp_strike:
                pnl_pts = net_premium - (sp_strike - idx_close)
            elif sc_strike < idx_close <= lc_strike:
                pnl_pts = net_premium - (idx_close - sc_strike)
            elif idx_close < lp_strike:
                pnl_pts = net_premium - wing_put
            else:
                pnl_pts = net_premium - wing_call
            actual_pnl_pts = round(pnl_pts, 4)
            actual_pnl_ils = round(pnl_pts * MULTIPLIER, 2)

    return {
        "id": row_id,
        "short_call_price": round(sc_price, 2),
        "short_put_price": round(sp_price, 2),
        "long_call_price": round(lc_price, 2),
        "long_put_price": round(lp_price, 2),
        "total_net_premium": round(net_premium, 2),
        "max_profit_ils": round(max_profit, 2),
        "max_risk_ils": round(max_risk, 2),
        "risk_reward_ratio": rr_ratio,
        "breakeven_upper": round(be_upper, 2),
        "breakeven_lower": round(be_lower, 2),
        "actual_pnl_points": actual_pnl_pts,
        "actual_pnl_ils": actual_pnl_ils,
    }


def apply_fix(fixed: dict) -> bool:
    """Update one row in Supabase."""
    row_id = fixed.pop("id")
    url = f"{SUPABASE_URL}/rest/v1/iron_condor_strategies?id=eq.{row_id}"
    r = httpx.patch(url, headers=headers(),
                    content=json.dumps(fixed), timeout=15)
    return r.status_code in (200, 204)


def main():
    apply = "--apply" in sys.argv

    if not SUPABASE_URL or not SUPABASE_KEY:
        print("ERROR: Set SUPABASE_URL and SUPABASE_KEY env vars")
        sys.exit(1)

    print(f"Mode: {'APPLY' if apply else 'DRY-RUN'}")
    print(f"Supabase: {SUPABASE_URL}")
    print()

    rows = fetch_all_strategies()
    print(f"Total strategies: {len(rows)}")

    to_fix = [r for r in rows if needs_fix(r)]
    already_ok = len(rows) - len(to_fix)
    print(f"Need fixing: {len(to_fix)}")
    print(f"Already OK:  {already_ok}")
    print()

    if not to_fix:
        print("Nothing to fix!")
        return

    fixed_count = 0
    for row in to_fix:
        fixed = fix_row(row)
        old_net = float(row.get("total_net_premium") or 0)
        new_net = fixed["total_net_premium"]
        old_profit = float(row.get("max_profit_ils") or 0)
        new_profit = fixed["max_profit_ils"]

        print(f"  ID {fixed['id']:>4}  |  "
              f"expiry {row.get('expiry_date')}  |  "
              f"interval {row.get('interval_pct')}%  |  "
              f"net_prem {old_net:>8.2f} -> {new_net:>8.2f}  |  "
              f"max_profit {old_profit:>10.2f} -> {new_profit:>10.2f}")

        if apply:
            ok = apply_fix(fixed)
            if ok:
                fixed_count += 1
            else:
                print(f"    FAILED to update ID {row['id']}")

    print()
    if apply:
        print(f"Updated {fixed_count}/{len(to_fix)} rows.")
    else:
        print(f"Dry-run complete. Run with --apply to update {len(to_fix)} rows.")


if __name__ == "__main__":
    main()
