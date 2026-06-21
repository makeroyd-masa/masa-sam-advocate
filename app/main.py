"""FastAPI entrypoint.  Run: `uvicorn app.main:app --reload`

Serves the API, /health, and — when a built frontend (dist/) is present — the
SPA, so the whole app is a single origin/process for deployment. An optional
HTTP Basic gate (DEMO_USER/DEMO_PASSWORD env) protects everything but /health,
to keep the pre-counsel demo leadership-only.
"""

from __future__ import annotations

import base64
import os
import secrets

from fastapi import FastAPI, Request
from fastapi.responses import FileResponse, Response

from . import __version__
from .config import REPO_ROOT, feature_flags, get_settings
from .db import connect_app, connect_pilot
from .routers.flows import api as flows_api
from .routers.intake import api as intake_api

app = FastAPI(title="SAM Medical Bill Advocate", version=__version__)

_DEMO_USER = os.environ.get("DEMO_USER", "")
_DEMO_PASSWORD = os.environ.get("DEMO_PASSWORD", "")


@app.middleware("http")
async def basic_auth_gate(request: Request, call_next):
    """Shared-password gate. No-op unless DEMO_PASSWORD is set. /health stays open
    so platform health checks work."""
    if _DEMO_PASSWORD and request.url.path != "/health":
        header = request.headers.get("authorization", "")
        ok = False
        if header.startswith("Basic "):
            try:
                user, _, pw = base64.b64decode(header[6:]).decode("utf-8").partition(":")
                ok = secrets.compare_digest(pw, _DEMO_PASSWORD) and (
                    not _DEMO_USER or secrets.compare_digest(user, _DEMO_USER)
                )
            except Exception:  # noqa: BLE001 — any decode failure = unauthorized
                ok = False
        if not ok:
            return Response(
                "Authentication required", status_code=401,
                headers={"WWW-Authenticate": 'Basic realm="SAM demo"'},
            )
    return await call_next(request)


app.include_router(intake_api)
app.include_router(flows_api)


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


# --- Serve the built SPA (single origin) -----------------------------------
# Defined last so API routes and /health take precedence. Falls back to
# index.html for client-side routes; serves real files (logo.svg, assets/…).
_DIST = REPO_ROOT / "dist"
if _DIST.exists():
    @app.get("/{full_path:path}")
    async def spa(full_path: str):
        candidate = _DIST / full_path
        if full_path and candidate.is_file():
            return FileResponse(candidate)
        return FileResponse(_DIST / "index.html")
