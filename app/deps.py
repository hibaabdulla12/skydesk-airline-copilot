from collections.abc import Iterator

from sqlalchemy.orm import Session

from app.db import SessionLocal


def get_db() -> Iterator[Session]:
    """Give each request its own database session, and always close it afterwards."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()