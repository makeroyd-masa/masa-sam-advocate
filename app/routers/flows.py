"""Flow output endpoints — produce and persist the §7 answer cards."""

from __future__ import annotations

import sqlite3

from fastapi import APIRouter, Depends, HTTPException

from .. import answer_card, repo
from ..db import get_app_db, get_pilot_db
from ..flows import flow1, flow2, flow3
from ..schemas import HandoffReq

api = APIRouter(prefix="/api/cases", tags=["flows"])


def _case_or_404(conn: sqlite3.Connection, case_id: int) -> dict:
    case = repo.get_case(conn, case_id)
    if not case:
        raise HTTPException(status_code=404, detail=f"case {case_id} not found")
    return case


@api.post("/{case_id}/flow1/explain")
def flow1_explain(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db),
                  pilot_db: sqlite3.Connection = Depends(get_pilot_db)):
    _case_or_404(app_db, case_id)
    card = flow1.explain(app_db, pilot_db, case_id)
    card_id = answer_card.persist_card(app_db, case_id, card)
    repo.update_case(app_db, case_id, current_stage="output", status="complete")
    repo.log_event(app_db, case_id, "card_rendered", to_stage="output",
                   detail={"flow": "flow1_explain", "card_id": card_id})
    return {"card_id": card_id, "card": card.to_dict()}


@api.post("/{case_id}/flow2/check")
def flow2_check(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db),
                pilot_db: sqlite3.Connection = Depends(get_pilot_db)):
    _case_or_404(app_db, case_id)
    card = flow2.analyze(app_db, pilot_db, case_id)
    card_id = answer_card.persist_card(app_db, case_id, card)
    savings = repo.case_savings(app_db, case_id)
    repo.update_case(app_db, case_id, current_stage="output", status="complete")
    repo.log_event(app_db, case_id, "card_rendered", to_stage="output",
                   detail={"flow": "flow2_error", "card_id": card_id, **savings})
    return {"card_id": card_id, "card": card.to_dict(), "savings": savings}


@api.post("/{case_id}/flow3/appeal")
def flow3_appeal(case_id: int, app_db: sqlite3.Connection = Depends(get_app_db),
                 pilot_db: sqlite3.Connection = Depends(get_pilot_db)):
    _case_or_404(app_db, case_id)
    card = flow3.analyze(app_db, pilot_db, case_id)
    card_id = answer_card.persist_card(app_db, case_id, card)
    repo.update_case(app_db, case_id, current_stage="output", status="complete")
    repo.log_event(app_db, case_id, "card_rendered", to_stage="output",
                   detail={"flow": "flow3_appeal", "card_id": card_id})
    return {"card_id": card_id, "card": card.to_dict()}


@api.post("/{case_id}/handoff")
def request_handoff(case_id: int, body: HandoffReq,
                    app_db: sqlite3.Connection = Depends(get_app_db)):
    """Member-initiated escalation to an in-house human advocate (PRD §7.7)."""
    _case_or_404(app_db, case_id)
    reason = body.reason or "Member requested a human advocate."
    handoff_id = repo.create_handoff(app_db, case_id, reason=reason)
    repo.update_case(app_db, case_id, status="handed_off")
    repo.log_event(app_db, case_id, "handoff_requested", detail={"reason": reason})
    return {"handoff_id": handoff_id, "status": "handed_off"}
