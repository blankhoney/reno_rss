import pytest


pytestmark = pytest.mark.asyncio


async def test_categories_returns_seeded_slugs(client):
    response = await client.get("/api/categories")

    assert response.status_code == 200
    assert [category["slug"] for category in response.json()["items"]] == [
        "ai_infra",
        "agent",
        "rag",
        "paper",
        "programming",
        "tooling",
        "product",
        "business",
        "game",
        "other",
    ]


async def test_feeds_requires_session(client):
    response = await client.get("/api/feeds")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


async def test_post_feed_creates_global_feed_and_subscription(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.post(
        "/api/feeds",
        json={"feed_url": "https://example.com/rss.xml", "category_id": 1},
    )

    assert response.status_code == 201
    assert response.json()["already_exists"] is False
    assert response.json()["feed"]["feed_url"] == "https://example.com/rss.xml"
    assert response.json()["feed"]["subscribed"] is True
    assert response.json()["job_id"] is None


async def test_reposting_existing_feed_subscribes_without_conflict(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as first:
        await first.post("/api/auth/login", json={"display_name": "First"})
        created = await first.post(
            "/api/feeds",
            json={"feed_url": "https://example.com/rss.xml", "category_id": 1},
        )

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as second:
        await second.post("/api/auth/login", json={"display_name": "Second"})
        reused = await second.post(
            "/api/feeds",
            json={"feed_url": "https://example.com/rss.xml", "category_id": 1},
        )
        feeds = await second.get("/api/feeds")

    assert reused.status_code == 200
    assert reused.json()["already_exists"] is True
    assert reused.json()["feed"]["id"] == created.json()["feed"]["id"]
    assert reused.json()["feed"]["subscribed"] is True
    assert feeds.json()["items"] == [reused.json()["feed"]]


async def test_user_can_unsubscribe_and_resubscribe_feed(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    created = await client.post(
        "/api/feeds",
        json={"feed_url": "https://example.com/rss.xml", "category_id": 1},
    )
    feed_id = created.json()["feed"]["id"]

    unsubscribed = await client.delete(f"/api/feeds/{feed_id}/subscribe")
    resubscribed = await client.post(f"/api/feeds/{feed_id}/subscribe")

    assert unsubscribed.status_code == 200
    assert unsubscribed.json() == {"subscribed": False}
    assert resubscribed.status_code == 200
    assert resubscribed.json() == {"subscribed": True}


@pytest.mark.parametrize("priority", [-21, 21])
async def test_feed_priority_rejects_values_outside_allowed_range(client, priority):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    created = await client.post(
        "/api/feeds",
        json={"feed_url": "https://example.com/rss.xml", "category_id": 1},
    )

    response = await client.put(
        f"/api/feeds/{created.json()['feed']['id']}/priority",
        json={"user_priority": priority},
    )

    assert response.status_code == 422
    assert response.json()["error"]["code"] == "unprocessable"
