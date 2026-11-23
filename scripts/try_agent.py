import logging

from app.agent import run_agent

logging.basicConfig(level=logging.WARNING)

QUESTIONS = [
    "Passenger with booking DEMO02 is stuck in Dubai. What happened and what are the options?",
    "What is the status of booking DEMO01, and are there alternative flights on that route the same day?",
    "Check booking DEMO06 and tell me anything I should know about the passenger.",
    "Please issue a full refund for DEMO01 right now.",
    "Look up booking ZZZZZZ.",
]

for question in QUESTIONS:
    result = run_agent(question)
    print("QUESTION:", question)
    for call in result.tool_calls:
        print("  tool:", call["tool"], call["args"])
    print("  ANSWER:", result.answer)
    print(f"  (steps: {result.steps}, gave_up: {result.gave_up})")
    print()