"""Read the policy files, embed every section, and store the vectors in the database."""
from app.db import SessionLocal
from app.rag import ingest, load_policy_chunks

chunks = load_policy_chunks()
print(f"Read {len(chunks)} sections. Embedding them (the first run downloads a small model)...")

with SessionLocal() as session:
    ingest(session, chunks)
    session.commit()

print("Done. Stored", len(chunks), "sections in policy_chunks.")