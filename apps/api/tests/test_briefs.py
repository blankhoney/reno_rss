from datetime import UTC, datetime

import pytest


@pytest.mark.asyncio
async def test_latest_brief_requires_session(client):
    response = await client.get("/api/briefs/latest")

    assert response.status_code == 401
    assert response.json()["error"]["code"] == "unauthenticated"


@pytest.mark.asyncio
async def test_latest_brief_returns_null_when_empty(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.get("/api/briefs/latest")

    assert response.status_code == 200
    assert response.json() == {"brief": None}


@pytest.mark.asyncio
async def test_latest_brief_does_not_cross_user_read_global_job(app):
    from httpx import ASGITransport, AsyncClient

    async with (
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            headers={"Referer": "https://test/"},
        ) as client_a,
        AsyncClient(
            transport=ASGITransport(app=app),
            base_url="https://test",
            headers={"Referer": "https://test/"},
        ) as client_b,
    ):
        login_a = await client_a.post("/api/auth/login", json={"display_name": "Ada"})
        login_b = await client_b.post("/api/auth/login", json={"display_name": "Babbage"})
        user_a = login_a.json()["user"]["id"]
        user_b = login_b.json()["user"]["id"]

        article_a = app.state.article_repository.upsert_from_source(
            {
                "feed_id": 1,
                "miniflux_entry_id": 601,
                "url": "https://example.com/ada-brief",
                "title": "Ada's private brief",
                "published_at": datetime(2026, 7, 18, tzinfo=UTC),
            }
        )
        article_b = app.state.article_repository.upsert_from_source(
            {
                "feed_id": 1,
                "miniflux_entry_id": 602,
                "url": "https://example.com/babbage-brief",
                "title": "Babbage's private brief",
                "published_at": datetime(2026, 7, 18, tzinfo=UTC),
            }
        )
        app.state.recommendation_repository.save_edition(
            user_id=user_a,
            items=[
                {
                    "article_id": article_a.id,
                    "rank": 1,
                    "rank_score": 91,
                    "tier": "must_read",
                    "reason": "Ada only",
                    "source": "fixture",
                }
            ],
            algorithm_version="b4.v1",
        )
        app.state.recommendation_repository.save_edition(
            user_id=user_b,
            items=[
                {
                    "article_id": article_b.id,
                    "rank": 1,
                    "rank_score": 82,
                    "tier": "read",
                    "reason": "Babbage only",
                    "source": "fixture",
                }
            ],
            algorithm_version="b4.v1",
        )

        global_job = app.state.job_repository.enqueue(
            "generate_daily_brief",
            {"trigger": "global-fixture"},
            dedupe_key="brief-global-fixture",
        )
        assert app.state.job_repository.claim_next("brief-worker") is not None
        app.state.job_repository.mark_succeeded(
            global_job.id,
            {
                "brief": {
                    "generated_at": "2026-07-19T08:00:00+00:00",
                    "title": "Global brief must not leak",
                    "must_read": [],
                    "worth_scan": [],
                    "can_skip": [],
                }
            },
        )

        response_a = await client_a.get("/api/briefs/latest")
        response_b = await client_b.get("/api/briefs/latest")

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    brief_a = response_a.json()["brief"]
    brief_b = response_b.json()["brief"]
    assert brief_a["source"] == "recommendations_fallback"
    assert brief_b["source"] == "recommendations_fallback"
    assert brief_a["must_read"][0]["article_id"] == article_a.id
    assert brief_b["worth_scan"][0]["article_id"] == article_b.id
    assert brief_a["title"] != "Global brief must not leak"
    assert brief_b["title"] != "Global brief must not leak"


@pytest.mark.asyncio
async def test_latest_brief_reads_current_user_recommendations(app, client):
    login = await client.post("/api/auth/login", json={"display_name": "Blank"})
    user_id = login.json()["user"]["id"]
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 501,
            "url": "https://example.com/must-read",
            "title": "Must Read From Repo",
            "published_at": datetime(2026, 7, 18, tzinfo=UTC),
        }
    )
    app.state.scoring_repository.create_score(
        article_id=article.id,
        base_score=93,
        is_active=True,
    )
    # Memory create_score leaves summary_zh empty; patch via list then replace.
    scores = app.state.scoring_repository.list_scores(article_id=article.id)
    active = scores[-1]
    from dataclasses import replace

    app.state.scoring_repository._scores[active.id] = replace(
        active,
        summary_zh="中文摘要：关键突破",
        recommendation_tier="must_read",
    )
    app.state.recommendation_repository.save_edition(
        user_id=user_id,
        items=[
            {
                "article_id": article.id,
                "rank": 1,
                "rank_score": 95.0,
                "tier": "must_read",
                "reason": "高分且新鲜",
                "source": "fixture",
            }
        ],
        algorithm_version="b4.v1",
    )

    response = await client.get("/api/briefs/latest")

    assert response.status_code == 200
    brief = response.json()["brief"]
    assert brief is not None
    assert brief["source"] == "recommendations_fallback"
    assert brief["title"].startswith("今日情报 ")
    assert len(brief["must_read"]) == 1
    must = brief["must_read"][0]
    assert must["article_id"] == article.id
    assert must["title"] == "Must Read From Repo"
    assert must["tier"] == "must_read"
    assert must["rank"] == 1
    assert must["rank_score"] == 95.0
    assert must["reason"] == "高分且新鲜"
    assert must["overall_score"] == 93
    assert must["summary_zh"] == "中文摘要：关键突破"
    assert brief["worth_scan"] == []
    assert brief["can_skip"] == []


@pytest.mark.asyncio
async def test_latest_brief_ignores_unowned_job_rows(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    # These rows have no owner and must not become a user's visible brief.
    thin = app.state.job_repository.enqueue(
        "generate_daily_brief",
        {"kind": "thin"},
        dedupe_key="brief-thin",
    )
    app.state.job_repository.claim_next("w1")
    app.state.job_repository.mark_succeeded(
        thin.id,
        {"status": "ok", "brief_id": 1, "item_count": 0},
    )
    full = app.state.job_repository.enqueue(
        "generate_daily_brief",
        {"kind": "daily_brief"},
        dedupe_key="brief-full",
    )
    app.state.job_repository.claim_next("w1")
    app.state.job_repository.mark_succeeded(
        full.id,
        {
            "generated_at": "2026-07-17T08:00:00+00:00",
            "title": "Global brief must not leak",
            "must_read": [],
            "worth_scan": [],
            "can_skip": [],
        },
    )

    response = await client.get("/api/briefs/latest")
    assert response.status_code == 200
    assert response.json() == {"brief": None}


def test_extract_brief_payload_accepts_nested_and_direct():
    from app.api.routes.briefs import extract_brief_payload

    direct = {
        "generated_at": "t",
        "title": "T",
        "must_read": [],
        "worth_scan": [],
        "can_skip": [],
    }
    assert extract_brief_payload(direct) == direct
    assert extract_brief_payload({"status": "ok", "brief": direct}) == direct
    assert extract_brief_payload({"status": "ok", "item_count": 0}) is None
    assert extract_brief_payload(None) is None


def test_recommendations_fallback_brief_tiers_are_disjoint():
    """Fallback brief must not put must_read into worth_scan (GOAL Daily Intelligence)."""
    from types import SimpleNamespace
    from uuid import uuid4

    from app.api.routes.briefs import brief_from_recommendations

    edition = SimpleNamespace(
        generated_at=datetime(2026, 7, 18, 9, 0, tzinfo=UTC),
        items=[
            SimpleNamespace(
                article_id=1, rank=1, tier="must_read", rank_score=95.0, reason="hot"
            ),
            SimpleNamespace(
                article_id=2, rank=2, tier="read", rank_score=72.0, reason="ok"
            ),
            SimpleNamespace(
                article_id=3, rank=3, tier="skim", rank_score=40.0, reason="low"
            ),
        ],
    )
    recommendation_repo = SimpleNamespace(latest_for_user=lambda _uid: edition)
    article_repo = SimpleNamespace(
        get_articles=lambda ids: {
            1: SimpleNamespace(title="Must"),
            2: SimpleNamespace(title="Read"),
            3: SimpleNamespace(title="Skim"),
        }
    )
    scoring_repo = SimpleNamespace(
        active_scores_for_articles=lambda ids: {
            1: SimpleNamespace(base_score=95, summary_zh="a"),
            2: SimpleNamespace(base_score=72, summary_zh="b"),
            3: SimpleNamespace(base_score=40, summary_zh="c"),
        }
    )
    brief = brief_from_recommendations(
        uuid4(), recommendation_repo, article_repo, scoring_repo
    )
    assert brief is not None
    must_ids = {row["article_id"] for row in brief["must_read"]}
    worth_ids = {row["article_id"] for row in brief["worth_scan"]}
    skip_ids = {row["article_id"] for row in brief["can_skip"]}
    assert must_ids == {1}
    assert worth_ids == {2}
    assert skip_ids == {3}
    assert must_ids.isdisjoint(worth_ids)
    assert must_ids.isdisjoint(skip_ids)
    assert worth_ids.isdisjoint(skip_ids)
