"""Flow 3 — ground ambulance primary-claim denial appeal (PRD §6.3, ground-only v1).

Air codes are intercepted at Stage 4 (intake) and never reach here. This engine:
  1. classifies the denial (the §5 router),
  2. grounds medical necessity in NCD 10.1 (binding for FFS/MA, persuasive for
     commercial/ERISA),
  3. routes the appeal pathway + deadline (Medicare or commercial appeal levels),
  4. computes the base-plus-mileage dollar anchor (floor when miles are missing),
  5. renders the ground NSA-carve-out honesty node, and
  6. assembles the appeal package (letter counsel-gated; NSA content suppressed).
"""

from __future__ import annotations

import json
import sqlite3
from datetime import date, timedelta

from .. import pilot, repo
from .. import router as denial_router
from ..answer_card import AnswerCard, Citation, Finding, HonestyNode, Pathway, dollars
from ..config import feature_flags

# insurance_situation → (flow3 segment, ncd_weight, framework, plan_key)
_SEGMENT = {
    "medicare_ffs": ("medicare_ffs", "binding", "medicare", "traditional_medicare"),
    "medicare_advantage": ("medicare_advantage", "binding", "medicare", "medicare_advantage"),
    "commercial_aca": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
    "employer_erisa": ("commercial_aca", "persuasive", "commercial", "self_funded_erisa"),
    # self_pay/medicaid shouldn't reach Flow 3; treat as commercial-persuasive fallback.
    "self_pay": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
    "medicaid": ("commercial_aca", "persuasive", "commercial", "fully_insured"),
}


def _compute_deadline(denial_letter_date: str | None, days: int | None) -> str | None:
    if not denial_letter_date or not days:
        return None
    try:
        d = date.fromisoformat(denial_letter_date[:10])
    except ValueError:
        return None
    return (d + timedelta(days=days)).isoformat()


def _pick_appeal_level(pilot_conn, framework: str, plan_key: str) -> dict | None:
    if framework == "medicare":
        levels = pilot.medicare_appeal_levels(pilot_conn, plan_key)
        return levels[0] if levels else None
    levels = pilot.commercial_appeal_levels(pilot_conn)
    for lv in levels:
        try:
            applicable = json.loads(lv.get("applicable_plan_types") or "[]")
        except (ValueError, TypeError):
            applicable = []
        if plan_key in applicable:
            return lv
    return levels[0] if levels else None


def analyze(app_conn: sqlite3.Connection, pilot_conn: sqlite3.Connection, case_id: int) -> AnswerCard:
    case = repo.get_case(app_conn, case_id)
    claim = app_conn.execute(
        "SELECT * FROM ambulance_claims WHERE case_id = ?", (case_id,)
    ).fetchone()
    claim = dict(claim) if claim else {}
    ctx = json.loads(case.get("machine_context") or "{}")
    state = ctx.get("ambulance_state")

    segment, ncd_weight, framework, plan_key = _SEGMENT.get(
        case["insurance_situation"] or "", _SEGMENT["commercial_aca"]
    )

    findings: list[Finding] = []
    citations: list[tuple[str, str]] = []   # (source_type, source_ref) for appeal_citations

    # 1) Denial classification --------------------------------------------
    denials = repo.get_denial_codes(app_conn, case_id)
    denial_basis = None
    for d in denials:
        decision = denial_router.route_denial_code(
            app_conn, pilot_conn, d["code"], d["code_type"],
            insurance_situation=case["insurance_situation"], problem_type="denial_appeal",
        )
        if decision.action == "appeal" or denial_basis is None:
            denial_basis = f"{d['code_type']} {d['code']}"
            copy = decision.copy
            # Prefer the plain-English copy when authored (matches Flow 1); fall back
            # to the payer's official wording. Append practical context if present.
            text = copy.plain_explanation or copy.official_text or "Denied by the payer."
            if copy.practical_meaning:
                text = f"{text} {copy.practical_meaning}"
            findings.append(Finding(
                title=f"Denied on {denial_basis}",
                text=text,
                tone="error",
                citation=Citation("code_explanation", denial_basis, f"source · {denial_basis}"),
            ))
            if decision.action == "appeal":
                break

    # 2) NCD 10.1 medical-necessity grounding ------------------------------
    covered = pilot.ncd_ambulance(pilot_conn, coverage_indicator="covered")
    if covered:
        ncd = covered[0]
        weight_txt = ("the governing standard" if ncd_weight == "binding"
                      else "persuasive authority alongside your plan's medical policy")
        findings.append(Finding(
            title=f"Meets NCD 10.1 — {ncd['section_title']}",
            text=f"Coverage criteria support a medically necessary transport. For your plan this "
                 f"is {weight_txt}.",
            tone="ok",
            citation=Citation("ncd", ncd["section_id"], "NCD 10.1 · reviewed"),
        ))
        citations.append(("ncd", ncd["section_id"]))

    # 3) Pathway + deadline -------------------------------------------------
    level = _pick_appeal_level(pilot_conn, framework, plan_key)
    pathway = None
    filing_deadline = None
    appeal_level_ref = None
    if level:
        appeal_level_ref = level["level_name"]
        days = level.get("filing_deadline_days")
        filing_deadline = _compute_deadline(claim.get("denial_letter_date"), days)
        if filing_deadline:
            detail = f"File by {filing_deadline}" + (f" ({days} days)." if days else ".")
        elif days:
            detail = f"File within {days} days of your denial-letter date."
        else:
            detail = "Refer to your plan's Evidence of Coverage for the filing deadline."
        pathway = Pathway(
            label=f"Level {level['level_number']} — {level['level_name']}",
            detail=detail,
            caveat="Always verify the current deadline on your denial letter before filing.",
        )
        src = "medicare_appeal_level" if framework == "medicare" else "commercial_appeal_level"
        citations.append((src, str(level.get("level_number"))))

    # 4) Dollar anchor (base + per-mile × loaded miles; floor if miles missing)
    hcpcs = (claim.get("transport_hcpcs") or "").upper()
    base = pilot.ambulance_base_rate(pilot_conn, hcpcs, state) if state else None
    per_mile = pilot.ambulance_mileage_rate(pilot_conn, state) if state else None
    miles = claim.get("loaded_miles")
    reasonable = None
    anchor_is_floor = 0
    if base is not None:
        if miles and per_mile:
            reasonable = base + round(per_mile * miles)
            findings.append(Finding(
                title="Medicare reasonable amount",
                text=f"Medicare pays a base rate for this level of ambulance service, plus a set "
                     f"amount for each mile you were actually carried (your “loaded miles”). "
                     f"Here: base {dollars(base)} + {miles:g} loaded miles × {dollars(per_mile)}/mile "
                     f"({dollars(round(per_mile * miles))}) = {dollars(reasonable)}.",
                tone="neutral",
                citation=Citation("ambulance_fs", f"{hcpcs}@{state}", f"Ambulance FS · {state}"),
            ))
        else:
            reasonable = base
            anchor_is_floor = 1
            findings.append(Finding(
                title="Medicare reasonable amount (floor)",
                text=f"Medicare pays a base rate for this level of service plus a set amount per "
                     f"“loaded mile” (the miles you were actually carried). Without your "
                     f"mileage this is the base rate only — at least {dollars(base)}; it will be "
                     f"higher once loaded miles are added.",
                tone="neutral",
                citation=Citation("ambulance_fs", f"{hcpcs}@{state}", f"Ambulance FS · {state}"),
            ))
        citations.append(("ambulance_fs", f"{hcpcs}@{state}"))

    # 5) Ground NSA-carve-out honesty node (ground only — never for air) ----
    honesty = HonestyNode(
        text="Ground ambulance isn't covered by the federal No Surprises Act — so this appeal "
             "rests on medical necessity and your plan terms, not surprise-billing protections."
    )

    # 6) Persist the appeal package (letter counsel-gated; NSA suppressed) ---
    letter_status = ("draft" if feature_flags().get("appeal_letter_generation_enabled")
                     else "pending_counsel_review")
    repo.upsert_flow3_appeal(
        app_conn, case_id, segment, ncd_weight, denial_basis=denial_basis,
        appeal_level_ref=appeal_level_ref, filing_deadline=filing_deadline,
        base_rate_cents=base, per_mile_rate_cents=per_mile, loaded_miles_used=miles,
        reasonable_amount_cents=reasonable, anchor_is_floor=anchor_is_floor,
        letter_status=letter_status, nsa_content_suppressed=1,
    )
    for source_type, source_ref in citations:
        repo.add_appeal_citation(app_conn, case_id, source_type, source_ref,
                                 was_approved=1 if source_type == "ncd" else None)

    number_label = "Medicare reasonable amount" + (" (floor)" if anchor_is_floor else "")
    return AnswerCard(
        flow="flow3_appeal",
        eyebrow="This denial looks appealable",
        headline="Your transport appears to meet Medicare's medical-necessity criteria.",
        number_cents=reasonable,
        number_label=number_label if reasonable is not None else None,
        number_display=(f"≈ {dollars(reasonable)}" if reasonable is not None else None),
        findings=findings,
        pathway=pathway,
        honesty_node=honesty,
        next_action="Generate my appeal letter",
        framing_note="Appeal letters are reviewed before they're finalized. Coverage decisions "
                     "remain your plan's.",
        escalation_offered=True,
        gated_content_note=None,   # ground appeals never cite NSA → nothing suppressed to note
    )
