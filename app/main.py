"""FastAPI entrypoint.  Run: `uvicorn app.main:app --reload`

Phase 0 exposes only /health (verifies both DB connections + surfaces the
feature-flag posture). Flow routers are added in later phases.
"""

from __future__ import annotations

from fastapi import FastAPI

from . import __version__
from .config import feature_flags, get_settings
from .db import connect_app, connect_pilot

app = FastAPI(title="SAM Medical Bill Advocate", version=__version__)


@app.get("/health")
def health() -> dict:
    """Liveness + both-DB connectivity check."""
    settings = get_settings()
    out: dict = {"status": "ok", "version": __version__, "databases": {}}

    # pilot.db (read-only reference data)
    try:
        conn = connect_pilot()
        try:
            carc = conn.execute(
                "SELECT COUNT(*) FROM codes WHERE code_type = 'CARC'"
            ).fetchone()[0]
        finally:
            conn.close()
        out["databases"]["pilot_db"] = {
            "connected": True,
            "read_only": True,
            "path": str(settings.pilot_db_file),
            "carc_codes": carc,
        }
    except Exception as exc:  # noqa: BLE001 — surface any connection error in the payload
        out["status"] = "degraded"
        out["databases"]["pilot_db"] = {"connected": False, "error": str(exc)}

    # app.db (writable case/state store)
    try:
        conn = connect_app()
        try:
            members = conn.execute("SELECT COUNT(*) FROM member_profile").fetchone()[0]
        finally:
            conn.close()
        out["databases"]["app_db"] = {
            "connected": True,
            "path": str(settings.app_db_file),
            "member_profiles": members,
        }
    except Exception as exc:  # noqa: BLE001
        out["status"] = "degraded"
        out["databases"]["app_db"] = {
            "connected": False,
            "error": str(exc),
            "hint": "Run: python scripts/init_app_db.py",
        }

    out["feature_flags"] = feature_flags()
    return out
