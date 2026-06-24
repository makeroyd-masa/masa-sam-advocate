"""Independent expected-output computation for fixtures (spec §3.1).

Re-derives expected findings from first principles using the pilot.db data layer
(app.pilot) and config (thresholds / POS map) — but DELIBERATELY does NOT import
or call app.flows (the engine under test). It is a separate implementation of the
same rules so the fixtures check the engine rather than mirror it.
"""

from __future__ import annotations

import sqlite3
from functools import lru_cache
from itertools import combinations

import canonical
import yaml

from app import pilot
from app.config import CONFIG_DIR, feature_flags, pos_facility_map, pricing_thresholds

# Independent copy of the §5 routing → flow map (mirrors app.router, not imported).
_ACTION_TO_FLOW = {
    "explain_only": "flow1_explain", "error_check": "flow2_error", "appeal": "flow3_appeal",
    "verify_with_payer": "none", "escalate_human": "none",
}
# insurance_situation → (flow3 segment, ncd_weight, framework, appeal plan_key)
_SEGMENT = {
    "medicare_ffs": ("medicare_ffs", "binding", "medicare", "traditional_medicare"),
    "medicare_advantage": ("medicare_advantage", "binding", "medicare", "medicare_advantage"),
    "commercial_aca": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
    "employer_erisa": ("commercial_aca", "persuasive", "commercial", "self_funded_erisa"),
    "self_pay": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
    "medicaid": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
}


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


# --- §5 routing (independent of app.router) ---------------------------------
@lru_cache
def _routing_map() -> dict:
    doc = yaml.safe_load((CONFIG_DIR / "carc_rarc_plain_english.yaml").read_text(encoding="utf-8"))
    return {(e["code"], e["code_type"]): e["suggested_action"] for e in doc["codes"]}


def route_action(code: str, code_type: str, *, insurance_situation: str | None = None,
                 problem_type: str | None = None, member_billed: bool = False) -> tuple[str, str]:
    """(effective_action, target_flow) for a denial code, with the locked overrides."""
    base = _routing_map().get((code, code_type))
    if base is None:
        return "explain_only", "flow1_explain"         # long tail
    action = base
    if code == "45" and code_type == "CARC" and (
        insurance_situation == "self_pay" or problem_type == "balance_bill"
    ):
        action = "error_check"
    elif code == "29" and code_type == "CARC" and member_billed:
        action = "escalate_human"
    return action, _ACTION_TO_FLOW[action]


# --- Flow 1 — explanation & reconciliation ----------------------------------
def _reconcile_category(bill: dict) -> str | None:
    b, a = bill.get("total_billed_cents"), bill.get("total_allowed_cents")
    p, r = bill.get("total_plan_paid_cents"), bill.get("patient_responsibility_cents")
    if b and r == b and (p or 0) == 0 and (a or 0) == 0:
        return "denied_claim"
    if a is not None and p is not None and r is not None:
        return "consistent" if p + r == a else "inconsistent"
    return None


def _classify_line(pilot_conn: sqlite3.Connection, raw_code: str) -> dict:
    from app.codes import detect_code_type
    info = pilot.lookup_code(pilot_conn, raw_code)
    if info and info["code_type"] not in ("CARC", "RARC"):
        desc = info["short_description"] or info["official_text"] or "(no description on file)"
        return {"code": raw_code, "kind": "described", "description": desc}
    if detect_code_type(raw_code) == "CPT":
        return {"code": raw_code, "kind": "cpt_fallback", "description": None}
    return {"code": raw_code, "kind": "unrecognized", "description": None}


_COST_SHARE_INSURED = ("employer_erisa", "commercial_aca")
_COINS_TOLERANCE_CENTS = 100


def compute_cost_share(bill: dict, insurance_situation: str | None,
                       has_denial_code: bool) -> list[dict]:
    """Independent reimplementation of app.flows.cost_share.check (engine not imported).
    Mirrors the LITE-scope checks (#1 reconciliation, #2 coinsurance rate, #5
    not-covered routing) and the same kill-switch + insured-only scope guard."""
    if not feature_flags().get("cost_share_check_enabled", False):
        return []
    if not bill or insurance_situation not in _COST_SHARE_INSURED:
        return []
    out: list[dict] = []
    parts = [bill.get(k) for k in ("copay_cents", "deductible_applied_cents",
                                   "coinsurance_cents", "not_covered_cents")]
    resp = bill.get("patient_responsibility_cents")
    if resp is not None and all(p is not None for p in parts) and sum(parts) != resp:
        out.append(canonical.cost_share_finding("reconciliation_gap"))
    rate, allowed = bill.get("coinsurance_rate_pct"), bill.get("total_allowed_cents")
    ded, coins = bill.get("deductible_applied_cents"), bill.get("coinsurance_cents")
    if None not in (rate, allowed, ded, coins):
        expected = round((rate / 100.0) * max(allowed - ded, 0))
        if abs(expected - coins) > _COINS_TOLERANCE_CENTS:
            out.append(canonical.cost_share_finding("coinsurance_mismatch"))
    nc = bill.get("not_covered_cents")
    if not has_denial_code and nc and nc > 0:
        out.append(canonical.cost_share_finding("not_covered"))
    return canonical.sort_cost_share(out)


def compute_flow1(pilot_conn: sqlite3.Connection, bill: dict, lines: list[dict],
                  denials: list[dict], insurance_situation: str | None) -> dict:
    member_billed = bool((bill.get("patient_responsibility_cents") or 0) > 0)
    appealable = any(
        route_action(d["code"], d["code_type"], insurance_situation=insurance_situation,
                     problem_type="explain", member_billed=member_billed)[0] == "appeal"
        for d in denials
    )
    return {
        "number_cents": bill.get("patient_responsibility_cents"),
        "reconciliation": _reconcile_category(bill),
        "appealable": appealable,
        "lines": [_classify_line(pilot_conn, ln["raw_code"]) for ln in lines],
        "denials_shown": sorted(f"{d['code_type']} {d['code']}" for d in denials),
        "cost_share": compute_cost_share(bill, insurance_situation, bool(denials)),
    }


# --- Flow 3 — ground ambulance appeal ---------------------------------------
def _appeal_level_ref(pilot_conn, framework: str, plan_key: str) -> str | None:
    if framework == "medicare":
        levels = pilot.medicare_appeal_levels(pilot_conn, plan_key)
        return levels[0]["level_name"] if levels else None
    import json as _json
    for lv in pilot.commercial_appeal_levels(pilot_conn):
        try:
            applicable = _json.loads(lv.get("applicable_plan_types") or "[]")
        except (ValueError, TypeError):
            applicable = []
        if plan_key in applicable:
            return lv["level_name"]
    levels = pilot.commercial_appeal_levels(pilot_conn)
    return levels[0]["level_name"] if levels else None


def compute_flow3(pilot_conn: sqlite3.Connection, transport_hcpcs: str, state: str,
                  loaded_miles: float | None, insurance_situation: str) -> dict:
    segment, ncd_weight, framework, plan_key = _SEGMENT.get(
        insurance_situation, _SEGMENT["commercial_aca"]
    )
    base = pilot.ambulance_base_rate(pilot_conn, transport_hcpcs.upper(), state)
    per_mile = pilot.ambulance_mileage_rate(pilot_conn, state)
    reasonable, floor = None, 0
    if base is not None:
        if loaded_miles and per_mile:
            reasonable = base + round(per_mile * loaded_miles)
        else:
            reasonable, floor = base, 1
    return {
        "kind": "appeal",
        "segment": segment,
        "ncd_weight": ncd_weight,
        "base_rate_cents": base,
        "per_mile_rate_cents": per_mile,
        "reasonable_amount_cents": reasonable,
        "anchor_is_floor": floor,
        "appeal_level_ref": _appeal_level_ref(pilot_conn, framework, plan_key),
    }
