from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

from app.providers.llm import LLMProvider


class TranslationSink(Protocol):
    def get_article_for_translation(self, article_id: int) -> dict[str, object] | None: ...

    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str,
        translated_at: datetime | None,
    ) -> None: ...


def translate_article(
    payload: dict[str, object],
    *,
    sink: TranslationSink,
    provider: LLMProvider,
    now: datetime | None = None,
) -> dict[str, object]:
    article_id = _required_int(payload, "article_id")
    article = sink.get_article_for_translation(article_id)
    if article is None:
        raise KeyError(f"article not found: {article_id}")

    existing_translation = str(article.get("content_zh") or "").strip()
    if existing_translation and article.get("content_zh_status") == "succeeded":
        return {"outcome": "cached", "content_zh_status": "succeeded"}

    sink.save_translation(article_id, content_zh=None, status="running", translated_at=None)
    try:
        translated_html = provider.translate_article(article).strip()
    except Exception:
        sink.save_translation(article_id, content_zh=None, status="failed", translated_at=None)
        raise

    translated_at = now or datetime.now(UTC)
    sink.save_translation(
        article_id,
        content_zh=translated_html,
        status="succeeded",
        translated_at=translated_at,
    )
    return {
        "outcome": "translated",
        "content_zh_status": "succeeded",
        "translated_at": translated_at.isoformat(),
        "html_length": len(translated_html),
    }


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"payload['{key}'] must be an int")
    return value
