from datetime import date, datetime, timezone

from fastapi import Depends, FastAPI, HTTPException, Query
from sqlalchemy.orm import Session

from app import schemas, services
from app.deps import get_db

app = FastAPI(title="SkyDesk", description="Synthetic airline data API (demo project)")


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/bookings/{pnr}", response_model=schemas.BookingOut)
def read_booking(pnr: str, db: Session = Depends(get_db)):
    booking = services.get_booking(db, pnr)
    if booking is None:
        raise HTTPException(status_code=404, detail=f"No booking found for PNR {pnr.upper()}")
    return booking


@app.get("/flights", response_model=list[schemas.FlightStatus])
def search_flights(
    origin: str = Query(min_length=3, max_length=3),
    destination: str = Query(min_length=3, max_length=3),
    flight_date: date = Query(alias="date"),
    db: Session = Depends(get_db),
):
    """All flights on a route for one day (alternatives to offer a passenger)."""
    return services.search_flights(db, origin, destination, flight_date)


@app.get("/flights/{flight_number}", response_model=schemas.FlightStatus)
def read_flight(
    flight_number: str,
    flight_date: date | None = Query(default=None, alias="date"),
    db: Session = Depends(get_db),
):
    """Status of one flight on one day (defaults to today, UTC)."""
    day = flight_date or datetime.now(timezone.utc).date()
    flight = services.get_flight_status(db, flight_number, day)
    if flight is None:
        raise HTTPException(status_code=404, detail=f"No flight {flight_number.upper()} on {day}")
    return flight