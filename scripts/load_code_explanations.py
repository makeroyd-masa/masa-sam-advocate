"""Load config/carc_rarc_plain_english.yaml into app.db code_explanations.

Usage: python scripts/load_code_explanations.py
Joins official_text from pilot.db. Run after init_app_db.py. Idempotent.
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.db import connect_app, connect_pilot  # noqa: E402
from app.loader import load_code_explanations  # noqa: E402


def main() -> int:
    app_conn = connect_app()
    pilot_conn = connect_pilot()
    try:
        n = load_code_explanations(app_conn, pilot_conn)
    finally:
        app_conn.close()
        pilot_conn.close()
    print(f"Loaded {n} code_explanations rows.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
