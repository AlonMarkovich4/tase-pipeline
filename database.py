"""
database.py -- Supabase helper for TASE pipeline (Render deployment).

Flat structure: each option record is its own row in the table.
Clears all rows before each fresh write (keep only latest snapshot).
"""

import os
import json
import logging
import time as _time

import httpx

logger = logging.getLogger("tase_pipeline")

_base_url:      str = ""
_api_key:       str = ""
_table:         str = "tase_putcall"
_history_table: str = "tase_putcall_history"

BATCH_SIZE = 50  # rows per POST request

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


def _init():
    global _base_url, _api_key, _table, _history_table
    _base_url      = os.environ.get("SUPABASE_URL", "").rstrip("/")
    _api_key       = os.environ.get("SUPABASE_KEY", "")
    _table         = os.environ.get("SUPABASE_TABLE", "tase_putcall")
    _history_table = os.environ.get("SUPABASE_HISTORY_TABLE", "tase_putcall_history")
    if not _base_url or not _api_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set"
        )


def _ensure_init():
    if not _base_url:
        _init()


def _headers() -> dict:
    return {
        "apikey":        _api_key,
        "Authorization": f"Bearer {_api_key}",
        "Content-Type":  "application/json",
        "Prefer":        "resolution=merge-duplicates",
    }


# ------------------------------------------------------------------
def test_connection() -> bool:
    """Call at startup to verify Supabase credentials."""
    try:
        _init()
        url = f"{_base_url}/rest/v1/{_table}?select=id&limit=1"
        r = httpx.get(url, headers=_headers(), timeout=10)
        if r.status_code in (200, 206):
            logger.info("Supabase connection OK  (%s)", _base_url)
            return True
        logger.error("Supabase test query returned %d: %s",
                     r.status_code, r.text[:200])
        return False
    except Exception as e:
        logger.error("Supabase connection FAILED: %s", e)
        return False


# ------------------------------------------------------------------
def _clear_table() -> bool:
    """Delete ALL rows from the table (keep only latest snapshot)."""
    _ensure_init()
    url = f"{_base_url}/rest/v1/{_table}?id=gt.0"
    try:
        r = httpx.delete(url, headers=_headers(), timeout=15)
        if r.status_code in (200, 204):
            logger.info("Cleared table before fresh write")
            return True
        logger.warning("Clear table returned %d: %s",
                       r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Clear table failed: %s", e)
    return False


# ------------------------------------------------------------------
def upsert_items(fetch_date: str, fetch_time: str,
                 expiry_date: str, trade_date: str,
                 items: list, max_retries: int = 3) -> bool:
    """
    Insert each option as its own row. Sends in batches.
    Does NOT clear the table — call clear_table() once before the loop.
    """
    _ensure_init()
    # on_conflict ensures UPSERT — avoids 409 if two instances
    # write simultaneously during a Render deploy
    url = (f"{_base_url}/rest/v1/{_table}"
           f"?on_conflict=fetch_date,fetch_time,expiry_date,"
           f"derivativeid_call,derivativeid_put")

    rows = []
    for item in items:
        row = {
            "fetch_date":  fetch_date,
            "fetch_time":  fetch_time,
            "expiry_date": expiry_date,
            "trade_date":  trade_date,
        }
        # Copy all API fields, converting keys to lowercase
        # Only include columns that exist in the table
        for key, val in item.items():
            col = key.lower()
            if col in VALID_COLUMNS:
                row[col] = val
        rows.append(row)

    # Send in batches
    total_ok = 0
    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        payload = json.dumps(batch, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                r = httpx.post(url, headers=_headers(),
                               content=payload, timeout=30)
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
    else:
        logger.error("Supabase upsert partial: %d/%d rows",
                      total_ok, len(rows))
        return False


def upsert_no_trading(fetch_date: str, fetch_time: str,
                      expiry_date: str) -> bool:
    """Write a single 'no trading' placeholder row."""
    _ensure_init()
    row = {
        "fetch_date":          fetch_date,
        "fetch_time":          fetch_time,
        "expiry_date":         expiry_date,
        "derivativename_call": "ללא מסחר",
        "derivativename_put":  "ללא מסחר",
    }
    url = f"{_base_url}/rest/v1/{_table}"

    try:
        r = httpx.post(url, headers=_headers(),
                       content=json.dumps(row, ensure_ascii=False),
                       timeout=30)
        if r.status_code in (200, 201, 204):
            logger.info("Supabase no-trading OK: %s %s",
                         fetch_date, expiry_date)
            return True
        logger.warning("Supabase no-trading %d: %s",
                        r.status_code, r.text[:200])
    except Exception as e:
        logger.warning("Supabase no-trading error: %s", e)
    return False


# ------------------------------------------------------------------
def copy_to_history(max_retries: int = 3) -> bool:
    """
    Copy all rows from the live table to the history table.
    Called at the last cycle of each trading day.
    """
    _ensure_init()

    # 1. Read all rows from live table
    read_url = f"{_base_url}/rest/v1/{_table}?select=*"
    try:
        r = httpx.get(read_url, headers=_headers(), timeout=30)
        if r.status_code not in (200, 206):
            logger.error("History read failed: %d", r.status_code)
            return False
        rows = r.json()
    except Exception as e:
        logger.error("History read error: %s", e)
        return False

    if not rows:
        logger.info("No rows to copy to history")
        return True

    # 2. Remove 'id' and 'fetched_at' so history table generates its own
    for row in rows:
        row.pop("id", None)
        row.pop("fetched_at", None)

    # 3. Insert into history table in batches
    write_url = f"{_base_url}/rest/v1/{_history_table}"
    total_ok = 0

    for i in range(0, len(rows), BATCH_SIZE):
        batch = rows[i : i + BATCH_SIZE]
        payload = json.dumps(batch, ensure_ascii=False)

        for attempt in range(1, max_retries + 1):
            try:
                r = httpx.post(write_url, headers=_headers(),
                               content=payload, timeout=30)
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
    else:
        logger.error("History save partial: %d/%d rows", total_ok, len(rows))
        return False


# ------------------------------------------------------------------
def backup_to_storage() -> bool:
    """
    Weekly backup: export history + strategies tables as CSV
    and upload to Supabase Storage bucket 'backups'.
    The bucket must be created manually in Supabase Dashboard.
    """
    _ensure_init()
    import csv
    import io
    from datetime import datetime
    from zoneinfo import ZoneInfo

    today = datetime.now(ZoneInfo("Asia/Jerusalem")).strftime("%Y-%m-%d")
    tables = [_history_table, "iron_condor_strategies"]
    success = 0

    for table in tables:
        # 1. Read all rows
        try:
            url = f"{_base_url}/rest/v1/{table}?select=*&order=id"
            r = httpx.get(url, headers=_headers(), timeout=30)
            if r.status_code not in (200, 206):
                logger.warning("Backup read %s: HTTP %d", table, r.status_code)
                continue
            rows = r.json()
        except Exception as e:
            logger.warning("Backup read %s error: %s", table, e)
            continue

        if not rows:
            logger.info("Backup %s: no rows, skipping", table)
            continue

        # 2. Convert to CSV
        buf = io.StringIO()
        writer = csv.DictWriter(buf, fieldnames=rows[0].keys())
        writer.writeheader()
        writer.writerows(rows)
        csv_bytes = buf.getvalue().encode("utf-8")

        # 3. Upload to Supabase Storage
        filename = f"{table}_{today}.csv"
        storage_url = (
            f"{_base_url}/storage/v1/object/backups/{filename}"
        )
        upload_headers = {
            "apikey": _api_key,
            "Authorization": f"Bearer {_api_key}",
            "Content-Type": "text/csv",
            "x-upsert": "true",
        }

        try:
            r = httpx.post(storage_url, headers=upload_headers,
                           content=csv_bytes, timeout=30)
            if r.status_code in (200, 201):
                logger.info("Backup %s OK: %s (%d rows, %.1f KB)",
                            table, filename, len(rows),
                            len(csv_bytes) / 1024)
                success += 1
            else:
                logger.warning("Backup upload %s: HTTP %d — %s",
                               table, r.status_code, r.text[:200])
        except Exception as e:
            logger.warning("Backup upload %s error: %s", table, e)

    return success == len(tables)
