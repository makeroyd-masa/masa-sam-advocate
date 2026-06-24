"""Canonical finding representations shared by the generator's reference_calc and
the test runner. Pure data shaping — imports nothing from app/ (and never the
engine). Both sides emit the SAME normalized dicts so equality comparison is
stable and independent of DB row ids.
"""

from __future__ import annotations


def ptp_finding(disallowed_code: str, other_code: str | None, indicator: int,
                recoverable_cents: int) -> dict:
    return {
        "type": "unbundling_ptp",
        "disallowed_code": disallowed_code,
        "other_code": other_code,
        "indicator": indicator,
        "recoverable_cents": recoverable_cents,
    }


def mue_finding(code: str, cap: int, units_over: int, recoverable_cents: int) -> dict:
    return {
        "type": "quantity_mue",
        "code": code,
        "cap": cap,
        "units_over": units_over,
        "recoverable_cents": recoverable_cents,
    }


def pfs_finding(code: str, setting: str, benchmark_cents: int, billed_multiple: float,
                tier: str) -> dict:
    return {
        "type": "price_benchmark",
        "code": code,
        "setting": setting,
        "benchmark_cents": benchmark_cents,
        "billed_multiple": round(billed_multiple, 2),
        "tier": tier,
    }


def facility_finding(code: str) -> dict:
    return {"type": "facility_unbenchmarked", "code": code}


def cost_share_finding(kind: str) -> dict:
    """A normalized cost-share verification finding (PRD addendum: cost-share v0.1).
    kind ∈ {'reconciliation_gap','coinsurance_mismatch','not_covered'}."""
    return {"type": "cost_share", "kind": kind}


def sort_cost_share(findings: list[dict]) -> list[dict]:
    return sorted(findings, key=lambda f: f["kind"])


def recon_category(note_text: str | None) -> str | None:
    """Classify a Flow 1 reconciliation note into a stable enum (shared by the
    runner and reference_calc so both speak the same language)."""
    t = (note_text or "").lower()
    if "denied claim" in t:
        return "denied_claim"
    if "internally consistent" in t:
        return "consistent"
    if "doesn't match" in t or "does not match" in t:
        return "inconsistent"
    return None


def sort_findings(findings: list[dict]) -> list[dict]:
    """Deterministic ordering for comparison: by type, then the implicated code(s)."""
    return sorted(
        findings,
        key=lambda f: (
            f["type"],
            f.get("disallowed_code") or f.get("code") or "",
            f.get("other_code") or "",
        ),
    )
