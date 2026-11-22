"""Business logic: database queries and the deterministic checks."""
from datetime import date, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session, contains_eager, joinedload, selectinload

from app import schemas
from app.models import Airport, Booking, Flight, FlightInstance, Segment


def _flight_status(inst: FlightInstance) -> schemas.FlightStatus:
    delay = timedelta(minutes=inst.delay_minutes)
    return schemas.FlightStatus(
        flight_number=inst.flight.flight_number,
        origin=inst.flight.origin,
        destination=inst.flight.destination,
        flight_date=inst.flight_date,
        status=inst.status,
        scheduled_departure=inst.scheduled_departure,
        scheduled_arrival=inst.scheduled_arrival,
        delay_minutes=inst.delay_minutes,
        estimated_departure=inst.scheduled_departure + delay,
        estimated_arrival=inst.scheduled_arrival + delay,
        disruption_reason=inst.disruption_reason,
    )


def _connection_checks(db: Session, segments: list[schemas.SegmentOut]) -> list[schemas.ConnectionCheck]:
    """For each pair of consecutive flights, is the connection still possible?"""
    checks = []
    for first, second in zip(segments, segments[1:]):
        airport = db.get(Airport, first.flight.destination)
        minimum = airport.min_connection_minutes if airport else 60
        layover = int((second.flight.estimated_departure - first.flight.estimated_arrival).total_seconds() // 60)
        any_cancelled = "cancelled" in (first.flight.status, second.flight.status)
        checks.append(
            schemas.ConnectionCheck(
                airport=first.flight.destination,
                layover_minutes=layover,
                minimum_required_minutes=minimum,
                feasible=layover >= minimum and not any_cancelled,
            )
        )
    return checks


def get_booking(db: Session, pnr: str) -> schemas.BookingOut | None:
    stmt = (
        select(Booking)
        .where(Booking.pnr == pnr.strip().upper())
        .options(
            joinedload(Booking.passenger),
            selectinload(Booking.segments)
            .joinedload(Segment.flight_instance)
            .joinedload(FlightInstance.flight),
        )
    )
    booking = db.scalars(stmt).first()
    if booking is None:
        return None

    segments = [
        schemas.SegmentOut(order=s.segment_order, status=s.status, flight=_flight_status(s.flight_instance))
        for s in booking.segments
    ]
    p = booking.passenger
    return schemas.BookingOut(
        pnr=booking.pnr,
        fare_class=booking.fare_class,
        ticket_price=float(booking.ticket_price),
        currency=booking.currency,
        status=booking.status,
        passenger=schemas.PassengerOut(
            full_name=p.full_name,
            loyalty_tier=p.loyalty_tier,
            needs_assistance=p.needs_assistance,
            is_unaccompanied_minor=p.is_unaccompanied_minor,
            remarks=p.remarks,
        ),
        segments=segments,
        connections=_connection_checks(db, segments),
    )


def _flight_query():
    return (
        select(FlightInstance)
        .join(FlightInstance.flight)
        .options(contains_eager(FlightInstance.flight))
        .order_by(FlightInstance.scheduled_departure)
    )


def get_flight_status(db: Session, flight_number: str, day: date) -> schemas.FlightStatus | None:
    stmt = _flight_query().where(
        Flight.flight_number == flight_number.strip().upper(), FlightInstance.flight_date == day
    )
    inst = db.scalars(stmt).first()
    return _flight_status(inst) if inst else None


def search_flights(db: Session, origin: str, destination: str, day: date) -> list[schemas.FlightStatus]:
    stmt = _flight_query().where(
        Flight.origin == origin.strip().upper(),
        Flight.destination == destination.strip().upper(),
        FlightInstance.flight_date == day,
    )
    return [_flight_status(i) for i in db.scalars(stmt).all()]