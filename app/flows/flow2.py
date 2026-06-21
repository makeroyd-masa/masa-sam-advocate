"""Flow 2 — error / overcharge detection + savings (PRD §6.2).

Three independent checks, kept distinct in the output:
  1. Unbundling (NCCI PTP) — disallowed code pairs with no valid modifier.
  2. Quantity (NCCI MUE) — units over the per-code daily cap.
  3. Price benchmark (PFS) — billed ÷ Medicare rate, POS-driven column, tiered.

Two honest savings tiers: recoverable likely-errors (PTP + MUE) vs above-benchmark
negotiation leverage (PFS multiple, never framed as "owed"). Un-benchmarkable
facility lines are logged so the coverage gap is measurable. The above-benchmark
call-to-action is situation-aware (self-pay/balance-bill actionable vs insured
context).
"""

from __future__ import annotations

import sqlite3
from itertools import combinations

from .. import pilot, repo
from ..answer_card import AnswerCard, Citation, Finding, dollars
from ..config import pos_facility_map, pricing_thresholds


def pos_setting(pos: str | None) -> str:
    """POS code → 'facility' | 'non_facility' (PRD §6.2; CMS PE-RVU rule)."""
    cfg = pos_facility_map()
    code = (pos or "").strip()
    if code and code in cfg.get("facility", {}):
        return "facility"
    if code and code in cfg.get("non_facility", {}):
        return "non_facility"
    return cfg.get("default", "non_facility")


def tier_for(multiple: float) -> dict:
    """Map a billed/benchmark multiple to a pricing tier (first matching band)."""
    for band in pricing_thresholds()["tiers"]:
        mx = band["max_multiple"]
        if mx is None or multiple < mx:
            return band
    return pricing_thresholds()["tiers"][-1]


def _line_by_code(lines: list[dict], code: str) -> dict | None:
    return next((ln for ln in lines if (ln["raw_code"] or "").upper() == code.upper()), None)


def analyze(app_conn: sqlite3.Connection, pilot_conn: sqlite3.Connection, case_id: int) -> AnswerCard:
    case = repo.get_case(app_conn, case_id)
    lines = repo.get_bill_lines(app_conn, case_id)
    is_self_pay = case["insurance_situation"] == "self_pay" or case["problem_type"] == "balance_bill"

    findings: list[Finding] = []
    recoverable_total = 0
    top_multiple = 0.0
    suggest_escalation = False

    # --- 1) Unbundling (NCCI PTP) over every code pair ---------------------
    flagged_pairs: set[frozenset[str]] = set()
    for a, b in combinations(lines, 2):
        edit = pilot.ptp_edit(pilot_conn, a["raw_code"], b["raw_code"])
        if not edit or edit["modifier_indicator"] == 9:
            continue
        disallowed = _line_by_code(lines, edit["column_two_code"])
        other = _line_by_code(lines, edit["column_one_code"])
        if not disallowed:
            continue
        ind = edit["modifier_indicator"]
        has_modifier = bool((disallowed.get("modifier") or "").strip())
        # 0 = never allowed; 1 = allowed only with an appropriate modifier.
        if ind == 1 and has_modifier:
            continue
        key = frozenset({a["raw_code"], b["raw_code"]})
        if key in flagged_pairs:
            continue
        flagged_pairs.add(key)
        recoverable = disallowed.get("billed_charge_cents") or 0
        recoverable_total += recoverable
        repo.add_flow2_finding(
            app_conn, case_id, "unbundling_ptp", "likely_error_recoverable",
            line_id=disallowed["line_id"], paired_line_id=other["line_id"] if other else None,
            ptp_modifier_indicator=ind, recoverable_cents=recoverable,
        )
        findings.append(Finding(
            title=f"Possible unbundling — {edit['column_one_code']} + {edit['column_two_code']}",
            text=f"These appear to be billed separately when one includes the other. "
                 f"The {edit['column_two_code']} line ({dollars(recoverable)}) can be questioned.",
            tone="error",
            citation=Citation("ncci_ptp",
                              edit["edit_id"] or f"{edit['column_one_code']}/{edit['column_two_code']}",
                              f"NCCI PTP · indicator {ind}"),
        ))

    # --- 2) Quantity (NCCI MUE) per line -----------------------------------
    for ln in lines:
        units = ln.get("units")
        cap = pilot.mue_cap(pilot_conn, ln["raw_code"])
        if not cap or not units or units <= cap["mue_value"]:
            continue
        excess = units - cap["mue_value"]
        charge = ln.get("billed_charge_cents") or 0
        per_unit = charge // units if units else 0
        recoverable = per_unit * excess
        recoverable_total += recoverable
        repo.add_flow2_finding(
            app_conn, case_id, "quantity_mue", "likely_error_recoverable",
            line_id=ln["line_id"], mue_cap=cap["mue_value"], units_over_cap=excess,
            recoverable_cents=recoverable,
        )
        findings.append(Finding(
            title=f"Units over the daily cap — {ln['raw_code']}",
            text=f"Billed {units} units; the Medicare daily maximum is {cap['mue_value']}. "
                 f"The {excess} excess unit(s) (~{dollars(recoverable)}) can be questioned.",
            tone="error",
            citation=Citation("ncci_mue", ln["raw_code"], f"MUE cap {cap['mue_value']}"),
        ))

    # --- 3) Price benchmark (PFS) per professional line --------------------
    for ln in lines:
        charge = ln.get("billed_charge_cents")
        setting = pos_setting(ln.get("encounter_pos"))
        rate = pilot.pfs_rate(pilot_conn, ln["raw_code"], setting)
        bench = rate["benchmark_cents"] if rate else None
        if not bench:  # None or 0 → not benchmarkable here (facility/revenue line)
            repo.add_flow2_finding(
                app_conn, case_id, "facility_unbenchmarked", "above_benchmark_leverage",
                line_id=ln["line_id"],
            )
            continue
        if not charge:
            continue
        multiple = charge / bench
        band = tier_for(multiple)
        if not band["surface"]:
            continue
        top_multiple = max(top_multiple, multiple)
        suggest_escalation = suggest_escalation or bool(band.get("suggest_escalation"))
        repo.add_flow2_finding(
            app_conn, case_id, "price_benchmark", "above_benchmark_leverage",
            line_id=ln["line_id"], pfs_setting=setting, benchmark_cents=bench,
            billed_multiple=round(multiple, 2), benchmark_tier=band["tier"],
        )
        cta = ("a strong basis to ask for a reduction" if is_self_pay
               else "useful context — for an insured plan your share is set by the allowed amount, "
                    "not this gross charge")
        findings.append(Finding(
            title=f"{ln['raw_code']} billed at {dollars(charge)}",
            text=f"That's about {multiple:.1f}× the Medicare benchmark ({dollars(bench)}) — {cta}.",
            tone="leverage",
            citation=Citation("pfs", ln["raw_code"], f"PFS · {setting} · POS {ln.get('encounter_pos') or '—'}"),
        ))

    return _build_card(recoverable_total, top_multiple, findings, is_self_pay, suggest_escalation)


def _build_card(recoverable: int, top_multiple: float, findings: list[Finding],
                is_self_pay: bool, suggest_escalation: bool) -> AnswerCard:
    n = len([f for f in findings if f.tone in ("error", "leverage")])
    has_error = recoverable > 0
    has_leverage = top_multiple > 0

    if has_error and has_leverage:
        headline = (f"{dollars(recoverable)} looks like a billing error, and one line is "
                    f"≈{top_multiple:.1f}× the Medicare rate.")
    elif has_error:
        headline = f"{dollars(recoverable)} looks like a billing error worth disputing."
    elif has_leverage:
        headline = f"One line is ≈{top_multiple:.1f}× the Medicare benchmark."
    else:
        headline = "I didn't find a clear billing error or overcharge on these lines."

    if has_error:
        next_action = "Send a correction request"
    elif has_leverage and is_self_pay:
        next_action = "Start a negotiation with this benchmark"
    else:
        next_action = "Talk to a human advocate" if has_leverage else None

    return AnswerCard(
        flow="flow2_error",
        eyebrow=f"I found {n} thing{'s' if n != 1 else ''} worth disputing" if n else "Error & overcharge check",
        headline=headline,
        number_cents=recoverable if has_error else None,
        number_label="likely error — ask to have removed" if has_error else None,
        number_display=dollars(recoverable) if has_error else None,
        number2_display=f"≈{top_multiple:.1f}×" if has_leverage else None,
        number2_label="over benchmark — negotiation leverage" if has_leverage else None,
        findings=findings,
        next_action=next_action,
        framing_note="These appear to be errors based on Medicare coding rules — not a final "
                     "determination of what you owe.",
        escalation_offered=True,
    )
