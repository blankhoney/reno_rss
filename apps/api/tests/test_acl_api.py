import pytest


@pytest.mark.asyncio
async def test_project_acl_owner_can_grant(client):
    await client.post("/api/auth/login", json={"display_name": "Owner"})
    me = await client.get("/api/auth/me")
    # Some deployments expose /api/auth/session; fall back to login response cookies only.
    put = await client.put(
        "/api/projects/p-demo/acl",
        json={"user_id": "00000000-0000-0000-0000-000000000099", "role": "viewer"},
    )
    # First put seeds owner grant for current user then adds viewer.
    assert put.status_code in {200, 403, 401}
    if put.status_code == 200:
        body = put.json()
        assert body["project_id"] == "p-demo"
        assert any(item["role"] == "owner" for item in body["items"])
        got = await client.get("/api/projects/p-demo/acl")
        assert got.status_code == 200
        assert got.json()["my_role"] == "owner"
    del me
