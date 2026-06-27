from datetime import UTC, datetime, timedelta

import pytest


def test_article_repository_dedupes_by_canonical_url_without_tracking_params():
    from app.db.repositories.articles import MemoryArticleRepository

    repository = MemoryArticleRepository()
    first = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post?utm_source=newsletter&id=1",
            "title": "Same article",
            "published_at": datetime(2026, 6, 23, 10, tzinfo=UTC),
        }
    )
    second = repository.upsert_from_source(
        {
            "feed_id": 2,
            "miniflux_entry_id": 202,
            "url": "https://example.com/post?id=1&utm_campaign=launch",
            "title": "Same article via another feed",
            "published_at": datetime(2026, 6, 23, 11, tzinfo=UTC),
        }
    )

    assert first.id == second.id
    assert second.canonical_url == "https://example.com/post?id=1"
    assert len(repository.sources_for_article(first.id)) == 2


def test_article_source_upsert_is_idempotent_for_feed_entry_pair():
    from app.db.repositories.articles import MemoryArticleRepository

    repository = MemoryArticleRepository()
    first = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Original title",
        }
    )
    second = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post?utm_medium=email",
            "title": "Updated source title",
        }
    )

    sources = repository.sources_for_article(first.id)

    assert second.id == first.id
    assert len(sources) == 1
    assert sources[0].source_title == "Updated source title"


@pytest.mark.asyncio
async def test_article_list_uses_published_at_id_keyset_order(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    now = datetime(2026, 6, 23, 12, tzinfo=UTC)
    oldest = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/oldest",
            "title": "Oldest",
            "published_at": now - timedelta(hours=2),
        }
    )
    middle = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 102,
            "url": "https://example.com/middle",
            "title": "Middle",
            "published_at": now - timedelta(hours=1),
        }
    )
    newest = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 103,
            "url": "https://example.com/newest",
            "title": "Newest",
            "published_at": now,
        }
    )

    first_page = await client.get("/api/articles?limit=2")
    second_page = await client.get(
        "/api/articles",
        params={"limit": 2, "cursor": first_page.json()["next_cursor"]},
    )

    assert first_page.status_code == 200
    assert [item["id"] for item in first_page.json()["items"]] == [newest.id, middle.id]
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["items"]] == [oldest.id]
    assert second_page.json()["has_more"] is False


@pytest.mark.asyncio
async def test_article_detail_returns_sources_and_content(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
            "content_text": "Full text",
            "content_html": "<p>Full text</p>",
            "content_source": "miniflux_feed",
            "content_quality": "full",
        }
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 200
    assert response.json()["id"] == article.id
    assert response.json()["content_text"] == "Full text"
    assert response.json()["content_zh"] is None
    assert response.json()["content_zh_status"] is None
    assert response.json()["sources"] == [
        {
            "feed_id": 1,
            "feed_title": None,
            "miniflux_entry_id": 101,
            "source_url": "https://example.com/post",
        }
    ]


@pytest.mark.asyncio
async def test_article_detail_returns_cached_translation(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    translated_at = datetime(2026, 6, 25, 1, tzinfo=UTC)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
            "content_html": "<p>Full text</p>",
        }
    )
    app.state.article_repository.save_translation(
        article.id,
        content_zh="<p>中文正文</p>",
        status="succeeded",
        translated_at=translated_at,
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 200
    assert response.json()["content_zh"] == "<p>中文正文</p>"
    assert response.json()["content_zh_status"] == "succeeded"
    assert response.json()["translated_at"] == translated_at.isoformat()


@pytest.mark.asyncio
async def test_translate_article_returns_cached_translation(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    translated_at = datetime(2026, 6, 25, 1, tzinfo=UTC)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    app.state.article_repository.save_translation(
        article.id,
        content_zh="<p>中文正文</p>",
        status="succeeded",
        translated_at=translated_at,
    )

    response = await client.post(f"/api/articles/{article.id}/translate")

    assert response.status_code == 200
    assert response.json() == {
        "status": "succeeded",
        "content_zh": "<p>中文正文</p>",
        "translated_at": translated_at.isoformat(),
        "job_id": None,
    }


@pytest.mark.asyncio
async def test_translate_article_enqueues_job_and_marks_translation_queued(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/translate")
    detail_response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert isinstance(response.json()["job_id"], int)
    assert detail_response.json()["content_zh_status"] == "queued"


@pytest.mark.asyncio
async def test_articles_require_auth_when_anonymous_demo_disabled(app, client):
    # Production default: no session cookie and the flag off → fail closed.
    assert app.state.anonymous_demo_enabled is False
    response = await client.get("/api/articles")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_anonymous_demo_serves_articles_but_not_admin(app, client):
    # Staging public demo: anonymous requests resolve to a shared demo user.
    app.state.anonymous_demo_enabled = True
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    articles_response = await client.get("/api/articles")
    admin_response = await client.get("/api/admin/users")

    assert articles_response.status_code == 200
    assert len(articles_response.json()["items"]) == 1
    # Demo user is role=user, so admin endpoints stay protected.
    assert admin_response.status_code == 403


@pytest.mark.asyncio
async def test_article_list_and_detail_surface_active_score(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    app.state.scoring_repository.create_score(
        article_id=article.id,
        base_score=82,
        is_active=True,
    )

    list_response = await client.get("/api/articles")
    detail_response = await client.get(f"/api/articles/{article.id}")

    item = list_response.json()["items"][0]
    assert item["score"]["overall"] == 82
    assert item["score"]["tier"] == "read"
    assert detail_response.json()["score"]["overall"] == 82


@pytest.mark.asyncio
async def test_article_score_is_null_without_active_score(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.json()["score"] is None


@pytest.mark.asyncio
async def test_article_state_upserts_for_current_user(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/state",
        json={"status": "read", "saved": True, "read_progress": 0.75},
    )

    assert response.status_code == 200
    assert response.json()["state"] == {
        "status": "read",
        "saved": True,
        "read_progress": 0.75,
    }
