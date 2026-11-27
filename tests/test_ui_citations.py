from pathlib import Path

from streamlit.testing.v1 import AppTest

from app import agent
from app.agent import AgentResult

APP = str(Path(__file__).parent.parent / "streamlit_app.py")


def test_unverified_citation_shows_a_warning(monkeypatch):
    result = AgentResult(answer="Hotel [SkyDesk Disruption Policy §9.9]", tool_calls=[], steps=1,
                         unverified_citations=["9.9"])
    monkeypatch.setattr(agent, "run_agent", lambda question: result)
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.chat_input[0].set_value("anything").run()
    assert not at.exception
    assert any("§9.9" in w.value for w in at.warning)


def test_verified_answer_shows_no_warning(monkeypatch):
    result = AgentResult(answer="Hotel [SkyDesk Disruption Policy §2.4]", tool_calls=[], steps=1)
    monkeypatch.setattr(agent, "run_agent", lambda question: result)
    at = AppTest.from_file(APP, default_timeout=15).run()
    at.chat_input[0].set_value("anything").run()
    assert not at.warning
