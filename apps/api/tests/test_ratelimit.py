import pytest


class CountingAskProvider:
    spends_llm_budget = True

    def __init__(self) -> None:
        self.calls = 0

    def answer_article_question(self, messages):
        self.calls += 1
        return ["limited answer"]


@pytest.mark.asyncio
async def test_llm_rate_limit_returns_envelope_before_provider_call(app, client):
    provider = CountingAskProvider()
    app.state.ask_provider = provider
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Limited Article",
            "content_text": "Enough context for rate-limit testing.",
        }
    )

    headers = {"X-Forwarded-For": "198.51.100.99, 203.0.113.10"}
    for _index in range(5):
        response = await client.post(
            f"/api/articles/{article.id}/ask",
            json={"question": "总结"},
            headers=headers,
        )
        assert response.status_code == 200

    limited = await client.post(
        f"/api/articles/{article.id}/ask",
        json={"question": "总结"},
        headers=headers,
    )
    spoofed_left_hop = await client.post(
        f"/api/articles/{article.id}/ask",
        json={"question": "总结"},
        headers={"X-Forwarded-For": "192.0.2.44, 203.0.113.10"},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
    assert spoofed_left_hop.status_code == 429
    assert provider.calls == 5


@pytest.mark.asyncio
async def test_write_rate_limit_applies_to_article_state(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Writable Article",
        }
    )

    for _index in range(30):
        response = await client.post(
            f"/api/articles/{article.id}/state",
            json={"saved": True},
        )
        assert response.status_code == 200

    limited = await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True},
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_auth_rate_limit_applies_to_login(client):
    headers = {"X-Forwarded-For": "198.51.100.71"}
    for index in range(5):
        response = await client.post(
            "/api/auth/login",
            json={"display_name": f"Login User {index}"},
            headers=headers,
        )
        assert response.status_code == 200
        client.cookies.clear()

    limited = await client.post(
        "/api/auth/login",
        json={"display_name": "Login User 6"},
        headers=headers,
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"


@pytest.mark.asyncio
async def test_auth_rate_limit_applies_to_recovery_code_attempts(client):
    headers = {"X-Forwarded-For": "198.51.100.72"}
    for _index in range(5):
        response = await client.post(
            "/api/auth/recover",
            json={"recovery_code": "invalid-recovery-code"},
            headers=headers,
        )
        assert response.status_code == 400
        assert response.json()["error"]["code"] == "invalid_recovery_code"

    limited = await client.post(
        "/api/auth/recover",
        json={"recovery_code": "invalid-recovery-code"},
        headers=headers,
    )

    assert limited.status_code == 429
    assert limited.json()["error"]["code"] == "rate_limited"
