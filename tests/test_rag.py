import hashlib
import math

import pytest

from app import rag
from app.db import SessionLocal
from app.embeddings import EMBEDDING_DIM
from app.models import PolicyChunk

SAMPLE = """# Test Policy

## Part 1. First part

### 1.1 Alpha rule
Line one of alpha.
Line two of alpha.

### 1.2 Beta rule
Beta text.

## Part 2. Second part

### 2.1 Gamma rule
Gamma text.
"""


def fake_vector(text: str) -> list[float]:
    """A stand-in embedder: texts that share words get similar vectors. Fast, offline, deterministic."""
    vector = [0.0] * EMBEDDING_DIM
    for word in text.lower().replace(".", " ").replace(",", " ").split():
        vector[int(hashlib.md5(word.encode()).hexdigest(), 16) % EMBEDDING_DIM] += 1.0
    norm = math.sqrt(sum(x * x for x in vector)) or 1.0
    return [x / norm for x in vector]


def fake_passages(texts):
    return [fake_vector(t) for t in texts]


@pytest.fixture
def session():
    """A database session whose changes are rolled back, so tests never touch your real ingested data."""
    with SessionLocal() as db:
        yield db
        db.rollback()


def test_chunker_splits_on_sections_and_keeps_context():
    chunks = rag.chunk_policy(SAMPLE)
    assert [c.section for c in chunks] == ["1.1", "1.2", "2.1"]
    assert chunks[0].content == "Line one of alpha. Line two of alpha."
    assert chunks[2].part == "Part 2. Second part"
    assert chunks[0].source == "Test Policy"
    assert "Part 1. First part" in chunks[0].text_to_embed and "Alpha rule" in chunks[0].text_to_embed


def test_chunker_rejects_heading_without_a_number():
    with pytest.raises(ValueError):
        rag.chunk_policy("# P\n\n## Part 1\n\n### Missing number\ntext")


def test_real_policy_file_is_well_formed():
    chunks = rag.load_policy_chunks()
    sections = [c.section for c in chunks]
    assert len(chunks) >= 20
    assert len(sections) == len(set(sections)), "section numbers must be unique, they are used as citations"
    assert all(c.content and c.title and c.part and c.source for c in chunks)


def test_vector_column_matches_embedding_size():
    assert PolicyChunk.__table__.c.embedding.type.dim == EMBEDDING_DIM


def test_search_finds_the_most_relevant_section(session):
    rag.ingest(session, rag.load_policy_chunks(), embed=fake_passages)
    hits = rag.search(session, "meal voucher when the delay is 2 hours or more", k=3, embed=fake_vector)
    assert hits[0].section == "2.2"
    assert hits[0].score >= hits[1].score >= hits[2].score


def test_search_finds_a_second_topic(session):
    rag.ingest(session, rag.load_policy_chunks(), embed=fake_passages)
    hits = rag.search(session, "unaccompanied minor never left alone", k=2, embed=fake_vector)
    assert hits[0].section == "6.1"


def test_ingest_replaces_instead_of_duplicating(session):
    chunks = rag.load_policy_chunks()
    rag.ingest(session, chunks, embed=fake_passages)
    rag.ingest(session, chunks, embed=fake_passages)
    assert session.query(PolicyChunk).count() == len(chunks)