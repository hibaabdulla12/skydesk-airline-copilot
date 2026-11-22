import os

from dotenv import load_dotenv
from google import genai

load_dotenv()
client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

# Ask Google which models this key can use for text generation
for model in client.models.list():
    if "generateContent" in (model.supported_actions or []):
        print(model.name)