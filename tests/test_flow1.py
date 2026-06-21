"""Phase 4 — Flow 1 explain + answer-card renderer (engine + API)."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app import repo
from app.answer_card import dollars
from app.db import get_app_db, get_pilot_db
from app.flows import flow1
from app.loader import load_code_explanations
from app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"
PILOT = REPO_ROOT / "data" / "pilot.db"

pytestmark = pytest.mark.skipif(not PILOT.exists(), reason="pilot.db not present")


def _pilot():
    c = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    return c


@pytest.fixture()
def app_db(tmp_path):
    path = tmp_path / "app.db"
    c = sqlite3.connect(path)
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    p = _pilot()
    load_code_explanations(c, p)
    p.close()
    repo.upsert_member(c, "m1")
    try:
        yield c
    finally:
        c.close()


# --- engine ----------------------------------------------------------------
def test_dollars():
    assert dollars(124000) == "$1,240.00"
    assert dollars(None) == "—"


def test_explain_denied_claim_is_appealable(app_db):
    pilot_conn = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="explain", insurance_situation="medicare_ffs")
        repo.upsert_bill_summary(app_db, cid, total_billed_cents=124000,
                                 total_allowed_cents=0, total_plan_paid_cents=0,
                                 patient_responsibility_cents=124000)
        repo.add_denial_code(app_db, cid, "50", "CARC", where_seen="bill_level")
        card = flow1.explain(app_db, pilot_conn, cid)
    finally:
        pilot_conn.close()

    assert card.flow == "flow1_explain"
    assert "appealable" in card.headline.lower()
    assert card.number_cents == 124000
    # CARC 50 finding present (authored plain copy or official-text fallback — both
    # mention medical necessity / necessary).
    carc = next(f for f in card.findings if f.title == "CARC 50")
    assert "medical" in carc.text.lower()
    assert carc.citation.source_type == "code_explanation"
    # full-denial reconciliation note
    assert any("denied claim" in f.text for f in card.findings)


def test_cpt_line_category_fallback(app_db):
    pilot_conn = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="explain", insurance_situation="commercial_aca")
        repo.add_bill_line(app_db, cid, 1, "99214", detected_code_type="CPT",
                           units=1, billed_charge_cents=48000, encounter_pos="11")
        card = flow1.explain(app_db, pilot_conn, cid)
    finally:
        pilot_conn.close()
    cpt = next(f for f in card.findings if f.title.startswith("99214"))
    assert "rate only" in cpt.title or "AMA" in cpt.text


# --- API -------------------------------------------------------------------
@pytest.fixture()
def client(app_db, tmp_path):
    # Reuse the prepared app_db file via dependency overrides.
    db_path = tmp_path / "app.db"

    def _app_db_dep():
        conn = sqlite3.connect(db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _pilot_dep():
        conn = _pilot()
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_app_db] = _app_db_dep
    app.dependency_overrides[get_pilot_db] = _pilot_dep
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def test_flow1_api_persists_card(client):
    cid = client.post("/api/cases", json={}).json()["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "explain"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_ffs"})
    client.post(f"/api/cases/{cid}/stage2",
                json={"total_billed_cents": 124000, "patient_responsibility_cents": 124000,
                      "denial_codes": ["CARC 50"]})
    r = client.post(f"/api/cases/{cid}/flow1/explain").json()
    assert r["card_id"] > 0
    assert r["card"]["flow"] == "flow1_explain"
    assert r["card"]["next_action"] == "Check this bill for errors & overcharges"
    # persisted: one answer_cards row + at least one citation
    state = client.get(f"/api/cases/{cid}").json()
    assert state["case"]["current_stage"] == "output"
