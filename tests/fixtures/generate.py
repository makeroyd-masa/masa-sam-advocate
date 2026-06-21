"""Tier A ground-truth fixture generator (spec §2, §4, §7).

Introspects pilot.db (read-only), composes synthetic cases around REAL rows, and
writes each case plus an independently-computed expected output to committed
fixture files. Run rarely, by hand; never imports the engine (app.flows).

  python tests/fixtures/generate.py [--pilot-db data/pilot.db] [--seed 1337] [--demo]

Determinism: a fixed seed governs all sampling; output JSON is sorted and carries
no timestamps, so re-running against the same pilot.db is byte-identical.
"""

from __future__ import annotations

import argparse
import json
import random
import re
import sqlite3
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))                       # reference_calc, canonical
sys.path.insert(0, str(HERE.parent.parent))         # repo root → app/

import reference_calc  # noqa: E402

from app import pilot  # noqa: E402
from app.config import REPO_ROOT  # noqa: E402

GEN_VERSION = "0.2.0"
DATA_DIR = HERE / "data"
DEMO_DIR = HERE / "demo"
TOUCHED_TABLES = ["ncci_ptp_edits", "ncci_mue", "physician_fee_schedule", "codes",
                  "ambulance_fee_schedule", "ncd_ambulance", "medicare_appeal_levels",
                  "commercial_appeal_levels"]
CHARGES = [9500, 12000, 7500, 18000, 6000, 24000, 4500, 15000]  # deterministic cycle
GROUND_LOS = ["A0426", "A0427", "A0428", "A0429", "A0432", "A0433", "A0434"]
STATES = ["CA", "TX", "NY", "FL", "PA", "OH", "MI", "GA", "NC", "WA", "AZ", "CO"]
LOOKUP_TYPES = ["HCPCS", "ICD10CM", "ICD10PCS", "RevenueCode", "MSDRG", "NDC", "Modifier", "POS"]


def line(no, code, *, units=1, charge=None, modifier=None, pos=None) -> dict:
    return {"line_no": no, "raw_code": code, "units": units,
            "billed_charge_cents": charge, "modifier": modifier, "encounter_pos": pos}


def make(pilot_conn, fid, category, source_table, source_rows, lines,
         insurance="medicare_ffs") -> dict:
    expected = reference_calc.compute_flow2(pilot_conn, lines)
    return {
        "fixture_id": fid, "flow": 2, "category": category,
        "provenance": {"pilot_db_version": "see MANIFEST.json", "source_table": source_table,
                       "source_rows": [str(r) for r in source_rows]},
        "input": {"problem_type": "error_overcharge", "insurance_situation": insurance,
                  "bill_lines": lines},
        "expected": expected,
    }


# --- candidate pools (deterministically ordered) ----------------------------
def ptp_pool(conn, indicator, active):
    sql = ("SELECT edit_id, column_one_code, column_two_code FROM ncci_ptp_edits "
           "WHERE modifier_indicator = ? " + ("AND deletion_date IS NULL " if active else "")
           + "ORDER BY edit_id LIMIT 3000")
    return conn.execute(sql, (indicator,)).fetchall()


def hcpcs_pool(conn):
    return [r[0] for r in conn.execute(
        "SELECT code FROM codes WHERE code_type='HCPCS' AND code GLOB '[A-V][0-9][0-9][0-9][0-9]' "
        "ORDER BY code LIMIT 4000")]


def mue_pool(conn):
    return conn.execute(
        "SELECT hcpcs_code, mue_value FROM ncci_mue WHERE deletion_date IS NULL AND mue_value >= 1 "
        "ORDER BY hcpcs_code LIMIT 4000").fetchall()


def pfs_pool(conn):
    # Base (no-modifier) rows only — this is the row pfs_rate() benchmarks against,
    # so charges derived from non_fac_rate hit the intended multiple. Component rows
    # (modifier 26/TC) carry different rates and would desync the band.
    return conn.execute(
        "SELECT hcpcs, non_fac_rate, fac_rate FROM physician_fee_schedule "
        "WHERE status_code='A' AND non_fac_rate > 0 AND (modifier IS NULL OR modifier='') "
        "ORDER BY hcpcs LIMIT 6000").fetchall()


# --- builders ---------------------------------------------------------------
def build_unbundling(conn, rng) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}
    ind0 = rng.sample(ptp_pool(conn, 0, True), 15)
    ind1 = rng.sample(ptp_pool(conn, 1, True), 20)
    ind9 = ptp_pool(conn, 9, False)
    ind9 = rng.sample(ind9, min(5, len(ind9)))

    out["unbundling_indicator_0"] = [
        make(conn, f"flow2_unbundling_ind0_{i:03d}", "unbundling_indicator_0", "ncci_ptp_edits",
             [e[0]], [line(1, e[1], charge=CHARGES[i % len(CHARGES)]),
                      line(2, e[2], charge=CHARGES[(i + 3) % len(CHARGES)])])
        for i, e in enumerate(ind0, 1)
    ]
    out["unbundling_indicator_1_no_modifier"] = [
        make(conn, f"flow2_unbundling_ind1_nomod_{i:03d}", "unbundling_indicator_1_no_modifier",
             "ncci_ptp_edits", [e[0]],
             [line(1, e[1], charge=CHARGES[i % len(CHARGES)]),
              line(2, e[2], charge=CHARGES[(i + 3) % len(CHARGES)])])
        for i, e in enumerate(ind1[:10], 1)
    ]
    out["unbundling_indicator_1_valid_modifier"] = [
        make(conn, f"flow2_unbundling_ind1_mod_{i:03d}", "unbundling_indicator_1_valid_modifier",
             "ncci_ptp_edits", [e[0]],
             [line(1, e[1], charge=CHARGES[i % len(CHARGES)]),
              line(2, e[2], charge=CHARGES[(i + 3) % len(CHARGES)], modifier="59")])
        for i, e in enumerate(ind1[10:20], 1)
    ]
    out["unbundling_indicator_9"] = [
        make(conn, f"flow2_unbundling_ind9_{i:03d}", "unbundling_indicator_9", "ncci_ptp_edits",
             [e[0]], [line(1, e[1], charge=CHARGES[i % len(CHARGES)]),
                      line(2, e[2], charge=CHARGES[(i + 3) % len(CHARGES)])])
        for i, e in enumerate(ind9, 1)
    ]

    # pair absent: two HCPCS codes with no PTP edit in either order (active or not)
    pool = hcpcs_pool(conn)
    rng.shuffle(pool)
    absent, idx = [], 0
    while len(absent) < 10 and idx + 1 < len(pool):
        a, b = pool[idx], pool[idx + 1]
        idx += 2
        from app import pilot
        if pilot.ptp_edit(conn, a, b, active_only=False) is None:
            absent.append((a, b))
    out["unbundling_pair_absent"] = [
        make(conn, f"flow2_unbundling_absent_{i:03d}", "unbundling_pair_absent", "codes",
             [a, b], [line(1, a, charge=CHARGES[i % len(CHARGES)]),
                      line(2, b, charge=CHARGES[(i + 2) % len(CHARGES)])])
        for i, (a, b) in enumerate(absent, 1)
    ]
    return out


def build_mue(conn, rng) -> dict[str, list[dict]]:
    pool = mue_pool(conn)
    at_cap = rng.sample(pool, 10)
    cap1 = rng.sample(pool, 10)
    over = rng.sample(pool, 10)
    PU = 3000  # per-unit charge so charge // units == PU exactly
    out = {}
    out["mue_at_cap"] = [
        make(conn, f"flow2_mue_atcap_{i:03d}", "mue_at_cap", "ncci_mue", [c],
             [line(1, c, units=cap, charge=cap * PU)])
        for i, (c, cap) in enumerate(at_cap, 1)
    ]
    out["mue_cap_plus_1"] = [
        make(conn, f"flow2_mue_cap1_{i:03d}", "mue_cap_plus_1", "ncci_mue", [c],
             [line(1, c, units=cap + 1, charge=(cap + 1) * PU)])
        for i, (c, cap) in enumerate(cap1, 1)
    ]
    out["mue_over_cap"] = [
        make(conn, f"flow2_mue_over_{i:03d}", "mue_over_cap", "ncci_mue", [c],
             [line(1, c, units=cap + 2 + (i % 3), charge=(cap + 2 + (i % 3)) * PU)])
        for i, (c, cap) in enumerate(over, 1)
    ]
    return out


def build_pfs(conn, rng) -> dict[str, list[dict]]:
    pool = pfs_pool(conn)
    bands = [("pfs_sub_2x", 1.5, 10), ("pfs_2_3x", 2.5, 8),
             ("pfs_3_5x", 4.0, 8), ("pfs_5x_plus", 6.0, 8)]
    out = {}
    for cat, mult, n in bands:
        picks = rng.sample(pool, n)
        out[cat] = [
            make(conn, f"{cat}_{i:03d}", cat, "physician_fee_schedule", [hc],
                 [line(1, hc, charge=round(nonfac * mult), pos="11")])
            for i, (hc, nonfac, _fac) in enumerate(picks, 1)
        ]

    # POS column flip: codes where facility != non-facility; one fixture per setting.
    flip_pool = [r for r in pool if r[2] and r[2] > 0 and r[2] != r[1]]
    flip = rng.sample(flip_pool, 3)
    flip_fx = []
    for i, (hc, nonfac, fac) in enumerate(flip, 1):
        charge = round(max(nonfac, fac) * 4.0)
        flip_fx.append(make(conn, f"flow2_pfs_posflip_office_{i:03d}", "pfs_pos_flip",
                            "physician_fee_schedule", [hc], [line(1, hc, charge=charge, pos="11")]))
        flip_fx.append(make(conn, f"flow2_pfs_posflip_hospital_{i:03d}", "pfs_pos_flip",
                            "physician_fee_schedule", [hc], [line(1, hc, charge=charge, pos="21")]))
    out["pfs_pos_flip"] = flip_fx

    # CPT-numbered: 5-digit PFS codes not present in `codes` (no AMA description stored)
    in_codes = {r[0] for r in conn.execute("SELECT code FROM codes WHERE code_type='HCPCS'")}
    cpt_pool = [r for r in pool if re.fullmatch(r"\d{5}", r[0]) and r[0] not in in_codes]
    cpt = rng.sample(cpt_pool, min(5, len(cpt_pool)))
    out["pfs_cpt_numbered"] = [
        make(conn, f"flow2_pfs_cpt_{i:03d}", "pfs_cpt_numbered", "physician_fee_schedule", [hc],
             [line(1, hc, charge=round(nonfac * 2.5), pos="11")])
        for i, (hc, nonfac, _fac) in enumerate(cpt, 1)
    ]
    return out


# --- Flow 1 -----------------------------------------------------------------
def make1(conn, fid, category, source_table, source_rows, *, bill=None, lines=None,
          denials=None, insurance="medicare_ffs") -> dict:
    bill, lines, denials = bill or {}, lines or [], denials or []
    expected = reference_calc.compute_flow1(conn, bill, lines, denials, insurance)
    return {
        "fixture_id": fid, "flow": 1, "category": category,
        "provenance": {"pilot_db_version": "see MANIFEST.json", "source_table": source_table,
                       "source_rows": [str(r) for r in source_rows]},
        "input": {"problem_type": "explain", "insurance_situation": insurance,
                  "bill_summary": bill, "denial_codes": denials, "bill_lines": lines},
        "expected": expected,
    }


def sample_code(conn, code_type):
    """First unambiguous code of a type that carries a description."""
    rows = conn.execute(
        "SELECT code FROM codes WHERE code_type=? AND (short_description IS NOT NULL "
        "OR description IS NOT NULL) ORDER BY code LIMIT 300", (code_type,)).fetchall()
    for (code,) in rows:
        info = pilot.lookup_code(conn, code)
        if info and not info["ambiguous"] and info["code_type"] == code_type:
            return code
    return None


def build_flow1(conn, rng) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}

    # code lookup — one unambiguous code per clinical code_type
    fx = []
    for i, ct in enumerate(LOOKUP_TYPES, 1):
        code = sample_code(conn, ct)
        if code:
            fx.append(make1(conn, f"flow1_lookup_{ct.lower()}_{i:03d}", "code_lookup", "codes",
                            [f"{ct}:{code}"], lines=[line(1, code)]))
    out["code_lookup"] = fx

    # CPT fallback — 5-digit PFS codes absent from `codes`
    in_codes = {r[0] for r in conn.execute("SELECT code FROM codes WHERE code_type='HCPCS'")}
    cpt = [r[0] for r in conn.execute(
        "SELECT DISTINCT hcpcs FROM physician_fee_schedule WHERE status_code='A' ORDER BY hcpcs")
        if re.fullmatch(r"\d{5}", r[0]) and r[0] not in in_codes][:3]
    out["cpt_lookup"] = [
        make1(conn, f"flow1_cpt_{i:03d}", "cpt_lookup", "physician_fee_schedule", [c],
              lines=[line(1, c)])
        for i, c in enumerate(cpt, 1)
    ]

    # CARC/RARC lookup — codes spanning routing actions
    denial_set = [("50", "CARC"), ("197", "CARC"), ("97", "CARC"),
                  ("18", "CARC"), ("16", "CARC"), ("N386", "RARC")]
    out["carc_rarc_lookup"] = [
        make1(conn, f"flow1_denial_{i:03d}", "carc_rarc_lookup", "codes", [f"{ct}:{c}"],
              bill={"total_billed_cents": 124000, "patient_responsibility_cents": 124000},
              denials=[{"code": c, "code_type": ct}])
        for i, (c, ct) in enumerate(denial_set, 1)
    ]

    # waterfall — consistent (plan_paid + resp == allowed) and broken (!=)
    cons, broke = [], []
    for i in range(8):
        allowed = 40000 + i * 5000
        resp = 8000 + i * 1000
        cons.append(make1(conn, f"flow1_waterfall_ok_{i+1:03d}", "waterfall_consistent", "synthetic",
                          ["n/a"], bill={"total_billed_cents": allowed + 50000,
                          "total_allowed_cents": allowed, "total_plan_paid_cents": allowed - resp,
                          "patient_responsibility_cents": resp}))
    for i in range(6):
        allowed = 50000 + i * 4000
        broke.append(make1(conn, f"flow1_waterfall_bad_{i+1:03d}", "waterfall_broken", "synthetic",
                           ["n/a"], bill={"total_billed_cents": allowed + 50000,
                           "total_allowed_cents": allowed, "total_plan_paid_cents": allowed - 9000,
                           "patient_responsibility_cents": 20000}))
    out["waterfall_consistent"] = cons
    out["waterfall_broken"] = broke
    return out


# --- Flow 3 -----------------------------------------------------------------
def make3_appeal(conn, fid, category, hcpcs, state, miles, insurance) -> dict:
    expected = reference_calc.compute_flow3(conn, hcpcs, state, miles, insurance)
    return {
        "fixture_id": fid, "flow": 3, "category": category,
        "provenance": {"pilot_db_version": "see MANIFEST.json", "source_table": "ambulance_fee_schedule",
                       "source_rows": [f"{hcpcs}@{state}", f"A0425@{state}"]},
        "input": {"problem_type": "denial_appeal", "insurance_situation": insurance, "state": state,
                  "ambulance_claim": {"transport_hcpcs": hcpcs, "loaded_miles": miles,
                                      "is_emergency": 1, "denial_letter_date": "2026-03-20"},
                  "denial_codes": [{"code": "50", "code_type": "CARC"}]},
        "expected": expected,
    }


def build_flow3(conn, rng) -> dict[str, list[dict]]:
    out: dict[str, list[dict]] = {}

    def pick(n):
        return [(rng.choice(GROUND_LOS), rng.choice(STATES)) for _ in range(n)]

    out["ambulance_base_plus_mileage"] = [
        make3_appeal(conn, f"flow3_anchor_mileage_{i:03d}", "ambulance_base_plus_mileage",
                     hc, st, [8, 12, 20, 5][i % 4], "medicare_ffs")
        for i, (hc, st) in enumerate(pick(12), 1)
    ]
    out["ambulance_base_only"] = [
        make3_appeal(conn, f"flow3_anchor_floor_{i:03d}", "ambulance_base_only", hc, st, None,
                     "medicare_ffs")
        for i, (hc, st) in enumerate(pick(8), 1)
    ]

    # segment weighting
    seg = []
    for i, ins in enumerate(["medicare_ffs", "medicare_advantage", "medicare_ffs",
                             "medicare_advantage", "medicare_ffs", "medicare_advantage"], 1):
        hc, st = rng.choice(GROUND_LOS), rng.choice(STATES)
        seg.append(make3_appeal(conn, f"flow3_segment_med_{i:03d}", "segment_medicare", hc, st, 10, ins))
    for i, ins in enumerate(["commercial_aca", "employer_erisa", "commercial_aca", "employer_erisa"], 1):
        hc, st = rng.choice(GROUND_LOS), rng.choice(STATES)
        seg.append(make3_appeal(conn, f"flow3_segment_comm_{i:03d}", "segment_commercial", hc, st, 10, ins))
    out["segment_weighting"] = seg

    # denial routing (router-level)
    routing = [("50", "CARC", "medicare_ffs", False), ("197", "CARC", "medicare_ffs", False),
               ("97", "CARC", "medicare_ffs", False), ("18", "CARC", "commercial_aca", False),
               ("16", "CARC", "medicare_ffs", False), ("29", "CARC", "self_pay", True)]
    rfx = []
    for i, (c, ct, ins, billed) in enumerate(routing, 1):
        action, target = reference_calc.route_action(c, ct, insurance_situation=ins, member_billed=billed)
        rfx.append({
            "fixture_id": f"flow3_routing_{i:03d}", "flow": 3, "category": "denial_routing",
            "provenance": {"pilot_db_version": "see MANIFEST.json", "source_table": "codes",
                           "source_rows": [f"{ct}:{c}"]},
            "input": {"code": c, "code_type": ct, "insurance_situation": ins, "member_billed": billed},
            "expected": {"kind": "routing", "action": action, "target_flow": target},
        })
    out["denial_routing"] = rfx

    # air handoff
    out["air_handoff"] = [
        {"fixture_id": f"flow3_air_{i:03d}", "flow": 3, "category": "air_handoff",
         "provenance": {"pilot_db_version": "see MANIFEST.json", "source_table": "codes",
                        "source_rows": [code]},
         "input": {"transport_hcpcs": code},
         "expected": {"kind": "air", "routed_to_handoff": True}}
        for i, code in enumerate(["A0430", "A0431", "A0435", "A0436"], 1)
    ]
    return out


def build_manifest(conn, seed, counts) -> dict:
    sources = {}
    for t in TOUCHED_TABLES:
        entries = []
        for (sid,) in conn.execute(f"SELECT DISTINCT source_id FROM {t} ORDER BY source_id"):
            row = conn.execute(
                "SELECT file_hash, row_count FROM dataset_releases WHERE source_id = ?", (sid,)
            ).fetchone()
            entries.append({"source_id": sid,
                            "file_hash": row[0] if row else None,
                            "row_count": row[1] if row else None})
        sources[t] = entries
    return {"generator_version": GEN_VERSION, "seed": seed, "sources": sources,
            "fixture_counts": counts}


def write_json(path: Path, obj) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def write_demo(categories: dict[str, list[dict]]) -> None:
    """A curated, high-impact subset rendered as human-readable cards (spec §6)."""
    picks = [
        ("unbundling_indicator_0", "Unbundling (NCCI PTP), never-allowed pair"),
        ("mue_over_cap", "Quantity (NCCI MUE), over the daily cap"),
        ("pfs_5x_plus", "Price benchmark (PFS), strong leverage"),
    ]
    cards = []
    for cat, label in picks:
        for fx in categories.get(cat, [])[:1]:
            ls = fx["input"]["bill_lines"]
            enter = "; ".join(
                f"{l['raw_code']} ×{l['units']} @ ${ (l['billed_charge_cents'] or 0)/100:,.2f}"
                + (f" POS {l['encounter_pos']}" if l['encounter_pos'] else "")
                for l in ls)
            exp = fx["expected"]
            cards.append(
                f"Demo — {label}\n"
                f"Enter in SAM: {enter}\n"
                f"Expected: recoverable ${exp['recoverable_total_cents']/100:,.2f}"
                + (f", top multiple ≈{exp['leverage_top_multiple']}×" if exp['leverage_top_multiple'] else "")
                + f"\nSource: {fx['fixture_id']} (see MANIFEST.json)\n")

    for fx in categories.get("ambulance_base_plus_mileage", [])[:1]:
        c, e = fx["input"]["ambulance_claim"], fx["expected"]
        cards.append(
            "Demo — Ground ambulance appeal (base + mileage anchor)\n"
            f"Enter in SAM: transport {c['transport_hcpcs']}, {c['loaded_miles']} loaded miles, "
            f"state {fx['input']['state']}, denial CARC 50\n"
            f"Expected: Medicare reasonable amount ${e['reasonable_amount_cents']/100:,.2f} "
            f"(base ${e['base_rate_cents']/100:,.2f} + mileage); appeal pathway {e['appeal_level_ref']}\n"
            f"Source: {fx['fixture_id']} (see MANIFEST.json)\n")

    (DEMO_DIR).mkdir(parents=True, exist_ok=True)
    (DEMO_DIR / "sam_demo_pack.md").write_text(
        "# SAM demo pack — manual entry (Flows 1-3)\n\n" + "\n".join(cards), encoding="utf-8")


def main() -> int:
    ap = argparse.ArgumentParser(description="Tier A fixture generator (Flow 2).")
    ap.add_argument("--pilot-db", default=str(REPO_ROOT / "data" / "pilot.db"))
    ap.add_argument("--seed", type=int, default=1337)
    ap.add_argument("--demo", action="store_true", help="also emit the human-readable demo pack")
    args = ap.parse_args()

    conn = sqlite3.connect(f"file:{args.pilot_db}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    rng = random.Random(args.seed)

    categories: dict[str, list[dict]] = {}
    categories.update(build_unbundling(conn, rng))
    categories.update(build_mue(conn, rng))
    categories.update(build_pfs(conn, rng))
    categories.update(build_flow1(conn, rng))
    categories.update(build_flow3(conn, rng))

    counts = {}
    for cat, fixtures in sorted(categories.items()):
        flow = fixtures[0]["flow"]
        write_json(DATA_DIR / f"flow{flow}" / f"{cat}.json", fixtures)
        counts[cat] = len(fixtures)

    write_json(HERE / "MANIFEST.json", build_manifest(conn, args.seed, counts))
    if args.demo:
        write_demo(categories)

    total = sum(counts.values())
    conn.close()
    print(f"Wrote {total} fixtures across {len(counts)} categories -> {DATA_DIR}")
    for cat in sorted(counts):
        print(f"  {cat}: {counts[cat]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
