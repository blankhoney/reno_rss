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


async def test_admin_can_create_and_read_ranking_benchmark_run(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    created = await client.post(
        "/api/admin/benchmarks",
        json={
            "suite": "ranking",
            "mode": "ci_mini",
            "provider": "mock",
            "params": {"sample": "mini"},
        },
    )

    assert created.status_code == 202
    body = created.json()
    assert body["benchmark_run"]["suite"] == "ranking"
    assert body["benchmark_run"]["mode"] == "ci_mini"
    assert body["benchmark_run"]["status"] == "queued"
    assert body["benchmark_run"]["params"] == {"sample": "mini", "provider": "mock"}
    assert body["job"]["job_type"] == "run_benchmark"
    job = app.state.job_repository.get_visible_job(
        body["job"]["id"],
        current_user_id=_admin.id,
        is_admin=True,
    )
    assert job is not None
    assert job.payload == {
        "benchmark_run_id": body["benchmark_run"]["id"],
        "suite": "ranking",
        "mode": "ci_mini",
        "provider": "mock",
        "params": {"sample": "mini"},
    }

    fetched = await client.get(f"/api/admin/benchmarks/{body['benchmark_run']['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["benchmark_run"]["id"] == body["benchmark_run"]["id"]


async def test_admin_benchmark_rejects_model_swap(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    response = await client.post(
        "/api/admin/benchmarks",
        json={"suite": "model_swap", "mode": "ci_mini", "provider": "mock"},
    )

    assert response.status_code == 400
    assert response.json()["error"]["code"] == "unsupported"


async def test_admin_benchmark_rejects_real_llm_without_manual_confirmation(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    ci_response = await client.post(
        "/api/admin/benchmarks",
        json={"suite": "ranking", "mode": "ci_mini", "provider": "minimax"},
    )
    manual_response = await client.post(
        "/api/admin/benchmarks",
        json={"suite": "ranking", "mode": "manual_full", "provider": "minimax"},
    )

    assert ci_response.status_code == 400
    assert manual_response.status_code == 400
    assert ci_response.json()["error"]["code"] == "real_llm_confirmation_required"
