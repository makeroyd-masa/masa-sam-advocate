"""Pydantic request/response models for the intake API (PRD §4 / §1.4 frames).

Enum literals mirror the CHECK constraints in docs/app_schema_v0_1.sql.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ProblemType = Literal["explain", "error_overcharge", "denial_appeal"]
InsuranceSituation = Literal[
    "medicare_ffs", "medicare_advantage", "commercial_aca",
    "employer_erisa", "medicaid", "self_pay",
]

DEV_MEMBER_REF = "dev-member-001"


class CreateCaseReq(BaseModel):
    member_ref: str = DEV_MEMBER_REF
    entry_point: str | None = None      # 'fab_global','claims','plan','payments','overview'
    seed_intent: str | None = None


class CaseState(BaseModel):
    case_id: int
    member_ref: str
    problem_type: str | None = None
    insurance_situation: str | None = None
    active_flow: str | None = None
    current_stage: str
    status: str
    entry_point: str | None = None
    seed_intent: str | None = None


class Stage0Req(BaseModel):
    problem_type: ProblemType


class Stage1Req(BaseModel):
    insurance_situation: InsuranceSituation
    plan_identifier: str | None = None


class Stage2Req(BaseModel):
    provider_name: str | None = None
    date_of_service_start: str | None = None
    date_of_service_end: str | None = None
    total_billed_cents: int | None = None
    total_allowed_cents: int | None = None
    total_plan_paid_cents: int | None = None
    patient_responsibility_cents: int | None = None
    notes: str | None = None
    denial_codes: list[str] = Field(default_factory=list)   # free text, e.g. ["CARC 50"]
    # Cost-share breakdown the member can read off a transparent EOB (PRD addendum:
    # cost-share v0.1). All optional; powers the Flow 1 cost-share check.
    copay_cents: int | None = None
    deductible_applied_cents: int | None = None
    coinsurance_cents: int | None = None
    not_covered_cents: int | None = None
    discount_cents: int | None = None
    coinsurance_rate_pct: float | None = None


class BillLineIn(BaseModel):
    raw_code: str
    units: int | None = None
    billed_charge_cents: int | None = None
    modifier: str | None = None
    encounter_pos: str | None = None


class Stage3Req(BaseModel):
    lines: list[BillLineIn]


class Stage4Req(BaseModel):
    transport_hcpcs: str
    transport_modifier: str | None = None
    denial_code: str | None = None       # free text, e.g. "CARC 50"
    denial_letter_date: str | None = None
    is_emergency: bool | None = None
    origin: str | None = None
    destination: str | None = None
    loaded_miles: float | None = None
    state: str | None = None             # 2-letter; for the dollar anchor (Flow 3)


class HandoffReq(BaseModel):
    reason: str | None = None


class StageResult(BaseModel):
    case: CaseState
    next_stage: str
    message: str | None = None
    routed_to_handoff: bool = False
    needs_clarification: bool = False
    detail: dict | None = None
