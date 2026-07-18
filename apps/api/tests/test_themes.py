from app.domain.themes import cluster_themes


def test_cluster_themes_groups_normalized_tags_by_weight():
    themes = cluster_themes(
        [
            {"article_id": 1, "tags": [" AI ", "rust"], "base_score": 90},
            {"article_id": 2, "tags": ["ai"], "keywords": ["agents"], "base_score": 80},
            {"article_id": 3, "tags": ["Cooking"], "base_score": 40},
            {"article_id": 4, "tags": [], "base_score": 99},
        ],
        max_themes=10,
    )
    assert themes[0]["label"] == "ai"
    assert themes[0]["article_ids"] == [1, 2]
    assert themes[0]["weight"] >= 2
    labels = [theme["label"] for theme in themes]
    assert "rust" in labels
    assert "agents" in labels
    assert "cooking" in labels


def test_cluster_themes_respects_max_themes():
    scores = [
        {"article_id": index, "tags": [f"tag-{index}"], "base_score": 50}
        for index in range(1, 12)
    ]
    themes = cluster_themes(scores, max_themes=3)
    assert len(themes) == 3


import pytest


@pytest.mark.asyncio
async def test_themes_latest_endpoint(app, client):
    await client.post("/api/auth/login", json={"display_name": "ThemeUser"})
    app.state.scoring_repository.create_score(
        article_id=1, base_score=88, is_active=True, tags=["ai", "infra"]
    )
    app.state.scoring_repository.create_score(
        article_id=2, base_score=70, is_active=True, tags=["ai"]
    )

    response = await client.get("/api/themes/latest")
    assert response.status_code == 200
    body = response.json()
    assert body["source_score_count"] == 2
    assert body["themes"][0]["label"] == "ai"
    assert set(body["themes"][0]["article_ids"]) == {1, 2}
