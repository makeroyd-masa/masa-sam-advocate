"""Phase 1 — read-only pilot.db accessors, against the real reference DB.

Skips cleanly if data/pilot.db is absent (CI without the 1 GB reference file).
"""

import sqlite3
from pathlib import Path

import pytest

from app import pilot
from app.codes import detect_code_type, parse_denial_code

REPO_ROOT = Path(__file__).resolve().parent.parent
PILOT = REPO_ROOT / "data" / "pilot.db"

pytestmark = pytest.mark.skipif(not PILOT.exists(), reason="pilot.db not present")


@pytest.fixture()
def conn():
    c = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    c.row_factory = sqlite3.Row
    try:
        yield c
    finally:
        c.close()


# --- codes -----------------------------------------------------------------
def test_lookup_hcpcs(conn):
    row = pilot.lookup_code(conn, "A0429")
    assert row and row["code_type"] == "HCPCS"
    assert "bls" in (row["short_description"] or "").lower()


def test_carc_official_text(conn):
    txt = pilot.official_text(conn, "50", "CARC")
    assert txt and "medical necessity" in txt.lower()


def test_cpt_not_in_codes(conn):
    # 99214 is CPT — not stored (AMA license); category fallback handled by Flow 1.
    assert pilot.lookup_code(conn, "99214") is None


def test_ambiguous_code_needs_type(conn):
    # '50' exists as CARC and POS — explicit type disambiguates.
    assert pilot.lookup_code(conn, "50", "CARC")["code_type"] == "CARC"


# --- NCCI ------------------------------------------------------------------
def test_ptp_pair_either_order(conn):
    edit = pilot.ptp_edit(conn, "80048", "80053")  # reversed order
    assert edit and edit["modifier_indicator"] == 0


def test_mue_cap(conn):
    cap = pilot.mue_cap(conn, "80053")
    assert cap and cap["mue_value"] == 1


# --- PFS -------------------------------------------------------------------
def test_pfs_setting_selects_column(conn):
    nf = pilot.pfs_rate(conn, "99214", "non_facility")
    fac = pilot.pfs_rate(conn, "99214", "facility")
    assert nf["benchmark_cents"] == 12699
    assert fac["benchmark_cents"] == 9485


def test_pfs_facility_line_unbenchmarkable(conn):
    assert pilot.pfs_rate(conn, "ZZZZZ", "non_facility") is None


# --- ambulance -------------------------------------------------------------
def test_ambulance_base_and_mileage(conn):
    base = pilot.ambulance_base_rate(conn, "A0429", "CA")
    assert base and base > 0
    per_mile = pilot.ambulance_mileage_rate(conn, "CA")
    assert per_mile == 915  # ground mileage, national


# --- NCD -------------------------------------------------------------------
def test_ncd_reviewed_and_covered(conn):
    assert len(pilot.ncd_ambulance(conn)) == 35
    assert len(pilot.ncd_ambulance(conn, coverage_indicator="covered")) == 6


# --- appeals ---------------------------------------------------------------
def test_medicare_appeal_levels(conn):
    levels = pilot.medicare_appeal_levels(conn, "traditional_medicare")
    assert levels[0]["level_number"] == 1
    assert levels[0]["filing_deadline_days"] == 120


# --- detection helpers -----------------------------------------------------
def test_detect_code_type():
    assert detect_code_type("A0429") == "HCPCS"
    assert detect_code_type("99214") == "CPT"


def test_parse_denial_code():
    assert parse_denial_code("CARC 50") == ("50", "CARC")
    assert parse_denial_code("N386") == ("N386", "RARC")
    assert parse_denial_code("50") == ("50", "CARC")
    assert parse_denial_code("") is None
