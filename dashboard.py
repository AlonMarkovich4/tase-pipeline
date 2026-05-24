"""
TASE TA-35 Options Dashboard
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
    page_title="TA-35 Options Monitor",
    page_icon="📊",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ------------------------------------------------------------------
# Minimal CSS — only RTL + small tweaks
# ------------------------------------------------------------------
st.markdown("""
<style>
    /* RTL for Hebrew */
    .main .block-container { direction: rtl; text-align: right; }
    [data-testid="stSidebar"] { direction: rtl; text-align: right; }
    [data-testid="stMarkdownContainer"] { direction: rtl; text-align: right; }
    [data-testid="stRadio"] > div { direction: rtl; }
    [data-testid="stRadio"] label { direction: rtl; text-align: right; }
    [data-testid="stAlert"] { direction: rtl; text-align: right; }
    [data-testid="stMetricLabel"] { direction: rtl; text-align: right; }
    [data-testid="stSelectbox"] label { direction: rtl; text-align: right; }

    /* Keep numbers LTR */
    [data-testid="stMetricValue"] { direction: ltr; }

    /* Hide branding */
    #MainMenu, footer, header { visibility: hidden; }
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
st.sidebar.title("📊 TA-35 Options")
st.sidebar.caption("Real-Time Options Monitor")
st.sidebar.divider()

now = datetime.now(TZ_ISRAEL)
day_he = DAY_HE.get(now.weekday(), "")
is_trading = now.weekday() in {0, 1, 2, 3, 4} and 9 <= now.hour < 18

st.sidebar.markdown(f"**יום {day_he}** · {now.strftime('%d/%m/%Y')} · {now.strftime('%H:%M')}")

if is_trading:
    st.sidebar.success("🟢 LIVE — שעות מסחר")
else:
    st.sidebar.error("🔴 CLOSED — מחוץ למסחר")

st.sidebar.divider()

if st.sidebar.button("🔄 רענן נתונים", use_container_width=True):
    st.cache_data.clear()
    st.rerun()

st.sidebar.divider()

page = st.sidebar.radio(
    "ניווט",
    ["מוניטור חי", "אסטרטגיות", "ביצועים היסטוריים"],
)

st.sidebar.divider()
st.sidebar.caption("v2.0 · Render · Supabase · Telegram")


# ==================================================================
# PAGE 1 — LIVE MONITOR
# ==================================================================
if page == "מוניטור חי":
    st.header("מוניטור חי — Put/Call")

    df = fetch_table("tase_putcall")

    if df.empty:
        st.warning("אין נתונים זמינים כרגע.")
    else:
        index_val = get_index(df)
        fetch_date = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else "—"
        fetch_time = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else ""
        n_exp = df["expiry_date"].nunique() if "expiry_date" in df.columns else 0

        # KPIs — native st.metric
        c1, c2, c3, c4 = st.columns(4)
        c1.metric("מדד TA-35", f"{index_val:,.2f}")
        c2.metric("עדכון אחרון", fetch_time, delta=fetch_date)
        c3.metric("ימי פקיעה", n_exp)
        c4.metric("רשומות", len(df))

        st.divider()

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
            sel = st.selectbox("בחר יום פקיעה:", labels, index=0)
            df = df[df["expiry_date"] == expiries[labels.index(sel)]]

        # Table
        wanted = [
            "derivativename_call", "expirationprice_call", "lastrate_call", "openpositions_call",
            "derivativename_put", "expirationprice_put", "lastrate_put", "openpositions_put",
        ]
        cols = [c for c in wanted if c in df.columns]
        if cols:
            dfd = df[cols].rename(columns={
                "derivativename_call": "Call",
                "expirationprice_call": "Strike Call",
                "lastrate_call": "מחיר Call",
                "openpositions_call": "O.I Call",
                "derivativename_put": "Put",
                "expirationprice_put": "Strike Put",
                "lastrate_put": "מחיר Put",
                "openpositions_put": "O.I Put",
            })
            st.dataframe(dfd, use_container_width=True, height=520, hide_index=True)
        else:
            st.dataframe(df, use_container_width=True, height=520, hide_index=True)


# ==================================================================
# PAGE 2 — STRATEGIES
# ==================================================================
elif page == "אסטרטגיות":
    st.header("אסטרטגיות Iron Condor")

    df_strat = fetch_table("iron_condor_strategies",
                           "&order=trigger_date.desc,expiry_date,interval_pct")

    if df_strat.empty:
        st.info("אין אסטרטגיות עדיין. הראשונה תיווצר ביום מסחר הקרוב אחרי 12:00.")
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
            st.metric("מדד TA-35 נוכחי", f"{idx:,.2f}")

        st.divider()

        for exp_date in sorted(df_w["expiry_date"].unique()):
            try:
                exp_d = date.fromisoformat(exp_date)
                dn = DAY_HE.get(exp_d.weekday(), "")
            except Exception:
                dn = ""

            df_e = df_w[df_w["expiry_date"] == exp_date].sort_values("interval_pct")
            has_res = df_e["result_status"].notna().any() if "result_status" in df_e.columns else False

            status = "  ✅ SETTLED" if has_res else "  ⏳ OPEN"
            st.subheader(f"יום {dn} — {exp_date}{status}")

            rows = []
            for _, r in df_e.iterrows():
                result = r.get("result_status", None)
                pnl = cnum(r.get("actual_pnl_ils", 0))
                rows.append({
                    "מרווח": f'{cnum(r.get("interval_pct", 0))}%',
                    "Long Put": f'{cnum(r.get("long_put_strike", 0)):.0f}',
                    "Short Put": f'{cnum(r.get("short_put_strike", 0)):.0f}',
                    "Short Call": f'{cnum(r.get("short_call_strike", 0)):.0f}',
                    "Long Call": f'{cnum(r.get("long_call_strike", 0)):.0f}',
                    "פרמיה": f'{cnum(r.get("total_net_premium", 0)):.2f}',
                    "רווח מקס ₪": f'{cnum(r.get("max_profit_ils", 0)):,.0f}',
                    "סיכון מקס ₪": f'{cnum(r.get("max_risk_ils", 0)):,.0f}',
                    "סטטוס": result if result else "פתוח",
                    "P&L ₪": f"{pnl:+,.0f}" if result else "—",
                })
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

            # Position check
            if idx > 0 and not df_e.empty:
                mid = df_e.iloc[len(df_e) // 2]
                sp = cnum(mid.get("short_put_strike", 0))
                sc = cnum(mid.get("short_call_strike", 0))
                if sp > 0 and sc > 0:
                    if sp <= idx <= sc:
                        st.success(f"מדד {idx:,.2f} בטווח הרווח ({sp:.0f} – {sc:.0f})")
                    elif idx < sp:
                        st.warning(f"מדד {idx:,.2f} מתחת ל-Short Put ({sp:.0f}) ב-{sp - idx:.0f} נקודות")
                    else:
                        st.warning(f"מדד {idx:,.2f} מעל ל-Short Call ({sc:.0f}) ב-{idx - sc:.0f} נקודות")

            st.divider()


# ==================================================================
# PAGE 3 — PERFORMANCE
# ==================================================================
elif page == "ביצועים היסטוריים":
    st.header("ביצועים היסטוריים — Iron Condor")

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

        # KPIs
        c1, c2, c3 = st.columns(3)
        c1.metric("סה״כ P&L", f"₪{total:+,.0f}",
                  delta="רווח" if total >= 0 else "הפסד")
        c2.metric("אחוז הצלחה", f"{wr:.0f}%",
                  delta=f"{wins} מתוך {trades}")
        c3.metric("עסקאות סגורות", trades)

        st.divider()

        # Charts
        st.subheader("P&L יומי ומצטבר")

        dbd = df_h.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
        dbd.columns = ["date", "pnl"]
        dbd["cumulative"] = dbd["pnl"].cumsum()
        dbd = dbd.set_index("date")

        tab1, tab2 = st.tabs(["P&L יומי", "P&L מצטבר"])
        with tab1:
            st.bar_chart(dbd["pnl"], color="#3b82f6")
        with tab2:
            st.line_chart(dbd["cumulative"], color="#10b981")

        st.divider()

        # By interval
        st.subheader("ביצועים לפי מרווח")

        dbp = df_h.groupby("interval_pct").agg(
            total_pnl=("actual_pnl_ils", "sum"),
            avg_pnl=("actual_pnl_ils", "mean"),
            trades=("actual_pnl_ils", "count"),
            wins=("actual_pnl_ils", lambda x: (x > 0).sum()),
        ).reset_index()
        dbp["win_rate"] = (dbp["wins"] / dbp["trades"] * 100).round(1)
        dbp.columns = ["מרווח %", "סה״כ P&L", "ממוצע P&L", "עסקאות", "ניצחונות", "הצלחה %"]
        st.dataframe(dbp, use_container_width=True, hide_index=True)

        st.divider()

        # Full table
        st.subheader("היסטוריה מלאה")

        det = ["trigger_date", "expiry_date", "interval_pct",
               "short_put_strike", "short_call_strike",
               "actual_index_close", "result_status", "actual_pnl_ils"]
        avail = [c for c in det if c in df_h.columns]
        dfd = df_h[avail].rename(columns={
            "trigger_date": "תאריך", "expiry_date": "פקיעה",
            "interval_pct": "מרווח %", "short_put_strike": "Short Put",
            "short_call_strike": "Short Call", "actual_index_close": "מדד פקיעה",
            "result_status": "תוצאה", "actual_pnl_ils": "P&L ₪",
        })
        st.dataframe(dfd, use_container_width=True, height=400, hide_index=True)
