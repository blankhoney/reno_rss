import pytest


pytestmark = pytest.mark.asyncio


async def test_rescore_preserves_history_and_switches_active_score():
    from app.db.repositories.scoring import MemoryScoringRepository

    repository = MemoryScoringRepository()
    old_score = repository.create_score(article_id=1, base_score=70, is_active=True)
    new_score = repository.create_score(article_id=1, base_score=88, is_active=True)

    scores = repository.list_scores(article_id=1)

    assert {score.id for score in scores} == {old_score.id, new_score.id}
    assert [score for score in scores if score.is_active] == [new_score]


async def test_admin_creates_scoring_batch(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    response = await client.post(
        "/api/admin/scoring-batches",
        json={"name": "Today", "candidate_window": "today", "article_ids": [1, 2]},
    )

    assert response.status_code == 201
    assert response.json()["batch"]["name"] == "Today"
    assert response.json()["batch"]["status"] == "queued"
    assert response.json()["batch"]["article_count"] == 2
    assert [item["article_id"] for item in response.json()["batch"]["items"]] == [1, 2]


async def test_admin_starts_scoring_batch_and_enqueues_job(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)
    created = await client.post(
        "/api/admin/scoring-batches",
        json={"candidate_window": "last_3_days", "article_ids": [1]},
    )

    response = await client.post(
        f"/api/admin/scoring-batches/{created.json()['batch']['id']}/start"
    )

    assert response.status_code == 202
    assert response.json()["batch_id"] == created.json()["batch"]["id"]
    assert response.json()["status"] == "queued"
    assert response.json()["job_id"]


async def test_admin_gets_scoring_batch_detail(app, client):
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)
    created = await client.post(
        "/api/admin/scoring-batches",
        json={"name": "Custom", "candidate_window": "custom", "article_ids": [3]},
    )

    response = await client.get(
        f"/api/admin/scoring-batches/{created.json()['batch']['id']}"
    )

    assert response.status_code == 200
    assert response.json()["batch"]["id"] == created.json()["batch"]["id"]
    assert response.json()["batch"]["items"][0]["article_id"] == 3
