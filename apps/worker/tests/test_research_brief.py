from datetime import UTC, datetime

import pytest

from app.jobs.research_brief import run_budgeted_research_brief, run_research_brief


class FakeResearchSink:
    def __init__(self) -> None:
        self.topn = [
            {
                "article_id": 1,
                "title": "Agents need evals",
                "content_text": "Evaluation harnesses catch regressions early.",
            },
            {
                "article_id": 2,
                "title": "RAG tradeoffs",
                "content_text": "Chunking strategy dominates retrieval quality.",
            },
        ]
        self.project = [
            {
                "article_id": 9,
                "title": "Project note",
                "summary_zh": "立项摘要",
            }
        ]
        self.topic_hits = [
            {
                "article_id": 3,
                "title": "Open-source LLM tooling",
                "content_text": "Tooling improves open source model ops.",
            }
        ]
        self.calls: list[tuple[str, dict[str, object]]] = []

    def list_topn_articles(self, *, limit: int) -> list[dict[str, object]]:
        self.calls.append(("topn", {"limit": limit}))
        return self.topn[:limit]

    def list_project_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]:
        self.calls.append(("project", {"user_id": user_id, "limit": limit}))
        return self.project[:limit]

    def search_articles_by_topic(self, *, topic: str, limit: int) -> list[dict[str, object]]:
        self.calls.append(("topic", {"topic": topic, "limit": limit}))
        return self.topic_hits[:limit]


class RecordingResearchProvider:
    model_provider = "minimax"

    def __init__(self) -> None:
        self.calls = 0

    def research_answer(self, *, question, citations, scope):
        self.calls += 1
        return f"{scope}: {question} ({len(citations)})"


class RejectingAgentLedger:
    def charge(self, account: str, units: int = 1, *, limit: int = 0) -> int:
        assert account == "agent"
        assert units == 1
        assert limit == 0
        raise RuntimeError("daily budget exceeded for agent")


def test_research_brief_topn_builds_mock_citations():
    sink = FakeResearchSink()
    result = run_research_brief(
        {"scope": "topn", "question": "What matters for agents?", "max_articles": 5},
        sink,
        now=datetime(2026, 7, 18, 10, 0, tzinfo=UTC),
    )
    assert result["status"] == "ok"
    assert result["article_count"] == 2
    brief = result["brief"]
    assert brief["provider"] == "mock"
    assert brief["question"] == "What matters for agents?"
    assert len(brief["citations"]) == 2
    assert brief["citations"][0] == {
        "article_id": 1,
        "title": "Agents need evals",
        "quote": "Evaluation harnesses catch regressions early.",
        "relevance": "mock",
        "question_hint": "What matters for agents?",
    }
    assert "mock" in brief["answer"].lower() or "（mock）" in brief["answer"]
    assert sink.calls == [("topn", {"limit": 5})]


def test_research_brief_project_requires_user_and_loads_project_articles():
    sink = FakeResearchSink()
    with pytest.raises(ValueError, match="user_id"):
        run_research_brief(
            {"scope": "project", "question": "summarize project"},
            sink,
        )
    result = run_research_brief(
        {
            "scope": "project",
            "question": "summarize project",
            "user_id": "11111111-1111-1111-1111-111111111111",
            "max_articles": 1,
        },
        sink,
    )
    assert result["article_count"] == 1
    assert result["brief"]["citations"][0]["article_id"] == 9
    assert result["brief"]["citations"][0]["quote"] == "立项摘要"


def test_research_brief_topic_searches_titles():
    sink = FakeResearchSink()
    result = run_research_brief(
        {"scope": "topic", "topic": "LLM", "question": "tooling?", "max_articles": 10},
        sink,
    )
    assert result["brief"]["topic"] == "LLM"
    assert result["brief"]["citations"][0]["article_id"] == 3
    assert sink.calls == [("topic", {"topic": "LLM", "limit": 10})]


def test_research_brief_rejects_empty_question_and_bad_scope():
    sink = FakeResearchSink()
    with pytest.raises(ValueError, match="question"):
        run_research_brief({"scope": "topn", "question": "  "}, sink)
    with pytest.raises(ValueError, match="scope"):
        run_research_brief({"scope": "all", "question": "hi"}, sink)
    with pytest.raises(ValueError, match="topic"):
        run_research_brief({"scope": "topic", "question": "hi"}, sink)


def test_budgeted_research_skips_real_provider_when_agent_cap_is_exhausted():
    provider = RecordingResearchProvider()

    result = run_budgeted_research_brief(
        {"scope": "topn", "question": "What matters?"},
        FakeResearchSink(),
        provider=provider,
        ledger=RejectingAgentLedger(),
    )

    assert result == {
        "status": "skipped_cap",
        "account": "agent",
        "article_count": 0,
        "brief": None,
    }
    assert provider.calls == 0


def test_worker_registry_includes_research_brief_handler():
    from app.main import build_handler_registry

    registry = build_handler_registry()
    assert "research_brief" in registry
    assert callable(registry["research_brief"])
