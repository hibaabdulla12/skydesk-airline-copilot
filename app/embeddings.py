"""Turns text into vectors (lists of numbers) so that texts with similar MEANING end up close together.

Runs locally on the CPU: free, no API quota, and no text leaves the machine.
The model is downloaded once (about 70 MB) the first time it is used.
"""
from functools import lru_cache

MODEL_NAME = "BAAI/bge-small-en-v1.5"
EMBEDDING_DIM = 384  # must match the Vector(384) column in models.py


@lru_cache(maxsize=1)
def _model():
    # Imported here so that the app and the tests start fast and only load the model when needed
    from fastembed import TextEmbedding

    return TextEmbedding(MODEL_NAME)


def embed_passages(texts: list[str]) -> list[list[float]]:
    """Vectors for documents (the chunks we store)."""
    return [vector.tolist() for vector in _model().passage_embed(texts)]


def embed_query(text: str) -> list[float]:
    """Vector for a question. This model embeds questions slightly differently from documents."""
    return next(iter(_model().query_embed([text]))).tolist()