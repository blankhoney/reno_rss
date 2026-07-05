from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.providers.llm import LLMProvider


ERROR_MESSAGE_LIMIT = 240
PROMPT_VERSION = "rss-score-v05"


class ScoreSink(Protocol):
    def list_batch_articles(self, batch_id: object) -> list[dict[str, object]]: ...

    def save_score(self, article_id: object, score: dict[str, object]) -> object: ...


def score_batch(
    payload: Mapping[str, object],
    sink: ScoreSink,
    provider: LLMProvider,
) -> dict[str, object]:
    batch_id = payload.get("batch_id")
    if batch_id is None:
        raise KeyError("payload['batch_id'] is required")

    rubric = payload.get("rubric", {})
    if not isinstance(rubric, Mapping):
        raise TypeError("payload['rubric'] must be a mapping")

    articles = sink.list_batch_articles(batch_id)
    scores_saved = 0
    scores_succeeded = 0
    scores_failed = 0
    for article in articles:
        article_id = _article_id(article)
        try:
            score = dict(provider.score_article(article, rubric))
            score.setdefault("model_provider", getattr(provider, "model_provider", "mock"))
            score.setdefault("model_name", getattr(provider, "model_name", "mock"))
            score.setdefault("prompt_version", PROMPT_VERSION)
            score.setdefault("scoring_status", "success")
        except Exception as error:
            score = _provider_error_score(provider, error)
        score["batch_id"] = batch_id
        sink.save_score(article_id, score)
        scores_saved += 1
        if score.get("scoring_status") == "success":
            scores_succeeded += 1
        else:
            scores_failed += 1

    _call_optional(sink, "finish_batch", batch_id)
    _call_optional(sink, "enqueue_recommendations", batch_id)
    return {
        "batch_id": batch_id,
        "articles_seen": len(articles),
        "scores_saved": scores_saved,
        "scores_succeeded": scores_succeeded,
        "scores_failed": scores_failed,
    }


def _article_id(article: Mapping[str, object]) -> object:
    if "id" in article:
        return article["id"]
    if "article_id" in article:
        return article["article_id"]
    raise KeyError("article must include 'id' or 'article_id'")


def _provider_error_score(provider: LLMProvider, error: Exception) -> dict[str, object]:
    return {
        "base_score": 0,
        "dimension_scores": {},
        "dimension_reasons": {},
        "summary_zh": "",
        "summary_original": "",
        "source_language": "unknown",
        "tags": [],
        "reason": "Scoring failed before a valid provider score was produced.",
        "risk_flags": [],
        "confidence": 0.0,
        "scoring_status": "error",
        "error": _bounded_error_message(error),
        "recommendation_tier": "skip",
        "model_provider": _provider_metadata(provider, "model_provider"),
        "model_name": _provider_metadata(provider, "model_name"),
        "prompt_version": PROMPT_VERSION,
    }


def _bounded_error_message(error: Exception) -> str:
    message = str(error) or error.__class__.__name__
    return message[:ERROR_MESSAGE_LIMIT]


def _provider_metadata(provider: LLMProvider, name: str) -> str:
    value = getattr(provider, name, None)
    if value is None or value == "":
        return "unknown"
    return str(value)


def _call_optional(sink: object, method_name: str, batch_id: object) -> None:
    method = getattr(sink, method_name, None)
    if method is not None:
        method(batch_id)
