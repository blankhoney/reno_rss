"""Select unscored articles and enqueue a scheduled score_batch (GOAL intelligence OS)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime, timedelta
import logging
from typing import Protocol


LOGGER = logging.getLogger(__name__)
DEFAULT_LOOKBACK_HOURS = 72
DEFAULT_MAX_ARTICLES = 30


class AutoScoreSink(Protocol):
    def count_scores_today(self, day_start: str) -> int: ...

    def list_unscored_article_ids(
        self,
        *,
        published_after: str,
        limit: int,
    ) -> list[int]: ...

    def create_scheduled_batch(
        self,
        article_ids: Sequence[int],
        *,
        name: str,
        candidate_window: str,
    ) -> int: ...

    def enqueue_score_batch(self, batch_id: int) -> None: ...

    def enqueue_recommendations(self, batch_id: object) -> None: ...


def run_auto_score_candidates(
    payload: Mapping[str, object],
    sink: AutoScoreSink,
    *,
    daily_article_cap: int = 60,
    now: datetime | None = None,
) -> dict[str, object]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    lookback_hours = _positive_int(payload.get("lookback_hours"), DEFAULT_LOOKBACK_HOURS)
    max_articles = _positive_int(payload.get("max_articles"), DEFAULT_MAX_ARTICLES)
    if daily_article_cap < 0:
        raise ValueError("daily_article_cap must be greater than or equal to 0")

    remaining = max_articles
    scored_today_before = 0
    if daily_article_cap > 0:
        day_start = current.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
        scored_today_before = sink.count_scores_today(day_start)
        remaining = min(max_articles, max(daily_article_cap - scored_today_before, 0))

    if remaining <= 0:
        LOGGER.warning(
            "auto_score skipped: daily cap exhausted scored_today_before=%s daily_cap=%s",
            scored_today_before,
            daily_article_cap,
        )
        sink.enqueue_recommendations(None)
        return {
            "status": "skipped_cap",
            "article_ids": [],
            "batch_id": None,
            "scored_today_before": scored_today_before,
            "daily_cap": daily_article_cap,
            "remaining": 0,
        }

    published_after = (current - timedelta(hours=lookback_hours)).isoformat()
    article_ids = sink.list_unscored_article_ids(
        published_after=published_after,
        limit=remaining,
    )
    if not article_ids:
        # Keep personalization and the daily brief fresh even when the current
        # cycle has no new articles to score.
        sink.enqueue_recommendations(None)
        return {
            "status": "empty",
            "article_ids": [],
            "batch_id": None,
            "scored_today_before": scored_today_before,
            "daily_cap": daily_article_cap,
            "remaining": remaining,
        }

    batch_id = sink.create_scheduled_batch(
        article_ids,
        name=f"scheduled-{current.strftime('%Y%m%dT%H%M')}",
        candidate_window="last_3_days" if lookback_hours <= 72 else "custom",
    )
    sink.enqueue_score_batch(batch_id)
    LOGGER.info(
        "auto_score enqueued batch_id=%s articles=%s remaining=%s",
        batch_id,
        len(article_ids),
        remaining,
    )
    return {
        "status": "enqueued",
        "article_ids": article_ids,
        "batch_id": batch_id,
        "scored_today_before": scored_today_before,
        "daily_cap": daily_article_cap,
        "remaining": remaining,
    }


def _positive_int(value: object, default: int) -> int:
    if value is None:
        return default
    parsed = int(value)
    if parsed <= 0:
        raise ValueError("lookback_hours/max_articles must be positive")
    return parsed
