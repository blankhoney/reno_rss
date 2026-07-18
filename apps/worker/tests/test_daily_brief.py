from datetime import UTC, datetime

from app.jobs.daily_brief import generate_daily_brief


class FakeBriefSink:
    def __init__(self) -> None:
        self.saved: dict[str, object] | None = None

    def list_latest_recommendation_items(self, *, limit: int = 10) -> list[dict[str, object]]:
        return [
            {
                "article_id": 1,
                "rank": 1,
                "rank_score": 90,
                "tier": "must_read",
                "reason": "hot",
                "title": "A",
            },
            {
                "article_id": 2,
                "rank": 2,
                "rank_score": 70,
                "tier": "read",
                "reason": "ok",
                "title": "B",
            },
            {
                "article_id": 3,
                "rank": 3,
                "rank_score": 55,
                "tier": "skim",
                "reason": "later",
                "title": "C",
            },
        ][:limit]

    def save_daily_brief(self, brief: dict[str, object]) -> int:
        self.saved = brief
        return 99


def test_generate_daily_brief_layers_items_by_tier():
    sink = FakeBriefSink()
    result = generate_daily_brief(
        {"limit": 10},
        sink,
        now=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
    )
    assert result["status"] == "ok"
    assert result["brief_id"] == 99
    assert result["item_count"] == 3
    assert sink.saved is not None
    assert sink.saved["title"] == "今日情报 2026-07-18"
    assert len(sink.saved["must_read"]) == 1
    assert len(sink.saved["worth_scan"]) == 2
    assert len(sink.saved["can_skip"]) == 1
