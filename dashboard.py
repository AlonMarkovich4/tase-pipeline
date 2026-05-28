"""
TASE TA-35 — Executive Strategy Dashboard
===========================================
Automated Iron Condor analytics, trade review,
forward-looking strategy monitor, and interactive
demo trading workspace.
"""

import os
import json
import uuid
import streamlit as st
import pandas as pd
import numpy as np
import httpx
import plotly.graph_objects as go
from datetime import datetime, date, timezone
from zoneinfo import ZoneInfo

# ==================================================================
# CONFIG
# ==================================================================
st.set_page_config(
    page_title="TA-35 Strategy Desk",
    page_icon="◆",
    layout="wide",
    initial_sidebar_state="expanded",
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")

try:
    from config import TASE_MULTIPLIER as MULTIPLIER, WING_WIDTH
except ImportError:
    MULTIPLIER = 50
    WING_WIDTH = 20

# ── Demo trading constants ──
DEMO_INITIAL_BALANCE = 100_000.0
STRATEGY_LOOKBACK_DAYS = 90  # how far back to load strategies (perf)

# Palette
C_BG       = "#0B0D10"
C_CARD     = "#151921"
C_BORDER   = "#1E2433"
C_TEXT     = "#E8EAED"
C_DIM      = "#9AA0A6"
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
# GLOBAL CSS — all styles centralized
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

/* ── Lock sidebar open ── */
[data-testid="collapsedControl"] {{ display: none !important; }}
section[data-testid="stSidebar"] {{ min-width: 280px !important; }}

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

/* ── Option Chain (Sandbox) ── */
.chain-wrap {{
    overflow-x: auto;
    margin: 12px 0;
    border-radius: 10px;
    border: 1px solid {C_BORDER};
    background: {C_CARD};
}}
.chain-wrap table {{
    width: 100%;
    min-width: 820px;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 13px;
    direction: ltr;
}}
.chain-wrap th {{
    background: rgba(255,255,255,0.03);
    color: {C_DIM};
    font-weight: 600;
    font-size: 10px;
    text-transform: uppercase;
    letter-spacing: 0.4px;
    padding: 9px 10px;
    border-bottom: 1px solid {C_BORDER};
    text-align: center;
    position: sticky;
    top: 0;
    z-index: 1;
}}
.chain-wrap th.call-hdr {{ color: {C_GREEN}; }}
.chain-wrap th.put-hdr  {{ color: {C_RED}; }}
.chain-wrap th.strike-hdr {{
    color: {C_YELLOW};
    font-size: 11px;
    min-width: 70px;
}}
.chain-wrap td {{
    padding: 7px 10px;
    text-align: center;
    border-bottom: 1px solid rgba(30,36,51,0.5);
    color: {C_TEXT};
    font-weight: 500;
    font-size: 13px;
}}
.chain-wrap tr:last-child td {{ border-bottom: none; }}
.chain-wrap tr:hover td {{ background: rgba(255,255,255,0.025); }}
.chain-wrap td.strike-col {{
    font-weight: 800;
    font-size: 14px;
    color: {C_YELLOW};
    background: rgba(255,214,0,0.04);
    border-left: 1px solid {C_BORDER};
    border-right: 1px solid {C_BORDER};
}}
.chain-wrap td.itm {{ background: rgba(255,255,255,0.025); }}
.chain-wrap td.atm-row {{
    background: rgba(0,176,255,0.06) !important;
    border-top: 1px solid rgba(0,176,255,0.2);
    border-bottom: 1px solid rgba(0,176,255,0.2);
}}
.chain-wrap .oi    {{ color: {C_DIM}; font-size: 11px; }}
.chain-wrap .delta {{ color: {C_DIM}; font-size: 11px; }}
.chain-wrap .no-data {{ color: rgba(255,255,255,0.15); }}

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
# DATA LAYER — Strategy Desk
# ==================================================================

_HEADERS_CACHE: dict | None = None


def _supabase_headers() -> dict:
    """Cached headers — credentials don't change at runtime."""
    global _HEADERS_CACHE
    if _HEADERS_CACHE is None:
        _HEADERS_CACHE = {
            "apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json",
        }
    return _HEADERS_CACHE


@st.cache_data(ttl=120)
def load_strategies() -> pd.DataFrame:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()
    # Lookback window for performance — only load recent strategies
    cutoff = (datetime.now(TZ).date()
              - pd.Timedelta(days=STRATEGY_LOOKBACK_DAYS)).isoformat()
    all_rows = []
    batch = 1000
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/iron_condor_strategies"
            f"?select=*&order=trigger_date.desc,expiry_date,interval_pct"
            f"&trigger_date=gte.{cutoff}"
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

    # ------------------------------------------------------------------
    # POST-LOAD VALIDATION: enforce Iron Condor pricing invariants
    # Premium can never exceed wing width — cap and flag corrupted rows
    # ------------------------------------------------------------------
    if "total_net_premium" in df.columns:
        wing_p = df.get("actual_wing_put", pd.Series(WING_WIDTH, index=df.index))
        wing_c = df.get("actual_wing_call", pd.Series(WING_WIDTH, index=df.index))
        wing_p = wing_p.replace(0, WING_WIDTH)
        wing_c = wing_c.replace(0, WING_WIDTH)
        wing_max = pd.concat([wing_p, wing_c], axis=1).max(axis=1)

        # Flag rows where premium > wing (impossible)
        corrupted = df["total_net_premium"] > wing_max
        if corrupted.any():
            df.loc[corrupted, "premium_flag"] = "price_capped"
            df.loc[corrupted, "total_net_premium"] = wing_max[corrupted]
            # Recalculate profit/risk from corrected premium
            df.loc[corrupted, "max_profit_ils"] = (
                df.loc[corrupted, "total_net_premium"] * MULTIPLIER
            )
            df.loc[corrupted, "max_risk_ils"] = (
                wing_max[corrupted] * MULTIPLIER
                - df.loc[corrupted, "max_profit_ils"]
            )

    return df


@st.cache_data(ttl=60)
def get_live_index() -> float:
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
# DATA LAYER — Demo Trading (Sandbox)
# ==================================================================

@st.cache_data(ttl=90)
def load_option_chain(expiry_date: str) -> pd.DataFrame:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()
    url_latest = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=fetch_date,fetch_time"
        f"&expiry_date=eq.{expiry_date}"
        f"&order=id.desc&limit=1"
    )
    try:
        r = httpx.get(url_latest, headers=_supabase_headers(), timeout=10)
        if r.status_code not in (200, 206) or not r.json():
            return pd.DataFrame()
        latest = r.json()[0]
        fd, ft = latest["fetch_date"], latest["fetch_time"]
    except Exception:
        return pd.DataFrame()
    all_rows = []
    batch = 500
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/tase_putcall"
            f"?select=expirationprice_call,lastrate_call,lastrate_put,"
            f"delta_call,delta_put,openpositions_call,openpositions_put,"
            f"dealsno_call,dealsno_put"
            f"&expiry_date=eq.{expiry_date}"
            f"&fetch_date=eq.{fd}&fetch_time=eq.{ft}"
            f"&order=expirationprice_call"
            f"&limit={batch}&offset={offset}"
        )
        try:
            r = httpx.get(url, headers=_supabase_headers(), timeout=15)
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
    df.rename(columns={"expirationprice_call": "strike"}, inplace=True)
    for col in ["lastrate_call", "lastrate_put"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            df[f"{col}_pts"] = df[col] / MULTIPLIER
    for col in ["delta_call", "delta_put", "openpositions_call",
                 "openpositions_put", "dealsno_call", "dealsno_put", "strike"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
    df = df[df["strike"] > 0]  # Filter out rows with missing/zero strikes
    return df.sort_values("strike").reset_index(drop=True)


@st.cache_data(ttl=120)
def get_available_expiries() -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=expiry_date&order=expiry_date&limit=1000"
    )
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            return sorted(set(row["expiry_date"] for row in r.json()
                              if row.get("expiry_date")))
    except Exception:
        pass
    return []


def get_demo_balance() -> float:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return DEMO_INITIAL_BALANCE
    url = f"{SUPABASE_URL}/rest/v1/demo_balance?select=balance&order=id.desc&limit=1"
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206) and r.json():
            return float(r.json()[0]["balance"])
    except Exception:
        pass
    return DEMO_INITIAL_BALANCE


def _update_demo_balance(new_balance: float, change: float, reason: str):
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    h = _supabase_headers()
    h["Prefer"] = "return=minimal"
    httpx.post(f"{SUPABASE_URL}/rest/v1/demo_balance", headers=h,
               content=json.dumps({"balance": round(new_balance, 2),
                                   "change_amount": round(change, 2),
                                   "change_reason": reason}), timeout=10)


def save_demo_trade(trade: dict) -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    h = _supabase_headers()
    h["Prefer"] = "return=minimal"
    r = httpx.post(f"{SUPABASE_URL}/rest/v1/demo_trades", headers=h,
                   content=json.dumps(trade), timeout=10)
    return r.status_code in (200, 201)


def load_demo_trades(status: str = "open") -> list:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = (f"{SUPABASE_URL}/rest/v1/demo_trades"
           f"?status=eq.{status}&order=created_at.desc&limit=100")
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            return r.json()
    except Exception:
        pass
    return []


def close_demo_trade(trade_id: str, settlement_index: float,
                     pnl_ils: float, reason: str = "manual_close") -> bool:
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    url = f"{SUPABASE_URL}/rest/v1/demo_trades?trade_id=eq.{trade_id}"
    h = _supabase_headers()
    h["Prefer"] = "return=minimal"
    r = httpx.patch(url, headers=h, content=json.dumps({
        "status": "closed",
        "settlement_index": settlement_index,
        "pnl_ils": round(pnl_ils, 2),
        "close_reason": reason,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }), timeout=10)
    return r.status_code in (200, 204)


# ==================================================================
# HELPERS
# ==================================================================

def fmt_ils(v: float) -> str:
    # Explicit sign for positive values; native "-" for negatives; no sign for 0
    if v > 0:
        return f"+{v:,.0f} ₪"
    return f"{v:,.0f} ₪"


def fmt_num(v: float, decimals: int = 2) -> str:
    return f"{v:,.{decimals}f}"


@st.cache_data(ttl=60)
def _fetch_option_prices_for_expiry(expiry_date: str) -> dict:
    """
    Batch fetch ALL latest option prices for one expiry in a single HTTP call.
    Returns: {(strike, side): price_in_pts}
    Replaces N individual fetches with 1 query — major perf win for the
    Open Positions page where every interval needs 4 leg prices.

    Sanity: drops prices > WING_WIDTH * 3 (corrupted theoretical TASE values).
    """
    if not expiry_date or not SUPABASE_URL:
        return {}
    # First get latest fetch_date+fetch_time for this expiry
    url_latest = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=fetch_date,fetch_time"
        f"&expiry_date=eq.{expiry_date}"
        f"&order=id.desc&limit=1"
    )
    try:
        r = httpx.get(url_latest, headers=_supabase_headers(), timeout=10)
        if r.status_code not in (200, 206) or not r.json():
            return {}
        latest = r.json()[0]
        fd, ft = latest["fetch_date"], latest["fetch_time"]
    except Exception:
        return {}

    url = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=expirationprice_call,lastrate_call,"
        f"expirationprice_put,lastrate_put"
        f"&expiry_date=eq.{expiry_date}"
        f"&fetch_date=eq.{fd}&fetch_time=eq.{ft}"
    )
    out: dict = {}
    price_cap = WING_WIDTH * 3  # sanity threshold for stale/theoretical prices
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=15)
        if r.status_code not in (200, 206):
            return {}
        for row in r.json():
            for side in ("call", "put"):
                strike = row.get(f"expirationprice_{side}") or 0
                raw = row.get(f"lastrate_{side}") or 0
                if not strike:
                    continue
                try:
                    price = float(str(raw).replace(",", "")) / MULTIPLIER
                    if 0 < price <= price_cap:
                        out[(float(strike), side)] = price
                except (ValueError, TypeError):
                    continue
    except Exception:
        pass
    return out


def compute_unrealized_pnl(row: pd.Series, live_index: float) -> tuple:
    entry_premium = row.get("total_net_premium", 0)
    expiry = str(row.get("expiry_date", ""))
    sc_strike = row.get("short_call_strike", 0)
    sp_strike = row.get("short_put_strike", 0)
    lc_strike = row.get("long_call_strike", 0)
    lp_strike = row.get("long_put_strike", 0)
    # Single batch fetch instead of 4 individual queries
    prices = _fetch_option_prices_for_expiry(expiry)
    sc_now = prices.get((float(sc_strike), "call"), 0) if sc_strike else 0
    sp_now = prices.get((float(sp_strike), "put"), 0) if sp_strike else 0
    lc_now = prices.get((float(lc_strike), "call"), 0) if lc_strike else 0
    lp_now = prices.get((float(lp_strike), "put"), 0) if lp_strike else 0
    if sc_now > 0 or sp_now > 0:
        current_premium = (sc_now + sp_now) - (lc_now + lp_now)
        # Apply same invariant: current premium can't exceed wing
        wing_put_v = row.get("actual_wing_put", 0) or (sp_strike - lp_strike) or WING_WIDTH
        wing_call_v = row.get("actual_wing_call", 0) or (lc_strike - sc_strike) or WING_WIDTH
        wing_max = max(wing_put_v, wing_call_v)
        if current_premium > wing_max:
            current_premium = wing_max
        pnl_pts = entry_premium - current_premium
        return round(pnl_pts * MULTIPLIER, 2), "live"
    wing_put = row.get("actual_wing_put", 0) or (sp_strike - lp_strike) or WING_WIDTH
    wing_call = row.get("actual_wing_call", 0) or (lc_strike - sc_strike) or WING_WIDTH
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


def _validate_premium(net_prem: float, wing_put: float, wing_call: float) -> float:
    """
    Iron Condor invariant: net premium can NEVER exceed wing width.
    If it does, the stored prices are corrupt (stale/theoretical TASE data).
    Cap to wing width to prevent impossible P&L displays.
    """
    wing_max = max(wing_put, wing_call)
    if wing_max > 0 and net_prem > wing_max:
        return wing_max
    return net_prem


def build_payoff_curve(row: pd.Series) -> tuple:
    lp = row.get("long_put_strike", 0)
    sp = row.get("short_put_strike", 0)
    sc = row.get("short_call_strike", 0)
    lc = row.get("long_call_strike", 0)
    raw_prem = row.get("total_net_premium", 0)
    wing_put = row.get("actual_wing_put", 0) or (sp - lp) or WING_WIDTH
    wing_call = row.get("actual_wing_call", 0) or (lc - sc) or WING_WIDTH
    # Enforce iron condor invariant: premium <= wing width
    net_prem = _validate_premium(raw_prem, wing_put, wing_call)
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


def settlement_zone_label(idx_close, sp, sc, lp, lc) -> str:
    if sp <= idx_close <= sc:
        return '<span class="strike-zone in">SAFE ZONE</span>'
    elif lp <= idx_close < sp:
        return '<span class="strike-zone out-put">PUT BREACH</span>'
    elif sc < idx_close <= lc:
        return '<span class="strike-zone out-call">CALL BREACH</span>'
    elif idx_close < lp:
        return '<span class="strike-zone out-put">MAX LOSS PUT</span>'
    return '<span class="strike-zone out-call">MAX LOSS CALL</span>'


# ── Sandbox helpers ──

def sandbox_compute_payoff(legs: list, price_range: np.ndarray) -> np.ndarray:
    total = np.zeros_like(price_range, dtype=float)
    for leg in legs:
        strike = leg["strike"]
        prem = leg["premium_pts"]
        qty = leg["qty"]
        sign = 1 if leg["action"] == "BUY" else -1
        if leg["type"] == "Call":
            intrinsic = np.maximum(price_range - strike, 0)
        else:
            intrinsic = np.maximum(strike - price_range, 0)
        total += sign * (intrinsic - prem) * MULTIPLIER * qty
    return total


def sandbox_compute_metrics(legs: list, base_index: float) -> dict:
    if not legs:
        return {"max_profit": 0, "max_loss": 0, "breakevens": [],
                "net_premium": 0, "price_warning": ""}
    x = np.linspace(base_index - 500, base_index + 500, 2000)
    y = sandbox_compute_payoff(legs, x)
    net_prem = sum(
        (-1 if l["action"] == "BUY" else 1) * l["premium_pts"] * l["qty"]
        for l in legs
    )
    breakevens = []
    for i in range(1, len(y)):
        if (y[i - 1] < 0 and y[i] >= 0) or (y[i - 1] >= 0 and y[i] < 0):
            x_cross = x[i - 1] + (0 - y[i - 1]) * (x[i] - x[i - 1]) / (y[i] - y[i - 1])
            breakevens.append(round(x_cross, 1))

    # ── Sanity: detect impossible iron condor metrics ──
    max_profit_val = float(np.max(y))
    max_loss_val = float(np.min(y))
    price_warning = ""

    # For iron condors (4 legs), max_profit should never exceed
    # wing_width * multiplier.  Flag but don't block.
    if len(legs) == 4 and max_profit_val > WING_WIDTH * MULTIPLIER * 1.5:
        price_warning = (
            f"⚠️ Max profit ₪{max_profit_val:,.0f} exceeds wing "
            f"limit ₪{WING_WIDTH * MULTIPLIER:,} — prices may be stale"
        )

    return {
        "max_profit": max_profit_val,
        "max_loss": max_loss_val,
        "breakevens": breakevens,
        "net_premium": net_prem,
        "price_warning": price_warning,
    }


def sandbox_trade_pnl(trade: dict, current_index: float) -> float:
    legs = trade.get("legs", [])
    if isinstance(legs, str):
        legs = json.loads(legs)
    total = 0.0
    for leg in legs:
        strike = float(leg["strike"])
        prem = float(leg["premium_pts"])
        qty = int(leg.get("qty", 1))
        sign = 1 if leg["action"] == "BUY" else -1
        intrinsic = (max(current_index - strike, 0) if leg["type"] == "Call"
                     else max(strike - current_index, 0))
        total += sign * (intrinsic - prem) * MULTIPLIER * qty
    return round(total, 2)


# ==================================================================
# RENDER COMPONENTS — Strategy Desk
# ==================================================================

def render_payoff_chart(row, ref_price: float = 0, ref_label: str = ""):
    x_prices, y_pnl = build_payoff_curve(row)
    be_upper = row.get("breakeven_upper", 0)
    be_lower = row.get("breakeven_lower", 0)
    fig = go.Figure()
    profit_y = np.where(y_pnl >= 0, y_pnl, 0)
    fig.add_trace(go.Scatter(x=x_prices, y=profit_y, fill="tozeroy",
                             fillcolor="rgba(38,222,129,0.50)", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    loss_y = np.where(y_pnl < 0, y_pnl, 0)
    fig.add_trace(go.Scatter(x=x_prices, y=loss_y, fill="tozeroy",
                             fillcolor="rgba(255,77,77,0.50)", line=dict(width=0),
                             showlegend=False, hoverinfo="skip"))
    fig.add_trace(go.Scatter(x=x_prices, y=y_pnl, mode="lines",
                             line=dict(color="rgba(255,255,255,0.35)", width=1),
                             showlegend=False,
                             hovertemplate="Index: %{x:,.0f}<br>P&L: %{y:,.0f} ₪<extra></extra>"))
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
    be_x = [v for v in [be_lower, be_upper] if v > 0]
    if be_x:
        fig.add_trace(go.Scatter(x=be_x, y=[0] * len(be_x), mode="markers",
                                 marker=dict(color=C_ORANGE, size=10, symbol="circle",
                                             line=dict(color=C_BG, width=2)),
                                 showlegend=False,
                                 hovertemplate="Breakeven: %{x:,.0f}<extra></extra>"))
    if ref_price > 0:
        fig.add_vline(x=ref_price, line=dict(color="#00BCD4", width=2, dash="dot"))
        fig.add_annotation(x=ref_price, y=max(y_pnl) * 0.9, text=ref_label,
                           showarrow=False, font=dict(size=13, color="#00BCD4", family="Inter"),
                           bgcolor="rgba(11,13,16,0.85)", bordercolor="#00BCD4",
                           borderwidth=1, borderpad=6)
    fig.update_layout(
        template="plotly_dark", paper_bgcolor=C_BG, plot_bgcolor=C_BG,
        height=360, margin=dict(l=50, r=30, t=20, b=50),
        xaxis=dict(gridcolor="rgba(255,255,255,0.04)", zeroline=False,
                   tickformat=",", tickfont=dict(size=10, color=C_DIM), dtick=40),
        yaxis=dict(title="P&L (₪)", gridcolor="rgba(255,255,255,0.06)", zeroline=False,
                   tickformat=",", tickfont=dict(size=10, color=C_DIM),
                   title_font=dict(size=11, color=C_DIM)),
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
    html = '<div class="table-scroll"><table><thead><tr><th>Leg</th><th>Action</th><th>Strike</th><th>Premium (₪)</th></tr></thead><tbody>'
    for name, action, strike, price in legs:
        css = "sell" if action == "SELL" else "buy"
        price_ils = price * MULTIPLIER
        html += f'<tr><td>{name}</td><td class="{css}">{action}</td><td><strong>{fmt_num(strike, 0)}</strong></td><td>{fmt_num(price_ils, 0)}</td></tr>'
    html += "</tbody></table></div>"
    st.markdown(html, unsafe_allow_html=True)


def render_expiry_metrics(row):
    net_prem = row.get("total_net_premium", 0)
    max_profit = row.get("max_profit_ils", 0)
    max_risk = row.get("max_risk_ils", 0)
    pflag = row.get("premium_flag", "")
    be_upper = row.get("breakeven_upper", 0)
    be_lower = row.get("breakeven_lower", 0)
    dte = int(row.get("days_to_expiry", 0))
    prem_color = "green" if net_prem > 0 else "red"

    # Recalculate RR from corrected max_profit/risk (not stored value)
    # When premium was capped, risk_reward_ratio in DB still reflects the
    # uncapped numbers; recompute for an accurate display.
    if max_profit > 0:
        rr = abs(max_risk) / max_profit
    else:
        rr = 0

    # Show warning if this row had corrupted/capped pricing
    if pflag in ("price_capped", "inverted_prices"):
        st.warning(
            "⚠️ TASE prices for this interval were stale/theoretical. "
            "Premium was capped to wing width. P&L shown is corrected."
        )
    elif pflag == "negative_premium":
        st.info(
            "ℹ️ Negative premium — this interval costs money to enter "
            "and is not tradeable."
        )

    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">Net Premium (pts)</div><div class="value {prem_color}">{fmt_num(net_prem)}</div></div>'
        f'<div class="metric-card glow-green"><div class="label">Max Profit</div><div class="value green">{fmt_ils(max_profit)}</div></div>'
        f'<div class="metric-card glow-red"><div class="label">Max Risk</div><div class="value red">{fmt_ils(-abs(max_risk))}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    # Display RR — if max_risk is 0 (capped to wing), show "1:0 (zero-risk)"
    if abs(max_risk) < 0.01 and max_profit > 0:
        rr_display = "1:0 (capped)"
    else:
        rr_display = f"1:{fmt_num(rr, 1)}"

    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">Risk / Reward</div><div class="value white">{rr_display}</div></div>'
        f'<div class="metric-card"><div class="label">Lower Breakeven</div><div class="value white">{fmt_num(be_lower, 0)}</div></div>'
        f'<div class="metric-card"><div class="label">Upper Breakeven</div><div class="value white">{fmt_num(be_upper, 0)}</div></div>'
        f'<div class="metric-card"><div class="label">DTE</div><div class="value blue">{dte}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )


def render_breadcrumb(steps: list):
    parts = []
    for i, (label, active) in enumerate(steps):
        cls = "crumb active" if active else "crumb"
        parts.append(f'<span class="{cls}"><span class="num">{i+1}</span>{label}</span>')
    html = '<div class="step-breadcrumb">' + '<span class="sep">‹</span>'.join(parts) + '</div>'
    st.markdown(html, unsafe_allow_html=True)


# ==================================================================
# STRATEGY TEMPLATES (Sandbox)
# ==================================================================

SANDBOX_TEMPLATES = {
    "empty": {
        "name": "אסטרטגיה ריקה",
        "icon": "⬜",
        "desc": "התחל מאפס — הוסף רגליים ידנית מהשרשרת",
        "legs": [],
    },
    "iron_condor": {
        "name": "Iron Condor",
        "icon": "🦅",
        "desc": "Sell OTM Call + Put, Buy wings",
        "legs": [
            {"type": "Put",  "action": "BUY",  "strike_offset": -3},
            {"type": "Put",  "action": "SELL", "strike_offset": -1},
            {"type": "Call", "action": "SELL", "strike_offset": +1},
            {"type": "Call", "action": "BUY",  "strike_offset": +3},
        ],
    },
    "vertical_put": {
        "name": "מרווח אנכי (Put)",
        "icon": "📉",
        "desc": "Bull Put Spread — Sell Put + Buy lower Put",
        "legs": [
            {"type": "Put", "action": "BUY",  "strike_offset": -2},
            {"type": "Put", "action": "SELL", "strike_offset": -1},
        ],
    },
    "vertical_call": {
        "name": "מרווח אנכי (Call)",
        "icon": "📈",
        "desc": "Bear Call Spread — Sell Call + Buy higher Call",
        "legs": [
            {"type": "Call", "action": "SELL", "strike_offset": +1},
            {"type": "Call", "action": "BUY",  "strike_offset": +2},
        ],
    },
    "long_straddle": {
        "name": "סטרדל ארוך",
        "icon": "⚡",
        "desc": "Buy ATM Call + Put — profit from big moves either way",
        "legs": [
            {"type": "Put",  "action": "BUY", "strike_offset": 0},
            {"type": "Call", "action": "BUY", "strike_offset": 0},
        ],
    },
    "short_straddle": {
        "name": "סטרדל קצר",
        "icon": "🎯",
        "desc": "Sell ATM Call + Put — profit from low volatility",
        "legs": [
            {"type": "Put",  "action": "SELL", "strike_offset": 0},
            {"type": "Call", "action": "SELL", "strike_offset": 0},
        ],
    },
    "long_strangle": {
        "name": "סטרנגל ארוך",
        "icon": "🔀",
        "desc": "Buy OTM Call + Put — cheaper volatility bet",
        "legs": [
            {"type": "Put",  "action": "BUY", "strike_offset": -2},
            {"type": "Call", "action": "BUY", "strike_offset": +2},
        ],
    },
    "short_strangle": {
        "name": "סטרנגל קצר",
        "icon": "🔒",
        "desc": "Sell OTM Call + Put — wider safe zone than straddle",
        "legs": [
            {"type": "Put",  "action": "SELL", "strike_offset": -2},
            {"type": "Call", "action": "SELL", "strike_offset": +2},
        ],
    },
    "butterfly": {
        "name": "פרפר (Butterfly)",
        "icon": "🦋",
        "desc": "Buy 1 lower + Buy 1 upper, Sell 2 middle — limited risk",
        "legs": [
            {"type": "Call", "action": "BUY",  "strike_offset": -1},
            {"type": "Call", "action": "SELL", "strike_offset": 0},
            {"type": "Call", "action": "SELL", "strike_offset": 0},
            {"type": "Call", "action": "BUY",  "strike_offset": +1},
        ],
    },
    "protective_put": {
        "name": "פוט מגן",
        "icon": "🛡️",
        "desc": "Buy Put to protect existing long position",
        "legs": [
            {"type": "Put", "action": "BUY", "strike_offset": -1},
        ],
    },
}


def _apply_template(key: str, base_index: float, step: int = 20) -> list:
    tpl = SANDBOX_TEMPLATES.get(key, {})
    center = round(base_index / step) * step
    return [
        {"type": ld["type"], "action": ld["action"],
         "strike": float(center + ld["strike_offset"] * step),
         "premium_pts": 0.0, "qty": 1}
        for ld in tpl.get("legs", [])
    ]


# ==================================================================
# SESSION STATE
# ==================================================================
if "sandbox_legs" not in st.session_state:
    st.session_state.sandbox_legs = []
if "sandbox_template" not in st.session_state:
    st.session_state.sandbox_template = None
if "settled_ids" not in st.session_state:
    st.session_state.settled_ids = set()


# ==================================================================
# SETTLEMENT DIALOG
# ==================================================================
@st.dialog("⚠️ סטלמנט אוטומטי — אופציות שפקעו")
def _settlement_dialog(results: list, new_balance: float):
    for r in results:
        icon = "📈" if r["pnl"] >= 0 else "📉"
        color = C_GREEN if r["pnl"] >= 0 else C_RED
        st.markdown(
            f'{icon} **{r["name"]}** (#{r["id"]}) — פקיעה {r["expiry"]}<br>'
            f'מדד סטלמנט: **{r["settle"]:,.0f}** | '
            f'P&L: <span style="color:{color};font-weight:800;">{fmt_ils(r["pnl"])}</span>',
            unsafe_allow_html=True,
        )
    st.divider()
    st.metric("יתרה מעודכנת", f"{new_balance:,.0f} ₪")
    if st.button("✅ אישור", use_container_width=True, type="primary"):
        st.rerun()


# ==================================================================
# HEADER
# ==================================================================
now_il = datetime.now(TZ)
live_index = get_live_index()

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
has_strategies = not df.empty

if has_strategies:
    df["_trigger_dt"] = pd.to_datetime(df["trigger_date"], errors="coerce")
    df["_iso_week"] = df["_trigger_dt"].dt.isocalendar().week.astype(int)
    df["_iso_year"] = df["_trigger_dt"].dt.isocalendar().year.astype(int)
    df["_week_label"] = df.apply(
        lambda r: f"{int(r['_iso_year'])}-W{int(r['_iso_week']):02d}  ({r['trigger_date']})",
        axis=1,
    )
    df["_is_settled"] = df["result_status"].notna() & (df["result_status"] != "")
    today_str = now_il.strftime("%Y-%m-%d")
    df["_is_expired"] = (df["expiry_date"] < today_str) & (~df["_is_settled"])
    df.loc[df["_is_expired"], "_is_settled"] = True

    n_global_active = int((~df["_is_settled"]).sum())
    n_global_history = int(df["_is_settled"].sum())
else:
    n_global_active = 0
    n_global_history = 0


# ==================================================================
# SIDEBAR NAVIGATION
# ==================================================================
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center;padding:18px 0 14px;">
        <div style="font-size:22px;font-weight:800;color:{C_TEXT};letter-spacing:-0.5px;">◆ Strategy Desk</div>
        <div style="font-size:11px;color:{C_DIM};margin-top:4px;">TA-35 Iron Condor</div>
    </div>
    """, unsafe_allow_html=True)

    nav_page = st.radio(
        "ניווט",
        ["🕹️ Demo Trading", "🔵 Open Positions", "📜 History"],
        captions=[
            "זירת מסחר דמו",
            f"{n_global_active} פוזיציות פתוחות",
            f"{n_global_history} אסטרטגיות שפקעו",
        ],
        label_visibility="collapsed",
    )

    st.markdown(f"""
    <div style="border-top:1px solid {C_BORDER};margin:16px 0;padding-top:14px;">
        <div style="color:{C_DIM};font-size:11px;text-align:center;">
            Auto-refresh 2 min<br>Multiplier: {MULTIPLIER}₪/pt
        </div>
    </div>
    """, unsafe_allow_html=True)


# ╔════════════════════════════════════════════════════════════════════╗
# ║  PAGE: 🕹️ DEMO TRADING WORKSPACE                                ║
# ╚════════════════════════════════════════════════════════════════════╝
if nav_page == "🕹️ Demo Trading":

    # ── Background: Auto-Settlement ──────────────────────────────
    _open_check = load_demo_trades("open")
    _today = now_il.strftime("%Y-%m-%d")
    _expired = [t for t in _open_check
                if t.get("expiry_date", "9999") < _today
                and t.get("trade_id") not in st.session_state.settled_ids]

    if _expired:
        _bal = get_demo_balance()
        _results = []
        for et in _expired:
            et_id = et.get("trade_id", "?")
            et_expiry = et.get("expiry_date", "")
            et_entry = float(et.get("entry_index", 0))
            settle_idx = 0.0
            try:
                s_url = (f"{SUPABASE_URL}/rest/v1/iron_condor_strategies"
                         f"?select=actual_index_close"
                         f"&expiry_date=eq.{et_expiry}&actual_index_close=gt.0&limit=1")
                sr = httpx.get(s_url, headers=_supabase_headers(), timeout=10)
                if sr.status_code in (200, 206) and sr.json():
                    settle_idx = float(sr.json()[0].get("actual_index_close", 0))
            except Exception:
                pass
            if settle_idx <= 0:
                settle_idx = live_index if live_index > 0 else et_entry
            final_pnl = sandbox_trade_pnl(et, settle_idx)
            close_demo_trade(et_id, settle_idx, final_pnl, "expiry_settlement")
            _bal += final_pnl
            _update_demo_balance(_bal, final_pnl, f"expiry_settle_{et_id}")
            st.session_state.settled_ids.add(et_id)
            _results.append({"id": et_id, "name": et.get("strategy_name", ""),
                             "expiry": et_expiry, "settle": settle_idx, "pnl": final_pnl})
        st.cache_data.clear()
        _settlement_dialog(_results, _bal)

    # ── Shared state ──
    # Use live index; fall back to last known base from Supabase;
    # 2000 is a stale placeholder that corrupts all chart/template math.
    if live_index > 0:
        base = live_index
    elif has_strategies and "base_index_value" in df.columns:
        _last_base = df["base_index_value"].iloc[0]
        base = _last_base if _last_base > 0 else 4500
    else:
        base = 4500  # reasonable TA-35 range, not the old 2000
    legs = st.session_state.sandbox_legs

    # ================================================================
    # § TOP MODULE — Payoff Chart (hero element)
    # ================================================================
    if legs and any(l["premium_pts"] > 0 for l in legs):
        metrics = sandbox_compute_metrics(legs, base)
        net_prem = metrics["net_premium"]
        max_profit = metrics["max_profit"]
        max_loss = metrics["max_loss"]
        be_list = metrics["breakevens"]
        prem_color = "green" if net_prem > 0 else "red"
        be_str = " / ".join(fmt_num(b, 0) for b in be_list) if be_list else "—"

        # Show price warning if iron condor metrics are impossible
        if metrics.get("price_warning"):
            st.warning(metrics["price_warning"])

        st.markdown(
            f'<div class="metric-grid">'
            f'<div class="metric-card"><div class="label">Net Premium (pts)</div>'
            f'<div class="value {prem_color}">{fmt_num(net_prem)}</div></div>'
            f'<div class="metric-card glow-green"><div class="label">Max Profit</div>'
            f'<div class="value green">{fmt_ils(max_profit)}</div></div>'
            f'<div class="metric-card glow-red"><div class="label">Max Loss</div>'
            f'<div class="value red">{fmt_ils(max_loss)}</div></div>'
            f'<div class="metric-card"><div class="label">Breakeven(s)</div>'
            f'<div class="value white" style="font-size:18px;">{be_str}</div></div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Build chart
        all_strikes = [l["strike"] for l in legs]
        min_s, max_s = min(all_strikes), max(all_strikes)
        margin = max(100, (max_s - min_s) * 0.8)
        x_range = np.linspace(min_s - margin, max_s + margin, 600)
        y_pnl = sandbox_compute_payoff(legs, x_range)

        fig = go.Figure()
        fig.add_trace(go.Scatter(x=x_range, y=np.where(y_pnl >= 0, y_pnl, 0),
                                 fill="tozeroy", fillcolor="rgba(38,222,129,0.45)",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x_range, y=np.where(y_pnl < 0, y_pnl, 0),
                                 fill="tozeroy", fillcolor="rgba(255,77,77,0.45)",
                                 line=dict(width=0), showlegend=False, hoverinfo="skip"))
        fig.add_trace(go.Scatter(x=x_range, y=y_pnl, mode="lines",
                                 line=dict(color="rgba(255,255,255,0.4)", width=1.5),
                                 showlegend=False,
                                 hovertemplate="Index: %{x:,.0f}<br>P&L: %{y:,.0f} ₪<extra></extra>"))
        fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))
        if be_list:
            fig.add_trace(go.Scatter(
                x=be_list, y=[0] * len(be_list), mode="markers+text",
                marker=dict(color=C_ORANGE, size=11, symbol="circle",
                            line=dict(color=C_BG, width=2)),
                text=[f"BE: {b:,.0f}" for b in be_list],
                textposition="top center", textfont=dict(size=11, color=C_ORANGE),
                showlegend=False, hovertemplate="Breakeven: %{x:,.0f}<extra></extra>"))
        if live_index > 0:
            fig.add_vline(x=live_index, line=dict(color="#00BCD4", width=2, dash="dot"))
            fig.add_annotation(x=live_index, y=max(y_pnl) * 0.85,
                               text=f"Live: {live_index:,.2f}", showarrow=False,
                               font=dict(size=12, color="#00BCD4"),
                               bgcolor="rgba(11,13,16,0.9)",
                               bordercolor="#00BCD4", borderwidth=1, borderpad=5)
        for leg in legs:
            color = C_GREEN if leg["action"] == "BUY" else C_RED
            label = f"{'B' if leg['action']=='BUY' else 'S'} {leg['type'][0]} {leg['strike']:,.0f}"
            fig.add_vline(x=leg["strike"], line=dict(color=color, width=1, dash="dash"))
            fig.add_annotation(x=leg["strike"], y=min(y_pnl) * 0.9, text=label,
                               showarrow=False, font=dict(size=10, color=color),
                               bgcolor="rgba(11,13,16,0.8)", borderpad=3)
        fig.update_layout(
            template="plotly_dark", paper_bgcolor=C_BG, plot_bgcolor=C_BG,
            height=420, margin=dict(l=55, r=30, t=25, b=50),
            xaxis=dict(title="TA-35 Index at Expiry", gridcolor="rgba(255,255,255,0.04)",
                       zeroline=False, tickformat=",", tickfont=dict(size=10, color=C_DIM),
                       title_font=dict(size=11, color=C_DIM)),
            yaxis=dict(title="P&L (₪)", gridcolor="rgba(255,255,255,0.06)", zeroline=False,
                       tickformat=",", tickfont=dict(size=10, color=C_DIM),
                       title_font=dict(size=11, color=C_DIM)),
            showlegend=False, hovermode="x unified",
        )
        st.plotly_chart(fig, use_container_width=True)

        # ── Legs summary + Execute button ──
        legs_html = ('<div class="table-scroll"><table><thead><tr>'
                     '<th>Leg</th><th>Action</th><th>Strike</th>'
                     '<th>Premium (₪)</th><th>Qty</th><th>Cost/Credit (₪)</th>'
                     '</tr></thead><tbody>')
        for leg in legs:
            css = "sell" if leg["action"] == "SELL" else "buy"
            prem_ils = leg["premium_pts"] * MULTIPLIER
            sign = -1 if leg["action"] == "BUY" else 1
            cost = sign * prem_ils * leg["qty"]
            cost_css = "buy" if cost > 0 else "sell"
            cost_lbl = f"+{cost:,.0f}" if cost > 0 else f"{cost:,.0f}"
            legs_html += (f'<tr><td>{leg["type"]}</td><td class="{css}">{leg["action"]}</td>'
                          f'<td><strong>{fmt_num(leg["strike"], 0)}</strong></td>'
                          f'<td>{fmt_num(prem_ils, 0)}</td><td>{leg["qty"]}</td>'
                          f'<td class="{cost_css}"><strong>{cost_lbl}</strong></td></tr>')
        legs_html += '</tbody></table></div>'
        st.markdown(legs_html, unsafe_allow_html=True)

        # Execute row
        exec_cols = st.columns([1.5, 2, 1.5])
        with exec_cols[0]:
            _real_expiries = get_available_expiries()
            if _real_expiries:
                trade_expiry = st.selectbox("📅 פקיעה", _real_expiries, index=0,
                                            key="sb_trade_expiry")
            else:
                trade_expiry = str(date.today())
        with exec_cols[1]:
            tpl_name = SANDBOX_TEMPLATES.get(
                st.session_state.sandbox_template or "empty", {}).get("name", "Custom")
            st.markdown(
                f'<div style="padding:10px 0;text-align:center;">'
                f'<strong style="color:{C_TEXT};">{tpl_name}</strong>'
                f'<span style="color:{C_DIM};font-size:12px;"> | {len(legs)} רגליים</span>'
                f'</div>', unsafe_allow_html=True)
        with exec_cols[2]:
            if st.button("🚀 שגר אסטרטגיה לתיק דמו", key="sb_execute",
                          use_container_width=True, type="primary"):
                tid = str(uuid.uuid4())[:12]
                ok = save_demo_trade({
                    "trade_id": tid, "strategy_name": tpl_name,
                    "expiry_date": str(trade_expiry), "status": "open",
                    "legs": legs,
                    "entry_index": live_index if live_index > 0 else base,
                    "net_premium_pts": round(net_prem, 4),
                    "max_profit_ils": round(max_profit, 2),
                    "max_risk_ils": round(abs(max_loss), 2),
                })
                if ok:
                    st.success(f"✅ עסקה {tid} בוצעה! — {tpl_name} | פקיעה {trade_expiry}")
                    st.session_state.sandbox_legs = []
                    st.session_state.sandbox_template = None
                    st.cache_data.clear()
                    st.rerun()
                else:
                    st.error("❌ שגיאה בשמירת העסקה.")

    elif legs:
        st.warning("הזן פרמיות (Premium) לפחות לרגל אחת כדי לראות את הגרף.")
    else:
        st.markdown(
            f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
            f'padding:60px 20px;text-align:center;margin:20px 0;">'
            f'<div style="font-size:48px;margin-bottom:12px;">📊</div>'
            f'<div style="color:{C_TEXT};font-size:18px;font-weight:700;">הגרף יופיע כאן</div>'
            f'<div style="color:{C_DIM};font-size:14px;margin-top:6px;">'
            f'בחר תבנית אסטרטגיה למטה או הוסף רגליים מהשרשרת</div></div>',
            unsafe_allow_html=True)

    # ================================================================
    # § STRATEGY BUILDER — Template + Leg Editor
    # ================================================================
    with st.expander("📐 בחר אסטרטגיה והגדר רגליים", expanded=not bool(legs)):
        ctrl_cols = st.columns([2.5, 1.5, 1.5])
        with ctrl_cols[0]:
            tpl_labels = {k: f"{v['icon']} {v['name']}" for k, v in SANDBOX_TEMPLATES.items()}
            sel_tpl = st.selectbox(
                "תבנית אסטרטגיה",
                list(SANDBOX_TEMPLATES.keys()),
                format_func=lambda k: tpl_labels[k],
                index=0,
                key="sb_template_select",
                label_visibility="collapsed",
            )
        with ctrl_cols[1]:
            if st.button("📐 טען תבנית", use_container_width=True, key="sb_load_tpl"):
                st.session_state.sandbox_template = sel_tpl
                st.session_state.sandbox_legs = _apply_template(sel_tpl, base)
                st.rerun()
        with ctrl_cols[2]:
            if st.button("🧹 נקה", use_container_width=True, key="sb_clear"):
                st.session_state.sandbox_legs = []
                st.session_state.sandbox_template = None
                st.rerun()

        # ── Editable Leg Rows ──
        if legs:
            updated_legs = []
            for idx, leg in enumerate(legs):
                cols = st.columns([1.5, 1.5, 2, 2, 1.2, 0.7])
                with cols[0]:
                    leg_type = st.selectbox("סוג", ["Call", "Put"],
                                            index=0 if leg["type"] == "Call" else 1,
                                            key=f"sb_lt_{idx}",
                                            label_visibility="collapsed" if idx > 0 else "visible")
                with cols[1]:
                    leg_action = st.selectbox("פעולה", ["BUY", "SELL"],
                                              index=0 if leg["action"] == "BUY" else 1,
                                              key=f"sb_la_{idx}",
                                              label_visibility="collapsed" if idx > 0 else "visible")
                with cols[2]:
                    leg_strike = st.number_input("Strike", min_value=0.0, max_value=5000.0,
                                                 value=float(leg["strike"]), step=10.0,
                                                 key=f"sb_ls_{idx}",
                                                 label_visibility="collapsed" if idx > 0 else "visible")
                with cols[3]:
                    leg_prem = st.number_input("Premium (pts)", min_value=0.0, max_value=500.0,
                                               value=float(leg["premium_pts"]), step=0.5,
                                               key=f"sb_lp_{idx}",
                                               label_visibility="collapsed" if idx > 0 else "visible")
                with cols[4]:
                    leg_qty = st.number_input("Qty", min_value=1, max_value=50,
                                              value=int(leg.get("qty", 1)), step=1,
                                              key=f"sb_lq_{idx}",
                                              label_visibility="collapsed" if idx > 0 else "visible")
                with cols[5]:
                    if idx > 0:
                        st.write("")
                    if st.button("🗑️", key=f"sb_del_{idx}", help="הסר"):
                        continue
                updated_legs.append({"type": leg_type, "action": leg_action,
                                     "strike": leg_strike, "premium_pts": leg_prem, "qty": leg_qty})
            if len(updated_legs) != len(legs):
                st.session_state.sandbox_legs = updated_legs
                st.rerun()
            else:
                st.session_state.sandbox_legs = updated_legs
                legs = updated_legs

        add_col, _, _ = st.columns([1, 1, 3])
        with add_col:
            if st.button("➕ הוסף רגל", use_container_width=True, key="sb_add_leg"):
                st.session_state.sandbox_legs.append(
                    {"type": "Call", "action": "BUY",
                     "strike": round(base / 10) * 10, "premium_pts": 0.0, "qty": 1})
                st.rerun()

    # ================================================================
    # § MIDDLE MODULE — Interactive Option Chain
    # ================================================================
    st.markdown('<div class="section-hdr">⛓️ שרשרת אופציות — Option Chain</div>',
                unsafe_allow_html=True)

    expiry_dates = get_available_expiries()

    if not expiry_dates:
        st.info("אין נתוני אופציות זמינים כרגע. המערכת תטען נתונים בזמן המסחר.")
    else:
        chain_header = st.columns([3, 1])
        with chain_header[1]:
            sel_expiry = st.selectbox("📅 פקיעה", expiry_dates, index=0,
                                      key="sb_chain_expiry")
        chain_df = load_option_chain(sel_expiry)

        if chain_df.empty:
            st.warning("אין נתוני שרשרת לתאריך הפקיעה שנבחר.")
        else:
            if live_index > 0:
                atm_strike = chain_df.iloc[
                    (chain_df["strike"] - live_index).abs().argsort().iloc[0]]["strike"]
                display_df = chain_df[
                    (chain_df["strike"] >= live_index - 200) &
                    (chain_df["strike"] <= live_index + 200)
                ].copy()
            else:
                atm_strike = 0
                display_df = chain_df.copy()

            if display_df.empty:
                display_df = chain_df.copy()

            with chain_header[0]:
                n_strikes = len(display_df)
                st.markdown(
                    f'<span style="color:{C_DIM};font-size:12px;">'
                    f'{n_strikes} strikes  |  Expiry: {sel_expiry}'
                    f'{"  |  ATM ≈ " + fmt_num(atm_strike, 0) if atm_strike > 0 else ""}'
                    f'</span>', unsafe_allow_html=True)

            # Build chain HTML
            chain_html = (
                '<div class="chain-wrap"><table><thead><tr>'
                '<th class="call-hdr">OI</th>'
                '<th class="call-hdr">Vol</th>'
                '<th class="call-hdr">Delta</th>'
                '<th class="call-hdr">Premium ₪</th>'
                '<th class="strike-hdr">⚡ STRIKE</th>'
                '<th class="put-hdr">Premium ₪</th>'
                '<th class="put-hdr">Delta</th>'
                '<th class="put-hdr">Vol</th>'
                '<th class="put-hdr">OI</th>'
                '</tr></thead><tbody>'
            )
            for _, row in display_df.iterrows():
                strike = int(row["strike"])
                c_rate = row.get("lastrate_call", 0) or 0
                p_rate = row.get("lastrate_put", 0) or 0
                c_delta = int(row.get("delta_call", 0) or 0)
                p_delta = int(row.get("delta_put", 0) or 0)
                c_oi = int(row.get("openpositions_call", 0) or 0)
                p_oi = int(row.get("openpositions_put", 0) or 0)
                c_vol = int(row.get("dealsno_call", 0) or 0)
                p_vol = int(row.get("dealsno_put", 0) or 0)

                is_atm = (atm_strike > 0 and strike == atm_strike)
                call_itm = "itm" if (live_index > 0 and strike < live_index) else ""
                put_itm = "itm" if (live_index > 0 and strike > live_index) else ""
                row_class = ' class="atm-row"' if is_atm else ""

                nd = '<span class="no-data">—</span>'
                c_rate_s = f"{c_rate:,.0f}" if c_rate > 0 else nd
                p_rate_s = f"{p_rate:,.0f}" if p_rate > 0 else nd
                c_delta_s = f'{c_delta}' if c_delta else nd
                p_delta_s = f'{p_delta}' if p_delta else nd
                c_oi_s = f'{c_oi:,}' if c_oi > 0 else nd
                p_oi_s = f'{p_oi:,}' if p_oi > 0 else nd
                c_vol_s = f'{c_vol}' if c_vol > 0 else nd
                p_vol_s = f'{p_vol}' if p_vol > 0 else nd

                chain_html += (
                    f'<tr{row_class}>'
                    f'<td class="{call_itm} oi">{c_oi_s}</td>'
                    f'<td class="{call_itm}">{c_vol_s}</td>'
                    f'<td class="{call_itm} delta">{c_delta_s}</td>'
                    f'<td class="{call_itm}">{c_rate_s}</td>'
                    f'<td class="strike-col">{strike:,}</td>'
                    f'<td class="{put_itm}">{p_rate_s}</td>'
                    f'<td class="{put_itm} delta">{p_delta_s}</td>'
                    f'<td class="{put_itm}">{p_vol_s}</td>'
                    f'<td class="{put_itm} oi">{p_oi_s}</td>'
                    f'</tr>'
                )
            chain_html += '</tbody></table></div>'
            st.markdown(chain_html, unsafe_allow_html=True)

            # ── Add to Sandbox widget ──
            st.markdown(
                f'<div style="color:{C_DIM};font-size:12px;margin:8px 0 4px;direction:rtl;">'
                f'➕ הוסף אופציה לגרף:</div>', unsafe_allow_html=True)

            add_cols = st.columns([1.5, 1.2, 1.2, 1.2, 1.5])
            with add_cols[0]:
                add_strike = st.selectbox("Strike",
                                          [int(s) for s in display_df["strike"].unique()],
                                          index=len(display_df) // 2,
                                          key="sb_add_strike", label_visibility="collapsed")
            with add_cols[1]:
                add_type = st.selectbox("Type", ["Call", "Put"],
                                        key="sb_add_type", label_visibility="collapsed")
            with add_cols[2]:
                add_action = st.selectbox("Action", ["BUY", "SELL"],
                                          key="sb_add_action", label_visibility="collapsed")

            match_row = display_df[display_df["strike"] == add_strike]
            auto_prem = 0.0
            if not match_row.empty:
                auto_prem = float(match_row.iloc[0].get(
                    f"lastrate_{add_type.lower()}_pts", 0) or 0)

            with add_cols[3]:
                st.markdown(
                    f'<div style="padding:8px 0;text-align:center;color:{C_TEXT};font-size:13px;">'
                    f'{fmt_num(auto_prem)} pts</div>', unsafe_allow_html=True)
            with add_cols[4]:
                if st.button("➕ הוסף לגרף", key="sb_chain_add", use_container_width=True):
                    st.session_state.sandbox_legs.append(
                        {"type": add_type, "action": add_action,
                         "strike": float(add_strike), "premium_pts": auto_prem, "qty": 1})
                    st.rerun()

    # ================================================================
    # § BOTTOM MODULE — Demo Portfolio & Real-Time P&L
    # ================================================================
    st.markdown('<div class="section-hdr">💼 תיק דמו — פוזיציות ו-P&L</div>',
                unsafe_allow_html=True)

    current_balance = get_demo_balance()
    open_trades = load_demo_trades("open")
    closed_trades = load_demo_trades("closed")

    total_unrealized = 0.0
    if open_trades and live_index > 0:
        for t in open_trades:
            total_unrealized += sandbox_trade_pnl(t, live_index)

    bal_color = "green" if current_balance >= DEMO_INITIAL_BALANCE else "red"
    unr_color = "green" if total_unrealized >= 0 else "red"
    unr_glow = "glow-green" if total_unrealized >= 0 else "glow-red"

    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">יתרת חשבון</div>'
        f'<div class="value {bal_color}">{current_balance:,.0f} ₪</div></div>'
        f'<div class="metric-card {unr_glow}"><div class="label">P&L לא ממומש</div>'
        f'<div class="value {unr_color}">{fmt_ils(total_unrealized)}</div></div>'
        f'<div class="metric-card"><div class="label">פתוחות</div>'
        f'<div class="value blue">{len(open_trades)}</div></div>'
        f'<div class="metric-card"><div class="label">סגורות</div>'
        f'<div class="value white">{len(closed_trades)}</div></div>'
        f'</div>', unsafe_allow_html=True)

    # ── Open positions ──
    if open_trades:
        for t in open_trades:
            t_id = t.get("trade_id", "?")
            t_name = t.get("strategy_name", "Custom")
            t_expiry = t.get("expiry_date", "")
            t_entry = float(t.get("entry_index", 0))
            t_legs = t.get("legs", [])
            if isinstance(t_legs, str):
                t_legs = json.loads(t_legs)
            t_max_profit = float(t.get("max_profit_ils", 0))
            t_pnl = sandbox_trade_pnl(t, live_index) if live_index > 0 else 0.0
            pnl_color = "green" if t_pnl >= 0 else "red"
            pnl_glow = "glow-green" if t_pnl >= 0 else "glow-red"

            st.markdown(
                f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
                f'padding:16px 20px;margin:10px 0;">'
                f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">'
                f'<div><span style="color:{C_TEXT};font-weight:700;font-size:15px;">{t_name}</span>'
                f'<span style="color:{C_DIM};font-size:12px;margin-left:10px;">#{t_id}</span></div>'
                f'<div style="display:flex;gap:20px;align-items:center;">'
                f'<span style="color:{C_DIM};font-size:12px;">פקיעה: <strong style="color:{C_TEXT};">{t_expiry}</strong></span>'
                f'<span style="color:{C_DIM};font-size:12px;">כניסה: <strong style="color:{C_YELLOW};">{t_entry:,.0f}</strong></span>'
                f'</div></div></div>', unsafe_allow_html=True)

            # Per-leg P&L table
            leg_html = ('<div class="table-scroll"><table><thead><tr>'
                        '<th>Leg</th><th>Action</th><th>Strike</th>'
                        '<th>Entry (₪)</th><th>Unrealized P&L</th>'
                        '</tr></thead><tbody>')
            for leg in t_legs:
                l_type = leg.get("type", "")
                l_action = leg.get("action", "")
                l_strike = float(leg.get("strike", 0))
                l_prem = float(leg.get("premium_pts", 0))
                l_qty = int(leg.get("qty", 1))
                l_sign = 1 if l_action == "BUY" else -1
                if live_index > 0:
                    intrinsic = (max(live_index - l_strike, 0) if l_type == "Call"
                                 else max(l_strike - live_index, 0))
                    leg_pnl = l_sign * (intrinsic - l_prem) * MULTIPLIER * l_qty
                else:
                    leg_pnl = 0.0
                css = "sell" if l_action == "SELL" else "buy"
                pnl_css = "buy" if leg_pnl >= 0 else "sell"
                leg_html += (f'<tr><td>{l_type}</td><td class="{css}">{l_action}</td>'
                             f'<td><strong>{l_strike:,.0f}</strong></td>'
                             f'<td>{l_prem * MULTIPLIER:,.0f}</td>'
                             f'<td class="{pnl_css}"><strong>{fmt_ils(leg_pnl)}</strong></td></tr>')
            leg_html += '</tbody></table></div>'
            st.markdown(leg_html, unsafe_allow_html=True)

            pnl_cols = st.columns([2, 1])
            with pnl_cols[0]:
                st.markdown(
                    f'<div class="metric-grid">'
                    f'<div class="metric-card {pnl_glow}"><div class="label">P&L לא ממומש</div>'
                    f'<div class="value {pnl_color}">{fmt_ils(t_pnl)}</div></div>'
                    f'<div class="metric-card"><div class="label">Max Profit</div>'
                    f'<div class="value blue">{fmt_ils(t_max_profit)}</div></div>'
                    f'</div>', unsafe_allow_html=True)
            with pnl_cols[1]:
                if st.button(f"🔒 סגור #{t_id}", key=f"sb_close_{t_id}", use_container_width=True):
                    s_idx = live_index if live_index > 0 else t_entry
                    f_pnl = sandbox_trade_pnl(t, s_idx)
                    close_demo_trade(t_id, s_idx, f_pnl, "manual_close")
                    _update_demo_balance(current_balance + f_pnl, f_pnl, f"close_{t_id}")
                    st.cache_data.clear()
                    st.rerun()
            st.markdown("---")
    else:
        st.markdown(
            f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
            f'padding:40px 20px;text-align:center;margin:12px 0;">'
            f'<div style="font-size:36px;margin-bottom:8px;">💼</div>'
            f'<div style="color:{C_TEXT};font-size:16px;font-weight:700;">אין פוזיציות פתוחות</div>'
            f'<div style="color:{C_DIM};font-size:13px;margin-top:4px;">'
            f'בנה אסטרטגיה למעלה ושגר לתיק הדמו</div></div>',
            unsafe_allow_html=True)

    # ── Closed trades ──
    if closed_trades:
        st.markdown('<div class="section-hdr">📜 היסטוריית עסקאות</div>',
                    unsafe_allow_html=True)
        closed_html = ('<div class="table-scroll"><table><thead><tr>'
                       '<th>ID</th><th>Strategy</th><th>Expiry</th>'
                       '<th>Entry</th><th>Settlement</th><th>P&L</th><th>סיבה</th>'
                       '</tr></thead><tbody>')
        total_realized = 0.0
        for ct in closed_trades:
            ct_pnl = float(ct.get("pnl_ils", 0))
            total_realized += ct_pnl
            pnl_css = "buy" if ct_pnl >= 0 else "sell"
            reason_lbl = "פקיעה" if "expiry" in ct.get("close_reason", "") else "ידני"
            closed_html += (
                f'<tr><td>{ct.get("trade_id","?")}</td>'
                f'<td>{ct.get("strategy_name","")}</td>'
                f'<td>{ct.get("expiry_date","")}</td>'
                f'<td>{float(ct.get("entry_index",0)):,.0f}</td>'
                f'<td>{float(ct.get("settlement_index",0)):,.0f}</td>'
                f'<td class="{pnl_css}"><strong>{fmt_ils(ct_pnl)}</strong></td>'
                f'<td>{reason_lbl}</td></tr>')
        closed_html += '</tbody></table></div>'
        st.markdown(closed_html, unsafe_allow_html=True)
        real_c = "#00E676" if total_realized >= 0 else "#FF1744"
        st.markdown(
            f'<div style="text-align:center;padding:10px;color:{C_DIM};font-size:13px;">'
            f'סה"כ ממומש: <strong style="color:{real_c};">{fmt_ils(total_realized)}</strong></div>',
            unsafe_allow_html=True)

        # ── CSV Export for knowledge preservation ──
        import csv
        import io
        # newline='' prevents double-newlines on Windows (\r\r\n -> \r\n)
        csv_buf = io.StringIO(newline='')
        fieldnames = ["trade_id", "strategy_name", "expiry_date", "entry_index",
                      "settlement_index", "pnl_ils", "close_reason", "legs", "closed_at"]
        writer = csv.DictWriter(csv_buf, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for ct in closed_trades:
            row_out = {k: ct.get(k, "") for k in fieldnames}
            if isinstance(row_out.get("legs"), (list, dict)):
                row_out["legs"] = json.dumps(row_out["legs"], ensure_ascii=False)
            writer.writerow(row_out)

        st.download_button(
            label="📥 ייצוא היסטוריה ל-CSV",
            data=csv_buf.getvalue(),
            file_name=f"demo_trades_{now_il.strftime('%Y%m%d')}.csv",
            mime="text/csv",
            key="sb_export_csv",
            use_container_width=True,
        )


# ╔════════════════════════════════════════════════════════════════════╗
# ║  STRATEGY DESK PAGES (Open Positions / History)                  ║
# ╚════════════════════════════════════════════════════════════════════╝
elif has_strategies:

    # ── Week selector ──
    week_options = (
        df[["_week_label", "_trigger_dt"]]
        .drop_duplicates("_week_label")
        .sort_values("_trigger_dt", ascending=False)
    )["_week_label"].tolist()

    render_breadcrumb([("שבוע מסחר", True)])
    selected_week = st.selectbox("📅 שבוע מסחר / תאריך הרצה", week_options, index=0,
                                  label_visibility="collapsed")

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
        f'</div>', unsafe_allow_html=True)

    all_active = week_all[~week_all["_is_settled"]]
    all_history = week_all[week_all["_is_settled"]]

    # ==============================================================
    # OPEN POSITIONS
    # ==============================================================
    if nav_page == "🔵 Open Positions":
        if all_active.empty:
            st.info("אין פוזיציות פתוחות כרגע — כל האסטרטגיות של השבוע פקעו.")
        else:
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

            summary_html = '<div class="metric-grid">'
            for ip in interval_pnl_active:
                u_color = "green" if ip["pnl"] >= 0 else "red"
                glow = "glow-green" if ip["pnl"] >= 0 else "glow-red"
                summary_html += f'<div class="metric-card {glow}"><div class="label">{ip["pct"]:.1f}% ({ip["n"]})</div><div class="value {u_color}">{fmt_ils(ip["pnl"])}</div></div>'
            summary_html += '</div>'
            st.markdown(summary_html, unsafe_allow_html=True)

            active_expiry_dates = sorted(all_active["expiry_date"].unique())
            active_expiry_labels = {}
            for ed in active_expiry_dates:
                edf = all_active[all_active["expiry_date"] == ed]
                day_he = DAY_HE.get(edf.iloc[0].get("expiry_day_name", ""), "")
                n_intervals = len(edf["interval_pct"].unique())
                active_expiry_labels[ed] = f"{ed} — יום {day_he}  |  {n_intervals} מרווחים"

            render_breadcrumb([("שבוע", False), ("תאריך פקיעה", True)])
            sel_active_expiry = st.selectbox("📅 תאריך פקיעה", active_expiry_dates,
                                              format_func=lambda x: active_expiry_labels.get(x, x),
                                              key="active_expiry")
            active_by_expiry = all_active[all_active["expiry_date"] == sel_active_expiry]

            avail_intervals = sorted(active_by_expiry["interval_pct"].unique())
            render_breadcrumb([("שבוע", False), ("פקיעה", False), ("מרווח", True)])
            sel_active_interval = st.selectbox("📐 מרווח אסטרטגיה", avail_intervals,
                                                format_func=lambda x: f"{x:.1f}%",
                                                key="active_interval")

            row = active_by_expiry[active_by_expiry["interval_pct"] == sel_active_interval].iloc[0]

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
                    f'</div>', unsafe_allow_html=True)

            render_legs_table(row)
            render_expiry_metrics(row)
            ref_p = live_index if live_index > 0 else 0
            ref_l = f"Live: {ref_p:,.2f}" if ref_p > 0 else ""
            render_payoff_chart(row, ref_price=ref_p, ref_label=ref_l)

    # ==============================================================
    # HISTORY
    # ==============================================================
    elif nav_page == "📜 History":
        if all_history.empty:
            st.info("אין היסטוריה — אף אסטרטגיה לא פקעה עדיין.")
        else:
            history_intervals = sorted(all_history["interval_pct"].unique())
            comparison_data = []
            for pct in history_intervals:
                idf = all_history[all_history["interval_pct"] == pct]
                comparison_data.append({
                    "pct": pct, "actual_pnl": idf["actual_pnl_ils"].sum(),
                    "max_possible": idf["max_profit_ils"].sum(),
                    "n_total": len(idf), "n_wins": int((idf["actual_pnl_ils"] > 0).sum()),
                })

            st.markdown('<div class="section-hdr">📊 מה יכולת להרוויח? — השוואת מרווחים</div>',
                        unsafe_allow_html=True)

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

            st.markdown('<div class="section-hdr">📈 Max Profit vs. Actual P&L</div>',
                        unsafe_allow_html=True)
            abs_max = max(max(abs(cd["max_possible"]), abs(cd["actual_pnl"]))
                          for cd in comparison_data) if comparison_data else 1
            for cd in comparison_data:
                max_w = (cd["max_possible"] / abs_max * 100) if abs_max > 0 else 0
                actual_w = (abs(cd["actual_pnl"]) / abs_max * 100) if abs_max > 0 else 0
                bar_c = C_GREEN if cd["actual_pnl"] >= 0 else C_RED
                st.markdown(
                    f'<div class="cmp-row">'
                    f'<div style="font-weight:700;color:{C_TEXT};font-size:14px;margin-bottom:6px">{cd["pct"]:.1f}%</div>'
                    f'<div class="cmp-line"><span class="cmp-lbl">Max</span><div class="cmp-track"><div class="cmp-fill" style="width:{max_w:.0f}%;background:{C_BLUE}"></div></div><span class="cmp-val" style="color:{C_BLUE}">{fmt_ils(cd["max_possible"])}</span></div>'
                    f'<div class="cmp-line"><span class="cmp-lbl">Actual</span><div class="cmp-track"><div class="cmp-fill" style="width:{actual_w:.0f}%;background:{bar_c}"></div></div><span class="cmp-val" style="color:{bar_c}">{fmt_ils(cd["actual_pnl"])}</span></div>'
                    f'</div>', unsafe_allow_html=True)

            st.markdown('<div class="section-hdr">🔍 ניתוח מפורט לפי פקיעה ומרווח</div>',
                        unsafe_allow_html=True)

            hist_expiry_dates = sorted(all_history["expiry_date"].unique())
            hist_expiry_labels = {}
            for ed in hist_expiry_dates:
                edf = all_history[all_history["expiry_date"] == ed]
                day_he = DAY_HE.get(edf.iloc[0].get("expiry_day_name", ""), "")
                total_pnl_day = edf["actual_pnl_ils"].sum()
                icon = "✅" if total_pnl_day > 0 else "❌"
                hist_expiry_labels[ed] = f"{ed} — {day_he}  |  {icon} {fmt_ils(total_pnl_day)}"

            render_breadcrumb([("שבוע", False), ("תאריך פקיעה", True)])
            sel_hist_expiry = st.selectbox("📅 תאריך פקיעה", hist_expiry_dates,
                                            format_func=lambda x: hist_expiry_labels.get(x, x),
                                            key="history_expiry")
            hist_by_expiry = all_history[all_history["expiry_date"] == sel_hist_expiry]

            hist_avail_intervals = sorted(hist_by_expiry["interval_pct"].unique())
            render_breadcrumb([("שבוע", False), ("פקיעה", False), ("מרווח", True)])
            sel_hist_interval = st.selectbox("📐 מרווח אסטרטגיה", hist_avail_intervals,
                                              format_func=lambda x: f"{x:.1f}%",
                                              key="history_interval")

            row = hist_by_expiry[hist_by_expiry["interval_pct"] == sel_hist_interval].iloc[0]

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
                f'</div>', unsafe_allow_html=True)

            render_legs_table(row)

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
            render_payoff_chart(row, ref_price=settle_price,
                                ref_label=f"Settlement: {settle_price:,.2f}" if settle_price > 0 else "")

            pnl_class = "profit" if actual_pnl >= 0 else "loss"
            glow_class = "glow-profit" if actual_pnl >= 0 else "glow-loss"
            st.markdown(
                f'<div class="pnl-hero {glow_class}">'
                f'<div class="title">Settlement Result — {sel_hist_expiry} @ {sel_hist_interval:.1f}%</div>'
                f'<div class="amount {pnl_class}">{fmt_ils(actual_pnl)}</div>'
                f'<div style="color:{C_DIM};font-size:13px;margin-top:8px">out of max possible: {fmt_ils(max_profit)}</div>'
                f'</div>', unsafe_allow_html=True)

else:
    if nav_page != "🕹️ Demo Trading":
        st.warning("אין נתוני אסטרטגיות ב-Supabase. ודא שהמערכת רצה ושיש חיבור תקין.")


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
