from datetime import UTC, datetime
from types import SimpleNamespace

import pytest


class RecordingAskProvider:
    def __init__(self, chunks):
        self.chunks = chunks
        self.calls = []

    def answer_article_question(self, messages):
        self.calls.append(messages)
        return list(self.chunks)


class ChunkingAskProvider(RecordingAskProvider):
    def answer_article_question(self, messages):
        self.calls.append(messages)
        for chunk in self.chunks:
            yield chunk


class StaticScoringRepository:
    def __init__(self, scores):
        self.scores = scores

    def list_scores(self, *, article_id):
        return list(self.scores)


@pytest.mark.asyncio
async def test_ask_requires_session(client):
    response = await client.post("/api/articles/1/ask", json={"question": "总结"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_ask_rejects_client_supplied_article_content(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
            "content_text": "Server-side article text",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/ask",
        json={"question": "总结", "article_content": "client supplied"},
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_ask_returns_content_required_when_article_has_no_usable_context(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Only title",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert response.status_code == 409
    assert response.json()["error"]["code"] == "content_required"


@pytest.mark.asyncio
async def test_ask_can_use_active_summary_and_score_reason_when_body_is_missing(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    provider = RecordingAskProvider(["可以回答"])
    app.state.ask_provider = provider
    app.state.scoring_repository = StaticScoringRepository(
        [
            SimpleNamespace(
                is_active=True,
                scoring_status="success",
                summary_zh="服务端摘要",
                reason="高信息密度",
                tags=["ai"],
                risk_flags=["low_signal"],
            )
        ]
    )
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Summary only",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert response.status_code == 200
    serialized_messages = str(provider.calls)
    assert "服务端摘要" in serialized_messages
    assert "高信息密度" in serialized_messages
    assert "ai" in serialized_messages


@pytest.mark.asyncio
async def test_ask_uses_html_projection_and_ignores_missing_selected_text(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    provider = RecordingAskProvider(["可以回答"])
    app.state.ask_provider = provider
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "HTML only",
            "content_html": "<article><p>HTML body text.</p></article>",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/ask",
        json={"question": "总结", "selected_text": "not in article"},
    )

    assert response.status_code == 200
    serialized_messages = str(provider.calls)
    assert "HTML body text." in serialized_messages
    assert "not in article" not in serialized_messages


@pytest.mark.asyncio
async def test_ask_streams_sse_without_think_blocks_from_server_built_context(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    provider = RecordingAskProvider(["结论：", "<think>hidden reasoning</think>", "值得读"])
    app.state.ask_provider = provider
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Agent Article",
            "content_text": "Server truth with Important quote.",
            "published_at": datetime(2026, 6, 24, tzinfo=UTC),
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/ask",
        json={"question": "解释这段", "selected_text": "Important quote"},
    )

    assert response.status_code == 200
    assert response.headers["content-type"].startswith("text/event-stream")
    assert response.headers["x-agent-search-status"] == "disabled"
    assert "data: 结论：" in response.text
    assert "data: 值得读" in response.text
    assert "hidden reasoning" not in response.text
    serialized_messages = str(provider.calls)
    assert "Server truth with Important quote." in serialized_messages
    assert "Important quote" in serialized_messages
    assert "client supplied" not in serialized_messages


@pytest.mark.asyncio
async def test_ask_strips_think_block_across_stream_chunks(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    app.state.ask_provider = ChunkingAskProvider(["结论：", "<thi", "nk>secret</think>", "可读"])
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Agent Article",
            "content_text": "Server truth.",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert response.status_code == 200
    assert "secret" not in response.text
    assert "data: 结论：" in response.text
    assert "data: 可读" in response.text
