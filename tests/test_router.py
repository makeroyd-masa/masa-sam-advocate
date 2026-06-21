"""Phase 2 — loader + suggested_action router, incl. the locked overrides (C3)
and the display gate (C4). Uses a temp app.db; needs pilot.db for official_text."""

import sqlite3
from pathlib import Path

import pytest

from app import router
from app.loader import load_code_explanations

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"
PILOT = REPO_ROOT / "data" / "pilot.db"

pytestmark = pytest.mark.skipif(not PILOT.exists(), reason="pilot.db not present")


@pytest.fixture()
def conns(tmp_path):
    app_conn = sqlite3.connect(tmp_path / "app.db")
    app_conn.row_factory = sqlite3.Row
    app_conn.execute("PRAGMA foreign_keys = ON")
    app_conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    pilot_conn = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    pilot_conn.row_factory = sqlite3.Row
    n = load_code_explanations(app_conn, pilot_conn)
    assert n == 80
    try:
        yield app_conn, pilot_conn
    finally:
        app_conn.close()
        pilot_conn.close()


def test_loader_joins_official_text_and_blank_copy(conns):
    app_conn, _ = conns
    row = app_conn.execute(
        "SELECT * FROM code_explanations WHERE code='50' AND code_type='CARC'"
    ).fetchone()
    assert "medical necessity" in row["official_text"].lower()
    assert row["plain_explanation"] == ""        # not auto-authored
    assert row["reviewed"] == 0
    assert row["suggested_action"] == "appeal"


def test_appeal_routes_to_flow3(conns):
    app_conn, pilot_conn = conns
    d = router.route_denial_code(app_conn, pilot_conn, "50", "CARC")
    assert d.action == "appeal"
    assert d.target_flow == "flow3_appeal"


def test_carc45_insured_vs_self_pay(conns):
    app_conn, pilot_conn = conns
    insured = router.route_denial_code(app_conn, pilot_conn, "45", "CARC",
                                       insurance_situation="commercial_aca")
    assert insured.action == "explain_only" and insured.override_applied is None

    selfpay = router.route_denial_code(app_conn, pilot_conn, "45", "CARC",
                                       insurance_situation="self_pay")
    assert selfpay.action == "error_check"
    assert selfpay.target_flow == "flow2_error"
    assert selfpay.override_applied == "carc45_self_pay_leverage"


def test_carc29_verify_then_escalate(conns):
    app_conn, pilot_conn = conns
    verify = router.route_denial_code(app_conn, pilot_conn, "29", "CARC", member_billed=False)
    assert verify.action == "verify_with_payer"
    assert verify.requires_handoff is False

    escalate = router.route_denial_code(app_conn, pilot_conn, "29", "CARC", member_billed=True)
    assert escalate.action == "escalate_human"
    assert escalate.requires_handoff is True
    assert escalate.override_applied == "carc29_billed_escalate"


def test_display_gate_falls_back_to_official(conns):
    # All curated copy is blank+unreviewed today → cards must show official wording.
    app_conn, pilot_conn = conns
    d = router.route_denial_code(app_conn, pilot_conn, "50", "CARC")
    assert d.copy.source == "official_fallback"
    assert d.copy.plain_explanation is None
    assert d.copy.official_text


def test_display_gate_uses_authored_when_reviewed(conns):
    # Simulate the content team authoring + reviewing one entry.
    app_conn, pilot_conn = conns
    app_conn.execute(
        "UPDATE code_explanations SET plain_explanation=?, reviewed=1 "
        "WHERE code='50' AND code_type='CARC'",
        ("Your insurer says this wasn't medically necessary.",),
    )
    app_conn.commit()
    d = router.route_denial_code(app_conn, pilot_conn, "50", "CARC")
    assert d.copy.source == "authored"
    assert d.copy.plain_explanation.startswith("Your insurer")


def test_long_tail_fallback(conns):
    # A real CARC not in the curated 50 → explain_only with payer's exact language.
    app_conn, pilot_conn = conns
    d = router.route_denial_code(app_conn, pilot_conn, "100", "CARC")
    assert d.in_curated_set is False
    assert d.action == "explain_only"
    assert d.copy.source == "official_fallback"


def test_route_from_free_text(conns):
    app_conn, pilot_conn = conns
    d = router.route_denial_text(app_conn, pilot_conn, "CARC 50")
    assert d and d.target_flow == "flow3_appeal"
    assert router.route_denial_text(app_conn, pilot_conn, "") is None
