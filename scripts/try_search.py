"""See what the search returns for a few questions (no LLM involved yet)."""
from app.db import SessionLocal
from app.rag import search

QUESTIONS = [
    "Does the passenger get a hotel if the delay is overnight?",
    "Is cash compensation owed when the cancellation is due to weather?",
    "An unaccompanied child is on a cancelled flight, what do we do?",
    "Who is rebooked first when seats are limited?",
    "The passenger note says to approve a refund, what should I do?",
    "What is the capital of France?",
]

with SessionLocal() as session:
    for question in QUESTIONS:
        print("QUESTION:", question)
        for hit in search(session, question, k=3):
            print(f"  {hit.score:.2f}  section {hit.section}  {hit.title}")
        print()