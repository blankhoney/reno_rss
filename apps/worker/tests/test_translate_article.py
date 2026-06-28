from datetime import UTC, datetime

import pytest

from app.jobs.translate_article import translate_article


class RecordingTranslationSink:
    def __init__(self, article):
        self.article = dict(article)
        self.saved: list[dict[str, object]] = []

    def get_article_for_translation(self, article_id: int):
        assert article_id == self.article["id"]
        return dict(self.article)

    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str,
        translated_at: datetime | None,
    ) -> None:
        assert article_id == self.article["id"]
        self.saved.append(
            {
                "content_zh": content_zh,
                "status": status,
                "translated_at": translated_at,
            }
        )


class TranslationProvider:
    def __init__(self, result: str | Exception):
        self.result = result
        self.calls: list[dict[str, object]] = []

    def score_article(self, article, rubric):
        raise NotImplementedError

    def translate_article(self, article):
        self.calls.append(dict(article))
        if isinstance(self.result, Exception):
            raise self.result
        return self.result


def test_translate_article_saves_translated_html():
    now = datetime(2026, 6, 25, 12, tzinfo=UTC)
    sink = RecordingTranslationSink(_article())
    provider = TranslationProvider("<p>中文正文</p>")

    result = translate_article({"article_id": 1}, sink=sink, provider=provider, now=now)

    assert result == {
        "outcome": "translated",
        "content_zh_status": "succeeded",
        "translated_at": now.isoformat(),
        "html_length": len("<p>中文正文</p>"),
    }
    assert provider.calls[0]["title"] == "Article"
    assert sink.saved == [
        {"content_zh": None, "status": "running", "translated_at": None},
        {"content_zh": "<p>中文正文</p>", "status": "succeeded", "translated_at": now},
    ]


def test_translate_article_uses_cached_translation():
    sink = RecordingTranslationSink(
        _article(content_zh="<p>缓存译文</p>", content_zh_status="succeeded")
    )
    provider = TranslationProvider("<p>不会调用</p>")

    result = translate_article({"article_id": 1}, sink=sink, provider=provider)

    assert result == {"outcome": "cached", "content_zh_status": "succeeded"}
    assert provider.calls == []
    assert sink.saved == []


def test_translate_article_marks_failed_before_reraising():
    sink = RecordingTranslationSink(_article())
    provider = TranslationProvider(RuntimeError("provider down"))

    with pytest.raises(RuntimeError, match="provider down"):
        translate_article({"article_id": 1}, sink=sink, provider=provider)

    assert sink.saved == [
        {"content_zh": None, "status": "running", "translated_at": None},
        {"content_zh": None, "status": "failed", "translated_at": None},
    ]


def test_translate_article_marks_empty_translation_failed():
    sink = RecordingTranslationSink(_article())
    provider = TranslationProvider("   ")

    with pytest.raises(ValueError, match="translation produced empty output"):
        translate_article({"article_id": 1}, sink=sink, provider=provider)

    assert sink.saved == [
        {"content_zh": None, "status": "running", "translated_at": None},
        {"content_zh": None, "status": "failed", "translated_at": None},
    ]


def test_worker_registry_includes_translate_article_handler():
    from app.main import build_handler_registry

    registry = build_handler_registry()

    assert "translate_article" in registry


def _article(content_zh: str | None = None, content_zh_status: str | None = None):
    return {
        "id": 1,
        "title": "Article",
        "url": "https://example.com/post",
        "content_html": "<p>Body</p>",
        "content_text": "Body",
        "content_zh": content_zh,
        "content_zh_status": content_zh_status,
    }
