from app import rag, tools


def fake_hits(*scored):
    return [rag.Hit("SkyDesk Disruption Policy", "Part 2. Delays", section, "Title", f"text {section}", score)
            for section, score in scored]


def patch_search(monkeypatch, hits):
    monkeypatch.setattr(tools.rag, "search", lambda db, query, k=4, **kw: hits)


def test_returns_relevant_sections_with_citations(monkeypatch):
    patch_search(monkeypatch, fake_hits(("2.4", 0.82), ("3.2", 0.7)))
    result = tools.search_policy("hotel for overnight delay")
    assert [r["citation"] for r in result["results"]] == [
        "SkyDesk Disruption Policy §2.4", "SkyDesk Disruption Policy §3.2"]


def test_drops_sections_below_the_threshold(monkeypatch):
    patch_search(monkeypatch, fake_hits(("2.4", 0.82), ("7.4", tools.MIN_POLICY_SCORE - 0.1)))
    result = tools.search_policy("hotel")
    assert [r["citation"].split("§")[1] for r in result["results"]] == ["2.4"]


def test_nothing_relevant_tells_the_model_not_to_state_entitlements(monkeypatch):
    patch_search(monkeypatch, fake_hits(("7.4", 0.1)))
    result = tools.search_policy("capital of France")
    assert result["results"] == []
    assert "Do not state any entitlement" in result["note"]


def test_rejects_empty_and_huge_queries():
    assert "error" in tools.search_policy("   ")
    assert "error" in tools.search_policy("x" * 501)


def test_policy_tool_is_registered_for_the_model():
    assert "search_policy" in tools.TOOL_MAP
    assert tools.search_policy in tools.TOOLS
