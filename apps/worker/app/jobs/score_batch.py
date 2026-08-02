from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime
import logging
from typing import Protocol

from app.providers.llm import LLMProvider


ERROR_MESSAGE_LIMIT = 240
PROMPT_VERSION = "rss-score-v05"
LOGGER = logging.getLogger(__name__)


class ScoreSink(Protocol):
    def list_batch_articles(self, batch_id: object) -> list[dict[str, object]]: ...

    def count_scores_today(self, day_start: str) -> int: ...

    def save_score(self, article_id: object, score: dict[str, object]) -> object: ...


class ScoreBudget(Protocol):
    def reserve_score_attempt(self, *, day_start: str, daily_cap: int) -> int | None: ...


class WebhookEmitter(Protocol):
    def emit(self, event: str, payload: Mapping[str, object]) -> dict[str, object]: ...


def score_batch(
    payload: Mapping[str, object],
    sink: ScoreSink,
    provider: LLMProvider,
    *,
    daily_article_cap: int = 0,
    now: datetime | None = None,
    score_budget: ScoreBudget | None = None,
    webhook: WebhookEmitter | None = None,
    high_score_threshold: int = 85,
) -> dict[str, object]:
    batch_id = payload.get("batch_id")
    if batch_id is None:
        raise KeyError("payload['batch_id'] is required")
    if daily_article_cap < 0:
        raise ValueError("daily_article_cap must be greater than or equal to 0")

    rubric = payload.get("rubric", {})
    if not isinstance(rubric, Mapping):
        raise TypeError("payload['rubric'] must be a mapping")

    articles = sink.list_batch_articles(batch_id)
    articles_to_score = articles
    scored_today_before = 0
    articles_skipped_cap = 0
    day_start: str | None = None
    if daily_article_cap > 0:
        day_start = _utc_day_start(now).isoformat()
        scored_today_before = sink.count_scores_today(day_start)
        if score_budget is None:
            # Compatibility path for in-memory callers; production injects the
            # database-backed reservation so this slice is not the hard limit.
            remaining = max(daily_article_cap - scored_today_before, 0)
            articles_to_score = articles[:remaining]
            articles_skipped_cap = len(articles) - len(articles_to_score)
        if articles_skipped_cap > 0:
            LOGGER.warning(
                "score_batch daily cap reached: batch_id=%s daily_cap=%s "
                "scored_today_before=%s articles_skipped_cap=%s",
                batch_id,
                daily_article_cap,
                scored_today_before,
                articles_skipped_cap,
            )

    scores_saved = 0
    scores_succeeded = 0
    scores_failed = 0
    webhook_attempted = 0
    webhook_delivered = 0
    threshold = max(0, min(100, int(high_score_threshold)))
    for index, article in enumerate(articles_to_score):
        if score_budget is not None:
            if day_start is None:
                raise RuntimeError("score budget requires a positive daily cap")
            # Reserve immediately before the provider call; the reservation is
            # the hard boundary that concurrent workers must share.
            reserved = score_budget.reserve_score_attempt(
                day_start=day_start,
                daily_cap=daily_article_cap,
            )
            if reserved is None:
                articles_skipped_cap += len(articles_to_score) - index
                LOGGER.warning(
                    "score_batch daily cap reached during reservation: "
                    "batch_id=%s daily_cap=%s scored_today_before=%s "
                    "articles_skipped_cap=%s",
                    batch_id,
                    daily_article_cap,
                    scored_today_before,
                    articles_skipped_cap,
                )
                break
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
            base_score = int(score.get("base_score") or 0)
            if webhook is not None and base_score >= threshold:
                webhook_attempted += 1
                delivery = webhook.emit(
                    "high_score",
                    {
                        "article_id": article_id,
                        "title": str(article.get("title") or ""),
                        "url": str(article.get("url") or ""),
                        "base_score": base_score,
                        "tier": str(score.get("recommendation_tier") or ""),
                        "tags": list(score.get("tags") or []),
                        "risk_flags": list(score.get("risk_flags") or []),
                    },
                )
                if delivery.get("ok") is True:
                    webhook_delivered += 1
        else:
            scores_failed += 1

    _call_optional(sink, "finish_batch", batch_id)
    _call_optional(sink, "enqueue_recommendations", batch_id)
    result: dict[str, object] = {
        "batch_id": batch_id,
        "articles_seen": len(articles),
        "scores_saved": scores_saved,
        "scores_succeeded": scores_succeeded,
        "scores_failed": scores_failed,
        "articles_skipped_cap": articles_skipped_cap,
        "daily_cap": daily_article_cap,
        "scored_today_before": scored_today_before,
    }
    if webhook is not None:
        result["webhooks"] = {
            "attempted": webhook_attempted,
            "delivered": webhook_delivered,
            "failed": webhook_attempted - webhook_delivered,
        }
    return result


def _utc_day_start(now: datetime | None = None) -> datetime:
    current = now or datetime.now(UTC)
    current = current.astimezone(UTC) if current.tzinfo else current.replace(tzinfo=UTC)
    return current.replace(hour=0, minute=0, second=0, microsecond=0)


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
