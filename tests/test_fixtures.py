"""Tier A fixture runner (spec §2). Loads committed fixtures, materializes each
`input` into a temp app.db (the same pattern as test_flow*.py), runs the engine,
and asserts the engine's findings equal the fixture's independently-computed
`expected`. One parametrized case per fixture id; does NOT require pilot.db unless
a fixture must be re-derived (Flow 2 reads pilot.db for benchmarks via the engine).
"""

import json
import sqlite3
import sys
from pathlib import Path

import pytest

TESTS = Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent
FIX = TESTS / "fixtures"
sys.path.insert(0, str(FIX))

import canonical  # noqa: E402

SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"
PILOT = REPO_ROOT / "data" / "pilot.db"
DATA = FIX / "data"


def _load_all() -> list[dict]:
    out: list[dict] = []
    for f in sorted(DATA.glob("**/*.json")):
        out.extend(json.loads(f.read_text(encoding="utf-8")))
    return out


ALL = _load_all()
pytestmark = pytest.mark.skipif(
    not PILOT.exists() or not ALL, reason="pilot.db or generated fixtures missing"
)


@pytest.fixture(scope="module")
def env(tmp_path_factory):
    from app import repo
    app_path = tmp_path_factory.mktemp("fixtures") / "app.db"
    app_conn = sqlite3.connect(app_path)
    app_conn.row_factory = sqlite3.Row
    app_conn.execute("PRAGMA foreign_keys = ON")
    app_conn.executescript(SCHEMA.read_text(encoding="utf-8"))
    repo.upsert_member(app_conn, "m1")
    pilot_conn = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    pilot_conn.row_factory = sqlite3.Row
    try:
        yield app_conn, pilot_conn
    finally:
        app_conn.close()
        pilot_conn.close()


def _engine_findings(conn: sqlite3.Connection, case_id: int) -> list[dict]:
    rows = conn.execute(
        """
        SELECT f.finding_type, f.ptp_modifier_indicator, f.mue_cap, f.units_over_cap,
               f.pfs_setting, f.benchmark_cents, f.billed_multiple, f.benchmark_tier,
               f.recoverable_cents, l.raw_code AS code, p.raw_code AS paired
        FROM flow2_findings f
        LEFT JOIN bill_lines l ON f.line_id = l.line_id
        LEFT JOIN bill_lines p ON f.paired_line_id = p.line_id
        WHERE f.case_id = ?
        """,
        (case_id,),
    ).fetchall()
    res: list[dict] = []
    for r in rows:
        t = r["finding_type"]
        if t == "unbundling_ptp":
            res.append(canonical.ptp_finding(r["code"], r["paired"],
                                             r["ptp_modifier_indicator"], r["recoverable_cents"]))
        elif t == "quantity_mue":
            res.append(canonical.mue_finding(r["code"], r["mue_cap"], r["units_over_cap"],
                                             r["recoverable_cents"]))
        elif t == "price_benchmark":
            res.append(canonical.pfs_finding(r["code"], r["pfs_setting"], r["benchmark_cents"],
                                             r["billed_multiple"], r["benchmark_tier"]))
        elif t == "facility_unbenchmarked":
            res.append(canonical.facility_finding(r["code"]))
    return canonical.sort_findings(res)


@pytest.mark.parametrize("fx", ALL, ids=[f["fixture_id"] for f in ALL])
def test_fixture(fx, env):
    if fx["flow"] != 2:
        pytest.skip("only Flow 2 fixtures implemented so far")
    from app import repo
    from app.codes import detect_code_type
    from app.flows import flow2

    app_conn, pilot_conn = env
    inp = fx["input"]
    case_id = repo.create_case(app_conn, "m1")
    repo.update_case(app_conn, case_id, problem_type=inp["problem_type"],
                     insurance_situation=inp["insurance_situation"])
    for ln in inp["bill_lines"]:
        repo.add_bill_line(app_conn, case_id, ln["line_no"], ln["raw_code"],
                           detected_code_type=detect_code_type(ln["raw_code"]),
                           units=ln["units"], billed_charge_cents=ln["billed_charge_cents"],
                           modifier=ln["modifier"], encounter_pos=ln["encounter_pos"])
    flow2.analyze(app_conn, pilot_conn, case_id)

    actual = _engine_findings(app_conn, case_id)
    expected = canonical.sort_findings(fx["expected"]["findings"])
    assert actual == expected, f"{fx['fixture_id']}\n actual={actual}\n expected={expected}"
