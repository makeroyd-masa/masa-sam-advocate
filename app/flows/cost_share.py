"""Cost-share verification (PRD addendum: cost-share v0.1, LITE scope).

For INSURED members (employer / commercial), a transparent EOB already prints the
billed → allowed → paid → owe waterfall, so the durable value isn't re-explaining
it — it's checking what the EOB *asserts* but doesn't *prove*: the cost-share
arithmetic. Three checks here:

  #1 reconciliation   — copay + deductible + coinsurance + not-covered must sum to
                        what you owe.
  #2 coinsurance rate — coinsurance ≈ rate × (allowed − deductible), when the rate
                        is known.
  #5 not-covered      — a not-covered amount is a coverage question (route to
                        appeal/handoff), not a pricing issue.

Accumulator checks (#3 deductible over-application, #4 charging past the OOP max)
are DEFERRED to a fast-follow (schema is ready; see member_accumulators).

Pure functions over the bill dict; Flow 1 wires them in behind the
`cost_share_check_enabled` flag. Framing stays "appears to / worth a closer look";
coverage determinations remain the payer's (PRD §8).
"""

from __future__ import annotations

from ..answer_card import Finding, dollars

# Cost-share reasoning only applies where the member's share is set by plan design
# (not self-pay / Medicaid / Medicare pathways).
INSURED_SITUATIONS = ("employer_erisa", "commercial_aca")

# Rounding slack for the coinsurance-rate check, in cents.
_COINS_TOLERANCE_CENTS = 100


def check(
    bill: dict | None,
    insurance_situation: str | None,
    *,
    has_denial_code: bool = False,
) -> tuple[list[Finding], bool]:
    """Return (findings, flagged). Empty for non-insured situations or no bill.

    `flagged` is True when a likely cost-share *error* (#1/#2) was surfaced — Flow 1
    uses it to raise the card's headline. #5 is a routing nudge, not an error, so it
    does not set `flagged`.
    """
    if not bill or insurance_situation not in INSURED_SITUATIONS:
        return [], False

    findings: list[Finding] = []
    flagged = False

    # --- #1 reconciliation: the parts must sum to what you owe ---------------
    # Only run on a COMPLETE breakdown (each part present, may be 0) so partial
    # entry can't produce a false "doesn't add up" finding.
    parts = (
        bill.get("copay_cents"),
        bill.get("deductible_applied_cents"),
        bill.get("coinsurance_cents"),
        bill.get("not_covered_cents"),
    )
    resp = bill.get("patient_responsibility_cents")
    if resp is not None and all(p is not None for p in parts):
        total = sum(parts)
        if total != resp:
            gap = abs(resp - total)
            flagged = True
            findings.append(Finding(
                title="The parts of your share don't add up",
                text=(f"Copay, deductible, coinsurance and not-covered come to {dollars(total)}, "
                      f"but the bill says you owe {dollars(resp)} — a {dollars(gap)} difference "
                      f"worth a closer look."),
                tone="error",
            ))

    # --- #2 coinsurance-rate consistency -------------------------------------
    rate = bill.get("coinsurance_rate_pct")
    allowed = bill.get("total_allowed_cents")
    ded = bill.get("deductible_applied_cents")
    coins = bill.get("coinsurance_cents")
    if None not in (rate, allowed, ded, coins):
        expected = round((rate / 100.0) * max(allowed - ded, 0))
        if abs(expected - coins) > _COINS_TOLERANCE_CENTS:
            flagged = True
            findings.append(Finding(
                title=f"Coinsurance doesn't match your {rate:g}% rate",
                text=(f"At {rate:g}% of the allowed amount after your deductible, coinsurance should "
                      f"be about {dollars(expected)}, but the bill shows {dollars(coins)} — "
                      f"worth a closer look."),
                tone="error",
            ))

    # --- #5 not-covered → routing (only if not already routed by a denial code)
    not_covered = bill.get("not_covered_cents")
    if not has_denial_code and not_covered and not_covered > 0:
        findings.append(Finding(
            title=f"{dollars(not_covered)} was marked not covered",
            text=("A not-covered amount is a coverage decision, not a pricing issue — that's the "
                  "part to question with your plan or appeal. A human advocate can help you start."),
            tone="error",
        ))

    return findings, flagged
