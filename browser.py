"""
browser.py -- Playwright browser lifecycle for TASE pipeline.

Handles launch, TASE-page navigation, and session recovery.
User-Agent is rotated from a small pool on every launch/restart
to reduce fingerprinting by the Imperva WAF.
"""
import logging
import random
import time

from config import PAGE_TIMEOUT_MS, RENDER_WAIT_SECONDS

logger = logging.getLogger("tase_pipeline")

_TASE_PAGE = (
    "https://market.tase.co.il/he/market_data/derivatives/01/"
    "major_data/putvscall"
    "?dType=2&updType=1&inQType=3&objId=01&qType=3"
)

_USER_AGENTS = [
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/125.0.0.0 Safari/537.36"
    ),
    (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
]


def navigate(page) -> None:
    """Navigate to the TASE options page, falling back on networkidle timeout."""
    try:
        page.goto(_TASE_PAGE, wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
        logger.info("TASE page loaded (networkidle)")
    except Exception:
        logger.warning("networkidle timeout — using domcontentloaded")
        page.goto(_TASE_PAGE, wait_until="domcontentloaded", timeout=PAGE_TIMEOUT_MS)
        time.sleep(RENDER_WAIT_SECONDS + 4)
    time.sleep(RENDER_WAIT_SECONDS)


def launch(pw, headless: bool):
    """Launch a fresh Playwright browser + context + page."""
    browser = pw.chromium.launch(
        headless=headless,
        args=[
            "--disable-blink-features=AutomationControlled",
            "--no-sandbox",
            "--disable-dev-shm-usage",
        ],
    )
    context = browser.new_context(
        locale="he-IL",
        user_agent=random.choice(_USER_AGENTS),
    )
    page = context.new_page()
    navigate(page)
    return browser, context, page


def recover(pw, browser, context, page, headless: bool):
    """
    Attempt session recovery in two stages:
    1. Reload the existing page — cheap and preserves cookies.
    2. Full browser restart if reload fails.

    Returns a (browser, context, page) triple pointing to a live session.
    Raises on complete failure so the caller can shut down cleanly.
    """
    # Import here to avoid a circular dependency at module load time
    # (browser → tase_api → database → supabase_client).
    from tase_api import get_expiry_dates

    try:
        page.reload(wait_until="networkidle", timeout=PAGE_TIMEOUT_MS)
        time.sleep(RENDER_WAIT_SECONDS)
        if get_expiry_dates(page):
            logger.info("Session recovered via reload")
            return browser, context, page
    except Exception:
        pass

    logger.warning("Full browser restart...")
    saved_cookies = []
    try:
        saved_cookies = context.cookies()
    except Exception:
        pass
    try:
        browser.close()
    except Exception:
        pass

    browser, context, page = launch(pw, headless)
    if saved_cookies:
        try:
            context.add_cookies(saved_cookies)
            logger.info("Restored %d cookies after recovery", len(saved_cookies))
        except Exception:
            pass
    return browser, context, page
