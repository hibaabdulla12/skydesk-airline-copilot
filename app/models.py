from datetime import date, datetime, time
from decimal import Decimal
from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    JSON, Boolean, Date, DateTime, ForeignKey, Integer, Numeric,
    String, Text, Time, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db import Base


class Airport(Base):
    __tablename__ = "airports"
    code: Mapped[str] = mapped_column(String(3), primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    city: Mapped[str] = mapped_column(String(80))
    country: Mapped[str] = mapped_column(String(80))
    min_connection_minutes: Mapped[int] = mapped_column(Integer, default=60)


class Flight(Base):
    __tablename__ = "flights"
    id: Mapped[int] = mapped_column(primary_key=True)
    flight_number: Mapped[str] = mapped_column(String(8), index=True)
    origin: Mapped[str] = mapped_column(String(3), ForeignKey("airports.code"))
    destination: Mapped[str] = mapped_column(String(3), ForeignKey("airports.code"))
    departure_time: Mapped[time] = mapped_column(Time)
    duration_minutes: Mapped[int] = mapped_column(Integer)


class FlightInstance(Base):
    __tablename__ = "flight_instances"
    id: Mapped[int] = mapped_column(primary_key=True)
    flight_id: Mapped[int] = mapped_column(ForeignKey("flights.id"))
    flight_date: Mapped[date] = mapped_column(Date, index=True)
    scheduled_departure: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    scheduled_arrival: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    status: Mapped[str] = mapped_column(String(20), default="scheduled")
    delay_minutes: Mapped[int] = mapped_column(Integer, default=0)
    disruption_reason: Mapped[str | None] = mapped_column(String(40))
    flight: Mapped["Flight"] = relationship()


class Passenger(Base):
    __tablename__ = "passengers"
    id: Mapped[int] = mapped_column(primary_key=True)
    full_name: Mapped[str] = mapped_column(String(120))
    email: Mapped[str] = mapped_column(String(120))
    loyalty_tier: Mapped[str] = mapped_column(String(20), default="none")
    needs_assistance: Mapped[bool] = mapped_column(Boolean, default=False)
    is_unaccompanied_minor: Mapped[bool] = mapped_column(Boolean, default=False)
    remarks: Mapped[str | None] = mapped_column(Text)


class Booking(Base):
    __tablename__ = "bookings"
    id: Mapped[int] = mapped_column(primary_key=True)
    pnr: Mapped[str] = mapped_column(String(6), unique=True, index=True)
    passenger_id: Mapped[int] = mapped_column(ForeignKey("passengers.id"))
    fare_class: Mapped[str] = mapped_column(String(1))
    ticket_price: Mapped[Decimal] = mapped_column(Numeric(10, 2))
    currency: Mapped[str] = mapped_column(String(3), default="INR")
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    passenger: Mapped["Passenger"] = relationship()
    segments: Mapped[list["Segment"]] = relationship(
        back_populates="booking", order_by="Segment.segment_order"
    )


class Segment(Base):
    __tablename__ = "segments"
    id: Mapped[int] = mapped_column(primary_key=True)
    booking_id: Mapped[int] = mapped_column(ForeignKey("bookings.id"))
    flight_instance_id: Mapped[int] = mapped_column(ForeignKey("flight_instances.id"))
    segment_order: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="confirmed")
    booking: Mapped["Booking"] = relationship(back_populates="segments")
    flight_instance: Mapped["FlightInstance"] = relationship()


class ActionLog(Base):
    __tablename__ = "action_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(String(40))
    action: Mapped[str] = mapped_column(String(40))
    pnr: Mapped[str | None] = mapped_column(String(6))
    details: Mapped[dict | None] = mapped_column(JSON)


class PolicyChunk(Base):
    """One section of the policy document, stored with its embedding (vector) for search."""
    __tablename__ = "policy_chunks"
    id: Mapped[int] = mapped_column(primary_key=True)
    source: Mapped[str] = mapped_column(String(120))
    part: Mapped[str] = mapped_column(String(120))
    section: Mapped[str] = mapped_column(String(20), index=True)
    title: Mapped[str] = mapped_column(String(200))
    content: Mapped[str] = mapped_column(Text)
    embedding: Mapped[list[float]] = mapped_column(Vector(384))
