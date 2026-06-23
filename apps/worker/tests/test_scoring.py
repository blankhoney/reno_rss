import json

from app.jobs.score_batch import score_batch
from app.providers.llm import DIMENSION_KEYS, MiniMaxProvider, MockProvider, tier_for_score


def test_mock_provider_returns_v04_dimensions_and_derived_tier():
    provider = MockProvider()
    article = {
        "id": 101,
        "title": "Practical RAG evaluation guide",
        "content_text": "A dense guide with code, benchmarks, and deployment checks.",
    }

    score = provider.score_article(article, {"version": "v0.4"})

    assert set(score["dimension_scores"]) == set(DIMENSION_KEYS)
    assert set(score["dimension_reasons"]) == set(DIMENSION_KEYS)
    assert score["scoring_status"] == "success"
    assert score["recommendation_tier"] == tier_for_score(score["base_score"])
    assert score == provider.score_article(article, {"version": "v0.4"})


def test_minimax_provider_strips_think_extracts_json_and_normalizes_values():
    raw_score = {
        "base_score": 150,
        "dimension_scores": {
            "topic_relevance": 120,
            "information_density": -5,
            "source_quality": 80,
            "novelty": 70,
            "timeliness": 65,
            "actionability": 110,
            "reading_cost_fit": 55,
            "risk_uncertainty": -20,
        },
        "dimension_reasons": {
            "topic_relevance": "Relevant",
            "information_density": "Sparse",
        },
        "summary_zh": "中" * 500,
        "summary_original": "A" * 500,
        "source_language": "English language label that is too long",
        "tags": [" AI ", "", "RAG", "ai", "AGENT"],
        "reason": "r" * 300,
        "risk_flags": ["reposted", "", "ClickBait", "custom", "reprint"],
        "confidence": 125,
        "scoring_status": "ignored",
    }

    class FakeClient:
        def __init__(self) -> None:
            self.messages = None

        def chat_completion(self, messages):
            self.messages = messages
            return (
                '<think>{"not": "the answer"}</think> prefixed text '
                f"{json.dumps(raw_score)} trailing text {{\"ignored\": true}}"
            )

    client = FakeClient()
    score = MiniMaxProvider(client).score_article({"title": "RAG"}, {"version": "v0.4"})

    assert client.messages
    assert score["base_score"] == 100
    assert score["dimension_scores"]["topic_relevance"] == 100
    assert score["dimension_scores"]["information_density"] == 0
    assert score["dimension_scores"]["actionability"] == 100
    assert score["dimension_scores"]["risk_uncertainty"] == 0
    assert score["tags"] == ["ai", "rag", "agent"]
    assert score["risk_flags"] == ["duplicate", "clickbait", "custom"]
    assert len(score["reason"]) == 240
    assert len(score["summary_zh"]) == 420
    assert len(score["summary_original"]) == 420
    assert len(score["source_language"]) == 24
    assert score["confidence"] == 1.0
    assert score["scoring_status"] == "success"


def test_score_batch_scores_all_articles_and_preserves_batch_id():
    class RecordingSink:
        def __init__(self) -> None:
            self.requested_batch_id = None
            self.saved: list[tuple[int, dict[str, object]]] = []

        def list_batch_articles(self, batch_id):
            self.requested_batch_id = batch_id
            return [
                {"id": 201, "title": "First article"},
                {"id": 202, "title": "Second article"},
            ]

        def save_score(self, article_id, score):
            self.saved.append((article_id, dict(score)))

    class RecordingProvider:
        def __init__(self) -> None:
            self.article_ids: list[int] = []
            self.rubrics: list[dict[str, object]] = []

        def score_article(self, article, rubric):
            self.article_ids.append(article["id"])
            self.rubrics.append(dict(rubric))
            return {
                "base_score": 73,
                "dimension_scores": {key: 73 for key in DIMENSION_KEYS},
                "dimension_reasons": {key: "ok" for key in DIMENSION_KEYS},
                "summary_zh": "摘要",
                "summary_original": "summary",
                "source_language": "en",
                "tags": ["ai"],
                "reason": "useful",
                "risk_flags": [],
                "confidence": 0.8,
                "scoring_status": "success",
                "recommendation_tier": "read",
            }

    sink = RecordingSink()
    provider = RecordingProvider()

    result = score_batch(
        {"batch_id": "batch-7", "rubric": {"version": "v0.4"}},
        sink,
        provider,
    )

    assert sink.requested_batch_id == "batch-7"
    assert provider.article_ids == [201, 202]
    assert provider.rubrics == [{"version": "v0.4"}, {"version": "v0.4"}]
    assert [article_id for article_id, _score in sink.saved] == [201, 202]
    assert [score["batch_id"] for _article_id, score in sink.saved] == ["batch-7", "batch-7"]
    assert result == {"batch_id": "batch-7", "articles_seen": 2, "scores_saved": 2}
