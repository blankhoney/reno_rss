from app.jobs.sync_miniflux import sync_miniflux_entries


class RecordingSink:
    def __init__(self) -> None:
        self.articles: list[dict[str, object]] = []
        self.sources: list[dict[str, object]] = []
        self._article_ids: dict[object, int] = {}

    def upsert_article(self, article: dict[str, object]) -> int:
        self.articles.append(dict(article))
        canonical_url = article["canonical_url"]
        if canonical_url not in self._article_ids:
            self._article_ids[canonical_url] = len(self._article_ids) + 100
        return self._article_ids[canonical_url]

    def upsert_article_source(self, source: dict[str, object]) -> None:
        self.sources.append(dict(source))


def test_sync_normalizes_canonical_url_without_tracking_params():
    sink = RecordingSink()

    result = sync_miniflux_entries(
        {
            "entries": [
                {
                    "feed_id": 1,
                    "miniflux_entry_id": 101,
                    "url": "https://example.com/read?b=2&utm_source=newsletter&fbclid=x&a=1&gclid=y",
                    "title": "Tracked link",
                    "published_at": "2026-06-24T09:00:00+08:00",
                }
            ]
        },
        sink,
    )

    assert result["articles_upserted"] == 1
    assert sink.articles[0]["canonical_url"] == "https://example.com/read?a=1&b=2"
    assert sink.sources[0]["source_url"] == (
        "https://example.com/read?b=2&utm_source=newsletter&fbclid=x&a=1&gclid=y"
    )


def test_sync_reuses_one_article_for_entries_with_same_canonical_url():
    sink = RecordingSink()

    result = sync_miniflux_entries(
        {
            "entries": [
                {
                    "feed_id": 1,
                    "miniflux_entry_id": 101,
                    "url": "https://example.com/post?id=1&utm_campaign=launch",
                    "title": "Original feed title",
                    "published_at": "2026-06-24T08:00:00+08:00",
                },
                {
                    "feed_id": 2,
                    "miniflux_entry_id": 202,
                    "url": "https://example.com/post?gclid=abc&id=1",
                    "title": "Second feed title",
                    "published_at": "2026-06-24T09:00:00+08:00",
                },
            ]
        },
        sink,
    )

    assert result["articles_upserted"] == 1
    assert result["sources_upserted"] == 2
    assert [article["canonical_url"] for article in sink.articles] == [
        "https://example.com/post?id=1"
    ]
    assert [source["article_id"] for source in sink.sources] == [100, 100]
    assert [
        (source["feed_id"], source["miniflux_entry_id"], source["source_title"])
        for source in sink.sources
    ] == [
        (1, 101, "Original feed title"),
        (2, 202, "Second feed title"),
    ]


def test_sync_skips_duplicate_source_entry_in_same_payload():
    sink = RecordingSink()

    result = sync_miniflux_entries(
        {
            "entries": [
                {
                    "feed_id": 1,
                    "miniflux_entry_id": 101,
                    "url": "https://example.com/post?utm_medium=email",
                    "title": "Original entry",
                },
                {
                    "feed_id": 1,
                    "miniflux_entry_id": 101,
                    "url": "https://example.com/post?utm_medium=email",
                    "title": "Duplicate entry",
                },
            ]
        },
        sink,
    )

    assert result["entries_seen"] == 2
    assert result["articles_upserted"] == 1
    assert result["sources_upserted"] == 1
    assert result["source_duplicates_skipped"] == 1
    assert len(sink.sources) == 1
    assert sink.sources[0]["source_title"] == "Original entry"
