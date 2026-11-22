import logging

from google.genai import types

from app.llm import generate

logging.basicConfig(level=logging.INFO)

response = generate(
    "In two sentences, explain what a missed connection is for an airline passenger.",
    config=types.GenerateContentConfig(
        system_instruction="You are a helpful airline operations assistant. Be concise.",
    ),
)

print(response.text)
print("total tokens used:", response.usage_metadata.total_token_count)
