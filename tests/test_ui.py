from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import agent
from app.agent import AgentResult

APP = str(Path(__file__).parent.parent / "streamlit_app.py")

FAKE = AgentResult(
    answer="The connection in Dubai is missed.",
    tool_calls=[{"tool": "get_booking", "args": {"pnr": "DEMO02"}, "result": {"connections": []}}],
    steps=2,
)


def open_app():
    return AppTest.from_file(APP, default_timeout=15).run()


def chat_texts(at):
    return [m.markdown[0].value for m in at.chat_message if m.markdown]


def test_typed_question_shows_answer_and_tool_calls(monkeypatch):
    monkeypatch.setattr(agent, "run_agent", lambda question: FAKE)
    at = open_app()
    at.chat_input[0].set_value("What happened to DEMO02?").run()
    assert not at.exception
    assert chat_texts(at) == ["What happened to DEMO02?", "The connection in Dubai is missed."]
    assert "1 tool calls" in at.expander[0].label


def test_demo_button_asks_the_question(monkeypatch):
    asked = []
    monkeypatch.setattr(agent, "run_agent", lambda question: asked.append(question) or FAKE)
    at = open_app()
    at.sidebar.button[1].click().run()  # DEMO02
    assert not at.exception
    assert "DEMO02" in asked[0]


def test_crash_in_agent_shows_friendly_message(monkeypatch):
    def boom(question):
        raise RuntimeError("database exploded")

    monkeypatch.setattr(agent, "run_agent", boom)
    at = open_app()
    at.chat_input[0].set_value("anything").run()
    assert not at.exception  # the UI must not show a traceback to the user
    assert "Something went wrong" in chat_texts(at)[-1]
    assert at.warning


def test_gave_up_shows_warning(monkeypatch):
    monkeypatch.setattr(agent, "run_agent", lambda q: AgentResult(answer="x", tool_calls=[], steps=6, gave_up=True))
    at = open_app()
    at.chat_input[0].set_value("anything").run()
    assert at.warning