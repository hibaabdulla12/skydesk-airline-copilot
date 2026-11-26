"""Check that the embedding model works: right vector size, and related texts score higher."""
import math

from app.embeddings import EMBEDDING_DIM, embed_passages, embed_query


def cosine(a, b):
    dot = sum(x * y for x, y in zip(a, b))
    return dot / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)))


question = embed_query("Does the passenger get a hotel when the delay lasts overnight?")
print("vector length:", len(question), "(expected", EMBEDDING_DIM, ")")

texts = [
    "A hotel room is provided when a delay means the passenger must wait overnight.",
    "Each passenger receives a meal voucher after a delay of two hours.",
    "The capital of France is Paris.",
]
for text, vector in zip(texts, embed_passages(texts)):
    print(f"  similarity {cosine(question, vector):.2f}  {text}")