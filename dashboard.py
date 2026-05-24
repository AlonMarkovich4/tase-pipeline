"""
TASE Pipeline — Streamlit Dashboard
=====================================
Live monitor, strategy viewer, and historical P&L analytics.
Connects to Supabase for all data.
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
# Dark theme CSS
# ------------------------------------------------------------------
st.markdown("""
<style>
    .main { background-color: #0e1117; }
    .stMetric { background-color: #1a1f2e; padding: 15px; border-radius: 10px; border: 1px solid #2d3748; }
    .big-metric { font-size: 48px; font-weight: bold; color: #00d4aa; text-align: center; }
    .sub-metric { font-size: 14px; color: #8892a0; text-align: center; }
    .status-online { color: #00d4aa; font-weight: bold; }
    .status-offline { color: #ff6b6b; font-weight: bold; }
    .profit { color: #00d4aa; }
    .loss { color: #ff6b6b; }
    div[data-testid="stDataFrame"] { border: 1px solid #2d3748; border-radius: 8px; }
</style>
""", unsafe_allow_html=True)

# ------------------------------------------------------------------
# Supabase connection
# ------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")


def _headers():
    return {
        "apikey": SUPABASE_KEY,
        "Authorization": f"Bearer {SUPABASE_KEY}",
        "Content-Type": "application/json",
    }


@st.cache_data(ttl=60)
def fetch_table(table: str, params: str = "") -> pd.DataFrame:
    """Fetch data from Supabase table."""
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
    """Clean numeric values."""
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
st.sidebar.title("📊 TASE TA-35")
st.sidebar.markdown("---")

now = datetime.now(TZ_ISRAEL)
st.sidebar.markdown(f"**זמן נוכחי:** {now.strftime('%H:%M:%S')}")
st.sidebar.markdown(f"**תאריך:** {now.strftime('%Y-%m-%d')}")

# Trading hours check
is_trading = (
    now.weekday() in {0, 1, 2, 3, 4}
    and now.hour >= 9 and now.hour < 18
)
if is_trading:
    st.sidebar.markdown('<p class="status-online">● מערכת פעילה</p>',
                        unsafe_allow_html=True)
else:
    st.sidebar.markdown('<p class="status-offline">● מחוץ לשעות מסחר</p>',
                        unsafe_allow_html=True)

st.sidebar.markdown("---")

if st.sidebar.button("🔄 רענן נתונים"):
    st.cache_data.clear()
    st.rerun()

page = st.sidebar.radio(
    "ניווט",
    ["📈 מוניטור חי", "🎯 אסטרטגיות שבועיות", "📊 ביצועים היסטוריים"],
)

# ==================================================================
# SECTION 1: LIVE MONITOR
# ==================================================================
if page == "📈 מוניטור חי":
    st.title("📈 מוניטור חי — TA-35 Put/Call")

    df = fetch_table("tase_putcall")

    if df.empty:
        st.warning("אין נתונים זמינים כרגע")
    else:
        # Extract index value
        index_val = 0.0
        for col in ["underlingasset_call", "underlingasset_put"]:
            if col in df.columns:
                vals = df[col].apply(clean_numeric)
                vals = vals[vals > 0]
                if not vals.empty:
                    index_val = vals.iloc[0]
                    break

        # Extract metadata
        fetch_date = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else ""
        fetch_time = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        expiry = df["expiry_date"].iloc[0] if "expiry_date" in df.columns else ""
        num_rows = len(df)

        # KPI cards
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("מדד TA-35", f"{index_val:,.2f}")
        with col2:
            st.metric("עדכון אחרון", f"{fetch_date} {fetch_time}")
        with col3:
            st.metric("פקיעה", expiry)
        with col4:
            st.metric("רשומות", num_rows)

        st.markdown("---")

        # Filters
        st.subheader("נתוני Put/Call")

        # Select important columns
        display_cols = []
        wanted = [
            "expiry_date", "derivativename_call", "expirationprice_call",
            "lastrate_call", "delta_call", "openpositions_call",
            "derivativename_put", "expirationprice_put",
            "lastrate_put", "delta_put", "openpositions_put",
        ]
        for c in wanted:
            if c in df.columns:
                display_cols.append(c)

        if display_cols:
            display_df = df[display_cols].copy()

            # Rename columns for display
            rename_map = {
                "expiry_date": "פקיעה",
                "derivativename_call": "שם Call",
                "expirationprice_call": "Strike Call",
                "lastrate_call": "מחיר Call",
                "delta_call": "דלתא Call",
                "openpositions_call": "פוזיציות Call",
                "derivativename_put": "שם Put",
                "expirationprice_put": "Strike Put",
                "lastrate_put": "מחיר Put",
                "delta_put": "דלתא Put",
                "openpositions_put": "פוזיציות Put",
            }
            display_df = display_df.rename(
                columns={k: v for k, v in rename_map.items() if k in display_df.columns}
            )
            st.dataframe(display_df, use_container_width=True, height=500)
        else:
            st.dataframe(df, use_container_width=True, height=500)


# ==================================================================
# SECTION 2: ACTIVE WEEKLY STRATEGIES
# ==================================================================
elif page == "🎯 אסטרטגיות שבועיות":
    st.title("🎯 אסטרטגיות Iron Condor — השבוע")

    df_strat = fetch_table("iron_condor_strategies",
                           "&order=trigger_date.desc,expiry_date,interval_pct")

    if df_strat.empty:
        st.info("אין אסטרטגיות עדיין. האסטרטגיה הראשונה תחושב ביום שני הקרוב ב-12:00.")
    else:
        # Get current week strategies
        today = date.today()
        monday = today - timedelta(days=today.weekday())
        friday = monday + timedelta(days=4)

        df_strat["trigger_date_dt"] = pd.to_datetime(df_strat["trigger_date"], errors="coerce")
        df_week = df_strat[
            (df_strat["trigger_date_dt"] >= pd.Timestamp(monday))
            & (df_strat["trigger_date_dt"] <= pd.Timestamp(friday))
        ].copy()

        if df_week.empty:
            # Show latest available
            latest_date = df_strat["trigger_date"].max()
            df_week = df_strat[df_strat["trigger_date"] == latest_date].copy()
            st.info(f"אין אסטרטגיות השבוע. מציג אחרון זמין: {latest_date}")

        # Get current index for comparison
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
            st.metric("מדד TA-35 נוכחי", f"{current_index:,.2f}")

        st.markdown("---")

        # Group by expiry date
        expiry_dates = sorted(df_week["expiry_date"].unique())

        day_names_he = {
            0: "שני", 1: "שלישי", 2: "רביעי",
            3: "חמישי", 4: "שישי",
        }

        for exp_date in expiry_dates:
            try:
                exp_d = date.fromisoformat(exp_date)
                day_name = day_names_he.get(exp_d.weekday(), "")
            except Exception:
                day_name = ""

            df_exp = df_week[df_week["expiry_date"] == exp_date].sort_values("interval_pct")

            # Check if settled
            has_result = df_exp["result_status"].notna().any() if "result_status" in df_exp.columns else False

            header = f"📅 יום {day_name} — {exp_date}"
            if has_result:
                header += " ✅ נסגר"

            st.subheader(header)

            # Display variations
            cols_display = []
            for _, row in df_exp.iterrows():
                pct = clean_numeric(row.get("interval_pct", 0))
                sp = clean_numeric(row.get("short_put_strike", 0))
                sc = clean_numeric(row.get("short_call_strike", 0))
                lp = clean_numeric(row.get("long_put_strike", 0))
                lc = clean_numeric(row.get("long_call_strike", 0))
                premium = clean_numeric(row.get("total_net_premium", 0))
                profit = clean_numeric(row.get("max_profit_ils", 0))
                risk = clean_numeric(row.get("max_risk_ils", 0))
                rr = clean_numeric(row.get("risk_reward_ratio", 0))
                result = row.get("result_status", None)
                pnl = clean_numeric(row.get("actual_pnl_ils", 0))

                cols_display.append({
                    "מרווח %": f"{pct}%",
                    "Long Put": f"{lp:.0f}",
                    "Short Put": f"{sp:.0f}",
                    "Short Call": f"{sc:.0f}",
                    "Long Call": f"{lc:.0f}",
                    "פרמיה": f"{premium:.2f}",
                    "רווח מקס ₪": f"{profit:.0f}",
                    "סיכון מקס ₪": f"{risk:.0f}",
                    "R/R": f"{rr:.2f}",
                    "תוצאה": result or "פתוח",
                    "P&L ₪": f"{pnl:+,.0f}" if result else "—",
                })

            df_display = pd.DataFrame(cols_display)
            st.dataframe(df_display, use_container_width=True, hide_index=True)

            # Visual: where is the index relative to strikes?
            if current_index > 0 and not df_exp.empty:
                mid_row = df_exp.iloc[len(df_exp) // 2]
                sp_mid = clean_numeric(mid_row.get("short_put_strike", 0))
                sc_mid = clean_numeric(mid_row.get("short_call_strike", 0))

                if sp_mid > 0 and sc_mid > 0:
                    if sp_mid <= current_index <= sc_mid:
                        st.success(f"✅ מדד {current_index:,.2f} בטווח הרווח ({sp_mid:.0f}–{sc_mid:.0f})")
                    elif current_index < sp_mid:
                        diff = sp_mid - current_index
                        st.warning(f"⚠️ מדד {current_index:,.2f} מתחת ל-Short Put ({sp_mid:.0f}) ב-{diff:.0f} נקודות")
                    else:
                        diff = current_index - sc_mid
                        st.warning(f"⚠️ מדד {current_index:,.2f} מעל ל-Short Call ({sc_mid:.0f}) ב-{diff:.0f} נקודות")

            st.markdown("---")


# ==================================================================
# SECTION 3: HISTORICAL PERFORMANCE
# ==================================================================
elif page == "📊 ביצועים היסטוריים":
    st.title("📊 ביצועים היסטוריים — Iron Condor")

    df_hist = fetch_table("iron_condor_strategies",
                          "&result_status=not.is.null&order=trigger_date,interval_pct")

    if df_hist.empty:
        st.info("אין תוצאות היסטוריות עדיין. התוצאות הראשונות יופיעו אחרי פקיעה ראשונה.")
    else:
        # Clean numeric columns
        for col in ["actual_pnl_ils", "max_profit_ils", "max_risk_ils", "interval_pct"]:
            if col in df_hist.columns:
                df_hist[col] = df_hist[col].apply(clean_numeric)

        # KPI Cards
        total_pnl = df_hist["actual_pnl_ils"].sum()
        total_trades = len(df_hist)
        wins = len(df_hist[df_hist["actual_pnl_ils"] > 0])
        win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

        col1, col2, col3 = st.columns(3)

        with col1:
            pnl_color = "profit" if total_pnl >= 0 else "loss"
            st.metric("סה״כ P&L מצטבר",
                      f"₪{total_pnl:+,.0f}",
                      delta=f"{'רווח' if total_pnl >= 0 else 'הפסד'}")

        with col2:
            st.metric("אחוז הצלחה", f"{win_rate:.1f}%",
                      delta=f"{wins}/{total_trades} עסקאות")

        with col3:
            st.metric("סה״כ עסקאות סגורות", total_trades)

        st.markdown("---")

        # Chart 1: Cumulative P&L over time
        st.subheader("📈 P&L מצטבר לאורך זמן")

        df_by_date = df_hist.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        df_by_date.columns = ["תאריך", "P&L"]
        df_by_date["P&L מצטבר"] = df_by_date["P&L"].cumsum()
        df_by_date = df_by_date.set_index("תאריך")

        st.bar_chart(df_by_date["P&L"], color="#00d4aa")
        st.line_chart(df_by_date["P&L מצטבר"], color="#4dabf7")

        st.markdown("---")

        # Chart 2: P&L by interval percentage
        st.subheader("📊 ביצועים לפי אחוז מרווח")

        df_by_pct = df_hist.groupby("interval_pct").agg(
            total_pnl=("actual_pnl_ils", "sum"),
            avg_pnl=("actual_pnl_ils", "mean"),
            trades=("actual_pnl_ils", "count"),
            wins=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        df_by_pct["win_rate"] = (df_by_pct["wins"] / df_by_pct["trades"] * 100).round(1)
        df_by_pct.columns = ["מרווח %", "סה״כ P&L ₪", "ממוצע P&L ₪",
                             "עסקאות", "ניצחונות", "אחוז הצלחה %"]

        st.dataframe(df_by_pct, use_container_width=True, hide_index=True)

        # Bar chart of total P&L by interval
        chart_data = df_by_pct.set_index("מרווח %")["סה״כ P&L ₪"]
        st.bar_chart(chart_data, color="#4dabf7")

        st.markdown("---")

        # Detailed history table
        st.subheader("📋 היסטוריית עסקאות מלאה")

        detail_cols = [
            "trigger_date", "expiry_date", "interval_pct",
            "short_put_strike", "short_call_strike",
            "actual_index_close", "result_status", "actual_pnl_ils",
        ]
        available = [c for c in detail_cols if c in df_hist.columns]
        df_detail = df_hist[available].copy()

        rename = {
            "trigger_date": "תאריך טריגר",
            "expiry_date": "תאריך פקיעה",
            "interval_pct": "מרווח %",
            "short_put_strike": "Short Put",
            "short_call_strike": "Short Call",
            "actual_index_close": "מדד בפקיעה",
            "result_status": "תוצאה",
            "actual_pnl_ils": "P&L ₪",
        }
        df_detail = df_detail.rename(columns={k: v for k, v in rename.items() if k in df_detail.columns})
        st.dataframe(df_detail, use_container_width=True, height=400, hide_index=True)


# ------------------------------------------------------------------
# Footer
# ------------------------------------------------------------------
st.sidebar.markdown("---")
st.sidebar.markdown("🤖 **TASE Pipeline v2.0**")
st.sidebar.markdown("Render + Supabase + Telegram")
