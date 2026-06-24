import pytest


pytestmark = pytest.mark.asyncio


async def test_admin_sync_enqueues_deduped_miniflux_sync_job(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    first = await client.post("/api/admin/sync", json={"limit": 50})
    second = await client.post("/api/admin/sync", json={"limit": 50})

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_type"] == "sync_miniflux_entries"
    assert first.json()["status"] == "queued"
    assert second.json()["job_id"] == first.json()["job_id"]


async def test_admin_sync_requires_admin(client):
    await client.post("/api/auth/login", json={"display_name": "User"})

    response = await client.post("/api/admin/sync", json={"limit": 50})

    assert response.status_code == 403
    assert response.json()["error"]["code"] == "forbidden"
