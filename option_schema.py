"""
option_schema.py -- Data validation layer for raw TASE options API items.

Every batch of raw items from _fetch_all_pages passes through validate_items()
before it reaches the database or strategy engine.  The function returns only
items that are structurally sound and emits DataQualityWarnings for anything
suspicious.  CRITICAL warnings mean the batch should not be used for strategy
decisions; WARNING means the data is usable but degraded.

Why this exists
---------------
TASE sometimes returns:
  - Stale feeds (TradeDate from yesterday during live trading hours)
  - Zero prices for all options (dead feed, not just illiquid)
  - Negative or missing strike prices (parse errors on their side)
  - Impossible price inversions (bid > ask implied by call/put structure)

Without a validation gate, a single bad cycle can produce corrupt strategy
entries that only surface at settlement.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, field_validator, model_validator

from config import TZ_ISRAEL, TRADING_DAYS, MARKET_OPEN, MARKET_CLOSE

logger = logging.getLogger("tase_pipeline")

# TA-35 index sane bounds — used for strike and underlying validation.
_STRIKE_MIN = Decimal("1000")
_STRIKE_MAX = Decimal("10000")

# Last-traded price is stored as index_points × 50 (the TASE multiplier).
# The most expensive near-money option in a normal market is under 300 pts,
# so 15 000 NIS (= 300 pts × 50) is a very conservative upper bound.
_RATE_MAX = Decimal("15000")


# ------------------------------------------------------------------
# Public types
# ------------------------------------------------------------------

class DQLevel(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING  = "WARNING"


@dataclass
class DataQualityWarning:
    level:  DQLevel
    code:   str    # e.g. "STALE_TRADE_DATE", "ALL_PRICES_ZERO"
    count:  int    # number of items affected (0 = whole-batch condition)
    detail: str    # human-readable description


@dataclass
class ValidationResult:
    accepted: list[dict]
    rejected: list[dict]
    warnings: list[DataQualityWarning] = field(default_factory=list)

    @property
    def has_critical(self) -> bool:
        return any(w.level == DQLevel.CRITICAL for w in self.warnings)

    @property
    def accepted_count(self) -> int:
        return len(self.accepted)

    @property
    def rejected_count(self) -> int:
        return len(self.rejected)


# ------------------------------------------------------------------
# Pydantic model
# ------------------------------------------------------------------

def _parse_number(v: Any) -> Optional[Decimal]:
    """Accept int / float / numeric-string; strip commas; return None on blank."""
    if v is None:
        return None
    if isinstance(v, Decimal):
        return v
    if isinstance(v, (int, float)):
        return Decimal(str(v))
    s = str(v).replace(",", "").strip()
    if not s or s in ("-", "N/A", "n/a", "--"):
        return None
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def _ci_get(item: dict, field: str) -> Any:
    """
    Read a field from a raw TASE item, case-insensitively.

    TASE has shipped both CamelCase (``LastRate_Call``) and lowercase-suffix
    (``LastRate_call``) key spellings across API versions. Reading by exact
    case made the validation gate go blind on a casing change and reject every
    cycle. Normalising on read means a future re-casing can never silence the
    gate again.
    """
    if field in item:                       # fast path: exact match
        return item[field]
    target = field.lower()
    for k, v in item.items():
        if k.lower() == target:
            return v
    return None


class OptionPair(BaseModel):
    """
    One put/call pair row as returned by the TASE API (raw CamelCase keys).

    extra='allow' so unknown fields are preserved and forwarded to the DB
    without modification — we validate only what we understand.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    # Strike prices (index points, e.g. 2100, 2120)
    ExpirationPrice_Call: Optional[Decimal] = None
    ExpirationPrice_Put:  Optional[Decimal] = None

    # Last traded prices (NIS = index_points × TASE_MULTIPLIER)
    LastRate_Call: Optional[Decimal] = None
    LastRate_Put:  Optional[Decimal] = None

    # Theoretical / base prices
    BaseRate_Call: Optional[Decimal] = None
    BaseRate_Put:  Optional[Decimal] = None

    # Intraday high / low
    HighRate_Call: Optional[Decimal] = None
    LowRate_Call:  Optional[Decimal] = None
    HighRate_Put:  Optional[Decimal] = None
    LowRate_Put:   Optional[Decimal] = None

    # Delta — TASE provides absolute integer in [0, 100] for both sides
    Delta_Call: Optional[Decimal] = None
    Delta_Put:  Optional[Decimal] = None

    # Derivative identifiers
    DerivativeID_Call:   Optional[str] = None
    DerivativeID_Put:    Optional[str] = None
    DerivativeName_Call: Optional[str] = None
    DerivativeName_Put:  Optional[str] = None

    # Underlying TA-35 index value at time of snapshot
    UnderlingAsset_Call: Optional[Decimal] = None
    UnderlingAsset_Put:  Optional[Decimal] = None

    # ── Key-casing normalisation (runs first, on the raw dict) ──────────
    @model_validator(mode="before")
    @classmethod
    def _normalize_key_casing(cls, data: Any) -> Any:
        """Map case-insensitive incoming keys onto the model's field names.

        TASE has used both ``LastRate_Call`` and ``LastRate_call``; lowercasing
        both sides lets the model read either spelling. Original keys are kept
        (extra='allow') so the DB layer's own key.lower() still sees everything.
        """
        if not isinstance(data, dict):
            return data
        lower_index: dict = {}
        for k, v in data.items():
            lower_index.setdefault(k.lower(), v)
        out = dict(data)
        for fname in cls.model_fields:
            if fname not in out:
                lk = fname.lower()
                if lk in lower_index:
                    out[fname] = lower_index[lk]
        return out

    # ── Per-field coercion ──────────────────────────────────────────
    @field_validator(
        "ExpirationPrice_Call", "ExpirationPrice_Put",
        "LastRate_Call", "LastRate_Put",
        "BaseRate_Call", "BaseRate_Put",
        "HighRate_Call", "LowRate_Call",
        "HighRate_Put",  "LowRate_Put",
        "Delta_Call",    "Delta_Put",
        "UnderlingAsset_Call", "UnderlingAsset_Put",
        mode="before",
    )
    @classmethod
    def coerce_number(cls, v: Any) -> Optional[Decimal]:
        return _parse_number(v)

    # ── Cross-field sanity ──────────────────────────────────────────
    @model_validator(mode="after")
    def check_call_side(self) -> "OptionPair":
        strike = self.ExpirationPrice_Call
        if strike is not None and not (_STRIKE_MIN <= strike <= _STRIKE_MAX):
            raise ValueError(
                f"Call strike {strike} outside TA-35 sane range "
                f"[{_STRIKE_MIN}, {_STRIKE_MAX}]"
            )
        rate = self.LastRate_Call
        if rate is not None and rate < 0:
            raise ValueError(f"Call LastRate is negative: {rate}")
        if rate is not None and rate > _RATE_MAX:
            raise ValueError(
                f"Call LastRate {rate} exceeds ceiling {_RATE_MAX} — "
                "likely a stale theoretical price"
            )
        delta = self.Delta_Call
        if delta is not None and not (0 <= delta <= 100):
            raise ValueError(f"Call delta {delta} outside [0, 100]")
        return self

    @model_validator(mode="after")
    def check_put_side(self) -> "OptionPair":
        strike = self.ExpirationPrice_Put
        if strike is not None and not (_STRIKE_MIN <= strike <= _STRIKE_MAX):
            raise ValueError(
                f"Put strike {strike} outside TA-35 sane range "
                f"[{_STRIKE_MIN}, {_STRIKE_MAX}]"
            )
        rate = self.LastRate_Put
        if rate is not None and rate < 0:
            raise ValueError(f"Put LastRate is negative: {rate}")
        if rate is not None and rate > _RATE_MAX:
            raise ValueError(
                f"Put LastRate {rate} exceeds ceiling {_RATE_MAX} — "
                "likely a stale theoretical price"
            )
        delta = self.Delta_Put
        if delta is not None and not (0 <= delta <= 100):
            raise ValueError(f"Put delta {delta} outside [0, 100]")
        return self

    @model_validator(mode="after")
    def check_underlying(self) -> "OptionPair":
        for val in (self.UnderlingAsset_Call, self.UnderlingAsset_Put):
            if val is not None and not (_STRIKE_MIN <= val <= _STRIKE_MAX):
                raise ValueError(
                    f"Underlying asset value {val} outside TA-35 sane range"
                )
        return self


# ------------------------------------------------------------------
# Trade-date staleness check
# ------------------------------------------------------------------

def _parse_trade_date(raw: str | None) -> Optional[date]:
    """Try DD/MM/YYYY (TASE default) then YYYY-MM-DD."""
    if not raw:
        return None
    for fmt in ("%d/%m/%Y", "%Y-%m-%d", "%d-%m-%Y"):
        try:
            return datetime.strptime(str(raw).strip(), fmt).date()
        except ValueError:
            continue
    return None


def check_trade_date(
    trade_date_raw: str | None,
    fetch_date_str: str,
) -> Optional[DataQualityWarning]:
    """
    Return a warning if the API's TradeDate is stale relative to today.

    Rules:
    - During trading hours: TradeDate must equal today. Stale = CRITICAL.
    - Outside trading hours: TradeDate may be the previous trading day.
      Two or more days stale = CRITICAL.
    - Unable to parse trade_date: WARNING only (might be a format change).
    """
    if trade_date_raw is None:
        return DataQualityWarning(
            level=DQLevel.WARNING,
            code="MISSING_TRADE_DATE",
            count=0,
            detail="API did not return a TradeDate — cannot verify feed freshness",
        )

    td = _parse_trade_date(trade_date_raw)
    if td is None:
        return DataQualityWarning(
            level=DQLevel.WARNING,
            code="UNPARSEABLE_TRADE_DATE",
            count=0,
            detail=f"Cannot parse TradeDate '{trade_date_raw}' — skipping staleness check",
        )

    now       = datetime.now(TZ_ISRAEL)
    today     = now.date()
    delta_days = (today - td).days

    if delta_days == 0:
        return None  # fresh

    in_market = (
        now.weekday() in TRADING_DAYS
        and MARKET_OPEN <= now.time() <= MARKET_CLOSE
    )

    if delta_days >= 2 or (in_market and delta_days >= 1):
        return DataQualityWarning(
            level=DQLevel.CRITICAL,
            code="STALE_TRADE_DATE",
            count=0,
            detail=(
                f"TradeDate is {td.isoformat()} but today is {today.isoformat()} "
                f"({'market open' if in_market else 'after hours'}) — "
                f"feed is {delta_days} day(s) stale"
            ),
        )

    return DataQualityWarning(
        level=DQLevel.WARNING,
        code="STALE_TRADE_DATE",
        count=0,
        detail=(
            f"TradeDate is {td.isoformat()} (yesterday) during after-hours — "
            "this is expected on rollover; will re-check next cycle"
        ),
    )


# ------------------------------------------------------------------
# Batch-level checks
# ------------------------------------------------------------------

def _check_zero_prices(accepted: list[dict]) -> Optional[DataQualityWarning]:
    """Warn if an unusually high fraction of items have zero call AND put prices."""
    if not accepted:
        return None

    def _zero_or_missing(val) -> bool:
        n = _parse_number(val)        # robust to None / "" / "0" / "0.0" / commas
        return n is None or n == 0

    zero = sum(
        1 for item in accepted
        if _zero_or_missing(_ci_get(item, "LastRate_Call"))
        and _zero_or_missing(_ci_get(item, "LastRate_Put"))
    )
    pct = zero / len(accepted)
    if pct >= 1.0:
        return DataQualityWarning(
            level=DQLevel.CRITICAL,
            code="ALL_PRICES_ZERO",
            count=zero,
            detail=(
                f"100% of {len(accepted)} items have zero call AND put prices — "
                "feed is likely a dead snapshot, not live data"
            ),
        )
    if pct >= 0.5:
        return DataQualityWarning(
            level=DQLevel.WARNING,
            code="MAJORITY_PRICES_ZERO",
            count=zero,
            detail=(
                f"{zero}/{len(accepted)} items ({pct:.0%}) have zero prices on both sides — "
                "market may be pre-open or highly illiquid"
            ),
        )
    return None


def _check_strike_diversity(accepted: list[dict]) -> Optional[DataQualityWarning]:
    """Warn if all call strikes are identical — indicates an API parse error."""
    strikes = set()
    for item in accepted:
        s = _parse_number(_ci_get(item, "ExpirationPrice_Call"))
        if s is not None:
            strikes.add(s)
    if len(accepted) > 5 and len(strikes) <= 1:
        return DataQualityWarning(
            level=DQLevel.CRITICAL,
            code="DUPLICATE_STRIKES",
            count=len(accepted),
            detail=(
                f"All {len(accepted)} items share strike "
                f"{next(iter(strikes), 'unknown')} — "
                "API returned a malformed response"
            ),
        )
    return None


# ------------------------------------------------------------------
# Main entry point
# ------------------------------------------------------------------

def validate_items(
    raw_items: list[dict],
    fetch_date: str,
    trade_date_raw: str | None,
    expiry_date: str,
) -> ValidationResult:
    """
    Validate a batch of raw TASE API items before they enter the pipeline.

    Parameters
    ----------
    raw_items      : list of raw dicts from _fetch_all_pages
    fetch_date     : "YYYY-MM-DD" string for today's date
    trade_date_raw : raw TradeDate string from the TASE response (may be None)
    expiry_date    : "YYYY-MM-DD" expiry this batch belongs to

    Returns
    -------
    ValidationResult with accepted items (original dicts, not Pydantic models),
    rejected items, and a list of DataQualityWarnings.

    The caller should check result.has_critical before using the data for
    strategy calculations.
    """
    warnings:  list[DataQualityWarning] = []
    accepted:  list[dict]               = []
    rejected:  list[dict]               = []

    # 1. Trade-date freshness
    td_warning = check_trade_date(trade_date_raw, fetch_date)
    if td_warning:
        warnings.append(td_warning)

    # 2. Per-item validation
    for item in raw_items:
        try:
            OptionPair.model_validate(item)
            accepted.append(item)
        except Exception as exc:
            rejected.append(item)
            logger.debug(
                "Rejected item (expiry %s, strike_call=%s): %s",
                expiry_date,
                item.get("ExpirationPrice_Call", "?"),
                exc,
            )

    if rejected:
        rejection_pct = len(rejected) / max(len(raw_items), 1)
        level = DQLevel.CRITICAL if rejection_pct >= 0.5 else DQLevel.WARNING
        warnings.append(DataQualityWarning(
            level=level,
            code="ITEMS_REJECTED",
            count=len(rejected),
            detail=(
                f"{len(rejected)}/{len(raw_items)} items failed validation "
                f"({rejection_pct:.0%}) for expiry {expiry_date}"
            ),
        ))

    # 3. Batch-level checks (run on accepted items only)
    for check_fn in (_check_zero_prices, _check_strike_diversity):
        w = check_fn(accepted)
        if w:
            warnings.append(w)

    # 4. Summary log
    if warnings:
        levels = [w.level.value for w in warnings]
        logger.warning(
            "Data quality report — expiry %s: %d accepted, %d rejected, "
            "warnings: %s",
            expiry_date, len(accepted), len(rejected),
            "; ".join(f"[{w.level.value}] {w.code}" for w in warnings),
        )
    else:
        logger.info(
            "Data quality OK — expiry %s: %d items accepted",
            expiry_date, len(accepted),
        )

    return ValidationResult(
        accepted=accepted,
        rejected=rejected,
        warnings=warnings,
    )
