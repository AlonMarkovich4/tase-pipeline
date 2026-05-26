"""
TASE TA-35 — Premium Options Trading Workstation
=================================================
Enterprise-grade dashboard: live monitor, Iron Condor strategies
with Plotly range-risk visualizations, historical P&L analytics,
and a fully isolated paper-trading sandbox.
"""

import os, math
import streamlit as st
import pandas as pd
import httpx
import plotly.graph_objects as go
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# ==================================================================
# CONFIG
# ==================================================================
st.set_page_config(page_title="TA-35 Workstation", page_icon="◆", layout="wide")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")
DAYS = {0:"שני",1:"שלישי",2:"רביעי",3:"חמישי",4:"שישי",5:"שבת",6:"ראשון"}

TASE_MULTIPLIER = 50
WING_WIDTH = 20
DEMO_INTERVALS = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]
DEMO_INITIAL_BALANCE = 100_000

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

# ==================================================================
# GLOBAL CSS
# ==================================================================
st.markdown(f"""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&display=swap');

/* ---- Reset & base ---- */
html, body, [class*="css"] {{
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif !important;
}}
.main .block-container {{
    direction: rtl; text-align: right;
    padding: 1.5rem 2rem 2rem !important;
    max-width: 1400px;
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

/* Hide Streamlit chrome */
#MainMenu, footer, header {{ visibility: hidden; }}
.stDeployButton {{ display: none; }}

/* ---- KPI Cards ---- */
.kpi-grid {{
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
    gap: 14px;
    margin-bottom: 24px;
}}
.kpi {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 18px 20px;
    position: relative;
    overflow: hidden;
}}
.kpi::after {{
    content: '';
    position: absolute;
    top: 0; right: 0;
    width: 4px; height: 100%;
    border-radius: 0 10px 10px 0;
}}
.kpi.accent-green::after {{ background: {C_GREEN}; }}
.kpi.accent-blue::after  {{ background: {C_BLUE}; }}
.kpi.accent-red::after   {{ background: {C_RED}; }}
.kpi.accent-dim::after   {{ background: {C_DIM}; }}
.kpi.accent-yellow::after {{ background: {C_YELLOW}; }}
.kpi .label {{
    font-size: 11px;
    font-weight: 600;
    color: {C_DIM};
    text-transform: uppercase;
    letter-spacing: 0.8px;
    margin-bottom: 6px;
}}
.kpi .val {{
    font-size: 24px;
    font-weight: 700;
    color: {C_TEXT};
    direction: ltr;
    unicode-bidi: isolate;
}}
.kpi .val.sm {{ font-size: 17px; }}
.kpi .val.green {{ color: {C_GREEN}; }}
.kpi .val.red {{ color: {C_RED}; }}
.kpi .val.blue {{ color: {C_BLUE}; }}
.kpi .val.yellow {{ color: {C_YELLOW}; }}
.kpi .sub {{
    font-size: 11px;
    color: {C_DIM};
    margin-top: 3px;
    direction: ltr;
    unicode-bidi: isolate;
}}

/* ---- Live dot ---- */
@keyframes pulse {{
    0%, 100% {{ opacity: 1; }}
    50% {{ opacity: 0.3; }}
}}
.live-dot {{
    display: inline-block;
    width: 8px; height: 8px;
    border-radius: 50%;
    margin-left: 6px;
    vertical-align: middle;
}}
.live-dot.on {{
    background: {C_GREEN};
    box-shadow: 0 0 8px {C_GREEN};
    animation: pulse 2s ease-in-out infinite;
}}
.live-dot.off {{
    background: {C_DIM};
}}

/* ---- Section header ---- */
.sec-hdr {{
    display: flex;
    align-items: center;
    gap: 8px;
    font-size: 16px;
    font-weight: 700;
    color: {C_TEXT};
    margin: 20px 0 14px;
    padding-bottom: 10px;
    border-bottom: 1px solid {C_BORDER};
}}

/* ---- Expiry header ---- */
.exp-hdr {{
    display: flex;
    align-items: center;
    gap: 10px;
    margin: 18px 0 10px;
}}
.exp-hdr .day {{
    font-size: 15px;
    font-weight: 700;
    color: {C_TEXT};
}}
.exp-hdr .badge {{
    font-size: 10px;
    font-weight: 700;
    padding: 3px 10px;
    border-radius: 4px;
    letter-spacing: 0.5px;
}}
.exp-hdr .badge.settled {{
    background: rgba(0,230,118,0.12);
    color: {C_GREEN};
    border: 1px solid rgba(0,230,118,0.3);
}}
.exp-hdr .badge.open {{
    background: rgba(0,176,255,0.10);
    color: {C_BLUE};
    border: 1px solid rgba(0,176,255,0.25);
}}

/* ---- Sidebar brand ---- */
.sb-brand {{
    text-align: center;
    padding: 20px 0 12px;
}}
.sb-brand .logo {{
    font-size: 11px;
    font-weight: 800;
    letter-spacing: 3px;
    color: {C_BLUE};
}}
.sb-brand .title {{
    font-size: 18px;
    font-weight: 800;
    color: {C_TEXT};
    margin-top: 4px;
}}
.sb-status {{
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    padding: 8px 12px;
    border-radius: 6px;
    margin: 10px 8px;
}}
.sb-status.on {{
    background: rgba(0,230,118,0.08);
    border: 1px solid rgba(0,230,118,0.25);
    color: {C_GREEN};
}}
.sb-status.off {{
    background: rgba(107,123,141,0.08);
    border: 1px solid rgba(107,123,141,0.25);
    color: {C_DIM};
}}
.sb-clock {{
    text-align: center;
    font-size: 13px;
    color: {C_DIM};
    margin: 6px 0 10px;
}}

/* ---- DataFrames ---- */
div[data-testid="stDataFrame"] {{
    border: 1px solid {C_BORDER};
    border-radius: 8px;
    overflow: hidden;
}}

/* ---- Buttons ---- */
.stButton > button {{
    background: {C_CARD} !important;
    color: {C_DIM} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    transition: all 0.15s !important;
}}
.stButton > button:hover {{
    background: {C_BORDER} !important;
    color: {C_TEXT} !important;
    border-color: {C_BLUE} !important;
}}

/* ---- Demo sandbox badge ---- */
.demo-badge {{
    display: inline-block;
    font-size: 10px;
    font-weight: 800;
    padding: 3px 10px;
    border-radius: 4px;
    letter-spacing: 1px;
    background: rgba(255,214,0,0.12);
    color: {C_YELLOW};
    border: 1px solid rgba(255,214,0,0.3);
    margin-right: 8px;
}}

/* ---- Misc ---- */
hr {{ border-color: {C_BORDER} !important; opacity: 0.5 !important; }}
[data-testid="stMetric"] {{ display: none; }}
</style>
""", unsafe_allow_html=True)


# ==================================================================
# HELPERS
# ==================================================================
def _hdr():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
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
    """Safe numeric."""
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
    if dec == 0:
        return f"{v:,.0f}"
    return f"{v:,.{dec}f}"


@st.cache_data(ttl=60)
def _fetch_ta35_yahoo() -> float:
    """Fetch TA-35 index from Yahoo Finance."""
    try:
        url = ("https://query1.finance.yahoo.com/v8/finance/chart/TA35.TA"
               "?interval=1d&range=1d")
        r = httpx.get(url, timeout=10,
                      headers={"User-Agent": "Mozilla/5.0"})
        if r.status_code == 200:
            meta = (r.json().get("chart", {})
                    .get("result", [{}])[0].get("meta", {}))
            price = meta.get("regularMarketPrice", 0)
            if price and price > 0:
                return float(price)
    except Exception:
        pass
    return 0.0


def get_idx(df):
    # 1. Yahoo Finance (real-time)
    yf = _fetch_ta35_yahoo()
    if yf > 0:
        return yf
    # 2. Fallback: underlingasset from DB
    for c in ["underlingasset_call", "underlingasset_put"]:
        if c in df.columns:
            for v in df[c]:
                x = N(v)
                if x and x > 0:
                    return x
    return 0.0


def relative_time(dt_str, tm_str=""):
    """Return relative timestamp string."""
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
        now = datetime.now(TZ)
        diff = now - t
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


def plotly_layout(fig, h=None):
    """Apply dark financial chart theme."""
    fig.update_layout(
        plot_bgcolor=C_CARD,
        paper_bgcolor=C_CARD,
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


def _build_strip_chart(lp_v, sp_v, sc_v, lc_v, bl_v, bh_v, idx, key):
    """Reusable Plotly strip chart for strike visualization."""
    pad = 25
    x0, x1 = lp_v - pad, lc_v + pad
    fig = go.Figure()

    # Risk left
    fig.add_shape(type="rect",
        x0=lp_v, x1=bl_v, y0=0.15, y1=0.85,
        fillcolor="rgba(255,23,68,0.10)", line=dict(width=0))
    # Profit zone
    fig.add_shape(type="rect",
        x0=bl_v, x1=bh_v, y0=0.15, y1=0.85,
        fillcolor="rgba(0,230,118,0.15)", line=dict(width=0))
    # Risk right
    fig.add_shape(type="rect",
        x0=bh_v, x1=lc_v, y0=0.15, y1=0.85,
        fillcolor="rgba(255,23,68,0.10)", line=dict(width=0))

    # Strike markers
    for val, lbl, clr in [
        (lp_v, "LP", C_RED), (sp_v, "SP", C_GREEN),
        (sc_v, "SC", C_GREEN), (lc_v, "LC", C_RED),
    ]:
        fig.add_trace(go.Scatter(
            x=[val], y=[0.5], mode="markers+text",
            marker=dict(size=9, color=clr, symbol="diamond"),
            text=[f"{lbl} {val:,.0f}"],
            textposition="top center",
            textfont=dict(size=9, color=clr),
            showlegend=False, hoverinfo="skip"))

    # BE markers
    for val in [bl_v, bh_v]:
        fig.add_trace(go.Scatter(
            x=[val], y=[0.5], mode="markers+text",
            marker=dict(size=6, color=C_TEXT, symbol="triangle-up"),
            text=[f"BE {val:,.0f}"],
            textposition="bottom center",
            textfont=dict(size=8, color=C_DIM),
            showlegend=False, hoverinfo="skip"))

    # Current index line
    if idx > 0:
        fig.add_trace(go.Scatter(
            x=[idx, idx], y=[0, 1], mode="lines",
            line=dict(color=C_BLUE, width=2, dash="dot"),
            showlegend=False, hoverinfo="skip"))
        fig.add_annotation(
            x=idx, y=1.05, text=f"TA-35: {idx:,.0f}",
            showarrow=False, font=dict(size=9, color=C_BLUE))

    fig.update_layout(
        xaxis=dict(range=[x0, x1], showgrid=False,
                   showline=False, zeroline=False,
                   tickfont=dict(size=9, color=C_DIM)),
        yaxis=dict(visible=False, range=[-0.1, 1.2]),
        height=110,
        margin=dict(l=0, r=0, t=16, b=20),
        plot_bgcolor=C_CARD, paper_bgcolor=C_CARD,
    )
    st.plotly_chart(fig, use_container_width=True, key=key)


# ==================================================================
# SIDEBAR
# ==================================================================
now = datetime.now(TZ)
is_live = now.weekday() in {0, 1, 2, 3, 4} and 9 <= now.hour < 18

st.sidebar.markdown("""
<div class="sb-brand">
    <div class="logo">◆ TASE TERMINAL</div>
    <div class="title">TA-35 Options</div>
</div>
""", unsafe_allow_html=True)

st.sidebar.markdown(
    f'<div class="sb-clock">יום {DAYS.get(now.weekday(), "")} · '
    f'{now.strftime("%d/%m/%Y")} · {now.strftime("%H:%M:%S")}</div>',
    unsafe_allow_html=True)

dot = "on" if is_live else "off"
label = "MARKET OPEN" if is_live else "MARKET CLOSED"
cls = "on" if is_live else "off"
st.sidebar.markdown(
    f'<div class="sb-status {cls}">'
    f'<span class="live-dot {dot}"></span> {label}</div>',
    unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 רענן נתונים", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("v3.0 · Render · Supabase · Telegram")


# ==================================================================
# MAIN TABS
# ==================================================================
main_tab1, main_tab2 = st.tabs([
    "📊 תחנת מסחר ומוניטור",
    "🎮 חדר מסחר דמו (Sandbox)",
])


# ██████████████████████████████████████████████████████████████████
# TAB 1: PRODUCTION WORKSTATION
# ██████████████████████████████████████████████████████████████████
with main_tab1:
    page = st.radio(
        "ניווט", ["מוניטור חי", "אסטרטגיות", "ביצועים"],
        horizontal=True, label_visibility="collapsed")

    # ==============================================================
    # PAGE 1: LIVE MONITOR
    # ==============================================================
    if page == "מוניטור חי":
        dot_html = f'<span class="live-dot {"on" if is_live else "off"}"></span>'
        st.markdown(
            f'<div class="sec-hdr">{dot_html} מוניטור חי — Put / Call</div>',
            unsafe_allow_html=True)

        df = fetch("tase_putcall")
        if df.empty:
            st.warning("אין נתונים זמינים כרגע.")
            st.stop()

        idx = get_idx(df)
        fd = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else ""
        ft = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        n_exp = df["expiry_date"].nunique() if "expiry_date" in df.columns else 0
        rel = relative_time(fd, ft)

        idx_cls = "green" if idx > 0 else "dim"
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi accent-green">
                <div class="label">TA-35 INDEX</div>
                <div class="val {idx_cls}">{fmt(idx, 2)}</div>
            </div>
            <div class="kpi accent-blue">
                <div class="label">LAST UPDATE</div>
                <div class="val sm">{ft or '—'}</div>
                <div class="sub">{rel}</div>
            </div>
            <div class="kpi accent-dim">
                <div class="label">EXPIRY DATES</div>
                <div class="val">{n_exp}</div>
            </div>
            <div class="kpi accent-dim">
                <div class="label">TOTAL ROWS</div>
                <div class="val">{len(df)}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Expiry filter
        if "expiry_date" in df.columns:
            exps = sorted(df["expiry_date"].unique())
            labels = []
            for e in exps:
                try:
                    d = date.fromisoformat(e)
                    labels.append(f"יום {DAYS.get(d.weekday(), '')} — {e}")
                except Exception:
                    labels.append(e)
            sel = st.selectbox("בחר יום פקיעה", labels, index=0)
            df = df[df["expiry_date"] == exps[labels.index(sel)]]

        # Build clean table
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
        else:
            st.info("אין נתוני מסחר ליום פקיעה זה.")

    # ==============================================================
    # PAGE 2: STRATEGIES
    # ==============================================================
    elif page == "אסטרטגיות":
        st.markdown(
            '<div class="sec-hdr">אסטרטגיות Iron Condor</div>',
            unsafe_allow_html=True)

        df_s = fetch("iron_condor_strategies",
                     "&order=trigger_date.desc,expiry_date,interval_pct")
        if df_s.empty:
            st.info("אין אסטרטגיות עדיין. הראשונה תיווצר ביום מסחר הקרוב אחרי 12:00.")
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

        # Current index
        idx = get_idx(fetch("tase_putcall"))

        if idx > 0:
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi accent-green" style="max-width:280px;">
                    <div class="label">CURRENT TA-35 INDEX</div>
                    <div class="val green">{fmt(idx, 2)}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        # ---- Per expiry ----
        for exp_date in sorted(df_w["expiry_date"].unique()):
            try:
                exp_d = date.fromisoformat(exp_date)
                dn = DAYS.get(exp_d.weekday(), "")
            except Exception:
                dn = ""

            df_e = df_w[df_w["expiry_date"] == exp_date].sort_values("interval_pct")
            has_res = (df_e["result_status"].notna().any()
                       if "result_status" in df_e.columns else False)

            badge = ('<span class="badge settled">SETTLED</span>' if has_res
                     else '<span class="badge open">OPEN</span>')
            st.markdown(
                f'<div class="exp-hdr">'
                f'<span class="day">יום {dn} — {exp_date}</span>{badge}</div>',
                unsafe_allow_html=True)

            # ---------- Variation selector ----------
            if not df_e.empty:
                intervals = sorted(df_e["interval_pct"].unique())
                int_labels = [f"{p:.1f}%" for p in intervals]
                sel_int = st.select_slider(
                    "בחר מרווח", options=int_labels,
                    value=int_labels[len(int_labels) // 2],
                    key=f"slider_{exp_date}")
                sel_pct = intervals[int_labels.index(sel_int)]
                sr = df_e[df_e["interval_pct"] == sel_pct].iloc[0]

                lp_v = N(sr.get("long_put_strike")) or 0
                sp_v = N(sr.get("short_put_strike")) or 0
                sc_v = N(sr.get("short_call_strike")) or 0
                lc_v = N(sr.get("long_call_strike")) or 0
                bl_v = N(sr.get("breakeven_lower")) or 0
                bh_v = N(sr.get("breakeven_upper")) or 0
                mp_v = N(sr.get("max_profit_ils")) or 0
                mr_v = N(sr.get("max_risk_ils")) or 0
                prem = N(sr.get("total_net_premium")) or 0
                rr_v = N(sr.get("risk_reward_ratio")) or 0
                res  = sr.get("result_status")
                pnl_v = N(sr.get("actual_pnl_ils"))

                # ---- KPI row ----
                st.markdown(f"""
                <div class="kpi-grid">
                    <div class="kpi accent-green">
                        <div class="label">רווח מקס</div>
                        <div class="val green">+{mp_v:,.0f} ₪</div>
                    </div>
                    <div class="kpi accent-red">
                        <div class="label">סיכון מקס</div>
                        <div class="val red">-{mr_v:,.0f} ₪</div>
                    </div>
                    <div class="kpi accent-blue">
                        <div class="label">פרמיה נטו</div>
                        <div class="val blue">{prem:,.2f}</div>
                    </div>
                    <div class="kpi accent-dim">
                        <div class="label">Risk / Reward</div>
                        <div class="val">{rr_v:.1f}x</div>
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # ---- Visual strike range ----
                if lp_v > 0 and lc_v > 0:
                    _build_strip_chart(lp_v, sp_v, sc_v, lc_v,
                                       bl_v, bh_v, idx,
                                       key=f"strip_{exp_date}")

                # ---- Position status ----
                if idx > 0 and sp_v > 0 and sc_v > 0:
                    if sp_v <= idx <= sc_v:
                        st.success(
                            f"✅ מדד {idx:,.0f} בטווח הרווח"
                            f" ({sp_v:,.0f} – {sc_v:,.0f})")
                    elif idx < sp_v:
                        st.warning(
                            f"⚠️ מדד {idx:,.0f} מתחת ל-Short Put"
                            f" ב-{sp_v - idx:,.0f} נק׳")
                    else:
                        st.warning(
                            f"⚠️ מדד {idx:,.0f} מעל ל-Short Call"
                            f" ב-{idx - sc_v:,.0f} נק׳")

                # ---- Result badge (if settled) ----
                if res and pnl_v is not None:
                    pnl_c = C_GREEN if pnl_v >= 0 else C_RED
                    st.markdown(
                        f'<div style="text-align:center;padding:8px 0">'
                        f'<span style="font-size:20px;font-weight:700;'
                        f'color:{pnl_c}">'
                        f'{"+" if pnl_v >= 0 else ""}{pnl_v:,.0f} ₪'
                        f'</span></div>',
                        unsafe_allow_html=True)

            st.markdown("---")

    # ==============================================================
    # PAGE 3: PERFORMANCE
    # ==============================================================
    elif page == "ביצועים":
        st.markdown(
            '<div class="sec-hdr">ביצועים היסטוריים — Iron Condor</div>',
            unsafe_allow_html=True)

        df_h = fetch("iron_condor_strategies",
                     "&result_status=not.is.null&order=trigger_date,interval_pct")
        if df_h.empty:
            st.info("אין תוצאות עדיין — יופיעו אחרי הפקיעה הראשונה.")
            st.stop()

        for c in ["actual_pnl_ils", "max_profit_ils", "max_risk_ils", "interval_pct"]:
            if c in df_h.columns:
                df_h[c] = df_h[c].apply(lambda v: N(v) or 0)

        total = df_h["actual_pnl_ils"].sum()
        trades = len(df_h)
        wins = len(df_h[df_h["actual_pnl_ils"] > 0])
        losses = trades - wins
        wr = (wins / trades * 100) if trades > 0 else 0
        avg_win = df_h[df_h["actual_pnl_ils"] > 0]["actual_pnl_ils"].mean() if wins > 0 else 0
        avg_loss = df_h[df_h["actual_pnl_ils"] <= 0]["actual_pnl_ils"].mean() if losses > 0 else 0
        pnl_cls = "green" if total >= 0 else "red"
        pnl_prefix = "+" if total >= 0 else ""

        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi accent-{"green" if total >= 0 else "red"}">
                <div class="label">TOTAL P&L</div>
                <div class="val {pnl_cls}">₪{pnl_prefix}{total:,.0f}</div>
                <div class="sub">{trades} trades</div>
            </div>
            <div class="kpi accent-green">
                <div class="label">WIN RATE</div>
                <div class="val green">{wr:.0f}%</div>
                <div class="sub">{wins}W / {losses}L</div>
            </div>
            <div class="kpi accent-blue">
                <div class="label">AVG WIN</div>
                <div class="val blue">₪{avg_win:+,.0f}</div>
            </div>
            <div class="kpi accent-red">
                <div class="label">AVG LOSS</div>
                <div class="val red">₪{avg_loss:+,.0f}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # ---- Charts ----
        dbd = df_h.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        dbd.columns = ["date", "pnl"]
        dbd["cum"] = dbd["pnl"].cumsum()
        dbd["color"] = dbd["pnl"].apply(lambda x: C_GREEN if x >= 0 else C_RED)

        tab1, tab2, tab3, tab4 = st.tabs(["P&L יומי", "P&L מצטבר", "Win Rate", "השוואת מרווחים"])

        with tab1:
            fig = go.Figure()
            fig.add_trace(go.Bar(
                x=dbd["date"], y=dbd["pnl"],
                marker_color=dbd["color"],
                hovertemplate="<b>%{x}</b><br>P&L: ₪%{y:,.0f}<extra></extra>",
            ))
            fig.update_layout(showlegend=False)
            plotly_layout(fig, h=340)
            st.plotly_chart(fig, use_container_width=True)

        with tab2:
            fig = go.Figure()
            fill_color = "rgba(0,230,118,0.1)" if dbd["cum"].iloc[-1] >= 0 else "rgba(255,23,68,0.1)"
            line_color = C_GREEN if dbd["cum"].iloc[-1] >= 0 else C_RED
            fig.add_trace(go.Scatter(
                x=dbd["date"], y=dbd["cum"],
                mode="lines", fill="tozeroy",
                fillcolor=fill_color,
                line=dict(color=line_color, width=2.5),
                hovertemplate="<b>%{x}</b><br>Cumulative: ₪%{y:,.0f}<extra></extra>",
            ))
            fig.update_layout(showlegend=False)
            plotly_layout(fig, h=340)
            st.plotly_chart(fig, use_container_width=True)

        with tab3:
            fig = go.Figure()
            fig.add_trace(go.Pie(
                labels=["ניצחונות", "הפסדים"],
                values=[wins, losses],
                marker=dict(colors=[C_GREEN, C_RED]),
                textinfo="percent+label",
                textfont=dict(size=13, color=C_TEXT),
                hovertemplate="%{label}: %{value} trades<br>%{percent}<extra></extra>",
                hole=0.55,
            ))
            fig.update_layout(
                plot_bgcolor=C_CARD, paper_bgcolor=C_CARD,
                font=dict(family="Inter", color=C_TEXT),
                margin=dict(l=20, r=20, t=20, b=20),
                height=300,
                showlegend=False,
                annotations=[dict(
                    text=f"{wr:.0f}%", x=0.5, y=0.5,
                    font=dict(size=28, color=C_GREEN, family="Inter"),
                    showarrow=False)],
            )
            st.plotly_chart(fig, use_container_width=True)

        with tab4:
            # Cumulative P&L per interval over time
            intervals = sorted(df_h["interval_pct"].unique())
            fig = go.Figure()
            palette = ["#00E676", "#00B0FF", "#FFD600", "#FF9100",
                        "#E040FB", "#FF1744", "#76FF03", "#18FFFF"]
            for i, pct in enumerate(intervals):
                df_pct = df_h[df_h["interval_pct"] == pct].copy()
                df_pct = df_pct.sort_values("trigger_date")
                df_pct["cum_pnl"] = df_pct["actual_pnl_ils"].cumsum()
                color = palette[i % len(palette)]
                fig.add_trace(go.Scatter(
                    x=df_pct["trigger_date"], y=df_pct["cum_pnl"],
                    mode="lines+markers",
                    name=f"{pct}%",
                    line=dict(color=color, width=2),
                    marker=dict(size=4, color=color),
                    hovertemplate=(
                        f"<b>מרווח {pct}%</b><br>"
                        "%{x}<br>"
                        "P&L מצטבר: ₪%{y:,.0f}<extra></extra>"
                    ),
                ))
            fig.update_layout(
                showlegend=True,
                legend=dict(
                    orientation="h", yanchor="bottom", y=-0.25,
                    font=dict(size=11, color=C_DIM)),
                xaxis_title="", yaxis_title="P&L מצטבר (₪)",
            )
            plotly_layout(fig, h=400)
            st.plotly_chart(fig, use_container_width=True)

        st.markdown("---")

        # ---- By interval ----
        st.markdown('<div class="sec-hdr">ביצועים לפי מרווח</div>', unsafe_allow_html=True)

        dbp = df_h.groupby("interval_pct").agg(
            pnl=("actual_pnl_ils", "sum"),
            avg=("actual_pnl_ils", "mean"),
            cnt=("actual_pnl_ils", "count"),
            w=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        dbp["wr"] = (dbp["w"] / dbp["cnt"] * 100).round(1)

        # Plotly grouped bar
        fig = go.Figure()
        colors = [C_GREEN if v >= 0 else C_RED for v in dbp["pnl"]]
        fig.add_trace(go.Bar(
            x=dbp["interval_pct"].apply(lambda x: f"{x}%"),
            y=dbp["pnl"],
            marker_color=colors,
            name="Total P&L",
            hovertemplate="מרווח: %{x}<br>P&L: ₪%{y:,.0f}<extra></extra>",
        ))
        fig.update_layout(showlegend=False,
                          xaxis_title="Interval %", yaxis_title="P&L (₪)")
        plotly_layout(fig, h=300)
        st.plotly_chart(fig, use_container_width=True)

        # Summary table
        dbp.columns = ["מרווח %", "סה״כ ₪", "ממוצע ₪", "עסקאות", "ניצחונות", "הצלחה %"]
        st.dataframe(dbp, use_container_width=True, hide_index=True)

        st.markdown("---")

        # ---- Full history ----
        st.markdown('<div class="sec-hdr">היסטוריה מלאה</div>', unsafe_allow_html=True)

        det = ["trigger_date", "expiry_date", "interval_pct",
               "short_put_strike", "short_call_strike",
               "actual_index_close", "result_status", "actual_pnl_ils"]
        avail = [c for c in det if c in df_h.columns]
        dfd = df_h[avail].sort_values("actual_pnl_ils", ascending=False)
        dfd = dfd.rename(columns={
            "trigger_date": "תאריך", "expiry_date": "פקיעה",
            "interval_pct": "מרווח %", "short_put_strike": "Short Put",
            "short_call_strike": "Short Call", "actual_index_close": "מדד פקיעה",
            "result_status": "תוצאה", "actual_pnl_ils": "P&L ₪",
        })
        st.dataframe(dfd, use_container_width=True, height=400, hide_index=True)


# ██████████████████████████████████████████████████████████████████
# TAB 2: DEMO SANDBOX (100% isolated — NO production DB writes)
# ██████████████████████████████████████████████████████████████████
with main_tab2:

    # ------------------------------------------------------------------
    # Session state initialization
    # ------------------------------------------------------------------
    if "demo_balance" not in st.session_state:
        st.session_state.demo_balance = DEMO_INITIAL_BALANCE
    if "demo_trades" not in st.session_state:
        st.session_state.demo_trades = []  # list of trade dicts
    if "demo_history" not in st.session_state:
        st.session_state.demo_history = []  # settled trades

    # ------------------------------------------------------------------
    # Header
    # ------------------------------------------------------------------
    st.markdown(
        f'<div class="sec-hdr">'
        f'<span class="demo-badge">SANDBOX</span>'
        f'חדר מסחר דמו — Iron Condor</div>',
        unsafe_allow_html=True)

    st.caption(
        "סביבת תרגול מבודדת לחלוטין. "
        "כל הנתונים נשמרים בזיכרון הסשן בלבד — "
        "אין שום כתיבה או שינוי ב-Database הייצור."
    )

    # ------------------------------------------------------------------
    # Read LIVE market data (READ ONLY)
    # ------------------------------------------------------------------
    df_live = fetch("tase_putcall")
    idx_demo = get_idx(df_live) if not df_live.empty else 0.0

    # ---- Portfolio KPIs ----
    active_count = len(st.session_state.demo_trades)
    settled_count = len(st.session_state.demo_history)
    total_realized = sum(t.get("pnl_ils", 0) for t in st.session_state.demo_history)
    bal_cls = "green" if st.session_state.demo_balance >= DEMO_INITIAL_BALANCE else "red"

    st.markdown(f"""
    <div class="kpi-grid">
        <div class="kpi accent-yellow">
            <div class="label">יתרה וירטואלית</div>
            <div class="val {bal_cls}">₪{st.session_state.demo_balance:,.0f}</div>
            <div class="sub">התחלה: ₪{DEMO_INITIAL_BALANCE:,.0f}</div>
        </div>
        <div class="kpi accent-green">
            <div class="label">TA-35 LIVE</div>
            <div class="val green">{fmt(idx_demo, 2)}</div>
        </div>
        <div class="kpi accent-blue">
            <div class="label">פוזיציות פתוחות</div>
            <div class="val blue">{active_count}</div>
        </div>
        <div class="kpi accent-dim">
            <div class="label">P&L מומש</div>
            <div class="val {"green" if total_realized >= 0 else "red"}">{total_realized:+,.0f} ₪</div>
            <div class="sub">{settled_count} עסקאות</div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # ==================================================================
    # SECTION 1: Strategy Builder
    # ==================================================================
    st.markdown(
        '<div class="sec-hdr">בניית אסטרטגיה</div>',
        unsafe_allow_html=True)

    if idx_demo <= 0:
        st.warning("אין נתוני מדד זמינים — לא ניתן לבנות אסטרטגיה כרגע.")
    else:
        # Find real options from live data for premium estimation
        def _find_demo_option(df, target_strike, side):
            """Find closest option with a real price from live data."""
            strike_col = f"expirationprice_{side}"
            price_col = f"lastrate_{side}"
            best_strike = target_strike
            best_price = 0.0
            best_diff = float("inf")
            best_priced_strike = target_strike
            best_priced_price = 0.0
            best_priced_diff = float("inf")

            for _, row in df.iterrows():
                strike = N(row.get(strike_col))
                if not strike or strike <= 0:
                    continue
                price = N(row.get(price_col)) or 0
                diff = abs(strike - target_strike)

                if price > 0 and diff < best_priced_diff:
                    best_priced_diff = diff
                    best_priced_strike = strike
                    best_priced_price = price

                if diff < best_diff:
                    best_diff = diff
                    best_strike = strike
                    best_price = price

            if best_priced_price > 0:
                return best_priced_strike, best_priced_price
            return best_strike, best_price

        # Interval selector
        col_a, col_b = st.columns([2, 1])
        with col_a:
            demo_pct = st.select_slider(
                "בחר מרווח הגנה",
                options=[f"{p:.1f}%" for p in DEMO_INTERVALS],
                value="2.0%",
                key="demo_interval_slider")
            sel_pct = float(demo_pct.replace("%", ""))

        # Expiry selector
        with col_b:
            if not df_live.empty and "expiry_date" in df_live.columns:
                today_str = date.today().isoformat()
                future_exp = sorted(
                    e for e in df_live["expiry_date"].unique()
                    if e > today_str)
                if future_exp:
                    demo_expiry = st.selectbox(
                        "פקיעה", future_exp, index=0,
                        key="demo_expiry_select")
                else:
                    demo_expiry = None
                    st.info("אין פקיעות עתידיות")
            else:
                demo_expiry = None
                st.info("אין נתוני פקיעה")

        # Calculate condor from live data
        offset = idx_demo * (sel_pct / 100.0)
        sc_target = idx_demo + offset
        sp_target = idx_demo - offset
        lc_target = sc_target + WING_WIDTH
        lp_target = sp_target - WING_WIDTH

        # Match to real options if we have data for this expiry
        if demo_expiry and not df_live.empty:
            df_exp = df_live[df_live["expiry_date"] == demo_expiry]
        else:
            df_exp = df_live

        if not df_exp.empty:
            sc_strike, sc_price = _find_demo_option(df_exp, sc_target, "call")
            lc_strike, lc_price = _find_demo_option(df_exp, lc_target, "call")
            sp_strike, sp_price = _find_demo_option(df_exp, sp_target, "put")
            lp_strike, lp_price = _find_demo_option(df_exp, lp_target, "put")
        else:
            sc_strike, sc_price = sc_target, 0
            lc_strike, lc_price = lc_target, 0
            sp_strike, sp_price = sp_target, 0
            lp_strike, lp_price = lp_target, 0

        # Validate order
        if sp_strike >= sc_strike:
            sp_strike = idx_demo - offset
            sc_strike = idx_demo + offset
        if lp_strike >= sp_strike:
            lp_strike = sp_strike - WING_WIDTH
        if lc_strike <= sc_strike:
            lc_strike = sc_strike + WING_WIDTH

        # Compute
        net_prem = (sc_price + sp_price) - (lc_price + lp_price)
        actual_wing = max(sc_strike - sp_strike, lc_strike - sc_strike,
                          sp_strike - lp_strike)
        actual_wing_max = max(sp_strike - lp_strike, lc_strike - sc_strike)
        max_profit = net_prem * TASE_MULTIPLIER
        max_risk = (actual_wing_max * TASE_MULTIPLIER) - max_profit
        rr = round(max_risk / max_profit, 2) if max_profit > 0 else 0
        be_lower = sp_strike - net_prem
        be_upper = sc_strike + net_prem

        # Preview KPIs
        prem_flag = net_prem < 0
        st.markdown(f"""
        <div class="kpi-grid">
            <div class="kpi accent-green">
                <div class="label">רווח מקס</div>
                <div class="val {"green" if max_profit > 0 else "red"}">
                    {max_profit:+,.0f} ₪</div>
                <div class="sub">{net_prem:,.2f} נק׳ × {TASE_MULTIPLIER}</div>
            </div>
            <div class="kpi accent-red">
                <div class="label">סיכון מקס</div>
                <div class="val red">{max_risk:,.0f} ₪</div>
                <div class="sub">כנף {actual_wing_max:,.0f} נק׳</div>
            </div>
            <div class="kpi accent-blue">
                <div class="label">טווח רווח</div>
                <div class="val sm blue">{sp_strike:,.0f} — {sc_strike:,.0f}</div>
                <div class="sub">BE: {be_lower:,.0f} — {be_upper:,.0f}</div>
            </div>
            <div class="kpi accent-dim">
                <div class="label">Risk / Reward</div>
                <div class="val">{rr:.1f}x</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        if prem_flag:
            st.warning(
                "⚠️ פרמיה שלילית — מרווח זה עולה כסף להיכנס "
                "ולא יניב רווח. שקול מרווח צר יותר.")

        # Strip chart preview
        if lp_strike > 0 and lc_strike > 0 and be_lower > 0 and be_upper > 0:
            _build_strip_chart(lp_strike, sp_strike, sc_strike, lc_strike,
                               be_lower, be_upper, idx_demo,
                               key="demo_preview_strip")

        # ---- Legs detail ----
        with st.expander("פירוט רגליים"):
            legs_data = [
                {"רגל": "Long Put", "Strike": f"{lp_strike:,.0f}",
                 "מחיר": f"{lp_price:,.2f}", "כיוון": "קנייה"},
                {"רגל": "Short Put", "Strike": f"{sp_strike:,.0f}",
                 "מחיר": f"{sp_price:,.2f}", "כיוון": "מכירה"},
                {"רגל": "Short Call", "Strike": f"{sc_strike:,.0f}",
                 "מחיר": f"{sc_price:,.2f}", "כיוון": "מכירה"},
                {"רגל": "Long Call", "Strike": f"{lc_strike:,.0f}",
                 "מחיר": f"{lc_price:,.2f}", "כיוון": "קנייה"},
            ]
            st.dataframe(pd.DataFrame(legs_data),
                         use_container_width=True, hide_index=True)

        # ---- Launch button ----
        can_trade = max_profit > 0 and max_risk > 0
        if st.button(
            "🚀 שגר פוזיציית דמו למסחר",
            use_container_width=True,
            disabled=not can_trade,
            key="demo_launch_btn",
        ):
            trade = {
                "id": len(st.session_state.demo_trades)
                      + len(st.session_state.demo_history) + 1,
                "timestamp": now.strftime("%Y-%m-%d %H:%M"),
                "interval_pct": sel_pct,
                "expiry_date": demo_expiry or "N/A",
                "base_index": round(idx_demo, 2),
                "lp_strike": round(lp_strike, 2),
                "sp_strike": round(sp_strike, 2),
                "sc_strike": round(sc_strike, 2),
                "lc_strike": round(lc_strike, 2),
                "net_premium": round(net_prem, 2),
                "max_profit": round(max_profit, 2),
                "max_risk": round(max_risk, 2),
                "be_lower": round(be_lower, 2),
                "be_upper": round(be_upper, 2),
                "wing_put": round(sp_strike - lp_strike, 2),
                "wing_call": round(lc_strike - sc_strike, 2),
                "status": "OPEN",
            }
            st.session_state.demo_trades.append(trade)
            st.success(
                f"✅ פוזיציה #{trade['id']} נפתחה — "
                f"מרווח {sel_pct}% | "
                f"{sp_strike:,.0f}—{sc_strike:,.0f}")
            st.rerun()

    # ==================================================================
    # SECTION 2: Active Demo Positions
    # ==================================================================
    st.markdown("---")
    st.markdown(
        '<div class="sec-hdr">פוזיציות פתוחות</div>',
        unsafe_allow_html=True)

    if not st.session_state.demo_trades:
        st.info("אין פוזיציות פתוחות. בנה אסטרטגיה למעלה ושגר אותה.")
    else:
        for i, trade in enumerate(st.session_state.demo_trades):
            t_sp = trade["sp_strike"]
            t_sc = trade["sc_strike"]
            t_lp = trade["lp_strike"]
            t_lc = trade["lc_strike"]
            t_bl = trade["be_lower"]
            t_bh = trade["be_upper"]

            st.markdown(
                f'<div class="exp-hdr">'
                f'<span class="day">#{trade["id"]} — '
                f'מרווח {trade["interval_pct"]}% | '
                f'פקיעה {trade["expiry_date"]}</span>'
                f'<span class="badge open">OPEN</span></div>',
                unsafe_allow_html=True)

            # KPIs for this position
            st.markdown(f"""
            <div class="kpi-grid">
                <div class="kpi accent-green">
                    <div class="label">רווח מקס</div>
                    <div class="val green">+{trade["max_profit"]:,.0f} ₪</div>
                </div>
                <div class="kpi accent-red">
                    <div class="label">סיכון מקס</div>
                    <div class="val red">{trade["max_risk"]:,.0f} ₪</div>
                </div>
                <div class="kpi accent-blue">
                    <div class="label">כניסה</div>
                    <div class="val sm blue">{trade["base_index"]:,.2f}</div>
                </div>
                <div class="kpi accent-dim">
                    <div class="label">טווח</div>
                    <div class="val sm">{t_sp:,.0f} — {t_sc:,.0f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

            # Strip chart with live index
            if t_lp > 0 and t_lc > 0:
                _build_strip_chart(t_lp, t_sp, t_sc, t_lc,
                                   t_bl, t_bh, idx_demo,
                                   key=f"demo_active_{trade['id']}")

            # Position status vs live index
            if idx_demo > 0:
                if t_sp <= idx_demo <= t_sc:
                    st.success(
                        f"✅ מדד {idx_demo:,.0f} בטווח הרווח "
                        f"({t_sp:,.0f} – {t_sc:,.0f})")
                elif idx_demo < t_sp:
                    st.warning(
                        f"⚠️ מדד {idx_demo:,.0f} מתחת ל-Short Put "
                        f"ב-{t_sp - idx_demo:,.0f} נק׳")
                else:
                    st.warning(
                        f"⚠️ מדד {idx_demo:,.0f} מעל ל-Short Call "
                        f"ב-{idx_demo - t_sc:,.0f} נק׳")

            st.markdown("---")

    # ==================================================================
    # SECTION 3: Sandbox Expiry Simulator
    # ==================================================================
    st.markdown(
        '<div class="sec-hdr">סימולטור פקיעה</div>',
        unsafe_allow_html=True)

    if not st.session_state.demo_trades:
        st.info("פתח פוזיציה כדי להריץ סימולציית פקיעה.")
    else:
        with st.expander("⚡ הרץ סימולציית פקיעה", expanded=True):
            st.caption(
                "הזן מחיר פקיעה מדומה כדי לראות מה היה קורה. "
                "הפוזיציה תיסגר, ה-P&L יעדכן את היתרה."
            )

            # Select which position to settle
            trade_labels = [
                f"#{t['id']} — {t['interval_pct']}% "
                f"({t['sp_strike']:,.0f}—{t['sc_strike']:,.0f})"
                for t in st.session_state.demo_trades
            ]

            if trade_labels:
                sel_trade = st.selectbox(
                    "בחר פוזיציה לסימולציה",
                    trade_labels, key="demo_settle_select")
                sel_idx_trade = trade_labels.index(sel_trade)
                active_trade = st.session_state.demo_trades[sel_idx_trade]

                # Mock expiry price input
                default_price = idx_demo if idx_demo > 0 else 2000.0
                mock_price = st.number_input(
                    "מחיר פקיעה מדומה (TA-35)",
                    min_value=1000.0, max_value=10000.0,
                    value=default_price, step=10.0,
                    key="demo_mock_price")

                # Preview P&L before confirming
                t = active_trade
                sp = t["sp_strike"]
                sc = t["sc_strike"]
                lp = t["lp_strike"]
                lc = t["lc_strike"]
                prem = t["net_premium"]
                w_put = t["wing_put"]
                w_call = t["wing_call"]

                if sp <= mock_price <= sc:
                    sim_pnl_pts = prem
                    sim_status = "max_profit"
                    sim_icon = "✅"
                    sim_label = "מדד בטווח הרווח — רווח מלא"
                elif lp <= mock_price < sp:
                    intrusion = sp - mock_price
                    sim_pnl_pts = prem - intrusion
                    sim_status = "partial_loss_put"
                    sim_icon = "⚠️"
                    sim_label = f"חדירה של {intrusion:,.0f} נק׳ בצד Put"
                elif sc < mock_price <= lc:
                    intrusion = mock_price - sc
                    sim_pnl_pts = prem - intrusion
                    sim_status = "partial_loss_call"
                    sim_icon = "⚠️"
                    sim_label = f"חדירה של {intrusion:,.0f} נק׳ בצד Call"
                elif mock_price < lp:
                    sim_pnl_pts = prem - w_put
                    sim_status = "max_loss_put"
                    sim_icon = "❌"
                    sim_label = "מדד מתחת ל-Long Put — הפסד מקסימלי"
                else:
                    sim_pnl_pts = prem - w_call
                    sim_status = "max_loss_call"
                    sim_icon = "❌"
                    sim_label = "מדד מעל ל-Long Call — הפסד מקסימלי"

                sim_pnl_ils = round(sim_pnl_pts * TASE_MULTIPLIER, 2)
                pnl_color = C_GREEN if sim_pnl_ils >= 0 else C_RED
                pnl_prefix = "+" if sim_pnl_ils >= 0 else ""

                st.markdown(f"""
                <div style="text-align:center; padding: 12px 0;">
                    <div style="font-size:13px; color:{C_DIM};">
                        {sim_icon} {sim_label}</div>
                    <div style="font-size:28px; font-weight:800;
                                color:{pnl_color}; margin-top:4px;">
                        {pnl_prefix}{sim_pnl_ils:,.0f} ₪
                    </div>
                    <div style="font-size:11px; color:{C_DIM};
                                margin-top:2px;">
                        {sim_pnl_pts:+,.2f} נק׳ × {TASE_MULTIPLIER}
                    </div>
                </div>
                """, unsafe_allow_html=True)

                # Settle button
                if st.button(
                    f"⚡ סגור פוזיציה #{active_trade['id']} "
                    f"ועדכן יתרה",
                    use_container_width=True,
                    key=f"demo_settle_btn_{active_trade['id']}",
                ):
                    # Move from active to history
                    settled_trade = st.session_state.demo_trades.pop(
                        sel_idx_trade)
                    settled_trade["status"] = "SETTLED"
                    settled_trade["settlement_price"] = mock_price
                    settled_trade["pnl_points"] = round(sim_pnl_pts, 2)
                    settled_trade["pnl_ils"] = sim_pnl_ils
                    settled_trade["result_status"] = sim_status
                    settled_trade["settled_at"] = now.strftime(
                        "%Y-%m-%d %H:%M")

                    st.session_state.demo_history.append(settled_trade)
                    st.session_state.demo_balance += sim_pnl_ils

                    st.success(
                        f"פוזיציה #{settled_trade['id']} נסגרה — "
                        f"P&L: {pnl_prefix}{sim_pnl_ils:,.0f} ₪ | "
                        f"יתרה חדשה: ₪{st.session_state.demo_balance:,.0f}")
                    st.rerun()

    # ==================================================================
    # SECTION 4: Demo Trade History
    # ==================================================================
    if st.session_state.demo_history:
        st.markdown("---")
        st.markdown(
            '<div class="sec-hdr">היסטוריית עסקאות דמו</div>',
            unsafe_allow_html=True)

        hist_rows = []
        for t in reversed(st.session_state.demo_history):
            pnl = t.get("pnl_ils", 0)
            hist_rows.append({
                "#": t["id"],
                "זמן פתיחה": t["timestamp"],
                "מרווח": f'{t["interval_pct"]}%',
                "טווח": f'{t["sp_strike"]:,.0f}—{t["sc_strike"]:,.0f}',
                "כניסה": f'{t["base_index"]:,.2f}',
                "פקיעה": f'{t.get("settlement_price", 0):,.2f}',
                "תוצאה": t.get("result_status", ""),
                "P&L ₪": f'{pnl:+,.0f}',
            })
        st.dataframe(pd.DataFrame(hist_rows),
                     use_container_width=True, hide_index=True)

        # Cumulative chart
        pnls = [t.get("pnl_ils", 0) for t in st.session_state.demo_history]
        cum = []
        running = 0
        for p in pnls:
            running += p
            cum.append(running)

        if len(cum) > 1:
            fig = go.Figure()
            fig.add_trace(go.Scatter(
                x=list(range(1, len(cum) + 1)), y=cum,
                mode="lines+markers",
                line=dict(color=C_GREEN if cum[-1] >= 0 else C_RED,
                          width=2.5),
                marker=dict(size=6),
                hovertemplate="עסקה #%{x}<br>P&L מצטבר: ₪%{y:,.0f}<extra></extra>",
            ))
            fig.update_layout(
                showlegend=False,
                xaxis_title="עסקה #", yaxis_title="P&L מצטבר (₪)",
            )
            plotly_layout(fig, h=250)
            st.plotly_chart(fig, use_container_width=True,
                            key="demo_cum_chart")

    # ---- Reset button ----
    st.markdown("---")
    col_r1, col_r2 = st.columns([3, 1])
    with col_r2:
        if st.button("🗑️ אפס חשבון דמו", key="demo_reset_btn"):
            st.session_state.demo_balance = DEMO_INITIAL_BALANCE
            st.session_state.demo_trades = []
            st.session_state.demo_history = []
            st.rerun()
