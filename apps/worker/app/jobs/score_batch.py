from __future__ import annotations

from collections.abc import Mapping
from typing import Protocol

from app.providers.llm import LLMProvider


class ScoreSink(Protocol):
    def list_batch_articles(self, batch_id: object) -> list[dict[str, object]]: ...

    def save_score(self, article_id: object, score: dict[str, object]) -> None: ...


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
    for article in articles:
        article_id = _article_id(article)
        score = dict(provider.score_article(article, rubric))
        score["batch_id"] = batch_id
        sink.save_score(article_id, score)
        scores_saved += 1

    return {
        "batch_id": batch_id,
        "articles_seen": len(articles),
        "scores_saved": scores_saved,
    }


def _article_id(article: Mapping[str, object]) -> object:
    if "id" in article:
        return article["id"]
    if "article_id" in article:
        return article["article_id"]
    raise KeyError("article must include 'id' or 'article_id'")
