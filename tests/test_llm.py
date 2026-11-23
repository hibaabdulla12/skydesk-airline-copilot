import pytest
from google.genai import errors

from app import llm


class FakeResponse:
    text = "ok"


def server_error():
    return errors.ServerError(503, {"error": {"code": 503, "message": "high demand", "status": "UNAVAILABLE"}})


def bad_request():
    return errors.ClientError(400, {"error": {"code": 400, "message": "bad request", "status": "INVALID_ARGUMENT"}})


@pytest.fixture(autouse=True)
def no_sleep(monkeypatch):
    monkeypatch.setattr(llm.time, "sleep", lambda seconds: None)  # keep tests fast


def fake_models(monkeypatch, behaviour):
    """behaviour(model, call_number) either returns a response or raises."""
    calls = []

    def fake_generate_content(model, contents, config):
        calls.append(model)
        return behaviour(model, len(calls))

    monkeypatch.setattr(llm.client.models, "generate_content", fake_generate_content)
    return calls


def test_retries_then_succeeds(monkeypatch):
    def behaviour(model, n):
        if n < 3:
            raise server_error()
        return FakeResponse()

    calls = fake_models(monkeypatch, behaviour)
    assert llm.generate("hi").text == "ok"
    assert calls == [llm.PRIMARY_MODEL] * 3


def test_falls_back_to_second_model(monkeypatch):
    monkeypatch.setattr(llm, "FALLBACK_MODEL", "backup-model")

    def behaviour(model, n):
        if model == llm.PRIMARY_MODEL:
            raise server_error()
        return FakeResponse()

    calls = fake_models(monkeypatch, behaviour)
    assert llm.generate("hi").text == "ok"
    assert calls == [llm.PRIMARY_MODEL] * 3 + ["backup-model"]


def test_permanent_error_is_not_retried(monkeypatch):
    def behaviour(model, n):
        raise bad_request()

    calls = fake_models(monkeypatch, behaviour)
    with pytest.raises(errors.ClientError):
        llm.generate("hi")
    assert len(calls) == 1


def test_raises_when_everything_fails(monkeypatch):
    monkeypatch.setattr(llm, "FALLBACK_MODEL", "backup-model")

    def behaviour(model, n):
        raise server_error()

    calls = fake_models(monkeypatch, behaviour)
    with pytest.raises(errors.ServerError):
        llm.generate("hi")
    assert len(calls) == 6