"""
TASE TA-35 — Options Playground
================================
Interactive Options Chain, Strategy Templates,
and Payoff Visualization.
Reads live data from Supabase (read-only).
"""

import os
import streamlit as st
import pandas as pd
import numpy as np
import httpx
import plotly.graph_objects as go
from datetime import datetime
from zoneinfo import ZoneInfo

# ==================================================================
# CONFIG
# ==================================================================
st.set_page_config(page_title="TA-35 Playground", page_icon="◆",
                   layout="wide")

SUPABASE_URL = os.environ.get("SUPABASE_URL", "").rstrip("/")
SUPABASE_KEY = os.environ.get("SUPABASE_KEY", "")
TZ = ZoneInfo("Asia/Jerusalem")
MULTIPLIER = 50

# Palette
C_BG      = "#0B0D10"
C_CARD    = "#151921"
C_BORDER  = "#1E2433"
C_TEXT    = "#E8EAED"
C_DIM     = "#6B7B8D"
C_GREEN   = "#00E676"
C_RED     = "#FF1744"
C_BLUE    = "#00B0FF"
C_YELLOW  = "#FFD600"
C_GRID    = "#1A1F2B"
C_BUY_BG  = "rgba(0,230,118,0.10)"
C_SELL_BG = "rgba(255,23,68,0.10)"

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

/* KPI row */
.kpi-row {{
    display: flex; gap: 14px;
    margin-bottom: 18px; flex-wrap: wrap;
}}
.kpi {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 14px 18px;
    flex: 1; min-width: 160px;
    position: relative; overflow: hidden;
}}
.kpi::after {{
    content: '';
    position: absolute; top: 0; right: 0;
    width: 4px; height: 100%;
    border-radius: 0 10px 10px 0;
}}
.kpi.g::after {{ background: {C_GREEN}; }}
.kpi.r::after {{ background: {C_RED}; }}
.kpi.b::after {{ background: {C_BLUE}; }}
.kpi.y::after {{ background: {C_YELLOW}; }}
.kpi .lb {{
    font-size: 10px; font-weight: 700;
    color: {C_DIM}; text-transform: uppercase;
    letter-spacing: 0.8px; margin-bottom: 3px;
}}
.kpi .vl {{
    font-size: 22px; font-weight: 700;
    color: {C_TEXT};
    direction: ltr; unicode-bidi: isolate;
}}
.kpi .sb {{
    font-size: 10px; color: {C_DIM};
    margin-top: 2px; direction: ltr;
    unicode-bidi: isolate;
}}

/* Chain grid */
.chain-table {{
    width: 100%;
    border-collapse: separate;
    border-spacing: 0;
    font-size: 13px;
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    overflow: hidden;
}}
.chain-table th {{
    background: {C_CARD};
    color: {C_DIM};
    font-size: 10px;
    font-weight: 700;
    text-transform: uppercase;
    letter-spacing: 0.8px;
    padding: 10px 8px;
    border-bottom: 1px solid {C_BORDER};
}}
.chain-table td {{
    padding: 6px 8px;
    border-bottom: 1px solid {C_BORDER};
    color: {C_TEXT};
    vertical-align: middle;
}}
.chain-table tr:last-child td {{
    border-bottom: none;
}}
.chain-table .strike-cell {{
    font-weight: 800;
    font-size: 15px;
    text-align: center;
    background: {C_CARD};
    color: {C_BLUE};
    min-width: 80px;
    border-left: 1px solid {C_BORDER};
    border-right: 1px solid {C_BORDER};
}}
.chain-table .call-side {{
    text-align: center;
}}
.chain-table .put-side {{
    text-align: center;
}}
.chain-table .price-cell {{
    font-weight: 600;
    font-family: 'JetBrains Mono', monospace;
    font-size: 13px;
    direction: ltr;
    unicode-bidi: isolate;
}}
.chain-table .atm-row td {{
    border-top: 2px solid {C_BLUE} !important;
    border-bottom: 2px solid {C_BLUE} !important;
}}
.chain-table .atm-row .strike-cell {{
    color: {C_YELLOW};
    font-size: 16px;
}}
.chain-table .itm {{
    background: rgba(0,176,255,0.04);
}}

/* Highlight rows with selected legs */
.chain-table .row-buy td {{
    background: {C_BUY_BG} !important;
}}
.chain-table .row-sell td {{
    background: {C_SELL_BG} !important;
}}
.chain-table .row-both td {{
    background: linear-gradient(90deg, {C_BUY_BG}, {C_SELL_BG}) !important;
}}

/* Ticket panel */
.ticket {{
    background: {C_CARD};
    border: 1px solid {C_BORDER};
    border-radius: 10px;
    padding: 16px 20px;
    margin-top: 16px;
}}
.ticket-title {{
    font-size: 14px; font-weight: 700;
    color: {C_TEXT}; margin-bottom: 12px;
    display: flex; align-items: center; gap: 8px;
}}
.leg-row {{
    display: flex; align-items: center; gap: 10px;
    padding: 8px 12px;
    border-radius: 6px;
    margin-bottom: 6px;
    font-size: 13px;
    color: {C_TEXT};
}}
.leg-row.buy {{ background: {C_BUY_BG}; border: 1px solid rgba(0,230,118,0.2); }}
.leg-row.sell {{ background: {C_SELL_BG}; border: 1px solid rgba(255,23,68,0.2); }}
.leg-badge {{
    font-size: 10px; font-weight: 800;
    padding: 2px 8px; border-radius: 4px;
    letter-spacing: 0.5px;
}}
.leg-badge.buy {{
    background: rgba(0,230,118,0.15); color: {C_GREEN};
    border: 1px solid rgba(0,230,118,0.3);
}}
.leg-badge.sell {{
    background: rgba(255,23,68,0.15); color: {C_RED};
    border: 1px solid rgba(255,23,68,0.3);
}}
.leg-detail {{
    flex: 1; font-weight: 600;
    direction: ltr; unicode-bidi: isolate;
}}
.leg-premium {{
    font-family: 'JetBrains Mono', monospace;
    font-size: 12px; color: {C_DIM};
    direction: ltr; unicode-bidi: isolate;
}}

/* Buttons override */
.stButton > button {{
    background: {C_CARD} !important;
    color: {C_DIM} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 6px !important;
    font-weight: 600 !important;
    font-size: 12px !important;
    transition: all 0.15s !important;
    width: 100%;
}}
.stButton > button:hover {{
    background: {C_BORDER} !important;
    color: {C_TEXT} !important;
    border-color: {C_BLUE} !important;
}}

/* Expiry selector */
.stRadio > div {{
    display: flex; gap: 8px; flex-wrap: wrap;
}}
.stRadio > div > label {{
    background: {C_CARD} !important;
    border: 1px solid {C_BORDER} !important;
    border-radius: 8px !important;
    padding: 6px 14px !important;
    font-size: 12px !important;
    font-weight: 600 !important;
    color: {C_DIM} !important;
}}
.stRadio > div > label[data-checked="true"] {{
    border-color: {C_BLUE} !important;
    color: {C_BLUE} !important;
}}

hr {{ border-color: {C_BORDER} !important; opacity: 0.3 !important; }}
</style>
""", unsafe_allow_html=True)


# ==================================================================
# DATA LAYER (read-only)
# ==================================================================
def _hdr():
    return {"apikey": SUPABASE_KEY,
            "Authorization": f"Bearer {SUPABASE_KEY}",
            "Content-Type": "application/json"}


@st.cache_data(ttl=45)
def load_options_chain() -> pd.DataFrame:
    """Fetch all rows from tase_putcall (live table). Read-only."""
    if not SUPABASE_URL or not SUPABASE_KEY:
        return pd.DataFrame()
    all_rows = []
    batch = 1000
    offset = 0
    try:
        while True:
            url = (f"{SUPABASE_URL}/rest/v1/tase_putcall"
                   f"?select=*&order=id&limit={batch}&offset={offset}")
            r = httpx.get(url, headers=_hdr(), timeout=15)
            if r.status_code not in (200, 206):
                break
            chunk = r.json()
            if not chunk:
                break
            all_rows.extend(chunk)
            if len(chunk) < batch:
                break
            offset += batch
    except Exception:
        pass
    if not all_rows:
        return pd.DataFrame()
    return pd.DataFrame(all_rows)


def N(val):
    """Safe numeric conversion."""
    if val is None or val == "":
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", ""))
    except (ValueError, TypeError):
        return 0.0


def get_index_value(df: pd.DataFrame) -> float:
    """Extract TA-35 index from the data."""
    if df.empty:
        return 0.0
    for col in ("underlingasset_call", "underlingasset_put"):
        if col in df.columns:
            vals = df[col].dropna()
            for v in vals:
                n = N(v)
                if n > 100:
                    return n
    return 0.0


def build_chain(df: pd.DataFrame, expiry: str) -> pd.DataFrame:
    """
    Build a clean options chain for one expiry date.
    Returns a DataFrame sorted by strike with call/put columns.
    """
    if df.empty:
        return pd.DataFrame()

    exp_df = df[df["expiry_date"] == expiry].copy()
    if exp_df.empty:
        return pd.DataFrame()

    rows = []
    for _, r in exp_df.iterrows():
        strike_call = N(r.get("expirationprice_call"))
        strike_put = N(r.get("expirationprice_put"))
        strike = strike_call if strike_call > 0 else strike_put
        if strike <= 0:
            continue

        rows.append({
            "strike":      strike,
            "call_price":  N(r.get("lastrate_call")),
            "call_bid":    N(r.get("baserate_call")),
            "call_delta":  N(r.get("delta_call")),
            "call_volume": N(r.get("overallturnoverunits_call")),
            "call_oi":     N(r.get("openpositions_call")),
            "call_id":     r.get("derivativeid_call", ""),
            "put_price":   N(r.get("lastrate_put")),
            "put_bid":     N(r.get("baserate_put")),
            "put_delta":   N(r.get("delta_put")),
            "put_volume":  N(r.get("overallturnoverunits_put")),
            "put_oi":      N(r.get("openpositions_put")),
            "put_id":      r.get("derivativeid_put", ""),
        })

    if not rows:
        return pd.DataFrame()

    chain = pd.DataFrame(rows)
    # Aggregate duplicates (same strike)
    chain = chain.groupby("strike", as_index=False).first()
    chain = chain.sort_values("strike").reset_index(drop=True)
    return chain


# ==================================================================
# SESSION STATE INIT
# ==================================================================
if "current_strategy" not in st.session_state:
    st.session_state.current_strategy = []  # list of leg dicts


def add_leg(strike: float, option_type: str, action: str,
            premium: float, opt_id: str = ""):
    """Toggle a leg in/out of the current strategy."""
    legs = st.session_state.current_strategy
    # Check if this exact leg already exists → remove it
    for i, leg in enumerate(legs):
        if (leg["strike"] == strike
                and leg["type"] == option_type
                and leg["action"] == action):
            legs.pop(i)
            return
    # Add new leg
    legs.append({
        "strike":   strike,
        "type":     option_type,   # "Call" / "Put"
        "action":   action,        # "BUY" / "SELL"
        "premium":  premium,
        "quantity": 1,
        "id":       opt_id,
    })


def remove_leg(idx: int):
    legs = st.session_state.current_strategy
    if 0 <= idx < len(legs):
        legs.pop(idx)


def clear_legs():
    st.session_state.current_strategy = []


def _find_strike(chain_df: pd.DataFrame, target: float,
                  exclude: set | None = None) -> dict:
    """Find the closest strike in chain to target, optionally excluding."""
    if chain_df.empty:
        return {"strike": target, "call_price": 0, "put_price": 0,
                "call_id": "", "put_id": ""}
    if exclude is None:
        exclude = set()
    filtered = chain_df[~chain_df["strike"].isin(exclude)]
    if filtered.empty:
        filtered = chain_df
    idx = (filtered["strike"] - target).abs().idxmin()
    row = filtered.loc[idx]
    return row.to_dict()


def inject_iron_condor(chain_df: pd.DataFrame, spot: float):
    """Inject a standard Iron Condor: Sell ±1.5%, Buy ±3%."""
    clear_legs()
    offset_short = spot * 0.015
    offset_long = spot * 0.030

    sp = _find_strike(chain_df, spot - offset_short)
    sc = _find_strike(chain_df, spot + offset_short,
                      exclude={sp["strike"]})
    lp = _find_strike(chain_df, spot - offset_long,
                      exclude={sp["strike"], sc["strike"]})
    lc = _find_strike(chain_df, spot + offset_long,
                      exclude={sp["strike"], sc["strike"], lp["strike"]})

    legs = st.session_state.current_strategy
    legs.append({"strike": sp["strike"], "type": "Put", "action": "SELL",
                 "premium": sp["put_price"], "quantity": 1,
                 "id": sp.get("put_id", "")})
    legs.append({"strike": lp["strike"], "type": "Put", "action": "BUY",
                 "premium": lp["put_price"], "quantity": 1,
                 "id": lp.get("put_id", "")})
    legs.append({"strike": sc["strike"], "type": "Call", "action": "SELL",
                 "premium": sc["call_price"], "quantity": 1,
                 "id": sc.get("call_id", "")})
    legs.append({"strike": lc["strike"], "type": "Call", "action": "BUY",
                 "premium": lc["call_price"], "quantity": 1,
                 "id": lc.get("call_id", "")})


def inject_long_straddle(chain_df: pd.DataFrame, spot: float):
    """Inject Long Straddle: Buy ATM Call + Buy ATM Put."""
    clear_legs()
    atm = _find_strike(chain_df, spot)
    legs = st.session_state.current_strategy
    legs.append({"strike": atm["strike"], "type": "Call", "action": "BUY",
                 "premium": atm["call_price"], "quantity": 1,
                 "id": atm.get("call_id", "")})
    legs.append({"strike": atm["strike"], "type": "Put", "action": "BUY",
                 "premium": atm["put_price"], "quantity": 1,
                 "id": atm.get("put_id", "")})


def inject_bull_spread(chain_df: pd.DataFrame, spot: float):
    """Inject Bull Call Spread: Buy ATM Call + Sell OTM Call."""
    clear_legs()
    atm = _find_strike(chain_df, spot)
    otm = _find_strike(chain_df, spot + spot * 0.02,
                       exclude={atm["strike"]})
    legs = st.session_state.current_strategy
    legs.append({"strike": atm["strike"], "type": "Call", "action": "BUY",
                 "premium": atm["call_price"], "quantity": 1,
                 "id": atm.get("call_id", "")})
    legs.append({"strike": otm["strike"], "type": "Call", "action": "SELL",
                 "premium": otm["call_price"], "quantity": 1,
                 "id": otm.get("call_id", "")})


# ------------------------------------------------------------------
# Payoff calculation engine
# ------------------------------------------------------------------
def calculate_payoff(legs: list, price_range: np.ndarray) -> np.ndarray:
    """
    Calculate aggregate expiry P&L across a spectrum of prices.
    Returns P&L in ₪ for each price point.
    """
    total = np.zeros_like(price_range, dtype=float)
    for leg in legs:
        s = leg["strike"]
        p = leg["premium"]
        q = leg["quantity"]

        if leg["type"] == "Call":
            intrinsic = np.maximum(price_range - s, 0)
        else:
            intrinsic = np.maximum(s - price_range, 0)

        if leg["action"] == "BUY":
            leg_pnl = (intrinsic - p) * q * MULTIPLIER
        else:
            leg_pnl = (p - intrinsic) * q * MULTIPLIER

        total += leg_pnl
    return total


def _leg_exists(strike: float, option_type: str, action: str) -> bool:
    for leg in st.session_state.current_strategy:
        if (leg["strike"] == strike
                and leg["type"] == option_type
                and leg["action"] == action):
            return True
    return False


def _strike_status(strike: float) -> str:
    """Return highlight class for a strike row: buy / sell / both / ''."""
    has_buy = False
    has_sell = False
    for leg in st.session_state.current_strategy:
        if leg["strike"] == strike:
            if leg["action"] == "BUY":
                has_buy = True
            else:
                has_sell = True
    if has_buy and has_sell:
        return "row-both"
    if has_buy:
        return "row-buy"
    if has_sell:
        return "row-sell"
    return ""


# ==================================================================
# HEADER
# ==================================================================
now = datetime.now(TZ)
st.markdown(f"""
<div style="display:flex;align-items:center;justify-content:space-between;
            margin-bottom:4px;">
    <div>
        <span style="font-size:10px;font-weight:800;letter-spacing:3px;
                      color:{C_BLUE};">TA-35 OPTIONS</span>
        <div style="font-size:22px;font-weight:800;color:{C_TEXT};
                    margin-top:2px;">
            🏗️ Options Playground
        </div>
    </div>
    <div style="text-align:left;color:{C_DIM};font-size:12px;">
        {now.strftime("%H:%M:%S")} IL
        <span style="display:inline-block;width:7px;height:7px;
                      border-radius:50%;margin-right:5px;
                      background:{C_GREEN};
                      box-shadow:0 0 6px {C_GREEN};
                      vertical-align:middle;"></span>
    </div>
</div>
""", unsafe_allow_html=True)

st.markdown("<hr>", unsafe_allow_html=True)


# ==================================================================
# LOAD DATA
# ==================================================================
raw_df = load_options_chain()

if raw_df.empty:
    st.warning("⚠️ No data available — check Supabase connection or wait for next pipeline cycle.")
    st.stop()

index_value = get_index_value(raw_df)

# Get available expiry dates
expiries = sorted(raw_df["expiry_date"].dropna().unique().tolist())
if not expiries:
    st.warning("⚠️ No expiry dates found in data.")
    st.stop()

# Fetch time info
fetch_time = ""
if "fetch_time" in raw_df.columns:
    fetch_time = raw_df["fetch_time"].dropna().iloc[-1] if not raw_df["fetch_time"].dropna().empty else ""
fetch_date = ""
if "fetch_date" in raw_df.columns:
    fetch_date = raw_df["fetch_date"].dropna().iloc[-1] if not raw_df["fetch_date"].dropna().empty else ""


# ==================================================================
# KPI ROW
# ==================================================================
st.markdown(f"""
<div class="kpi-row">
    <div class="kpi b">
        <div class="lb">TA-35 Index</div>
        <div class="vl">{index_value:,.2f}</div>
        <div class="sb">Live</div>
    </div>
    <div class="kpi y">
        <div class="lb">Expiries</div>
        <div class="vl">{len(expiries)}</div>
        <div class="sb">Available</div>
    </div>
    <div class="kpi g">
        <div class="lb">Options Rows</div>
        <div class="vl">{len(raw_df):,}</div>
        <div class="sb">{fetch_date} {fetch_time}</div>
    </div>
    <div class="kpi r">
        <div class="lb">Strategy Legs</div>
        <div class="vl">{len(st.session_state.current_strategy)}</div>
        <div class="sb">Selected</div>
    </div>
</div>
""", unsafe_allow_html=True)


# ==================================================================
# EXPIRY SELECTOR
# ==================================================================
st.markdown(f"""
<div style="font-size:13px;font-weight:700;color:{C_TEXT};margin-bottom:6px;">
    📅 Expiry Date
</div>
""", unsafe_allow_html=True)

selected_expiry = st.radio(
    "expiry", expiries,
    format_func=lambda e: f"{e}",
    horizontal=True,
    label_visibility="collapsed",
)

chain = build_chain(raw_df, selected_expiry)

if chain.empty:
    st.info("No options data for this expiry.")
    st.stop()


# ==================================================================
# STRATEGY TEMPLATES
# ==================================================================
st.markdown(f"""
<div style="font-size:13px;font-weight:700;color:{C_TEXT};
            margin:12px 0 8px;display:flex;align-items:center;gap:8px;">
    🎯 Strategy Templates
    <span style="font-size:10px;color:{C_DIM};font-weight:500;">
        Quick-load a preset strategy
    </span>
</div>
""", unsafe_allow_html=True)

tcols = st.columns(4)
with tcols[0]:
    if st.button("🦅 Iron Condor", key="tpl_ic", use_container_width=True):
        inject_iron_condor(chain, index_value)
        st.rerun()
with tcols[1]:
    if st.button("🔀 Long Straddle", key="tpl_ls", use_container_width=True):
        inject_long_straddle(chain, index_value)
        st.rerun()
with tcols[2]:
    if st.button("📈 Bull Vertical", key="tpl_bv", use_container_width=True):
        inject_bull_spread(chain, index_value)
        st.rerun()
with tcols[3]:
    if st.button("🗑️ ניקוי לוח תכנון", key="tpl_clear", use_container_width=True):
        clear_legs()
        st.rerun()


# ==================================================================
# OPTIONS CHAIN GRID
# ==================================================================
st.markdown(f"""
<div style="font-size:13px;font-weight:700;color:{C_TEXT};
            margin:16px 0 10px;display:flex;align-items:center;gap:8px;">
    📊 Options Chain
    <span style="font-size:10px;color:{C_DIM};font-weight:500;">
        {len(chain)} strikes · {selected_expiry}
    </span>
</div>
""", unsafe_allow_html=True)

# Find ATM strike (closest to index)
atm_strike = 0.0
if index_value > 0 and not chain.empty:
    atm_strike = chain.loc[
        (chain["strike"] - index_value).abs().idxmin(), "strike"
    ]

# Build the chain using Streamlit columns for button interactivity
# Header
hdr_cols = st.columns([1.2, 1, 1, 1, 1.5, 1, 1, 1, 1.2])
headers = ["מכור CALL", "קנה CALL", "OI", "פרמיה CALL",
           "STRIKE",
           "פרמיה PUT", "OI", "קנה PUT", "מכור PUT"]
for col, h in zip(hdr_cols, headers):
    col.markdown(
        f"<div style='text-align:center;font-size:10px;font-weight:700;"
        f"color:{C_DIM};text-transform:uppercase;letter-spacing:0.5px;"
        f"padding:4px 0;'>{h}</div>",
        unsafe_allow_html=True,
    )

st.markdown(
    f"<hr style='margin:0 0 2px 0;border-color:{C_BORDER};opacity:0.5;'>",
    unsafe_allow_html=True,
)

# Rows
for idx, row in chain.iterrows():
    strike = row["strike"]
    call_price = row["call_price"]
    put_price = row["put_price"]
    call_oi = int(row["call_oi"]) if row["call_oi"] > 0 else ""
    put_oi = int(row["put_oi"]) if row["put_oi"] > 0 else ""
    is_atm = (strike == atm_strike)
    is_itm_call = (index_value > 0 and strike < index_value)
    is_itm_put = (index_value > 0 and strike > index_value)

    # Check highlight status
    row_class = _strike_status(strike)

    # Row background color
    if row_class == "row-buy":
        row_bg = C_BUY_BG
    elif row_class == "row-sell":
        row_bg = C_SELL_BG
    elif row_class == "row-both":
        row_bg = "rgba(224,64,251,0.08)"
    elif is_atm:
        row_bg = "rgba(0,176,255,0.08)"
    else:
        row_bg = "transparent"

    # Container with background
    container = st.container()
    with container:
        cols = st.columns([1.2, 1, 1, 1, 1.5, 1, 1, 1, 1.2])

        # SELL CALL button
        sell_call_key = f"sc_{strike}_{selected_expiry}"
        active_sc = _leg_exists(strike, "Call", "SELL")
        with cols[0]:
            if st.button(
                "✓ מכור" if active_sc else "מכור",
                key=sell_call_key,
                type="primary" if active_sc else "secondary",
            ):
                add_leg(strike, "Call", "SELL", call_price,
                        row.get("call_id", ""))
                st.rerun()

        # BUY CALL button
        buy_call_key = f"bc_{strike}_{selected_expiry}"
        active_bc = _leg_exists(strike, "Call", "BUY")
        with cols[1]:
            if st.button(
                "✓ קנה" if active_bc else "קנה",
                key=buy_call_key,
                type="primary" if active_bc else "secondary",
            ):
                add_leg(strike, "Call", "BUY", call_price,
                        row.get("call_id", ""))
                st.rerun()

        # Call OI
        with cols[2]:
            st.markdown(
                f"<div style='text-align:center;color:{C_DIM};"
                f"font-size:11px;padding-top:6px;'>"
                f"{call_oi}</div>",
                unsafe_allow_html=True,
            )

        # Call Premium
        call_color = C_TEXT if call_price > 0 else C_DIM
        with cols[3]:
            st.markdown(
                f"<div style='text-align:center;font-weight:600;"
                f"font-family:monospace;font-size:13px;"
                f"color:{call_color};padding-top:5px;'>"
                f"{call_price:.2f}" if call_price > 0 else
                f"<div style='text-align:center;color:{C_DIM};"
                f"font-size:12px;padding-top:5px;'>—</div>",
                unsafe_allow_html=True,
            )

        # STRIKE (center)
        strike_color = C_YELLOW if is_atm else C_BLUE
        strike_size = "16px" if is_atm else "14px"
        atm_label = " ◄ ATM" if is_atm else ""
        with cols[4]:
            st.markdown(
                f"<div style='text-align:center;font-weight:800;"
                f"font-size:{strike_size};color:{strike_color};"
                f"padding-top:3px;'>"
                f"{strike:,.0f}"
                f"<span style='font-size:9px;color:{C_DIM};"
                f"margin-right:4px;'>{atm_label}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Put Premium
        put_color = C_TEXT if put_price > 0 else C_DIM
        with cols[5]:
            st.markdown(
                f"<div style='text-align:center;font-weight:600;"
                f"font-family:monospace;font-size:13px;"
                f"color:{put_color};padding-top:5px;'>"
                f"{put_price:.2f}" if put_price > 0 else
                f"<div style='text-align:center;color:{C_DIM};"
                f"font-size:12px;padding-top:5px;'>—</div>",
                unsafe_allow_html=True,
            )

        # Put OI
        with cols[6]:
            st.markdown(
                f"<div style='text-align:center;color:{C_DIM};"
                f"font-size:11px;padding-top:6px;'>"
                f"{put_oi}</div>",
                unsafe_allow_html=True,
            )

        # BUY PUT button
        buy_put_key = f"bp_{strike}_{selected_expiry}"
        active_bp = _leg_exists(strike, "Put", "BUY")
        with cols[7]:
            if st.button(
                "✓ קנה" if active_bp else "קנה",
                key=buy_put_key,
                type="primary" if active_bp else "secondary",
            ):
                add_leg(strike, "Put", "BUY", put_price,
                        row.get("put_id", ""))
                st.rerun()

        # SELL PUT button
        sell_put_key = f"sp_{strike}_{selected_expiry}"
        active_sp = _leg_exists(strike, "Put", "SELL")
        with cols[8]:
            if st.button(
                "✓ מכור" if active_sp else "מכור",
                key=sell_put_key,
                type="primary" if active_sp else "secondary",
            ):
                add_leg(strike, "Put", "SELL", put_price,
                        row.get("put_id", ""))
                st.rerun()

    # ATM separator line
    if is_atm:
        st.markdown(
            f"<hr style='margin:0;border-color:{C_BLUE};opacity:0.4;'>",
            unsafe_allow_html=True,
        )


# ==================================================================
# CURRENT SELECTION TICKET
# ==================================================================
st.markdown("<hr>", unsafe_allow_html=True)

legs = st.session_state.current_strategy

st.markdown(f"""
<div style="font-size:14px;font-weight:700;color:{C_TEXT};
            margin-bottom:10px;display:flex;align-items:center;gap:8px;">
    📝 לוח השרטוט שלך
    <span style="font-size:11px;color:{C_DIM};font-weight:500;">
        {len(legs)} {"רגל" if len(legs) == 1 else "רגליים"} נבחרו
    </span>
</div>
""", unsafe_allow_html=True)

if not legs:
    st.markdown(f"""
    <div style="background:{C_CARD};border:1px solid {C_BORDER};
                border-radius:10px;padding:30px;text-align:center;">
        <div style="font-size:32px;margin-bottom:8px;">🎯</div>
        <div style="color:{C_DIM};font-size:13px;">
            לחץ על <strong>קנה</strong> או <strong>מכור</strong>
            בשרשרת למעלה כדי להוסיף רגליים לאסטרטגיה
        </div>
    </div>
    """, unsafe_allow_html=True)

else:
    # Summary metrics
    total_premium = 0.0
    for leg in legs:
        p = leg["premium"] * leg["quantity"]
        if leg["action"] == "SELL":
            total_premium += p
        else:
            total_premium -= p

    total_cost = total_premium * MULTIPLIER
    cost_color = C_GREEN if total_premium >= 0 else C_RED
    cost_label = "קרדיט נטו" if total_premium >= 0 else "דביט נטו"

    st.markdown(f"""
    <div class="kpi-row">
        <div class="kpi {'g' if total_premium >= 0 else 'r'}">
            <div class="lb">{cost_label}</div>
            <div class="vl" style="color:{cost_color};">
                {abs(total_premium):,.2f} נק׳
            </div>
            <div class="sb">{abs(total_cost):,.0f} ₪ (×{MULTIPLIER})</div>
        </div>
        <div class="kpi b">
            <div class="lb">Legs</div>
            <div class="vl">{len(legs)}</div>
            <div class="sb">
                {sum(1 for l in legs if l['action']=='BUY')} Buy ·
                {sum(1 for l in legs if l['action']=='SELL')} Sell
            </div>
        </div>
    </div>
    """, unsafe_allow_html=True)

    # Leg rows
    for i, leg in enumerate(legs):
        action_he = "קנה" if leg["action"] == "BUY" else "מכור"
        action_cls = "buy" if leg["action"] == "BUY" else "sell"
        badge_color = C_GREEN if leg["action"] == "BUY" else C_RED

        leg_cols = st.columns([0.8, 3, 1.5, 1, 0.8])

        # Action badge
        with leg_cols[0]:
            st.markdown(
                f"<div style='padding-top:5px;'>"
                f"<span class='leg-badge {action_cls}'>"
                f"{action_he}</span></div>",
                unsafe_allow_html=True,
            )

        # Leg detail
        with leg_cols[1]:
            st.markdown(
                f"<div style='font-weight:600;color:{C_TEXT};"
                f"font-size:13px;padding-top:6px;'>"
                f"{leg['type']} @ {leg['strike']:,.0f}"
                f"<span style='color:{C_DIM};font-size:11px;"
                f"margin-right:8px;'>"
                f"פרמיה: {leg['premium']:.2f}</span>"
                f"</div>",
                unsafe_allow_html=True,
            )

        # Quantity
        with leg_cols[2]:
            new_qty = st.number_input(
                "qty", min_value=1, max_value=100,
                value=leg["quantity"],
                key=f"qty_{i}_{leg['strike']}_{leg['type']}_{leg['action']}",
                label_visibility="collapsed",
            )
            if new_qty != leg["quantity"]:
                leg["quantity"] = new_qty
                st.rerun()

        # Cost per leg
        with leg_cols[3]:
            leg_cost = leg["premium"] * leg["quantity"] * MULTIPLIER
            if leg["action"] == "BUY":
                leg_cost = -leg_cost
            lc_color = C_GREEN if leg_cost >= 0 else C_RED
            st.markdown(
                f"<div style='text-align:center;font-family:monospace;"
                f"font-size:12px;color:{lc_color};padding-top:8px;'>"
                f"{leg_cost:+,.0f}₪</div>",
                unsafe_allow_html=True,
            )

        # Remove button
        with leg_cols[4]:
            if st.button("✕", key=f"rm_{i}_{leg['strike']}_{leg['type']}"):
                remove_leg(i)
                st.rerun()

    st.markdown("<div style='height:8px;'></div>", unsafe_allow_html=True)

    # Clear all button
    btn_cols = st.columns([3, 1])
    with btn_cols[1]:
        if st.button("🗑️ נקה הכל", key="clear_all"):
            clear_legs()
            st.rerun()

    # ==============================================================
    # PAYOFF DIAGRAM
    # ==============================================================
    st.markdown("<hr>", unsafe_allow_html=True)
    st.markdown(f"""
    <div style="font-size:14px;font-weight:700;color:{C_TEXT};
                margin-bottom:10px;display:flex;align-items:center;gap:8px;">
        📊 Payoff at Expiry
        <span style="font-size:10px;color:{C_DIM};font-weight:500;">
            P&L profile across TA-35 expiry prices
        </span>
    </div>
    """, unsafe_allow_html=True)

    # Price range: ±10% from index
    spot = index_value if index_value > 0 else 2000
    lo = spot * 0.90
    hi = spot * 1.10
    x = np.linspace(lo, hi, 500)
    y = calculate_payoff(legs, x)

    # Find breakeven points (where y crosses zero)
    breakevens = []
    for i in range(1, len(y)):
        if y[i - 1] * y[i] < 0:
            # Linear interpolation
            x_be = x[i - 1] + (0 - y[i - 1]) * (x[i] - x[i - 1]) / (y[i] - y[i - 1])
            breakevens.append(x_be)

    max_profit = float(np.max(y))
    max_loss = float(np.min(y))
    pnl_at_spot = float(np.interp(spot, x, y))

    # Build Plotly figure
    fig = go.Figure()

    # Profit zone fill (green)
    y_profit = np.where(y > 0, y, 0)
    fig.add_trace(go.Scatter(
        x=x, y=y_profit,
        fill="tozeroy",
        fillcolor="rgba(0,230,118,0.12)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Loss zone fill (red)
    y_loss = np.where(y < 0, y, 0)
    fig.add_trace(go.Scatter(
        x=x, y=y_loss,
        fill="tozeroy",
        fillcolor="rgba(255,23,68,0.12)",
        line=dict(width=0),
        showlegend=False,
        hoverinfo="skip",
    ))

    # Main P&L line
    fig.add_trace(go.Scatter(
        x=x, y=y,
        mode="lines",
        line=dict(color=C_BLUE, width=2.5),
        name="P&L",
        hovertemplate="TA-35: %{x:,.0f}<br>P&L: %{y:+,.0f} ₪<extra></extra>",
    ))

    # Zero line
    fig.add_hline(y=0, line_dash="dash",
                  line_color=C_DIM, line_width=1)

    # Current spot line
    fig.add_vline(
        x=spot, line_dash="dot",
        line_color=C_YELLOW, line_width=1.5,
        annotation_text=f"Spot {spot:,.0f}",
        annotation_position="top",
        annotation_font=dict(size=10, color=C_YELLOW),
    )

    # Breakeven markers
    for be in breakevens:
        fig.add_vline(
            x=be, line_dash="dot",
            line_color=C_DIM, line_width=1,
            annotation_text=f"BE {be:,.0f}",
            annotation_position="bottom",
            annotation_font=dict(size=9, color=C_DIM),
        )

    # Mark strike prices of legs
    for leg in legs:
        fig.add_trace(go.Scatter(
            x=[leg["strike"]],
            y=[float(np.interp(leg["strike"], x, y))],
            mode="markers",
            marker=dict(
                size=8,
                color=C_GREEN if leg["action"] == "BUY" else C_RED,
                line=dict(width=1, color=C_TEXT),
            ),
            showlegend=False,
            hovertemplate=(
                f"{leg['action']} {leg['type']} @ {leg['strike']:,.0f}<br>"
                f"P&L: %{{y:+,.0f}} ₪<extra></extra>"
            ),
        ))

    fig.update_layout(
        template="plotly_dark",
        paper_bgcolor=C_BG,
        plot_bgcolor=C_BG,
        font=dict(family="Inter, sans-serif", color=C_TEXT, size=11),
        height=420,
        margin=dict(l=50, r=30, t=30, b=50),
        xaxis=dict(
            title="TA-35 Expiry Price",
            gridcolor=C_BORDER,
            zeroline=False,
            tickformat=",",
        ),
        yaxis=dict(
            title="P&L (₪)",
            gridcolor=C_BORDER,
            zeroline=False,
            tickformat="+,",
        ),
        hovermode="x unified",
        showlegend=False,
    )

    st.plotly_chart(fig, use_container_width=True)

    # Payoff summary KPIs
    be_str = " · ".join(f"{b:,.0f}" for b in breakevens) if breakevens else "—"
    st.markdown(f"""
    <div class="kpi-row">
        <div class="kpi g">
            <div class="lb">Max Profit</div>
            <div class="vl" style="color:{C_GREEN};">{max_profit:+,.0f} ₪</div>
        </div>
        <div class="kpi r">
            <div class="lb">Max Loss</div>
            <div class="vl" style="color:{C_RED};">{max_loss:+,.0f} ₪</div>
        </div>
        <div class="kpi y">
            <div class="lb">P&L at Spot</div>
            <div class="vl" style="color:{C_GREEN if pnl_at_spot >= 0 else C_RED};">
                {pnl_at_spot:+,.0f} ₪
            </div>
            <div class="sb">TA-35 = {spot:,.0f}</div>
        </div>
        <div class="kpi b">
            <div class="lb">Breakeven</div>
            <div class="vl" style="font-size:14px;">{be_str}</div>
        </div>
    </div>
    """, unsafe_allow_html=True)
