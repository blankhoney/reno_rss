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


class RecordingWebhook:
    def __init__(self) -> None:
        self.events: list[tuple[str, dict[str, object]]] = []

    def emit(self, event: str, payload: dict[str, object]):
        self.events.append((event, payload))
        return {"ok": True, "event": event, "status_code": 204, "error": None}


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
    assert len(sink.saved["worth_scan"]) == 1  # "read" only; disjoint from must_read
    assert len(sink.saved["can_skip"]) == 1
    assert result["brief"]["must_read"][0]["title"] == "A"
    assert result["brief"]["must_read"][0]["reason"] == "hot"
    assert result["brief"]["must_read"][0]["tier"] == "must_read"
    assert result["brief"]["worth_scan"][0]["article_id"] == 2


def test_generate_daily_brief_emits_auditable_webhook_summary():
    webhook = RecordingWebhook()

    result = generate_daily_brief(
        {"limit": 10},
        FakeBriefSink(),
        now=datetime(2026, 7, 18, 8, 0, tzinfo=UTC),
        webhook=webhook,
    )

    assert webhook.events == [
        (
            "daily_brief",
            {
                "title": "今日情报 2026-07-18",
                "generated_at": "2026-07-18T08:00:00+00:00",
                "item_count": 3,
                "must_read_count": 1,
            },
        )
    ]
    assert result["webhook"] == {
        "ok": True,
        "event": "daily_brief",
        "status_code": 204,
        "error": None,
    }
