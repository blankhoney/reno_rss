import pytest


pytestmark = pytest.mark.asyncio


async def test_enqueue_research_job_requires_auth(client):
    response = await client.post(
        "/api/research/jobs",
        json={"scope": "topn", "question": "What is new in agents?"},
    )
    assert response.status_code == 401


async def test_enqueue_and_get_research_job(client):
    await client.post("/api/auth/login", json={"display_name": "Researcher"})

    created = await client.post(
        "/api/research/jobs",
        json={
            "scope": "topic",
            "topic": "LLM",
            "question": "What tooling matters?",
            "max_articles": 5,
        },
    )
    assert created.status_code == 202
    body = created.json()
    assert body["job_type"] == "research_brief"
    assert body["status"] == "queued"
    assert body["poll_url"] == f"/api/jobs/{body['job_id']}"

    # Shared jobs API
    shared = await client.get(body["poll_url"])
    assert shared.status_code == 200
    assert shared.json()["job_type"] == "research_brief"

    # Alias under /api/research/jobs/{id}
    alias = await client.get(f"/api/research/jobs/{body['job_id']}")
    assert alias.status_code == 200
    assert alias.json()["id"] == body["job_id"]


async def test_research_topic_scope_requires_topic(client):
    await client.post("/api/auth/login", json={"display_name": "Researcher"})
    response = await client.post(
        "/api/research/jobs",
        json={"scope": "topic", "question": "missing topic"},
    )
    assert response.status_code == 422


async def test_research_job_dedupes_identical_request(client):
    await client.post("/api/auth/login", json={"display_name": "Researcher"})
    payload = {"scope": "topn", "question": "same question twice"}
    first = await client.post("/api/research/jobs", json=payload)
    second = await client.post("/api/research/jobs", json=payload)
    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
