"""Phase 1 — app.db repository helpers, against a fresh schema-built temp DB."""

import sqlite3
from pathlib import Path

import pytest

from app import repo

REPO_ROOT = Path(__file__).resolve().parent.parent
SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"


@pytest.fixture()
def conn(tmp_path):
    c = sqlite3.connect(tmp_path / "app.db")
    c.row_factory = sqlite3.Row
    c.execute("PRAGMA foreign_keys = ON")
    c.executescript(SCHEMA.read_text(encoding="utf-8"))
    repo.upsert_member(c, "m1", default_insurance_situation="medicare_ffs")
    try:
        yield c
    finally:
        c.close()


def test_case_lifecycle(conn):
    case_id = repo.create_case(conn, "m1", entry_point="claims", seed_intent="appeal")
    assert case_id > 0
    repo.update_case(conn, case_id, problem_type="denial_appeal",
                     insurance_situation="medicare_ffs", active_flow="flow3_appeal",
                     current_stage="stage4_ambulance", machine_context={"shown": ["stage0"]})
    case = repo.get_case(conn, case_id)
    assert case["problem_type"] == "denial_appeal"
    assert case["entry_point"] == "claims"
    assert '"shown"' in case["machine_context"]


def test_update_case_rejects_unknown_column(conn):
    cid = repo.create_case(conn, "m1")
    with pytest.raises(ValueError):
        repo.update_case(conn, cid, bogus="x")


def test_bill_and_denial_capture(conn):
    cid = repo.create_case(conn, "m1")
    repo.upsert_bill_summary(conn, cid, provider_name="Mercy", total_billed_cents=124000,
                             patient_responsibility_cents=124000)
    line_id = repo.add_bill_line(conn, cid, 1, "99214", detected_code_type="CPT",
                                 units=1, billed_charge_cents=48000, encounter_pos="11")
    repo.add_denial_code(conn, cid, "50", "CARC", where_seen="line", line_id=line_id)
    assert repo.get_bill_lines(conn, cid)[0]["raw_code"] == "99214"
    assert repo.get_denial_codes(conn, cid)[0]["code"] == "50"


def test_flow2_findings_and_savings_view(conn):
    cid = repo.create_case(conn, "m1")
    repo.add_flow2_finding(conn, cid, "unbundling_ptp", "likely_error_recoverable",
                           ptp_modifier_indicator=0, recoverable_cents=9500)
    repo.add_flow2_finding(conn, cid, "price_benchmark", "above_benchmark_leverage",
                           pfs_setting="non_facility", benchmark_cents=12699,
                           billed_multiple=3.78, benchmark_tier="solid_leverage")
    s = repo.case_savings(conn, cid)
    assert s["recoverable_cents"] == 9500
    assert s["leverage_line_count"] == 1


def test_flow3_appeal_and_card(conn):
    cid = repo.create_case(conn, "m1")
    repo.upsert_ambulance_claim(conn, cid, transport_hcpcs="A0429", is_emergency=1,
                                loaded_miles=12.0)
    repo.upsert_flow3_appeal(conn, cid, "medicare_ffs", "binding", denial_basis="CARC 50",
                             base_rate_cents=45000, per_mile_rate_cents=915,
                             reasonable_amount_cents=55980, anchor_is_floor=0)
    repo.add_appeal_citation(conn, cid, "ncd", "NCD-10.1", was_approved=1)
    card_id = repo.create_answer_card(conn, cid, "Your transport appears appealable.",
                                      flow="flow3_appeal", number_cents=55980,
                                      number_label="reasonable_amount", escalation_offered=1)
    repo.add_card_citation(conn, card_id, "ncd", "NCD-10.1", display_text="NCD 10.1 · reviewed")
    appeal = conn.execute("SELECT * FROM flow3_appeals WHERE case_id = ?", (cid,)).fetchone()
    assert appeal["reasonable_amount_cents"] == 55980
    assert appeal["nsa_content_suppressed"] == 1  # schema default — NSA off


def test_handoff(conn):
    cid = repo.create_case(conn, "m1")
    hid = repo.create_handoff(conn, cid, reason="air ambulance out of scope")
    row = conn.execute("SELECT * FROM handoffs WHERE handoff_id = ?", (hid,)).fetchone()
    assert row["handoff_type"] == "in_house_advocate"
