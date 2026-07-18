"""Build an in-app daily intelligence brief from ranked candidates (mock-safe)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol


class BriefSink(Protocol):
    def list_latest_recommendation_items(self, *, limit: int = 10) -> list[dict[str, object]]: ...

    def save_daily_brief(self, brief: dict[str, object]) -> int: ...


def generate_daily_brief(
    payload: Mapping[str, object],
    sink: BriefSink,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    limit = int(payload.get("limit", 10) or 10)
    limit = max(1, min(limit, 20))
    items = sink.list_latest_recommendation_items(limit=limit)
    must_read = [item for item in items if str(item.get("tier", "")) == "must_read"]
    worth = [item for item in items if str(item.get("tier", "")) in {"read", "must_read"}]
    skim = [item for item in items if str(item.get("tier", "")) == "skim"]

    brief = {
        "generated_at": current.isoformat(),
        "title": f"今日情报 {current.date().isoformat()}",
        "must_read": _brief_rows(must_read),
        "worth_scan": _brief_rows(worth),
        "can_skip": _brief_rows(skim),
        "item_count": len(items),
        "source": "recommendations_latest",
    }
    brief_id = sink.save_daily_brief(brief)
    return {"status": "ok", "brief_id": brief_id, "item_count": len(items)}


def _brief_rows(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in items:
        rows.append(
            {
                "article_id": item.get("article_id"),
                "rank": item.get("rank"),
                "tier": item.get("tier"),
                "rank_score": item.get("rank_score"),
                "reason": item.get("reason") or "",
                "title": item.get("title") or "",
            }
        )
    return rows
