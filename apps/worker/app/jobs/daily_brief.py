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
    # Disjoint tiers for the intelligence dashboard (must_read / read / skim|skip).
    must_read = [item for item in items if str(item.get("tier", "")) == "must_read"]
    worth = [item for item in items if str(item.get("tier", "")) == "read"]
    skip = [
        item
        for item in items
        if str(item.get("tier", "")) in {"skim", "skip"}
    ]

    brief = {
        "generated_at": current.isoformat(),
        "title": f"今日情报 {current.date().isoformat()}",
        "must_read": _brief_rows(must_read),
        "worth_scan": _brief_rows(worth),
        "can_skip": _brief_rows(skip),
        "item_count": len(items),
        "source": "recommendations_latest",
    }
    brief_id = sink.save_daily_brief(brief)
    webhook = _maybe_emit_brief_webhook(brief)
    # Include full `brief` so the worker job.result is readable by GET /api/briefs/latest
    # (in addition to the sink's synthetic jobs row).
    result: dict[str, object] = {
        "status": "ok",
        "brief_id": brief_id,
        "item_count": len(items),
        "brief": brief,
    }
    if webhook is not None:
        result["webhook"] = webhook
    return result


def _maybe_emit_brief_webhook(brief: Mapping[str, object]) -> dict[str, object] | None:
    """Optional outbound webhook when AI_READER_WEBHOOK_URL is set."""
    import os

    url = (os.environ.get("AI_READER_WEBHOOK_URL") or "").strip()
    if not url:
        return None
    secret = (os.environ.get("AI_READER_WEBHOOK_SECRET") or "").strip() or None
    try:
        import importlib.util
        import sys
        from pathlib import Path

        domain_path = None
        for parent in Path(__file__).resolve().parents:
            candidate = parent / "apps/api/app/domain/webhooks.py"
            if candidate.exists():
                domain_path = candidate
                break
        if domain_path is None:
            return {"ok": False, "error": "webhooks_module_missing"}
        module_name = "ai_reader_webhooks"
        spec = importlib.util.spec_from_file_location(module_name, domain_path)
        if spec is None or spec.loader is None:
            return {"ok": False, "error": "webhooks_load_failed"}
        module = importlib.util.module_from_spec(spec)
        sys.modules[module_name] = module
        spec.loader.exec_module(module)
        delivery = module.deliver_webhook(
            url,
            "daily_brief",
            {
                "title": brief.get("title"),
                "generated_at": brief.get("generated_at"),
                "item_count": brief.get("item_count"),
                "must_read_count": len(brief.get("must_read") or [])
                if isinstance(brief.get("must_read"), list)
                else 0,
            },
            secret=secret,
        )
        return {
            "ok": delivery.ok,
            "status_code": delivery.status_code,
            "error": delivery.error,
            "event": delivery.event,
        }
    except Exception as exc:
        return {"ok": False, "error": str(exc)}


def _brief_rows(items: Sequence[Mapping[str, object]]) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for item in items:
        risk_flags = item.get("risk_flags")
        if not isinstance(risk_flags, list):
            risk_flags = []
        source_quality = item.get("source_quality")
        if source_quality is None:
            source_quality = item.get("source_quality_score")
        rows.append(
            {
                "article_id": item.get("article_id"),
                "rank": item.get("rank"),
                "tier": item.get("tier"),
                "rank_score": item.get("rank_score"),
                "reason": item.get("reason") or "",
                "title": item.get("title") or "",
                "summary_zh": item.get("summary_zh") or None,
                "overall_score": item.get("overall_score")
                if item.get("overall_score") is not None
                else item.get("base_score"),
                "risk_flags": list(risk_flags),
                "source_quality": source_quality,
            }
        )
    return rows
