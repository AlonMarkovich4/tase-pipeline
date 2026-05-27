"""
TASE TA-35 — Executive Strategy Dashboard
===========================================
Automated Iron Condor analytics, trade review,
and forward-looking strategy monitor.
Reads from Supabase iron_condor_strategies + tase_putcall.
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import httpx
import plotly.graph_objects as go
from datetime import datetime, date
from zoneinfo import ZoneInfo

# ==================================================================
# CONFIG
# ==================================================================
st.set_page_config(
    page_title="TA-35 Strategy Desk",
    page_icon="◆",
    layout="wide",
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")
MULTIPLIER = 50

# Palette
C_BG       = "#0B0D10"
C_CARD     = "#151921"
C_BORDER   = "#1E2433"
C_TEXT     = "#E8EAED"
C_DIM      = "#6B7B8D"
C_GREEN    = "#00E676"
C_RED      = "#FF1744"
C_BLUE     = "#00B0FF"
C_YELLOW   = "#FFD600"
C_GRID     = "#1A1F2B"
C_PROFIT   = "#00E676"
C_LOSS     = "#FF1744"

DAY_HE = {
    "Monday": "שני", "Tuesday": "שלישי", "Wednesday": "רביעי",
    "Thursday": "חמישי", "Friday": "שישי",
}

# ==================================================================
# GLOBAL CSS
# ==================================================================
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}
.main .block-container {{
    padding: 1rem 2rem 2rem !important;
    max-width: 1440px;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}

/* ── Header ── */
.dash-header {{
    text-align: center;
    padding: 22px 0 10px;
    margin-bottom: 6px;
}}
.dash-header h1 {{
    color: {C_TEXT};
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0;
}}
.dash-header .sub {{
    color: {C_DIM};
    font-size: 13px;
    margin-top: 4px;
}}

/* ── Metric Cards ── */
.metric-row {{
    display: flex;
    gap: 14px;
    margin: 16px 0;
    flex-wrap: wrap;
}}
.metric-card {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 12px;
    padding: 18px 22px;
    flex: 1;
    min-width: 180px;
    text-align: center;
    position: relative;
    overflow: hidden;
}}
.metric-card .label {{
    color: {C_DIM};
    font-size: 12px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}}
.metric-card .value {{
    font-size: 28px;
    font-weight: 800;
    letter-spacing: -0.5px;
}}
.metric-card .value.green {{ color: {C_GREEN}; }}
.metric-card .value.red {{ color: {C_RED}; }}
.metric-card .value.blue {{ color: {C_BLUE}; }}
.metric-card .value.yellow {{ color: {C_YELLOW}; }}
.metric-card .value.white {{ color: {C_TEXT}; }}

/* Glow effect for P&L card */
.metric-card.glow-green {{
    border-color: rgba(0,230,118,0.3);
    box-shadow: 0 0 20px rgba(0,230,118,0.12);
}}
.metric-card.glow-red {{
    border-color: rgba(255,23,68,0.3);
    box-shadow: 0 0 20px rgba(255,23,68,0.12);
}}

/* ── Big P&L Hero ── */
.pnl-hero {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 14px;
    padding: 28px;
    text-align: center;
    margin: 18px 0;
}}
.pnl-hero .title {{
    color: {C_DIM};
    font-size: 14px;
    font-weight: 600;
    margin-bottom: 8px;
}}
.pnl-hero .amount {{
    font-size: 44px;
    font-weight: 800;
    letter-spacing: -1px;
}}
.pnl-hero .amount.profit {{
    color: {C_GREEN};
    text-shadow: 0 0 30px rgba(0,230,118,0.35);
}}
.pnl-hero .amount.loss {{
    color: {C_RED};
    text-shadow: 0 0 30px rgba(255,23,68,0.35);
}}
.pnl-hero.glow-profit {{
    border-color: rgba(0,230,118,0.35);
    box-shadow: 0 0 35px rgba(0,230,118,0.10);
}}
.pnl-hero.glow-loss {{
    border-color: rgba(255,23,68,0.35);
    box-shadow: 0 0 35px rgba(255,23,68,0.10);
}}

/* ── Legs Table ── */
.legs-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 14px;
    margin: 12px 0;
    direction: ltr;
}}
.legs-table th {{
    background: {C_CARD};
    color: {C_DIM};
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 10px 14px;
    border-bottom: 1px solid {C_BORDER};
    text-align: center;
}}
.legs-table td {{
    padding: 10px 14px;
    text-align: center;
    border-bottom: 1px solid {C_BORDER};
    color: {C_TEXT};
    font-weight: 500;
}}
.legs-table tr:last-child td {{ border-bottom: none; }}
.legs-table .buy  {{ color: {C_GREEN}; font-weight: 700; }}
.legs-table .sell {{ color: {C_RED}; font-weight: 700; }}

/* ── Status Badge ── */
.badge {{
    display: inline-block;
    padding: 4px 14px;
    border-radius: 20px;
    font-size: 12px;
    font-weight: 700;
    letter-spacing: 0.3px;
}}
.badge.settled {{
    background: rgba(0,230,118,0.12);
    color: {C_GREEN};
    border: 1px solid rgba(0,230,118,0.25);
}}
.badge.active {{
    background: rgba(0,176,255,0.12);
    color: {C_BLUE};
    border: 1px solid rgba(0,176,255,0.25);
}}
.badge.loss {{
    background: rgba(255,23,68,0.12);
    color: {C_RED};
    border: 1px solid rgba(255,23,68,0.25);
}}

/* ── Section Header ── */
.section-hdr {{
    color: {C_TEXT};
    font-size: 16px;
    font-weight: 700;
    margin: 22px 0 8px;
    padding-bottom: 6px;
    border-bottom: 1px solid {C_BORDER};
}}

/* Streamlit overrides */
.stSelectbox label {{ color: {C_TEXT} !important; font-weight: 600 !important; }}
div[data-baseweb="select"] {{
    background: {C_CARD} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 8px !important;
}}
</style>
""", unsafe_allow_html=True)


# ==================================================================
# DATA LAYER
# ==================================================================

def _supabase_headers() -> dict:
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


@st.cache_data(ttl=120)
def load_strategies() -> pd.DataFrame:
    """Load all strategies from iron_condor_strategies."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()

    all_rows = []
    batch = 1000
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/iron_condor_strategies"
            f"?select=*&order=trigger_date.desc,expiry_date,interval_pct"
            f"&limit={batch}&offset={offset}"
        )
        try:
            r = httpx.get(url, headers=_supabase_headers(), timeout=20)
            if r.status_code not in (200, 206):
                break
            rows = r.json()
            if not rows:
                break
            all_rows.extend(rows)
            if len(rows) < batch:
                break
            offset += batch
        except Exception:
            break

    if not all_rows:
        return pd.DataFrame()

    df = pd.DataFrame(all_rows)

    # Ensure numeric columns
    num_cols = [
        "base_index_value", "interval_pct",
        "short_put_strike", "long_put_strike",
        "short_call_strike", "long_call_strike",
        "short_put_price", "long_put_price",
        "short_call_price", "long_call_price",
        "short_put_delta", "long_put_delta",
        "short_call_delta", "long_call_delta",
        "total_net_premium", "max_profit_ils", "max_risk_ils",
        "risk_reward_ratio", "breakeven_upper", "breakeven_lower",
        "days_to_expiry", "wing_width",
        "actual_wing_put", "actual_wing_call",
        "actual_index_close", "actual_pnl_points", "actual_pnl_ils",
    ]
    for c in num_cols:
        if c in df.columns:
            df[c] = pd.to_numeric(df[c], errors="coerce").fillna(0)

    return df


@st.cache_data(ttl=60)
def get_live_index() -> float:
    """Get latest TA-35 index from tase_putcall live table."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 0.0
    url = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=underlingasset_call"
        f"&underlingasset_call=gt.0"
        f"&order=id.desc&limit=1"
    )
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            rows = r.json()
            if rows:
                val = rows[0].get("underlingasset_call", 0)
                return float(val) if val else 0.0
    except Exception:
        pass
    return 0.0


# ==================================================================
# HELPERS
# ==================================================================

def fmt_ils(v: float) -> str:
    """Format ILS amount."""
    sign = "+" if v > 0 else ""
    return f"{sign}{v:,.0f} ₪"


def fmt_num(v: float, decimals: int = 2) -> str:
    return f"{v:,.{decimals}f}"


@st.cache_data(ttl=60)
def _fetch_current_option_price(derivative_id: str, side: str) -> float:
    """Fetch current lastrate for a specific option from tase_putcall."""
    if not derivative_id or not SUPABASE_URL:
        return 0.0
    col_id = f"derivativeid_{side}"
    col_price = f"lastrate_{side}"
    url = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?{col_id}=eq.{derivative_id}"
        f"&select={col_price}"
        f"&order=id.desc&limit=1"
    )
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            rows = r.json()
            if rows:
                val = rows[0].get(col_price, 0)
                if val is not None:
                    try:
                        return float(str(val).replace(",", ""))
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass
    return 0.0


def compute_unrealized_pnl(row: pd.Series, live_index: float) -> tuple:
    """
    Compute real unrealized P&L based on current option prices.

    Real P&L = (entry_premium - current_premium) × MULTIPLIER
    Where:
      entry_premium   = what we received when selling the condor
      current_premium = what it would cost to close now

    Returns (pnl_ils, method) where method is "live" or "expiry_proxy".
    """
    entry_premium = row.get("total_net_premium", 0)

    # Try to get current prices for all 4 legs
    sc_id = str(row.get("short_call_id", ""))
    sp_id = str(row.get("short_put_id", ""))
    lc_id = str(row.get("long_call_id", ""))
    lp_id = str(row.get("long_put_id", ""))

    sc_now = _fetch_current_option_price(sc_id, "call") if sc_id else 0
    sp_now = _fetch_current_option_price(sp_id, "put") if sp_id else 0
    lc_now = _fetch_current_option_price(lc_id, "call") if lc_id else 0
    lp_now = _fetch_current_option_price(lp_id, "put") if lp_id else 0

    # If we got at least the short legs priced, compute real P&L
    if sc_now > 0 or sp_now > 0:
        current_premium = (sc_now + sp_now) - (lc_now + lp_now)
        # We sold at entry_premium, buying back at current_premium
        pnl_pts = entry_premium - current_premium
        return round(pnl_pts * MULTIPLIER, 2), "live"

    # Fallback: expiry-proxy (same as before)
    sp_strike = row.get("short_put_strike", 0)
    sc_strike = row.get("short_call_strike", 0)
    lp_strike = row.get("long_put_strike", 0)
    lc_strike = row.get("long_call_strike", 0)
    wing_put = row.get("actual_wing_put", 0) or (sp_strike - lp_strike) or 20
    wing_call = row.get("actual_wing_call", 0) or (lc_strike - sc_strike) or 20

    if sp_strike <= live_index <= sc_strike:
        pnl_pts = entry_premium
    elif lp_strike <= live_index < sp_strike:
        pnl_pts = entry_premium - (sp_strike - live_index)
    elif sc_strike < live_index <= lc_strike:
        pnl_pts = entry_premium - (live_index - sc_strike)
    elif live_index < lp_strike:
        pnl_pts = entry_premium - wing_put
    else:
        pnl_pts = entry_premium - wing_call

    return round(pnl_pts * MULTIPLIER, 2), "expiry_proxy"


def build_payoff_curve(row: pd.Series) -> tuple:
    """Build x (price range) and y (P&L) arrays for payoff chart."""
    lp = row.get("long_put_strike", 0)
    sp = row.get("short_put_strike", 0)
    sc = row.get("short_call_strike", 0)
    lc = row.get("long_call_strike", 0)
    net_prem = row.get("total_net_premium", 0)
    wing_put = row.get("actual_wing_put", 0) or (sp - lp) or 20
    wing_call = row.get("actual_wing_call", 0) or (lc - sc) or 20

    margin = max(100, (lc - lp) * 0.6)
    x = np.linspace(lp - margin, lc + margin, 500)

    y = np.zeros_like(x)
    for i, price in enumerate(x):
        if sp <= price <= sc:
            pts = net_prem
        elif lp <= price < sp:
            pts = net_prem - (sp - price)
        elif sc < price <= lc:
            pts = net_prem - (price - sc)
        elif price < lp:
            pts = net_prem - wing_put
        else:
            pts = net_prem - wing_call
        y[i] = pts * MULTIPLIER

    return x, y


# ==================================================================
# RENDER HEADER
# ==================================================================
now_il = datetime.now(TZ)

st.markdown(f"""
<div class="dash-header">
    <h1>◆ TA-35 — Iron Condor Strategy Desk</h1>
    <div class="sub">{now_il.strftime("%A, %d %B %Y — %H:%M")} Israel</div>
</div>
""", unsafe_allow_html=True)


# ==================================================================
# LOAD DATA
# ==================================================================
df = load_strategies()

if df.empty:
    st.warning("אין נתוני אסטרטגיות ב-Supabase. ודא שהמערכת רצה ושיש חיבור תקין.")
    st.stop()

# Build week labels: "2026-W22 (25/05)"
df["_trigger_dt"] = pd.to_datetime(df["trigger_date"], errors="coerce")
df["_iso_week"] = df["_trigger_dt"].dt.isocalendar().week.astype(int)
df["_iso_year"] = df["_trigger_dt"].dt.isocalendar().year.astype(int)
df["_week_label"] = df.apply(
    lambda r: f"{int(r['_iso_year'])}-W{int(r['_iso_week']):02d}  ({r['trigger_date']})",
    axis=1,
)

# Determine settled vs active
today_str = now_il.strftime("%Y-%m-%d")
df["_is_settled"] = df["result_status"].notna() & (df["result_status"] != "")

# Unique weeks sorted chronologically
week_options = (
    df[["_week_label", "_trigger_dt"]]
    .drop_duplicates("_week_label")
    .sort_values("_trigger_dt", ascending=False)
)["_week_label"].tolist()

interval_options = sorted(df["interval_pct"].unique())


# ==================================================================
# EXECUTIVE CONTROL BOARD
# ==================================================================
col_w, col_i = st.columns(2)
with col_w:
    selected_week = st.selectbox(
        "📅 בחר שבוע מסחר / תאריך הרצה",
        week_options,
        index=0,
    )
with col_i:
    selected_interval = st.selectbox(
        "📐 בחר מרווח אסטרטגיה (% Interval)",
        interval_options,
        format_func=lambda x: f"{x:.1f}%",
        index=0,
    )

# Filter to selected week + interval
mask = (df["_week_label"] == selected_week) & (df["interval_pct"] == selected_interval)
filtered = df[mask].copy()

if filtered.empty:
    st.info("אין אסטרטגיות למרווח ולשבוע שנבחרו.")
    st.stop()

# Sort by expiry date
filtered = filtered.sort_values("expiry_date")

# Get live index for active positions
live_index = get_live_index()

# Base index at entry
base_index = filtered.iloc[0].get("base_index_value", 0)
trigger_date = filtered.iloc[0].get("trigger_date", "")
trigger_time = filtered.iloc[0].get("trigger_time", "")

# Count settled / active
n_settled = int(filtered["_is_settled"].sum())
n_active = len(filtered) - n_settled
n_total = len(filtered)


# ==================================================================
# TOP METRICS ROW
# ==================================================================
# Overall P&L for settled strategies
settled_pnl = filtered.loc[filtered["_is_settled"], "actual_pnl_ils"].sum()

# Unrealized P&L for active strategies
unrealized_pnl = 0.0
pnl_method = "live"
if n_active > 0 and live_index > 0:
    for _, row in filtered[~filtered["_is_settled"]].iterrows():
        pnl_val, method = compute_unrealized_pnl(row, live_index)
        unrealized_pnl += pnl_val
        if method == "expiry_proxy":
            pnl_method = "expiry_proxy"

total_pnl = settled_pnl + unrealized_pnl

# Status badge
if n_active == 0:
    status_html = '<span class="badge settled">✅ SETTLED</span>'
elif n_settled == 0:
    status_html = '<span class="badge active">🔵 ACTIVE</span>'
else:
    status_html = '<span class="badge active">🔵 PARTIALLY ACTIVE</span>'

st.markdown(f"""
<div class="metric-row">
    <div class="metric-card">
        <div class="label">📅 תאריך הרצה</div>
        <div class="value white">{trigger_date}</div>
    </div>
    <div class="metric-card">
        <div class="label">⏰ שעת הרצה</div>
        <div class="value white">{trigger_time}</div>
    </div>
    <div class="metric-card">
        <div class="label">📊 מדד כניסה (TA-35)</div>
        <div class="value yellow">{fmt_num(base_index)}</div>
    </div>
    <div class="metric-card">
        <div class="label">📐 מרווח</div>
        <div class="value blue">{selected_interval:.1f}%</div>
    </div>
    <div class="metric-card">
        <div class="label">🎯 פקיעות</div>
        <div class="value white">{n_total} ({n_settled} settled / {n_active} active)</div>
    </div>
    <div class="metric-card">
        <div class="label">סטטוס</div>
        <div style="margin-top:6px">{status_html}</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==================================================================
# P&L BREAKDOWN BY INTERVAL
# ==================================================================
week_all = df[df["_week_label"] == selected_week].copy()

# Compute P&L per interval
interval_pnl_rows = []
for pct in sorted(week_all["interval_pct"].unique()):
    idf = week_all[week_all["interval_pct"] == pct]
    settled_sum = idf.loc[idf["_is_settled"], "actual_pnl_ils"].sum()
    unrealized_sum = 0.0
    method = "live"
    for _, r in idf[~idf["_is_settled"]].iterrows():
        if live_index > 0:
            val, m = compute_unrealized_pnl(r, live_index)
            unrealized_sum += val
            if m == "expiry_proxy":
                method = "expiry_proxy"
    total = settled_sum + unrealized_sum
    n_s = int(idf["_is_settled"].sum())
    n_a = len(idf) - n_s
    interval_pnl_rows.append({
        "pct": pct, "settled_pnl": settled_sum,
        "unrealized_pnl": unrealized_sum, "total_pnl": total,
        "n_settled": n_s, "n_active": n_a, "method": method,
    })

# Build compact P&L table for all intervals
pnl_table = (
    '<div dir="ltr"><table class="legs-table">'
    '<thead><tr>'
    '<th>מרווח</th><th>פקיעות</th>'
    '<th>P&L מומש</th><th>P&L צף</th><th>סה"כ</th>'
    '</tr></thead><tbody>'
)
grand_total = 0.0
for ip in interval_pnl_rows:
    pct = ip["pct"]
    total = ip["total_pnl"]
    grand_total += total
    t_css = "buy" if total > 0 else ("sell" if total < 0 else "")
    s_css = "buy" if ip["settled_pnl"] > 0 else ("sell" if ip["settled_pnl"] < 0 else "")
    u_css = "buy" if ip["unrealized_pnl"] > 0 else ("sell" if ip["unrealized_pnl"] < 0 else "")
    highlight = ' style="background:rgba(0,176,255,0.08)"' if pct == selected_interval else ""
    status = f'{ip["n_settled"]}✅ {ip["n_active"]}🔵' if ip["n_active"] > 0 else f'{ip["n_settled"]}✅'
    pnl_table += (
        f'<tr{highlight}>'
        f'<td><strong>{pct:.1f}%</strong></td>'
        f'<td>{status}</td>'
        f'<td class="{s_css}">{fmt_ils(ip["settled_pnl"])}</td>'
        f'<td class="{u_css}">{fmt_ils(ip["unrealized_pnl"])}</td>'
        f'<td class="{t_css}"><strong>{fmt_ils(total)}</strong></td>'
        f'</tr>'
    )

# Grand total row
gt_css = "buy" if grand_total > 0 else ("sell" if grand_total < 0 else "")
pnl_table += (
    f'<tr style="border-top:2px solid {C_BORDER};font-weight:700">'
    f'<td>סה"כ</td><td></td><td></td><td></td>'
    f'<td class="{gt_css}"><strong>{fmt_ils(grand_total)}</strong></td>'
    f'</tr>'
)
pnl_table += '</tbody></table></div>'

st.markdown('<div class="section-hdr">💰 P&L לפי מרווח — שבוע נבחר</div>',
            unsafe_allow_html=True)
st.markdown(pnl_table, unsafe_allow_html=True)


# ==================================================================
# LIVE INDEX / SETTLEMENT INDEX
# ==================================================================
if n_active > 0 and live_index > 0:
    idx_color = "green" if live_index >= base_index else "red"
    chg_color = "green" if live_index >= base_index else "red"
    sp_color = "green" if settled_pnl >= 0 else "red"
    up_color = "green" if unrealized_pnl >= 0 else "red"
    glow = "green" if idx_color == "green" else "red"
    chg_val = live_index - base_index
    chg_pct = chg_val / base_index * 100 if base_index > 0 else 0
    st.markdown(
        f'<div class="metric-row">'
        f'<div class="metric-card glow-{glow}"><div class="label">🔴 מדד נוכחי בשוק (פוזיציה פתוחה)</div><div class="value {idx_color}">{fmt_num(live_index)}</div></div>'
        f'<div class="metric-card"><div class="label">📊 שינוי מכניסה</div><div class="value {chg_color}">{fmt_num(chg_val)} ({chg_pct:+.2f}%)</div></div>'
        f'<div class="metric-card"><div class="label">💰 P&L מומש (settled)</div><div class="value {sp_color}">{fmt_ils(settled_pnl)}</div></div>'
        f'<div class="metric-card"><div class="label">📈 P&L צף (active)</div><div class="value {up_color}">{fmt_ils(unrealized_pnl)}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ==================================================================
# PER-EXPIRY BREAKDOWN
# ==================================================================
# ==================================================================
# SPLIT INTO TABS: Active vs History
# ==================================================================
active_df = filtered[~filtered["_is_settled"]]
history_df = filtered[filtered["_is_settled"]]

tab_active, tab_history = st.tabs([
    f"🔵 פוזיציות פתוחות ({len(active_df)})",
    f"📜 היסטוריה ({len(history_df)})",
])


def render_expiry_card(row, container):
    """Render a single expiry card (legs table, metrics, payoff chart)."""
    exp_date = row.get("expiry_date", "")
    exp_day = row.get("expiry_day_name", "")
    exp_day_he = DAY_HE.get(exp_day, exp_day)
    is_settled = row["_is_settled"]
    result_status = row.get("result_status", "")

    if is_settled:
        pnl = row.get("actual_pnl_ils", 0)
        pnl_icon = "✅" if pnl > 0 else "❌"
        badge_text = f"{pnl_icon} {fmt_ils(pnl)}"
        idx_label = f"מדד פקיעה: {fmt_num(row.get('actual_index_close', 0))}"
    else:
        if live_index > 0:
            u_pnl, _ = compute_unrealized_pnl(row, live_index)
            badge_text = f"🔵 צף: {fmt_ils(u_pnl)}"
        else:
            badge_text = "🔵 פתוח"
        idx_label = f"מדד נוכחי: {fmt_num(live_index)}" if live_index > 0 else ""

    expander_label = f"📅 {exp_date} — יום {exp_day_he}  |  {badge_text}  |  {idx_label}"
    with container.expander(expander_label, expanded=True):

        # ── 4 Legs Table ──
        legs = [
            ("Long Put (הגנה)", "BUY", row.get("long_put_strike", 0),
             row.get("long_put_price", 0), row.get("long_put_delta", 0),
             row.get("long_put_id", "")),
            ("Short Put (מכירה)", "SELL", row.get("short_put_strike", 0),
             row.get("short_put_price", 0), row.get("short_put_delta", 0),
             row.get("short_put_id", "")),
            ("Short Call (מכירה)", "SELL", row.get("short_call_strike", 0),
             row.get("short_call_price", 0), row.get("short_call_delta", 0),
             row.get("short_call_id", "")),
            ("Long Call (הגנה)", "BUY", row.get("long_call_strike", 0),
             row.get("long_call_price", 0), row.get("long_call_delta", 0),
             row.get("long_call_id", "")),
        ]

        legs_html = (
            '<div dir="ltr"><table class="legs-table">'
            '<thead><tr>'
            '<th>Leg</th><th>Action</th><th>Strike</th>'
            '<th>Premium</th><th>Delta</th><th>ID</th>'
            '</tr></thead><tbody>'
        )
        for name, action, strike, price, delta, opt_id in legs:
            css = "sell" if action == "SELL" else "buy"
            legs_html += (
                f'<tr>'
                f'<td>{name}</td>'
                f'<td class="{css}">{action}</td>'
                f'<td><strong>{fmt_num(strike, 0)}</strong></td>'
                f'<td>{fmt_num(price)}</td>'
                f'<td>{fmt_num(delta, 4)}</td>'
                f'<td style="color:{C_DIM};font-size:11px">{opt_id}</td>'
                f'</tr>'
            )
        legs_html += "</tbody></table></div>"
        st.markdown(legs_html, unsafe_allow_html=True)

        # ── Key metrics for this expiry ──
        net_prem = row.get("total_net_premium", 0)
        max_profit = row.get("max_profit_ils", 0)
        max_risk = row.get("max_risk_ils", 0)
        rr = row.get("risk_reward_ratio", 0)
        be_upper = row.get("breakeven_upper", 0)
        be_lower = row.get("breakeven_lower", 0)
        dte = int(row.get("days_to_expiry", 0))

        prem_color = "green" if net_prem > 0 else "red"
        st.markdown(
            f'<div class="metric-row">'
            f'<div class="metric-card"><div class="label">פרמיה נטו (נק\')</div><div class="value {prem_color}">{fmt_num(net_prem)}</div></div>'
            f'<div class="metric-card"><div class="label">רווח מקסימלי</div><div class="value green">{fmt_ils(max_profit)}</div></div>'
            f'<div class="metric-card"><div class="label">הפסד מקסימלי</div><div class="value red">{fmt_ils(-abs(max_risk))}</div></div>'
            f'<div class="metric-card"><div class="label">Risk/Reward</div><div class="value white">1:{fmt_num(rr, 1)}</div></div>'
            f'<div class="metric-card"><div class="label">Breakeven</div><div class="value white">{fmt_num(be_lower, 0)} — {fmt_num(be_upper, 0)}</div></div>'
            f'<div class="metric-card"><div class="label">ימים לפקיעה</div><div class="value blue">{dte}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # ── Payoff Chart (trading-desk style) ──
        x_prices, y_pnl = build_payoff_curve(row)

        fig = go.Figure()

        # Solid green fill for profit zone
        profit_y = np.where(y_pnl >= 0, y_pnl, 0)
        fig.add_trace(go.Scatter(
            x=x_prices, y=profit_y,
            fill="tozeroy",
            fillcolor="rgba(0,200,100,0.55)",
            line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        ))

        # Solid red fill for loss zone
        loss_y = np.where(y_pnl < 0, y_pnl, 0)
        fig.add_trace(go.Scatter(
            x=x_prices, y=loss_y,
            fill="tozeroy",
            fillcolor="rgba(220,38,38,0.55)",
            line=dict(width=0),
            showlegend=False, hoverinfo="skip",
        ))

        # Thin white payoff outline on top
        fig.add_trace(go.Scatter(
            x=x_prices, y=y_pnl,
            mode="lines",
            line=dict(color="rgba(255,255,255,0.35)", width=1),
            showlegend=False,
            hovertemplate="מדד: %{x:,.0f}<br>P&L: %{y:,.0f} ₪<extra></extra>",
        ))

        # Zero line
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))

        # Orange breakeven dots on the zero line
        be_x = [v for v in [be_lower, be_upper] if v > 0]
        if be_x:
            fig.add_trace(go.Scatter(
                x=be_x, y=[0] * len(be_x),
                mode="markers",
                marker=dict(color="#FF9800", size=10, symbol="circle",
                            line=dict(color="#0B0D10", width=2)),
                showlegend=False,
                hovertemplate="Breakeven: %{x:,.0f}<extra></extra>",
            ))

        # Reference line: Settlement price or Live index
        if is_settled:
            ref_price = row.get("actual_index_close", 0)
            ref_label = f"פקיעה: {ref_price:,.2f}"
        elif live_index > 0:
            ref_price = live_index
            ref_label = f"נוכחי: {ref_price:,.2f}"
        else:
            ref_price = 0
            ref_label = ""

        if ref_price > 0:
            fig.add_vline(
                x=ref_price,
                line=dict(color="#00BCD4", width=2, dash="dot"),
            )
            # Label at top
            fig.add_annotation(
                x=ref_price, y=max(y_pnl) * 0.9,
                text=ref_label,
                showarrow=False,
                font=dict(size=13, color="#00BCD4", family="Inter"),
                bgcolor="rgba(11,13,16,0.85)",
                bordercolor="#00BCD4",
                borderwidth=1,
                borderpad=6,
            )

        # X-axis label
        fig.add_annotation(
            x=0.5, y=-0.12,
            xref="paper", yref="paper",
            text="שער המדד בפקיעה",
            showarrow=False,
            font=dict(size=12, color=C_DIM),
        )

        fig.update_layout(
            template="plotly_dark",
            paper_bgcolor=C_BG,
            plot_bgcolor=C_BG,
            height=360,
            margin=dict(l=50, r=30, t=20, b=50),
            xaxis=dict(
                gridcolor="rgba(255,255,255,0.04)",
                zeroline=False,
                tickformat=",",
                tickfont=dict(size=10, color=C_DIM),
                showgrid=True,
                dtick=40,
            ),
            yaxis=dict(
                title="(₪) רווח/הפסד",
                gridcolor="rgba(255,255,255,0.06)",
                zeroline=False,
                tickformat=",",
                tickfont=dict(size=10, color=C_DIM),
                title_font=dict(size=11, color=C_DIM),
                showgrid=True,
            ),
            showlegend=False,
            hovermode="x unified",
        )

        st.plotly_chart(fig, use_container_width=True)


# ── Render Active tab ──
with tab_active:
    if active_df.empty:
        st.info("אין פוזיציות פתוחות כרגע — כל האסטרטגיות פקעו.")
    else:
        for _, row in active_df.iterrows():
            render_expiry_card(row, tab_active)

# ── Render History tab ──
with tab_history:
    if history_df.empty:
        st.info("אין היסטוריה — אף אסטרטגיה לא פקעה עדיין.")
    else:
        for _, row in history_df.iterrows():
            render_expiry_card(row, tab_history)


# ==================================================================
# WEEKLY AGGREGATE SUMMARY
# ==================================================================
st.markdown('<div class="section-hdr">📊 סיכום שבועי — כל המרווחים</div>',
            unsafe_allow_html=True)

# Get all strategies for the selected week (all intervals)
week_mask = df["_week_label"] == selected_week
week_df = df[week_mask].copy()

if not week_df.empty:
    # Aggregate by interval
    agg = week_df.groupby("interval_pct").agg(
        expiries=("expiry_date", "nunique"),
        settled=("_is_settled", "sum"),
        total_pnl=("actual_pnl_ils", "sum"),
        avg_premium=("total_net_premium", "mean"),
        max_profit=("max_profit_ils", "mean"),
        max_risk=("max_risk_ils", "mean"),
    ).reset_index()

    # Add win count
    settled_df = week_df[week_df["_is_settled"]]
    if not settled_df.empty:
        wins = settled_df[settled_df["actual_pnl_ils"] > 0].groupby(
            "interval_pct"
        ).size().reset_index(name="wins")
        agg = agg.merge(wins, on="interval_pct", how="left")
        agg["wins"] = agg["wins"].fillna(0).astype(int)
    else:
        agg["wins"] = 0

    agg["settled"] = agg["settled"].astype(int)

    # Build summary table — NO indentation (Markdown treats 4+ spaces as code block)
    summary_html = (
        '<div dir="ltr"><table class="legs-table">'
        '<thead><tr>'
        '<th>Interval</th><th>Expiries</th><th>Settled</th>'
        '<th>Wins</th><th>P&L (₪)</th><th>Avg Premium</th>'
        '<th>Avg Max Profit</th><th>Avg Max Risk</th>'
        '</tr></thead><tbody>'
    )
    for _, r in agg.iterrows():
        pnl = r["total_pnl"]
        pnl_css = "buy" if pnl > 0 else ("sell" if pnl < 0 else "")
        summary_html += (
            f'<tr>'
            f'<td><strong>{r["interval_pct"]:.1f}%</strong></td>'
            f'<td>{int(r["expiries"])}</td>'
            f'<td>{int(r["settled"])}</td>'
            f'<td>{int(r["wins"])}</td>'
            f'<td class="{pnl_css}"><strong>{fmt_ils(pnl)}</strong></td>'
            f'<td>{fmt_num(r["avg_premium"])} pts</td>'
            f'<td class="buy">{fmt_ils(r["max_profit"])}</td>'
            f'<td class="sell">{fmt_ils(-abs(r["max_risk"]))}</td>'
            f'</tr>'
        )

    # Total row
    total = agg["total_pnl"].sum()
    total_css = "buy" if total > 0 else ("sell" if total < 0 else "")
    summary_html += (
        f'<tr style="border-top:2px solid {C_BORDER};font-weight:700">'
        f'<td>סה"כ</td>'
        f'<td>{int(agg["expiries"].sum())}</td>'
        f'<td>{int(agg["settled"].sum())}</td>'
        f'<td>{int(agg["wins"].sum())}</td>'
        f'<td class="{total_css}"><strong>{fmt_ils(total)}</strong></td>'
        f'<td colspan="2"></td>'
        f'<td></td>'
        f'</tr>'
    )
    summary_html += '</tbody></table></div>'
    st.markdown(summary_html, unsafe_allow_html=True)


# ==================================================================
# FOOTER
# ==================================================================
st.markdown(f"""
<div style="text-align:center; padding:30px 0 10px; color:{C_DIM}; font-size:11px;">
    TA-35 Iron Condor Strategy Desk — Automated Pipeline Monitor<br>
    Data refreshes every 2 minutes &nbsp;|&nbsp; Multiplier: {MULTIPLIER}₪ per point
    &nbsp;|&nbsp; {now_il.strftime("%H:%M:%S")} IL
</div>
""", unsafe_allow_html=True)
