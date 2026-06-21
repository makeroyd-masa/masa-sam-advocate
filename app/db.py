"""SQLite connection helpers for the two databases (CLAUDE.md data layer).

  * pilot.db  — READ-ONLY reference data. Opened with mode=ro so a stray write
    raises instead of silently corrupting reference data. Never written to.
  * app.db    — the app's writable case/state store. foreign_keys is enforced.

The two are separate files with no cross-db FKs; pilot codes are stored as plain
values in app.db and resolved against pilot.db at query time.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager

from .config import get_settings


def _connect(path: str, *, read_only: bool) -> sqlite3.Connection:
    if read_only:
        conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    else:
        conn = sqlite3.connect(path)
        conn.execute("PRAGMA foreign_keys = ON")
    conn.row_factory = sqlite3.Row
    return conn


def connect_pilot() -> sqlite3.Connection:
    """Open the read-only reference DB. Caller closes."""
    return _connect(str(get_settings().pilot_db_file), read_only=True)


def connect_app() -> sqlite3.Connection:
    """Open the writable app DB (foreign keys on). Caller closes."""
    return _connect(str(get_settings().app_db_file), read_only=False)


@contextmanager
def pilot_conn() -> Iterator[sqlite3.Connection]:
    conn = connect_pilot()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def app_conn() -> Iterator[sqlite3.Connection]:
    conn = connect_app()
    try:
        yield conn
    finally:
        conn.close()


# FastAPI dependencies -------------------------------------------------------
def get_pilot_db() -> Iterator[sqlite3.Connection]:
    with pilot_conn() as conn:
        yield conn


def get_app_db() -> Iterator[sqlite3.Connection]:
    with app_conn() as conn:
        yield conn
