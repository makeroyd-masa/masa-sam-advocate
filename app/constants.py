"""Shared domain constants.

Ambulance scope (PRD §6.3, §10 #11 — ground-only v1). These sets are the single
source of truth for the Stage-4 ground/air split, reused by intake and Flow 3.
"""

from __future__ import annotations

# Ground level-of-service codes that run the ground appeal flow.
GROUND_LOS_CODES: frozenset[str] = frozenset(
    {"A0426", "A0427", "A0428", "A0429", "A0432", "A0433", "A0434"}
)
# Ground mileage code — its fee-schedule rate is the per-mile rate (≈$9.15 nat'l).
GROUND_MILEAGE_CODE: str = "A0425"

GROUND_CODES: frozenset[str] = GROUND_LOS_CODES | {GROUND_MILEAGE_CODE}

# Air codes. Present in the fee schedule (A0430/A0431) or absent (A0435/A0436),
# but ALL are out of scope for v1: detected at Stage 4 and routed to the
# human-advocate handoff. Never run the ground flow; never assert NSA protections.
AIR_CODES: frozenset[str] = frozenset({"A0430", "A0431", "A0435", "A0436"})


def ambulance_scope(hcpcs: str) -> str:
    """Classify a transport HCPCS: 'ground_los' | 'ground_mileage' | 'air' | 'unknown'."""
    code = (hcpcs or "").strip().upper()
    if code in GROUND_LOS_CODES:
        return "ground_los"
    if code == GROUND_MILEAGE_CODE:
        return "ground_mileage"
    if code in AIR_CODES:
        return "air"
    return "unknown"
