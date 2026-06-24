"""Phase 6 — Flow 3 ground ambulance appeal (engine + API), real pilot.db."""

import json
import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import apply_schema

from app import repo
from app.db import get_app_db, get_pilot_db
from app.flows import flow3
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
    c = sqlite3.connect(tmp_path / "app.db")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    apply_schema(c)
    p = _pilot()
    load_code_explanations(c, p)
    p.close()
    repo.upsert_member(c, "m1")
    try:
        yield c
    finally:
        c.close()


def _setup_ground_case(app_db, insurance, *, miles=12.0, state="CA",
                       denial_date="2026-03-20"):
    cid = repo.create_case(app_db, "m1")
    repo.update_case(app_db, cid, problem_type="denial_appeal", insurance_situation=insurance,
                     active_flow="flow3_appeal",
                     machine_context={"ambulance_state": state})
    repo.upsert_ambulance_claim(app_db, cid, transport_hcpcs="A0429", is_emergency=1,
                                loaded_miles=miles, denial_letter_date=denial_date)
    repo.add_denial_code(app_db, cid, "50", "CARC", where_seen="bill_level")
    return cid


def test_ffs_full_anchor(app_db):
    p = _pilot()
    try:
        cid = _setup_ground_case(app_db, "medicare_ffs", miles=12.0)
        card = flow3.analyze(app_db, p, cid)
    finally:
        p.close()
    appeal = app_db.execute("SELECT * FROM flow3_appeals WHERE case_id=?", (cid,)).fetchone()
    assert appeal["segment"] == "medicare_ffs"
    assert appeal["ncd_weight"] == "binding"
    # A0429 CA = 49736, A0425 = 915; 49736 + 915*12 = 60716
    assert appeal["reasonable_amount_cents"] == 60716
    assert appeal["anchor_is_floor"] == 0
    assert appeal["filing_deadline"] == "2026-07-18"   # 2026-03-20 + 120 days
    assert appeal["letter_status"] == "pending_counsel_review"   # flag off
    assert appeal["nsa_content_suppressed"] == 1
    assert card.number_cents == 60716
    assert card.pathway and "Redetermination" in card.pathway.label
    assert card.honesty_node and "No Surprises Act" in card.honesty_node.text


def test_ffs_floor_when_no_miles(app_db):
    p = _pilot()
    try:
        cid = _setup_ground_case(app_db, "medicare_ffs", miles=None)
        flow3.analyze(app_db, p, cid)
    finally:
        p.close()
    appeal = app_db.execute("SELECT * FROM flow3_appeals WHERE case_id=?", (cid,)).fetchone()
    assert appeal["reasonable_amount_cents"] == 49736   # base only
    assert appeal["anchor_is_floor"] == 1


def test_commercial_persuasive_weight(app_db):
    p = _pilot()
    try:
        cid = _setup_ground_case(app_db, "commercial_aca")
        card = flow3.analyze(app_db, p, cid)
    finally:
        p.close()
    appeal = app_db.execute("SELECT * FROM flow3_appeals WHERE case_id=?", (cid,)).fetchone()
    assert appeal["segment"] == "commercial_aca"
    assert appeal["ncd_weight"] == "persuasive"
    assert "Internal Appeal" in (appeal["appeal_level_ref"] or "")
    assert any("persuasive" in f.text for f in card.findings)


def test_ncd_citation_recorded_approved(app_db):
    p = _pilot()
    try:
        cid = _setup_ground_case(app_db, "medicare_ffs")
        flow3.analyze(app_db, p, cid)
    finally:
        p.close()
    cites = app_db.execute(
        "SELECT * FROM appeal_citations WHERE case_id=? AND source_type='ncd'", (cid,)
    ).fetchall()
    assert cites and cites[0]["was_approved"] == 1


# --- API: ground appeal + air-handoff guard --------------------------------
@pytest.fixture()
def client(app_db, tmp_path):
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


def test_ground_appeal_walk(client):
    cid = client.post("/api/cases", json={"entry_point": "claims"}).json()["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_ffs"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    client.post(f"/api/cases/{cid}/stage4",
                json={"transport_hcpcs": "A0429", "denial_code": "CARC 50",
                      "denial_letter_date": "2026-03-20", "is_emergency": True,
                      "loaded_miles": 12, "state": "CA"})
    r = client.post(f"/api/cases/{cid}/flow3/appeal").json()
    assert r["card"]["flow"] == "flow3_appeal"
    assert r["card"]["number_cents"] == 60716
    assert r["card"]["honesty_node"]["text"]


def test_air_code_never_reaches_flow3(client):
    cid = client.post("/api/cases", json={}).json()["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_advantage"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    s4 = client.post(f"/api/cases/{cid}/stage4", json={"transport_hcpcs": "A0431"}).json()
    assert s4["routed_to_handoff"] is True
    # no ambulance_claims row was written for the air code
    state = client.get(f"/api/cases/{cid}").json()
    assert state["case"]["status"] == "handed_off"
