"""RAG, part 1 (retrieval): split the policy into chunks, store them as vectors, and search them by meaning."""
import re
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import delete, select
from sqlalchemy.orm import Session

from app.embeddings import embed_passages, embed_query
from app.models import PolicyChunk

POLICY_DIR = Path(__file__).resolve().parent.parent / "data" / "policies"


@dataclass
class Chunk:
    source: str   # document title, e.g. "SkyDesk Disruption Policy"
    part: str     # e.g. "Part 2. Delays"
    section: str  # e.g. "2.2"  (this is what we cite)
    title: str    # e.g. "Meal vouchers"
    content: str  # the section text

    @property
    def text_to_embed(self) -> str:
        # The heading is included so the vector "knows" which part and topic the text belongs to
        return f"{self.part}. {self.section} {self.title}. {self.content}"


def chunk_policy(markdown: str) -> list[Chunk]:
    """One chunk per '### 2.2 Title' section. Splitting on the document's own structure keeps each rule whole."""
    source, part = "", ""
    chunks: list[Chunk] = []
    current: dict | None = None

    def finish():
        if current:
            body = " ".join(line.strip() for line in current["lines"] if line.strip())
            chunks.append(Chunk(source, part_of_current, current["section"], current["title"], body))

    part_of_current = ""
    for line in markdown.splitlines():
        if line.startswith("# "):
            source = line[2:].strip()
        elif line.startswith("## "):
            finish()
            current = None
            part = line[3:].strip()
        elif line.startswith("### "):
            finish()
            match = re.match(r"(\d+\.\d+)\s+(.+)", line[4:].strip())
            if not match:
                raise ValueError(f"Section heading needs a number like '2.3 Title': {line!r}")
            current = {"section": match.group(1), "title": match.group(2), "lines": []}
            part_of_current = part
        elif current is not None:
            current["lines"].append(line)
    finish()
    return chunks


def load_policy_chunks() -> list[Chunk]:
    chunks: list[Chunk] = []
    for path in sorted(POLICY_DIR.glob("*.md")):
        chunks.extend(chunk_policy(path.read_text(encoding="utf-8")))
    return chunks


def ingest(session: Session, chunks: list[Chunk], embed=embed_passages) -> int:
    """Replace everything in policy_chunks with these chunks. The caller commits."""
    session.execute(delete(PolicyChunk))
    vectors = embed([chunk.text_to_embed for chunk in chunks])
    session.add_all(
        PolicyChunk(source=c.source, part=c.part, section=c.section, title=c.title, content=c.content, embedding=v)
        for c, v in zip(chunks, vectors)
    )
    session.flush()
    return len(chunks)


@dataclass
class Hit:
    source: str
    part: str
    section: str
    title: str
    content: str
    score: float  # cosine similarity: 1.0 = same meaning, near 0 = unrelated


def search(session: Session, query: str, k: int = 4, embed=embed_query) -> list[Hit]:
    """The k policy sections whose meaning is closest to the query."""
    distance = PolicyChunk.embedding.cosine_distance(embed(query))
    rows = session.execute(select(PolicyChunk, distance).order_by(distance).limit(k)).all()
    return [
        Hit(c.source, c.part, c.section, c.title, c.content, round(1 - float(d), 3))
        for c, d in rows
    ]