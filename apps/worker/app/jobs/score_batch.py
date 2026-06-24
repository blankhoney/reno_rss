from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.providers.llm import DIMENSION_KEYS, LLMProvider, tier_for_score


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
    scores_failed = 0
    for article in articles:
        article_id = _article_id(article)
        try:
            score = dict(provider.score_article(article, rubric))
            score.setdefault("model_provider", getattr(provider, "model_provider", "mock"))
            score.setdefault("model_name", getattr(provider, "model_name", "mock"))
            score.setdefault("prompt_version", "rss-score-v04")
        except Exception as error:
            score = _baseline_error_score(article, str(error))
            scores_failed += 1
        score["batch_id"] = batch_id
        sink.save_score(article_id, score)
        scores_saved += 1

    _call_optional(sink, "finish_batch", batch_id)
    _call_optional(sink, "enqueue_recommendations", batch_id)
    return {
        "batch_id": batch_id,
        "articles_seen": len(articles),
        "scores_saved": scores_saved,
        "scores_failed": scores_failed,
    }


def _article_id(article: Mapping[str, object]) -> object:
    if "id" in article:
        return article["id"]
    if "article_id" in article:
        return article["article_id"]
    raise KeyError("article must include 'id' or 'article_id'")


def _baseline_error_score(article: Mapping[str, object], error: str) -> dict[str, object]:
    combined = " ".join(
        str(article.get(key) or "")
        for key in ("title", "content_text", "content_html", "url")
        if article.get(key)
    )
    base_score = min(100, len(combined) // 50)
    return {
        "base_score": base_score,
        "dimension_scores": {key: base_score for key in DIMENSION_KEYS},
        "dimension_reasons": {key: "评分失败，需重新评分。" for key in DIMENSION_KEYS},
        "summary_zh": "",
        "summary_original": "",
        "source_language": "unknown",
        "tags": [],
        "reason": "评分失败，需重新评分。",
        "risk_flags": [],
        "confidence": 0.0,
        "scoring_status": "error",
        "error": error,
        "recommendation_tier": tier_for_score(base_score),
        "model_provider": "baseline",
        "model_name": "length-baseline",
        "prompt_version": "rss-score-v04",
    }


def _call_optional(sink: object, method_name: str, batch_id: object) -> None:
    method = getattr(sink, method_name, None)
    if method is not None:
        method(batch_id)
