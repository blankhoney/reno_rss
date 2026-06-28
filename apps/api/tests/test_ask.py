from datetime import UTC, datetime
import json
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


class FakeMiniMaxStream:
    def __init__(self, lines):
        self.lines = lines

    def __enter__(self):
        return self

    def __exit__(self, _exc_type, _exc, _traceback):
        return False

    def raise_for_status(self):
        return None

    def iter_lines(self):
        return iter(self.lines)


def _minimax_stream_line(content):
    return "data: " + json.dumps(
        {"choices": [{"delta": {"content": content}}]},
        ensure_ascii=False,
    )


@pytest.mark.asyncio
async def test_ask_requires_session(client):
    response = await client.post("/api/articles/1/ask", json={"question": "总结"})

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


def test_create_ask_provider_falls_back_when_minimax_key_is_unconfigured():
    from app.api.routes.ask import DeterministicAskProvider, create_ask_provider
    from app.core.config import Settings

    settings = Settings(llm_provider="minimax", minimax_api_key="")

    assert isinstance(create_ask_provider(settings), DeterministicAskProvider)


def test_create_app_selects_minimax_ask_provider_when_key_is_configured(monkeypatch):
    from app.api.routes.ask import MiniMaxAskProvider
    from app.main import create_app

    monkeypatch.setenv("LLM_PROVIDER", "minimax")
    monkeypatch.setenv("MINIMAX_API_KEY", "test-key")

    app = create_app()

    assert isinstance(app.state.ask_provider, MiniMaxAskProvider)


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
async def test_ask_includes_selected_text_even_when_not_in_article_body(app, client):
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
    assert "用户选中文字（来自页面，可能为译文/跨段）" in serialized_messages
    assert "not in article" in serialized_messages


@pytest.mark.asyncio
async def test_ask_marks_missing_selected_text_as_none(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    provider = RecordingAskProvider(["可以回答"])
    app.state.ask_provider = provider
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Plain text",
            "content_text": "Article body.",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert response.status_code == 200
    serialized_messages = str(provider.calls)
    assert "用户选中文字（来自页面，可能为译文/跨段）：\\n无" in serialized_messages


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
async def test_ask_streams_minimax_chunks_without_logging_bodies(app, client, caplog):
    from app.api.routes.ask import MiniMaxAskProvider

    captured_request = {}

    def stream_factory(method, url, *, headers, json, timeout):
        captured_request.update(
            {
                "method": method,
                "url": url,
                "headers": headers,
                "json": json,
                "timeout": timeout,
            }
        )
        return FakeMiniMaxStream(
            [
                _minimax_stream_line("结论："),
                _minimax_stream_line("<think>hidden provider reasoning</think>值得读"),
                "data: [DONE]",
            ]
        )

    await client.post("/api/auth/login", json={"display_name": "Blank"})
    app.state.ask_provider = MiniMaxAskProvider(
        api_key="test-key",
        base_url="https://llm.example/v1",
        model="MiniMax-Test",
        timeout_seconds=9.0,
        stream_factory=stream_factory,
    )
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Agent Article",
            "content_text": "Server truth with private body.",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert response.status_code == 200
    assert "data: 结论：" in response.text
    assert "data: 值得读" in response.text
    assert "hidden provider reasoning" not in response.text
    assert captured_request["method"] == "POST"
    assert captured_request["url"] == "https://llm.example/v1/chat/completions"
    assert captured_request["headers"] == {"Authorization": "Bearer test-key"}
    assert captured_request["json"]["model"] == "MiniMax-Test"
    assert captured_request["json"]["stream"] is True
    assert captured_request["json"]["temperature"] == 0.2
    assert captured_request["timeout"] == 9.0
    assert "Server truth with private body." in str(captured_request["json"]["messages"])
    assert "Server truth with private body." not in caplog.text
    assert "结论：" not in caplog.text


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
