from app.db import Base, engine
import app.models  # noqa: F401  (importing registers the tables)

Base.metadata.create_all(engine)
print("Tables:", ", ".join(Base.metadata.tables))
