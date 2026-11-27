"""Step 4.2: proposals, approvals and the audit trail.

The agent can only PROPOSE an action. A person approves or rejects it. Every step is written as a row
in action_log, which is only ever appended to, so there is a complete history of who did what.
Nothing here carries out the action in an airline system: execution is simulated by the "approved" record.
"""
from sqlalchemy import select
from sqlalchemy.orm import Session

from app import entitlements, services
from app.db import SessionLocal
from app.models import ActionLog

ACTIONS = ("issue_meal_voucher", "book_hotel", "rebook", "refund", "pay_compensation")
ROLES = ("agent", "duty_manager")
MANAGER_REFUND_LIMIT_INR = 50000  # policy 7.2


def required_approver(booking, action: str, amount: int | None) -> str:
    """6.1 and 7.2: refunds for unaccompanied minors, and refunds above the limit, need the duty manager."""
    if action == "refund" and (booking.passenger.is_unaccompanied_minor or (amount or 0) > MANAGER_REFUND_LIMIT_INR):
        return "duty_manager"
    return "agent"


def _find(report, kind: str):
    return next((e for e in report.entitlements if e.kind == kind), None)


def _segment_to_rebook(booking):
    for segment in booking.segments:
        if segment.flight.status == "cancelled":
            return segment
    for connection, next_segment in zip(booking.connections, booking.segments[1:]):
        if not connection.feasible:
            return next_segment
    return None


def _log(db: Session, actor: str, action: str, pnr: str, details: dict) -> ActionLog:
    row = ActionLog(actor=actor, action=action, pnr=pnr, details=details)
    db.add(row)
    db.flush()
    return row


def _earlier_proposal(db: Session, pnr: str, action: str) -> int | None:
    """Id of an earlier proposal for the same action that was not rejected (pending or approved)."""
    rows = db.scalars(select(ActionLog).where(ActionLog.pnr == pnr).order_by(ActionLog.id)).all()
    rejected = {(r.details or {}).get("proposal_id") for r in rows if r.action == "rejected"}
    for row in rows:
        if row.action == "proposed" and (row.details or {}).get("action_type") == action and row.id not in rejected:
            return row.id
    return None


def _not_allowed(entitlement, missing: str) -> dict:
    return {"error": f"Not allowed: {entitlement.reason if entitlement else missing}"}


def propose(db: Session, pnr: str, action: str, flight_number: str = "", flight_day=None,
            proposed_by: str = "agent") -> dict:
    """Check an action against the policy rules and record it as pending. The caller commits."""
    pnr = pnr.strip().upper()
    if action not in ACTIONS:
        return {"error": f"Unknown action. Allowed actions: {', '.join(ACTIONS)}"}
    booking = services.get_booking(db, pnr)
    if booking is None:
        return {"error": f"No booking found for PNR {pnr}"}
    report = entitlements.calculate(booking)
    if report.situation == "none":
        return {"error": "This booking has no disruption, so there is nothing to propose."}

    amount, citation, details = None, None, {}
    if action == "issue_meal_voucher":
        e = _find(report, "meal_voucher")
        if not e or e.status != "applies":
            return _not_allowed(e, "no meal voucher entitlement")
        amount, citation = e.amount_inr, e.citation
    elif action == "book_hotel":
        e = _find(report, "hotel")
        if not e or e.status == "does_not_apply":
            return _not_allowed(e, "no hotel entitlement")
        citation = e.citation
    elif action == "pay_compensation":
        e = _find(report, "cash_compensation")
        if not e or e.status == "does_not_apply":
            return _not_allowed(e, "no compensation entitlement")
        amount, citation = e.amount_inr, e.citation  # the amount always comes from the calculator
    elif action == "refund":
        e = _find(report, "refund_option")
        if not e or e.status != "applies":
            e = _find(report, "rebooking_or_refund")
        if not e or e.status != "applies":
            return _not_allowed(e, "no refund entitlement")
        amount, citation = int(round(booking.ticket_price)), e.citation
    else:  # rebook
        e = _find(report, "rebooking_or_refund")
        if not e or e.status != "applies":
            return _not_allowed(e, "no rebooking entitlement")
        target = _segment_to_rebook(booking)
        if target is None:
            return {"error": "No flight in this booking needs rebooking."}
        if not flight_number or flight_day is None:
            return {"error": "A rebooking needs flight_number and flight_date of the new flight."}
        new = services.get_flight_status(db, flight_number, flight_day)
        if new is None:
            return {"error": f"No flight {flight_number.upper()} on {flight_day}."}
        if new.status == "cancelled":
            return {"error": f"Flight {new.flight_number} on {new.flight_date} is cancelled."}
        old = target.flight
        if (new.origin, new.destination) != (old.origin, old.destination):
            return {"error": f"The new flight must fly {old.origin} to {old.destination}."}
        citation = e.citation
        details = {"replaces": f"{old.flight_number} on {old.flight_date}",
                   "new_flight": f"{new.flight_number} on {new.flight_date}",
                   "new_estimated_departure": new.estimated_departure.isoformat()}

    earlier = _earlier_proposal(db, pnr, action)
    if earlier is not None:
        return {"error": f"This action was already proposed as proposal #{earlier}."}

    approver = required_approver(booking, action, amount)
    row = _log(db, proposed_by, "proposed", pnr, {
        "action_type": action, "amount_inr": amount, "required_approver": approver,
        "citation": citation, "details": details})
    return {"proposal_id": row.id, "status": "pending_approval", "action": action, "pnr": pnr,
            "amount_inr": amount, "required_approver": approver, "citation": citation, "details": details,
            "note": "This is only a proposal. A person must approve it; nothing has been done yet."}


def decide(db: Session, proposal_id: int, decision: str, role: str, note: str | None = None) -> dict:
    """Approve or reject a pending proposal. Anyone may reject; only the required role may approve."""
    if decision not in ("approved", "rejected"):
        return {"error": "decision must be approved or rejected"}
    if role not in ROLES:
        return {"error": f"role must be one of {', '.join(ROLES)}"}
    proposal = db.get(ActionLog, proposal_id)
    if proposal is None or proposal.action != "proposed":
        return {"error": f"There is no proposal #{proposal_id}."}
    decisions = db.scalars(select(ActionLog).where(
        ActionLog.pnr == proposal.pnr, ActionLog.action.in_(("approved", "rejected")))).all()
    if any((r.details or {}).get("proposal_id") == proposal_id for r in decisions):
        return {"error": f"Proposal #{proposal_id} was already decided."}
    if decision == "approved" and proposal.details["required_approver"] == "duty_manager" and role != "duty_manager":
        return {"error": f"Proposal #{proposal_id} needs the duty manager to approve it."}
    _log(db, role, decision, proposal.pnr,
         {"proposal_id": proposal_id, "action_type": proposal.details["action_type"], "note": note})
    return {"proposal_id": proposal_id, "status": decision, "decided_by": role}


def list_pending(db: Session) -> list[dict]:
    rows = db.scalars(select(ActionLog).order_by(ActionLog.id)).all()
    decided = {(r.details or {}).get("proposal_id") for r in rows if r.action in ("approved", "rejected")}
    return [
        {"id": r.id, "pnr": r.pnr, "action": r.details["action_type"], "amount_inr": r.details.get("amount_inr"),
         "required_approver": r.details["required_approver"], "citation": r.details.get("citation"),
         "details": r.details.get("details", {})}
        for r in rows if r.action == "proposed" and r.id not in decided
    ]


def recent_events(db: Session, limit: int = 10) -> list[dict]:
    rows = db.scalars(select(ActionLog).order_by(ActionLog.id.desc()).limit(limit)).all()
    return [
        {"id": r.id, "time": r.created_at.strftime("%d %b %H:%M") if r.created_at else "", "who": r.actor,
         "event": r.action, "pnr": r.pnr or "", "what": (r.details or {}).get("action_type", "")}
        for r in rows
    ]


# Wrappers that open their own session and commit. The tool and the UI use these.
def propose_now(pnr: str, action: str, flight_number: str = "", flight_day=None) -> dict:
    with SessionLocal() as db:
        result = propose(db, pnr, action, flight_number, flight_day)
        db.commit()
    return result


def decide_now(proposal_id: int, decision: str, role: str, note: str | None = None) -> dict:
    with SessionLocal() as db:
        result = decide(db, proposal_id, decision, role, note)
        db.commit()
    return result


def pending_now() -> list[dict]:
    with SessionLocal() as db:
        return list_pending(db)


def recent_now(limit: int = 10) -> list[dict]:
    with SessionLocal() as db:
        return recent_events(db, limit)
