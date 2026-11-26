from sqlalchemy import text

from app.db import Base, engine
import app.models  # noqa: F401  (importing registers the tables)

with engine.begin() as connection:
    # pgvector adds the "vector" column type to Postgres. Safe to run many times.
    connection.execute(text("CREATE EXTENSION IF NOT EXISTS vector"))

Base.metadata.create_all(engine)
print("Tables:", ", ".join(Base.metadata.tables))