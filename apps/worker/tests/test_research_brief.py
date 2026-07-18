from datetime import UTC, datetime

import pytest

from app.jobs.research_brief import run_budgeted_research_brief, run_research_brief
from app.runner import RetryableJobError


USER_ID = "11111111-1111-1111-1111-111111111111"


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

    def list_topn_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]:
        self.calls.append(("topn", {"user_id": user_id, "limit": limit}))
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
        return f"{scope}: {question} ({len(citations)}) [1]"


class RejectingAgentLedger:
    def charge(self, account: str, units: int = 1, *, limit: int = 0) -> int:
        assert account == "agent"
        assert units == 1
        assert limit == 0
        raise RuntimeError("daily budget exceeded for agent")


class RecordingAgentLedger:
    def __init__(self) -> None:
        self.calls = 0

    def charge(self, account: str, units: int = 1, *, limit: int = 0) -> int:
        self.calls += 1
        return self.calls


class FailingResearchProvider:
    model_provider = "minimax"

    def research_answer(self, *, question, citations, scope):
        raise RuntimeError("provider timeout")


class UncitedResearchProvider:
    model_provider = "minimax"

    def research_answer(self, *, question, citations, scope):
        return "This answer contains no evidence marker."


class OutOfRangeCitationProvider:
    model_provider = "minimax"

    def research_answer(self, *, question, citations, scope):
        return "This answer points at evidence that was never retrieved [99]."


def test_research_brief_topn_builds_mock_citations():
    sink = FakeResearchSink()
    result = run_research_brief(
        {
            "scope": "topn",
            "question": "What matters for agents?",
            "max_articles": 5,
            "user_id": USER_ID,
        },
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
        "start_hint": 0,
        "relevance_score": 1.0,
        "question_hint": "What matters for agents?",
    }
    assert "mock" in brief["answer"].lower() or "（mock）" in brief["answer"]
    assert sink.calls == [("topn", {"user_id": USER_ID, "limit": 5})]


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
            "user_id": USER_ID,
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


def test_research_citation_selects_the_question_relevant_source_window():
    sink = FakeResearchSink()
    sink.topic_hits = [
        {
            "article_id": 7,
            "title": "Retrieval systems",
            "content_text": (
                "This introduction is unrelated. "
                "Chunking strategy dominates retrieval quality for RAG systems. "
                "The closing sentence is also unrelated."
            ),
        }
    ]

    result = run_research_brief(
        {
            "scope": "topic",
            "topic": "RAG",
            "question": "How does chunking affect retrieval quality?",
        },
        sink,
    )

    citation = result["brief"]["citations"][0]
    assert citation["quote"] == (
        "Chunking strategy dominates retrieval quality for RAG systems."
    )
    assert citation["start_hint"] > 0
    assert citation["relevance_score"] > 0


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
        {"scope": "topn", "question": "What matters?", "user_id": USER_ID},
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


def test_real_provider_failure_is_retryable_not_mock_success():
    with pytest.raises(RetryableJobError, match="research provider failed"):
        run_budgeted_research_brief(
            {"scope": "topn", "question": "What matters?", "user_id": USER_ID},
            FakeResearchSink(),
            provider=FailingResearchProvider(),
            ledger=RecordingAgentLedger(),
        )


@pytest.mark.parametrize(
    "provider",
    [UncitedResearchProvider(), OutOfRangeCitationProvider()],
)
def test_real_provider_requires_valid_citation_markers(provider):
    with pytest.raises(RetryableJobError, match="citation markers"):
        run_budgeted_research_brief(
            {"scope": "topn", "question": "What matters?", "user_id": USER_ID},
            FakeResearchSink(),
            provider=provider,
            ledger=RecordingAgentLedger(),
        )


def test_empty_real_corpus_does_not_spend_agent_budget():
    sink = FakeResearchSink()
    sink.topn = []
    provider = RecordingResearchProvider()
    ledger = RecordingAgentLedger()

    result = run_budgeted_research_brief(
        {"scope": "topn", "question": "What matters?", "user_id": USER_ID},
        sink,
        provider=provider,
        ledger=ledger,
    )

    assert result["status"] == "empty"
    assert result["brief"]["provider"] == "none"
    assert provider.calls == 0
    assert ledger.calls == 0


def test_worker_registry_includes_research_brief_handler():
    from app.main import build_handler_registry

    registry = build_handler_registry()
    assert "research_brief" in registry
    assert callable(registry["research_brief"])
