"""
health_server.py -- Minimal JSON health endpoint for Render liveness checks.

Owns the health-state dict and serialises every mutation through a Lock so
the HTTP handler thread never observes a partially-updated state.
"""
import json
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

logger = logging.getLogger("tase_pipeline")

_lock: threading.Lock = threading.Lock()
_state: dict = {
    "status":               "starting",
    "last_cycle":           None,
    "last_ok":              None,
    "consecutive_failures": 0,
    "cycles_today":         0,
    # Knowledge/health signals — last time each major action succeeded, so the
    # whole pipeline's health is visible at a glance from the /health endpoint.
    "last_rows":            0,       # rows stored on the last successful cycle
    "last_expiries":        0,
    "last_strategy_at":     None,    # ISO ts of last strategy generation
    "last_settlement_at":   None,    # ISO ts of last settlement run
    "last_archive_date":    None,    # date of last EOD snapshot archived
}


def update(**kwargs) -> None:
    """Thread-safe update of one or more health-state fields."""
    with _lock:
        _state.update(kwargs)


def snapshot() -> dict:
    """Return a consistent copy of the health state."""
    with _lock:
        return dict(_state)


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self):
        snap = snapshot()
        healthy = (
            snap["status"] in ("running", "sleeping")
            and snap["consecutive_failures"] < 5
        )
        code = 200 if healthy else 503
        body = json.dumps(snap, default=str).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, *_args):
        pass


def start() -> None:
    port = int(os.environ.get("PORT", "10000"))
    server = HTTPServer(("0.0.0.0", port), _Handler)
    t = threading.Thread(target=server.serve_forever, daemon=True)
    t.start()
    logger.info("Health-check server listening on :%d", port)
