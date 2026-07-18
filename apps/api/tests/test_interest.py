from datetime import UTC, datetime

import pytest

from app.domain.personalization import InterestSignal, build_interest_profile, tokenize


def test_tokenize_extracts_cjk_and_words():
    assert "rust" in tokenize("Rust release 笔记")
    assert "笔记" in tokenize("Rust release 笔记")


def test_build_interest_profile_weights_keywords():
    profile = build_interest_profile(
        [
            InterestSignal(text="Rust async runtime", weight=2),
            InterestSignal(text="Rust crates", weight=1),
            InterestSignal(text="llm agents", weight=1.5),
        ],
        feedback_types=["underrated", "underrated", "overrated"],
        project_count=2,
        annotation_count=3,
        generated_at=datetime(2026, 7, 18, tzinfo=UTC),
    )
    terms = {item["term"]: item["weight"] for item in profile["keywords"]}
    assert terms["rust"] >= terms["llm"]
    assert profile["project_count"] == 2
    assert profile["annotation_count"] == 3
    assert profile["feedback_counts"]["underrated"] == 2


@pytest.mark.asyncio
async def test_interest_requires_session(client):
    response = await client.get("/api/me/interest")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_interest_get_reset_export(client, app):
    await client.post("/api/auth/login", json={"display_name": "InterestUser"})

    got = await client.get("/api/me/interest")
    assert got.status_code == 200
    body = got.json()
    assert "keywords" in body
    assert body["reset_at"] is None

    reset = await client.post("/api/me/interest/reset")
    assert reset.status_code == 200
    assert reset.json()["status"] == "ok"
    assert reset.json()["reset_at"] is not None

    after = await client.get("/api/me/interest")
    assert after.status_code == 200
    assert after.json()["reset_at"] is not None
    assert after.json()["keywords"] == []

    export = await client.get("/api/me/interest/export")
    assert export.status_code == 200
    assert export.json()["format"] == "interest_vector.v1"
    assert "export" in export.json()


@pytest.mark.asyncio
async def test_annotation_search_and_zip_export(app, client):
    await client.post("/api/auth/login", json={"display_name": "NoteUser"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 9001,
            "url": "https://example.com/zip",
            "title": "Zip Export Target",
            "published_at": datetime(2026, 7, 18, tzinfo=UTC),
        }
    )
    # Login user id from session
    me = await client.get("/api/auth/me")
    user_id = None
    # Prefer repository path via annotation create endpoint
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={"content": "remember the async runtime note", "selected_text": "async runtime"},
    )
    assert created.status_code == 201

    search = await client.get("/api/annotations/search", params={"q": "async"})
    assert search.status_code == 200
    assert len(search.json()["items"]) >= 1
    assert "async" in search.json()["items"][0]["selected_text"].lower()

    # Project state then zip export
    await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True, "project": True},
    )
    zip_response = await client.get("/api/export/project", params={"format": "zip"})
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")
    assert zip_response.content[:2] == b"PK"
    del user_id
    del me
