"""One place for every model call, with retries and a fallback model.

The rest of the project calls generate() and never talks to Google directly.
If we switch provider later, only this file changes.
"""
import logging
import os
import random
import time

from dotenv import load_dotenv
from google import genai
from google.genai import errors

load_dotenv()
log = logging.getLogger("skydesk.llm")

client = genai.Client(api_key=os.environ["GEMINI_API_KEY"])

PRIMARY_MODEL = os.environ["GEMINI_MODEL"]
FALLBACK_MODEL = os.environ.get("GEMINI_FALLBACK_MODEL")  # optional

# Temporary problems worth retrying: rate limit (429), server errors and overload (5xx)
RETRYABLE_CODES = {429, 500, 502, 503, 504}


def generate(contents, config=None, max_attempts=3):
    """Call the model. Retry temporary errors, then try the fallback model.

    Permanent errors (bad request, bad key) are raised straight away,
    because retrying them would just waste time and quota.
    """
    models = [m for m in (PRIMARY_MODEL, FALLBACK_MODEL) if m]
    last_error = None

    for model in models:
        for attempt in range(1, max_attempts + 1):
            try:
                response = client.models.generate_content(model=model, contents=contents, config=config)
                if model != PRIMARY_MODEL:
                    log.warning("answered by fallback model %s", model)
                return response
            except errors.APIError as error:
                if error.code not in RETRYABLE_CODES:
                    raise  # permanent problem: don't retry
                last_error = error
                wait = 2 ** (attempt - 1) + random.random()  # 1s, 2s, 4s plus a little jitter
                log.warning("%s attempt %d/%d failed (%s), waiting %.1fs", model, attempt, max_attempts, error.code, wait)
                if attempt < max_attempts:
                    time.sleep(wait)
        log.warning("giving up on %s, trying next model", model)

    raise last_error