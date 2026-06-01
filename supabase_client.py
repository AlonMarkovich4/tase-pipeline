"""
supabase_client.py -- Shared Supabase HTTP client for TASE pipeline.

Centralises base URL, API key, and standard request headers so that
database.py and strategy_engine.py cannot diverge.  Each module still
owns its own table-name variables; this module only manages credentials
and the HTTP layer.
"""
import os

_base_url:    str  = ""
_api_key:     str  = ""
_std_headers: dict = {}
_initialized: bool = False


def ensure_init() -> None:
    global _base_url, _api_key, _std_headers, _initialized
    if _initialized:
        return
    _base_url = os.environ.get("SUPABASE_URL", "").rstrip("/")
    _api_key  = os.environ.get("SUPABASE_KEY", "")
    if not _base_url or not _api_key:
        raise RuntimeError(
            "SUPABASE_URL and SUPABASE_KEY environment variables must be set"
        )
    _std_headers = {
        "apikey":        _api_key,
        "Authorization": f"Bearer {_api_key}",
        "Content-Type":  "application/json",
    }
    _initialized = True


def rest_url(path: str) -> str:
    """Return a PostgREST endpoint URL: <base>/rest/v1/<path>"""
    return f"{_base_url}/rest/v1/{path}"


def storage_url(path: str) -> str:
    """Return a Supabase Storage URL: <base>/storage/v1/object/<path>"""
    return f"{_base_url}/storage/v1/object/{path}"


def headers(**overrides) -> dict:
    """Return a copy of the standard request headers with optional overrides.

    Callers that need UPSERT behaviour should pass Prefer='resolution=merge-duplicates'.
    Callers that want minimal response bodies should pass Prefer='return=minimal'.
    """
    return {**_std_headers, **overrides}


def base_url() -> str:
    return _base_url


def api_key() -> str:
    return _api_key
