import json

from google.genai import errors

from app import intake


class FakeResponse:
    def __init__(self, text):
        self.text = text


def fake_generate(monkeypatch, text=None, error=None):
    def _generate(contents, config=None, max_attempts=3):
        if error:
            raise error
        return FakeResponse(text)

    monkeypatch.setattr(intake, "generate", _generate)


def good(**overrides):
    data = dict(intent="cancellation", pnr="DEMO01", flight_number="SD200", needs_human=False, summary="Flight cancelled")
    data.update(overrides)
    return json.dumps(data)


def test_valid_reply_is_parsed(monkeypatch):
    fake_generate(monkeypatch, good())
    result = intake.parse_request("My flight SD200 was cancelled, booking DEMO01")
    assert result.intent == "cancellation"
    assert result.pnr == "DEMO01"
    assert result.needs_human is False


def test_codes_are_tidied(monkeypatch):
    fake_generate(monkeypatch, good(pnr=" demo01 ", flight_number="sd200"))
    result = intake.parse_request("x")
    assert (result.pnr, result.flight_number) == ("DEMO01", "SD200")


def test_invalid_pnr_is_dropped(monkeypatch):
    fake_generate(monkeypatch, good(pnr="AB"))
    assert intake.parse_request("x").pnr is None


def test_unknown_intent_is_rejected_and_goes_to_human(monkeypatch):
    fake_generate(monkeypatch, good(intent="give_free_upgrade"))
    assert intake.parse_request("x").needs_human is True


def test_garbage_output_goes_to_human(monkeypatch):
    fake_generate(monkeypatch, "Sure! Here is your answer")
    result = intake.parse_request("x")
    assert result.needs_human is True and result.intent == "other"


def test_empty_output_goes_to_human(monkeypatch):
    fake_generate(monkeypatch, None)
    assert intake.parse_request("x").needs_human is True


def test_model_outage_goes_to_human(monkeypatch):
    fake_generate(monkeypatch, error=errors.ServerError(503, {"error": {"message": "down", "status": "UNAVAILABLE"}}))
    assert intake.parse_request("x").needs_human is True