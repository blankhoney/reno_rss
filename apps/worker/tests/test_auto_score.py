from datetime import UTC, datetime

from app.jobs.auto_score import run_auto_score_candidates


class FakeAutoScoreSink:
    def __init__(
        self,
        *,
        scored_today: int = 0,
        article_ids: list[int] | None = None,
    ) -> None:
        self.scored_today = scored_today
        self.article_ids = list(article_ids or [])
        self.created: dict[str, object] | None = None
        self.enqueued_batch_id: int | None = None
        self.recommendation_batch_ids: list[object] = []

    def count_scores_today(self, day_start: str) -> int:
        assert day_start.endswith("00:00:00+00:00") or "T00:00:00" in day_start
        return self.scored_today

    def list_unscored_article_ids(self, *, published_after: str, limit: int) -> list[int]:
        return self.article_ids[:limit]

    def create_scheduled_batch(
        self,
        article_ids,
        *,
        name: str,
        candidate_window: str,
    ) -> int:
        self.created = {
            "article_ids": list(article_ids),
            "name": name,
            "candidate_window": candidate_window,
        }
        return 42

    def enqueue_score_batch(self, batch_id: int) -> None:
        self.enqueued_batch_id = batch_id

    def enqueue_recommendations(self, batch_id: object) -> None:
        self.recommendation_batch_ids.append(batch_id)


def test_auto_score_enqueues_batch_under_cap():
    sink = FakeAutoScoreSink(scored_today=10, article_ids=[7, 8, 9, 10])
    now = datetime(2026, 7, 18, 15, 0, tzinfo=UTC)
    result = run_auto_score_candidates(
        {"lookback_hours": 72, "max_articles": 3},
        sink,
        daily_article_cap=60,
        now=now,
    )
    assert result["status"] == "enqueued"
    assert result["article_ids"] == [7, 8, 9]
    assert result["batch_id"] == 42
    assert sink.enqueued_batch_id == 42
    assert sink.recommendation_batch_ids == []
    assert sink.created is not None
    assert sink.created["candidate_window"] == "last_3_days"


def test_auto_score_skips_when_daily_cap_exhausted():
    sink = FakeAutoScoreSink(scored_today=60, article_ids=[1, 2])
    result = run_auto_score_candidates(
        {"max_articles": 30},
        sink,
        daily_article_cap=60,
        now=datetime(2026, 7, 18, 15, 0, tzinfo=UTC),
    )
    assert result["status"] == "skipped_cap"
    assert result["batch_id"] is None
    assert sink.enqueued_batch_id is None
    assert sink.recommendation_batch_ids == [None]


def test_auto_score_empty_when_no_candidates():
    sink = FakeAutoScoreSink(scored_today=0, article_ids=[])
    result = run_auto_score_candidates(
        {},
        sink,
        daily_article_cap=60,
        now=datetime(2026, 7, 18, 15, 0, tzinfo=UTC),
    )
    assert result["status"] == "empty"
    assert result["batch_id"] is None
    assert sink.recommendation_batch_ids == [None]
