"""Create or migrate app.db from the docs/app_schema_v*.sql files; seed a dev member.

Portable replacement for the CLAUDE.md command
    sqlite3 "$APP_DB_PATH" < docs/app_schema_v0_1.sql
which requires the sqlite3 CLI (not present on every dev machine). This uses the
Python stdlib instead.

Schema = the v0.1 base plus ordered, ADDITIVE deltas (v0.2 adds the cost-share
columns + member_accumulators). Behavior:
  * fresh DB           → apply base + all deltas, then seed.
  * existing DB        → apply any not-yet-applied deltas idempotently, then seed.
  * existing + --force → drop and recreate from scratch.

The existing-DB migration is what lets a redeploy onto a PERSISTENT volume (Railway
/data, Fly volume) pick up new columns without wiping in-session cases — each delta
is gated on a sentinel column so re-running is a no-op (deltas must stay additive).

Usage:
    python scripts/init_app_db.py            # create if absent, else migrate in place
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

_DOCS = REPO_ROOT / "docs"
BASE_SCHEMA = _DOCS / "app_schema_v0_1.sql"
# Ordered additive deltas. Each is (sentinel_table, sentinel_column, file): the delta
# is applied only when the sentinel column is absent, so migrating is idempotent.
# A delta MUST be additive (ALTER ADD COLUMN / CREATE TABLE IF NOT EXISTS) — never a
# rewrite — so applying it to a populated volume DB can't lose data.
DELTAS = [
    ("bill_summaries", "copay_cents", _DOCS / "app_schema_v0_2.sql"),
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


def _has_column(conn: sqlite3.Connection, table: str, column: str) -> bool:
    return any(r[1] == column for r in conn.execute(f"PRAGMA table_info({table})"))


def apply_pending_deltas(conn: sqlite3.Connection) -> list[str]:
    """Apply each delta whose sentinel column is missing. Returns the files applied."""
    applied: list[str] = []
    for table, sentinel, delta_file in DELTAS:
        if not _has_column(conn, table, sentinel):
            conn.executescript(delta_file.read_text(encoding="utf-8"))
            applied.append(delta_file.name)
    conn.commit()
    return applied


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Create app.db (base + deltas), or migrate an existing one in place."
    )
    parser.add_argument(
        "--force", action="store_true", help="Drop the existing app.db and recreate it."
    )
    args = parser.parse_args()

    db_path = get_settings().app_db_file

    if db_path.exists() and not args.force:
        conn = sqlite3.connect(db_path)
        try:
            conn.execute("PRAGMA foreign_keys = ON")
            applied = apply_pending_deltas(conn)
            seed_dev_member(conn)
        finally:
            conn.close()
        if applied:
            print(f"Migrated existing {db_path}: applied [{', '.join(applied)}].")
        else:
            print(f"app.db at {db_path} already current — no migration needed.")
        return 0

    if db_path.exists():  # --force
        db_path.unlink()
        print(f"Removed existing {db_path}")

    db_path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys = ON")
        conn.executescript(BASE_SCHEMA.read_text(encoding="utf-8"))
        apply_pending_deltas(conn)
        seed_dev_member(conn)
    finally:
        conn.close()

    applied = ", ".join(f.name for f in [BASE_SCHEMA, *(d[2] for d in DELTAS)])
    print(f"Created {db_path} from [{applied}] and seeded member '{DEV_MEMBER_REF}'.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
