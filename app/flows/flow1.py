"""Flow 1 — bill / EOB explanation (PRD §6.1).

Describes each captured code (line codes via lookup_code with a CPT category
fallback; CARC/RARC via the §5 layer with the display gate), reconciles the
bill-level totals into a plain-English consistency account, and ends in the §4
progressive checkpoint. Where a denial looks appealable or a charge looks like a
likely error, it surfaces the hand-off to Flow 3 / Flow 2.
"""

from __future__ import annotations

import sqlite3

from .. import pilot, repo
from .. import router as denial_router
from ..answer_card import AnswerCard, Citation, Finding, ReconRow, dollars
from ..config import code_label


def _reconcile(bill: dict | None) -> tuple[list[ReconRow], str | None]:
    if not bill:
        return [], None
    b = bill.get("total_billed_cents")
    a = bill.get("total_allowed_cents")
    p = bill.get("total_plan_paid_cents")
    r = bill.get("patient_responsibility_cents")
    rows: list[ReconRow] = []
    if b is not None:
        rows.append(ReconRow("Billed", b))
    if a is not None:
        rows.append(ReconRow("Plan allowed", a))
    if p is not None:
        rows.append(ReconRow("Plan paid", p))
    if r is not None:
        rows.append(ReconRow("You owe", r, is_total=True))

    note = None
    # Full denial first: nothing allowed/paid and the whole billed amount lands on you.
    if b and r == b and (p or 0) == 0 and (a or 0) == 0:
        note = "The full billed amount was passed to you — typical of a denied claim."
    elif a is not None and p is not None and r is not None:
        note = (
            "Plan paid plus your share equals the allowed amount — internally consistent."
            if p + r == a
            else f"Plan paid plus your share ({dollars(p + r)}) doesn't match the allowed "
                 f"amount ({dollars(a)}) — worth a closer look."
        )
    return rows, note


def _describe_line(pilot_conn: sqlite3.Connection, line: dict) -> Finding:
    raw = line["raw_code"]
    label = code_label(raw)            # MASA-owned plain label (config/code_labels.yaml)
    info = pilot.lookup_code(pilot_conn, raw)
    if info and info["code_type"] not in ("CARC", "RARC"):
        desc = label or info["short_description"] or info["official_text"] or "(no description on file)"
        return Finding(
            title=f"{raw} — {desc}",
            text=info["short_description"] or info["official_text"] or "",
            tone="neutral",
            citation=Citation("code_set", raw, f"source · {info['code_type']}"),
        )
    # CPT (and anything not in `codes`) → MASA label if available, else category
    # fallback (CPT descriptors are AMA-licensed and not stored, PRD §2.1).
    if (line.get("detected_code_type") or "").upper() == "CPT":
        return Finding(
            title=f"{raw} — {label}" if label else f"{raw} — procedure (rate only)",
            text="I can show the Medicare rate for this code; the full AMA description "
                 "isn't printable here.",
            tone="ok",
            citation=Citation("code_set", raw, "source · CPT (detection only)"),
        )
    return Finding(title=f"{raw}", text="Code not recognized — double-check it against the bill.",
                   tone="neutral")


def explain(app_conn: sqlite3.Connection, pilot_conn: sqlite3.Connection, case_id: int) -> AnswerCard:
    case = repo.get_case(app_conn, case_id)
    bill = app_conn.execute(
        "SELECT * FROM bill_summaries WHERE case_id = ?", (case_id,)
    ).fetchone()
    bill = dict(bill) if bill else None
    denials = repo.get_denial_codes(app_conn, case_id)
    lines = repo.get_bill_lines(app_conn, case_id)

    member_billed = bool(bill and (bill.get("patient_responsibility_cents") or 0) > 0)
    findings: list[Finding] = []
    appealable = False
    error_likely = False

    # 1) Denial codes — the dispatcher (with the §5 display gate).
    for d in denials:
        decision = denial_router.route_denial_code(
            app_conn, pilot_conn, d["code"], d["code_type"],
            insurance_situation=case["insurance_situation"], problem_type=case["problem_type"],
            member_billed=member_billed,
        )
        copy = decision.copy
        text = copy.plain_explanation or copy.official_text or "(no description on file)"
        if copy.practical_meaning:
            text = f"{text} {copy.practical_meaning}"
        tone = "error" if decision.action in ("appeal", "error_check") else "ok"
        findings.append(Finding(
            title=f"{d['code_type']} {d['code']}",
            text=text,
            tone=tone,
            citation=Citation("code_explanation", f"{d['code_type']} {d['code']}",
                              f"source · {d['code_type']} {d['code']}"),
        ))
        appealable = appealable or decision.action == "appeal"
        error_likely = error_likely or decision.action == "error_check"

    # 2) Line codes — describe (CPT fallback).
    for line in lines:
        findings.append(_describe_line(pilot_conn, line))

    rows, recon_note = _reconcile(bill)
    if recon_note:
        findings.append(Finding(title="How your share was reached", text=recon_note, tone="neutral"))

    # Headline + framing reflect what we found.
    if appealable:
        eyebrow, headline = ("Here's what your bill says",
                             "This charge was denied — and that looks appealable.")
        secondary = "This looks like a denial — help me appeal"
    elif error_likely:
        eyebrow, headline = ("Here's what your bill says",
                             "Part of this bill looks like it may be a billing error.")
        secondary = None
    else:
        eyebrow, headline = ("Here's what your bill says",
                             "Here's a plain-English read of your bill.")
        secondary = None

    pr = bill.get("patient_responsibility_cents") if bill else None
    return AnswerCard(
        flow="flow1_explain",
        eyebrow=eyebrow,
        headline=headline,
        number_cents=pr,
        number_label="you owe" if pr is not None else None,
        number_display=dollars(pr) if pr is not None else None,
        reconciliation=rows,
        findings=findings,
        next_action="Check this bill for errors & overcharges",
        secondary_action=secondary,
        framing_note="This is an explanation of what your bill says — not a determination of "
                     "what you owe. Coverage decisions remain your plan's.",
        escalation_offered=True,
    )
