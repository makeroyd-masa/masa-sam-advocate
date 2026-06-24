"""Phase 3 — intake state machine via the HTTP API (TestClient).

Overrides the DB dependencies to use an isolated temp app.db + the real pilot.db.
"""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import apply_schema

from app.db import get_app_db, get_pilot_db
from app.loader import load_code_explanations
from app.main import app

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"
PILOT = REPO_ROOT / "data" / "pilot.db"

pytestmark = pytest.mark.skipif(not PILOT.exists(), reason="pilot.db not present")


@pytest.fixture()
def client(tmp_path):
    app_db_path = tmp_path / "app.db"
    # Build schema + load the routing layer so Stage-2 classification is real.
    boot = sqlite3.connect(app_db_path)
    boot.row_factory = sqlite3.Row
    apply_schema(boot)
    pilot_boot = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    pilot_boot.row_factory = sqlite3.Row
    load_code_explanations(boot, pilot_boot)
    boot.close()
    pilot_boot.close()

    def _app_db():
        conn = sqlite3.connect(app_db_path)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        try:
            yield conn
        finally:
            conn.close()

    def _pilot_db():
        conn = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
        finally:
            conn.close()

    app.dependency_overrides[get_app_db] = _app_db
    app.dependency_overrides[get_pilot_db] = _pilot_db
    with TestClient(app) as tc:
        yield tc
    app.dependency_overrides.clear()


def _create(client, **kw):
    return client.post("/api/cases", json=kw).json()


def test_denial_appeal_walk_to_stage4(client):
    cid = _create(client, entry_point="claims", seed_intent="appeal")["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_ffs"})
    r = client.post(f"/api/cases/{cid}/stage2",
                    json={"total_billed_cents": 124000, "patient_responsibility_cents": 124000,
                          "denial_codes": ["CARC 50"]}).json()
    assert r["next_stage"] == "stage4_ambulance"
    routing = r["detail"]["denial_routing"][0]
    assert routing["action"] == "appeal" and routing["target_flow"] == "flow3_appeal"


def test_stage4_ground_persists_claim(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_ffs"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    r = client.post(f"/api/cases/{cid}/stage4",
                    json={"transport_hcpcs": "A0429", "is_emergency": True,
                          "loaded_miles": 12, "state": "CA", "denial_code": "CARC 50"}).json()
    assert r["next_stage"] == "analysis"
    assert r["case"]["status"] == "analyzing"
    assert not r["routed_to_handoff"]


def test_stage4_air_routes_to_handoff(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_advantage"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    r = client.post(f"/api/cases/{cid}/stage4", json={"transport_hcpcs": "A0430"}).json()
    assert r["routed_to_handoff"] is True
    assert r["case"]["status"] == "handed_off"
    assert r["case"]["current_stage"] == "done"


def test_stage4_unknown_code_clarifies(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "denial_appeal"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicare_ffs"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    r = client.post(f"/api/cases/{cid}/stage4", json={"transport_hcpcs": "Z9999"}).json()
    assert r["needs_clarification"] is True
    assert r["case"]["current_stage"] == "stage4_ambulance"


def test_medicaid_shortcircuit(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "explain"})
    r = client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "medicaid"}).json()
    assert r["routed_to_handoff"] is True
    assert r["case"]["current_stage"] == "done"


def test_explain_then_checkpoint_to_error_check(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "explain"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "commercial_aca"})
    r = client.post(f"/api/cases/{cid}/stage2", json={"total_billed_cents": 50000}).json()
    assert r["next_stage"] == "analysis"          # explain ends at analysis
    acc = client.post(f"/api/cases/{cid}/checkpoint/accept").json()
    assert acc["case"]["current_stage"] == "stage3_lines"
    assert acc["case"]["active_flow"] == "flow2_error"
    r3 = client.post(f"/api/cases/{cid}/stage3",
                     json={"lines": [{"raw_code": "99214", "units": 1,
                                      "billed_charge_cents": 48000, "encounter_pos": "11"}]}).json()
    assert r3["next_stage"] == "analysis"


def test_resume_returns_state(client):
    cid = _create(client)["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "error_overcharge"})
    got = client.get(f"/api/cases/{cid}").json()
    assert got["case"]["problem_type"] == "error_overcharge"
    assert got["case"]["active_flow"] == "flow2_error"


def test_missing_case_404(client):
    assert client.get("/api/cases/99999").status_code == 404


def test_member_initiated_handoff(client):
    cid = _create(client)["case"]["case_id"]
    r = client.post(f"/api/cases/{cid}/handoff", json={"reason": "wants help"}).json()
    assert r["status"] == "handed_off"
    assert client.get(f"/api/cases/{cid}").json()["case"]["status"] == "handed_off"
