"""Read-only accessors over pilot.db reference data (CLAUDE.md data layer).

Every function takes an open sqlite3.Connection (inject via app.db.get_pilot_db or
pass connect_pilot()). Nothing here writes — pilot.db is opened mode=ro upstream.

Notes grounded in the actual pilot.db (verified 2026-06-20):
  * codes.description holds the official X12/WPC text for CARC/RARC (official_text).
  * CPT Category-I numerics (e.g. 99214) are NOT in `codes` (AMA license) → category
    fallback; they still resolve in PFS/NCCI, which are keyed by code number.
  * ncci_ptp active subset = deletion_date IS NULL. modifier_indicator ∈ {0,1,9}.
  * ambulance_fee_schedule.geo_key = 2-letter state (50 + DC + PR = 52). One
    reference_rate column → base = LOS code rate; per-mile = A0425 rate.
"""

from __future__ import annotations

import sqlite3

from .constants import GROUND_MILEAGE_CODE

# ---------------------------------------------------------------------------
# codes
# ---------------------------------------------------------------------------
# code_type values that share a numeric code space and need an explicit type.
_AMBIGUOUS_TYPES = {"CARC", "RARC", "POS", "RevenueCode", "Modifier", "MSDRG"}


def lookup_code(
    conn: sqlite3.Connection, code: str, code_type: str | None = None
) -> dict | None:
    """Resolve a code in `codes`. Returns dict with official_text (=description) or
    None if not found (e.g. CPT — caller applies the category fallback).

    If code_type is omitted, returns the single match when unambiguous; for codes
    that exist under multiple types (e.g. '50' = CARC and POS) pass code_type."""
    code = (code or "").strip()
    if not code:
        return None
    if code_type:
        rows = conn.execute(
            "SELECT * FROM codes WHERE code = ? AND code_type = ?", (code, code_type)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM codes WHERE code = ?", (code,)).fetchall()
    if not rows:
        return None
    row = rows[0]
    return {
        "code": row["code"],
        "code_type": row["code_type"],
        "official_text": row["description"],
        "short_description": row["short_description"],
        "is_header": row["is_header"],
        "ambiguous": len(rows) > 1,
    }


def official_text(conn: sqlite3.Connection, code: str, code_type: str) -> str | None:
    """The raw X12/WPC wording for a CARC/RARC (codes.description). Used by the
    Phase-2 loader to populate code_explanations.official_text."""
    row = conn.execute(
        "SELECT description FROM codes WHERE code = ? AND code_type = ?", (code, code_type)
    ).fetchone()
    return row["description"] if row else None


# ---------------------------------------------------------------------------
# NCCI — PTP (unbundling) + MUE (quantity)
# ---------------------------------------------------------------------------
def ptp_edit(
    conn: sqlite3.Connection, code_a: str, code_b: str, *, active_only: bool = True
) -> dict | None:
    """Look up a PTP edit for a code pair, trying both column orders.

    Returns {column_one_code, column_two_code, modifier_indicator, edit_id} or None.
    modifier_indicator: 0 = never allowed; 1 = allowed with appropriate modifier;
    9 = not applicable. active_only restricts to non-deleted edits."""
    active = "AND deletion_date IS NULL" if active_only else ""
    row = conn.execute(
        f"""
        SELECT edit_id, column_one_code, column_two_code, modifier_indicator, deletion_date
        FROM ncci_ptp_edits
        WHERE ((column_one_code = ? AND column_two_code = ?)
            OR (column_one_code = ? AND column_two_code = ?))
        {active}
        LIMIT 1
        """,
        (code_a, code_b, code_b, code_a),
    ).fetchone()
    if not row:
        return None
    return {
        "edit_id": row["edit_id"],
        "column_one_code": row["column_one_code"],
        "column_two_code": row["column_two_code"],
        "modifier_indicator": row["modifier_indicator"],
    }


def mue_cap(conn: sqlite3.Connection, hcpcs: str, *, active_only: bool = True) -> dict | None:
    """Per-code daily MUE cap. Returns {mue_value, adjudication_indicator} or None."""
    active = "AND deletion_date IS NULL" if active_only else ""
    row = conn.execute(
        f"""
        SELECT mue_value, mue_adjudication_indicator
        FROM ncci_mue WHERE hcpcs_code = ? {active} LIMIT 1
        """,
        (hcpcs,),
    ).fetchone()
    if not row:
        return None
    return {
        "mue_value": row["mue_value"],
        "adjudication_indicator": row["mue_adjudication_indicator"],
    }


# ---------------------------------------------------------------------------
# PFS — Medicare physician fee schedule benchmark
# ---------------------------------------------------------------------------
def pfs_rate(conn: sqlite3.Connection, hcpcs: str, setting: str) -> dict | None:
    """Benchmark rate for a professional line. setting ∈ {'facility','non_facility'}.

    Returns {benchmark_cents, non_fac_rate, fac_rate, status_code, setting} or None
    (None = not benchmarkable here, e.g. facility/revenue lines — log per §6.2)."""
    if setting not in ("facility", "non_facility"):
        raise ValueError(f"setting must be facility|non_facility, got {setting!r}")
    # Prefer the base (no-modifier) row for a stable benchmark.
    row = conn.execute(
        """
        SELECT non_fac_rate, fac_rate, status_code FROM physician_fee_schedule
        WHERE hcpcs = ? ORDER BY (modifier IS NULL OR modifier = '') DESC LIMIT 1
        """,
        (hcpcs,),
    ).fetchone()
    if not row:
        return None
    benchmark = row["fac_rate"] if setting == "facility" else row["non_fac_rate"]
    return {
        "benchmark_cents": benchmark,
        "non_fac_rate": row["non_fac_rate"],
        "fac_rate": row["fac_rate"],
        "status_code": row["status_code"],
        "setting": setting,
    }


# ---------------------------------------------------------------------------
# Ambulance fee schedule — base + per-mile (PRD §6.3, C2). geo_key = state abbrev.
# ---------------------------------------------------------------------------
def ambulance_base_rate(conn: sqlite3.Connection, hcpcs: str, state: str) -> int | None:
    """reference_rate (cents) for a level-of-service code in a state."""
    row = conn.execute(
        "SELECT reference_rate FROM ambulance_fee_schedule WHERE hcpcs = ? AND geo_key = ?",
        (hcpcs, (state or "").strip().upper()),
    ).fetchone()
    return row["reference_rate"] if row else None


def ambulance_mileage_rate(conn: sqlite3.Connection, state: str) -> int | None:
    """Per-mile rate (cents) = A0425 reference_rate for the state (≈915 nationally)."""
    return ambulance_base_rate(conn, GROUND_MILEAGE_CODE, state)


# ---------------------------------------------------------------------------
# NCD 10.1 ambulance medical-necessity criteria (all 35 reviewed)
# ---------------------------------------------------------------------------
def ncd_ambulance(
    conn: sqlite3.Connection,
    *,
    coverage_indicator: str | None = None,
    reviewed_only: bool = True,
) -> list[dict]:
    """NCD 10.1 rows. coverage_indicator ∈ {covered, non_covered, conditional, informational}."""
    clauses, params = [], []
    if reviewed_only:
        clauses.append("reviewed = 1")
    if coverage_indicator:
        clauses.append("coverage_indicator = ?")
        params.append(coverage_indicator)
    where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = conn.execute(
        f"SELECT ncd_id, section_id, section_title, coverage_indicator, criteria_text, "
        f"criterion_type, citation, reviewed FROM ncd_ambulance {where} ORDER BY section_id",
        params,
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Appeal frameworks
# ---------------------------------------------------------------------------
def medicare_appeal_levels(conn: sqlite3.Connection, plan_type: str) -> list[dict]:
    """plan_type ∈ {'traditional_medicare','medicare_advantage'}. Ordered by level."""
    rows = conn.execute(
        "SELECT level_number, level_name, decision_maker, filing_deadline_days, "
        "filing_deadline_basis, citation, plan_type FROM medicare_appeal_levels "
        "WHERE plan_type = ? ORDER BY level_number",
        (plan_type,),
    ).fetchall()
    return [dict(r) for r in rows]


def commercial_appeal_levels(conn: sqlite3.Connection) -> list[dict]:
    rows = conn.execute(
        "SELECT level_number, level_name, applicable_plan_types, filing_deadline_days, "
        "filing_deadline_basis, iro_applicable, citation FROM commercial_appeal_levels "
        "ORDER BY level_number"
    ).fetchall()
    return [dict(r) for r in rows]


# ---------------------------------------------------------------------------
# Plan context (Flow 1 ACA reconciliation — lighter; refined in Phase 4)
# ---------------------------------------------------------------------------
def sbc_fields_for_document(conn: sqlite3.Connection, sbc_document_id: str) -> list[dict]:
    rows = conn.execute(
        "SELECT field_name, field_value, confidence, page_number FROM sbc_fields "
        "WHERE sbc_document_id = ?",
        (sbc_document_id,),
    ).fetchall()
    return [dict(r) for r in rows]
