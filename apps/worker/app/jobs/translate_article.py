from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol

import httpx

from app.providers.llm import LLMProvider
from app.runner import RetryableJobError


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


class TranslationBudget(Protocol):
    def charge(self, account: str, units: int = 1, *, limit: int = 0) -> int: ...


def translate_article(
    payload: dict[str, object],
    *,
    sink: TranslationSink,
    provider: LLMProvider,
    now: datetime | None = None,
    budget: TranslationBudget | None = None,
    daily_limit: int = 0,
) -> dict[str, object]:
    article_id = _required_int(payload, "article_id")
    article = sink.get_article_for_translation(article_id)
    if article is None:
        raise KeyError(f"article not found: {article_id}")

    existing_translation = str(article.get("content_zh") or "").strip()
    if existing_translation and article.get("content_zh_status") == "succeeded":
        return {"outcome": "cached", "content_zh_status": "succeeded"}

    if budget is not None:
        # Reserve immediately before the provider attempt; cached translations
        # are free and exhausted budgets must not start a provider call.
        try:
            budget.charge("translate", 1, limit=max(0, int(daily_limit)))
        except Exception:
            sink.save_translation(
                article_id,
                content_zh=None,
                status="failed",
                translated_at=None,
            )
            raise

    sink.save_translation(article_id, content_zh=None, status="running", translated_at=None)
    try:
        translated_html = provider.translate_article(article).strip()
    except (httpx.TimeoutException, httpx.TransportError) as error:
        sink.save_translation(article_id, content_zh=None, status="failed", translated_at=None)
        detail = str(error) or error.__class__.__name__
        raise RetryableJobError(f"translation transient network failure: {detail}") from error
    except Exception:
        sink.save_translation(article_id, content_zh=None, status="failed", translated_at=None)
        raise
    if not translated_html:
        sink.save_translation(article_id, content_zh=None, status="failed", translated_at=None)
        raise ValueError("translation produced empty output")

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
