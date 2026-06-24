"""Tier A fixture runner (spec §2). Loads committed fixtures, materializes each
`input` into a temp app.db (the same pattern as test_flow*.py), runs the engine,
and asserts the engine's findings equal the fixture's independently-computed
`expected`. One parametrized case per fixture id; does NOT require pilot.db unless
a fixture must be re-derived (Flow 2 reads pilot.db for benchmarks via the engine).
"""

import json
import os
import sqlite3
import sys
from pathlib import Path

import pytest

from conftest import apply_schema

TESTS = Path(__file__).resolve().parent
REPO_ROOT = TESTS.parent
FIX = TESTS / "fixtures"
sys.path.insert(0, str(FIX))

import canonical  # noqa: E402

SCHEMA = REPO_ROOT / "docs" / "app_schema_v0_1.sql"
DATA = FIX / "data"

# Resolve the reference DB: explicit override > real pilot.db > committed slim
# ci_pilot.db. The slim DB lets CI run the engine against the fixtures with no
# 1 GB dependency; locally the real pilot.db is used when present.
_REAL_PILOT = REPO_ROOT / "data" / "pilot.db"
_CI_PILOT = FIX / "ci_pilot.db"
if os.environ.get("SAM_PILOT_DB"):
    PILOT = Path(os.environ["SAM_PILOT_DB"])
elif _REAL_PILOT.exists():
    PILOT = _REAL_PILOT
else:
    PILOT = _CI_PILOT


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
    from app.loader import load_code_explanations
    app_path = tmp_path_factory.mktemp("fixtures") / "app.db"
    app_conn = sqlite3.connect(app_path)
    app_conn.row_factory = sqlite3.Row
    app_conn.execute("PRAGMA foreign_keys = ON")
    apply_schema(app_conn)
    repo.upsert_member(app_conn, "m1")
    pilot_conn = sqlite3.connect(f"file:{PILOT}?mode=ro", uri=True)
    pilot_conn.row_factory = sqlite3.Row
    load_code_explanations(app_conn, pilot_conn)   # Flow 1 / routing fixtures need it
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


import re  # noqa: E402


def _flow1_actual(card: dict, input_lines: list[dict]) -> dict:
    recon = None
    for f in card["findings"]:
        if f["title"] == "How your share was reached":
            recon = canonical.recon_category(f["text"])
            break
    lines = []
    for ln in input_lines:
        code = ln["raw_code"]
        f = next((x for x in card["findings"] if x["title"].startswith(code)), None)
        if f is None:
            lines.append({"code": code, "kind": "unrecognized", "description": None})
        elif "rate only" in f["title"]:
            lines.append({"code": code, "kind": "cpt_fallback", "description": None})
        elif "not recognized" in f["text"].lower():
            lines.append({"code": code, "kind": "unrecognized", "description": None})
        else:
            lines.append({"code": code, "kind": "described", "description": f["text"]})
    return {
        "number_cents": card["number_cents"],
        "reconciliation": recon,
        "appealable": "appealable" in card["headline"].lower(),
        "lines": lines,
        "denials_shown": sorted(x["title"] for x in card["findings"]
                                if re.match(r"^(CARC|RARC) ", x["title"])),
    }


def _run_flow1(fx, app_conn, pilot_conn):
    from app import repo
    from app.codes import detect_code_type
    from app.flows import flow1
    inp = fx["input"]
    cid = repo.create_case(app_conn, "m1")
    repo.update_case(app_conn, cid, problem_type="explain",
                     insurance_situation=inp["insurance_situation"])
    if inp.get("bill_summary"):
        repo.upsert_bill_summary(app_conn, cid, **inp["bill_summary"])
    for d in inp.get("denial_codes", []):
        repo.add_denial_code(app_conn, cid, d["code"], d["code_type"], where_seen="bill_level")
    for ln in inp.get("bill_lines", []):
        repo.add_bill_line(app_conn, cid, ln["line_no"], ln["raw_code"],
                           detected_code_type=detect_code_type(ln["raw_code"]),
                           units=ln.get("units"), billed_charge_cents=ln.get("billed_charge_cents"),
                           modifier=ln.get("modifier"), encounter_pos=ln.get("encounter_pos"))
    card = flow1.explain(app_conn, pilot_conn, cid).to_dict()
    return _flow1_actual(card, inp.get("bill_lines", []))


def _run_flow3(fx, app_conn, pilot_conn):
    kind = fx["expected"]["kind"]
    if kind == "air":
        from app.intake import classify_transport
        return {"kind": "air",
                "routed_to_handoff": classify_transport(fx["input"]["transport_hcpcs"]) == "air"}
    if kind == "routing":
        from app import router
        inp = fx["input"]
        d = router.route_denial_code(app_conn, pilot_conn, inp["code"], inp["code_type"],
                                     insurance_situation=inp["insurance_situation"],
                                     member_billed=inp["member_billed"])
        return {"kind": "routing", "action": d.action, "target_flow": d.target_flow}
    # appeal
    from app import repo
    from app.flows import flow3
    inp = fx["input"]
    claim = inp["ambulance_claim"]
    cid = repo.create_case(app_conn, "m1")
    repo.update_case(app_conn, cid, problem_type="denial_appeal",
                     insurance_situation=inp["insurance_situation"], active_flow="flow3_appeal",
                     machine_context={"ambulance_state": inp["state"]})
    repo.upsert_ambulance_claim(app_conn, cid, transport_hcpcs=claim["transport_hcpcs"],
                                loaded_miles=claim["loaded_miles"], is_emergency=claim["is_emergency"],
                                denial_letter_date=claim["denial_letter_date"])
    for d in inp.get("denial_codes", []):
        repo.add_denial_code(app_conn, cid, d["code"], d["code_type"], where_seen="bill_level")
    flow3.analyze(app_conn, pilot_conn, cid)
    r = app_conn.execute("SELECT * FROM flow3_appeals WHERE case_id = ?", (cid,)).fetchone()
    return {"kind": "appeal", "segment": r["segment"], "ncd_weight": r["ncd_weight"],
            "base_rate_cents": r["base_rate_cents"], "per_mile_rate_cents": r["per_mile_rate_cents"],
            "reasonable_amount_cents": r["reasonable_amount_cents"],
            "anchor_is_floor": r["anchor_is_floor"], "appeal_level_ref": r["appeal_level_ref"]}


@pytest.mark.parametrize("fx", ALL, ids=[f["fixture_id"] for f in ALL])
def test_fixture(fx, env):
    app_conn, pilot_conn = env

    if fx["flow"] == 2:
        from app import repo
        from app.codes import detect_code_type
        from app.flows import flow2
        inp = fx["input"]
        cid = repo.create_case(app_conn, "m1")
        repo.update_case(app_conn, cid, problem_type=inp["problem_type"],
                         insurance_situation=inp["insurance_situation"])
        for ln in inp["bill_lines"]:
            repo.add_bill_line(app_conn, cid, ln["line_no"], ln["raw_code"],
                               detected_code_type=detect_code_type(ln["raw_code"]),
                               units=ln["units"], billed_charge_cents=ln["billed_charge_cents"],
                               modifier=ln["modifier"], encounter_pos=ln["encounter_pos"])
        flow2.analyze(app_conn, pilot_conn, cid)
        actual = _engine_findings(app_conn, cid)
        expected = canonical.sort_findings(fx["expected"]["findings"])
    elif fx["flow"] == 1:
        actual = _run_flow1(fx, app_conn, pilot_conn)
        expected = fx["expected"]
    elif fx["flow"] == 3:
        actual = _run_flow3(fx, app_conn, pilot_conn)
        expected = fx["expected"]
    else:
        pytest.skip(f"flow {fx['flow']} not implemented")

    assert actual == expected, f"{fx['fixture_id']}\n actual={actual}\n expected={expected}"
