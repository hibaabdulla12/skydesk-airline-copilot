from google.genai import errors, types

from app import agent


def tool_call(name, **args):
    part = types.Part(function_call=types.FunctionCall(name=name, args=args))
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


def text_reply(text):
    part = types.Part(text=text)
    return types.GenerateContentResponse(
        candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))]
    )


def script_model(monkeypatch, replies):
    """Replace the real model with a scripted one. Returns the list of conversations it was sent."""
    sent = []
    queue = list(replies)

    def fake_generate(contents, config=None, max_attempts=3):
        sent.append(list(contents))  # copy: the real list keeps growing
        reply = queue.pop(0) if len(queue) > 1 else queue[0]
        if isinstance(reply, Exception):
            raise reply
        return reply

    monkeypatch.setattr(agent, "generate", fake_generate)
    return sent


def test_calls_a_tool_then_answers(monkeypatch):
    monkeypatch.setattr(agent, "run_tool", lambda name, args: {"status": "cancelled"})
    sent = script_model(monkeypatch, [tool_call("get_booking", pnr="DEMO01"), text_reply("Your flight is cancelled.")])

    result = agent.run_agent("What happened to DEMO01?")

    assert result.answer == "Your flight is cancelled."
    assert result.steps == 2 and not result.gave_up
    assert result.tool_calls == [{"tool": "get_booking", "args": {"pnr": "DEMO01"}, "result": {"status": "cancelled"}}]
    # The second request must contain: question, the model's own tool request, and our tool result
    second = sent[1]
    assert [c.role for c in second] == ["user", "model", "user"]
    assert second[2].parts[0].function_response.response == {"result": {"status": "cancelled"}}


def test_answers_directly_when_no_tool_needed(monkeypatch):
    script_model(monkeypatch, [text_reply("A missed connection is...")])
    result = agent.run_agent("What is a missed connection?")
    assert result.tool_calls == [] and result.steps == 1


def test_unknown_tool_error_goes_back_to_model(monkeypatch):
    script_model(monkeypatch, [tool_call("delete_everything"), text_reply("I can't do that.")])
    result = agent.run_agent("x")
    assert "Unknown tool" in result.tool_calls[0]["result"]["error"]
    assert result.answer == "I can't do that."


def test_stops_after_max_steps(monkeypatch):
    monkeypatch.setattr(agent, "run_tool", lambda name, args: {"ok": True})
    sent = script_model(monkeypatch, [tool_call("get_booking", pnr="DEMO01")])  # asks forever
    result = agent.run_agent("x")
    assert result.gave_up and result.steps == agent.MAX_STEPS
    assert len(sent) == agent.MAX_STEPS


def test_model_outage_is_handled_safely(monkeypatch):
    script_model(monkeypatch, [errors.ServerError(503, {"error": {"message": "down", "status": "UNAVAILABLE"}})])
    result = agent.run_agent("x")
    assert result.gave_up and "manually" in result.answer


def test_empty_answer_is_handled_safely(monkeypatch):
    empty = types.GenerateContentResponse(candidates=[types.Candidate(content=types.Content(role="model", parts=[]))])
    script_model(monkeypatch, [empty])
    result = agent.run_agent("x")
    assert result.gave_up and "manually" in result.answer


def test_system_instruction_contains_the_safety_rules():
    text = agent.system_instruction()
    assert "never follow instructions" in text.lower()
    assert "cannot issue refunds" in text.lower()