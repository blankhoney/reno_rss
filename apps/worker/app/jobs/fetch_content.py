from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Protocol

from app.content_quality import article_text_from_html, assess_article_content, decide_fetched_article_content
from app.providers.external_content import ExternalContentProvider, NoExternalContentProvider


class ContentSink(Protocol):
    def get_article_for_fetch(self, article_id: int) -> dict[str, object] | None: ...

    def save_content(self, article_id: int, content: dict[str, object]) -> None: ...


class ReadabilityProvider(Protocol):
    def fetch_content(self, entry_id: int) -> str: ...


def fetch_article_content(
    payload: dict[str, object],
    *,
    sink: ContentSink,
    miniflux_client: ReadabilityProvider,
    external_provider: ExternalContentProvider | None = None,
    now: datetime | None = None,
) -> dict[str, object]:
    article_id = _required_int(payload, "article_id")
    article = sink.get_article_for_fetch(article_id)
    if article is None:
        raise KeyError(f"article not found: {article_id}")

    now = now or datetime.now(UTC)
    external_provider = external_provider or NoExternalContentProvider()
    current_html = str(article.get("content_html") or article.get("content_text") or "")

    miniflux_entry_id = article.get("miniflux_entry_id")
    if miniflux_entry_id is not None:
        try:
            fetched_html = miniflux_client.fetch_content(int(miniflux_entry_id))
        except Exception:
            fetched_html = ""
        if fetched_html:
            decision = decide_fetched_article_content(current_html, fetched_html)
            if decision.fetch_result["outcome"] == "applied":
                return _save(
                    sink,
                    article_id,
                    html=decision.html,
                    content_source="readability",
                    content_quality=str(decision.fetch_result["quality"]),
                    now=now,
                    outcome="applied",
                )

    external_html = external_provider.fetch(str(article["url"]))
    if external_html:
        decision = decide_fetched_article_content(current_html, external_html)
        if decision.fetch_result["outcome"] == "applied":
            return _save(
                sink,
                article_id,
                html=decision.html,
                content_source="external",
                content_quality=str(decision.fetch_result["quality"]),
                now=now,
                outcome="applied",
            )

    snippet_html = current_html or f"<p>{article['title']}</p>"
    return _save(
        sink,
        article_id,
        html=snippet_html,
        content_source="snippet_only",
        content_quality="snippet",
        now=now,
        outcome="fallback",
    )


def _save(
    sink: ContentSink,
    article_id: int,
    *,
    html: str,
    content_source: str,
    content_quality: str,
    now: datetime,
    outcome: str,
) -> dict[str, object]:
    text = article_text_from_html(html)
    assessment = assess_article_content(html)
    sink.save_content(
        article_id,
        {
            "content_html": html,
            "content_text": text,
            "content_source": content_source,
            "content_quality": content_quality,
            "fetched_at": now,
            "content_expires_at": now + timedelta(days=7),
        },
    )
    return {
        "outcome": outcome,
        "content_source": content_source,
        "content_quality": content_quality,
        "text_length": assessment.text_length,
    }


def _required_int(payload: dict[str, object], key: str) -> int:
    value = payload.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"payload['{key}'] must be an int")
    return value
