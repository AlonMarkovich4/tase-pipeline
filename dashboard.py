"""
TASE Pipeline — Streamlit Dashboard
=====================================
Live monitor, strategy viewer, and historical P&L analytics.
"""

import os
import streamlit as st
import pandas as pd
import httpx
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------
# Page config
# ------------------------------------------------------------------
st.set_page_config(
    page_title="TASE TA-35 Dashboard",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# CSS — clean RTL + dark theme
# ------------------------------------------------------------------
st.markdown("""
<style>
    /* ---- Global RTL ---- */
    .main .block-container { direction: rtl; text-align: right; }
    [data-testid="stSidebar"] { direction: rtl; text-align: right; }
    [data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
    [data-testid="stRadio"] > div { direction: rtl; }
    [data-testid="stRadio"] label { direction: rtl; text-align: right; }
    [data-testid="stAlert"] { direction: rtl; text-align: right; }

    /* ---- Hide branding ---- */
    #MainMenu, footer, header { visibility: hidden; }

    /* ---- Custom KPI card ---- */
    .kpi-card {
        background: linear-gradient(145deg, #1e293b, #172033);
        border: 1px solid #334155;
        border-radius: 12px;
        padding: 20px 16px;
        text-align: center;
        min-height: 110px;
        display: flex;
        flex-direction: column;
        justify-content: center;
    }
    .kpi-label {
        font-size: 13px;
        color: #94a3b8;
        font-weight: 500;
        margin-bottom: 6px;
    }
    .kpi-value {
        font-size: 26px;
        font-weight: 700;
        color: #00d4aa;
        direction: ltr;
        unicode-bidi: isolate;
    }
    .kpi-value.small-text {
        font-size: 18px;
    }

    /* ---- Section title ---- */
    .section-title {
        font-size: 24px;
        font-weight: 700;
        color: #f1f5f9;
        margin-bottom: 20px;
        padding-bottom: 10px;
        border-bottom: 2px solid #1e293b;
    }

    /* ---- Status badge ---- */
    .status-badge {
        border-radius: 8px;
        padding: 10px;
        text-align: center;
        font-weight: 600;
        font-size: 14px;
        margin: 8px 0;
    }
    .status-badge.online {
        background: #052e16;
        border: 1px solid #22c55e;
        color: #4ade80;
    }
    .status-badge.offline {
        background: #2a1215;
        border: 1px solid #ef4444;
        color: #f87171;
    }

    /* ---- Strategy result badges ---- */
    .badge-profit { background: #052e16; color: #4ade80; padding: 3px 10px; border-radius: 6px; font-size: 13px; }
    .badge-loss { background: #2a1215; color: #f87171; padding: 3px 10px; border-radius: 6px; font-size: 13px; }
    .badge-open { background: #1e293b; color: #94a3b8; padding: 3px 10px; border-radius: 6px; font-size: 13px; }

    /* ---- Sidebar ---- */
    .sidebar-title {
        text-align: center;
        padding: 8px 0;
    }
    .sidebar-title .icon { font-size: 36px; }
    .sidebar-title .name {
        font-size: 20px;
        font-weight: 800;
        color: #00d4aa;
    }
    .sidebar-info {
        font-size: 14px;
        color: #cbd5e1;
        text-align: center;
        padding: 4px 0;
    }

    /* ---- DataFrames ---- */
    div[data-testid="stDataFrame"] {
        border: 1px solid #1e293b;
        border-radius: 10px;
        overflow: hidden;
    }

    /* ---- Buttons ---- */
    .stButton > button {
        background: #00d4aa !important;
        color: #0f172a !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: 700 !important;
        width: 100% !important;
    }

    /* ---- Dividers ---- */
    hr { border-color: #1e293b !important; opacity: 0.4 !important; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")
DAY_NAMES_HE = {0: "שני", 1: "שלישי", 2: "רביעי", 3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון"}


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


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


def clean_numeric(val):
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def kpi_card(label: str, value: str, small: bool = False):
    size_cls = " small-text" if small else ""
    return f"""
    <div class="kpi-card">
        <div class="kpi-label">{label}</div>
        <div class="kpi-value{size_cls}">{value}</div>
    </div>
    """


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
st.sidebar.markdown("""
<div class="sidebar-title">
    <div class="icon">📊</div>
    <div class="name">TASE TA-35</div>
</div>
""", unsafe_allow_html=True)
st.sidebar.markdown("---")

now = datetime.now(TZ_ISRAEL)
day_he = DAY_NAMES_HE.get(now.weekday(), "")

st.sidebar.markdown(
    f'<div class="sidebar-info">🕐 {now.strftime("%H:%M")} &nbsp;·&nbsp; '
    f'יום {day_he} &nbsp;·&nbsp; {now.strftime("%d/%m/%Y")}</div>',
    unsafe_allow_html=True,
)

is_trading = now.weekday() in {0, 1, 2, 3, 4} and 9 <= now.hour < 18
if is_trading:
    st.sidebar.markdown(
        '<div class="status-badge online">🟢 מערכת פעילה</div>',
        unsafe_allow_html=True)
else:
    st.sidebar.markdown(
        '<div class="status-badge offline">🔴 מחוץ לשעות מסחר</div>',
        unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 רענן נתונים"):
    st.cache_data.clear()
    st.rerun()

page = st.sidebar.radio(
    "ניווט",
    ["📈 מוניטור חי", "🎯 אסטרטגיות שבועיות", "📊 ביצועים היסטוריים"],
)

st.sidebar.markdown("---")
st.sidebar.markdown(
    '<div class="sidebar-info" style="opacity:0.5; font-size:12px;">'
    '🤖 TASE Pipeline v2.0<br>Render · Supabase · Telegram</div>',
    unsafe_allow_html=True)


# ==================================================================
# PAGE 1: LIVE MONITOR
# ==================================================================
if page == "📈 מוניטור חי":
    st.markdown('<div class="section-title">📈 מוניטור חי — נתוני Put/Call</div>',
                unsafe_allow_html=True)

    df = fetch_table("tase_putcall")

    if df.empty:
        st.warning("אין נתונים זמינים כרגע")
    else:
        # Extract values
        index_val = 0.0
        for col in ["underlingasset_call", "underlingasset_put"]:
            if col in df.columns:
                vals = df[col].apply(clean_numeric)
                vals = vals[vals > 0]
                if not vals.empty:
                    index_val = vals.iloc[0]
                    break

        fetch_date = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else "—"
        fetch_time = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        num_expiries = df["expiry_date"].nunique() if "expiry_date" in df.columns else 0
        num_rows = len(df)

        # KPI row — HTML cards
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.markdown(kpi_card("מדד TA-35", f"{index_val:,.2f}"), unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("עדכון אחרון", f"{fetch_time}", small=True), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("ימי פקיעה", str(num_expiries)), unsafe_allow_html=True)
        with c4:
            st.markdown(kpi_card("רשומות", str(num_rows)), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Expiry filter
        if "expiry_date" in df.columns:
            expiries = sorted(df["expiry_date"].unique())
            labels = []
            for e in expiries:
                try:
                    d = date.fromisoformat(e)
                    labels.append(f"יום {DAY_NAMES_HE.get(d.weekday(), '')} — {e}")
                except Exception:
                    labels.append(e)

            selected_label = st.selectbox("בחר יום פקיעה", labels, index=0)
            selected_expiry = expiries[labels.index(selected_label)]
            df_filtered = df[df["expiry_date"] == selected_expiry].copy()
        else:
            df_filtered = df.copy()

        # Columns to display
        wanted = [
            "derivativename_call", "expirationprice_call",
            "lastrate_call", "openpositions_call",
            "derivativename_put", "expirationprice_put",
            "lastrate_put", "openpositions_put",
        ]
        display_cols = [c for c in wanted if c in df_filtered.columns]

        if display_cols:
            display_df = df_filtered[display_cols].copy()
            rename_map = {
                "derivativename_call": "שם Call",
                "expirationprice_call": "Strike Call",
                "lastrate_call": "מחיר Call",
                "openpositions_call": "פוזיציות Call",
                "derivativename_put": "שם Put",
                "expirationprice_put": "Strike Put",
                "lastrate_put": "מחיר Put",
                "openpositions_put": "פוזיציות Put",
            }
            display_df = display_df.rename(
                columns={k: v for k, v in rename_map.items() if k in display_df.columns}
            )
            st.dataframe(display_df, use_container_width=True, height=500, hide_index=True)
        else:
            st.dataframe(df_filtered, use_container_width=True, height=500, hide_index=True)


# ==================================================================
# PAGE 2: STRATEGIES
# ==================================================================
elif page == "🎯 אסטרטגיות שבועיות":
    st.markdown('<div class="section-title">🎯 אסטרטגיות Iron Condor — שבועי</div>',
                unsafe_allow_html=True)

    df_strat = fetch_table("iron_condor_strategies",
                           "&order=trigger_date.desc,expiry_date,interval_pct")

    if df_strat.empty:
        st.info("אין אסטרטגיות עדיין. הראשונה תיווצר ביום מסחר הקרוב ב-12:00.")
    else:
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        friday = monday + timedelta(days=4)

        df_strat["trigger_date_dt"] = pd.to_datetime(df_strat["trigger_date"], errors="coerce")
        df_week = df_strat[
            (df_strat["trigger_date_dt"] >= pd.Timestamp(monday))
            & (df_strat["trigger_date_dt"] <= pd.Timestamp(friday))
        ].copy()

        if df_week.empty:
            latest_date = df_strat["trigger_date"].max()
            df_week = df_strat[df_strat["trigger_date"] == latest_date].copy()
            st.info(f"אין אסטרטגיות השבוע. מציג: {latest_date}")

        # Current index
        df_live = fetch_table("tase_putcall")
        current_index = 0.0
        if not df_live.empty:
            for col in ["underlingasset_call", "underlingasset_put"]:
                if col in df_live.columns:
                    vals = df_live[col].apply(clean_numeric)
                    vals = vals[vals > 0]
                    if not vals.empty:
                        current_index = vals.iloc[0]
                        break

        if current_index > 0:
            st.markdown(kpi_card("מדד TA-35 נוכחי", f"{current_index:,.2f}"),
                        unsafe_allow_html=True)
            st.markdown("<br>", unsafe_allow_html=True)

        # Group by expiry
        for exp_date in sorted(df_week["expiry_date"].unique()):
            try:
                exp_d = date.fromisoformat(exp_date)
                day_name = DAY_NAMES_HE.get(exp_d.weekday(), "")
            except Exception:
                day_name = ""

            df_exp = df_week[df_week["expiry_date"] == exp_date].sort_values("interval_pct")

            has_result = (df_exp["result_status"].notna().any()
                          if "result_status" in df_exp.columns else False)
            settled = " ✅" if has_result else ""

            st.markdown(
                f'<div class="section-title" style="font-size:18px; margin-top:10px;">'
                f'📅 יום {day_name} — {exp_date}{settled}</div>',
                unsafe_allow_html=True)

            rows = []
            for _, row in df_exp.iterrows():
                pct = clean_numeric(row.get("interval_pct", 0))
                result = row.get("result_status", None)
                pnl = clean_numeric(row.get("actual_pnl_ils", 0))

                rows.append({
                    "מרווח": f"{pct}%",
                    "Long Put": f'{clean_numeric(row.get("long_put_strike", 0)):.0f}',
                    "Short Put": f'{clean_numeric(row.get("short_put_strike", 0)):.0f}',
                    "Short Call": f'{clean_numeric(row.get("short_call_strike", 0)):.0f}',
                    "Long Call": f'{clean_numeric(row.get("long_call_strike", 0)):.0f}',
                    "פרמיה": f'{clean_numeric(row.get("total_net_premium", 0)):.2f}',
                    "רווח מקס": f'{clean_numeric(row.get("max_profit_ils", 0)):,.0f} ₪',
                    "סיכון מקס": f'{clean_numeric(row.get("max_risk_ils", 0)):,.0f} ₪',
                    "תוצאה": result or "⏳ פתוח",
                    "P&L": f"{pnl:+,.0f} ₪" if result else "—",
                })

            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Position indicator
            if current_index > 0 and not df_exp.empty:
                mid = df_exp.iloc[len(df_exp) // 2]
                sp = clean_numeric(mid.get("short_put_strike", 0))
                sc = clean_numeric(mid.get("short_call_strike", 0))
                if sp > 0 and sc > 0:
                    if sp <= current_index <= sc:
                        st.success(f"✅ מדד {current_index:,.2f} בטווח הרווח ({sp:.0f} – {sc:.0f})")
                    elif current_index < sp:
                        st.warning(f"⚠️ מדד {current_index:,.2f} מתחת ל-Short Put ({sp:.0f})")
                    else:
                        st.warning(f"⚠️ מדד {current_index:,.2f} מעל ל-Short Call ({sc:.0f})")

            st.markdown("---")


# ==================================================================
# PAGE 3: HISTORICAL PERFORMANCE
# ==================================================================
elif page == "📊 ביצועים היסטוריים":
    st.markdown('<div class="section-title">📊 ביצועים היסטוריים — Iron Condor</div>',
                unsafe_allow_html=True)

    df_hist = fetch_table("iron_condor_strategies",
                          "&result_status=not.is.null&order=trigger_date,interval_pct")

    if df_hist.empty:
        st.info("אין תוצאות היסטוריות עדיין. יופיעו אחרי הפקיעה הראשונה.")
    else:
        for col in ["actual_pnl_ils", "max_profit_ils", "max_risk_ils", "interval_pct"]:
            if col in df_hist.columns:
                df_hist[col] = df_hist[col].apply(clean_numeric)

        total_pnl = df_hist["actual_pnl_ils"].sum()
        total_trades = len(df_hist)
        wins = len(df_hist[df_hist["actual_pnl_ils"] > 0])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        # KPI cards
        c1, c2, c3 = st.columns(3)
        with c1:
            color = "#4ade80" if total_pnl >= 0 else "#f87171"
            st.markdown(f"""
            <div class="kpi-card">
                <div class="kpi-label">סה״כ P&L</div>
                <div class="kpi-value" style="color:{color}">₪{total_pnl:+,.0f}</div>
            </div>
            """, unsafe_allow_html=True)
        with c2:
            st.markdown(kpi_card("אחוז הצלחה", f"{win_rate:.0f}%"), unsafe_allow_html=True)
        with c3:
            st.markdown(kpi_card("עסקאות סגורות", f"{wins}/{total_trades}"), unsafe_allow_html=True)

        st.markdown("<br>", unsafe_allow_html=True)

        # Cumulative P&L chart
        st.markdown('<div class="section-title" style="font-size:18px;">📈 P&L מצטבר</div>',
                    unsafe_allow_html=True)

        df_by_date = df_hist.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        df_by_date.columns = ["date", "pnl"]
        df_by_date["cumulative"] = df_by_date["pnl"].cumsum()
        df_by_date = df_by_date.set_index("date")

        st.bar_chart(df_by_date["pnl"], color="#00d4aa")
        st.line_chart(df_by_date["cumulative"], color="#4dabf7")

        st.markdown("---")

        # By interval
        st.markdown('<div class="section-title" style="font-size:18px;">📊 ביצועים לפי מרווח</div>',
                    unsafe_allow_html=True)

        df_by_pct = df_hist.groupby("interval_pct").agg(
            total_pnl=("actual_pnl_ils", "sum"),
            avg_pnl=("actual_pnl_ils", "mean"),
            trades=("actual_pnl_ils", "count"),
            wins=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        df_by_pct["win_rate"] = (df_by_pct["wins"] / df_by_pct["trades"] * 100).round(1)
        df_by_pct.columns = ["מרווח %", "סה״כ P&L", "ממוצע P&L",
                             "עסקאות", "ניצחונות", "הצלחה %"]

        st.dataframe(df_by_pct, use_container_width=True, hide_index=True)

        st.markdown("---")

        # Full history table
        st.markdown('<div class="section-title" style="font-size:18px;">📋 כל העסקאות</div>',
                    unsafe_allow_html=True)

        detail_cols = [
            "trigger_date", "expiry_date", "interval_pct",
            "short_put_strike", "short_call_strike",
            "actual_index_close", "result_status", "actual_pnl_ils",
        ]
        available = [c for c in detail_cols if c in df_hist.columns]
        df_detail = df_hist[available].copy()

        rename = {
            "trigger_date": "תאריך",
            "expiry_date": "פקיעה",
            "interval_pct": "מרווח %",
            "short_put_strike": "Short Put",
            "short_call_strike": "Short Call",
            "actual_index_close": "מדד בפקיעה",
            "result_status": "תוצאה",
            "actual_pnl_ils": "P&L ₪",
        }
        df_detail = df_detail.rename(columns={k: v for k, v in rename.items() if k in df_detail.columns})
        st.dataframe(df_detail, use_container_width=True, height=400, hide_index=True)
