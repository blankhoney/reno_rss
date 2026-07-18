from datetime import UTC, datetime

import pytest


def test_normalize_title_strips_punctuation_and_case():
    from app.domain.clusters import normalize_title

    assert normalize_title("  OpenAI's GPT-5: Launch! ") == "openai s gpt 5 launch"


def test_title_similarity_jaccard_on_tokens():
    from app.domain.clusters import title_similarity

    high = title_similarity(
        "OpenAI launches GPT-5 model",
        "OpenAI launches GPT-5 to developers",
    )
    low = title_similarity(
        "OpenAI launches GPT-5 model",
        "Local bakery opens downtown",
    )
    assert high > 0.45
    assert low < 0.2


def test_cluster_articles_merges_same_day_high_overlap():
    from app.domain.clusters import ClusterArticle, cluster_articles

    day = datetime(2026, 7, 18, 10, tzinfo=UTC)
    clusters = cluster_articles(
        [
            ClusterArticle(id=1, title="Apple unveils Vision Pro 2", published_at=day, base_score=70),
            ClusterArticle(
                id=2,
                title="Apple unveils Vision Pro 2 headset",
                published_at=day.replace(hour=12),
                base_score=90,
            ),
            ClusterArticle(
                id=3,
                title="Unrelated cooking tips for summer",
                published_at=day,
                base_score=50,
            ),
        ]
    )

    assert len(clusters) == 1
    cluster = clusters[0]
    assert cluster.size == 2
    assert cluster.main_article_id == 2  # higher base_score
    assert set(cluster.related_article_ids) == {1}
    assert "Vision" in cluster.label or "Apple" in cluster.label
    assert cluster.id.startswith("cl_")


def test_cluster_articles_does_not_merge_across_days():
    from app.domain.clusters import ClusterArticle, cluster_articles

    clusters = cluster_articles(
        [
            ClusterArticle(
                id=1,
                title="Apple unveils Vision Pro 2 headset",
                published_at=datetime(2026, 7, 17, tzinfo=UTC),
            ),
            ClusterArticle(
                id=2,
                title="Apple unveils Vision Pro 2 headset",
                published_at=datetime(2026, 7, 18, tzinfo=UTC),
            ),
        ]
    )
    assert clusters == []


def test_cluster_articles_respects_limit_and_min_size():
    from app.domain.clusters import ClusterArticle, cluster_articles

    day = datetime(2026, 7, 18, tzinfo=UTC)
    articles = [
        ClusterArticle(id=1, title="Alpha beta gamma news", published_at=day, base_score=10),
        ClusterArticle(id=2, title="Alpha beta gamma update", published_at=day, base_score=20),
        ClusterArticle(id=3, title="Delta epsilon zeta news", published_at=day, base_score=30),
        ClusterArticle(id=4, title="Delta epsilon zeta report", published_at=day, base_score=40),
        ClusterArticle(id=5, title="Lonely single article only", published_at=day, base_score=99),
    ]
    clusters = cluster_articles(articles, limit=1)
    assert len(clusters) == 1
    # Prefer larger / higher main score among multi-article clusters
    assert clusters[0].size == 2


def test_cluster_articles_without_published_at_never_merge():
    from app.domain.clusters import ClusterArticle, cluster_articles

    clusters = cluster_articles(
        [
            ClusterArticle(id=1, title="Same title twice", published_at=None),
            ClusterArticle(id=2, title="Same title twice", published_at=None),
        ]
    )
    assert clusters == []


@pytest.mark.asyncio
async def test_latest_clusters_requires_session(client):
    response = await client.get("/api/clusters/latest")
    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_latest_clusters_returns_storyline_payload(app, client):
    await client.post("/api/auth/login", json={"display_name": "ClusterUser"})
    day = datetime(2026, 7, 18, 9, tzinfo=UTC)
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 1,
            "url": "https://example.com/a",
            "title": "SpaceX Starship completes test flight",
            "published_at": day,
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 2,
            "miniflux_entry_id": 2,
            "url": "https://example.com/b",
            "title": "SpaceX Starship completes orbital test flight",
            "published_at": day.replace(hour=14),
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 3,
            "url": "https://example.com/c",
            "title": "Garden tips for tomatoes",
            "published_at": day,
        }
    )

    response = await client.get("/api/clusters/latest?limit=20")
    assert response.status_code == 200
    body = response.json()
    assert "clusters" in body
    assert len(body["clusters"]) == 1
    cluster = body["clusters"][0]
    assert cluster["size"] == 2
    assert cluster["main_article_id"] in {1, 2}
    assert set(cluster["related_article_ids"]) | {cluster["main_article_id"]} == {1, 2}
    assert isinstance(cluster["id"], str)
    assert isinstance(cluster["label"], str)
