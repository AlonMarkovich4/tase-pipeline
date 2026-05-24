"""
TASE TA-35 Options Dashboard
"""

import os
import streamlit as st
import pandas as pd
import httpx
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(
    page_title="TA-35 Options Monitor",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Professional dark theme CSS
# ------------------------------------------------------------------
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

/* ---- Base ---- */
html, body, [class*="css"] {
    font-family: 'Inter', -apple-system, BlinkMacSystemFont, sans-serif;
}
.main .block-container {
    direction: rtl;
    text-align: right;
    padding-top: 2rem;
    max-width: 1200px;
}
[data-testid="stSidebar"] { direction: rtl; text-align: right; }
[data-testid="stSidebar"] > div:first-child {
    background-color: #0c111b;
    border-left: 1px solid #1f2937;
}
[data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
[data-testid="stRadio"] > div { direction: rtl; }
[data-testid="stRadio"] label {
    direction: rtl;
    text-align: right;
    font-size: 14px;
    font-weight: 500;
    color: #d1d5db;
}
[data-testid="stAlert"] { direction: rtl; text-align: right; }
[data-testid="stSelectbox"] label { direction: rtl; text-align: right; }

/* ---- Hide branding ---- */
#MainMenu, footer, header { visibility: hidden; }

/* ---- Metric card ---- */
.metric-row {
    display: flex;
    gap: 12px;
    margin-bottom: 24px;
    flex-wrap: wrap;
}
.metric-card {
    flex: 1;
    min-width: 160px;
    background: #111827;
    border: 1px solid #1f2937;
    border-radius: 8px;
    padding: 16px 20px;
}
.metric-card .label {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 6px;
}
.metric-card .value {
    font-size: 22px;
    font-weight: 700;
    color: #f9fafb;
    direction: ltr;
    unicode-bidi: isolate;
}
.metric-card .value.green { color: #10b981; }
.metric-card .value.red { color: #ef4444; }
.metric-card .value.sm { font-size: 16px; }
.metric-card .sub {
    font-size: 11px;
    color: #6b7280;
    margin-top: 2px;
}

/* ---- Page header ---- */
.page-header {
    font-size: 20px;
    font-weight: 700;
    color: #f9fafb;
    margin-bottom: 24px;
    padding-bottom: 12px;
    border-bottom: 1px solid #1f2937;
    display: flex;
    align-items: center;
    gap: 10px;
}
.page-header .dot {
    width: 8px; height: 8px;
    border-radius: 50%;
    display: inline-block;
}
.page-header .dot.green { background: #10b981; }
.page-header .dot.gray { background: #6b7280; }

/* ---- Section header ---- */
.section-hdr {
    font-size: 15px;
    font-weight: 600;
    color: #d1d5db;
    margin: 20px 0 12px;
    padding-bottom: 8px;
    border-bottom: 1px solid #1f2937;
}

/* ---- Sidebar ---- */
.sb-brand {
    text-align: center;
    padding: 16px 0 8px;
    border-bottom: 1px solid #1f2937;
    margin-bottom: 16px;
}
.sb-brand .name {
    font-size: 15px;
    font-weight: 700;
    color: #f9fafb;
    letter-spacing: 1px;
}
.sb-brand .sub {
    font-size: 11px;
    color: #6b7280;
    margin-top: 2px;
}
.sb-info {
    font-size: 13px;
    color: #9ca3af;
    text-align: center;
    padding: 4px 0;
    line-height: 1.6;
}
.sb-status {
    text-align: center;
    font-size: 12px;
    font-weight: 600;
    padding: 8px;
    border-radius: 6px;
    margin: 10px 0;
}
.sb-status.on {
    background: rgba(16, 185, 129, 0.1);
    border: 1px solid rgba(16, 185, 129, 0.3);
    color: #10b981;
}
.sb-status.off {
    background: rgba(239, 68, 68, 0.1);
    border: 1px solid rgba(239, 68, 68, 0.3);
    color: #ef4444;
}

/* ---- DataFrames ---- */
div[data-testid="stDataFrame"] {
    border: 1px solid #1f2937;
    border-radius: 6px;
    overflow: hidden;
}

/* ---- Buttons ---- */
.stButton > button {
    background: #1f2937 !important;
    color: #d1d5db !important;
    border: 1px solid #374151 !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 13px !important;
    width: 100% !important;
    transition: background 0.2s !important;
}
.stButton > button:hover {
    background: #374151 !important;
    color: #f9fafb !important;
}

/* ---- Dividers ---- */
hr { border-color: #1f2937 !important; opacity: 0.6 !important; }

/* ---- Expiry day tag ---- */
.expiry-tag {
    display: inline-block;
    font-size: 14px;
    font-weight: 600;
    color: #e5e7eb;
    padding: 6px 0;
    margin: 16px 0 8px;
    border-bottom: 2px solid #374151;
    width: 100%;
}
.expiry-tag .settled {
    font-size: 11px;
    font-weight: 600;
    color: #10b981;
    background: rgba(16,185,129,0.1);
    padding: 2px 8px;
    border-radius: 4px;
    margin-right: 8px;
}
.expiry-tag .open-tag {
    font-size: 11px;
    font-weight: 600;
    color: #6b7280;
    background: #1f2937;
    padding: 2px 8px;
    border-radius: 4px;
    margin-right: 8px;
}

/* ---- Position indicator ---- */
.pos-indicator {
    font-size: 13px;
    padding: 8px 14px;
    border-radius: 6px;
    margin: 8px 0 16px;
    font-weight: 500;
}
.pos-indicator.safe {
    background: rgba(16, 185, 129, 0.08);
    border: 1px solid rgba(16, 185, 129, 0.2);
    color: #10b981;
}
.pos-indicator.warn {
    background: rgba(245, 158, 11, 0.08);
    border: 1px solid rgba(245, 158, 11, 0.2);
    color: #f59e0b;
}
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")
DAY_HE = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"}


def _headers():
    return {"apikey": SUPABASE_KEY, "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}


@st.cache_data(ttl=60)
def fetch_table(table: str, params: str = "") -> pd.DataFrame:
    url = f"{SUPABASE_URL}/rest/v1/{table}?select=*{params}"
    try:
        r = httpx.get(url, headers=_headers(), timeout=15)
        if r.status_code in (200, 206):
            data = r.json()
            if data:
                return pd.DataFrame(data)
    except Exception:
        pass
    return pd.DataFrame()


def cnum(val):
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def get_index(df):
    for col in ["underlingasset_call", "underlingasset_put"]:
        if col in df.columns:
            vals = df[col].apply(cnum)
            vals = vals[vals > 0]
            if not vals.empty:
                return vals.iloc[0]
    return 0.0


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
st.sidebar.markdown("""
<div class="sb-brand">
    <div class="name">◆ TA-35 OPTIONS</div>
    <div class="sub">Real-Time Monitor</div>
</div>
""", unsafe_allow_html=True)

now = datetime.now(TZ_ISRAEL)
day_he = DAY_HE.get(now.weekday(), "")
is_trading = now.weekday() in {0, 1, 2, 3, 4} and 9 <= now.hour < 18

st.sidebar.markdown(
    f'<div class="sb-info">יום {day_he} · {now.strftime("%d/%m/%Y")} · {now.strftime("%H:%M")}</div>',
    unsafe_allow_html=True)

if is_trading:
    st.sidebar.markdown('<div class="sb-status on">LIVE — שעות מסחר</div>', unsafe_allow_html=True)
else:
    st.sidebar.markdown('<div class="sb-status off">CLOSED — מחוץ לשעות מסחר</div>', unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.sidebar.button("רענן נתונים"):
    st.cache_data.clear()
    st.rerun()

page = st.sidebar.radio("", ["מוניטור חי", "אסטרטגיות", "ביצועים"])

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<div class="sb-info" style="opacity:0.4; font-size:11px;">v2.0 · Render · Supabase</div>',
    unsafe_allow_html=True)


# ==================================================================
# PAGE 1 — LIVE MONITOR
# ==================================================================
if page == "מוניטור חי":
    dot = "green" if is_trading else "gray"
    st.markdown(f'<div class="page-header"><span class="dot {dot}"></span>מוניטור חי — Put/Call Data</div>',
                unsafe_allow_html=True)

    df = fetch_table("tase_putcall")

    if df.empty:
        st.warning("אין נתונים זמינים כרגע")
    else:
        index_val = get_index(df)
        fetch_date = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else "—"
        fetch_time = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        n_exp = df["expiry_date"].nunique() if "expiry_date" in df.columns else 0

        st.markdown(f"""
        <div class="metric-row">
            <div class="metric-card">
                <div class="label">מדד TA-35</div>
                <div class="value">{index_val:,.2f}</div>
            </div>
            <div class="metric-card">
                <div class="label">עדכון אחרון</div>
                <div class="value sm">{fetch_date}</div>
                <div class="sub">{fetch_time}</div>
            </div>
            <div class="metric-card">
                <div class="label">ימי פקיעה</div>
                <div class="value">{n_exp}</div>
            </div>
            <div class="metric-card">
                <div class="label">סה״כ רשומות</div>
                <div class="value">{len(df)}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Expiry filter
        if "expiry_date" in df.columns:
            expiries = sorted(df["expiry_date"].unique())
            labels = []
            for e in expiries:
                try:
                    d = date.fromisoformat(e)
                    labels.append(f"יום {DAY_HE.get(d.weekday(), '')} — {e}")
                except Exception:
                    labels.append(e)
            sel = st.selectbox("פקיעה", labels, index=0)
            df = df[df["expiry_date"] == expiries[labels.index(sel)]]

        wanted = [
            "derivativename_call", "expirationprice_call", "lastrate_call", "openpositions_call",
            "derivativename_put", "expirationprice_put", "lastrate_put", "openpositions_put",
        ]
        cols = [c for c in wanted if c in df.columns]
        if cols:
            dfd = df[cols].rename(columns={
                "derivativename_call": "Call", "expirationprice_call": "Strike C",
                "lastrate_call": "מחיר C", "openpositions_call": "O.I Call",
                "derivativename_put": "Put", "expirationprice_put": "Strike P",
                "lastrate_put": "מחיר P", "openpositions_put": "O.I Put",
            })
            st.dataframe(dfd, use_container_width=True, height=520, hide_index=True)
        else:
            st.dataframe(df, use_container_width=True, height=520, hide_index=True)


# ==================================================================
# PAGE 2 — STRATEGIES
# ==================================================================
elif page == "אסטרטגיות":
    st.markdown('<div class="page-header">אסטרטגיות Iron Condor — שבועי</div>',
                unsafe_allow_html=True)

    df_strat = fetch_table("iron_condor_strategies",
                           "&order=trigger_date.desc,expiry_date,interval_pct")

    if df_strat.empty:
        st.info("אין אסטרטגיות. הראשונה תיווצר ביום מסחר הקרוב אחרי 12:00.")
    else:
        today_d = date.today()
        mon = today_d - timedelta(days=today_d.weekday())
        fri = mon + timedelta(days=4)
        df_strat["_dt"] = pd.to_datetime(df_strat["trigger_date"], errors="coerce")
        df_w = df_strat[(df_strat["_dt"] >= pd.Timestamp(mon)) &
                        (df_strat["_dt"] <= pd.Timestamp(fri))].copy()
        if df_w.empty:
            latest = df_strat["trigger_date"].max()
            df_w = df_strat[df_strat["trigger_date"] == latest].copy()
            st.info(f"אין אסטרטגיות השבוע — מציג {latest}")

        # Current index
        idx = get_index(fetch_table("tase_putcall"))
        if idx > 0:
            st.markdown(f"""
            <div class="metric-row">
                <div class="metric-card" style="flex:0 0 220px;">
                    <div class="label">מדד TA-35 נוכחי</div>
                    <div class="value">{idx:,.2f}</div>
                </div>
            </div>
            """, unsafe_allow_html=True)

        for exp_date in sorted(df_w["expiry_date"].unique()):
            try:
                exp_d = date.fromisoformat(exp_date)
                dn = DAY_HE.get(exp_d.weekday(), "")
            except Exception:
                dn = ""

            df_e = df_w[df_w["expiry_date"] == exp_date].sort_values("interval_pct")
            has_res = df_e["result_status"].notna().any() if "result_status" in df_e.columns else False

            tag = f'<span class="settled">SETTLED</span>' if has_res else '<span class="open-tag">OPEN</span>'
            st.markdown(f'<div class="expiry-tag">יום {dn} · {exp_date} {tag}</div>',
                        unsafe_allow_html=True)

            rows = []
            for _, r in df_e.iterrows():
                result = r.get("result_status", None)
                pnl = cnum(r.get("actual_pnl_ils", 0))
                rows.append({
                    "מרווח": f'{cnum(r.get("interval_pct", 0))}%',
                    "LP": f'{cnum(r.get("long_put_strike", 0)):.0f}',
                    "SP": f'{cnum(r.get("short_put_strike", 0)):.0f}',
                    "SC": f'{cnum(r.get("short_call_strike", 0)):.0f}',
                    "LC": f'{cnum(r.get("long_call_strike", 0)):.0f}',
                    "פרמיה": f'{cnum(r.get("total_net_premium", 0)):.2f}',
                    "רווח מקס": f'{cnum(r.get("max_profit_ils", 0)):,.0f}',
                    "סיכון מקס": f'{cnum(r.get("max_risk_ils", 0)):,.0f}',
                    "סטטוס": result or "פתוח",
                    "P&L": f"{pnl:+,.0f}" if result else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            if idx > 0 and not df_e.empty:
                mid = df_e.iloc[len(df_e) // 2]
                sp = cnum(mid.get("short_put_strike", 0))
                sc = cnum(mid.get("short_call_strike", 0))
                if sp > 0 and sc > 0:
                    if sp <= idx <= sc:
                        st.markdown(
                            f'<div class="pos-indicator safe">מדד {idx:,.2f} בטווח הרווח ({sp:.0f} – {sc:.0f})</div>',
                            unsafe_allow_html=True)
                    elif idx < sp:
                        st.markdown(
                            f'<div class="pos-indicator warn">מדד {idx:,.2f} מתחת ל-Short Put ({sp:.0f}) ב-{sp - idx:.0f} נק׳</div>',
                            unsafe_allow_html=True)
                    else:
                        st.markdown(
                            f'<div class="pos-indicator warn">מדד {idx:,.2f} מעל ל-Short Call ({sc:.0f}) ב-{idx - sc:.0f} נק׳</div>',
                            unsafe_allow_html=True)


# ==================================================================
# PAGE 3 — PERFORMANCE
# ==================================================================
elif page == "ביצועים":
    st.markdown('<div class="page-header">ביצועים היסטוריים</div>',
                unsafe_allow_html=True)

    df_h = fetch_table("iron_condor_strategies",
                       "&result_status=not.is.null&order=trigger_date,interval_pct")

    if df_h.empty:
        st.info("אין תוצאות עדיין — יופיעו אחרי הפקיעה הראשונה.")
    else:
        for c in ["actual_pnl_ils", "max_profit_ils", "max_risk_ils", "interval_pct"]:
            if c in df_h.columns:
                df_h[c] = df_h[c].apply(cnum)

        total = df_h["actual_pnl_ils"].sum()
        trades = len(df_h)
        wins = len(df_h[df_h["actual_pnl_ils"] > 0])
        wr = (wins / trades * 100) if trades > 0 else 0
        pnl_cls = "green" if total >= 0 else "red"

        st.markdown(f"""
        <div class="metric-row">
            <div class="metric-card">
                <div class="label">סה״כ P&L</div>
                <div class="value {pnl_cls}">{total:+,.0f} ₪</div>
            </div>
            <div class="metric-card">
                <div class="label">אחוז הצלחה</div>
                <div class="value">{wr:.0f}%</div>
                <div class="sub">{wins} מתוך {trades}</div>
            </div>
            <div class="metric-card">
                <div class="label">עסקאות סגורות</div>
                <div class="value">{trades}</div>
            </div>
        </div>
        """, unsafe_allow_html=True)

        # Charts
        st.markdown('<div class="section-hdr">P&L מצטבר</div>', unsafe_allow_html=True)
        dbd = df_h.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        dbd.columns = ["date", "pnl"]
        dbd["cum"] = dbd["pnl"].cumsum()
        dbd = dbd.set_index("date")
        st.bar_chart(dbd["pnl"], color="#10b981")
        st.line_chart(dbd["cum"], color="#3b82f6")

        st.markdown("---")

        st.markdown('<div class="section-hdr">לפי מרווח</div>', unsafe_allow_html=True)
        dbp = df_h.groupby("interval_pct").agg(
            pnl=("actual_pnl_ils", "sum"),
            avg=("actual_pnl_ils", "mean"),
            n=("actual_pnl_ils", "count"),
            w=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        dbp["wr"] = (dbp["w"] / dbp["n"] * 100).round(1)
        dbp.columns = ["מרווח %", "סה״כ P&L", "ממוצע", "עסקאות", "ניצחונות", "הצלחה %"]
        st.dataframe(dbp, use_container_width=True, hide_index=True)

        st.markdown("---")

        st.markdown('<div class="section-hdr">היסטוריה מלאה</div>', unsafe_allow_html=True)
        det = ["trigger_date", "expiry_date", "interval_pct",
               "short_put_strike", "short_call_strike",
               "actual_index_close", "result_status", "actual_pnl_ils"]
        avail = [c for c in det if c in df_h.columns]
        dfd = df_h[avail].rename(columns={
            "trigger_date": "תאריך", "expiry_date": "פקיעה", "interval_pct": "מרווח",
            "short_put_strike": "SP", "short_call_strike": "SC",
            "actual_index_close": "מדד פקיעה", "result_status": "תוצאה", "actual_pnl_ils": "P&L",
        })
        st.dataframe(dfd, use_container_width=True, height=400, hide_index=True)
