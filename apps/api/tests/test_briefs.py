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
async def test_latest_brief_reads_succeeded_job_and_enriches_items(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
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

    job = app.state.job_repository.enqueue(
        "generate_daily_brief",
        {"limit": 10, "trigger": "test"},
        dedupe_key="brief-test-1",
    )
    claimed = app.state.job_repository.claim_next("test-worker")
    assert claimed is not None and claimed.id == job.id
    app.state.job_repository.mark_succeeded(
        job.id,
        {
            "status": "ok",
            "brief_id": job.id,
            "item_count": 2,
            "brief": {
                "generated_at": "2026-07-18T08:00:00+00:00",
                "title": "今日情报 2026-07-18",
                "must_read": [
                    {
                        "article_id": article.id,
                        "rank": 1,
                        "tier": "must_read",
                        "rank_score": 95.0,
                        "reason": "高分且新鲜",
                        "title": "",  # force enrichment from article repo
                    }
                ],
                "worth_scan": [
                    {
                        "article_id": 9999,
                        "rank": 2,
                        "tier": "read",
                        "rank_score": 72.0,
                        "reason": "可扫一眼",
                        "title": "Orphan Title",
                    }
                ],
                "can_skip": [],
            },
        },
    )

    response = await client.get("/api/briefs/latest")

    assert response.status_code == 200
    body = response.json()
    brief = body["brief"]
    assert brief is not None
    assert brief["title"] == "今日情报 2026-07-18"
    assert brief["generated_at"] == "2026-07-18T08:00:00+00:00"
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
    assert brief["worth_scan"][0]["title"] == "Orphan Title"
    assert brief["worth_scan"][0]["overall_score"] == 72.0
    assert brief["can_skip"] == []


@pytest.mark.asyncio
async def test_latest_brief_prefers_sink_shaped_result_over_thin_status(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    # Thin status row (worker job.result without nested brief) — should be skipped.
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

    # Sink-shaped full brief row.
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
            "title": "今日情报 2026-07-17",
            "must_read": [],
            "worth_scan": [],
            "can_skip": [],
        },
    )

    response = await client.get("/api/briefs/latest")
    assert response.status_code == 200
    assert response.json()["brief"]["title"] == "今日情报 2026-07-17"


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
