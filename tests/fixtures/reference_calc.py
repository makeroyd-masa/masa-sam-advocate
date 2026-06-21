"""Independent expected-output computation for fixtures (spec §3.1).

Re-derives expected findings from first principles using the pilot.db data layer
(app.pilot) and config (thresholds / POS map) — but DELIBERATELY does NOT import
or call app.flows (the engine under test). It is a separate implementation of the
same rules so the fixtures check the engine rather than mirror it.
"""

from __future__ import annotations

import sqlite3
from itertools import combinations

import canonical

from app import pilot
from app.config import pos_facility_map, pricing_thresholds


# --- independent reimplementations of the band/column rules (read config) ----
def pos_setting(pos: str | None) -> str:
    cfg = pos_facility_map()
    code = (pos or "").strip()
    if code and code in cfg.get("facility", {}):
        return "facility"
    if code and code in cfg.get("non_facility", {}):
        return "non_facility"
    return cfg.get("default", "non_facility")


def tier_for(multiple: float) -> dict:
    tiers = pricing_thresholds()["tiers"]
    for band in tiers:
        mx = band["max_multiple"]
        if mx is None or multiple < mx:
            return band
    return tiers[-1]


def _line_by_code(lines: list[dict], code: str) -> dict | None:
    return next((ln for ln in lines if (ln["raw_code"] or "").upper() == code.upper()), None)


def compute_flow2(pilot_conn: sqlite3.Connection, lines: list[dict]) -> dict:
    """Expected Flow 2 findings for a bill. `lines` are the structured intake
    line dicts (raw_code, units, billed_charge_cents, modifier, encounter_pos).

    Mirrors all three checks the engine runs over the whole bill (independently),
    so the expected set includes any incidental findings, not just the fixture's
    headline category."""
    findings: list[dict] = []

    # 1) Unbundling (NCCI PTP) — every unordered code pair, active subset.
    seen: set[frozenset[str]] = set()
    for a, b in combinations(lines, 2):
        edit = pilot.ptp_edit(pilot_conn, a["raw_code"], b["raw_code"])
        if not edit or edit["modifier_indicator"] == 9:
            continue
        disallowed = _line_by_code(lines, edit["column_two_code"])
        other = _line_by_code(lines, edit["column_one_code"])
        if not disallowed:
            continue
        ind = edit["modifier_indicator"]
        if ind == 1 and (disallowed.get("modifier") or "").strip():
            continue
        key = frozenset({a["raw_code"], b["raw_code"]})
        if key in seen:
            continue
        seen.add(key)
        findings.append(canonical.ptp_finding(
            disallowed["raw_code"], other["raw_code"] if other else None, ind,
            disallowed.get("billed_charge_cents") or 0,
        ))

    # 2) Quantity (NCCI MUE) — per line.
    for ln in lines:
        units = ln.get("units")
        cap = pilot.mue_cap(pilot_conn, ln["raw_code"])
        if not cap or not units or units <= cap["mue_value"]:
            continue
        excess = units - cap["mue_value"]
        charge = ln.get("billed_charge_cents") or 0
        per_unit = charge // units if units else 0
        findings.append(canonical.mue_finding(
            ln["raw_code"], cap["mue_value"], excess, per_unit * excess,
        ))

    # 3) Price benchmark (PFS) — per line (facility/revenue lines logged).
    for ln in lines:
        charge = ln.get("billed_charge_cents")
        setting = pos_setting(ln.get("encounter_pos"))
        rate = pilot.pfs_rate(pilot_conn, ln["raw_code"], setting)
        bench = rate["benchmark_cents"] if rate else None
        if not bench:
            findings.append(canonical.facility_finding(ln["raw_code"]))
            continue
        if not charge:
            continue
        multiple = charge / bench
        band = tier_for(multiple)
        if not band["surface"]:
            continue
        findings.append(canonical.pfs_finding(
            ln["raw_code"], setting, bench, multiple, band["tier"],
        ))

    findings = canonical.sort_findings(findings)
    recoverable_total = sum(
        f["recoverable_cents"] for f in findings if f["type"] in ("unbundling_ptp", "quantity_mue")
    )
    multiples = [f["billed_multiple"] for f in findings if f["type"] == "price_benchmark"]
    return {
        "findings": findings,
        "recoverable_total_cents": recoverable_total,
        "leverage_top_multiple": max(multiples) if multiples else None,
    }
