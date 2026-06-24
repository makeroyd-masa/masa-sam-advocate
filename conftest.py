"""Ensure the repo root is importable so `from app...` works under pytest."""

import sys
from pathlib import Path

_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(_ROOT))

# app.db schema = v0.1 base + ordered additive deltas (mirrors scripts/init_app_db.py).
SCHEMA_FILES = [
    _ROOT / "docs" / "app_schema_v0_1.sql",
    _ROOT / "docs" / "app_schema_v0_2.sql",
]


def apply_schema(conn) -> None:
    """Apply the full app.db schema (base + deltas) to a fresh connection."""
    for f in SCHEMA_FILES:
        conn.executescript(f.read_text(encoding="utf-8"))
