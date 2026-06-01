"""
config.py -- Shared constants for TASE Pipeline.

Single source of truth for timezone, day names, trading hours,
and strategy parameters used across all modules.
"""

from datetime import time as dt_time
from zoneinfo import ZoneInfo

# ------------------------------------------------------------------
# Timezone
# ------------------------------------------------------------------
TZ_ISRAEL = ZoneInfo("Asia/Jerusalem")

# ------------------------------------------------------------------
# Trading calendar
# ------------------------------------------------------------------
TRADING_DAYS = {0, 1, 2, 3, 4}          # Mon-Fri (TASE since Nov 2024)
MARKET_OPEN  = dt_time(9, 30)
MARKET_CLOSE = dt_time(17, 30)

DAY_NAMES_EN = {
    0: "Monday", 1: "Tuesday", 2: "Wednesday",
    3: "Thursday", 4: "Friday", 5: "Saturday", 6: "Sunday",
}

DAY_NAMES_HE = {
    0: "שני", 1: "שלישי", 2: "רביעי",
    3: "חמישי", 4: "שישי", 5: "שבת", 6: "ראשון",
}

# Combined (English, Hebrew) — backward compatible with main.py
DAY_NAMES = {
    wd: (DAY_NAMES_EN[wd], DAY_NAMES_HE[wd]) for wd in range(7)
}

# ------------------------------------------------------------------
# Strategy parameters
# ------------------------------------------------------------------
TASE_MULTIPLIER = 50
WING_WIDTH      = 20
INTERVALS       = [0.5, 1.0, 1.5, 2.0, 2.5, 3.0, 3.5, 4.0]

# Pricing sanity threshold — TASE returns stale theoretical prices for
# illiquid OTM options.  Any quote above this many points is rejected as
# corrupt (a real OTM option in our chains rarely exceeds 30-40 pts).
PRICE_SANITY_MAX_PTS = WING_WIDTH * 3   # 60 pts

# ------------------------------------------------------------------
# Pipeline timing
# ------------------------------------------------------------------
STRATEGY_WINDOW_OPEN  = dt_time(12, 0)
STRATEGY_WINDOW_CLOSE = dt_time(13, 0)
SETTLEMENT_AFTER      = dt_time(10, 0)
WEEKLY_SUMMARY_TIME   = dt_time(17, 0)

# ------------------------------------------------------------------
# Infrastructure
# ------------------------------------------------------------------
BROWSER_RESTART_SECONDS = 6 * 3600       # restart Playwright every 6h
FETCH_INTERVAL_MINUTES  = 15
BATCH_SIZE              = 50             # Supabase rows per POST
PAGE_TIMEOUT_MS         = 45_000         # Playwright navigation timeout
RENDER_WAIT_SECONDS     = 6              # post-navigation settle delay
