"""
TASE TA-35 Options Dashboard
"""

import os
import streamlit as st
import pandas as pd
import httpx
from datetime import datetime, date, timedelta
from zoneinfo import ZoneInfo

st.set_page_config(page_title="TA-35 Options", page_icon="📊", layout="wide")

# RTL only — no design overrides
st.markdown("""<style>
.main .block-container{direction:rtl;text-align:right}
[data-testid="stSidebar"]{direction:rtl;text-align:right}
[data-testid="stMarkdownContainer"]{direction:rtl;text-align:right}
[data-testid="stRadio"] > div{direction:rtl}
[data-testid="stRadio"] label{direction:rtl;text-align:right}
[data-testid="stAlert"]{direction:rtl;text-align:right}
[data-testid="stMetricValue"]{direction:ltr}
#MainMenu,footer,header{visibility:hidden}
</style>""", unsafe_allow_html=True)

# ------------------------------------------------------------------
SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")
DAYS = {0:"שני",1:"שלישי",2:"רביעי",3:"חמישי",4:"שישי",5:"שבת",6:"ראשון"}

def _hdr():
    return {"apikey":SUPABASE_KEY,"Authorization":f"Bearer {SUPABASE_KEY}",
            "Content-Type":"application/json"}

@st.cache_data(ttl=60)
def fetch(table, params=""):
    try:
        r = httpx.get(f"{SUPABASE_URL}/rest/v1/{table}?select=*{params}",
                      headers=_hdr(), timeout=15)
        if r.status_code in (200,206):
            d = r.json()
            if d: return pd.DataFrame(d)
    except Exception: pass
    return pd.DataFrame()

def n(val):
    """Safe numeric conversion."""
    if val is None or val == "" or (isinstance(val, str) and val.strip() == ""):
        return None
    if isinstance(val, (int, float)): return float(val)
    try: return float(str(val).replace(",",""))
    except: return None

def fmt(val, decimals=0):
    """Format number or return —."""
    v = n(val)
    if v is None: return "—"
    if decimals == 0: return f"{v:,.0f}"
    return f"{v:,.{decimals}f}"

def get_idx(df):
    for c in ["underlingasset_call","underlingasset_put"]:
        if c in df.columns:
            for v in df[c]:
                x = n(v)
                if x and x > 0: return x
    return 0.0

# ------------------------------------------------------------------
# Sidebar
# ------------------------------------------------------------------
now = datetime.now(TZ)
is_live = now.weekday() in {0,1,2,3,4} and 9 <= now.hour < 18

st.sidebar.markdown(f"### 📊 TA-35 Options")
st.sidebar.caption(f"יום {DAYS.get(now.weekday(),'')} · {now.strftime('%d/%m/%Y')} · {now.strftime('%H:%M')}")

if is_live:
    st.sidebar.success("🟢 שוק פתוח")
else:
    st.sidebar.info("🔴 שוק סגור")

st.sidebar.divider()
page = st.sidebar.radio("ניווט", ["מוניטור חי","אסטרטגיות","ביצועים"])
st.sidebar.divider()
if st.sidebar.button("🔄 רענן", use_container_width=True):
    st.cache_data.clear()
    st.rerun()


# ==================================================================
if page == "מוניטור חי":
# ==================================================================
    st.title("מוניטור חי")

    df = fetch("tase_putcall")
    if df.empty:
        st.warning("אין נתונים זמינים.")
        st.stop()

    idx = get_idx(df)
    ft = df["fetch_time"].iloc[0] if "fetch_time" in df.columns else "—"
    fd = df["fetch_date"].iloc[0] if "fetch_date" in df.columns else ""

    c1, c2, c3 = st.columns(3)
    c1.metric("מדד TA-35", fmt(idx, 2))
    c2.metric("עדכון אחרון", f"{fd}  {ft}")
    c3.metric("רשומות", len(df))

    st.divider()

    # Filter by expiry
    if "expiry_date" in df.columns:
        exps = sorted(df["expiry_date"].unique())
        labels = []
        for e in exps:
            try:
                d = date.fromisoformat(e)
                labels.append(f"יום {DAYS.get(d.weekday(),'')} — {e}")
            except: labels.append(e)
        choice = st.selectbox("יום פקיעה", labels)
        df = df[df["expiry_date"] == exps[labels.index(choice)]]

    # Build clean table
    rows = []
    for _, r in df.iterrows():
        strike_c = n(r.get("expirationprice_call"))
        strike_p = n(r.get("expirationprice_put"))
        if strike_c is None and strike_p is None:
            continue  # skip empty header rows
        rows.append({
            "Strike": fmt(strike_c or strike_p),
            "Call": r.get("derivativename_call","") or "",
            "מחיר Call": fmt(r.get("lastrate_call")),
            "O.I Call": fmt(r.get("openpositions_call")),
            "Put": r.get("derivativename_put","") or "",
            "מחיר Put": fmt(r.get("lastrate_put")),
            "O.I Put": fmt(r.get("openpositions_put")),
        })

    if rows:
        st.dataframe(pd.DataFrame(rows), use_container_width=True,
                     height=550, hide_index=True)
    else:
        st.info("אין נתוני מסחר ליום הזה.")


# ==================================================================
elif page == "אסטרטגיות":
# ==================================================================
    st.title("אסטרטגיות Iron Condor")

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
        st.caption(f"מציג אסטרטגיות מ-{latest}")

    idx = get_idx(fetch("tase_putcall"))
    if idx > 0:
        st.metric("מדד TA-35 נוכחי", fmt(idx, 2))
    st.divider()

    for exp in sorted(df_w["expiry_date"].unique()):
        try:
            ed = date.fromisoformat(exp)
            dn = DAYS.get(ed.weekday(), "")
        except: dn = ""

        df_e = df_w[df_w["expiry_date"] == exp].sort_values("interval_pct")
        settled = (df_e["result_status"].notna().any()
                   if "result_status" in df_e.columns else False)

        tag = "✅ נסגר" if settled else "⏳ פתוח"
        st.subheader(f"יום {dn} — {exp}  ({tag})")

        tbl = []
        for _, r in df_e.iterrows():
            res = r.get("result_status")
            pnl = n(r.get("actual_pnl_ils", 0))
            tbl.append({
                "מרווח": f'{n(r.get("interval_pct",0)) or 0}%',
                "Long Put": fmt(r.get("long_put_strike")),
                "Short Put": fmt(r.get("short_put_strike")),
                "Short Call": fmt(r.get("short_call_strike")),
                "Long Call": fmt(r.get("long_call_strike")),
                "פרמיה": fmt(r.get("total_net_premium"), 2),
                "רווח מקס ₪": fmt(r.get("max_profit_ils")),
                "סיכון מקס ₪": fmt(r.get("max_risk_ils")),
                "סטטוס": res if res else "פתוח",
                "P&L ₪": f"{pnl:+,.0f}" if res and pnl is not None else "—",
            })
        st.dataframe(pd.DataFrame(tbl), use_container_width=True, hide_index=True)

        if idx > 0 and not df_e.empty:
            mid = df_e.iloc[len(df_e)//2]
            sp = n(mid.get("short_put_strike",0)) or 0
            sc = n(mid.get("short_call_strike",0)) or 0
            if sp > 0 and sc > 0:
                if sp <= idx <= sc:
                    st.success(f"מדד {idx:,.2f} בטווח הרווח ({sp:.0f} – {sc:.0f})")
                elif idx < sp:
                    st.warning(f"מדד {idx:,.2f} מתחת ל-Short Put ({sp:.0f})")
                else:
                    st.warning(f"מדד {idx:,.2f} מעל ל-Short Call ({sc:.0f})")
        st.divider()


# ==================================================================
elif page == "ביצועים":
# ==================================================================
    st.title("ביצועים היסטוריים")

    df_h = fetch("iron_condor_strategies",
                 "&result_status=not.is.null&order=trigger_date,interval_pct")
    if df_h.empty:
        st.info("אין תוצאות עדיין.")
        st.stop()

    for c in ["actual_pnl_ils","max_profit_ils","max_risk_ils","interval_pct"]:
        if c in df_h.columns:
            df_h[c] = df_h[c].apply(lambda v: n(v) or 0)

    total = df_h["actual_pnl_ils"].sum()
    trades = len(df_h)
    wins = len(df_h[df_h["actual_pnl_ils"] > 0])
    wr = (wins/trades*100) if trades > 0 else 0

    c1, c2, c3 = st.columns(3)
    c1.metric("סה״כ P&L", f"₪{total:+,.0f}")
    c2.metric("הצלחה", f"{wr:.0f}%", delta=f"{wins} מתוך {trades}")
    c3.metric("עסקאות", trades)

    st.divider()

    # Charts in tabs
    st.subheader("גרפים")
    dbd = df_h.groupby("trigger_date")["actual_pnl_ils"].sum().reset_index()
    dbd.columns = ["date","pnl"]
    dbd["cum"] = dbd["pnl"].cumsum()
    dbd = dbd.set_index("date")

    t1, t2 = st.tabs(["יומי","מצטבר"])
    with t1: st.bar_chart(dbd["pnl"], color="#2563eb")
    with t2: st.line_chart(dbd["cum"], color="#16a34a")

    st.divider()

    # By interval
    st.subheader("לפי מרווח")
    dbp = df_h.groupby("interval_pct").agg(
        pnl=("actual_pnl_ils","sum"), avg=("actual_pnl_ils","mean"),
        cnt=("actual_pnl_ils","count"),
        w=("actual_pnl_ils", lambda x: (x>0).sum())
    ).reset_index()
    dbp["wr"] = (dbp["w"]/dbp["cnt"]*100).round(1)
    dbp.columns = ["מרווח %","סה״כ ₪","ממוצע ₪","עסקאות","ניצחונות","הצלחה %"]
    st.dataframe(dbp, use_container_width=True, hide_index=True)

    st.divider()

    # Full history
    st.subheader("כל העסקאות")
    det = ["trigger_date","expiry_date","interval_pct",
           "short_put_strike","short_call_strike",
           "actual_index_close","result_status","actual_pnl_ils"]
    av = [c for c in det if c in df_h.columns]
    dfd = df_h[av].rename(columns={
        "trigger_date":"תאריך","expiry_date":"פקיעה","interval_pct":"מרווח",
        "short_put_strike":"SP","short_call_strike":"SC",
        "actual_index_close":"מדד פקיעה","result_status":"תוצאה",
        "actual_pnl_ils":"P&L ₪"})
    st.dataframe(dfd, use_container_width=True, height=400, hide_index=True)
