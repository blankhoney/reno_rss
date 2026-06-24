from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit


TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


class ArticleSink(Protocol):
    def upsert_article(self, article: dict[str, object]) -> int: ...

    def upsert_article_source(self, source: dict[str, object]) -> None: ...


class MinifluxEntryClient(Protocol):
    def list_entries(
        self,
        *,
        limit: int,
        after_entry_id: int | None = None,
    ) -> list[dict[str, object]]: ...


def run_sync_miniflux_entries(
    payload: dict[str, object],
    *,
    sink: ArticleSink,
    client: MinifluxEntryClient | None = None,
) -> dict[str, int]:
    if "entries" in payload:
        return sync_miniflux_entries(payload, sink)
    if client is None:
        raise ValueError("client is required when payload does not include entries")

    limit = _optional_int(payload, "limit", default=100)
    after_entry_id = _optional_int(payload, "after_entry_id", default=None)
    entries = client.list_entries(limit=limit, after_entry_id=after_entry_id)
    return sync_miniflux_entries({**payload, "entries": entries}, sink)


def sync_miniflux_entries(payload: dict[str, object], sink: ArticleSink) -> dict[str, int]:
    entries = _entries_from_payload(payload)
    article_ids_by_canonical_url: dict[str, int] = {}
    seen_source_keys: set[tuple[int, int]] = set()
    counts = {
        "entries_seen": len(entries),
        "articles_upserted": 0,
        "sources_upserted": 0,
        "source_duplicates_skipped": 0,
    }

    for entry in entries:
        feed_id = _required_int(entry, "feed_id")
        miniflux_entry_id = _required_int(entry, "miniflux_entry_id")
        source_key = (feed_id, miniflux_entry_id)
        if source_key in seen_source_keys:
            counts["source_duplicates_skipped"] += 1
            continue

        url = _required_str(entry, "url")
        title = _required_str(entry, "title")
        canonical_url = canonicalize_url(url)
        article_id = article_ids_by_canonical_url.get(canonical_url)
        if article_id is None:
            article_id = sink.upsert_article(
                _article_from_entry(
                    entry,
                    feed_id=feed_id,
                    title=title,
                    url=url,
                    canonical_url=canonical_url,
                )
            )
            article_ids_by_canonical_url[canonical_url] = article_id
            counts["articles_upserted"] += 1

        sink.upsert_article_source(
            {
                "article_id": article_id,
                "feed_id": feed_id,
                "miniflux_entry_id": miniflux_entry_id,
                "source_url": url,
                "source_title": title,
                "published_at": entry.get("published_at"),
            }
        )
        seen_source_keys.add(source_key)
        counts["sources_upserted"] += 1

    return counts


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            urlencode(sorted(query_items), doseq=True),
            "",
        )
    )


def _entries_from_payload(payload: dict[str, object]) -> list[dict[str, object]]:
    entries = payload.get("entries", [])
    if not isinstance(entries, list):
        raise TypeError("payload['entries'] must be a list")
    for entry in entries:
        if not isinstance(entry, dict):
            raise TypeError("payload['entries'] must contain dictionaries")
    return entries


def _article_from_entry(
    entry: dict[str, object],
    *,
    feed_id: int,
    title: str,
    url: str,
    canonical_url: str,
) -> dict[str, object]:
    article: dict[str, object] = {
        "primary_feed_id": feed_id,
        "title": title,
        "url": url,
        "canonical_url": canonical_url,
    }
    _copy_optional(entry, article, "published_at")
    _copy_optional(entry, article, "content_text")
    _copy_optional(entry, article, "content_html")
    if "content_text" in article or "content_html" in article:
        article["content_source"] = "miniflux_feed"
        article["content_quality"] = "full"
    return article


def _copy_optional(
    source: dict[str, object],
    destination: dict[str, object],
    key: str,
) -> None:
    value = source.get(key)
    if value is not None:
        destination[key] = value


def _required_int(entry: dict[str, object], key: str) -> int:
    value = entry.get(key)
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"entry['{key}'] must be an int")
    return value


def _optional_int(
    payload: dict[str, object],
    key: str,
    *,
    default: int | None,
) -> int | None:
    value = payload.get(key, default)
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, int):
        raise TypeError(f"payload['{key}'] must be an int")
    return value


def _required_str(entry: dict[str, object], key: str) -> str:
    value = entry.get(key)
    if not isinstance(value, str):
        raise TypeError(f"entry['{key}'] must be a string")
    return value
