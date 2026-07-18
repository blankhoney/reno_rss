import pytest


pytestmark = pytest.mark.asyncio


async def test_saved_searches_empty_by_default(client):
    await client.post("/api/auth/login", json={"display_name": "FilterUser"})
    response = await client.get("/api/saved-searches")
    assert response.status_code == 200
    assert response.json() == {"items": []}


async def test_put_and_get_saved_searches(client):
    await client.post("/api/auth/login", json={"display_name": "FilterUser"})
    put = await client.put(
        "/api/saved-searches",
        json={
            "items": [
                {
                    "name": "AI unread",
                    "q": "agent",
                    "module": "unread",
                    "sort": "score_desc",
                },
                {
                    "name": "Project queue",
                    "q": "",
                    "module": "project",
                    "sort": "published_desc",
                },
            ]
        },
    )
    assert put.status_code == 200
    items = put.json()["items"]
    assert len(items) == 2
    assert items[0]["name"] == "AI unread"
    assert items[0]["q"] == "agent"
    assert items[0]["module"] == "unread"
    assert items[0]["sort"] == "score_desc"
    assert "id" in items[0]

    got = await client.get("/api/saved-searches")
    assert got.status_code == 200
    assert got.json()["items"][1]["module"] == "project"

    # Replace clears previous set
    cleared = await client.put("/api/saved-searches", json={"items": []})
    assert cleared.json()["items"] == []


async def test_saved_searches_reject_bad_module(client):
    await client.post("/api/auth/login", json={"display_name": "FilterUser"})
    response = await client.put(
        "/api/saved-searches",
        json={"items": [{"name": "bad", "module": "not-a-module"}]},
    )
    assert response.status_code == 422


async def test_saved_searches_require_auth(client):
    response = await client.get("/api/saved-searches")
    assert response.status_code == 401
