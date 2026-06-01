"""
database.py -- Supabase helper for TASE pipeline (Render deployment).

Flat structure: each option record is its own row in the table.
Clears all rows before each fresh write (keep only latest snapshot).
"""

import csv
import io
import json
import logging
import os
import time as _time
from datetime import datetime as _dt, date as _date, timedelta as _td

import httpx
import supabase_client as _sc
from config import TZ_ISRAEL, BATCH_SIZE

logger = logging.getLogger("tase_pipeline")

_table:         str = ""
_history_table: str = ""

# Columns that exist in the Supabase table (all lowercase)
VALID_COLUMNS = {
    "fetch_date", "fetch_time", "expiry_date", "trade_date",
    "rowtype", "drvtype",
    "derivativeid_call", "derivativename_call", "expirationprice_call",
    "expirationdate_call", "delta_call", "lastrate_call", "baserate_call",
    "lowrate_call", "highrate_call", "dealsno_call",
    "overallturnoverunits_call", "turnovervolume_derivative_call",
    "overallturnovervalue_shekel_call", "openpositions_call",
    "positionchange_call", "curr_hour_call", "underlingasset_call",
    "derivativeid_put", "derivativename_put", "expirationprice_put",
    "expirationdate_put", "delta_put", "lastrate_put", "baserate_put",
    "lowrate_put", "highrate_put", "dealsno_put",
    "overallturnoverunits_put", "turnovervolume_derivative_put",
    "overallturnovervalue_shekel_put", "openpositions_put",
    "positionchange_put", "curr_hour_put", "underlingasset_put",
}

_UPSERT_PREFER = {"Prefer": "resolution=merge-duplicates"}


def _init():
    global _table, _history_table
    _sc.ensure_init()
    _table         = os.environ.get("SUPABASE_TABLE", "tase_putcall")
    _history_table = os.environ.get("SUPABASE_HISTORY_TABLE", "tase_putcall_history")


def _ensure_init():
    if not _table:
        _init()


# ------------------------------------------------------------------
def test_connection() -> bool:
    """Call at startup to verify Supabase credentials."""
    try:
        _init()
        url = _sc.rest_url(f"{_table}?select=id&limit=1")
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206):
            logger.info("Supabase connection OK  (%s)", _sc.base_url())
            return True
        logger.error("Supabase test query returned %d: %s",
                     r.status_code, r.text[:200])
        return False
    except Exception as e:
        logger.error("Supabase connection FAILED: %s", e)
        return False


# ------------------------------------------------------------------
def _clear_old_snapshots(keep_date: str, keep_time: str) -> bool:
    """Delete rows from previous snapshots, keeping only the current one.
    Safe: only runs after a successful write, so data is never lost."""
    _ensure_init()
    try:
        r = httpx.delete(
            _sc.rest_url(_table),
            headers=_sc.headers(),
            params={"or": f"(fetch_date.neq.{keep_date},fetch_time.neq.{keep_time})"},
            timeout=15,
        )
        if r.status_code in (200, 204):
            logger.info("Cleared old snapshots (keeping %s %s)",
                        keep_date, keep_time)
            return True
        logger.warning("Clear old snapshots returned %d: %s",
                       r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Clear old snapshots failed: %s", e)
    return False


# ------------------------------------------------------------------
def upsert_items(fetch_date: str, fetch_time: str,
                 expiry_date: str, trade_date: str,
                 items: list, max_retries: int = 3) -> bool:
    """
    Insert each option as its own row.  Sends in batches.
    Does NOT clear the table — call _clear_old_snapshots() after the full cycle.
    """
    _ensure_init()
    url = _sc.rest_url(
        f"{_table}?on_conflict=fetch_date,fetch_time,expiry_date,"
        f"derivativeid_call,derivativeid_put"
    )

    rows = []
    for item in items:
        row = {
            "fetch_date":  fetch_date,
            "fetch_time":  fetch_time,
            "expiry_date": expiry_date,
            "trade_date":  trade_date,
        }
        for key, val in item.items():
            col = key.lower()
            if col in VALID_COLUMNS:
                row[col] = val
        rows.append(row)

    total_ok = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch   = rows[i : i + BATCH_SIZE]
        payload = json.dumps(batch, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                r = httpx.post(
                    url,
                    headers=_sc.headers(**_UPSERT_PREFER),
                    content=payload,
                    timeout=30,
                )
                if r.status_code in (200, 201, 204):
                    total_ok += len(batch)
                    break
                logger.warning(
                    "Supabase batch %d-%d: %d (attempt %d/%d): %s",
                    i, i + len(batch), r.status_code,
                    attempt, max_retries, r.text[:200],
                )
            except Exception as e:
                logger.warning(
                    "Supabase batch error (attempt %d/%d): %s",
                    attempt, max_retries, e,
                )
            _time.sleep(2 ** attempt)

    if total_ok == len(rows):
        logger.info("Supabase upsert OK: %d rows (%s / %s)",
                    total_ok, fetch_date, expiry_date)
        return True
    logger.error("Supabase upsert partial: %d/%d rows", total_ok, len(rows))
    return False


def upsert_no_trading(fetch_date: str, fetch_time: str,
                      expiry_date: str, max_retries: int = 3) -> bool:
    """Write a single 'no trading' placeholder row, with retry."""
    _ensure_init()
    row = {
        "fetch_date":          fetch_date,
        "fetch_time":          fetch_time,
        "expiry_date":         expiry_date,
        "derivativename_call": "ללא מסחר",
        "derivativename_put":  "ללא מסחר",
    }
    url     = _sc.rest_url(_table)
    payload = json.dumps(row, ensure_ascii=False)

    for attempt in range(1, max_retries + 1):
        try:
            r = httpx.post(url, headers=_sc.headers(), content=payload, timeout=30)
            if r.status_code in (200, 201, 204):
                logger.info("Supabase no-trading OK: %s %s",
                            fetch_date, expiry_date)
                return True
            logger.warning("Supabase no-trading %d (attempt %d/%d): %s",
                           r.status_code, attempt, max_retries, r.text[:200])
        except Exception as e:
            logger.warning("Supabase no-trading error (attempt %d/%d): %s",
                           attempt, max_retries, e)
        if attempt < max_retries:
            _time.sleep(2 ** attempt)
    return False


# ------------------------------------------------------------------
def copy_to_history(max_retries: int = 3) -> bool:
    """
    Copy all rows from the live table to the history table.
    Called at the last cycle of each trading day.
    """
    _ensure_init()

    rows = []
    batch_sz = 1000
    offset = 0
    try:
        while True:
            read_url = _sc.rest_url(
                f"{_table}?select=*&order=id&limit={batch_sz}&offset={offset}"
            )
            r = httpx.get(read_url, headers=_sc.headers(), timeout=30)
            if r.status_code not in (200, 206):
                logger.error("History read failed: %d", r.status_code)
                return False
            chunk = r.json()
            if not chunk:
                break
            rows.extend(chunk)
            if len(chunk) < batch_sz:
                break
            offset += batch_sz
    except Exception as e:
        logger.error("History read error: %s", e)
        return False

    if not rows:
        logger.info("No rows to copy to history")
        return True

    for row in rows:
        row.pop("id", None)
        row.pop("fetched_at", None)

    write_url = _sc.rest_url(
        f"{_history_table}?on_conflict=fetch_date,fetch_time,expiry_date,"
        f"derivativeid_call,derivativeid_put"
    )
    total_ok = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch   = rows[i : i + BATCH_SIZE]
        payload = json.dumps(batch, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                r = httpx.post(
                    write_url,
                    headers=_sc.headers(**_UPSERT_PREFER),
                    content=payload,
                    timeout=30,
                )
                if r.status_code in (200, 201, 204):
                    total_ok += len(batch)
                    break
                logger.warning(
                    "History batch %d-%d: %d (attempt %d/%d): %s",
                    i, i + len(batch), r.status_code,
                    attempt, max_retries, r.text[:200],
                )
            except Exception as e:
                logger.warning(
                    "History batch error (attempt %d/%d): %s",
                    attempt, max_retries, e,
                )
            _time.sleep(2 ** attempt)

    if total_ok == len(rows):
        logger.info("History save OK: %d rows copied", total_ok)
        return True
    logger.error("History save partial: %d/%d rows", total_ok, len(rows))
    return False


# ------------------------------------------------------------------
def backup_to_storage() -> bool:
    """
    Weekly backup: export history + strategies tables as CSV
    and upload to Supabase Storage bucket 'backups'.
    The bucket must be created manually in the Supabase Dashboard.
    """
    _ensure_init()
    today  = _dt.now(TZ_ISRAEL).strftime("%Y-%m-%d")
    tables = [_history_table, "iron_condor_strategies"]
    success = 0

    for table in tables:
        rows = []
        batch_sz = 1000
        offset = 0
        try:
            while True:
                url = _sc.rest_url(
                    f"{table}?select=*&order=id&limit={batch_sz}&offset={offset}"
                )
                r = httpx.get(url, headers=_sc.headers(), timeout=30)
                if r.status_code not in (200, 206):
                    logger.warning("Backup read %s: HTTP %d", table, r.status_code)
                    break
                chunk = r.json()
                if not chunk:
                    break
                rows.extend(chunk)
                if len(chunk) < batch_sz:
                    break
                offset += batch_sz
        except Exception as e:
            logger.warning("Backup read %s error: %s", table, e)
            continue

        if not rows:
            logger.info("Backup %s: no rows, skipping", table)
            continue

        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode("utf-8")

        filename = f"{table}_{today}.csv"
        try:
            r = httpx.post(
                _sc.storage_url(f"backups/{filename}"),
                headers=_sc.headers(**{"Content-Type": "text/csv", "x-upsert": "true"}),
                content=csv_bytes,
                timeout=30,
            )
            if r.status_code in (200, 201):
                logger.info("Backup %s OK: %s (%d rows, %.1f KB)",
                            table, filename, len(rows), len(csv_bytes) / 1024)
                success += 1
            else:
                logger.warning("Backup upload %s: HTTP %d — %s",
                               table, r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Backup upload %s error: %s", table, e)

    return success == len(tables)


# ------------------------------------------------------------------
# Pipeline state — restart-safe markers (daily/weekly summaries,
# strategy triggers, settlement done).
# ------------------------------------------------------------------

def has_history_earlier_this_week(today_iso: str) -> bool:
    """Return True if tase_putcall_history has any rows from a date
    earlier than today_iso within the same ISO week."""
    _ensure_init()
    try:
        d      = _date.fromisoformat(today_iso)
        monday = d - _td(days=d.weekday())
    except ValueError:
        return False

    if monday >= d:
        return False

    yesterday_in_week = (d - _td(days=1)).isoformat()
    url = _sc.rest_url(
        f"{_history_table}"
        f"?fetch_date=gte.{monday.isoformat()}"
        f"&fetch_date=lte.{yesterday_in_week}"
        f"&select=id&limit=1"
    )
    try:
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206):
            return len(r.json()) > 0
    except Exception as e:
        logger.warning("has_history_earlier_this_week error: %s", e)
    return False


def state_is_set(key: str) -> bool:
    """Return True if a marker exists for this key. Safe on errors → False."""
    _ensure_init()
    try:
        url = _sc.rest_url(f"pipeline_state?key=eq.{key}&select=key&limit=1")
        r = httpx.get(url, headers=_sc.headers(), timeout=10)
        if r.status_code in (200, 206):
            return len(r.json()) > 0
    except Exception as e:
        logger.warning("state_is_set(%s) error: %s", key, e)
    return False


def state_set(key: str, value: str = "1") -> bool:
    """UPSERT a state marker. Safe on errors → False (caller must tolerate)."""
    _ensure_init()
    try:
        url     = _sc.rest_url("pipeline_state?on_conflict=key")
        payload = json.dumps([{"key": key, "value": value}])
        r = httpx.post(
            url,
            headers=_sc.headers(**_UPSERT_PREFER),
            content=payload,
            timeout=10,
        )
        if r.status_code in (200, 201, 204):
            return True
        logger.warning("state_set(%s) returned %d: %s",
                       key, r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("state_set(%s) error: %s", key, e)
    return False
