"""Intake API — the resumable Stage 0–4 (+3-alt) state machine (PRD §4, §1.4).

Each endpoint corresponds to a screen frame and writes its mapped app.db table,
then advances cases.current_stage and logs a case_event. Reads pilot.db only to
classify captured denial codes (the §5 router).
"""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import intake, repo, router as denial_router
from ..codes import detect_code_type, parse_denial_code
from ..config import escalation_config
from ..db import get_app_db, get_pilot_db
from ..schemas import (
    CaseState,
    CreateCaseReq,
    Stage0Req,
    Stage1Req,
    Stage2Req,
    Stage3Req,
    Stage4Req,
    StageResult,
)

api = APIRouter(prefix="/api/cases", tags=["intake"])


# --- helpers ---------------------------------------------------------------
def _case_or_404(conn: sqlite3.Connection, case_id: int) -> dict:
    case = repo.get_case(conn, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return case


def _state(case: dict) -> CaseState:
    return CaseState(**{k: case.get(k) for k in CaseState.model_fields})


def _advance(conn: sqlite3.Connection, case: dict, *, status: str | None = None,
             **updates) -> dict:
    """Apply field updates, advance to the computed next stage, log the transition."""
    from_stage = case["current_stage"]
    to_stage = intake.next_stage(updates.get("problem_type", case["problem_type"]), from_stage)
    fields = {**updates, "current_stage": to_stage}
    if status:
        fields["status"] = status
    repo.update_case(conn, case["case_id"], **fields)
    repo.log_event(conn, case["case_id"], "stage_complete",
                   from_stage=from_stage, to_stage=to_stage)
    return repo.get_case(conn, case["case_id"])


# --- create / resume -------------------------------------------------------
@api.post("", response_model=StageResult)
def create_case(req: CreateCaseReq, app_db: sqlite3.Connection = Depends(get_app_db)):
    # Ensure the member exists (prototype: host app provides identity in prod).
    repo.upsert_member(app_db, req.member_ref)
    case_id = repo.create_case(app_db, req.member_ref, entry_point=req.entry_point,
                               seed_intent=req.seed_intent)
    repo.log_event(app_db, case_id, "case_created", to_stage="stage0_intent",
                   detail={"entry_point": req.entry_point, "seed_intent": req.seed_intent})
    case = repo.get_case(app_db, case_id)
    return StageResult(case=_state(case), next_stage="stage0_intent",
                       message="Case created. Capture intent next (Stage 0).")


@api.get("/{case_id}", response_model=StageResult)
def get_case(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    return StageResult(case=_state(case),
                       next_stage=intake.next_stage(case["problem_type"], case["current_stage"]))


# --- Stage 0: intent -------------------------------------------------------
@api.post("/{case_id}/stage0", response_model=StageResult)
def stage0(case_id: int, req: Stage0Req, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    case = _advance(app_db, case, problem_type=req.problem_type,
                    active_flow=intake.PROBLEM_TO_FLOW[req.problem_type], status="intake")
    return StageResult(case=_state(case), next_stage=case["current_stage"])


# --- Stage 1: insurance situation (+ Medicaid short-circuit) ---------------
@api.post("/{case_id}/stage1", response_model=StageResult)
def stage1(case_id: int, req: Stage1Req, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    if req.plan_identifier:
        repo.upsert_member(app_db, case["member_ref"], plan_identifier=req.plan_identifier)

    if intake.is_medicaid_shortcircuit(req.insurance_situation):
        repo.update_case(app_db, case_id, insurance_situation=req.insurance_situation,
                         current_stage="done", status="handed_off")
        repo.create_handoff(app_db, case_id, reason="Medicaid pathway (Workflow 5) — "
                            "handled by a human advocate in the prototype.")
        repo.log_event(app_db, case_id, "handoff_requested",
                       from_stage="stage1_insurance", to_stage="done",
                       detail={"trigger": "medicaid_shortcircuit"})
        case = repo.get_case(app_db, case_id)
        return StageResult(case=_state(case), next_stage="done", routed_to_handoff=True,
                           message="Medicaid cases route to a human advocate in this version.")

    case = _advance(app_db, case, insurance_situation=req.insurance_situation)
    return StageResult(case=_state(case), next_stage=case["current_stage"])


# --- Stage 2: bill-level capture + denial codes ----------------------------
@api.post("/{case_id}/stage2", response_model=StageResult)
def stage2(case_id: int, req: Stage2Req, app_db: sqlite3.Connection = Depends(get_app_db),
           pilot_db: sqlite3.Connection = Depends(get_pilot_db)):
    case = _case_or_404(app_db, case_id)
    repo.upsert_bill_summary(
        app_db, case_id,
        provider_name=req.provider_name, date_of_service_start=req.date_of_service_start,
        date_of_service_end=req.date_of_service_end, total_billed_cents=req.total_billed_cents,
        total_allowed_cents=req.total_allowed_cents, total_plan_paid_cents=req.total_plan_paid_cents,
        patient_responsibility_cents=req.patient_responsibility_cents, notes=req.notes,
    )

    # Capture + classify any denial codes the member could read (the §5 dispatcher).
    member_billed = bool(req.patient_responsibility_cents and req.patient_responsibility_cents > 0)
    routing: list[dict] = []
    for raw in req.denial_codes:
        parsed = parse_denial_code(raw)
        if not parsed:
            continue
        code, code_type = parsed
        repo.add_denial_code(app_db, case_id, code, code_type, where_seen="bill_level")
        decision = denial_router.route_denial_code(
            app_db, pilot_db, code, code_type,
            insurance_situation=case["insurance_situation"],
            problem_type=case["problem_type"], member_billed=member_billed,
        )
        routing.append({"code": code, "code_type": code_type, "action": decision.action,
                        "target_flow": decision.target_flow,
                        "requires_handoff": decision.requires_handoff})

    case = _advance(app_db, case, machine_context={"denial_routing": routing})
    return StageResult(case=_state(case), next_stage=case["current_stage"],
                       detail={"denial_routing": routing})


# --- Stage 3: line-item capture --------------------------------------------
@api.post("/{case_id}/stage3", response_model=StageResult)
def stage3(case_id: int, req: Stage3Req, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    if not req.lines:
        raise HTTPException(status_code=422, detail="at least one bill line is required")
    for i, line in enumerate(req.lines, start=1):
        repo.add_bill_line(
            app_db, case_id, i, line.raw_code,
            detected_code_type=detect_code_type(line.raw_code),
            units=line.units, billed_charge_cents=line.billed_charge_cents,
            modifier=line.modifier, encounter_pos=line.encounter_pos,
        )
    case = _advance(app_db, case, status="analyzing")
    return StageResult(case=_state(case), next_stage=case["current_stage"],
                       message=f"Captured {len(req.lines)} line(s); ready for the error check.")


# --- Stage 3-alt: no itemized bill → request letter ------------------------
@api.post("/{case_id}/stage3alt", response_model=StageResult)
def stage3alt(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    repo.upsert_itemized_bill_request(app_db, case_id, letter_status="draft")
    repo.update_case(app_db, case_id, current_stage="stage3alt_no_codes",
                     status="awaiting_member_input")
    repo.log_event(app_db, case_id, "itemized_bill_requested",
                   from_stage=case["current_stage"], to_stage="stage3alt_no_codes")
    case = repo.get_case(app_db, case_id)
    return StageResult(case=_state(case), next_stage="stage3alt_no_codes",
                       message="We'll request the itemized bill and resume the audit when it arrives.")


# --- Stage 4: ambulance appeal capture (ground/air split) ------------------
@api.post("/{case_id}/stage4", response_model=StageResult)
def stage4(case_id: int, req: Stage4Req, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    kind = intake.classify_transport(req.transport_hcpcs)

    if kind == "air":
        reason = next((t["reason"] for t in escalation_config()["human_advocate"]["triggers"]
                       if t["id"] == "air_ambulance_out_of_scope"), "Air ambulance is out of scope.")
        repo.create_handoff(app_db, case_id, reason=reason)
        repo.update_case(app_db, case_id, current_stage="done", status="handed_off")
        repo.log_event(app_db, case_id, "handoff_requested", from_stage="stage4_ambulance",
                       to_stage="done", detail={"trigger": "air_ambulance_out_of_scope",
                                                "hcpcs": req.transport_hcpcs})
        case = repo.get_case(app_db, case_id)
        return StageResult(case=_state(case), next_stage="done", routed_to_handoff=True,
                           message="Air ambulance is handled differently and may involve federal "
                                   "protections — connecting you with a human advocate.")

    if kind == "unknown":
        return StageResult(case=_state(case), next_stage="stage4_ambulance",
                           needs_clarification=True,
                           message=f"'{req.transport_hcpcs}' isn't a recognized ground transport "
                                   "code (A0426–A0429, A0432–A0434, or A0425 mileage). Please check it.")

    # ground → persist the claim and move to analysis (Flow 3 runs in Phase 6)
    repo.upsert_ambulance_claim(
        app_db, case_id, transport_hcpcs=req.transport_hcpcs.strip().upper(),
        transport_modifier=req.transport_modifier, denial_letter_date=req.denial_letter_date,
        is_emergency=(None if req.is_emergency is None else int(req.is_emergency)),
        origin=req.origin, destination=req.destination, loaded_miles=req.loaded_miles,
    )
    if req.denial_code:
        parsed = parse_denial_code(req.denial_code)
        if parsed:
            repo.add_denial_code(app_db, case_id, parsed[0], parsed[1], where_seen="bill_level")
    if req.state:
        repo.update_case(app_db, case_id,
                         machine_context={**_machine_ctx(case), "ambulance_state": req.state.upper()})
    case = repo.get_case(app_db, case_id)
    case = _advance(app_db, case, status="analyzing")
    return StageResult(case=_state(case), next_stage=case["current_stage"],
                       message="Ground transport captured; ready to build the appeal.")


# --- checkpoint: explain → error check (progressive, PRD §4.1) -------------
@api.post("/{case_id}/checkpoint/accept", response_model=StageResult)
def accept_checkpoint(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db)):
    case = _case_or_404(app_db, case_id)
    repo.update_case(app_db, case_id, current_stage="stage3_lines",
                     active_flow="flow2_error", status="intake")
    repo.log_event(app_db, case_id, "checkpoint_accepted", to_stage="stage3_lines")
    case = repo.get_case(app_db, case_id)
    return StageResult(case=_state(case), next_stage="stage3_lines",
                       message="Add your bill lines and I'll check for errors & overcharges.")


def _machine_ctx(case: dict) -> dict:
    import json
    raw = case.get("machine_context")
    return json.loads(raw) if raw else {}
