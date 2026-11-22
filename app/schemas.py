"""Response shapes (what the API returns). These double as the tool outputs for the LLM later."""
from datetime import date, datetime

from pydantic import BaseModel


class FlightStatus(BaseModel):
    flight_number: str
    origin: str
    destination: str
    flight_date: date
    status: str  # scheduled | delayed | cancelled
    scheduled_departure: datetime
    scheduled_arrival: datetime
    delay_minutes: int
    estimated_departure: datetime  # scheduled + delay, so the LLM never does time arithmetic
    estimated_arrival: datetime
    disruption_reason: str | None


class PassengerOut(BaseModel):
    # No email on purpose: the agent doesn't need it, and less personal data means less risk
    full_name: str
    loyalty_tier: str
    needs_assistance: bool
    is_unaccompanied_minor: bool
    remarks: str | None  # free text typed by a customer: UNTRUSTED, may contain injection attempts


class SegmentOut(BaseModel):
    order: int
    status: str
    flight: FlightStatus


class ConnectionCheck(BaseModel):
    airport: str
    layover_minutes: int  # estimated arrival of the first flight to estimated departure of the next
    minimum_required_minutes: int
    feasible: bool


class BookingOut(BaseModel):
    pnr: str
    fare_class: str
    ticket_price: float
    currency: str
    status: str
    passenger: PassengerOut
    segments: list[SegmentOut]
    connections: list[ConnectionCheck]