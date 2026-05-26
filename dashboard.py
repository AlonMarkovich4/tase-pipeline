"""
TASE TA-35 — Options Trading Playground
========================================
Free-form options sandbox with multi-portfolio management,
live options chain, custom strategy builder, payoff visualization,
and an expiry simulator. Production analytics in a secondary tab.
"""

import os, math, uuid
import streamlit as st
import pandas as pd
import numpy as np
import httpx
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# ==================================================================
# CONFIG
# ==================================================================
st.set_page_config(page_title="TA-35 Playground", page_icon="◆",
                   layout="wide")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")
DAYS_HE = {0: "שני", 1: "שלישי", 2: "רביעי",
            3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"}
MULTIPLIER = 50
DEFAULT_BALANCE = 100_000

# Palette
C_BG     = "#0B0D10"
C_CARD   = "#151921"
C_BORDER = "#1E2433"
C_TEXT   = "#E8EAED"
C_DIM    = "#6B7B8D"
C_GREEN  = "#00E676"
C_RED    = "#FF1744"
C_BLUE   = "#00B0FF"
C_YELLOW = "#FFD600"
C_PURPLE = "#E040FB"
C_GRID   = "#1A1F2B"

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
    direction: rtl; text-align: right;
    padding: 1.2rem 2rem 2rem !important;
    max-width: 1440px;
}}
[data-testid="stSidebar"] {{
    direction: rtl; text-align: right;
    background: {C_BG} !important;
    border-left: 1px solid {C_BORDER} !important;
}}
[data-testid="stSidebar"] > div:first-child {{
    background: {C_BG} !important;
}}
[data-testid="stMarkdownContainer"],
[data-testid="stAlert"],
[data-testid="stRadio"] > div,
[data-testid="stRadio"] label,
[data-testid="stSelectbox"] label {{
    direction: rtl; text-align: right;
}}
#MainMenu, footer, header {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}

/* KPI cards */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(180px, 1fr));
    gap: 12px; margin-bottom: 20px;
}}
.kpi {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 16px 18px;
    position: relative; overflow: hidden;
}}
.kpi::after {{
    content: '';
    position: absolute; top: 0; right: 0;
    width: 4px; height: 100%;
    border-radius: 0 10px 10px 0;
}}
.kpi.ag::after {{ background: {C_GREEN}; }}
.kpi.ar::after {{ background: {C_RED}; }}
.kpi.ab::after {{ background: {C_BLUE}; }}
.kpi.ad::after {{ background: {C_DIM}; }}
.kpi.ay::after {{ background: {C_YELLOW}; }}
.kpi.ap::after {{ background: {C_PURPLE}; }}
.kpi .lb {{
    font-size: 10px; font-weight: 700;
    color: {C_DIM}; text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 4px;
}}
.kpi .vl {{
    font-size: 22px; font-weight: 700;
    color: {C_TEXT};
    direction: ltr; unicode-bidi: isolate;
}}
.kpi .vl.sm {{ font-size: 16px; }}
.kpi .vl.g {{ color: {C_GREEN}; }}
.kpi .vl.r {{ color: {C_RED}; }}
.kpi .vl.b {{ color: {C_BLUE}; }}
.kpi .vl.y {{ color: {C_YELLOW}; }}
.kpi .sb {{
    font-size: 10px; color: {C_DIM};
    margin-top: 2px; direction: ltr;
    unicode-bidi: isolate;
}}

/* Section header */
.sec {{
    display: flex; align-items: center; gap: 8px;
    font-size: 15px; font-weight: 700; color: {C_TEXT};
    margin: 18px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid {C_BORDER};
}}

/* Badges */
.badge {{
    display: inline-block;
    font-size: 9px; font-weight: 800;
    padding: 2px 8px; border-radius: 4px;
    letter-spacing: 0.5px; margin-right: 6px;
}}
.badge.sandbox {{
    background: rgba(255,214,0,0.12);
    color: {C_YELLOW};
    border: 1px solid rgba(255,214,0,0.3);
}}
.badge.buy {{
    background: rgba(0,230,118,0.12);
    color: {C_GREEN};
    border: 1px solid rgba(0,230,118,0.3);
}}
.badge.sell {{
    background: rgba(255,23,68,0.12);
    color: {C_RED};
    border: 1px solid rgba(255,23,68,0.3);
}}

/* Sidebar */
.sb-brand {{ text-align: center; padding: 16px 0 8px; }}
.sb-brand .logo {{
    font-size: 10px; font-weight: 800;
    letter-spacing: 3px; color: {C_BLUE};
}}
.sb-brand .title {{
    font-size: 17px; font-weight: 800;
    color: {C_TEXT}; margin-top: 3px;
}}
.sb-clock {{
    text-align: center; font-size: 12px;
    color: {C_DIM}; margin: 4px 0 8px;
}}
@keyframes pulse {{
    0%,100% {{ opacity:1; }} 50% {{ opacity:0.3; }}
}}
.live-dot {{
    display: inline-block; width: 7px; height: 7px;
    border-radius: 50%; margin-left: 5px;
    vertical-align: middle;
}}
.live-dot.on {{
    background: {C_GREEN};
    box-shadow: 0 0 6px {C_GREEN};
    animation: pulse 2s ease-in-out infinite;
}}
.live-dot.off {{ background: {C_DIM}; }}

/* Buttons */
.stButton > button {{
    background: {C_CARD} !important;
    color: {C_DIM} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    transition: all 0.15s !important;
}}
.stButton > button:hover {{
    background: {C_BORDER} !important;
    color: {C_TEXT} !important;
    border-color: {C_BLUE} !important;
}}

/* DataFrames */
div[data-testid="stDataFrame"] {{
    border: 1px solid {C_BORDER};
    border-radius: 8px; overflow: hidden;
}}

hr {{ border-color: {C_BORDER} !important; opacity: 0.4 !important; }}
[data-testid="stMetric"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)


# ==================================================================
# HELPERS
# ==================================================================
def _hdr():
    return {"apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}


@st.cache_data(ttl=60)
def fetch(table, params=""):
    try:
        r = httpx.get(f"{SUPABASE_URL}/rest/v1/{table}?select=*{params}",
                      headers=_hdr(), timeout=15)
        if r.status_code in (200, 206):
            d = r.json()
            if d:
                return pd.DataFrame(d)
    except Exception:
        pass
    return pd.DataFrame()


def N(val):
    if val is None or val == "":
        return None
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return None


def fmt(val, dec=0):
    v = N(val)
    if v is None:
        return "—"
    return f"{v:,.{dec}f}"


@st.cache_data(ttl=60)
def _fetch_ta35_yahoo() -> float:
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/TA35.TA"
               "?interval=1d&range=1d")
        r = httpx.get(url, timeout=10,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            meta = (r.json().get("chart", {})
                    .get("result", [{}])[0].get("meta", {}))
            p = meta.get("regularMarketPrice", 0)
            if p and p > 0:
                return float(p)
    except Exception:
        pass
    return 0.0


def get_idx(df):
    yf = _fetch_ta35_yahoo()
    if yf > 0:
        return yf
    for c in ["underlingasset_call", "underlingasset_put"]:
        if c in df.columns:
            for v in df[c]:
                x = N(v)
                if x and x > 0:
                    return x
    return 0.0


def relative_time(dt_str, tm_str=""):
    try:
        s = f"{dt_str} {tm_str}".strip()
        for f in ["%Y-%m-%d %H:%M", "%Y-%m-%d"]:
            try:
                t = datetime.strptime(s, f).replace(tzinfo=TZ)
                break
            except ValueError:
                continue
        else:
            return s
        now_t = datetime.now(TZ)
        diff = now_t - t
        mins = int(diff.total_seconds() / 60)
        if mins < 1:
            return "עכשיו"
        if mins < 60:
            return f"לפני {mins} דקות"
        hrs = mins // 60
        if hrs < 24:
            return f"לפני {hrs} שעות"
        return f"לפני {diff.days} ימים"
    except Exception:
        return dt_str


def plotly_dark(fig, h=None):
    fig.update_layout(
        plot_bgcolor=C_CARD, paper_bgcolor=C_CARD,
        font=dict(family="Inter, sans-serif", color=C_TEXT, size=12),
        margin=dict(l=20, r=20, t=30, b=20),
        xaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID,
                   tickfont=dict(size=10, color=C_DIM)),
        yaxis=dict(gridcolor=C_GRID, zerolinecolor=C_GRID,
                   tickfont=dict(size=10, color=C_DIM)),
        hoverlabel=dict(bgcolor=C_CARD, bordercolor=C_BORDER,
                        font=dict(color=C_TEXT, size=12)),
        legend=dict(font=dict(size=11, color=C_DIM)),
        height=h,
    )
    return fig


# ==================================================================
# SESSION STATE INIT
# ==================================================================
if "portfolios" not in st.session_state:
    st.session_state.portfolios = {}
if "active_portfolio" not in st.session_state:
    st.session_state.active_portfolio = None
if "leg_builder" not in st.session_state:
    st.session_state.leg_builder = []


# ==================================================================
# SIDEBAR
# ==================================================================
now = datetime.now(TZ)
is_live = now.weekday() in {0, 1, 2, 3, 4} and 9 <= now.hour < 18

st.sidebar.markdown("""
<div class="sb-brand">
    <div class="logo">◆ TASE TERMINAL</div>
    <div class="title">TA-35 Playground</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown(
    f'<div class="sb-clock">יום {DAYS_HE.get(now.weekday(), "")} · '
    f'{now.strftime("%d/%m/%Y")} · {now.strftime("%H:%M:%S")}</div>',
    unsafe_allow_html=True)

dot = "on" if is_live else "off"
mkt = "MARKET OPEN" if is_live else "MARKET CLOSED"
st.sidebar.markdown(
    f'<div style="text-align:center;font-size:11px;font-weight:700;'
    f'padding:6px;border-radius:6px;margin:6px 8px;'
    f'background:rgba({"0,230,118" if is_live else "107,123,141"},0.08);'
    f'border:1px solid rgba({"0,230,118" if is_live else "107,123,141"},0.25);'
    f'color:{"#00E676" if is_live else "#6B7B8D"}">'
    f'<span class="live-dot {dot}"></span> {mkt}</div>',
    unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 רענן נתונים", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("v4.0 · Playground · Render · Supabase")


# ==================================================================
# FETCH LIVE DATA ONCE
# ==================================================================
df_live = fetch("tase_putcall")
IDX = get_idx(df_live) if not df_live.empty else 0.0


# ██████████████████████████████████████████████████████████████████
# MAIN TABS
# ██████████████████████████████████████████████████████████████████
tab_play, tab_prod = st.tabs([
    "🎮 מגרש משחקים — Options Playground",
    "📊 מוניטור מערכת אוטומטית ואנליטיקה",
])


# ██████████████████████████████████████████████████████████████████
# TAB 1: PLAYGROUND
# ██████████████████████████████████████████████████████████████████
with tab_play:

    # ==============================================================
    # 1A. PORTFOLIO MANAGEMENT BAR
    # ==============================================================
    st.markdown(
        '<div class="sec"><span class="badge sandbox">SANDBOX</span>'
        'ניהול תיקים מדומים</div>',
        unsafe_allow_html=True)

    pcol1, pcol2 = st.columns([3, 2])

    # ---- Active portfolio selector ----
    with pcol1:
        names = list(st.session_state.portfolios.keys())
        if names:
            sel_name = st.selectbox(
                "בחר תיק פעיל לעבודה", names,
                index=(names.index(st.session_state.active_portfolio)
                       if st.session_state.active_portfolio in names
                       else 0),
                key="port_select")
            st.session_state.active_portfolio = sel_name
        else:
            st.info("אין תיקים — צור תיק חדש כדי להתחיל.")

    # ---- Create new portfolio ----
    with pcol2:
        with st.expander("➕ פתח תיק מסחר מדומה חדש", expanded=not names):
            new_name = st.text_input(
                "שם התיק", placeholder='למשל "תיק שמרני"',
                key="new_port_name")
            new_balance = st.number_input(
                "יתרת פתיחה (₪)", min_value=10_000,
                max_value=10_000_000, value=DEFAULT_BALANCE,
                step=10_000, key="new_port_bal")
            if st.button("🚀 צור תיק", key="create_port_btn",
                         use_container_width=True):
                if new_name and new_name.strip():
                    name = new_name.strip()
                    if name in st.session_state.portfolios:
                        st.error(f"תיק בשם \"{name}\" כבר קיים.")
                    else:
                        st.session_state.portfolios[name] = {
                            "balance": float(new_balance),
                            "initial": float(new_balance),
                            "trades": [],
                            "history": [],
                            "created": now.strftime("%Y-%m-%d %H:%M"),
                        }
                        st.session_state.active_portfolio = name
                        st.success(f"✅ תיק \"{name}\" נוצר — ₪{new_balance:,.0f}")
                        st.rerun()
                else:
                    st.warning("הזן שם לתיק.")

    # ---- Stop if no active portfolio ----
    port = None
    if st.session_state.active_portfolio:
        port = st.session_state.portfolios.get(
            st.session_state.active_portfolio)

    if not port:
        st.stop()

    # ---- Portfolio KPIs ----
    active_trades = port["trades"]
    history = port["history"]
    balance = port["balance"]
    initial = port["initial"]
    realized = sum(t.get("pnl_ils", 0) for t in history)
    bal_cls = "g" if balance >= initial else "r"
    real_cls = "g" if realized >= 0 else "r"

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi ay">
            <div class="lb">יתרה — {st.session_state.active_portfolio}</div>
            <div class="vl {bal_cls}">₪{balance:,.0f}</div>
            <div class="sb">התחלה: ₪{initial:,.0f}</div>
        </div>
        <div class="kpi ag">
            <div class="lb">TA-35 LIVE</div>
            <div class="vl g">{fmt(IDX, 2)}</div>
        </div>
        <div class="kpi ab">
            <div class="lb">פוזיציות פתוחות</div>
            <div class="vl b">{len(active_trades)}</div>
        </div>
        <div class="kpi ad">
            <div class="lb">P&L מומש</div>
            <div class="vl {real_cls}">{realized:+,.0f} ₪</div>
            <div class="sb">{len(history)} עסקאות</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ==============================================================
    # 1B. OPTIONS CHAIN + FREE-FORM STRATEGY BUILDER
    # ==============================================================
    st.markdown('<div class="sec">בניית אסטרטגיה חופשית</div>',
                unsafe_allow_html=True)

    if IDX <= 0 or df_live.empty:
        st.warning("אין נתוני שוק — לא ניתן לבנות אסטרטגיה.")
        st.stop()

    # ---- Expiry selector ----
    if "expiry_date" in df_live.columns:
        today_str = date.today().isoformat()
        all_exp = sorted(df_live["expiry_date"].unique())
        future_exp = [e for e in all_exp if e > today_str] or all_exp[-3:]
        exp_labels = []
        for e in future_exp:
            try:
                d = date.fromisoformat(e)
                exp_labels.append(
                    f"יום {DAYS_HE.get(d.weekday(), '')} — {e}")
            except Exception:
                exp_labels.append(e)
        sel_exp_label = st.selectbox(
            "בחר יום פקיעה", exp_labels, index=0,
            key="chain_expiry")
        sel_exp = future_exp[exp_labels.index(sel_exp_label)]
        df_chain = df_live[df_live["expiry_date"] == sel_exp].copy()
    else:
        df_chain = df_live.copy()
        sel_exp = "N/A"

    # ---- Build options chain grid ----
    chain_rows = []
    for _, row in df_chain.iterrows():
        strike_c = N(row.get("expirationprice_call"))
        strike_p = N(row.get("expirationprice_put"))
        strike = strike_c or strike_p
        if not strike or strike <= 0:
            continue
        chain_rows.append({
            "strike": strike,
            "call_price": N(row.get("lastrate_call")) or 0,
            "call_oi": N(row.get("openpositions_call")) or 0,
            "call_delta": N(row.get("delta_call")) or 0,
            "call_name": str(row.get("derivativename_call", "")).strip(),
            "put_price": N(row.get("lastrate_put")) or 0,
            "put_oi": N(row.get("openpositions_put")) or 0,
            "put_delta": N(row.get("delta_put")) or 0,
            "put_name": str(row.get("derivativename_put", "")).strip(),
        })

    chain_rows.sort(key=lambda x: x["strike"])

    if not chain_rows:
        st.info("אין נתוני שרשרת אופציות ליום פקיעה זה.")
        st.stop()

    # Display chain
    st.markdown(
        f'<div style="font-size:12px;color:{C_DIM};margin-bottom:8px;">'
        f'שרשרת אופציות — {sel_exp} | '
        f'TA-35: {IDX:,.2f} | '
        f'{len(chain_rows)} strikes</div>',
        unsafe_allow_html=True)

    display_chain = []
    for cr in chain_rows:
        itm_call = "◀" if cr["strike"] < IDX else ""
        itm_put = "◀" if cr["strike"] > IDX else ""
        atm = " ★" if abs(cr["strike"] - IDX) < 15 else ""
        display_chain.append({
            "Call Δ": f'{cr["call_delta"]:.2f}' if cr["call_delta"] else "—",
            "Call O.I": f'{cr["call_oi"]:,.0f}' if cr["call_oi"] else "—",
            "Call ₪": f'{cr["call_price"]:,.1f}' if cr["call_price"] else "—",
            f"{itm_call}": "",
            f"Strike{atm}": f'{cr["strike"]:,.0f}',
            f" {itm_put}": "",
            "Put ₪": f'{cr["put_price"]:,.1f}' if cr["put_price"] else "—",
            "Put O.I": f'{cr["put_oi"]:,.0f}' if cr["put_oi"] else "—",
            "Put Δ": f'{cr["put_delta"]:.2f}' if cr["put_delta"] else "—",
        })

    st.dataframe(pd.DataFrame(display_chain),
                 use_container_width=True, height=320, hide_index=True)

    # ---- Leg builder ----
    st.markdown('<div class="sec">הוסף רגליים לאסטרטגיה</div>',
                unsafe_allow_html=True)

    strikes_list = [cr["strike"] for cr in chain_rows]

    leg_col1, leg_col2, leg_col3, leg_col4 = st.columns([1.5, 1.5, 1.5, 1])

    with leg_col1:
        leg_type = st.selectbox("סוג", ["Call", "Put"],
                                key="leg_type_sel")

    with leg_col2:
        leg_action = st.selectbox("פעולה",
                                  ["Sell (Short)", "Buy (Long)"],
                                  key="leg_action_sel")

    with leg_col3:
        # Find ATM strike as default
        atm_idx = 0
        min_diff = float("inf")
        for i, s in enumerate(strikes_list):
            d = abs(s - IDX)
            if d < min_diff:
                min_diff = d
                atm_idx = i
        leg_strike = st.selectbox(
            "Strike",
            [f"{s:,.0f}" for s in strikes_list],
            index=atm_idx,
            key="leg_strike_sel")
        leg_strike_val = strikes_list[
            [f"{s:,.0f}" for s in strikes_list].index(leg_strike)]

    with leg_col4:
        leg_qty = st.number_input(
            "כמות", min_value=1, max_value=100,
            value=1, step=1, key="leg_qty")

    # Look up price
    cr_match = next(
        (c for c in chain_rows if c["strike"] == leg_strike_val), None)
    if cr_match:
        if leg_type == "Call":
            leg_price = cr_match["call_price"]
        else:
            leg_price = cr_match["put_price"]
    else:
        leg_price = 0

    is_sell = "Sell" in leg_action
    leg_sign = 1 if is_sell else -1  # sell = receive premium, buy = pay

    if st.button("➕ הוסף רגל", key="add_leg_btn",
                 use_container_width=True):
        st.session_state.leg_builder.append({
            "type": leg_type,
            "action": "Sell" if is_sell else "Buy",
            "strike": leg_strike_val,
            "price": leg_price,
            "qty": leg_qty,
            "sign": leg_sign,
        })
        st.rerun()

    # ---- Current legs preview ----
    legs = st.session_state.leg_builder
    if legs:
        st.markdown('<div class="sec">רגליים באסטרטגיה הנוכחית</div>',
                    unsafe_allow_html=True)

        total_credit = 0
        leg_display = []
        for j, leg in enumerate(legs):
            prem = leg["sign"] * leg["price"] * leg["qty"] * MULTIPLIER
            total_credit += prem
            badge_cls = "sell" if leg["action"] == "Sell" else "buy"
            leg_display.append({
                "#": j + 1,
                "סוג": leg["type"],
                "פעולה": leg["action"],
                "Strike": f'{leg["strike"]:,.0f}',
                "מחיר": f'{leg["price"]:,.2f}',
                "כמות": leg["qty"],
                "פרמיה ₪": f'{prem:+,.0f}',
            })

        st.dataframe(pd.DataFrame(leg_display),
                     use_container_width=True, hide_index=True)

        # Net premium summary
        prem_cls = C_GREEN if total_credit >= 0 else C_RED
        prem_label = "קרדיט (מקבל)" if total_credit >= 0 else "דביט (משלם)"
        st.markdown(
            f'<div style="text-align:center;padding:10px 0;">'
            f'<span style="font-size:11px;color:{C_DIM};">'
            f'פרמיה נטו — {prem_label}</span><br>'
            f'<span style="font-size:26px;font-weight:800;'
            f'color:{prem_cls};">'
            f'{total_credit:+,.0f} ₪</span></div>',
            unsafe_allow_html=True)

        # Action buttons
        btn_col1, btn_col2, btn_col3 = st.columns(3)
        with btn_col1:
            if st.button("🚀 שגר אסטרטגיה לתיק הנבחר",
                         key="launch_strat_btn",
                         use_container_width=True):
                trade = {
                    "id": str(uuid.uuid4())[:8],
                    "timestamp": now.strftime("%Y-%m-%d %H:%M"),
                    "expiry": sel_exp,
                    "legs": [dict(l) for l in legs],
                    "net_premium_ils": round(total_credit, 2),
                    "base_index": round(IDX, 2),
                    "status": "OPEN",
                }
                port["trades"].append(trade)
                st.session_state.leg_builder = []
                st.success(
                    f"✅ אסטרטגיה עם {len(legs)} רגליים נשלחה "
                    f"לתיק \"{st.session_state.active_portfolio}\"")
                st.rerun()

        with btn_col2:
            if st.button("🗑️ נקה רגליים", key="clear_legs_btn",
                         use_container_width=True):
                st.session_state.leg_builder = []
                st.rerun()

        with btn_col3:
            if st.button("🔄 Iron Condor מהיר",
                         key="quick_condor_btn",
                         use_container_width=True):
                # Auto-populate a standard condor
                pct = 2.0
                offset = IDX * (pct / 100.0)
                sp_t = IDX - offset
                sc_t = IDX + offset
                lp_t = sp_t - 20
                lc_t = sc_t + 20

                def _closest(target, slist):
                    return min(slist, key=lambda s: abs(s - target))

                sp_s = _closest(sp_t, strikes_list)
                sc_s = _closest(sc_t, strikes_list)
                lp_s = _closest(lp_t, strikes_list)
                lc_s = _closest(lc_t, strikes_list)

                def _get_price(strike, side):
                    m = next(
                        (c for c in chain_rows if c["strike"] == strike),
                        None)
                    return m[f"{side}_price"] if m else 0

                st.session_state.leg_builder = [
                    {"type": "Put", "action": "Buy",
                     "strike": lp_s, "price": _get_price(lp_s, "put"),
                     "qty": 1, "sign": -1},
                    {"type": "Put", "action": "Sell",
                     "strike": sp_s, "price": _get_price(sp_s, "put"),
                     "qty": 1, "sign": 1},
                    {"type": "Call", "action": "Sell",
                     "strike": sc_s, "price": _get_price(sc_s, "call"),
                     "qty": 1, "sign": 1},
                    {"type": "Call", "action": "Buy",
                     "strike": lc_s, "price": _get_price(lc_s, "call"),
                     "qty": 1, "sign": -1},
                ]
                st.rerun()

    # ==============================================================
    # 1C. ACTIVE POSITIONS + PAYOFF + SIMULATOR
    # ==============================================================
    st.markdown("---")
    st.markdown('<div class="sec">פוזיציות פתוחות בתיק</div>',
                unsafe_allow_html=True)

    if not port["trades"]:
        st.info("אין פוזיציות פתוחות. בנה אסטרטגיה למעלה.")
    else:
        for ti, trade in enumerate(port["trades"]):
            t_legs = trade["legs"]
            t_prem = trade["net_premium_ils"]

            # Header
            leg_desc = " + ".join(
                f'{l["action"]} {l["qty"]}×{l["type"]} {l["strike"]:,.0f}'
                for l in t_legs)
            st.markdown(
                f'<div style="font-size:14px;font-weight:700;'
                f'color:{C_TEXT};margin:12px 0 6px;">'
                f'#{trade["id"]} — {leg_desc}'
                f'<span class="badge sandbox" '
                f'style="margin-right:10px;">OPEN</span></div>',
                unsafe_allow_html=True)

            # KPIs
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi ab">
                    <div class="lb">כניסה</div>
                    <div class="vl sm b">{trade["base_index"]:,.2f}</div>
                </div>
                <div class="kpi {"ag" if t_prem >= 0 else "ar"}">
                    <div class="lb">פרמיה נטו</div>
                    <div class="vl {"g" if t_prem >= 0 else "r"}">{t_prem:+,.0f} ₪</div>
                </div>
                <div class="kpi ad">
                    <div class="lb">פקיעה</div>
                    <div class="vl sm">{trade["expiry"]}</div>
                </div>
                <div class="kpi ad">
                    <div class="lb">רגליים</div>
                    <div class="vl sm">{len(t_legs)}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # ---- Payoff diagram ----
            all_strikes = sorted(set(l["strike"] for l in t_legs))
            if all_strikes:
                pad = max(50, (all_strikes[-1] - all_strikes[0]) * 0.4)
                x_range = np.linspace(
                    all_strikes[0] - pad, all_strikes[-1] + pad, 300)

                payoff = np.zeros_like(x_range)
                for leg in t_legs:
                    s = leg["strike"]
                    p = leg["price"]
                    q = leg["qty"]
                    sign = leg["sign"]

                    if leg["type"] == "Call":
                        intrinsic = np.maximum(x_range - s, 0)
                    else:
                        intrinsic = np.maximum(s - x_range, 0)

                    if leg["action"] == "Sell":
                        leg_pnl = (p - intrinsic) * q * MULTIPLIER
                    else:
                        leg_pnl = (intrinsic - p) * q * MULTIPLIER

                    payoff += leg_pnl

                # Colors
                colors = np.where(payoff >= 0, C_GREEN, C_RED)

                fig = go.Figure()
                # Fill areas
                fig.add_trace(go.Scatter(
                    x=x_range, y=np.maximum(payoff, 0),
                    fill="tozeroy",
                    fillcolor="rgba(0,230,118,0.08)",
                    line=dict(width=0),
                    showlegend=False, hoverinfo="skip"))
                fig.add_trace(go.Scatter(
                    x=x_range, y=np.minimum(payoff, 0),
                    fill="tozeroy",
                    fillcolor="rgba(255,23,68,0.08)",
                    line=dict(width=0),
                    showlegend=False, hoverinfo="skip"))
                # Main line
                fig.add_trace(go.Scatter(
                    x=x_range, y=payoff,
                    mode="lines",
                    line=dict(color=C_BLUE, width=2),
                    name="P&L at Expiry",
                    hovertemplate=(
                        "מדד: %{x:,.0f}<br>"
                        "P&L: ₪%{y:,.0f}<extra></extra>"
                    )))

                # Zero line
                fig.add_hline(y=0, line=dict(color=C_DIM, width=1,
                                             dash="dot"))

                # Strike markers
                for s in all_strikes:
                    fig.add_vline(
                        x=s, line=dict(color=C_DIM, width=1, dash="dot"))
                    fig.add_annotation(
                        x=s, y=0, text=f"{s:,.0f}",
                        showarrow=True, arrowhead=0, arrowcolor=C_DIM,
                        ay=-25, font=dict(size=9, color=C_DIM))

                # Live index
                if IDX > 0:
                    fig.add_vline(
                        x=IDX,
                        line=dict(color=C_BLUE, width=2, dash="dash"))
                    fig.add_annotation(
                        x=IDX, y=max(payoff) * 0.8,
                        text=f"TA-35: {IDX:,.0f}",
                        showarrow=False,
                        font=dict(size=10, color=C_BLUE,
                                  family="Inter"))

                fig.update_layout(
                    showlegend=False,
                    xaxis_title="מדד TA-35 בפקיעה",
                    yaxis_title="P&L (₪)",
                )
                plotly_dark(fig, h=300)
                st.plotly_chart(fig, use_container_width=True,
                                key=f"payoff_{trade['id']}")

            # ---- Expiry simulator ----
            with st.expander("⚡ סימולטור פקיעה"):
                mock = st.number_input(
                    "מחיר פקיעה מדומה",
                    min_value=1000.0, max_value=10000.0,
                    value=float(IDX) if IDX > 0 else 2000.0,
                    step=10.0,
                    key=f"sim_price_{trade['id']}")

                # Calculate PnL at mock price
                sim_pnl = 0
                for leg in t_legs:
                    s = leg["strike"]
                    p = leg["price"]
                    q = leg["qty"]
                    if leg["type"] == "Call":
                        intr = max(mock - s, 0)
                    else:
                        intr = max(s - mock, 0)
                    if leg["action"] == "Sell":
                        sim_pnl += (p - intr) * q * MULTIPLIER
                    else:
                        sim_pnl += (intr - p) * q * MULTIPLIER

                sim_pnl = round(sim_pnl, 2)
                sim_c = C_GREEN if sim_pnl >= 0 else C_RED

                st.markdown(
                    f'<div style="text-align:center;padding:8px 0;">'
                    f'<span style="font-size:24px;font-weight:800;'
                    f'color:{sim_c};">'
                    f'{sim_pnl:+,.0f} ₪</span></div>',
                    unsafe_allow_html=True)

                if st.button(
                    f"⚡ סגור פוזיציה #{trade['id']} ועדכן יתרה",
                    key=f"settle_{trade['id']}",
                    use_container_width=True,
                ):
                    closed = port["trades"].pop(ti)
                    closed["status"] = "SETTLED"
                    closed["settlement_price"] = mock
                    closed["pnl_ils"] = sim_pnl
                    closed["settled_at"] = now.strftime("%Y-%m-%d %H:%M")
                    port["history"].append(closed)
                    port["balance"] += sim_pnl
                    st.success(
                        f"פוזיציה #{closed['id']} נסגרה — "
                        f"P&L: {sim_pnl:+,.0f} ₪ | "
                        f"יתרה: ₪{port['balance']:,.0f}")
                    st.rerun()

            st.markdown("---")

    # ==============================================================
    # 1D. TRADE HISTORY
    # ==============================================================
    if port["history"]:
        st.markdown('<div class="sec">היסטוריית עסקאות</div>',
                    unsafe_allow_html=True)

        hist_rows = []
        for t in reversed(port["history"]):
            pnl = t.get("pnl_ils", 0)
            leg_s = " | ".join(
                f'{l["action"][0]}·{l["type"][0]} {l["strike"]:,.0f}'
                for l in t["legs"])
            hist_rows.append({
                "#": t["id"],
                "פתיחה": t["timestamp"],
                "סגירה": t.get("settled_at", ""),
                "רגליים": leg_s,
                "כניסה": f'{t["base_index"]:,.2f}',
                "פקיעה": f'{t.get("settlement_price", 0):,.2f}',
                "P&L ₪": f'{pnl:+,.0f}',
            })
        st.dataframe(pd.DataFrame(hist_rows),
                     use_container_width=True, hide_index=True)

        # Cumulative P&L chart
        pnls = [t.get("pnl_ils", 0) for t in port["history"]]
        cum = []
        r = 0
        for p in pnls:
            r += p
            cum.append(r)

        if len(cum) > 1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(range(1, len(cum) + 1)), y=cum,
                mode="lines+markers",
                line=dict(
                    color=C_GREEN if cum[-1] >= 0 else C_RED,
                    width=2.5),
                marker=dict(size=5),
                hovertemplate=(
                    "עסקה #%{x}<br>"
                    "P&L מצטבר: ₪%{y:,.0f}<extra></extra>"),
            ))
            fig.update_layout(
                showlegend=False,
                xaxis_title="עסקה #",
                yaxis_title="P&L מצטבר (₪)")
            plotly_dark(fig, h=220)
            st.plotly_chart(fig, use_container_width=True,
                            key="hist_cum_chart")

    # ---- Portfolio controls ----
    st.markdown("---")
    ctrl1, ctrl2, ctrl3 = st.columns([2, 1, 1])
    with ctrl2:
        if st.button("🗑️ אפס תיק נוכחי", key="reset_port_btn"):
            port["balance"] = port["initial"]
            port["trades"] = []
            port["history"] = []
            st.session_state.leg_builder = []
            st.rerun()
    with ctrl3:
        if st.button("❌ מחק תיק", key="delete_port_btn"):
            name = st.session_state.active_portfolio
            del st.session_state.portfolios[name]
            remaining = list(st.session_state.portfolios.keys())
            st.session_state.active_portfolio = (
                remaining[0] if remaining else None)
            st.session_state.leg_builder = []
            st.rerun()


# ██████████████████████████████████████████████████████████████████
# TAB 2: PRODUCTION MONITOR & ANALYTICS
# ██████████████████████████████████████████████████████████████████
with tab_prod:
    prod_page = st.radio(
        "ניווט", ["מוניטור חי", "אסטרטגיות", "ביצועים"],
        horizontal=True, label_visibility="collapsed",
        key="prod_nav")

    # ==============================================================
    # PROD PAGE 1: LIVE MONITOR
    # ==============================================================
    if prod_page == "מוניטור חי":
        dot_html = f'<span class="live-dot {"on" if is_live else "off"}"></span>'
        st.markdown(
            f'<div class="sec">{dot_html} מוניטור חי — Put / Call</div>',
            unsafe_allow_html=True)

        df = df_live
        if df.empty:
            st.warning("אין נתונים זמינים כרגע.")
            st.stop()

        fd = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else ""
        ft = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        n_exp = df["expiry_date"].nunique() if "expiry_date" in df.columns else 0
        rel = relative_time(fd, ft)

        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi ag">
                <div class="lb">TA-35 INDEX</div>
                <div class="vl g">{fmt(IDX, 2)}</div>
            </div>
            <div class="kpi ab">
                <div class="lb">LAST UPDATE</div>
                <div class="vl sm">{ft or '—'}</div>
                <div class="sb">{rel}</div>
            </div>
            <div class="kpi ad">
                <div class="lb">EXPIRY DATES</div>
                <div class="vl">{n_exp}</div>
            </div>
            <div class="kpi ad">
                <div class="lb">TOTAL ROWS</div>
                <div class="vl">{len(df)}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if "expiry_date" in df.columns:
            exps = sorted(df["expiry_date"].unique())
            labels = []
            for e in exps:
                try:
                    d = date.fromisoformat(e)
                    labels.append(f"יום {DAYS_HE.get(d.weekday(), '')} — {e}")
                except Exception:
                    labels.append(e)
            sel = st.selectbox("בחר יום פקיעה", labels, index=0,
                               key="prod_exp_sel")
            df = df[df["expiry_date"] == exps[labels.index(sel)]]

        rows = []
        for _, r in df.iterrows():
            sc = N(r.get("expirationprice_call"))
            sp = N(r.get("expirationprice_put"))
            if sc is None and sp is None:
                continue
            rows.append({
                "Strike": fmt(sc or sp),
                "Call": str(r.get("derivativename_call", "") or "").strip() or "—",
                "מחיר Call": fmt(r.get("lastrate_call")),
                "O.I Call": fmt(r.get("openpositions_call")),
                "Put": str(r.get("derivativename_put", "") or "").strip() or "—",
                "מחיר Put": fmt(r.get("lastrate_put")),
                "O.I Put": fmt(r.get("openpositions_put")),
            })
        if rows:
            st.dataframe(pd.DataFrame(rows), use_container_width=True,
                         height=540, hide_index=True)

    # ==============================================================
    # PROD PAGE 2: STRATEGIES
    # ==============================================================
    elif prod_page == "אסטרטגיות":
        st.markdown('<div class="sec">אסטרטגיות Iron Condor — מערכת אוטומטית</div>',
                    unsafe_allow_html=True)

        df_s = fetch("iron_condor_strategies",
                     "&order=trigger_date.desc,expiry_date,interval_pct")
        if df_s.empty:
            st.info("אין אסטרטגיות עדיין.")
            st.stop()

        today_d = date.today()
        mon = today_d - timedelta(days=today_d.weekday())
        fri = mon + timedelta(days=4)
        df_s["_dt"] = pd.to_datetime(df_s["trigger_date"], errors="coerce")
        df_w = df_s[(df_s["_dt"] >= pd.Timestamp(mon)) &
                    (df_s["_dt"] <= pd.Timestamp(fri))].copy()
        if df_w.empty:
            latest = df_s["trigger_date"].max()
            df_w = df_s[df_s["trigger_date"] == latest].copy()
            st.caption(f"אין אסטרטגיות השבוע — מציג {latest}")

        if IDX > 0:
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi ag" style="max-width:260px;">
                    <div class="lb">CURRENT TA-35</div>
                    <div class="vl g">{fmt(IDX, 2)}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        for exp_date in sorted(df_w["expiry_date"].unique()):
            try:
                dn = DAYS_HE.get(date.fromisoformat(exp_date).weekday(), "")
            except Exception:
                dn = ""
            df_e = df_w[df_w["expiry_date"] == exp_date].sort_values("interval_pct")
            has_res = (df_e["result_status"].notna().any()
                       if "result_status" in df_e.columns else False)
            badge_h = ("settled" if has_res else "open")
            badge_t = ("SETTLED" if has_res else "OPEN")
            st.markdown(
                f'<div style="font-size:14px;font-weight:700;'
                f'color:{C_TEXT};margin:14px 0 8px;">'
                f'יום {dn} — {exp_date} '
                f'<span class="badge {badge_h}">{badge_t}</span></div>',
                unsafe_allow_html=True)

            if not df_e.empty:
                intervals = sorted(df_e["interval_pct"].unique())
                int_labels = [f"{p:.1f}%" for p in intervals]
                sel_int = st.select_slider(
                    "מרווח", options=int_labels,
                    value=int_labels[len(int_labels) // 2],
                    key=f"prod_sl_{exp_date}")
                sel_pct = intervals[int_labels.index(sel_int)]
                sr = df_e[df_e["interval_pct"] == sel_pct].iloc[0]

                mp_v = N(sr.get("max_profit_ils")) or 0
                mr_v = N(sr.get("max_risk_ils")) or 0
                prem = N(sr.get("total_net_premium")) or 0
                rr_v = N(sr.get("risk_reward_ratio")) or 0
                res = sr.get("result_status")
                pnl_v = N(sr.get("actual_pnl_ils"))

                st.markdown(f"""
                <div class="kpi-grid">
                    <div class="kpi ag">
                        <div class="lb">רווח מקס</div>
                        <div class="vl g">+{mp_v:,.0f} ₪</div>
                    </div>
                    <div class="kpi ar">
                        <div class="lb">סיכון מקס</div>
                        <div class="vl r">-{mr_v:,.0f} ₪</div>
                    </div>
                    <div class="kpi ab">
                        <div class="lb">פרמיה</div>
                        <div class="vl b">{prem:,.2f}</div>
                    </div>
                    <div class="kpi ad">
                        <div class="lb">R/R</div>
                        <div class="vl">{rr_v:.1f}x</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                if res and pnl_v is not None:
                    pc = C_GREEN if pnl_v >= 0 else C_RED
                    st.markdown(
                        f'<div style="text-align:center;padding:6px 0">'
                        f'<span style="font-size:18px;font-weight:700;'
                        f'color:{pc}">'
                        f'{"+" if pnl_v >= 0 else ""}{pnl_v:,.0f} ₪'
                        f'</span></div>',
                        unsafe_allow_html=True)

            st.markdown("---")

    # ==============================================================
    # PROD PAGE 3: PERFORMANCE
    # ==============================================================
    elif prod_page == "ביצועים":
        st.markdown('<div class="sec">ביצועים היסטוריים — Iron Condor</div>',
                    unsafe_allow_html=True)

        df_h = fetch("iron_condor_strategies",
                     "&result_status=not.is.null&order=trigger_date,interval_pct")
        if df_h.empty:
            st.info("אין תוצאות עדיין — יופיעו אחרי הפקיעה הראשונה.")
            st.stop()

        for c in ["actual_pnl_ils", "max_profit_ils", "max_risk_ils",
                   "interval_pct"]:
            if c in df_h.columns:
                df_h[c] = df_h[c].apply(lambda v: N(v) or 0)

        total = df_h["actual_pnl_ils"].sum()
        trades = len(df_h)
        wins = len(df_h[df_h["actual_pnl_ils"] > 0])
        losses = trades - wins
        wr = (wins / trades * 100) if trades > 0 else 0
        avg_win = (df_h[df_h["actual_pnl_ils"] > 0]["actual_pnl_ils"].mean()
                   if wins > 0 else 0)
        avg_loss = (df_h[df_h["actual_pnl_ils"] <= 0]["actual_pnl_ils"].mean()
                    if losses > 0 else 0)
        pnl_cls = "g" if total >= 0 else "r"

        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi {"ag" if total >= 0 else "ar"}">
                <div class="lb">TOTAL P&L</div>
                <div class="vl {pnl_cls}">₪{"+" if total >= 0 else ""}{total:,.0f}</div>
                <div class="sb">{trades} trades</div>
            </div>
            <div class="kpi ag">
                <div class="lb">WIN RATE</div>
                <div class="vl g">{wr:.0f}%</div>
                <div class="sb">{wins}W / {losses}L</div>
            </div>
            <div class="kpi ab">
                <div class="lb">AVG WIN</div>
                <div class="vl b">₪{avg_win:+,.0f}</div>
            </div>
            <div class="kpi ar">
                <div class="lb">AVG LOSS</div>
                <div class="vl r">₪{avg_loss:+,.0f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Charts
        dbd = df_h.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        dbd.columns = ["date", "pnl"]
        dbd["cum"] = dbd["pnl"].cumsum()
        dbd["color"] = dbd["pnl"].apply(
            lambda x: C_GREEN if x >= 0 else C_RED)

        ch1, ch2 = st.tabs(["P&L יומי", "P&L מצטבר"])

        with ch1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=dbd["date"], y=dbd["pnl"],
                marker_color=dbd["color"],
                hovertemplate="<b>%{x}</b><br>₪%{y:,.0f}<extra></extra>"))
            fig.update_layout(showlegend=False)
            plotly_dark(fig, h=320)
            st.plotly_chart(fig, use_container_width=True)

        with ch2:
            fig = go.Figure()
            lc = C_GREEN if dbd["cum"].iloc[-1] >= 0 else C_RED
            fc = ("rgba(0,230,118,0.1)" if dbd["cum"].iloc[-1] >= 0
                  else "rgba(255,23,68,0.1)")
            fig.add_trace(go.Scatter(
                x=dbd["date"], y=dbd["cum"],
                mode="lines", fill="tozeroy",
                fillcolor=fc, line=dict(color=lc, width=2.5),
                hovertemplate="<b>%{x}</b><br>₪%{y:,.0f}<extra></extra>"))
            fig.update_layout(showlegend=False)
            plotly_dark(fig, h=320)
            st.plotly_chart(fig, use_container_width=True)

        # By interval table
        st.markdown("---")
        st.markdown('<div class="sec">ביצועים לפי מרווח</div>',
                    unsafe_allow_html=True)

        dbp = df_h.groupby("interval_pct").agg(
            pnl=("actual_pnl_ils", "sum"),
            avg=("actual_pnl_ils", "mean"),
            cnt=("actual_pnl_ils", "count"),
            w=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        dbp["wr"] = (dbp["w"] / dbp["cnt"] * 100).round(1)
        dbp.columns = ["מרווח %", "סה״כ ₪", "ממוצע ₪",
                        "עסקאות", "ניצחונות", "הצלחה %"]
        st.dataframe(dbp, use_container_width=True, hide_index=True)

        # Full history
        st.markdown("---")
        st.markdown('<div class="sec">היסטוריה מלאה</div>',
                    unsafe_allow_html=True)
        det = ["trigger_date", "expiry_date", "interval_pct",
               "short_put_strike", "short_call_strike",
               "actual_index_close", "result_status", "actual_pnl_ils"]
        avail = [c for c in det if c in df_h.columns]
        dfd = df_h[avail].sort_values("actual_pnl_ils", ascending=False)
        dfd = dfd.rename(columns={
            "trigger_date": "תאריך", "expiry_date": "פקיעה",
            "interval_pct": "מרווח %", "short_put_strike": "Short Put",
            "short_call_strike": "Short Call",
            "actual_index_close": "מדד פקיעה",
            "result_status": "תוצאה", "actual_pnl_ils": "P&L ₪",
        })
        st.dataframe(dfd, use_container_width=True, height=400,
                     hide_index=True)
