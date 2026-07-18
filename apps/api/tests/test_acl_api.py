import pytest
from uuid import uuid4


@pytest.mark.asyncio
async def test_project_acl_owner_can_grant(app, client):
    login = await client.post("/api/auth/login", json={"display_name": "Owner"})
    owner_id = login.json()["user"]["id"]
    viewer, _, _ = app.state.auth_store.create_user("Viewer")

    put = await client.put(
        "/api/projects/p-demo/acl",
        json={"user_id": str(viewer.id), "role": "viewer"},
    )
    assert put.status_code == 200
    assert put.json() == {
        "project_id": "p-demo",
        "items": [
            {"user_id": owner_id, "role": "owner"},
            {"user_id": str(viewer.id), "role": "viewer"},
        ],
    }

    got = await client.get("/api/projects/p-demo/acl")
    assert got.status_code == 200
    assert got.json()["my_role"] == "owner"


@pytest.mark.asyncio
async def test_project_acl_non_owner_cannot_grant(app, client):
    login = await client.post("/api/auth/login", json={"display_name": "Owner"})
    owner_id = login.json()["user"]["id"]
    editor, editor_token, _ = app.state.auth_store.create_user("Editor")
    target, _, _ = app.state.auth_store.create_user("Target")

    first = await client.put(
        "/api/projects/p-locked/acl",
        json={"user_id": str(editor.id), "role": "editor"},
    )
    assert first.status_code == 200

    from app.core.security import SESSION_COOKIE_NAME

    client.cookies.set(SESSION_COOKIE_NAME, editor_token)
    denied = await client.put(
        "/api/projects/p-locked/acl",
        json={"user_id": str(target.id), "role": "viewer"},
    )
    assert denied.status_code == 403
    assert denied.json()["error"]["code"] == "forbidden"

    grants = app.state.project_acl_repository.list_grants("p-locked")
    assert [(str(grant.user_id), grant.role.value) for grant in grants] == [
        (owner_id, "owner"),
        (str(editor.id), "editor"),
    ]


def test_memory_project_acl_repository_isolates_projects_and_bootstraps_owner():
    from app.db.repositories.project_acl import MemoryProjectAclRepository
    from app.domain.acl import ProjectRole

    store = MemoryProjectAclRepository()
    owner_id = uuid4()
    viewer_id = uuid4()

    grants = store.grant(
        "project-a",
        actor_user_id=owner_id,
        target_user_id=viewer_id,
        role=ProjectRole.VIEWER,
    )

    assert [(grant.user_id, grant.role) for grant in grants] == [
        (owner_id, ProjectRole.OWNER),
        (viewer_id, ProjectRole.VIEWER),
    ]
    assert store.list_grants("project-b") == []
