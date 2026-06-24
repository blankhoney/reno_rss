from datetime import UTC, datetime, timedelta

from app.jobs.fetch_content import fetch_article_content


class RecordingContentSink:
    def __init__(self, article):
        self.article = dict(article)
        self.saved: dict[str, object] | None = None

    def get_article_for_fetch(self, article_id: int):
        assert article_id == self.article["id"]
        return dict(self.article)

    def save_content(self, article_id: int, content: dict[str, object]) -> None:
        assert article_id == self.article["id"]
        self.saved = dict(content)


class FakeMinifluxClient:
    def __init__(self, content: str | Exception):
        self.content = content

    def fetch_content(self, entry_id: int) -> str:
        assert entry_id == 101
        if isinstance(self.content, Exception):
            raise self.content
        return self.content


class FakeExternalProvider:
    def __init__(self, content: str | None):
        self.content = content

    def fetch(self, url: str) -> str | None:
        assert url == "https://example.com/post"
        return self.content


def test_fetch_article_content_applies_miniflux_readability_content():
    now = datetime(2026, 6, 24, 12, tzinfo=UTC)
    sink = RecordingContentSink(_article())
    full_html = f"<article>{'useful text ' * 40}</article>"

    result = fetch_article_content(
        {"article_id": 1},
        sink=sink,
        miniflux_client=FakeMinifluxClient(full_html),
        external_provider=FakeExternalProvider(None),
        now=now,
    )

    assert result["outcome"] == "applied"
    assert sink.saved is not None
    assert sink.saved["content_html"] == full_html
    assert sink.saved["content_source"] == "readability"
    assert sink.saved["content_quality"] == "full"
    assert sink.saved["fetched_at"] == now
    assert sink.saved["content_expires_at"] == now + timedelta(days=7)


def test_fetch_article_content_falls_back_to_external_then_snippet():
    now = datetime(2026, 6, 24, 12, tzinfo=UTC)
    external_html = f"<article>{'external text ' * 40}</article>"
    sink = RecordingContentSink(_article())

    external_result = fetch_article_content(
        {"article_id": 1},
        sink=sink,
        miniflux_client=FakeMinifluxClient(RuntimeError("miniflux down")),
        external_provider=FakeExternalProvider(external_html),
        now=now,
    )

    assert external_result["content_source"] == "external"
    assert sink.saved is not None
    assert sink.saved["content_html"] == external_html

    snippet_sink = RecordingContentSink(_article(content_html="<p>Short body</p>"))
    snippet_result = fetch_article_content(
        {"article_id": 1},
        sink=snippet_sink,
        miniflux_client=FakeMinifluxClient(RuntimeError("miniflux down")),
        external_provider=FakeExternalProvider(None),
        now=now,
    )

    assert snippet_result["content_source"] == "snippet_only"
    assert snippet_sink.saved is not None
    assert snippet_sink.saved["content_quality"] == "snippet"


def _article(content_html: str = "<p>Short body</p>"):
    return {
        "id": 1,
        "title": "Article",
        "url": "https://example.com/post",
        "content_html": content_html,
        "content_text": "Short body",
        "miniflux_entry_id": 101,
    }
