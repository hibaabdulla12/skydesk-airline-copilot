from datetime import timedelta

import pytest
from sqlalchemy import select

from app import actions, services, tools
from app.db import SessionLocal
from app.models import ActionLog


@pytest.fixture
def db():
    """A session whose changes are rolled back, so tests never leave rows in your real action_log."""
    with SessionLocal() as session:
        yield session
        session.rollback()


def pnr_rows(db, pnr):
    return db.scalars(select(ActionLog).where(ActionLog.pnr == pnr).order_by(ActionLog.id)).all()


# ---- proposing ----

def test_meal_voucher_proposal_is_recorded_as_pending(db):
    result = actions.propose(db, "DEMO01", "issue_meal_voucher")
    assert result["status"] == "pending_approval"
    assert result["amount_inr"] == 600 and result["required_approver"] == "agent"
    assert [(r.actor, r.action) for r in pnr_rows(db, "DEMO01")] == [("agent", "proposed")]
    assert [p["id"] for p in actions.list_pending(db)] == [result["proposal_id"]]


def test_pnr_is_normalised(db):
    assert actions.propose(db, " demo01 ", "book_hotel")["status"] == "pending_approval"


def test_unknown_action_booking_and_undisrupted_booking_are_refused(db):
    assert "Unknown action" in actions.propose(db, "DEMO01", "give_free_upgrade")["error"]
    assert "No booking found" in actions.propose(db, "ZZZZZZ", "refund")["error"]
    assert "no disruption" in actions.propose(db, "DEMO07", "issue_meal_voucher")["error"]
    assert pnr_rows(db, "DEMO07") == []


def test_compensation_amount_comes_from_the_calculator_and_weather_is_refused(db):
    ok = actions.propose(db, "DEMO01", "pay_compensation")
    assert ok["amount_inr"] == 10000 and ok["citation"].endswith("§3.3")
    refused = actions.propose(db, "DEMO03", "pay_compensation")
    assert "extraordinary" in refused["error"]


def test_same_action_cannot_be_proposed_twice_but_can_after_a_rejection(db):
    first = actions.propose(db, "DEMO01", "issue_meal_voucher")
    assert "already proposed" in actions.propose(db, "DEMO01", "issue_meal_voucher")["error"]
    actions.decide(db, first["proposal_id"], "rejected", "agent")
    assert actions.propose(db, "DEMO01", "issue_meal_voucher")["status"] == "pending_approval"


def test_refund_amount_is_the_ticket_price(db):
    booking = services.get_booking(db, "DEMO01")
    result = actions.propose(db, "DEMO01", "refund")
    assert result["amount_inr"] == int(round(booking.ticket_price))


# ---- who must approve ----

def test_large_refunds_and_minors_need_the_duty_manager(db):
    booking = services.get_booking(db, "DEMO01")
    expensive = booking.model_copy(update={"ticket_price": 60000.0})
    assert actions.required_approver(expensive, "refund", 60000) == "duty_manager"
    assert actions.required_approver(booking, "refund", 12000) == "agent"
    assert actions.required_approver(expensive, "pay_compensation", 60000) == "agent"  # the limit is for refunds
    assert actions.propose(db, "DEMO04", "refund")["required_approver"] == "duty_manager"  # unaccompanied minor


# ---- rebooking ----

def next_good_flight(db, booking):
    old = booking.segments[0].flight
    for offset in range(1, 7):
        day = old.flight_date + timedelta(days=offset)
        flight = services.get_flight_status(db, old.flight_number, day)
        if flight and flight.status != "cancelled":
            return flight
    pytest.skip("no usable later flight in the generated data")


def test_rebooking_onto_a_valid_flight(db):
    booking = services.get_booking(db, "DEMO01")
    new = next_good_flight(db, booking)
    result = actions.propose(db, "DEMO01", "rebook", new.flight_number, new.flight_date)
    assert result["status"] == "pending_approval"
    assert new.flight_number in result["details"]["new_flight"]
    assert result["details"]["replaces"].startswith(booking.segments[0].flight.flight_number)


def test_rebooking_refuses_bad_flights(db):
    booking = services.get_booking(db, "DEMO01")
    old = booking.segments[0].flight
    assert "cancelled" in actions.propose(db, "DEMO01", "rebook", old.flight_number, old.flight_date)["error"]
    assert "needs flight_number" in actions.propose(db, "DEMO01", "rebook")["error"]
    assert "No flight" in actions.propose(db, "DEMO01", "rebook", "SD999", old.flight_date)["error"]
    other_route = services.search_flights(db, old.destination, old.origin, old.flight_date)[0]
    assert "must fly" in actions.propose(db, "DEMO01", "rebook", other_route.flight_number, other_route.flight_date)["error"]


# ---- deciding ----

def test_approval_is_recorded_and_clears_the_pending_list(db):
    proposal = actions.propose(db, "DEMO01", "issue_meal_voucher")
    result = actions.decide(db, proposal["proposal_id"], "approved", "agent", note="ok")
    assert result == {"proposal_id": proposal["proposal_id"], "status": "approved", "decided_by": "agent"}
    assert actions.list_pending(db) == []
    rows = pnr_rows(db, "DEMO01")
    assert [r.action for r in rows] == ["proposed", "approved"]      # appended, nothing rewritten
    assert rows[1].details["proposal_id"] == proposal["proposal_id"]


def test_a_proposal_cannot_be_decided_twice(db):
    proposal = actions.propose(db, "DEMO01", "issue_meal_voucher")
    actions.decide(db, proposal["proposal_id"], "approved", "agent")
    assert "already decided" in actions.decide(db, proposal["proposal_id"], "rejected", "agent")["error"]


def test_an_agent_cannot_approve_what_needs_the_duty_manager(db):
    proposal = actions.propose(db, "DEMO04", "refund")
    assert "duty manager" in actions.decide(db, proposal["proposal_id"], "approved", "agent")["error"]
    assert actions.list_pending(db)[0]["id"] == proposal["proposal_id"]   # still pending
    assert actions.decide(db, proposal["proposal_id"], "approved", "duty_manager")["status"] == "approved"


def test_anyone_may_reject(db):
    proposal = actions.propose(db, "DEMO04", "refund")
    assert actions.decide(db, proposal["proposal_id"], "rejected", "agent")["status"] == "rejected"


def test_bad_decisions_are_refused(db):
    assert "no proposal" in actions.decide(db, 999999999, "approved", "agent")["error"].lower()
    proposal = actions.propose(db, "DEMO01", "book_hotel")
    assert "decision" in actions.decide(db, proposal["proposal_id"], "maybe", "agent")["error"]
    assert "role" in actions.decide(db, proposal["proposal_id"], "approved", "intern")["error"]


def test_audit_trail_lists_latest_events_first(db):
    proposal = actions.propose(db, "DEMO01", "issue_meal_voucher")
    actions.decide(db, proposal["proposal_id"], "approved", "agent")
    events = actions.recent_events(db, 2)
    assert [(e["who"], e["event"]) for e in events] == [("agent", "approved"), ("agent", "proposed")]


# ---- the tool the model calls ----

def test_tool_is_registered():
    assert "propose_action" in tools.TOOL_MAP


def test_tool_validates_and_cleans_its_input(monkeypatch):
    seen = []
    monkeypatch.setattr(tools.actions, "propose_now", lambda *args: seen.append(args) or {"status": "pending_approval"})
    assert "error" in tools.propose_action("12", "refund")
    assert "error" in tools.propose_action("DEMO01", "rebook", "SD200", "tomorrow")
    assert tools.propose_action(" demo01 ", " rebook ", " sd216 ", "2026-12-05") == {"status": "pending_approval"}
    pnr, action, flight_number, day = seen[0]
    assert (pnr, action, flight_number, str(day)) == ("DEMO01", "rebook", "SD216", "2026-12-05")
