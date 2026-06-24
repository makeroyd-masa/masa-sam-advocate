"""Repository helpers for app.db (the writable case/state store).

Every function takes an open sqlite3.Connection (foreign_keys ON; see app.db).
Writes commit before returning. Money is INTEGER cents; enums must match the
CHECK constraints in docs/app_schema_v0_1.sql. PHI lives only here (PRD §1.2).
"""

from __future__ import annotations

import json
import sqlite3


# --- member_profile --------------------------------------------------------
def upsert_member(
    conn: sqlite3.Connection,
    member_ref: str,
    *,
    default_insurance_situation: str | None = None,
    plan_identifier: str | None = None,
) -> None:
    conn.execute(
        "INSERT INTO member_profile (member_ref, default_insurance_situation, plan_identifier) "
        "VALUES (?, ?, ?) ON CONFLICT(member_ref) DO UPDATE SET "
        "default_insurance_situation = COALESCE(excluded.default_insurance_situation, "
        "member_profile.default_insurance_situation), "
        "plan_identifier = COALESCE(excluded.plan_identifier, member_profile.plan_identifier), "
        "updated_at = CURRENT_TIMESTAMP",
        (member_ref, default_insurance_situation, plan_identifier),
    )
    conn.commit()


# --- cases + events --------------------------------------------------------
def create_case(
    conn: sqlite3.Connection,
    member_ref: str,
    *,
    entry_point: str | None = None,
    seed_intent: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO cases (member_ref, entry_point, seed_intent) VALUES (?, ?, ?)",
        (member_ref, entry_point, seed_intent),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_case(conn: sqlite3.Connection, case_id: int) -> dict | None:
    row = conn.execute("SELECT * FROM cases WHERE case_id = ?", (case_id,)).fetchone()
    return dict(row) if row else None


def update_case(conn: sqlite3.Connection, case_id: int, **fields) -> None:
    """Update whitelisted case columns. machine_context accepts a dict (JSON-encoded)."""
    allowed = {
        "problem_type", "insurance_situation", "active_flow", "current_stage",
        "status", "machine_context", "entry_point", "seed_intent",
    }
    sets, params = [], []
    for key, val in fields.items():
        if key not in allowed:
            raise ValueError(f"update_case: unknown column {key!r}")
        if key == "machine_context" and isinstance(val, (dict, list)):
            val = json.dumps(val)
        sets.append(f"{key} = ?")
        params.append(val)
    if not sets:
        return
    sets.append("updated_at = CURRENT_TIMESTAMP")
    params.append(case_id)
    conn.execute(f"UPDATE cases SET {', '.join(sets)} WHERE case_id = ?", params)
    conn.commit()


def log_event(
    conn: sqlite3.Connection,
    case_id: int,
    event_type: str,
    *,
    from_stage: str | None = None,
    to_stage: str | None = None,
    detail: dict | None = None,
) -> None:
    conn.execute(
        "INSERT INTO case_events (case_id, event_type, from_stage, to_stage, detail) "
        "VALUES (?, ?, ?, ?, ?)",
        (case_id, event_type, from_stage, to_stage, json.dumps(detail) if detail else None),
    )
    conn.commit()


# --- Stage 2: bill summary + denial codes ----------------------------------
def upsert_bill_summary(conn: sqlite3.Connection, case_id: int, **fields) -> None:
    cols = [
        "provider_name", "date_of_service_start", "date_of_service_end",
        "total_billed_cents", "total_allowed_cents", "total_plan_paid_cents",
        "patient_responsibility_cents", "notes",
        # Cost-share breakdown (PRD addendum: cost-share v0.1).
        "copay_cents", "deductible_applied_cents", "coinsurance_cents",
        "not_covered_cents", "discount_cents", "coinsurance_rate_pct",
    ]
    vals = [fields.get(c) for c in cols]
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols)
    conn.execute(
        f"INSERT INTO bill_summaries (case_id, {', '.join(cols)}) "
        f"VALUES (?, {', '.join('?' for _ in cols)}) "
        f"ON CONFLICT(case_id) DO UPDATE SET {updates}",
        (case_id, *vals),
    )
    conn.commit()


def add_denial_code(
    conn: sqlite3.Connection,
    case_id: int,
    code: str,
    code_type: str,
    *,
    where_seen: str | None = None,
    line_id: int | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO captured_denial_codes (case_id, code, code_type, where_seen, line_id) "
        "VALUES (?, ?, ?, ?, ?)",
        (case_id, code, code_type, where_seen, line_id),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_denial_codes(conn: sqlite3.Connection, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM captured_denial_codes WHERE case_id = ? ORDER BY id", (case_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Stage 3: bill lines ---------------------------------------------------
def add_bill_line(
    conn: sqlite3.Connection,
    case_id: int,
    line_no: int,
    raw_code: str,
    *,
    detected_code_type: str | None = None,
    units: int | None = None,
    billed_charge_cents: int | None = None,
    modifier: str | None = None,
    encounter_pos: str | None = None,
) -> int:
    cur = conn.execute(
        "INSERT INTO bill_lines (case_id, line_no, raw_code, detected_code_type, units, "
        "billed_charge_cents, modifier, encounter_pos) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, line_no, raw_code, detected_code_type, units, billed_charge_cents,
         modifier, encounter_pos),
    )
    conn.commit()
    return int(cur.lastrowid)


def get_bill_lines(conn: sqlite3.Connection, case_id: int) -> list[dict]:
    rows = conn.execute(
        "SELECT * FROM bill_lines WHERE case_id = ? ORDER BY line_no", (case_id,)
    ).fetchall()
    return [dict(r) for r in rows]


# --- Stage 3-alt / Stage 4 -------------------------------------------------
def upsert_itemized_bill_request(
    conn: sqlite3.Connection, case_id: int, *, letter_status: str = "draft"
) -> None:
    conn.execute(
        "INSERT INTO itemized_bill_requests (case_id, letter_status) VALUES (?, ?) "
        "ON CONFLICT(case_id) DO UPDATE SET letter_status = excluded.letter_status",
        (case_id, letter_status),
    )
    conn.commit()


def upsert_ambulance_claim(conn: sqlite3.Connection, case_id: int, **fields) -> None:
    cols = [
        "transport_hcpcs", "transport_modifier", "denial_letter_date", "is_emergency",
        "origin", "destination", "loaded_miles",
    ]
    vals = [fields.get(c) for c in cols]
    updates = ", ".join(f"{c} = excluded.{c}" for c in cols)
    conn.execute(
        f"INSERT INTO ambulance_claims (case_id, {', '.join(cols)}) "
        f"VALUES (?, {', '.join('?' for _ in cols)}) "
        f"ON CONFLICT(case_id) DO UPDATE SET {updates}",
        (case_id, *vals),
    )
    conn.commit()


# --- code_explanations (read; loaded in Phase 2) ---------------------------
def get_code_explanation(conn: sqlite3.Connection, code: str, code_type: str) -> dict | None:
    row = conn.execute(
        "SELECT * FROM code_explanations WHERE code = ? AND code_type = ?", (code, code_type)
    ).fetchone()
    return dict(row) if row else None


# --- Flow 2 findings -------------------------------------------------------
def add_flow2_finding(conn: sqlite3.Connection, case_id: int, finding_type: str,
                      savings_class: str, **fields) -> int:
    cols = [
        "line_id", "paired_line_id", "ptp_modifier_indicator", "mue_cap", "units_over_cap",
        "pfs_setting", "benchmark_cents", "billed_multiple", "benchmark_tier",
        "recoverable_cents",
    ]
    vals = [fields.get(c) for c in cols]
    cur = conn.execute(
        f"INSERT INTO flow2_findings (case_id, finding_type, savings_class, {', '.join(cols)}) "
        f"VALUES (?, ?, ?, {', '.join('?' for _ in cols)})",
        (case_id, finding_type, savings_class, *vals),
    )
    conn.commit()
    return int(cur.lastrowid)


def case_savings(conn: sqlite3.Connection, case_id: int) -> dict:
    row = conn.execute(
        "SELECT recoverable_cents, leverage_line_count FROM v_case_savings WHERE case_id = ?",
        (case_id,),
    ).fetchone()
    return dict(row) if row else {"recoverable_cents": 0, "leverage_line_count": 0}


# --- Flow 3 appeal + citations ---------------------------------------------
def upsert_flow3_appeal(conn: sqlite3.Connection, case_id: int, segment: str,
                        ncd_weight: str, **fields) -> None:
    cols = [
        "denial_basis", "appeal_level_ref", "filing_deadline", "base_rate_cents",
        "per_mile_rate_cents", "loaded_miles_used", "reasonable_amount_cents",
        "anchor_is_floor", "gap_to_anchor_cents", "letter_status", "nsa_content_suppressed",
    ]
    present = {c: fields[c] for c in cols if c in fields}
    set_cols = ["segment", "ncd_weight", *present.keys()]
    set_vals = [segment, ncd_weight, *present.values()]
    updates = ", ".join(f"{c} = excluded.{c}" for c in set_cols)
    conn.execute(
        f"INSERT INTO flow3_appeals (case_id, {', '.join(set_cols)}) "
        f"VALUES (?, {', '.join('?' for _ in set_cols)}) "
        f"ON CONFLICT(case_id) DO UPDATE SET {updates}",
        (case_id, *set_vals),
    )
    conn.commit()


def add_appeal_citation(conn: sqlite3.Connection, case_id: int, source_type: str,
                        source_ref: str, *, was_approved: int | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO appeal_citations (case_id, source_type, source_ref, was_approved) "
        "VALUES (?, ?, ?, ?)",
        (case_id, source_type, source_ref, was_approved),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- answer_cards + citations (§7) -----------------------------------------
def create_answer_card(conn: sqlite3.Connection, case_id: int, headline: str, *,
                       flow: str | None = None, number_cents: int | None = None,
                       number_label: str | None = None, why_text: str | None = None,
                       next_action: str | None = None, framing: str = "likely",
                       escalation_offered: int = 0,
                       gated_content_note: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO answer_cards (case_id, flow, headline, number_cents, number_label, "
        "why_text, next_action, framing, escalation_offered, gated_content_note) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (case_id, flow, headline, number_cents, number_label, why_text, next_action,
         framing, escalation_offered, gated_content_note),
    )
    conn.commit()
    return int(cur.lastrowid)


def add_card_citation(conn: sqlite3.Connection, card_id: int, source_type: str,
                      source_ref: str, *, display_text: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO card_citations (card_id, source_type, source_ref, display_text) "
        "VALUES (?, ?, ?, ?)",
        (card_id, source_type, source_ref, display_text),
    )
    conn.commit()
    return int(cur.lastrowid)


# --- handoffs --------------------------------------------------------------
def create_handoff(conn: sqlite3.Connection, case_id: int, *,
                   handoff_type: str = "in_house_advocate", partner: str | None = None,
                   reason: str | None = None) -> int:
    cur = conn.execute(
        "INSERT INTO handoffs (case_id, handoff_type, partner, reason) VALUES (?, ?, ?, ?)",
        (case_id, handoff_type, partner, reason),
    )
    conn.commit()
    return int(cur.lastrowid)
