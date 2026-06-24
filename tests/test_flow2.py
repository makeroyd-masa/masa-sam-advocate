"""Phase 5 — Flow 2 error/overcharge detection (engine + API), real pilot.db."""

import sqlite3
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from conftest import apply_schema

from app import repo
from app.db import get_app_db, get_pilot_db
from app.flows import flow2
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


def _findings(conn, case_id, ftype):
    return conn.execute(
        "SELECT * FROM flow2_findings WHERE case_id=? AND finding_type=?", (case_id, ftype)
    ).fetchall()


def test_unbundling_ptp(app_db):
    p = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="error_overcharge",
                         insurance_situation="medicare_ffs")
        repo.add_bill_line(app_db, cid, 1, "80053", units=1, billed_charge_cents=12000)
        repo.add_bill_line(app_db, cid, 2, "80048", units=1, billed_charge_cents=9500)
        card = flow2.analyze(app_db, p, cid)
    finally:
        p.close()
    rows = _findings(app_db, cid, "unbundling_ptp")
    assert len(rows) == 1
    assert rows[0]["ptp_modifier_indicator"] == 0
    # recoverable = the disallowed (column_two = 80048) line charge
    assert rows[0]["recoverable_cents"] == 9500
    assert card.number_cents >= 9500


def test_quantity_mue(app_db):
    p = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="error_overcharge",
                         insurance_situation="medicare_ffs")
        repo.add_bill_line(app_db, cid, 1, "80053", units=3, billed_charge_cents=30000)
        flow2.analyze(app_db, p, cid)
    finally:
        p.close()
    rows = _findings(app_db, cid, "quantity_mue")
    assert len(rows) == 1
    assert rows[0]["mue_cap"] == 1
    assert rows[0]["units_over_cap"] == 2
    assert rows[0]["recoverable_cents"] == 20000   # (30000//3) * 2


def test_pfs_benchmark_leverage(app_db):
    p = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="error_overcharge",
                         insurance_situation="self_pay")
        repo.add_bill_line(app_db, cid, 1, "99214", units=1, billed_charge_cents=48000,
                           encounter_pos="11")
        card = flow2.analyze(app_db, p, cid)
    finally:
        p.close()
    rows = _findings(app_db, cid, "price_benchmark")
    assert len(rows) == 1
    assert rows[0]["pfs_setting"] == "non_facility"
    assert rows[0]["benchmark_cents"] == 12699
    assert rows[0]["benchmark_tier"] == "solid_leverage"   # 48000/12699 ≈ 3.78×
    assert card.number2_display.startswith("≈3.")


def test_facility_line_logged(app_db):
    p = _pilot()
    try:
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="error_overcharge",
                         insurance_situation="medicare_ffs")
        # a revenue-code-style line that won't resolve against PFS
        repo.add_bill_line(app_db, cid, 1, "0450", units=1, billed_charge_cents=500000,
                           encounter_pos="22")
        flow2.analyze(app_db, p, cid)
    finally:
        p.close()
    assert len(_findings(app_db, cid, "facility_unbenchmarked")) == 1


def test_situation_aware_cta(app_db):
    p = _pilot()
    try:
        # insured: leverage is context, softer CTA
        cid = repo.create_case(app_db, "m1")
        repo.update_case(app_db, cid, problem_type="error_overcharge",
                         insurance_situation="commercial_aca")
        repo.add_bill_line(app_db, cid, 1, "99214", units=1, billed_charge_cents=48000,
                           encounter_pos="11")
        insured = flow2.analyze(app_db, p, cid)
        assert any("allowed amount" in f.text for f in insured.findings)
    finally:
        p.close()


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


def test_flow2_api_two_tier(client):
    cid = client.post("/api/cases", json={}).json()["case"]["case_id"]
    client.post(f"/api/cases/{cid}/stage0", json={"problem_type": "error_overcharge"})
    client.post(f"/api/cases/{cid}/stage1", json={"insurance_situation": "self_pay"})
    client.post(f"/api/cases/{cid}/stage2", json={})
    client.post(f"/api/cases/{cid}/stage3", json={"lines": [
        {"raw_code": "80053", "units": 1, "billed_charge_cents": 12000},
        {"raw_code": "80048", "units": 1, "billed_charge_cents": 9500},
        {"raw_code": "99214", "units": 1, "billed_charge_cents": 48000, "encounter_pos": "11"},
    ]})
    r = client.post(f"/api/cases/{cid}/flow2/check").json()
    assert r["card"]["flow"] == "flow2_error"
    assert r["savings"]["recoverable_cents"] >= 9500       # unbundling
    assert r["card"]["number2_display"].startswith("≈3.")  # PFS leverage tier
