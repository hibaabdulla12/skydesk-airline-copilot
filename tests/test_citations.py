from google.genai import types

from app import agent
from scripts.tune_threshold import suggest


def policy_call(*sections):
    results = [{"citation": f"SkyDesk Disruption Policy §{s}", "title": "t", "text": "x", "score": 0.8} for s in sections]
    return {"tool": "search_policy", "args": {"query": "q"}, "result": {"results": results}}


def test_citation_that_was_retrieved_is_verified():
    answer = "Hotel is provided [SkyDesk Disruption Policy §2.4]."
    assert agent.verify_citations(answer, [policy_call("2.4", "3.2")]) == []


def test_invented_citation_is_flagged():
    answer = "Hotel [SkyDesk Disruption Policy §2.4] and a free upgrade [SkyDesk Disruption Policy §9.9]."
    assert agent.verify_citations(answer, [policy_call("2.4")]) == ["9.9"]


def test_citation_without_any_policy_search_is_flagged():
    assert agent.verify_citations("See §2.4", []) == ["2.4"]


def test_answer_without_citations_has_nothing_to_flag():
    assert agent.verify_citations("The flight is cancelled.", []) == []


def test_empty_search_results_do_not_crash():
    trace = [{"tool": "search_policy", "args": {}, "result": {"results": [], "note": "none"}},
             {"tool": "search_policy", "args": {}, "result": {"error": "bad"}}]
    assert agent.verify_citations("See §2.4", trace) == ["2.4"]


def test_run_agent_reports_unverified_citations(monkeypatch):
    def reply(part):
        return types.GenerateContentResponse(
            candidates=[types.Candidate(content=types.Content(role="model", parts=[part]))])

    queue = [reply(types.Part(text="You get a hotel [SkyDesk Disruption Policy §9.9]."))]
    monkeypatch.setattr(agent, "generate", lambda contents, config=None, max_attempts=3: queue[0])
    result = agent.run_agent("x")
    assert result.unverified_citations == ["9.9"]


def test_prompt_demands_citations_and_refuses_to_guess_amounts():
    text = agent.system_instruction().lower()
    assert "never state an entitlement without a citation" in text
    assert "do not calculate compensation amounts" in text


def test_suggest_threshold_between_the_two_groups():
    assert suggest([0.8, 0.7, 0.75], [0.4, 0.5]) == 0.6


def test_suggest_threshold_reports_overlap():
    assert suggest([0.8, 0.5], [0.6]) is None
