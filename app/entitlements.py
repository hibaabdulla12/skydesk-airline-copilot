"""Step 4.1: the policy's numbers and eligibility rules as plain, testable code.

The model never works out an amount or a threshold. It asks this module, then explains the result.
Every rule points to a section of the policy document, and a test checks that those sections exist.
"""
from typing import Literal

from pydantic import BaseModel

from app.schemas import BookingOut, SegmentOut

POLICY = "SkyDesk Disruption Policy"

# The numbers from the policy. If the policy changes, change them here and in the tests.
DELAY_MIN = 30                 # 1.2  a flight counts as delayed from here
MEAL_DELAY_MIN = 120           # 2.2
REFUND_DELAY_MIN = 240         # 2.3
HOTEL_DELAY_MIN = 360          # 2.4
COMPENSATION_DELAY_MIN = 180   # 2.5
SHORT_FLIGHT_MIN = 240         # 2.5  under 4 hours is a short flight
LOUNGE_DELAY_MIN = 120         # 6.3
MEAL_VOUCHER_INR = 600
COMPENSATION_SHORT_INR = 5000
COMPENSATION_LONG_INR = 10000

CONTROLLABLE = {"technical", "crew"}                 # 1.4
EXTRAORDINARY = {"weather", "air_traffic_control"}   # 1.4


class Entitlement(BaseModel):
    kind: str
    status: Literal["applies", "does_not_apply", "needs_confirmation"]
    amount_inr: int | None = None
    citation: str
    reason: str


class EntitlementReport(BaseModel):
    pnr: str
    situation: Literal["none", "delay", "cancellation", "missed_connection"]
    cause: Literal["controllable", "extraordinary", "unknown"] | None
    entitlements: list[Entitlement]
    notes: list[str] = []


def _entitlement(kind, status, section, reason, amount=None) -> Entitlement:
    return Entitlement(kind=kind, status=status, amount_inr=amount, citation=f"{POLICY} §{section}", reason=reason)


def _rule(kind, applies: bool, section, yes, no, amount=None) -> Entitlement:
    return _entitlement(kind, "applies" if applies else "does_not_apply", section, yes if applies else no,
                        amount if applies else None)


def _minutes(segment: SegmentOut) -> int:
    flight = segment.flight
    return int((flight.scheduled_arrival - flight.scheduled_departure).total_seconds() // 60)


def _cause(reason: str | None) -> str:
    if reason in CONTROLLABLE:
        return "controllable"
    if reason in EXTRAORDINARY:
        return "extraordinary"
    return "unknown"


def _compensation_amount(flight_minutes: int) -> int:
    return COMPENSATION_SHORT_INR if flight_minutes < SHORT_FLIGHT_MIN else COMPENSATION_LONG_INR


def _priority_group(booking: BookingOut) -> int:
    """3.4: 1 unaccompanied minors, 2 assistance, 3 Gold and Platinum, 4 fare class J or B, 5 everyone else."""
    p = booking.passenger
    if p.is_unaccompanied_minor:
        return 1
    if p.needs_assistance:
        return 2
    if p.loyalty_tier in ("gold", "platinum"):
        return 3
    if booking.fare_class in ("J", "B"):
        return 4
    return 5


def _compensation_when_pending(cause, section, amount, why_pending) -> Entitlement:
    """Cancellations and missed connections: the final outcome depends on facts the system does not hold."""
    if cause == "extraordinary":
        return _entitlement("cash_compensation", "does_not_apply", "5.2",
                            "The cause is extraordinary (weather or air traffic control): no cash compensation.")
    return _entitlement("cash_compensation", "needs_confirmation", section,
                        f"If confirmed, the amount is INR {amount}. {why_pending}", amount)


def calculate(booking: BookingOut) -> EntitlementReport:
    segments = booking.segments
    cancelled = [s for s in segments if s.flight.status == "cancelled"]
    delayed = [s for s in segments if s.flight.status == "delayed" and s.flight.delay_minutes >= DELAY_MIN]
    missed = any(not c.feasible for c in booking.connections)

    if cancelled:
        situation, trigger = "cancellation", cancelled[0]
    elif missed and delayed:
        situation, trigger = "missed_connection", max(delayed, key=lambda s: s.flight.delay_minutes)
    elif delayed:
        situation, trigger = "delay", max(delayed, key=lambda s: s.flight.delay_minutes)
    else:
        notes = []
        if missed:
            notes.append("A connection is shorter than the minimum connection time without any disruption. "
                         "The policy does not cover this: refer the case to the duty manager (section 1.1).")
        return EntitlementReport(pnr=booking.pnr, situation="none", cause=None, entitlements=[], notes=notes)

    cause = _cause(trigger.flight.disruption_reason)
    items: list[Entitlement] = []
    notes: list[str] = []
    if cause == "unknown":
        notes.append("The disruption reason is missing, so compensation cannot be decided: a human agent must check.")

    if situation == "delay":
        worst = max(s.flight.delay_minutes for s in delayed)
        final = segments[-1]
        arrival_delay = final.flight.delay_minutes if final in delayed else 0  # an earlier delay may be absorbed
        items.append(_rule("meal_voucher", worst >= MEAL_DELAY_MIN, "2.2",
                           f"Delay of {worst} minutes is {MEAL_DELAY_MIN} minutes or more, whatever the cause.",
                           f"Delay of {worst} minutes is under {MEAL_DELAY_MIN} minutes.", MEAL_VOUCHER_INR))
        items.append(_rule("refund_option", worst >= REFUND_DELAY_MIN, "2.3",
                           f"Delay of {worst} minutes is {REFUND_DELAY_MIN} minutes or more: the passenger may choose a full refund.",
                           f"Delay of {worst} minutes is under {REFUND_DELAY_MIN} minutes."))
        if worst >= HOTEL_DELAY_MIN:
            items.append(_entitlement("hotel", "needs_confirmation", "2.4",
                                      "A delay of 6 hours or more gives a hotel if the passenger must wait overnight: a human agent confirms."))
        else:
            items.append(_entitlement("hotel", "does_not_apply", "2.4",
                                      f"Delay of {worst} minutes is under {HOTEL_DELAY_MIN} minutes."))
        if arrival_delay < COMPENSATION_DELAY_MIN:
            items.append(_entitlement("cash_compensation", "does_not_apply", "2.5",
                                      f"Arrival delay of {arrival_delay} minutes is under {COMPENSATION_DELAY_MIN} minutes."))
        elif cause == "controllable":
            amount = _compensation_amount(_minutes(final))
            items.append(_entitlement("cash_compensation", "applies", "2.5",
                                      f"Arrival delay of {arrival_delay} minutes with a controllable cause, flight time {_minutes(final)} minutes.",
                                      amount))
        elif cause == "extraordinary":
            items.append(_entitlement("cash_compensation", "does_not_apply", "5.2",
                                      "The cause is extraordinary (weather or air traffic control): no cash compensation."))
        else:
            items.append(_entitlement("cash_compensation", "needs_confirmation", "2.5",
                                      "The cause is unknown, so a human agent must decide."))
        if booking.passenger.loyalty_tier in ("gold", "platinum") and worst >= LOUNGE_DELAY_MIN:
            items.append(_entitlement("lounge_access", "applies", "6.3",
                                      f"Gold and Platinum members get lounge access for delays of {LOUNGE_DELAY_MIN} minutes or more."))

    elif situation == "cancellation":
        items.append(_entitlement("rebooking_or_refund", "applies", "3.1",
                                  "The passenger chooses between rebooking at no charge and a full refund, whatever the cause."))
        items.append(_entitlement("meal_voucher", "applies", "3.2", "Meal voucher while waiting for the rebooked flight.",
                                  MEAL_VOUCHER_INR))
        items.append(_entitlement("hotel", "needs_confirmation", "3.2",
                                  "A hotel is provided if the rebooked flight leaves on a later day: depends on the new flight."))
        items.append(_compensation_when_pending(
            cause, "3.3", _compensation_amount(_minutes(trigger)),
            "It applies only if the cancellation notice was under 24 hours, which the system does not record: a human agent confirms."))
        items.append(_entitlement("rebooking_priority", "applies", "3.4",
                                  f"Priority group {_priority_group(booking)} of 5 (1 = unaccompanied minors, 5 = everyone else)."))

    else:  # missed_connection
        total = sum(_minutes(s) for s in segments)
        items.append(_entitlement("rebooking_or_refund", "applies", "4.1",
                                  "Rebooking on the next available flight to the final destination at no charge, or a full refund."))
        items.append(_entitlement("meal_voucher", "applies", "4.2", "Meal voucher after a missed connection.",
                                  MEAL_VOUCHER_INR))
        items.append(_entitlement("hotel", "needs_confirmation", "4.2",
                                  "A hotel is provided if the next flight leaves on a later day: depends on the new flight."))
        items.append(_compensation_when_pending(
            cause, "4.4", _compensation_amount(total),
            "It depends on how late the passenger reaches the final destination, which is not known until rebooked."))
        items.append(_entitlement("rebooking_priority", "applies", "3.4",
                                  f"Priority group {_priority_group(booking)} of 5 (1 = unaccompanied minors, 5 = everyone else)."))

    if booking.passenger.is_unaccompanied_minor:
        items.append(_entitlement("special_handling", "applies", "6.1",
                                  "Unaccompanied minor: never left alone, guardian informed, staff escort, and any refund needs the duty manager."))
    if booking.passenger.needs_assistance:
        items.append(_entitlement("special_handling", "applies", "6.2",
                                  "Passenger needs assistance: confirm the service at every airport before finalising a rebooking."))

    return EntitlementReport(pnr=booking.pnr, situation=situation, cause=cause, entitlements=items, notes=notes)
