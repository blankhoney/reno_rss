from datetime import UTC, datetime
import io
import json
import zipfile

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
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 701,
            "url": "https://example.com/rust-reactor",
            "title": "Rust Reactor Architecture",
            "content_text": "Rust async runtime internals",
        }
    )
    projected = await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True, "project": True},
    )
    assert projected.status_code == 200

    got = await client.get("/api/me/interest")
    assert got.status_code == 200
    body = got.json()
    assert body["project_count"] == 1
    assert any(item["term"] == "rust" for item in body["keywords"])
    assert body["reset_at"] is None

    reset = await client.post("/api/me/interest/reset")
    assert reset.status_code == 200
    assert reset.json()["status"] == "ok"
    assert reset.json()["reset_at"] is not None

    after = await client.get("/api/me/interest")
    assert after.status_code == 200
    assert after.json()["reset_at"] is not None
    assert after.json()["keywords"] == []
    assert after.json()["project_count"] == 0

    # A post-reset interaction opts the project back into personalization.
    await client.post(f"/api/articles/{article.id}/state", json={"project": False})
    await client.post(f"/api/articles/{article.id}/state", json={"project": True})
    rebuilt = await client.get("/api/me/interest")
    assert rebuilt.json()["project_count"] == 1
    assert any(item["term"] == "rust" for item in rebuilt.json()["keywords"])

    export = await client.get("/api/me/interest/export")
    assert export.status_code == 200
    assert export.json()["format"] == "interest_vector.v1"
    assert "export" in export.json()


@pytest.mark.asyncio
async def test_interest_decodes_annotation_body_before_building_signals(app, client):
    await client.post("/api/auth/login", json={"display_name": "Interest Meta User"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 702,
            "url": "https://example.com/interest-meta",
            "title": "Interest meta article",
        }
    )
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "old body",
        "prefix": "anchor_only_token",
        "suffix": "meta_only_token",
        "start": 0,
        "end": 8,
    }
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "content": "new body",
            "selected_text": "kept quote",
            "color": "purple",
            "tags": ["meta_tag"],
            "anchor": anchor,
        },
    )
    assert created.status_code == 201

    profile = await client.get("/api/me/interest")
    assert profile.status_code == 200
    terms = {item["term"] for item in profile.json()["keywords"]}
    assert {"new", "body", "kept", "quote"}.issubset(terms)
    assert {"old", "anchor_only_token", "meta_only_token", "purple", "meta_tag"}.isdisjoint(terms)


def test_database_interest_reset_repository_is_shared_across_instances():
    from uuid import uuid4

    from sqlalchemy import create_engine

    from app.db.models import user_interest_resets
    from app.db.repositories.interest import DatabaseInterestResetRepository

    engine = create_engine("sqlite:///:memory:")
    user_interest_resets.create(engine)
    first = DatabaseInterestResetRepository(engine=engine)
    second = DatabaseInterestResetRepository(engine=engine)
    user_id = uuid4()
    reset_at = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)

    first.set_reset_at(user_id, reset_at)

    assert second.get_reset_at(user_id) == reset_at


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
    annotation_id = created.json()["annotation"]["id"]

    search = await client.get("/api/annotations/search", params={"q": "async"})
    assert search.status_code == 200
    assert len(search.json()["items"]) >= 1
    assert "async" in search.json()["items"][0]["selected_text"].lower()

    deleted = await client.delete(f"/api/annotations/{annotation_id}")
    assert deleted.status_code == 200
    assert (await client.get("/api/annotations/search", params={"q": "async"})).json()["items"] == []
    interest_after_delete = await client.get("/api/me/interest")
    assert interest_after_delete.status_code == 200
    assert interest_after_delete.json()["annotation_count"] == 0
    assert all(item["term"] != "async" for item in interest_after_delete.json()["keywords"])

    # Project state then zip export; the deleted annotation must not reappear.
    await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True, "project": True},
    )
    zip_response = await client.get("/api/export/project", params={"format": "zip"})
    assert zip_response.status_code == 200
    assert zip_response.headers["content-type"].startswith("application/zip")
    assert zip_response.content[:2] == b"PK"
    with zipfile.ZipFile(io.BytesIO(zip_response.content)) as archive:
        project_json = json.loads(archive.read("project.json"))
    assert project_json["items"][0]["annotations"] == []
    del user_id
    del me
