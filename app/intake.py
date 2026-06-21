"""Intake state-machine logic (PRD §4). Pure transition rules + Stage-4 scope
split; the API layer (app/routers/intake.py) wires these to persistence.

The machine is resumable: state lives in cases.current_stage + machine_context,
so the API only needs (problem_type, current_stage, insurance_situation) to know
what comes next.
"""

from __future__ import annotations

from .constants import ambulance_scope

# problem_type → active_flow once analysis runs.
PROBLEM_TO_FLOW = {
    "explain": "flow1_explain",
    "error_overcharge": "flow2_error",
    "denial_appeal": "flow3_appeal",
}

# After Stage 2 (bill-level capture), where each intent goes next.
_AFTER_STAGE2 = {
    "explain": "analysis",            # Flow 1; checkpoint may later add stage3
    "error_overcharge": "stage3_lines",
    "denial_appeal": "stage4_ambulance",
}


def next_stage(problem_type: str | None, current_stage: str) -> str:
    """Deterministic next stage for the linear intake path."""
    if current_stage == "stage0_intent":
        return "stage1_insurance"
    if current_stage == "stage1_insurance":
        return "stage2_bill"
    if current_stage == "stage2_bill":
        return _AFTER_STAGE2.get(problem_type or "", "analysis")
    if current_stage in ("stage3_lines", "stage3alt_no_codes", "stage4_ambulance"):
        return "analysis"
    if current_stage == "analysis":
        return "output"
    if current_stage == "output":
        return "done"
    return current_stage


def is_medicaid_shortcircuit(insurance_situation: str | None) -> bool:
    """Medicaid always routes to the Medicaid pathway (Workflow 5), which is not
    built in the prototype → handled as a human-advocate handoff (PRD §3)."""
    return insurance_situation == "medicaid"


def classify_transport(transport_hcpcs: str) -> str:
    """Stage-4 ground/air split (ground-only v1). Returns:
    'ground' (run Flow 3) | 'air' (→ handoff) | 'unknown' (ask to clarify)."""
    scope = ambulance_scope(transport_hcpcs)
    if scope in ("ground_los", "ground_mileage"):
        return "ground"
    if scope == "air":
        return "air"
    return "unknown"
