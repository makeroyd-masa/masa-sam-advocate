#!/bin/sh
# Container entrypoint: prepare app.db, load the routing layer, serve.
set -e

: "${PILOT_DB_PATH:=/data/pilot.db}"
: "${APP_DB_PATH:=/data/app.db}"
: "${PORT:=8000}"
export PILOT_DB_PATH APP_DB_PATH

if [ ! -f "$PILOT_DB_PATH" ]; then
  if [ -n "$PILOT_DB_URL" ]; then
    echo "pilot.db missing — fetching from PILOT_DB_URL (first boot)..."
    python scripts/fetch_pilot_db.py || echo "pilot.db fetch failed; /health will read degraded"
  else
    echo "WARNING: pilot.db not found at $PILOT_DB_PATH and PILOT_DB_URL unset."
    echo "         Mount a volume + set PILOT_DB_URL; /health will read 'degraded' until then."
  fi
fi

# Idempotent: creates app.db + dev member if absent; loads code_explanations
# (needs pilot.db for official_text). Tolerate a missing pilot.db on first boot.
python scripts/init_app_db.py || true
python scripts/load_code_explanations.py || echo "skipped routing-layer load (pilot.db?)"

exec uvicorn app.main:app --host 0.0.0.0 --port "$PORT"
