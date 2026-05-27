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

# Palette — high-contrast dark theme
C_BG       = "#0B0D10"
C_CARD     = "#151921"
C_BORDER   = "#1E2433"
C_TEXT     = "#E8EAED"
C_DIM      = "#9AA0A6"        # ← boosted from #6B7B8D for accessibility
C_GREEN    = "#00E676"
C_RED      = "#FF1744"
C_BLUE     = "#00B0FF"
C_YELLOW   = "#FFD600"
C_ORANGE   = "#FF9800"

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
.metric-grid {{
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
    min-width: 170px;
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
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
}}
.metric-card .value.green {{ color: {C_GREEN}; }}
.metric-card .value.red {{ color: {C_RED}; }}
.metric-card .value.blue {{ color: {C_BLUE}; }}
.metric-card .value.yellow {{ color: {C_YELLOW}; }}
.metric-card .value.white {{ color: {C_TEXT}; }}

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

/* ── Tables — responsive scroll wrapper ── */
.table-scroll {{
    overflow-x: auto;
    -webkit-overflow-scrolling: touch;
    margin: 12px 0;
    border-radius: 10px;
    border: 1px solid {C_BORDER};
    background: {C_CARD};
}}
.table-scroll table {{
    width: 100%;
    min-width: 560px;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 14px;
    direction: ltr;
}}
.table-scroll th {{
    background: rgba(255,255,255,0.03);
    color: {C_DIM};
    font-weight: 600;
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    padding: 11px 14px;
    border-bottom: 1px solid {C_BORDER};
    text-align: center;
    position: sticky;
    top: 0;
    z-index: 1;
}}
.table-scroll td {{
    padding: 10px 14px;
    text-align: center;
    border-bottom: 1px solid rgba(30,36,51,0.6);
    color: {C_TEXT};
    font-weight: 500;
}}
.table-scroll tr:last-child td {{ border-bottom: none; }}
.table-scroll tr:hover td {{ background: rgba(255,255,255,0.02); }}
.table-scroll .buy  {{ color: {C_GREEN}; font-weight: 700; }}
.table-scroll .sell {{ color: {C_RED}; font-weight: 700; }}

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
    margin: 24px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid {C_BORDER};
    direction: rtl;
    text-align: right;
}}

/* ── Step Breadcrumb ── */
.step-breadcrumb {{
    display: flex;
    align-items: center;
    gap: 6px;
    margin: 16px 0 8px;
    direction: rtl;
}}
.step-breadcrumb .crumb {{
    display: inline-flex;
    align-items: center;
    gap: 6px;
    font-size: 13px;
    font-weight: 600;
    color: {C_DIM};
}}
.step-breadcrumb .crumb.active {{
    color: {C_BLUE};
}}
.step-breadcrumb .num {{
    width: 24px;
    height: 24px;
    border-radius: 50%;
    display: inline-flex;
    align-items: center;
    justify-content: center;
    font-size: 12px;
    font-weight: 700;
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    color: {C_DIM};
    flex-shrink: 0;
}}
.step-breadcrumb .crumb.active .num {{
    background: rgba(0,176,255,0.15);
    border-color: {C_BLUE};
    color: {C_BLUE};
}}
.step-breadcrumb .sep {{
    color: {C_BORDER};
    font-size: 14px;
    margin: 0 2px;
}}

/* ── Comparison Bar ── */
.cmp-row {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 14px 18px;
    margin: 8px 0;
}}
.cmp-line {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 3px 0;
}}
.cmp-line .cmp-lbl {{
    color: {C_DIM};
    font-size: 11px;
    font-weight: 600;
    min-width: 55px;
    text-align: left;
}}
.cmp-line .cmp-track {{
    flex: 1;
    height: 20px;
    background: rgba(255,255,255,0.04);
    border-radius: 5px;
    overflow: hidden;
}}
.cmp-line .cmp-fill {{
    height: 100%;
    border-radius: 5px;
    transition: width 0.3s ease;
}}
.cmp-line .cmp-val {{
    min-width: 85px;
    text-align: right;
    font-weight: 700;
    font-size: 13px;
}}

/* ── Settlement position indicator ── */
.strike-zone {{
    display: inline-block;
    padding: 2px 8px;
    border-radius: 4px;
    font-size: 11px;
    font-weight: 700;
}}
.strike-zone.in {{
    background: rgba(0,230,118,0.15);
    color: {C_GREEN};
}}
.strike-zone.out-put {{
    background: rgba(255,23,68,0.12);
    color: {C_RED};
}}
.strike-zone.out-call {{
    background: rgba(255,23,68,0.12);
    color: {C_RED};
}}

/* ── Streamlit overrides ── */
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
    sign = "+" if v > 0 else ""
    return f"{sign}{v:,.0f} ₪"


def fmt_num(v: float, decimals: int = 2) -> str:
    return f"{v:,.{decimals}f}"


@st.cache_data(ttl=60)
def _fetch_current_option_price(derivative_id: str, side: str) -> float:
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
                        # TASE lastrate is in ₪/contract — divide by multiplier for points
                        return float(str(val).replace(",", "")) / MULTIPLIER
                    except (ValueError, TypeError):
                        pass
    except Exception:
        pass
    return 0.0


def compute_unrealized_pnl(row: pd.Series, live_index: float) -> tuple:
    entry_premium = row.get("total_net_premium", 0)
    sc_id = str(row.get("short_call_id", ""))
    sp_id = str(row.get("short_put_id", ""))
    lc_id = str(row.get("long_call_id", ""))
    lp_id = str(row.get("long_put_id", ""))

    sc_now = _fetch_current_option_price(sc_id, "call") if sc_id else 0
    sp_now = _fetch_current_option_price(sp_id, "put") if sp_id else 0
    lc_now = _fetch_current_option_price(lc_id, "call") if lc_id else 0
    lp_now = _fetch_current_option_price(lp_id, "put") if lp_id else 0

    if sc_now > 0 or sp_now > 0:
        current_premium = (sc_now + sp_now) - (lc_now + lp_now)
        pnl_pts = entry_premium - current_premium
        return round(pnl_pts * MULTIPLIER, 2), "live"

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


def settlement_zone_label(idx_close: float, sp: float, sc: float, lp: float, lc: float) -> str:
    """Return an HTML badge showing where settlement landed relative to strikes."""
    if sp <= idx_close <= sc:
        return '<span class="strike-zone in">SAFE ZONE</span>'
    elif lp <= idx_close < sp:
        return '<span class="strike-zone out-put">PUT BREACH</span>'
    elif sc < idx_close <= lc:
        return '<span class="strike-zone out-call">CALL BREACH</span>'
    elif idx_close < lp:
        return '<span class="strike-zone out-put">MAX LOSS PUT</span>'
    else:
        return '<span class="strike-zone out-call">MAX LOSS CALL</span>'


# ==================================================================
# RENDER COMPONENTS
# ==================================================================

def render_payoff_chart(row, ref_price: float = 0, ref_label: str = ""):
    x_prices, y_pnl = build_payoff_curve(row)
    be_upper = row.get("breakeven_upper", 0)
    be_lower = row.get("breakeven_lower", 0)
    fig = go.Figure()

    profit_y = np.where(y_pnl >= 0, y_pnl, 0)
    fig.add_trace(go.Scatter(x=x_prices, y=profit_y, fill="tozeroy", fillcolor="rgba(38,222,129,0.50)", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    loss_y = np.where(y_pnl < 0, y_pnl, 0)
    fig.add_trace(go.Scatter(x=x_prices, y=loss_y, fill="tozeroy", fillcolor="rgba(255,77,77,0.50)", line=dict(width=0), showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x_prices, y=y_pnl, mode="lines", line=dict(color="rgba(255,255,255,0.35)", width=1), showlegend=False, hovertemplate="Index: %{x:,.0f}<br>P&L: %{y:,.0f} ₪<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))

    be_x = [v for v in [be_lower, be_upper] if v > 0]
    if be_x:
        fig.add_trace(go.Scatter(x=be_x, y=[0] * len(be_x), mode="markers", marker=dict(color=C_ORANGE, size=10, symbol="circle", line=dict(color=C_BG, width=2)), showlegend=False, hovertemplate="Breakeven: %{x:,.0f}<extra></extra>"))

    if ref_price > 0:
        fig.add_vline(x=ref_price, line=dict(color="#00BCD4", width=2, dash="dot"))
        fig.add_annotation(x=ref_price, y=max(y_pnl) * 0.9, text=ref_label, showarrow=False, font=dict(size=13, color="#00BCD4", family="Inter"), bgcolor="rgba(11,13,16,0.85)", bordercolor="#00BCD4", borderwidth=1, borderpad=6)

    fig.update_layout(
        template="plotly_dark", paper_bgcolor=C_BG, plot_bgcolor=C_BG,
        height=360, margin=dict(l=50, r=30, t=20, b=50),
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False, tickformat=",", tickfont=dict(size=10, color=C_DIM), showgrid=True, dtick=40),
        yaxis=dict(title="P&L (₪)", gridcolor="rgba(255,255,255,0.06)", zeroline=False, tickformat=",", tickfont=dict(size=10, color=C_DIM), title_font=dict(size=11, color=C_DIM), showgrid=True),
        showlegend=False, hovermode="x unified",
    )
    st.plotly_chart(fig, use_container_width=True)


def render_legs_table(row):
    legs = [
        ("Long Put", "BUY", row.get("long_put_strike", 0), row.get("long_put_price", 0)),
        ("Short Put", "SELL", row.get("short_put_strike", 0), row.get("short_put_price", 0)),
        ("Short Call", "SELL", row.get("short_call_strike", 0), row.get("short_call_price", 0)),
        ("Long Call", "BUY", row.get("long_call_strike", 0), row.get("long_call_price", 0)),
    ]
    html = '<div class="table-scroll"><table><thead><tr><th>Leg</th><th>Action</th><th>Strike</th><th>Premium (pts)</th></tr></thead><tbody>'
    for name, action, strike, price in legs:
        css = "sell" if action == "SELL" else "buy"
        html += f'<tr><td>{name}</td><td class="{css}">{action}</td><td><strong>{fmt_num(strike, 0)}</strong></td><td>{fmt_num(price)}</td></tr>'
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def render_expiry_metrics(row):
    net_prem = row.get("total_net_premium", 0)
    max_profit = row.get("max_profit_ils", 0)
    max_risk = row.get("max_risk_ils", 0)
    rr = abs(row.get("risk_reward_ratio", 0))
    be_upper = row.get("breakeven_upper", 0)
    be_lower = row.get("breakeven_lower", 0)
    dte = int(row.get("days_to_expiry", 0))
    prem_color = "green" if net_prem > 0 else "red"
    # Row 1: P&L range
    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">Net Premium (pts)</div><div class="value {prem_color}">{fmt_num(net_prem)}</div></div>'
        f'<div class="metric-card glow-green"><div class="label">Max Profit</div><div class="value green">{fmt_ils(max_profit)}</div></div>'
        f'<div class="metric-card glow-red"><div class="label">Max Risk</div><div class="value red">{fmt_ils(-abs(max_risk))}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Row 2: Structure
    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">Risk / Reward</div><div class="value white">1:{fmt_num(rr, 1)}</div></div>'
        f'<div class="metric-card"><div class="label">Lower Breakeven</div><div class="value white">{fmt_num(be_lower, 0)}</div></div>'
        f'<div class="metric-card"><div class="label">Upper Breakeven</div><div class="value white">{fmt_num(be_upper, 0)}</div></div>'
        f'<div class="metric-card"><div class="label">DTE</div><div class="value blue">{dte}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_breadcrumb(steps: list):
    """Render step breadcrumb. steps = list of (label, is_active)."""
    parts = []
    for i, (label, active) in enumerate(steps):
        cls = "crumb active" if active else "crumb"
        parts.append(f'<span class="{cls}"><span class="num">{i+1}</span>{label}</span>')
    html = '<div class="step-breadcrumb">' + '<span class="sep">‹</span>'.join(parts) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


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

df["_trigger_dt"] = pd.to_datetime(df["trigger_date"], errors="coerce")
df["_iso_week"] = df["_trigger_dt"].dt.isocalendar().week.astype(int)
df["_iso_year"] = df["_trigger_dt"].dt.isocalendar().year.astype(int)
df["_week_label"] = df.apply(
    lambda r: f"{int(r['_iso_year'])}-W{int(r['_iso_week']):02d}  ({r['trigger_date']})",
    axis=1,
)
df["_is_settled"] = df["result_status"].notna() & (df["result_status"] != "")

# Expired but never settled → treat as settled (missed settlement)
today_str = now_il.strftime("%Y-%m-%d")
df["_is_expired"] = (df["expiry_date"] < today_str) & (~df["_is_settled"])
df.loc[df["_is_expired"], "_is_settled"] = True

week_options = (
    df[["_week_label", "_trigger_dt"]]
    .drop_duplicates("_week_label")
    .sort_values("_trigger_dt", ascending=False)
)["_week_label"].tolist()

live_index = get_live_index()


# ==================================================================
# STEP 1 — GLOBAL: Week selector
# ==================================================================
render_breadcrumb([("שבוע מסחר", True)])

selected_week = st.selectbox(
    "📅 שבוע מסחר / תאריך הרצה",
    week_options,
    index=0,
    label_visibility="collapsed",
)

week_all = df[df["_week_label"] == selected_week].copy()
if week_all.empty:
    st.info("אין אסטרטגיות לשבוע שנבחר.")
    st.stop()

base_index = week_all.iloc[0].get("base_index_value", 0)
trigger_date = week_all.iloc[0].get("trigger_date", "")
trigger_time = week_all.iloc[0].get("trigger_time", "")

n_total_week = len(week_all)
n_settled_week = int(week_all["_is_settled"].sum())
n_active_week = n_total_week - n_settled_week

if n_active_week == 0:
    week_status = '<span class="badge settled">SETTLED</span>'
elif n_settled_week == 0:
    week_status = '<span class="badge active">ACTIVE</span>'
else:
    week_status = '<span class="badge active">PARTIALLY ACTIVE</span>'

st.markdown(
    f'<div class="metric-grid">'
    f'<div class="metric-card"><div class="label">Run Date</div><div class="value white">{trigger_date}</div></div>'
    f'<div class="metric-card"><div class="label">Run Time</div><div class="value white">{trigger_time}</div></div>'
    f'<div class="metric-card"><div class="label">Entry Index</div><div class="value yellow">{fmt_num(base_index)}</div></div>'
    f'<div class="metric-card"><div class="label">Strategies</div><div class="value white">{n_total_week}</div></div>'
    f'<div class="metric-card"><div class="label">Status</div><div style="margin-top:6px">{week_status}</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)


# ==================================================================
# TABS
# ==================================================================
all_active = week_all[~week_all["_is_settled"]]
all_history = week_all[week_all["_is_settled"]]

tab_active, tab_history = st.tabs([
    f"🔵 Open Positions ({len(all_active)})",
    f"📜 History ({len(all_history)})",
])


# ==================================================================
# ACTIVE TAB — Week → Expiry → Interval
# ==================================================================
with tab_active:
    if all_active.empty:
        st.info("אין פוזיציות פתוחות כרגע — כל האסטרטגיות של השבוע פקעו.")
    else:
        # ── P&L by interval for this tab ──
        active_intervals = sorted(all_active["interval_pct"].unique())

        interval_pnl_active = []
        for pct in active_intervals:
            idf = all_active[all_active["interval_pct"] == pct]
            total_unr = 0.0
            for _, r in idf.iterrows():
                if live_index > 0:
                    val, _ = compute_unrealized_pnl(r, live_index)
                    total_unr += val
            interval_pnl_active.append({"pct": pct, "n": len(idf), "pnl": total_unr})

        # Summary cards
        summary_html = '<div class="metric-grid">'
        for ip in interval_pnl_active:
            u_color = "green" if ip["pnl"] >= 0 else "red"
            glow = "glow-green" if ip["pnl"] >= 0 else "glow-red"
            summary_html += f'<div class="metric-card {glow}"><div class="label">{ip["pct"]:.1f}% ({ip["n"]})</div><div class="value {u_color}">{fmt_ils(ip["pnl"])}</div></div>'
        summary_html += '</div>'
        st.markdown(summary_html, unsafe_allow_html=True)

        # Step 2: Select expiry date
        active_expiry_dates = sorted(all_active["expiry_date"].unique())
        active_expiry_labels = {}
        for ed in active_expiry_dates:
            edf = all_active[all_active["expiry_date"] == ed]
            day_he = DAY_HE.get(edf.iloc[0].get("expiry_day_name", ""), "")
            n_intervals = len(edf["interval_pct"].unique())
            active_expiry_labels[ed] = f"{ed} — יום {day_he}  |  {n_intervals} מרווחים"

        render_breadcrumb([("שבוע", False), ("תאריך פקיעה", True)])

        sel_active_expiry = st.selectbox(
            "📅 תאריך פקיעה",
            active_expiry_dates,
            format_func=lambda x: active_expiry_labels.get(x, x),
            key="active_expiry",
        )

        # Filter to selected expiry
        active_by_expiry = all_active[all_active["expiry_date"] == sel_active_expiry]

        # Step 3: Select interval
        avail_intervals = sorted(active_by_expiry["interval_pct"].unique())
        interval_preview = []
        for pct in avail_intervals:
            r = active_by_expiry[active_by_expiry["interval_pct"] == pct].iloc[0]
            if live_index > 0:
                u, _ = compute_unrealized_pnl(r, live_index)
            else:
                u = 0.0
            interval_preview.append({"pct": pct, "pnl": u})

        render_breadcrumb([("שבוע", False), ("פקיעה", False), ("מרווח", True)])

        sel_active_interval = st.selectbox(
            "📐 מרווח אסטרטגיה",
            avail_intervals,
            format_func=lambda x: f"{x:.1f}%",
            key="active_interval",
        )

        # ── Render detail ──
        row = active_by_expiry[active_by_expiry["interval_pct"] == sel_active_interval].iloc[0]

        # Live index strip
        if live_index > 0:
            idx_color = "green" if live_index >= base_index else "red"
            chg_val = live_index - base_index
            chg_pct = chg_val / base_index * 100 if base_index > 0 else 0
            u_pnl, u_method = compute_unrealized_pnl(row, live_index)
            unr_color = "green" if u_pnl >= 0 else "red"
            glow = "green" if u_pnl >= 0 else "red"
            method_label = "LIVE" if u_method == "live" else "PROXY"
            st.markdown(
                f'<div class="metric-grid">'
                f'<div class="metric-card glow-{("green" if live_index >= base_index else "red")}"><div class="label">Live Index</div><div class="value {idx_color}">{fmt_num(live_index)}</div></div>'
                f'<div class="metric-card"><div class="label">Change from Entry</div><div class="value {idx_color}">{fmt_num(chg_val)} ({chg_pct:+.2f}%)</div></div>'
                f'<div class="metric-card glow-{glow}"><div class="label">Unrealized P&L ({method_label})</div><div class="value {unr_color}">{fmt_ils(u_pnl)}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        render_legs_table(row)
        render_expiry_metrics(row)

        ref_p = live_index if live_index > 0 else 0
        ref_l = f"Live: {ref_p:,.2f}" if ref_p > 0 else ""
        render_payoff_chart(row, ref_price=ref_p, ref_label=ref_l)


# ==================================================================
# HISTORY TAB — Week → Expiry → Interval
# ==================================================================
with tab_history:
    if all_history.empty:
        st.info("אין היסטוריה — אף אסטרטגיה לא פקעה עדיין.")
    else:
        # ── P&L by interval table (inside history tab) ──
        history_intervals = sorted(all_history["interval_pct"].unique())

        comparison_data = []
        for pct in history_intervals:
            idf = all_history[all_history["interval_pct"] == pct]
            actual_pnl = idf["actual_pnl_ils"].sum()
            max_possible = idf["max_profit_ils"].sum()
            n_total = len(idf)
            n_wins = int((idf["actual_pnl_ils"] > 0).sum())
            comparison_data.append({
                "pct": pct, "actual_pnl": actual_pnl,
                "max_possible": max_possible, "n_total": n_total,
                "n_wins": n_wins,
            })

        st.markdown('<div class="section-hdr">📊 מה יכולת להרוויח? — השוואת מרווחים</div>', unsafe_allow_html=True)

        # Comparison table
        best_pct = max(comparison_data, key=lambda x: x["actual_pnl"])["pct"] if comparison_data else 0
        comp_html = '<div class="table-scroll"><table><thead><tr><th>Interval</th><th>Expiries</th><th>Wins</th><th>Win Rate</th><th>Max Possible</th><th>Actual P&L</th><th>Utilization</th></tr></thead><tbody>'
        for cd in comparison_data:
            pct = cd["pct"]
            actual = cd["actual_pnl"]
            max_p = cd["max_possible"]
            wr = (cd["n_wins"] / cd["n_total"] * 100) if cd["n_total"] > 0 else 0
            util = (actual / max_p * 100) if max_p > 0 else 0
            a_css = "buy" if actual > 0 else ("sell" if actual < 0 else "")
            wr_css = "buy" if wr >= 70 else ("sell" if wr < 40 else "")
            u_css = "buy" if util > 50 else ("sell" if util < 0 else "")
            hl = ' style="background:rgba(0,230,118,0.06)"' if pct == best_pct else ""
            comp_html += f'<tr{hl}><td><strong>{pct:.1f}%</strong></td><td>{cd["n_total"]}</td><td>{cd["n_wins"]}</td><td class="{wr_css}">{wr:.0f}%</td><td class="buy">{fmt_ils(max_p)}</td><td class="{a_css}"><strong>{fmt_ils(actual)}</strong></td><td class="{u_css}">{util:.0f}%</td></tr>'
        comp_html += '</tbody></table></div>'
        st.markdown(comp_html, unsafe_allow_html=True)

        # Visual comparison bars
        st.markdown('<div class="section-hdr">📈 Max Profit vs. Actual P&L</div>', unsafe_allow_html=True)
        abs_max = max(max(abs(cd["max_possible"]), abs(cd["actual_pnl"])) for cd in comparison_data) if comparison_data else 1
        for cd in comparison_data:
            pct = cd["pct"]
            max_p = cd["max_possible"]
            actual = cd["actual_pnl"]
            max_w = (max_p / abs_max * 100) if abs_max > 0 else 0
            actual_w = (abs(actual) / abs_max * 100) if abs_max > 0 else 0
            bar_c = C_GREEN if actual >= 0 else C_RED
            st.markdown(
                f'<div class="cmp-row">'
                f'<div style="font-weight:700;color:{C_TEXT};font-size:14px;margin-bottom:6px">{pct:.1f}%</div>'
                f'<div class="cmp-line"><span class="cmp-lbl">Max</span><div class="cmp-track"><div class="cmp-fill" style="width:{max_w:.0f}%;background:{C_BLUE}"></div></div><span class="cmp-val" style="color:{C_BLUE}">{fmt_ils(max_p)}</span></div>'
                f'<div class="cmp-line"><span class="cmp-lbl">Actual</span><div class="cmp-track"><div class="cmp-fill" style="width:{actual_w:.0f}%;background:{bar_c}"></div></div><span class="cmp-val" style="color:{bar_c}">{fmt_ils(actual)}</span></div>'
                f'</div>',
                unsafe_allow_html=True,
            )

        # ── Step 2: Select expiry date ──
        st.markdown('<div class="section-hdr">🔍 ניתוח מפורט לפי פקיעה ומרווח</div>', unsafe_allow_html=True)

        hist_expiry_dates = sorted(all_history["expiry_date"].unique())
        hist_expiry_labels = {}
        for ed in hist_expiry_dates:
            edf = all_history[all_history["expiry_date"] == ed]
            day_he = DAY_HE.get(edf.iloc[0].get("expiry_day_name", ""), "")
            total_pnl_day = edf["actual_pnl_ils"].sum()
            icon = "✅" if total_pnl_day > 0 else "❌"
            hist_expiry_labels[ed] = f"{ed} — {day_he}  |  {icon} {fmt_ils(total_pnl_day)}"

        render_breadcrumb([("שבוע", False), ("תאריך פקיעה", True)])

        sel_hist_expiry = st.selectbox(
            "📅 תאריך פקיעה",
            hist_expiry_dates,
            format_func=lambda x: hist_expiry_labels.get(x, x),
            key="history_expiry",
        )

        hist_by_expiry = all_history[all_history["expiry_date"] == sel_hist_expiry]

        # Step 3: Select interval
        hist_avail_intervals = sorted(hist_by_expiry["interval_pct"].unique())

        render_breadcrumb([("שבוע", False), ("פקיעה", False), ("מרווח", True)])

        sel_hist_interval = st.selectbox(
            "📐 מרווח אסטרטגיה",
            hist_avail_intervals,
            format_func=lambda x: f"{x:.1f}%",
            key="history_interval",
        )

        row = hist_by_expiry[hist_by_expiry["interval_pct"] == sel_hist_interval].iloc[0]

        # Settlement info strip
        settle_price = row.get("actual_index_close", 0)
        sp_s = row.get("short_put_strike", 0)
        sc_s = row.get("short_call_strike", 0)
        lp_s = row.get("long_put_strike", 0)
        lc_s = row.get("long_call_strike", 0)
        zone_badge = settlement_zone_label(settle_price, sp_s, sc_s, lp_s, lc_s) if settle_price > 0 else ""

        actual_pnl = row.get("actual_pnl_ils", 0)
        max_profit = row.get("max_profit_ils", 0)
        a_color = "green" if actual_pnl >= 0 else "red"
        glow = "glow-green" if actual_pnl >= 0 else "glow-red"

        st.markdown(
            f'<div class="metric-grid">'
            f'<div class="metric-card"><div class="label">Settlement Index</div><div class="value white">{fmt_num(settle_price)}</div></div>'
            f'<div class="metric-card"><div class="label">Position</div><div style="margin-top:8px">{zone_badge}</div></div>'
            f'<div class="metric-card {glow}"><div class="label">Actual P&L</div><div class="value {a_color}">{fmt_ils(actual_pnl)}</div></div>'
            f'<div class="metric-card"><div class="label">Max Possible</div><div class="value blue">{fmt_ils(max_profit)}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        render_legs_table(row)

        # Strike vs Settlement table — where did the index land?
        strike_table = '<div class="table-scroll"><table><thead><tr><th>Strike Level</th><th>Value</th><th>Settlement</th><th>Distance</th></tr></thead><tbody>'
        strikes = [("Long Put", lp_s), ("Short Put", sp_s), ("Short Call", sc_s), ("Long Call", lc_s)]
        for label, strike_val in strikes:
            if strike_val > 0 and settle_price > 0:
                dist = settle_price - strike_val
                dist_css = "buy" if dist > 0 else "sell"
                marker = " ◄" if abs(dist) == min(abs(settle_price - s) for _, s in strikes if s > 0) else ""
                strike_table += f'<tr><td>{label}</td><td><strong>{fmt_num(strike_val, 0)}</strong></td><td>{fmt_num(settle_price)}</td><td class="{dist_css}">{dist:+.2f}{marker}</td></tr>'
        strike_table += '</tbody></table></div>'
        st.markdown(strike_table, unsafe_allow_html=True)

        render_expiry_metrics(row)

        settle_label = f"Settlement: {settle_price:,.2f}" if settle_price > 0 else ""
        render_payoff_chart(row, ref_price=settle_price, ref_label=settle_label)

        # P&L hero
        pnl_class = "profit" if actual_pnl >= 0 else "loss"
        glow_class = "glow-profit" if actual_pnl >= 0 else "glow-loss"
        st.markdown(
            f'<div class="pnl-hero {glow_class}">'
            f'<div class="title">Settlement Result — {sel_hist_expiry} @ {sel_hist_interval:.1f}%</div>'
            f'<div class="amount {pnl_class}">{fmt_ils(actual_pnl)}</div>'
            f'<div style="color:{C_DIM};font-size:13px;margin-top:8px">out of max possible: {fmt_ils(max_profit)}</div>'
            f'</div>',
            unsafe_allow_html=True,
        )


# ==================================================================
# FOOTER
# ==================================================================
st.markdown(f"""
<div style="text-align:center; padding:30px 0 10px; color:{C_DIM}; font-size:11px;">
    TA-35 Iron Condor Strategy Desk &mdash; Automated Pipeline<br>
    Auto-refresh 2 min &nbsp;|&nbsp; Multiplier: {MULTIPLIER}₪/pt
    &nbsp;|&nbsp; {now_il.strftime("%H:%M:%S")} IL
</div>
""", unsafe_allow_html=True)
