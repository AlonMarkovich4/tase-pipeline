"""
TASE TA-35 — Premium Options Trading Workstation
=================================================
Enterprise-grade dashboard: live monitor, Iron Condor strategies
with Plotly range-risk visualizations, and historical P&L analytics.
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

# Palette
C_BG       = "#0B0D10"
C_CARD     = "#151921"
C_BORDER   = "#1E2433"
C_TEXT     = "#E8EAED"
C_DIM      = "#6B7B8D"
C_GREEN    = "#00E676"
C_RED      = "#FF1744"
C_BLUE     = "#00B0FF"
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
page = st.sidebar.radio("ניווט", ["מוניטור חי", "אסטרטגיות", "ביצועים"])
st.sidebar.markdown("---")

if st.sidebar.button("🔄 רענן נתונים", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.markdown("---")
st.sidebar.caption("v2.0 · Render · Supabase · Telegram")


# ==================================================================
# PAGE 1: LIVE MONITOR
# ==================================================================
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


# ==================================================================
# PAGE 2: STRATEGIES
# ==================================================================
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

        # ---------- Break-Even Range Chart ----------
        if not df_e.empty:
            rows_data = []
            for _, r in df_e.iterrows():
                lp  = N(r.get("long_put_strike")) or 0
                sp  = N(r.get("short_put_strike")) or 0
                sc  = N(r.get("short_call_strike")) or 0
                lc  = N(r.get("long_call_strike")) or 0
                bl  = N(r.get("breakeven_lower")) or 0
                bh  = N(r.get("breakeven_upper")) or 0
                pct = N(r.get("interval_pct")) or 0
                mp  = N(r.get("max_profit_ils")) or 0
                mr  = N(r.get("max_risk_ils")) or 0
                if lp == 0 or lc == 0:
                    continue
                rows_data.append(dict(
                    pct=pct, lp=lp, sp=sp, sc=sc, lc=lc,
                    bl=bl, bh=bh, mp=mp, mr=mr))

            if rows_data:
                # Sort widest at top (reversed for plotly y-axis)
                rows_data.sort(key=lambda d: d["pct"])
                labels = [f"{d['pct']:.1f}%" for d in rows_data]
                x_lo = min(d["lp"] for d in rows_data) - 20
                x_hi = max(d["lc"] for d in rows_data) + 20

                fig = go.Figure()

                for i, d in enumerate(rows_data):
                    y = labels[i]

                    # Risk zone left (Long Put → BE lower)
                    fig.add_trace(go.Bar(
                        x=[d["bl"] - d["lp"]], y=[y],
                        base=d["lp"], orientation="h",
                        marker=dict(color="rgba(255,23,68,0.15)",
                                    line=dict(width=0)),
                        width=0.5, showlegend=False,
                        hovertemplate=(
                            f"<b>{y}</b> הפסד<br>"
                            f"Long Put: {d['lp']:,.0f}<br>"
                            f"BE: {d['bl']:,.0f}<br>"
                            f"סיכון: -{d['mr']:,.0f} ₪"
                            "<extra></extra>"),
                    ))

                    # Profit zone (BE lower → BE upper)
                    fig.add_trace(go.Bar(
                        x=[d["bh"] - d["bl"]], y=[y],
                        base=d["bl"], orientation="h",
                        marker=dict(color="rgba(0,230,118,0.25)",
                                    line=dict(width=0)),
                        width=0.5, showlegend=False,
                        hovertemplate=(
                            f"<b>{y}</b> רווח<br>"
                            f"BE: {d['bl']:,.0f} — {d['bh']:,.0f}<br>"
                            f"Short Put: {d['sp']:,.0f} | "
                            f"Short Call: {d['sc']:,.0f}<br>"
                            f"רווח מקס: +{d['mp']:,.0f} ₪"
                            "<extra></extra>"),
                    ))

                    # Risk zone right (BE upper → Long Call)
                    fig.add_trace(go.Bar(
                        x=[d["lc"] - d["bh"]], y=[y],
                        base=d["bh"], orientation="h",
                        marker=dict(color="rgba(255,23,68,0.15)",
                                    line=dict(width=0)),
                        width=0.5, showlegend=False,
                        hovertemplate=(
                            f"<b>{y}</b> הפסד<br>"
                            f"BE: {d['bh']:,.0f}<br>"
                            f"Long Call: {d['lc']:,.0f}<br>"
                            f"סיכון: -{d['mr']:,.0f} ₪"
                            "<extra></extra>"),
                    ))

                    # Short strikes — inner ticks
                    fig.add_trace(go.Scatter(
                        x=[d["sp"], d["sc"]], y=[y, y],
                        mode="markers",
                        marker=dict(symbol="line-ns", size=8,
                                    line=dict(width=1.5,
                                              color="rgba(0,230,118,0.6)")),
                        showlegend=False,
                        hovertemplate=(
                            f"Short: %{{x:,.0f}}<extra></extra>"),
                    ))

                    # Profit annotation on the right
                    fig.add_annotation(
                        x=d["lc"] + 3, y=y,
                        text=f"+{d['mp']:,.0f}₪",
                        showarrow=False, xanchor="left",
                        font=dict(size=9, color=C_GREEN),
                    )

                # Current index line
                if idx > 0:
                    fig.add_vline(
                        x=idx, line_width=1.5, line_dash="dot",
                        line_color=C_BLUE,
                        annotation_text=f"TA-35: {idx:,.0f}",
                        annotation_position="top",
                        annotation_font=dict(size=9, color=C_BLUE),
                    )

                # Settlement line
                if has_res and "actual_index_close" in df_e.columns:
                    cv = N(df_e["actual_index_close"].iloc[0])
                    if cv and cv > 0:
                        fig.add_vline(
                            x=cv, line_width=1.5,
                            line_color=C_RED,
                            annotation_text=f"פקיעה: {cv:,.0f}",
                            annotation_position="top right",
                            annotation_font=dict(size=9, color=C_RED),
                        )

                n_rows = len(rows_data)
                fig.update_layout(
                    barmode="stack",
                    xaxis=dict(
                        range=[x_lo, x_hi + 60],
                        showgrid=False, showline=False,
                        zeroline=False,
                        tickfont=dict(size=9, color=C_DIM),
                    ),
                    yaxis=dict(
                        showgrid=False, showline=False,
                        tickfont=dict(size=10, color=C_TEXT,
                                      family="Inter"),
                        autorange="reversed",
                    ),
                    height=max(120, 28 * n_rows + 50),
                    margin=dict(l=4, r=4, t=20, b=4),
                    plot_bgcolor=C_CARD,
                    paper_bgcolor=C_CARD,
                    font=dict(family="Inter", color=C_TEXT, size=9),
                    hoverlabel=dict(
                        bgcolor=C_CARD, bordercolor=C_BORDER,
                        font=dict(color=C_TEXT, size=10),
                    ),
                    hovermode="closest",
                )
                st.plotly_chart(fig, use_container_width=True,
                                key=f"range_{exp_date}")

        # ---------- Variation selector + detail card ----------
        intervals = sorted(df_e["interval_pct"].unique())
        int_labels = [f"{p:.1f}%" for p in intervals]
        sel_int = st.select_slider(
            "מרווח", options=int_labels,
            value=int_labels[len(int_labels) // 2] if int_labels else None,
            key=f"slider_{exp_date}")
        sel_pct = intervals[int_labels.index(sel_int)]
        sr = df_e[df_e["interval_pct"] == sel_pct].iloc[0]

        lp_v  = N(sr.get("long_put_strike")) or 0
        sp_v  = N(sr.get("short_put_strike")) or 0
        sc_v  = N(sr.get("short_call_strike")) or 0
        lc_v  = N(sr.get("long_call_strike")) or 0
        bl_v  = N(sr.get("breakeven_lower")) or 0
        bh_v  = N(sr.get("breakeven_upper")) or 0
        prem  = N(sr.get("total_net_premium")) or 0
        mp_v  = N(sr.get("max_profit_ils")) or 0
        mr_v  = N(sr.get("max_risk_ils")) or 0
        rr_v  = N(sr.get("risk_reward_ratio")) or 0
        dte_v = N(sr.get("days_to_expiry")) or 0
        res   = sr.get("result_status")
        pnl_v = N(sr.get("actual_pnl_ils"))

        # Position status
        if idx > 0 and sp_v > 0 and sc_v > 0:
            if sp_v <= idx <= sc_v:
                pos_html = (f'<span style="color:{C_GREEN}">✅ מדד בטווח הרווח'
                            f' ({sp_v:,.0f} – {sc_v:,.0f})</span>')
            elif idx < sp_v:
                pos_html = (f'<span style="color:{C_RED}">⚠️ מתחת ל-Short Put'
                            f' ב-{sp_v - idx:,.0f} נק׳</span>')
            else:
                pos_html = (f'<span style="color:{C_RED}">⚠️ מעל ל-Short Call'
                            f' ב-{idx - sc_v:,.0f} נק׳</span>')
        else:
            pos_html = ""

        status_badge = ""
        if res:
            pnl_color = C_GREEN if pnl_v and pnl_v >= 0 else C_RED
            pnl_sign = "+" if pnl_v and pnl_v >= 0 else ""
            status_badge = (
                f'<div style="text-align:center;margin-top:8px;">'
                f'<span style="font-size:18px;font-weight:700;'
                f'color:{pnl_color}">'
                f'{pnl_sign}{pnl_v:,.0f} ₪</span>'
                f'<div style="font-size:10px;color:{C_DIM};'
                f'margin-top:2px">{res}</div></div>')

        st.markdown(f"""
        <div style="background:{C_CARD};border:1px solid {C_BORDER};
                    border-radius:10px;padding:16px 20px;
                    margin:8px 0 4px;">
            <div style="display:flex;justify-content:space-between;
                        align-items:center;margin-bottom:10px;">
                <span style="font-size:15px;font-weight:700;
                             color:{C_TEXT}">
                    מרווח {sel_int}</span>
                <span style="font-size:11px;color:{C_DIM}">
                    {int(dte_v)} ימים לפקיעה</span>
            </div>
            <div style="display:grid;
                        grid-template-columns:repeat(4,1fr);
                        gap:10px;direction:ltr;">
                <div style="text-align:center">
                    <div style="font-size:9px;color:{C_DIM};
                                text-transform:uppercase;
                                letter-spacing:0.5px">Long Put</div>
                    <div style="font-size:14px;font-weight:600;
                                color:{C_RED}">{lp_v:,.0f}</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:9px;color:{C_DIM};
                                text-transform:uppercase;
                                letter-spacing:0.5px">Short Put</div>
                    <div style="font-size:14px;font-weight:600;
                                color:{C_GREEN}">{sp_v:,.0f}</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:9px;color:{C_DIM};
                                text-transform:uppercase;
                                letter-spacing:0.5px">Short Call</div>
                    <div style="font-size:14px;font-weight:600;
                                color:{C_GREEN}">{sc_v:,.0f}</div>
                </div>
                <div style="text-align:center">
                    <div style="font-size:9px;color:{C_DIM};
                                text-transform:uppercase;
                                letter-spacing:0.5px">Long Call</div>
                    <div style="font-size:14px;font-weight:600;
                                color:{C_RED}">{lc_v:,.0f}</div>
                </div>
            </div>
            <div style="border-top:1px solid {C_BORDER};
                        margin:10px 0;padding-top:10px;
                        display:grid;
                        grid-template-columns:repeat(4,1fr);
                        gap:8px;text-align:center;">
                <div>
                    <div style="font-size:9px;color:{C_DIM}">פרמיה</div>
                    <div style="font-size:13px;font-weight:600;
                                color:{C_TEXT}">{prem:,.2f}</div>
                </div>
                <div>
                    <div style="font-size:9px;color:{C_DIM}">רווח מקס</div>
                    <div style="font-size:13px;font-weight:600;
                                color:{C_GREEN}">+{mp_v:,.0f} ₪</div>
                </div>
                <div>
                    <div style="font-size:9px;color:{C_DIM}">סיכון מקס</div>
                    <div style="font-size:13px;font-weight:600;
                                color:{C_RED}">-{mr_v:,.0f} ₪</div>
                </div>
                <div>
                    <div style="font-size:9px;color:{C_DIM}">Risk/Reward</div>
                    <div style="font-size:13px;font-weight:600;
                                color:{C_TEXT}">{rr_v:.1f}x</div>
                </div>
            </div>
            <div style="border-top:1px solid {C_BORDER};
                        margin-top:8px;padding-top:8px;
                        display:flex;justify-content:space-between;
                        font-size:11px;">
                <span style="color:{C_DIM}">BE תחתון:
                    <b style="color:{C_TEXT}">{bl_v:,.0f}</b></span>
                <span style="color:{C_DIM}">BE עליון:
                    <b style="color:{C_TEXT}">{bh_v:,.0f}</b></span>
            </div>
            {"<div style='margin-top:6px;text-align:center;font-size:12px'>"
             + pos_html + "</div>" if pos_html else ""}
            {status_badge}
        </div>
        """, unsafe_allow_html=True)

        st.markdown("---")


# ==================================================================
# PAGE 3: PERFORMANCE
# ==================================================================
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
