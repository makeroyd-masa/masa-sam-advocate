"""The app.db schema (docs/app_schema_v0_1.sql) executes cleanly and seeds work."""

import sqlite3
from pathlib import Path

from conftest import apply_schema

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"

EXPECTED_TABLES = {
    "member_profile", "cases", "case_events", "bill_summaries", "bill_lines",
    "captured_denial_codes", "itemized_bill_requests", "ambulance_claims",
    "code_explanations", "flow2_findings", "flow3_appeals", "appeal_citations",
    "answer_cards", "card_citations", "handoffs",
}


def _build(tmp_path) -> sqlite3.Connection:
    conn = sqlite3.connect(tmp_path / "t.db")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    return conn


def test_all_tables_and_view_created(tmp_path):
    conn = _build(tmp_path)
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert EXPECTED_TABLES <= tables
    views = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='view'")}
    assert "v_case_savings" in views


def test_v0_2_costshare_delta_applies(tmp_path):
    """The v0.2 delta adds the cost-share columns + member_accumulators on top of v0.1."""
    conn = sqlite3.connect(tmp_path / "t2.db")
    conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(conn)
    cols = {r[1] for r in conn.execute("PRAGMA table_info(bill_summaries)")}
    assert {"copay_cents", "deductible_applied_cents", "coinsurance_cents",
            "not_covered_cents", "discount_cents", "coinsurance_rate_pct"} <= cols
    tables = {r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert "member_accumulators" in tables


def test_member_fk_enforced(tmp_path):
    conn = _build(tmp_path)
    # cases.member_ref is a required FK — inserting a case for an unknown member fails.
    try:
        conn.execute("INSERT INTO cases (member_ref) VALUES ('nobody')")
        conn.commit()
        raised = False
    except sqlite3.IntegrityError:
        raised = True
    assert raised, "FK to member_profile should be enforced"


def test_savings_view_two_tiers(tmp_path):
    conn = _build(tmp_path)
    conn.execute("INSERT INTO member_profile (member_ref) VALUES ('m1')")
    conn.execute("INSERT INTO cases (case_id, member_ref) VALUES (1, 'm1')")
    conn.executescript(
        """
        INSERT INTO flow2_findings (case_id, finding_type, savings_class, recoverable_cents)
            VALUES (1, 'unbundling_ptp', 'likely_error_recoverable', 9500);
        INSERT INTO flow2_findings (case_id, finding_type, savings_class, recoverable_cents)
            VALUES (1, 'price_benchmark', 'above_benchmark_leverage', NULL);
        """
    )
    conn.commit()
    row = conn.execute("SELECT recoverable_cents, leverage_line_count FROM v_case_savings").fetchone()
    assert row[0] == 9500
    assert row[1] == 1
