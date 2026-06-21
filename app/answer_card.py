"""The §7 answer-card model + persistence — the one output structure every flow
uses. The rich dataclass is what the frontend renders (matches the screen frames);
persist_card() normalizes it into answer_cards + card_citations for the record.

Card structure (PRD §7): eyebrow + headline → the number → why (line-by-line, with
citations) → exactly one primary next action → "appears to / likely" framing →
human-advocate escalation.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Literal

# card_citations.source_type enum
CitationSource = Literal[
    "code_set", "ncci_ptp", "ncci_mue", "pfs", "ambulance_fs", "ncd",
    "medicare_appeal_level", "commercial_appeal_level", "nsa_rule",
    "sbc_field", "plan_attribute", "code_explanation",
]


def dollars(cents: int | None) -> str:
    """Integer cents → '$1,240.00'. None → '—'."""
    if cents is None:
        return "—"
    return f"${cents / 100:,.2f}"


@dataclass
class Citation:
    source_type: str
    source_ref: str
    display_text: str | None = None


@dataclass
class Finding:
    title: str
    text: str
    tone: str = "neutral"          # 'error' | 'leverage' | 'ok' | 'neutral' (UI dot)
    citation: Citation | None = None


@dataclass
class ReconRow:
    label: str
    cents: int
    is_total: bool = False


@dataclass
class HonestyNode:
    text: str


@dataclass
class Pathway:
    label: str
    detail: str
    caveat: str | None = None


@dataclass
class AnswerCard:
    flow: str                                   # answer_cards.flow enum
    headline: str
    eyebrow: str | None = None
    number_cents: int | None = None
    number_label: str | None = None
    number_display: str | None = None           # e.g. "≈ $546" or "≈4.4×"
    # Optional second tier for Flow 2's honest split (recoverable $ vs ×-Medicare).
    number2_display: str | None = None          # e.g. "≈4.4×"
    number2_label: str | None = None            # e.g. "over benchmark"
    reconciliation: list[ReconRow] = field(default_factory=list)
    findings: list[Finding] = field(default_factory=list)
    next_action: str | None = None
    secondary_action: str | None = None
    framing_note: str | None = None             # the "appears to / likely" line
    honesty_node: HonestyNode | None = None
    pathway: Pathway | None = None
    escalation_offered: bool = True
    gated_content_note: str | None = None

    def to_dict(self) -> dict:
        return asdict(self)


def _why_text(card: AnswerCard) -> str:
    return "\n".join(f"{f.title}: {f.text}" for f in card.findings)


def persist_card(app_conn, case_id: int, card: AnswerCard) -> int:
    """Write the card to answer_cards + its findings' citations to card_citations.
    Returns card_id. Uses the repo helpers (each commits)."""
    from . import repo

    card_id = repo.create_answer_card(
        app_conn, case_id, card.headline,
        flow=card.flow, number_cents=card.number_cents, number_label=card.number_label,
        why_text=_why_text(card), next_action=card.next_action, framing="likely",
        escalation_offered=int(card.escalation_offered),
        gated_content_note=card.gated_content_note,
    )
    for f in card.findings:
        if f.citation:
            repo.add_card_citation(app_conn, card_id, f.citation.source_type,
                                   f.citation.source_ref, display_text=f.citation.display_text)
    return card_id
