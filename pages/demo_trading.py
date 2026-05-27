"""
🕹️ זירת מסחר דמו — Paper Trading Arena
=========================================
Interactive payoff graph builder with strategy templates
and custom leg construction for TASE TA-35 Mini options.
"""

import os
import json
import uuid
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
    page_title="TA-35 Demo Trading",
    page_icon="🕹️",
    layout="wide",
)

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")

# Import multiplier from shared config (single source of truth)
try:
    from config import TASE_MULTIPLIER as MULTIPLIER
except ImportError:
    MULTIPLIER = 50

# Palette — shared with main dashboard
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
.arena-header {{
    text-align: center;
    padding: 18px 0 8px;
    margin-bottom: 6px;
}}
.arena-header h1 {{
    color: {C_TEXT};
    font-size: 26px;
    font-weight: 800;
    letter-spacing: -0.5px;
    margin: 0;
}}
.arena-header .sub {{
    color: {C_DIM};
    font-size: 13px;
    margin-top: 4px;
}}

/* ── Metric Cards ── */
.metric-grid {{
    display: flex;
    gap: 14px;
    margin: 14px 0;
    flex-wrap: wrap;
}}
.metric-card {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 12px;
    padding: 16px 20px;
    flex: 1;
    min-width: 150px;
    text-align: center;
}}
.metric-card .label {{
    color: {C_DIM};
    font-size: 11px;
    font-weight: 600;
    text-transform: uppercase;
    letter-spacing: 0.5px;
    margin-bottom: 5px;
}}
.metric-card .value {{
    font-size: 22px;
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

/* ── Legs Table ── */
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
    min-width: 500px;
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
    padding: 10px 14px;
    border-bottom: 1px solid {C_BORDER};
    text-align: center;
    position: sticky;
    top: 0;
}}
.table-scroll td {{
    padding: 9px 14px;
    text-align: center;
    border-bottom: 1px solid rgba(30,36,51,0.6);
    color: {C_TEXT};
    font-weight: 500;
}}
.table-scroll tr:last-child td {{ border-bottom: none; }}
.table-scroll tr:hover td {{ background: rgba(255,255,255,0.02); }}
.table-scroll .buy  {{ color: {C_GREEN}; font-weight: 700; }}
.table-scroll .sell {{ color: {C_RED}; font-weight: 700; }}

/* ── Leg Builder Card ── */
.leg-card {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 14px 18px;
    margin: 6px 0;
    display: flex;
    align-items: center;
    gap: 12px;
}}
.leg-card .leg-type {{
    font-size: 12px;
    font-weight: 700;
    text-transform: uppercase;
    min-width: 50px;
}}
.leg-card .leg-type.call {{ color: {C_GREEN}; }}
.leg-card .leg-type.put {{ color: {C_RED}; }}

/* ── Section Header ── */
.section-hdr {{
    color: {C_TEXT};
    font-size: 16px;
    font-weight: 700;
    margin: 22px 0 10px;
    padding-bottom: 6px;
    border-bottom: 1px solid {C_BORDER};
    direction: rtl;
    text-align: right;
}}

/* ── Strategy Templates ── */
.tpl-grid {{
    display: flex;
    gap: 10px;
    margin: 10px 0;
    flex-wrap: wrap;
}}
.tpl-btn {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 14px 20px;
    cursor: pointer;
    text-align: center;
    flex: 1;
    min-width: 140px;
    transition: border-color 0.2s;
}}
.tpl-btn:hover {{
    border-color: {C_BLUE};
}}
.tpl-btn .tpl-name {{
    color: {C_TEXT};
    font-size: 14px;
    font-weight: 700;
}}
.tpl-btn .tpl-desc {{
    color: {C_DIM};
    font-size: 11px;
    margin-top: 3px;
}}

/* ── Streamlit overrides ── */
.stSelectbox label {{ color: {C_TEXT} !important; font-weight: 600 !important; }}
div[data-baseweb="select"] {{
    background: {C_CARD} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 8px !important;
}}
.stNumberInput label {{ color: {C_TEXT} !important; font-weight: 600 !important; }}

/* ── Option Chain ── */
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
.chain-wrap th.put-hdr {{ color: {C_RED}; }}
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
.chain-wrap td.itm {{
    background: rgba(255,255,255,0.025);
}}
.chain-wrap td.atm-row {{
    background: rgba(0,176,255,0.06) !important;
    border-top: 1px solid rgba(0,176,255,0.2);
    border-bottom: 1px solid rgba(0,176,255,0.2);
}}
.chain-wrap .oi {{ color: {C_DIM}; font-size: 11px; }}
.chain-wrap .delta {{ color: {C_DIM}; font-size: 11px; }}
.chain-wrap .no-data {{ color: rgba(255,255,255,0.15); }}
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


# ==================================================================
# STRATEGY TEMPLATES
# ==================================================================

STRATEGY_TEMPLATES = {
    "iron_condor": {
        "name": "Iron Condor",
        "name_he": "קונדור ברזל",
        "icon": "🦅",
        "desc": "Sell OTM Call + Put, Buy wings for protection",
        "legs": [
            {"type": "Put",  "action": "BUY",  "strike_offset": -3},  # Long Put (far OTM)
            {"type": "Put",  "action": "SELL", "strike_offset": -1},   # Short Put
            {"type": "Call", "action": "SELL", "strike_offset": +1},   # Short Call
            {"type": "Call", "action": "BUY",  "strike_offset": +3},   # Long Call (far OTM)
        ],
    },
    "bull_put_spread": {
        "name": "Bull Put Spread",
        "name_he": "ספרד פוט שורי",
        "icon": "📈",
        "desc": "Sell Put near ATM, Buy Put further OTM",
        "legs": [
            {"type": "Put", "action": "BUY",  "strike_offset": -2},
            {"type": "Put", "action": "SELL", "strike_offset": -1},
        ],
    },
    "bear_call_spread": {
        "name": "Bear Call Spread",
        "name_he": "ספרד קול דובי",
        "icon": "📉",
        "desc": "Sell Call near ATM, Buy Call further OTM",
        "legs": [
            {"type": "Call", "action": "SELL", "strike_offset": +1},
            {"type": "Call", "action": "BUY",  "strike_offset": +2},
        ],
    },
    "long_straddle": {
        "name": "Long Straddle",
        "name_he": "סטרדל ארוך",
        "icon": "⚡",
        "desc": "Buy ATM Call + Put — profit from big moves",
        "legs": [
            {"type": "Put",  "action": "BUY", "strike_offset": 0},
            {"type": "Call", "action": "BUY", "strike_offset": 0},
        ],
    },
    "custom": {
        "name": "Custom Build",
        "name_he": "בנייה חופשית",
        "icon": "🛠️",
        "desc": "Build any combination of legs manually",
        "legs": [],
    },
}


@st.cache_data(ttl=90)
def load_option_chain(expiry_date: str) -> pd.DataFrame:
    """Load latest option chain snapshot from tase_putcall for a given expiry."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()

    # Get latest fetch_date + fetch_time for this expiry
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

    # Fetch all rows for that snapshot
    all_rows = []
    batch = 500
    offset = 0
    while True:
        url = (
            f"{SUPABASE_URL}/rest/v1/tase_putcall"
            f"?select=expirationprice_call,lastrate_call,lastrate_put,"
            f"delta_call,delta_put,openpositions_call,openpositions_put,"
            f"dealsno_call,dealsno_put,derivativeid_call,derivativeid_put"
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

    # Convert lastrate from ₪/contract to index points
    for col in ["lastrate_call", "lastrate_put"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)
            df[f"{col}_pts"] = df[col] / MULTIPLIER

    for col in ["delta_call", "delta_put", "openpositions_call", "openpositions_put",
                 "dealsno_call", "dealsno_put", "strike"]:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    df = df.sort_values("strike").reset_index(drop=True)
    return df


@st.cache_data(ttl=120)
def get_available_expiries() -> list:
    """Get distinct expiry dates from tase_putcall."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = (
        f"{SUPABASE_URL}/rest/v1/tase_putcall"
        f"?select=expiry_date"
        f"&order=expiry_date"
        f"&limit=1000"
    )
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            return sorted(set(row["expiry_date"] for row in r.json() if row.get("expiry_date")))
    except Exception:
        pass
    return []


def get_demo_balance() -> float:
    """Get current demo account balance."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return 100000.0
    url = f"{SUPABASE_URL}/rest/v1/demo_balance?select=balance&order=id.desc&limit=1"
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206) and r.json():
            return float(r.json()[0]["balance"])
    except Exception:
        pass
    return 100000.0


def update_demo_balance(new_balance: float, change: float, reason: str):
    """Insert a new balance record."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return
    url = f"{SUPABASE_URL}/rest/v1/demo_balance"
    headers = _supabase_headers()
    headers["Prefer"] = "return=minimal"
    httpx.post(url, headers=headers, content=json.dumps({
        "balance": round(new_balance, 2),
        "change_amount": round(change, 2),
        "change_reason": reason,
    }), timeout=10)


def save_demo_trade(trade: dict):
    """Save a new demo trade to Supabase."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    url = f"{SUPABASE_URL}/rest/v1/demo_trades"
    headers = _supabase_headers()
    headers["Prefer"] = "return=minimal"
    r = httpx.post(url, headers=headers, content=json.dumps(trade), timeout=10)
    return r.status_code in (200, 201)


def load_demo_trades(status: str = "open") -> list:
    """Load demo trades by status."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return []
    url = (
        f"{SUPABASE_URL}/rest/v1/demo_trades"
        f"?status=eq.{status}&order=created_at.desc&limit=100"
    )
    try:
        r = httpx.get(url, headers=_supabase_headers(), timeout=10)
        if r.status_code in (200, 206):
            return r.json()
    except Exception:
        pass
    return []


def close_demo_trade(trade_id: str, settlement_index: float, pnl_ils: float, reason: str = "manual_close"):
    """Close a demo trade — update status, settlement, P&L."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return False
    from datetime import timezone
    url = f"{SUPABASE_URL}/rest/v1/demo_trades?trade_id=eq.{trade_id}"
    headers = _supabase_headers()
    headers["Prefer"] = "return=minimal"
    r = httpx.patch(url, headers=headers, content=json.dumps({
        "status": "closed",
        "settlement_index": settlement_index,
        "pnl_ils": round(pnl_ils, 2),
        "close_reason": reason,
        "closed_at": datetime.now(timezone.utc).isoformat(),
    }), timeout=10)
    return r.status_code in (200, 204)


def compute_trade_pnl(trade: dict, current_index: float) -> float:
    """Compute P&L for a trade at a given index level."""
    legs = trade.get("legs", [])
    if isinstance(legs, str):
        legs = json.loads(legs)

    total_pnl = 0.0
    for leg in legs:
        strike = float(leg["strike"])
        prem = float(leg["premium_pts"])
        qty = int(leg.get("qty", 1))
        sign = 1 if leg["action"] == "BUY" else -1

        if leg["type"] == "Call":
            intrinsic = max(current_index - strike, 0)
        else:
            intrinsic = max(strike - current_index, 0)

        leg_pnl = sign * (intrinsic - prem) * MULTIPLIER * qty
        total_pnl += leg_pnl

    return round(total_pnl, 2)


def generate_strike_grid(base_index: float, step: int = 10, count: int = 15) -> list:
    """Generate a list of strikes around the current index."""
    center = round(base_index / step) * step
    return [center + (i - count) * step for i in range(2 * count + 1)]


def apply_template(template_key: str, base_index: float, step: int = 20) -> list:
    """Create legs from a template, using strike offsets × step around base_index."""
    tpl = STRATEGY_TEMPLATES.get(template_key, {})
    center = round(base_index / step) * step
    legs = []
    for leg_def in tpl.get("legs", []):
        strike = center + leg_def["strike_offset"] * step
        legs.append({
            "type": leg_def["type"],
            "action": leg_def["action"],
            "strike": float(strike),
            "premium_pts": 0.0,  # User will fill or fetch
            "qty": 1,
        })
    return legs


def compute_payoff(legs: list, price_range: np.ndarray) -> np.ndarray:
    """Compute total P&L in ₪ for an array of underlying prices at expiry."""
    total = np.zeros_like(price_range, dtype=float)
    for leg in legs:
        strike = leg["strike"]
        prem = leg["premium_pts"]
        qty = leg["qty"]
        sign = 1 if leg["action"] == "BUY" else -1

        if leg["type"] == "Call":
            intrinsic = np.maximum(price_range - strike, 0)
        else:  # Put
            intrinsic = np.maximum(strike - price_range, 0)

        # P&L per contract = (intrinsic - premium) for BUY, (premium - intrinsic) for SELL
        leg_pnl = sign * (intrinsic - prem) * MULTIPLIER * qty
        total += leg_pnl

    return total


def compute_strategy_metrics(legs: list, base_index: float) -> dict:
    """Compute key metrics: max profit, max loss, breakevens."""
    if not legs:
        return {"max_profit": 0, "max_loss": 0, "breakevens": [], "net_premium": 0}

    x = np.linspace(base_index - 500, base_index + 500, 2000)
    y = compute_payoff(legs, x)

    max_profit = float(np.max(y))
    max_loss = float(np.min(y))

    # Net premium received/paid
    net_prem = 0.0
    for leg in legs:
        sign = -1 if leg["action"] == "BUY" else 1  # SELL = receive, BUY = pay
        net_prem += sign * leg["premium_pts"] * leg["qty"]

    # Find breakevens (where P&L crosses zero)
    breakevens = []
    for i in range(1, len(y)):
        if (y[i-1] < 0 and y[i] >= 0) or (y[i-1] >= 0 and y[i] < 0):
            # Linear interpolation
            x_cross = x[i-1] + (0 - y[i-1]) * (x[i] - x[i-1]) / (y[i] - y[i-1])
            breakevens.append(round(x_cross, 1))

    return {
        "max_profit": max_profit,
        "max_loss": max_loss,
        "breakevens": breakevens,
        "net_premium": net_prem,
    }


# ==================================================================
# SESSION STATE INIT
# ==================================================================
if "arena_legs" not in st.session_state:
    st.session_state.arena_legs = []
if "arena_template" not in st.session_state:
    st.session_state.arena_template = None


# ==================================================================
# SIDEBAR
# ==================================================================
with st.sidebar:
    st.markdown(f"""
    <div style="text-align:center;padding:18px 0 14px;">
        <div style="font-size:22px;font-weight:800;color:{C_TEXT};letter-spacing:-0.5px;">🕹️ זירת מסחר</div>
        <div style="font-size:11px;color:{C_DIM};margin-top:4px;">Paper Trading — TA-35</div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f'<div style="border-bottom:1px solid {C_BORDER};margin:8px 0 16px;"></div>', unsafe_allow_html=True)

    st.markdown(f"""
    <div style="color:{C_DIM};font-size:12px;padding:8px 4px;direction:rtl;line-height:1.7;">
        <strong style="color:{C_TEXT};">איך זה עובד?</strong><br>
        ① בחר תבנית אסטרטגיה או בנה ידנית<br>
        ② הגדר מחירי מימוש ופרמיות<br>
        ③ הגרף מתעדכן מיידית<br>
        ④ נתח breakevens ו-risk/reward
    </div>
    """, unsafe_allow_html=True)

    st.markdown(f"""
    <div style="border-top:1px solid {C_BORDER};margin:16px 0;padding-top:14px;">
        <div style="color:{C_DIM};font-size:11px;text-align:center;">
            Multiplier: {MULTIPLIER}₪/pt<br>
            <a href="/" target="_self" style="color:{C_BLUE};text-decoration:none;">← חזרה לדשבורד</a>
        </div>
    </div>
    """, unsafe_allow_html=True)


# ==================================================================
# HEADER
# ==================================================================
now_il = datetime.now(TZ)
live_index = get_live_index()

st.markdown(f"""
<div class="arena-header">
    <h1>🕹️ זירת מסחר דמו — Paper Trading</h1>
    <div class="sub">TA-35 Mini Options  |  {now_il.strftime("%H:%M")} Israel  |  Index: {fmt_num(live_index) if live_index > 0 else "N/A"}</div>
</div>
""", unsafe_allow_html=True)


# ==================================================================
# SECTION 1: STRATEGY TEMPLATE SELECTOR
# ==================================================================
st.markdown('<div class="section-hdr">① בחר אסטרטגיה</div>', unsafe_allow_html=True)

template_cols = st.columns(len(STRATEGY_TEMPLATES))
for i, (key, tpl) in enumerate(STRATEGY_TEMPLATES.items()):
    with template_cols[i]:
        if st.button(
            f"{tpl['icon']} {tpl['name_he']}",
            key=f"tpl_{key}",
            use_container_width=True,
            type="primary" if st.session_state.arena_template == key else "secondary",
        ):
            st.session_state.arena_template = key
            base = live_index if live_index > 0 else 2000
            st.session_state.arena_legs = apply_template(key, base)
            st.rerun()

# Show selected template info
if st.session_state.arena_template and st.session_state.arena_template in STRATEGY_TEMPLATES:
    tpl = STRATEGY_TEMPLATES[st.session_state.arena_template]
    st.markdown(
        f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:10px;'
        f'padding:12px 18px;margin:8px 0;direction:rtl;text-align:right;">'
        f'<span style="font-size:18px;">{tpl["icon"]}</span> '
        f'<strong style="color:{C_TEXT};">{tpl["name"]}</strong> '
        f'<span style="color:{C_DIM};font-size:13px;">— {tpl["desc"]}</span>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ==================================================================
# SECTION 2: LEG BUILDER
# ==================================================================
st.markdown('<div class="section-hdr">② הגדר רגליים</div>', unsafe_allow_html=True)

legs = st.session_state.arena_legs
base = live_index if live_index > 0 else 2000
strikes = generate_strike_grid(base, step=10, count=20)

if not legs:
    st.info("בחר תבנית אסטרטגיה למעלה, או הוסף רגליים ידנית 👇")

# Render each leg as editable row
updated_legs = []
for idx, leg in enumerate(legs):
    cols = st.columns([1.5, 1.5, 2, 2, 1.5, 0.8])

    with cols[0]:
        leg_type = st.selectbox(
            "סוג", ["Call", "Put"],
            index=0 if leg["type"] == "Call" else 1,
            key=f"leg_type_{idx}",
            label_visibility="collapsed" if idx > 0 else "visible",
        )

    with cols[1]:
        leg_action = st.selectbox(
            "פעולה", ["BUY", "SELL"],
            index=0 if leg["action"] == "BUY" else 1,
            key=f"leg_action_{idx}",
            label_visibility="collapsed" if idx > 0 else "visible",
        )

    with cols[2]:
        leg_strike = st.number_input(
            "Strike",
            min_value=0.0,
            max_value=5000.0,
            value=float(leg["strike"]),
            step=10.0,
            key=f"leg_strike_{idx}",
            label_visibility="collapsed" if idx > 0 else "visible",
        )

    with cols[3]:
        leg_premium = st.number_input(
            "Premium (pts)",
            min_value=0.0,
            max_value=500.0,
            value=float(leg["premium_pts"]),
            step=0.5,
            key=f"leg_prem_{idx}",
            label_visibility="collapsed" if idx > 0 else "visible",
        )

    with cols[4]:
        leg_qty = st.number_input(
            "Qty",
            min_value=1,
            max_value=50,
            value=int(leg.get("qty", 1)),
            step=1,
            key=f"leg_qty_{idx}",
            label_visibility="collapsed" if idx > 0 else "visible",
        )

    with cols[5]:
        if idx > 0:
            st.write("")  # Spacer for alignment
        if st.button("🗑️", key=f"leg_del_{idx}", help="הסר רגל"):
            continue  # Skip this leg (delete)

    updated_legs.append({
        "type": leg_type,
        "action": leg_action,
        "strike": leg_strike,
        "premium_pts": leg_premium,
        "qty": leg_qty,
    })

# Update state if changed
if len(updated_legs) != len(legs):
    st.session_state.arena_legs = updated_legs
    st.rerun()
else:
    st.session_state.arena_legs = updated_legs

# Add leg button
btn_cols = st.columns([1, 1, 4])
with btn_cols[0]:
    if st.button("➕ הוסף רגל", use_container_width=True):
        st.session_state.arena_legs.append({
            "type": "Call",
            "action": "BUY",
            "strike": round(base / 10) * 10,
            "premium_pts": 0.0,
            "qty": 1,
        })
        st.rerun()

with btn_cols[1]:
    if st.button("🧹 נקה הכל", use_container_width=True):
        st.session_state.arena_legs = []
        st.session_state.arena_template = None
        st.rerun()


# ==================================================================
# SECTION 3: OPTION CHAIN
# ==================================================================
st.markdown('<div class="section-hdr">③ שרשרת אופציות — Option Chain</div>', unsafe_allow_html=True)

expiry_dates = get_available_expiries()

if not expiry_dates:
    st.info("אין נתוני אופציות זמינים כרגע. המערכת תטען נתונים בזמן המסחר.")
else:
    chain_cols = st.columns([3, 1])
    with chain_cols[1]:
        sel_expiry = st.selectbox(
            "📅 פקיעה",
            expiry_dates,
            index=0,
            key="chain_expiry",
        )

    chain_df = load_option_chain(sel_expiry)

    if chain_df.empty:
        st.warning("אין נתוני שרשרת לתאריך הפקיעה שנבחר.")
    else:
        # Filter: show strikes within ±200 of live index (or all if no index)
        if live_index > 0:
            atm_strike = chain_df.iloc[(chain_df["strike"] - live_index).abs().argsort().iloc[0]]["strike"]
            display_df = chain_df[
                (chain_df["strike"] >= live_index - 200) &
                (chain_df["strike"] <= live_index + 200)
            ].copy()
        else:
            atm_strike = 0
            display_df = chain_df.copy()

        if display_df.empty:
            display_df = chain_df.copy()

        with chain_cols[0]:
            n_strikes = len(display_df)
            st.markdown(
                f'<span style="color:{C_DIM};font-size:12px;">'
                f'{n_strikes} strikes  |  Expiry: {sel_expiry}'
                f'{"  |  ATM ≈ " + fmt_num(atm_strike, 0) if atm_strike > 0 else ""}'
                f'</span>',
                unsafe_allow_html=True,
            )

        # Build chain HTML table
        chain_html = (
            '<div class="chain-wrap"><table><thead><tr>'
            '<th class="call-hdr">+</th>'
            '<th class="call-hdr">OI</th>'
            '<th class="call-hdr">Vol</th>'
            '<th class="call-hdr">Delta</th>'
            '<th class="call-hdr">Premium ₪</th>'
            '<th class="strike-hdr">⚡ STRIKE</th>'
            '<th class="put-hdr">Premium ₪</th>'
            '<th class="put-hdr">Delta</th>'
            '<th class="put-hdr">Vol</th>'
            '<th class="put-hdr">OI</th>'
            '<th class="put-hdr">+</th>'
            '</tr></thead><tbody>'
        )

        for _, row in display_df.iterrows():
            strike = int(row["strike"])
            c_rate = row.get("lastrate_call", 0) or 0
            p_rate = row.get("lastrate_put", 0) or 0
            c_pts = row.get("lastrate_call_pts", 0) or 0
            p_pts = row.get("lastrate_put_pts", 0) or 0
            c_delta = int(row.get("delta_call", 0) or 0)
            p_delta = int(row.get("delta_put", 0) or 0)
            c_oi = int(row.get("openpositions_call", 0) or 0)
            p_oi = int(row.get("openpositions_put", 0) or 0)
            c_vol = int(row.get("dealsno_call", 0) or 0)
            p_vol = int(row.get("dealsno_put", 0) or 0)

            # ITM highlighting
            is_atm = (atm_strike > 0 and strike == atm_strike)
            call_itm = "itm" if (live_index > 0 and strike < live_index) else ""
            put_itm = "itm" if (live_index > 0 and strike > live_index) else ""
            row_class = ' class="atm-row"' if is_atm else ""

            # Format values
            c_rate_s = f"{c_rate:,.0f}" if c_rate > 0 else '<span class="no-data">—</span>'
            p_rate_s = f"{p_rate:,.0f}" if p_rate > 0 else '<span class="no-data">—</span>'
            c_delta_s = f'{c_delta}' if c_delta != 0 else '<span class="no-data">—</span>'
            p_delta_s = f'{p_delta}' if p_delta != 0 else '<span class="no-data">—</span>'
            c_oi_s = f'{c_oi:,}' if c_oi > 0 else '<span class="no-data">—</span>'
            p_oi_s = f'{p_oi:,}' if p_oi > 0 else '<span class="no-data">—</span>'
            c_vol_s = f'{c_vol}' if c_vol > 0 else '<span class="no-data">—</span>'
            p_vol_s = f'{p_vol}' if p_vol > 0 else '<span class="no-data">—</span>'

            chain_html += (
                f'<tr{row_class}>'
                f'<td><span class="add-call" data-strike="{strike}" data-pts="{c_pts:.2f}">📥</span></td>'
                f'<td class="{call_itm} oi">{c_oi_s}</td>'
                f'<td class="{call_itm}">{c_vol_s}</td>'
                f'<td class="{call_itm} delta">{c_delta_s}</td>'
                f'<td class="{call_itm}">{c_rate_s}</td>'
                f'<td class="strike-col">{strike:,}</td>'
                f'<td class="{put_itm}">{p_rate_s}</td>'
                f'<td class="{put_itm} delta">{p_delta_s}</td>'
                f'<td class="{put_itm}">{p_vol_s}</td>'
                f'<td class="{put_itm} oi">{p_oi_s}</td>'
                f'<td><span class="add-put" data-strike="{strike}" data-pts="{p_pts:.2f}">📥</span></td>'
                f'</tr>'
            )

        chain_html += '</tbody></table></div>'
        st.markdown(chain_html, unsafe_allow_html=True)

        # Interactive "Add to Graph" — Streamlit buttons (since HTML onclick can't update session_state)
        st.markdown(f'<div style="color:{C_DIM};font-size:12px;margin:6px 0 12px;direction:rtl;">⬇️ הוסף אופציה לגרף:</div>', unsafe_allow_html=True)

        add_cols = st.columns([1.5, 1.5, 1, 1, 1.5])
        with add_cols[0]:
            add_strike = st.selectbox(
                "Strike",
                [int(s) for s in display_df["strike"].unique()],
                index=len(display_df) // 2,
                key="chain_add_strike",
                label_visibility="collapsed",
            )
        with add_cols[1]:
            add_type = st.selectbox(
                "Type", ["Call", "Put"],
                key="chain_add_type",
                label_visibility="collapsed",
            )
        with add_cols[2]:
            add_action = st.selectbox(
                "Action", ["BUY", "SELL"],
                key="chain_add_action",
                label_visibility="collapsed",
            )

        # Auto-fill premium from chain data
        match_row = display_df[display_df["strike"] == add_strike]
        auto_prem = 0.0
        if not match_row.empty:
            if add_type == "Call":
                auto_prem = float(match_row.iloc[0].get("lastrate_call_pts", 0) or 0)
            else:
                auto_prem = float(match_row.iloc[0].get("lastrate_put_pts", 0) or 0)

        with add_cols[3]:
            st.markdown(
                f'<div style="padding:8px 0;text-align:center;color:{C_TEXT};font-size:13px;">'
                f'{fmt_num(auto_prem)} pts</div>',
                unsafe_allow_html=True,
            )

        with add_cols[4]:
            if st.button("➕ הוסף לגרף", key="chain_add_btn", use_container_width=True):
                st.session_state.arena_legs.append({
                    "type": add_type,
                    "action": add_action,
                    "strike": float(add_strike),
                    "premium_pts": auto_prem,
                    "qty": 1,
                })
                st.rerun()


# ==================================================================
# SECTION 4: PAYOFF CHART + METRICS
# ==================================================================
st.markdown('<div class="section-hdr">④ גרף תשואה בפקיעה</div>', unsafe_allow_html=True)

legs = st.session_state.arena_legs

if legs and any(l["premium_pts"] > 0 for l in legs):
    metrics = compute_strategy_metrics(legs, base)

    # Metrics strip
    net_prem = metrics["net_premium"]
    max_profit = metrics["max_profit"]
    max_loss = metrics["max_loss"]
    be_list = metrics["breakevens"]

    prem_color = "green" if net_prem > 0 else "red"
    profit_glow = "glow-green" if max_profit > 0 else ""
    loss_glow = "glow-red" if max_loss < 0 else ""

    be_str = " / ".join(fmt_num(b, 0) for b in be_list) if be_list else "—"

    st.markdown(
        f'<div class="metric-grid">'
        f'<div class="metric-card"><div class="label">Net Premium (pts)</div>'
        f'<div class="value {prem_color}">{fmt_num(net_prem)}</div></div>'
        f'<div class="metric-card {profit_glow}"><div class="label">Max Profit</div>'
        f'<div class="value green">{fmt_ils(max_profit)}</div></div>'
        f'<div class="metric-card {loss_glow}"><div class="label">Max Loss</div>'
        f'<div class="value red">{fmt_ils(max_loss)}</div></div>'
        f'<div class="metric-card"><div class="label">Breakeven(s)</div>'
        f'<div class="value white" style="font-size:18px;">{be_str}</div></div>'
        f'</div>',
        unsafe_allow_html=True,
    )

    # ── Payoff Chart ──
    all_strikes = [l["strike"] for l in legs]
    min_s, max_s = min(all_strikes), max(all_strikes)
    margin = max(100, (max_s - min_s) * 0.8)
    x_range = np.linspace(min_s - margin, max_s + margin, 600)
    y_pnl = compute_payoff(legs, x_range)

    fig = go.Figure()

    # Profit fill
    profit_y = np.where(y_pnl >= 0, y_pnl, 0)
    fig.add_trace(go.Scatter(
        x=x_range, y=profit_y, fill="tozeroy",
        fillcolor="rgba(38,222,129,0.45)", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))

    # Loss fill
    loss_y = np.where(y_pnl < 0, y_pnl, 0)
    fig.add_trace(go.Scatter(
        x=x_range, y=loss_y, fill="tozeroy",
        fillcolor="rgba(255,77,77,0.45)", line=dict(width=0),
        showlegend=False, hoverinfo="skip",
    ))

    # Main line
    fig.add_trace(go.Scatter(
        x=x_range, y=y_pnl, mode="lines",
        line=dict(color="rgba(255,255,255,0.4)", width=1.5),
        showlegend=False,
        hovertemplate="Index: %{x:,.0f}<br>P&L: %{y:,.0f} ₪<extra></extra>",
    ))

    # Zero line
    fig.add_hline(y=0, line=dict(color="rgba(255,255,255,0.15)", width=1))

    # Breakeven markers
    if be_list:
        fig.add_trace(go.Scatter(
            x=be_list, y=[0] * len(be_list), mode="markers+text",
            marker=dict(color=C_ORANGE, size=11, symbol="circle",
                        line=dict(color=C_BG, width=2)),
            text=[f"BE: {b:,.0f}" for b in be_list],
            textposition="top center",
            textfont=dict(size=11, color=C_ORANGE),
            showlegend=False,
            hovertemplate="Breakeven: %{x:,.0f}<extra></extra>",
        ))

    # Live index marker
    if live_index > 0:
        fig.add_vline(x=live_index, line=dict(color="#00BCD4", width=2, dash="dot"))
        fig.add_annotation(
            x=live_index, y=max(y_pnl) * 0.85,
            text=f"Live: {live_index:,.2f}",
            showarrow=False,
            font=dict(size=12, color="#00BCD4", family="Inter"),
            bgcolor="rgba(11,13,16,0.9)",
            bordercolor="#00BCD4", borderwidth=1, borderpad=5,
        )

    # Strike markers
    for leg in legs:
        color = C_GREEN if leg["action"] == "BUY" else C_RED
        label = f"{'B' if leg['action'] == 'BUY' else 'S'} {leg['type'][0]} {leg['strike']:,.0f}"
        fig.add_vline(x=leg["strike"], line=dict(color=color, width=1, dash="dash"))
        fig.add_annotation(
            x=leg["strike"], y=min(y_pnl) * 0.9,
            text=label, showarrow=False,
            font=dict(size=10, color=color),
            bgcolor="rgba(11,13,16,0.8)",
            borderpad=3,
        )

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=C_BG, plot_bgcolor=C_BG,
        height=420,
        margin=dict(l=55, r=30, t=25, b=50),
        xaxis=dict(
            title="TA-35 Index at Expiry",
            gridcolor="rgba(255,255,255,0.04)", zeroline=False,
            tickformat=",", tickfont=dict(size=10, color=C_DIM),
            title_font=dict(size=11, color=C_DIM),
        ),
        yaxis=dict(
            title="P&L (₪)",
            gridcolor="rgba(255,255,255,0.06)", zeroline=False,
            tickformat=",", tickfont=dict(size=10, color=C_DIM),
            title_font=dict(size=11, color=C_DIM),
        ),
        showlegend=False,
        hovermode="x unified",
    )

    st.plotly_chart(fig, use_container_width=True)

    # ── Legs Summary Table ──
    html = ('<div class="table-scroll"><table><thead><tr>'
            '<th>Leg</th><th>Action</th><th>Strike</th>'
            '<th>Premium (₪)</th><th>Qty</th><th>Cost/Credit (₪)</th>'
            '</tr></thead><tbody>')
    for leg in legs:
        css = "sell" if leg["action"] == "SELL" else "buy"
        prem_ils = leg["premium_pts"] * MULTIPLIER
        sign = -1 if leg["action"] == "BUY" else 1
        cost = sign * prem_ils * leg["qty"]
        cost_css = "buy" if cost > 0 else "sell"
        cost_label = f"+{cost:,.0f}" if cost > 0 else f"{cost:,.0f}"
        html += (
            f'<tr><td>{leg["type"]}</td>'
            f'<td class="{css}">{leg["action"]}</td>'
            f'<td><strong>{fmt_num(leg["strike"], 0)}</strong></td>'
            f'<td>{fmt_num(prem_ils, 0)}</td>'
            f'<td>{leg["qty"]}</td>'
            f'<td class="{cost_css}"><strong>{cost_label}</strong></td>'
            f'</tr>'
        )
    html += '</tbody></table></div>'
    st.markdown(html, unsafe_allow_html=True)

    # ── Execute Trade Button ──
    st.markdown("---")
    exec_cols = st.columns([1, 2, 1])
    with exec_cols[0]:
        trade_expiry = st.date_input(
            "📅 פקיעה לעסקה",
            value=date.today() + pd.Timedelta(days=2),
            key="trade_expiry_input",
        )
    with exec_cols[1]:
        strategy_label = st.session_state.arena_template or "custom"
        tpl_name = STRATEGY_TEMPLATES.get(strategy_label, {}).get("name", "Custom")
        st.markdown(
            f'<div style="padding:10px 0;text-align:center;">'
            f'<span style="color:{C_DIM};font-size:12px;">אסטרטגיה: </span>'
            f'<strong style="color:{C_TEXT};">{tpl_name}</strong>'
            f'<span style="color:{C_DIM};font-size:12px;"> | {len(legs)} רגליים</span>'
            f'</div>',
            unsafe_allow_html=True,
        )
    with exec_cols[2]:
        if st.button("🚀 בצע עסקת דמו", key="execute_trade_btn", use_container_width=True, type="primary"):
            trade_id = str(uuid.uuid4())[:12]
            trade_data = {
                "trade_id": trade_id,
                "strategy_name": tpl_name,
                "expiry_date": str(trade_expiry),
                "status": "open",
                "legs": legs,
                "entry_index": live_index if live_index > 0 else base,
                "net_premium_pts": round(net_prem, 4),
                "max_profit_ils": round(max_profit, 2),
                "max_risk_ils": round(abs(max_loss), 2),
            }
            ok = save_demo_trade(trade_data)
            if ok:
                st.success(f"✅ עסקה {trade_id} בוצעה! — {tpl_name} | פקיעה {trade_expiry}")
                # Clear legs after execution
                st.session_state.arena_legs = []
                st.session_state.arena_template = None
                st.cache_data.clear()
                st.rerun()
            else:
                st.error("❌ שגיאה בשמירת העסקה. נסה שוב.")

elif legs:
    st.warning("הזן פרמיות (Premium) לפחות לרגל אחת כדי לראות את הגרף.")
else:
    st.markdown(
        f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
        f'padding:60px 20px;text-align:center;margin:20px 0;">'
        f'<div style="font-size:48px;margin-bottom:12px;">📊</div>'
        f'<div style="color:{C_TEXT};font-size:18px;font-weight:700;">הגרף יופיע כאן</div>'
        f'<div style="color:{C_DIM};font-size:14px;margin-top:6px;">בחר אסטרטגיה או הוסף רגליים כדי להתחיל</div>'
        f'</div>',
        unsafe_allow_html=True,
    )


# ==================================================================
# SECTION 5: AUTO-SETTLEMENT CHECK
# ==================================================================
# Check if any open demo trades have expired
_open_trades_check = load_demo_trades("open")
_today_str = now_il.strftime("%Y-%m-%d")
_expired_trades = [t for t in _open_trades_check if t.get("expiry_date", "9999") < _today_str]

if _expired_trades:
    _bal = get_demo_balance()
    _settle_msgs = []
    for et in _expired_trades:
        et_id = et.get("trade_id", "?")
        et_name = et.get("strategy_name", "")
        et_expiry = et.get("expiry_date", "")
        et_entry = float(et.get("entry_index", 0))

        # Try to get actual settlement index from iron_condor_strategies
        settle_idx = 0.0
        try:
            s_url = (
                f"{SUPABASE_URL}/rest/v1/iron_condor_strategies"
                f"?select=actual_index_close"
                f"&expiry_date=eq.{et_expiry}"
                f"&actual_index_close=gt.0"
                f"&limit=1"
            )
            sr = httpx.get(s_url, headers=_supabase_headers(), timeout=10)
            if sr.status_code in (200, 206) and sr.json():
                settle_idx = float(sr.json()[0].get("actual_index_close", 0))
        except Exception:
            pass

        # If no settlement data, use live index or entry as fallback
        if settle_idx <= 0:
            settle_idx = live_index if live_index > 0 else et_entry

        final_pnl = compute_trade_pnl(et, settle_idx)
        close_demo_trade(et_id, settle_idx, final_pnl, "expiry_settlement")
        _bal += final_pnl
        update_demo_balance(_bal, final_pnl, f"expiry_settle_{et_id}")

        pnl_icon = "📈" if final_pnl >= 0 else "📉"
        _settle_msgs.append(
            f'{pnl_icon} <strong>{et_name}</strong> (#{et_id}) — פקיעה {et_expiry} | '
            f'מדד סטלמנט: <strong>{settle_idx:,.0f}</strong> | '
            f'P&L: <strong>{fmt_ils(final_pnl)}</strong>'
        )

    # Show settlement notification
    settle_lines = "<br>".join(_settle_msgs)
    st.markdown(
        f'<div style="background:rgba(255,214,0,0.08);border:1px solid rgba(255,214,0,0.3);'
        f'border-radius:12px;padding:18px 22px;margin:16px 0;direction:rtl;text-align:right;">'
        f'<div style="font-size:18px;font-weight:800;color:{C_YELLOW};margin-bottom:10px;">'
        f'⚠️ האופציות פקעו! — סטלמנט אוטומטי</div>'
        f'<div style="color:{C_TEXT};font-size:13px;line-height:1.8;">{settle_lines}</div>'
        f'<div style="color:{C_DIM};font-size:12px;margin-top:10px;">'
        f'יתרה מעודכנת: <strong style="color:{C_TEXT};">{_bal:,.0f} ₪</strong></div>'
        f'</div>',
        unsafe_allow_html=True,
    )
    st.cache_data.clear()


# ==================================================================
# SECTION 6: DEMO PORTFOLIO
# ==================================================================
st.markdown('<div class="section-hdr">⑥ תיק דמו — פוזיציות פתוחות</div>', unsafe_allow_html=True)

# Balance display
current_balance = get_demo_balance()
balance_color = "green" if current_balance >= 100000 else "red"
pnl_from_start = current_balance - 100000

open_trades = load_demo_trades("open")
closed_trades = load_demo_trades("closed")

# Portfolio summary strip
total_unrealized = 0.0
if open_trades and live_index > 0:
    for t in open_trades:
        total_unrealized += compute_trade_pnl(t, live_index)

unr_color = "green" if total_unrealized >= 0 else "red"
unr_glow = "glow-green" if total_unrealized >= 0 else "glow-red"

st.markdown(
    f'<div class="metric-grid">'
    f'<div class="metric-card"><div class="label">יתרת חשבון</div>'
    f'<div class="value {balance_color}">{current_balance:,.0f} ₪</div></div>'
    f'<div class="metric-card {unr_glow}"><div class="label">P&L לא ממומש</div>'
    f'<div class="value {unr_color}">{fmt_ils(total_unrealized)}</div></div>'
    f'<div class="metric-card"><div class="label">עסקאות פתוחות</div>'
    f'<div class="value blue">{len(open_trades)}</div></div>'
    f'<div class="metric-card"><div class="label">עסקאות סגורות</div>'
    f'<div class="value white">{len(closed_trades)}</div></div>'
    f'</div>',
    unsafe_allow_html=True,
)

if open_trades:
    for t in open_trades:
        t_id = t.get("trade_id", "?")
        t_name = t.get("strategy_name", "Custom")
        t_expiry = t.get("expiry_date", "")
        t_entry = float(t.get("entry_index", 0))
        t_legs = t.get("legs", [])
        if isinstance(t_legs, str):
            t_legs = json.loads(t_legs)
        t_net_prem = float(t.get("net_premium_pts", 0))
        t_max_profit = float(t.get("max_profit_ils", 0))

        # Compute unrealized P&L
        if live_index > 0:
            t_pnl = compute_trade_pnl(t, live_index)
        else:
            t_pnl = 0.0
        pnl_color = "green" if t_pnl >= 0 else "red"
        pnl_glow = "glow-green" if t_pnl >= 0 else "glow-red"

        # Trade card
        st.markdown(
            f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
            f'padding:16px 20px;margin:10px 0;">'
            f'<div style="display:flex;justify-content:space-between;align-items:center;flex-wrap:wrap;gap:10px;">'
            f'<div>'
            f'<span style="color:{C_TEXT};font-weight:700;font-size:15px;">{t_name}</span>'
            f'<span style="color:{C_DIM};font-size:12px;margin-left:10px;">#{t_id}</span>'
            f'</div>'
            f'<div style="display:flex;gap:20px;align-items:center;">'
            f'<span style="color:{C_DIM};font-size:12px;">פקיעה: <strong style="color:{C_TEXT};">{t_expiry}</strong></span>'
            f'<span style="color:{C_DIM};font-size:12px;">כניסה: <strong style="color:{C_YELLOW};">{t_entry:,.0f}</strong></span>'
            f'<span style="color:{C_DIM};font-size:12px;">רגליים: <strong style="color:{C_TEXT};">{len(t_legs)}</strong></span>'
            f'</div>'
            f'</div>'
            f'</div>',
            unsafe_allow_html=True,
        )

        # Legs detail + P&L per leg
        leg_html = (
            '<div class="table-scroll"><table><thead><tr>'
            '<th>Leg</th><th>Action</th><th>Strike</th>'
            '<th>Entry (₪)</th><th>Unrealized P&L</th>'
            '</tr></thead><tbody>'
        )
        for leg in t_legs:
            l_type = leg.get("type", "")
            l_action = leg.get("action", "")
            l_strike = float(leg.get("strike", 0))
            l_prem = float(leg.get("premium_pts", 0))
            l_qty = int(leg.get("qty", 1))
            l_sign = 1 if l_action == "BUY" else -1

            if live_index > 0:
                if l_type == "Call":
                    intrinsic = max(live_index - l_strike, 0)
                else:
                    intrinsic = max(l_strike - live_index, 0)
                leg_pnl = l_sign * (intrinsic - l_prem) * MULTIPLIER * l_qty
            else:
                leg_pnl = 0.0

            css = "sell" if l_action == "SELL" else "buy"
            pnl_css = "buy" if leg_pnl >= 0 else "sell"
            entry_ils = l_prem * MULTIPLIER

            leg_html += (
                f'<tr>'
                f'<td>{l_type}</td>'
                f'<td class="{css}">{l_action}</td>'
                f'<td><strong>{l_strike:,.0f}</strong></td>'
                f'<td>{entry_ils:,.0f}</td>'
                f'<td class="{pnl_css}"><strong>{fmt_ils(leg_pnl)}</strong></td>'
                f'</tr>'
            )
        leg_html += '</tbody></table></div>'
        st.markdown(leg_html, unsafe_allow_html=True)

        # P&L summary + close button
        pnl_cols = st.columns([2, 1])
        with pnl_cols[0]:
            st.markdown(
                f'<div class="metric-grid">'
                f'<div class="metric-card {pnl_glow}"><div class="label">P&L לא ממומש</div>'
                f'<div class="value {pnl_color}">{fmt_ils(t_pnl)}</div></div>'
                f'<div class="metric-card"><div class="label">Max Profit</div>'
                f'<div class="value blue">{fmt_ils(t_max_profit)}</div></div>'
                f'</div>',
                unsafe_allow_html=True,
            )
        with pnl_cols[1]:
            if st.button(f"🔒 סגור עסקה #{t_id}", key=f"close_{t_id}", use_container_width=True):
                settle_idx = live_index if live_index > 0 else t_entry
                final_pnl = compute_trade_pnl(t, settle_idx)
                close_demo_trade(t_id, settle_idx, final_pnl, "manual_close")
                new_bal = current_balance + final_pnl
                update_demo_balance(new_bal, final_pnl, f"close_trade_{t_id}")
                st.cache_data.clear()
                st.rerun()

        st.markdown("---")

else:
    st.markdown(
        f'<div style="background:{C_CARD};border:1px solid {C_BORDER};border-radius:12px;'
        f'padding:40px 20px;text-align:center;margin:12px 0;">'
        f'<div style="font-size:36px;margin-bottom:8px;">💼</div>'
        f'<div style="color:{C_TEXT};font-size:16px;font-weight:700;">אין פוזיציות פתוחות</div>'
        f'<div style="color:{C_DIM};font-size:13px;margin-top:4px;">בנה אסטרטגיה למעלה ולחץ "בצע עסקת דמו"</div>'
        f'</div>',
        unsafe_allow_html=True,
    )

# ── Closed trades summary ──
if closed_trades:
    st.markdown('<div class="section-hdr">📜 עסקאות סגורות</div>', unsafe_allow_html=True)

    closed_html = (
        '<div class="table-scroll"><table><thead><tr>'
        '<th>ID</th><th>Strategy</th><th>Expiry</th>'
        '<th>Entry Index</th><th>Settlement</th><th>P&L</th><th>Reason</th>'
        '</tr></thead><tbody>'
    )
    total_realized = 0.0
    for ct in closed_trades:
        ct_id = ct.get("trade_id", "?")
        ct_name = ct.get("strategy_name", "")
        ct_expiry = ct.get("expiry_date", "")
        ct_entry = float(ct.get("entry_index", 0))
        ct_settle = float(ct.get("settlement_index", 0))
        ct_pnl = float(ct.get("pnl_ils", 0))
        ct_reason = ct.get("close_reason", "")
        total_realized += ct_pnl

        pnl_css = "buy" if ct_pnl >= 0 else "sell"
        reason_label = "פקיעה" if "expiry" in ct_reason else "ידני"

        closed_html += (
            f'<tr>'
            f'<td>{ct_id}</td>'
            f'<td>{ct_name}</td>'
            f'<td>{ct_expiry}</td>'
            f'<td>{ct_entry:,.0f}</td>'
            f'<td>{ct_settle:,.0f}</td>'
            f'<td class="{pnl_css}"><strong>{fmt_ils(ct_pnl)}</strong></td>'
            f'<td>{reason_label}</td>'
            f'</tr>'
        )
    closed_html += '</tbody></table></div>'
    st.markdown(closed_html, unsafe_allow_html=True)

    real_color = "green" if total_realized >= 0 else "red"
    st.markdown(
        f'<div style="text-align:center;padding:10px;color:{C_DIM};font-size:13px;">'
        f'סה"כ ממומש: <strong style="color:{"#00E676" if total_realized >= 0 else "#FF1744"};">'
        f'{fmt_ils(total_realized)}</strong></div>',
        unsafe_allow_html=True,
    )


# ==================================================================
# FOOTER
# ==================================================================
st.markdown(f"""
<div style="text-align:center; padding:30px 0 10px; color:{C_DIM}; font-size:11px;">
    Paper Trading Arena &mdash; Demo Only, No Real Money<br>
    TA-35 Mini &nbsp;|&nbsp; Multiplier: {MULTIPLIER}₪/pt
    &nbsp;|&nbsp; {now_il.strftime("%H:%M:%S")} IL
</div>
""", unsafe_allow_html=True)
