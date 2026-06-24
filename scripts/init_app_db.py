"""Create app.db from the docs/app_schema_v*.sql files and seed a dev member fixture.

Portable replacement for the CLAUDE.md command
    sqlite3 "$APP_DB_PATH" < docs/app_schema_v0_1.sql
which requires the sqlite3 CLI (not present on every dev machine). This uses the
Python stdlib instead.

Schema is the v0.1 base plus ordered additive deltas (v0.2 adds the cost-share
verification columns + member_accumulators). Deltas are applied in version order
on a fresh DB; this is a prototype, so --force recreates rather than migrating.

Usage:
    python scripts/init_app_db.py            # create if absent (errors if present)
    python scripts/init_app_db.py --force    # drop and recreate

PHI note: app.db is the ONLY place member data lives (PRD §1.2). The seeded
member is an opaque dev fixture standing in for the host MASA app's identity.
"""

from __future__ import annotations

import argparse
import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from app.config import REPO_ROOT, get_settings  # noqa: E402

# v0.1 base + ordered additive deltas, applied in this order on a fresh DB.
SCHEMA_FILES = [
    REPO_ROOT / "docs" / "app_schema_v0_1.sql",
    REPO_ROOT / "docs" / "app_schema_v0_2.sql",
]
DEV_MEMBER_REF = "dev-member-001"


def seed_dev_member(conn: sqlite3.Connection) -> None:
    """Insert a single opaque dev member if not already present."""
    conn.execute(
        "INSERT OR IGNORE INTO member_profile (member_ref, default_insurance_situation, "
        "plan_identifier) VALUES (?, ?, ?)",
        (DEV_MEMBER_REF, None, None),
    )
    conn.commit()


def main() -> int:
    parser = argparse.ArgumentParser(description="Initialize app.db from the v0.1 base + deltas.")
    parser.add_argument(
        "--force", action="store_true", help="Drop the existing app.db and recreate it."
    )
    args = parser.parse_args()

    db_path = get_settings().app_db_file

    if db_path.exists():
        if not args.force:
            print(f"app.db already exists at {db_path}. Use --force to recreate.")
            # Still make sure the dev fixture is present, then exit cleanly.
            conn = sqlite3.connect(db_path)
            conn.execute("PRAGMA foreign_keys = ON")
            seed_dev_member(conn)
            conn.close()
            return 0
        db_path.unlink()
        print(f"Removed existing {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)

    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        for schema_file in SCHEMA_FILES:
            conn.executescript(schema_file.read_text(encoding="utf-8"))
        seed_dev_member(conn)
    finally:
        conn.close()

    applied = ", ".join(f.name for f in SCHEMA_FILES)
    print(f"Created {db_path} from [{applied}] and seeded member '{DEV_MEMBER_REF}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
