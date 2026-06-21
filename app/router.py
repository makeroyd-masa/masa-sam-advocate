"""The §5 denial-code router — the dispatcher between flows (PRD §5.1).

Reads the curated suggested_action from code_explanations and applies the locked
v0.3 override layer that the flat YAML enum can't express (C3):
  * CARC 45 (charge exceeds fee schedule) is insurance_situation-aware: a
    contractual write-off to explain for insured members, but real negotiation
    leverage for self-pay / balance-bill members (routes to Flow 2).
  * CARC 29 (timely filing) is verify-then-escalate: generally the provider's
    failure, so if the member was actually billed it escalates to a human.

Also owns the display gate: member-facing copy is shown ONLY when it is authored
AND reviewed; otherwise the card falls back to the payer's exact official wording.
"""

from __future__ import annotations

import sqlite3
from dataclasses import dataclass, field

from . import pilot
from .codes import parse_denial_code

# suggested_action → which engine the case should move toward.
ACTION_TO_FLOW = {
    "explain_only": "flow1_explain",
    "error_check": "flow2_error",
    "appeal": "flow3_appeal",
    "verify_with_payer": "none",
    "escalate_human": "none",
}


@dataclass
class MemberCopy:
    source: str               # 'authored' | 'official_fallback'
    plain_explanation: str | None
    practical_meaning: str | None
    official_text: str | None
    label: str                # how to introduce the text in the UI


@dataclass
class RoutingDecision:
    code: str
    code_type: str
    base_action: str          # curated suggested_action (or 'explain_only' for tail)
    action: str               # effective action after overrides
    target_flow: str
    commonly_disputable: bool | None
    reason: str
    requires_handoff: bool = False
    override_applied: str | None = None
    in_curated_set: bool = True
    copy: MemberCopy | None = field(default=None)


def _resolve_copy(
    explanation: dict | None, pilot_conn: sqlite3.Connection, code: str, code_type: str
) -> MemberCopy:
    """Display gate (C4): authored+reviewed copy wins; else official text fallback."""
    if explanation:
        plain = (explanation.get("plain_explanation") or "").strip()
        if explanation.get("reviewed") == 1 and plain:
            return MemberCopy(
                source="authored",
                plain_explanation=plain,
                practical_meaning=(explanation.get("practical_meaning") or "").strip() or None,
                official_text=explanation.get("official_text"),
                label="What this means",
            )
        official = explanation.get("official_text")
    else:
        official = pilot.official_text(pilot_conn, code, code_type)
    return MemberCopy(
        source="official_fallback",
        plain_explanation=None,
        practical_meaning=None,
        official_text=official,
        label="The payer's exact language",
    )


def route_denial_code(
    app_conn: sqlite3.Connection,
    pilot_conn: sqlite3.Connection,
    code: str,
    code_type: str,
    *,
    insurance_situation: str | None = None,
    problem_type: str | None = None,
    member_billed: bool = False,
) -> RoutingDecision:
    """Classify a single denial code into an effective action + target flow."""
    row = app_conn.execute(
        "SELECT * FROM code_explanations WHERE code = ? AND code_type = ?", (code, code_type)
    ).fetchone()
    explanation = dict(row) if row else None
    copy = _resolve_copy(explanation, pilot_conn, code, code_type)

    # Long tail: not in the curated set → explain with the payer's exact wording.
    if explanation is None:
        return RoutingDecision(
            code=code, code_type=code_type, base_action="explain_only",
            action="explain_only", target_flow="flow1_explain", commonly_disputable=None,
            reason="Not in the curated set — showing the payer's exact language.",
            in_curated_set=False, copy=copy,
        )

    base_action = explanation["suggested_action"]
    action = base_action
    override = None
    requires_handoff = False
    reason = "Routed by curated suggested_action."

    is_self_pay = insurance_situation == "self_pay" or problem_type == "balance_bill"

    # --- Override: CARC 45 insurance_situation-aware -----------------------
    if code == "45" and code_type == "CARC":
        if is_self_pay:
            action, override = "error_check", "carc45_self_pay_leverage"
            reason = ("Charge exceeds the fee schedule. For self-pay/balance-bill this is "
                      "negotiation leverage — check it against the Medicare benchmark.")
        else:
            reason = ("Charge exceeds the fee schedule — a contractual write-off you do not "
                      "owe as an insured member.")

    # --- Override: CARC 29 verify-then-escalate ----------------------------
    elif code == "29" and code_type == "CARC":
        if member_billed:
            action, override = "escalate_human", "carc29_billed_escalate"
            requires_handoff = True
            reason = ("Timely-filing denial is generally the provider's failure; you were "
                      "billed anyway — escalating to a human advocate.")
        else:
            reason = ("Timely-filing limit expired — generally the provider's issue, not "
                      "yours. Verify you weren't billed.")

    if action == "escalate_human":
        requires_handoff = True

    return RoutingDecision(
        code=code, code_type=code_type, base_action=base_action, action=action,
        target_flow=ACTION_TO_FLOW[action],
        commonly_disputable=bool(explanation["commonly_disputable"]),
        reason=reason, requires_handoff=requires_handoff, override_applied=override,
        in_curated_set=True, copy=copy,
    )


def route_denial_text(
    app_conn: sqlite3.Connection, pilot_conn: sqlite3.Connection, text: str, **kwargs
) -> RoutingDecision | None:
    """Parse free-text ('CARC 50') then route. None if no code is found."""
    parsed = parse_denial_code(text)
    if not parsed:
        return None
    code, code_type = parsed
    return route_denial_code(app_conn, pilot_conn, code, code_type, **kwargs)
