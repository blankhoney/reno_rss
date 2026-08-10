from collections import Counter
from datetime import UTC, datetime, timedelta
from threading import Barrier, Thread

import pytest


def test_article_repository_dedupes_by_canonical_url_without_tracking_params():
    from app.db.repositories.articles import MemoryArticleRepository

    repository = MemoryArticleRepository()
    first = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post?utm_source=newsletter&id=1",
            "title": "Same article",
            "published_at": datetime(2026, 6, 23, 10, tzinfo=UTC),
        }
    )
    second = repository.upsert_from_source(
        {
            "feed_id": 2,
            "miniflux_entry_id": 202,
            "url": "https://example.com/post?id=1&utm_campaign=launch",
            "title": "Same article via another feed",
            "published_at": datetime(2026, 6, 23, 11, tzinfo=UTC),
        }
    )

    assert first.id == second.id
    assert second.canonical_url == "https://example.com/post?id=1"
    assert len(repository.sources_for_article(first.id)) == 2


def test_article_source_upsert_is_idempotent_for_feed_entry_pair():
    from app.db.repositories.articles import MemoryArticleRepository

    repository = MemoryArticleRepository()
    first = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Original title",
        }
    )
    second = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post?utm_medium=email",
            "title": "Updated source title",
        }
    )

    sources = repository.sources_for_article(first.id)

    assert second.id == first.id
    assert len(sources) == 1
    assert sources[0].source_title == "Updated source title"


@pytest.mark.asyncio
async def test_article_list_uses_published_at_id_keyset_order(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    now = datetime(2026, 6, 23, 12, tzinfo=UTC)
    oldest = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/oldest",
            "title": "Oldest",
            "published_at": now - timedelta(hours=2),
        }
    )
    middle = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 102,
            "url": "https://example.com/middle",
            "title": "Middle",
            "published_at": now - timedelta(hours=1),
        }
    )
    newest = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 103,
            "url": "https://example.com/newest",
            "title": "Newest",
            "published_at": now,
        }
    )

    first_page = await client.get("/api/articles?limit=2")
    second_page = await client.get(
        "/api/articles",
        params={"limit": 2, "cursor": first_page.json()["next_cursor"]},
    )

    assert first_page.status_code == 200
    assert [item["id"] for item in first_page.json()["items"]] == [newest.id, middle.id]
    assert first_page.json()["has_more"] is True
    assert second_page.status_code == 200
    assert [item["id"] for item in second_page.json()["items"]] == [oldest.id]
    assert second_page.json()["has_more"] is False


@pytest.mark.asyncio
async def test_article_score_sort_uses_full_corpus_composite_cursor(app, client):
    await client.post("/api/auth/login", json={"display_name": "Ranked Reader"})
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)
    created = []
    for index in range(105):
        created.append(
            app.state.article_repository.upsert_from_source(
                {
                    "feed_id": 1,
                    "miniflux_entry_id": 10_000 + index,
                    "url": f"https://example.com/ranked/{index}",
                    "title": f"Ranked {index}",
                    "published_at": now + timedelta(minutes=index),
                }
            )
        )

    # The highest score is deliberately the oldest article, outside the old
    # latest-100 candidate window.
    app.state.scoring_repository.create_score(
        article_id=created[0].id,
        base_score=99,
        is_active=True,
    )
    app.state.scoring_repository.create_score(
        article_id=created[50].id,
        base_score=98,
        is_active=True,
    )
    app.state.scoring_repository.create_score(
        article_id=created[-1].id,
        base_score=97,
        is_active=True,
    )

    first = await client.get("/api/articles", params={"sort": "score", "limit": 2})
    second = await client.get(
        "/api/articles",
        params={
            "sort": "score",
            "limit": 2,
            "cursor": first.json()["next_cursor"],
        },
    )

    assert first.status_code == 200
    assert [item["id"] for item in first.json()["items"]] == [
        created[0].id,
        created[50].id,
    ]
    assert first.json()["has_more"] is True
    assert first.json()["next_cursor"]
    assert second.status_code == 200
    assert second.json()["items"][0]["id"] == created[-1].id
    assert {item["id"] for item in first.json()["items"]}.isdisjoint(
        {item["id"] for item in second.json()["items"]}
    )


@pytest.mark.asyncio
async def test_article_dimension_sort_uses_dimension_value_and_validates_cursor(app, client):
    from dataclasses import replace

    await client.post("/api/auth/login", json={"display_name": "Dimension Reader"})
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)
    low = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 20_001,
            "url": "https://example.com/dimension/low",
            "title": "High base, low technical",
            "published_at": now,
        }
    )
    high = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 20_002,
            "url": "https://example.com/dimension/high",
            "title": "Low base, high technical",
            "published_at": now - timedelta(days=1),
        }
    )
    low_score = app.state.scoring_repository.create_score(
        article_id=low.id,
        base_score=95,
        is_active=True,
    )
    high_score = app.state.scoring_repository.create_score(
        article_id=high.id,
        base_score=60,
        is_active=True,
    )
    app.state.scoring_repository._scores[low_score.id] = replace(
        low_score,
        dimension_scores={"topic_relevance": 10},
    )
    app.state.scoring_repository._scores[high_score.id] = replace(
        high_score,
        dimension_scores={"topic_relevance": 100},
    )

    ranked = await client.get(
        "/api/articles",
        params={"module": "technical", "limit": 1},
    )
    wrong_cursor = await client.get(
        "/api/articles",
        params={"sort": "score", "limit": 1, "cursor": ranked.json()["next_cursor"]},
    )

    assert ranked.status_code == 200
    assert ranked.json()["items"][0]["id"] == high.id
    assert ranked.json()["next_cursor"]
    assert wrong_cursor.status_code == 400
    assert wrong_cursor.json()["error"]["code"] == "invalid_cursor"


@pytest.mark.asyncio
async def test_article_list_module_filters_saved_and_project_server_side(app, client):
    from uuid import UUID

    login = await client.post("/api/auth/login", json={"display_name": "Queue User"})
    user_id = UUID(login.json()["user"]["id"])
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)
    plain = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 201,
            "url": "https://example.com/plain",
            "title": "Plain",
            "published_at": now - timedelta(hours=3),
        }
    )
    saved = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 202,
            "url": "https://example.com/saved",
            "title": "Saved",
            "published_at": now - timedelta(hours=2),
        }
    )
    project = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 203,
            "url": "https://example.com/project",
            "title": "Project",
            "published_at": now - timedelta(hours=1),
        }
    )
    app.state.article_repository.upsert_state(user_id, plain.id, status="read")
    app.state.article_repository.upsert_state(user_id, saved.id, saved=True)
    app.state.article_repository.upsert_state(user_id, project.id, saved=True, project=True)

    starred = await client.get("/api/articles", params={"module": "starred", "limit": 20})
    projects = await client.get("/api/articles", params={"module": "project", "limit": 20})
    read = await client.get("/api/articles", params={"module": "read", "limit": 20})
    bad = await client.get("/api/articles", params={"module": "nope", "limit": 20})
    dimension = await client.get("/api/articles", params={"module": "technical", "limit": 20})

    assert starred.status_code == 200
    assert {item["id"] for item in starred.json()["items"]} == {saved.id, project.id}
    assert projects.status_code == 200
    assert [item["id"] for item in projects.json()["items"]] == [project.id]
    assert read.status_code == 200
    assert [item["id"] for item in read.json()["items"]] == [plain.id]
    assert bad.status_code == 400
    assert bad.json()["error"]["code"] == "invalid_module"
    assert dimension.status_code == 200
    assert {item["id"] for item in dimension.json()["items"]} >= {plain.id, saved.id, project.id}


def test_normalize_list_module_and_state_matches():
    from app.db.repositories.articles import (
        ArticleStateRecord,
        normalize_list_module,
        state_matches_module,
    )

    assert normalize_list_module(None) == "all"
    assert normalize_list_module("technical") == "all"
    assert normalize_list_module("starred") == "starred"
    try:
        normalize_list_module("bogus")
        raise AssertionError("expected ValueError")
    except ValueError:
        pass

    saved = ArticleStateRecord(status="unread", saved=True, project=False, read_progress=0.0)
    assert state_matches_module(saved, "starred") is True
    assert state_matches_module(saved, "project") is False


@pytest.mark.asyncio
async def test_article_list_q_filters_title_substring(app, client):
    await client.post("/api/auth/login", json={"display_name": "Searcher"})
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)
    hit = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 401,
            "url": "https://example.com/rust-async",
            "title": "Rust async runtime notes",
            "published_at": now,
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 402,
            "url": "https://example.com/other",
            "title": "Unrelated marketing post",
            "published_at": now - timedelta(hours=1),
        }
    )

    response = await client.get("/api/articles", params={"q": "rust async", "limit": 20})
    assert response.status_code == 200
    ids = [item["id"] for item in response.json()["items"]]
    assert ids == [hit.id]


@pytest.mark.asyncio
async def test_article_annotations_are_private_to_current_user(app, client):
    await client.post("/api/auth/login", json={"display_name": "Annotator"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 301,
            "url": "https://example.com/annotated",
            "title": "Annotated",
            "content_html": "<p>Body</p>",
        }
    )

    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "Body",
        "prefix": "",
        "suffix": "",
        "start": 0,
        "end": 4,
    }
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "content": "关键判断",
            "selected_text": "Body",
            "type": "annotation",
            "anchor": anchor,
        },
    )
    listed = await client.get(f"/api/articles/{article.id}/annotations")
    missing = await client.post(
        "/api/articles/99999/annotations",
        json={"content": "ghost"},
    )

    assert created.status_code == 201
    assert created.json()["annotation"]["content"] == "关键判断"
    assert created.json()["annotation"]["selected_text"] == "Body"
    assert created.json()["annotation"]["anchor"] == anchor
    assert listed.status_code == 200
    assert len(listed.json()["items"]) == 1
    assert listed.json()["items"][0]["id"] == created.json()["annotation"]["id"]
    assert listed.json()["items"][0]["anchor"] == anchor
    assert missing.status_code == 404


@pytest.mark.asyncio
async def test_annotation_edit_and_soft_delete_preserve_anchor_and_visibility(app, client):
    owner, owner_token, _ = app.state.auth_store.create_user("Annotation Owner")
    _, other_token, _ = app.state.auth_store.create_user("Other Annotation User")
    from app.core.security import SESSION_COOKIE_NAME

    client.cookies.set(SESSION_COOKIE_NAME, owner_token)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 304,
            "url": "https://example.com/annotation-lifecycle",
            "title": "Annotation lifecycle",
            "content_text": "quoted body",
        }
    )
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "quoted",
        "prefix": "",
        "suffix": " body",
        "start": 0,
        "end": 6,
    }
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "content": "old body",
            "selected_text": "quoted",
            "type": "comment",
            "color": "yellow",
            "tags": ["old"],
            "anchor": anchor,
        },
    )
    assert created.status_code == 201
    annotation_id = created.json()["annotation"]["id"]

    updated = await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "  new body  ", "color": "BLUE", "tags": ["AI", "ai", "research"]},
    )
    assert updated.status_code == 200
    updated_annotation = updated.json()["annotation"]
    assert updated_annotation["content"] == "new body"
    assert updated_annotation["color"] == "blue"
    assert updated_annotation["tags"] == ["AI", "research"]
    assert updated_annotation["selected_text"] == "quoted"
    assert updated_annotation["type"] == "comment"
    assert updated_annotation["anchor"] == anchor
    assert updated_annotation["updated_at"] is not None

    cleared = await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "body only", "color": None, "tags": []},
    )
    assert cleared.status_code == 200
    cleared_annotation = cleared.json()["annotation"]
    assert cleared_annotation["content"] == "body only"
    assert cleared_annotation["color"] is None
    assert cleared_annotation["tags"] == []
    assert cleared_annotation["selected_text"] == "quoted"
    assert cleared_annotation["type"] == "comment"
    assert cleared_annotation["anchor"] == anchor

    new_search = await client.get("/api/annotations/search", params={"q": "body only"})
    old_search = await client.get("/api/annotations/search", params={"q": "old body"})
    assert [item["id"] for item in new_search.json()["items"]] == [annotation_id]
    assert old_search.json()["items"] == []
    selected_search = await client.get("/api/annotations/search", params={"q": "QUOTED"})
    assert [item["id"] for item in selected_search.json()["items"]] == [annotation_id]

    from app.db.repositories.articles import AnnotationDeleteResult

    deleted = await client.delete(f"/api/annotations/{annotation_id}")
    assert deleted.status_code == 200
    assert deleted.json() == {"deleted": True, "id": annotation_id}
    stored = app.state.article_repository._annotations[annotation_id]
    assert stored.deleted_at is not None
    assert stored.deleted_at == stored.updated_at
    assert stored.deleted_by == owner.id
    assert stored.delete_reason == "user_request"
    original_audit = (
        stored.deleted_at,
        stored.updated_at,
        stored.deleted_by,
        stored.delete_reason,
    )
    assert app.state.article_repository.get_annotation(owner.id, annotation_id) is None
    assert (
        app.state.article_repository.soft_delete_annotation(owner.id, annotation_id)
        is AnnotationDeleteResult.ALREADY_DELETED
    )
    repeated = app.state.article_repository._annotations[annotation_id]
    assert (
        repeated.deleted_at,
        repeated.updated_at,
        repeated.deleted_by,
        repeated.delete_reason,
    ) == original_audit

    assert (await client.get(f"/api/articles/{article.id}/annotations")).json()["items"] == []
    assert (await client.get("/api/annotations/search", params={"q": "new body"})).json()["items"] == []
    assert (await client.get("/api/annotations/review")).json()["items"] == []
    assert (await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "again", "color": None, "tags": []},
    )).status_code == 404
    retried_delete = await client.delete(f"/api/annotations/{annotation_id}")
    assert retried_delete.status_code == 200
    assert retried_delete.json() == deleted.json()
    assert (await client.post(
        f"/api/annotations/{annotation_id}/review",
        json={"remembered": True},
    )).status_code == 404

    client.cookies.set(SESSION_COOKIE_NAME, other_token)
    assert (await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "other", "color": None, "tags": []},
    )).status_code == 404
    assert (await client.delete(f"/api/annotations/{annotation_id}")).status_code == 404
    assert (await client.post(
        f"/api/annotations/{annotation_id}/review",
        json={"remembered": True},
    )).status_code == 404
    assert (await client.get(f"/api/articles/{article.id}/annotations")).json()["items"] == []
    assert (await client.get("/api/annotations/search", params={"q": "new body"})).json()["items"] == []
    assert (await client.get("/api/annotations/review")).json()["items"] == []


def test_annotation_delete_openapi_declares_typed_success_and_not_found(app):
    operation = app.openapi()["paths"]["/api/annotations/{annotation_id}"]["delete"]
    assert operation["responses"]["200"]["content"]["application/json"]["schema"] == {
        "$ref": "#/components/schemas/AnnotationDeleteResponse"
    }
    assert operation["responses"]["404"]["description"] == "Annotation not found"
    schema = app.openapi()["components"]["schemas"]["AnnotationDeleteResponse"]
    assert schema["required"] == ["id"]
    assert schema["properties"]["deleted"]["const"] is True
    assert schema["properties"]["id"]["type"] == "integer"


def test_memory_annotation_delete_is_atomic_and_typed():
    from app.db.repositories.articles import AnnotationDeleteResult, MemoryArticleRepository
    from uuid import uuid4

    repository = MemoryArticleRepository()
    owner_id = uuid4()
    article = repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 9001,
            "url": "https://example.com/memory-delete-race",
            "title": "Memory delete race",
        }
    )
    annotation = repository.create_annotation(owner_id, article.id, content="race")
    assert annotation is not None
    barrier = Barrier(2)
    results: list[AnnotationDeleteResult] = []

    def delete() -> None:
        barrier.wait()
        results.append(repository.soft_delete_annotation(owner_id, annotation.id))

    threads = [Thread(target=delete), Thread(target=delete)]
    for thread in threads:
        thread.start()
    for thread in threads:
        thread.join(timeout=5)
        assert not thread.is_alive()

    assert Counter(results) == Counter(
        [AnnotationDeleteResult.DELETED, AnnotationDeleteResult.ALREADY_DELETED]
    )
    tombstone = repository._annotations[annotation.id]
    assert tombstone.deleted_at is not None
    assert tombstone.deleted_at == tombstone.updated_at
    assert tombstone.deleted_by == owner_id
    assert tombstone.delete_reason == "user_request"
    assert repository.list_annotations(owner_id, article.id) == []


@pytest.mark.asyncio
async def test_annotation_delete_missing_and_unknown_results_fail_closed(app, client, monkeypatch):
    from app.db.repositories.articles import AnnotationDeleteResult

    await client.post("/api/auth/login", json={"display_name": "Delete Result User"})
    owner, _, _ = app.state.auth_store.create_user("Delete Result Owner")
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 9003,
            "url": "https://example.com/delete-result-boundary",
            "title": "Delete result boundary",
        }
    )
    annotation = app.state.article_repository.create_annotation(owner.id, article.id, content="owner")
    assert annotation is not None

    missing = await client.delete("/api/annotations/999999")
    non_owner = await client.delete(f"/api/annotations/{annotation.id}")
    assert missing.status_code == non_owner.status_code == 404
    assert missing.json() == non_owner.json()
    assert missing.json()["error"] == {
        "code": "not_found",
        "message": "Annotation not found",
        "details": {},
    }
    assert app.state.article_repository.get_annotation(owner.id, annotation.id) is not None
    assert bool(AnnotationDeleteResult.NOT_FOUND_OR_NOT_OWNER) is True

    invalid_results = (
        "deleted",
        "already_deleted",
        "not_found_or_not_owner",
        "future_delete_result",
    )
    for invalid_result in invalid_results:
        monkeypatch.setattr(
            app.state.article_repository,
            "soft_delete_annotation",
            lambda *_args, _result=invalid_result, **_kwargs: _result,
        )
        with pytest.raises(
            AssertionError,
            match="soft_delete_annotation must return AnnotationDeleteResult",
        ):
            await client.delete("/api/annotations/999999")


@pytest.mark.asyncio
async def test_annotation_delete_admin_has_no_owner_override(app, client):
    from app.core.security import SESSION_COOKIE_NAME

    owner, owner_token, _ = app.state.auth_store.create_user("Delete Owner")
    _, admin_token, _ = app.state.auth_store.create_user("Delete Admin", role="admin")
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 9002,
            "url": "https://example.com/admin-delete-boundary",
            "title": "Admin delete boundary",
        }
    )
    owner_annotation = app.state.article_repository.create_annotation(owner.id, article.id, content="owner")
    assert owner_annotation is not None

    client.cookies.set(SESSION_COOKIE_NAME, admin_token)
    assert (await client.delete(f"/api/annotations/{owner_annotation.id}")).status_code == 404
    assert app.state.article_repository.get_annotation(owner.id, owner_annotation.id) is not None

    client.cookies.set(SESSION_COOKIE_NAME, owner_token)
    assert (await client.delete(f"/api/annotations/{owner_annotation.id}")).status_code == 200

    client.cookies.set(SESSION_COOKIE_NAME, admin_token)
    assert (await client.delete(f"/api/annotations/{owner_annotation.id}")).status_code == 404
    admin = app.state.auth_store.get_user_by_session(admin_token)
    assert admin is not None
    admin_annotation = app.state.article_repository.create_annotation(admin.id, article.id, content="admin")
    assert admin_annotation is not None
    first = await client.delete(f"/api/annotations/{admin_annotation.id}")
    second = await client.delete(f"/api/annotations/{admin_annotation.id}")
    assert first.status_code == second.status_code == 200
    assert first.json() == second.json() == {"deleted": True, "id": admin_annotation.id}


@pytest.mark.asyncio
async def test_visible_annotation_owner_isolation_preserves_owner_state(app, client):
    owner, owner_token, _ = app.state.auth_store.create_user("Visible Annotation Owner")
    _, other_token, _ = app.state.auth_store.create_user("Visible Annotation Other")
    from app.core.security import SESSION_COOKIE_NAME

    client.cookies.set(SESSION_COOKIE_NAME, owner_token)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 307,
            "url": "https://example.com/visible-owner-annotation",
            "title": "Visible owner annotation",
            "content_text": "owneronly quote body",
        }
    )
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "owneronly quote",
        "prefix": "",
        "suffix": " body",
        "start": 0,
        "end": 15,
    }
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "content": "owneronly private note",
            "selected_text": "owneronly quote",
            "type": "comment",
            "color": "purple",
            "tags": ["owneronly"],
            "anchor": anchor,
        },
    )
    assert created.status_code == 201
    annotation_id = created.json()["annotation"]["id"]

    owner_list_before = await client.get(f"/api/articles/{article.id}/annotations")
    owner_review_before = await client.get("/api/annotations/review")
    owner_interest_before = await client.get("/api/me/interest")
    assert owner_list_before.status_code == 200
    assert owner_review_before.status_code == 200
    assert owner_interest_before.status_code == 200
    assert [item["id"] for item in owner_list_before.json()["items"]] == [annotation_id]
    assert [item["id"] for item in owner_review_before.json()["items"]] == [annotation_id]
    assert owner_interest_before.json()["annotation_count"] == 1

    client.cookies.set(SESSION_COOKIE_NAME, other_token)
    other_update = await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "other must not write", "color": "blue", "tags": ["other"]},
    )
    other_delete = await client.delete(f"/api/annotations/{annotation_id}")
    other_review = await client.post(
        f"/api/annotations/{annotation_id}/review",
        json={"remembered": True},
    )
    other_list = await client.get(f"/api/articles/{article.id}/annotations")
    other_search = await client.get("/api/annotations/search", params={"q": "owneronly"})
    other_review_queue = await client.get("/api/annotations/review")
    other_interest = await client.get("/api/me/interest")

    assert other_update.status_code == 404
    assert other_delete.status_code == 404
    assert other_review.status_code == 404
    assert other_list.status_code == 200
    assert other_list.json()["items"] == []
    assert other_search.status_code == 200
    assert other_search.json()["items"] == []
    assert other_review_queue.status_code == 200
    assert other_review_queue.json()["items"] == []
    assert other_interest.status_code == 200
    assert other_interest.json()["annotation_count"] == 0
    assert all(item["term"] not in {"owneronly", "private", "note"} for item in other_interest.json()["keywords"])

    client.cookies.set(SESSION_COOKIE_NAME, owner_token)
    owner_list_after = await client.get(f"/api/articles/{article.id}/annotations")
    owner_review_after = await client.get("/api/annotations/review")
    owner_interest_after = await client.get("/api/me/interest")

    assert owner_list_after.json() == owner_list_before.json()
    assert owner_review_after.json() == owner_review_before.json()
    before_interest = {key: value for key, value in owner_interest_before.json().items() if key != "generated_at"}
    after_interest = {key: value for key, value in owner_interest_after.json().items() if key != "generated_at"}
    assert after_interest == before_interest
    stored = app.state.article_repository.get_annotation(owner.id, annotation_id)
    assert stored is not None
    assert stored.review_count == 0


@pytest.mark.asyncio
async def test_annotation_search_uses_decoded_body_not_anchor_meta(app, client):
    await client.post("/api/auth/login", json={"display_name": "Search Meta User"})
    _, other_token, _ = app.state.auth_store.create_user("Other Search Meta User")
    from app.core.security import SESSION_COOKIE_NAME

    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 306,
            "url": "https://example.com/annotation-search-meta",
            "title": "Annotation search meta",
        }
    )
    anchor = {
        "kind": "text-quote",
        "version": 1,
        "exact": "old body",
        "prefix": "",
        "suffix": "",
        "start": 0,
        "end": 8,
    }
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={"content": "old body", "anchor": anchor},
    )
    assert created.status_code == 201
    annotation_id = created.json()["annotation"]["id"]

    updated = await client.put(
        f"/api/annotations/{annotation_id}",
        json={"content": "new body", "color": "blue", "tags": []},
    )
    assert updated.status_code == 200

    assert (await client.get("/api/annotations/search", params={"q": "old body"})).json()["items"] == []
    current = await client.get("/api/annotations/search", params={"q": "new body"})
    assert [item["id"] for item in current.json()["items"]] == [annotation_id]
    current_upper = await client.get("/api/annotations/search", params={"q": "NEW BODY"})
    assert [item["id"] for item in current_upper.json()["items"]] == [annotation_id]

    deleted = await client.delete(f"/api/annotations/{annotation_id}")
    assert deleted.status_code == 200
    assert (await client.get("/api/annotations/search", params={"q": "new body"})).json()["items"] == []

    client.cookies.set(SESSION_COOKIE_NAME, other_token)
    assert (await client.get("/api/annotations/search", params={"q": "old body"})).json()["items"] == []
    assert (await client.get("/api/annotations/search", params={"q": "new body"})).json()["items"] == []


@pytest.mark.asyncio
async def test_annotation_write_boundary_returns_401_and_403(app, client):
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 305,
            "url": "https://example.com/annotation-boundary",
            "title": "Annotation boundary",
        }
    )
    unauthenticated = await client.put(
        "/api/annotations/1",
        json={"content": "no session", "color": None, "tags": []},
    )
    assert unauthenticated.status_code == 401

    _, token, _ = app.state.auth_store.create_user("Boundary User")
    from app.core.security import SESSION_COOKIE_NAME

    client.cookies.set(SESSION_COOKIE_NAME, token)
    client.headers["Origin"] = "https://evil.example"
    forbidden = await client.put(
        f"/api/annotations/{article.id}",
        json={"content": "bad origin", "color": None, "tags": []},
    )
    assert forbidden.status_code == 403
    client.headers.pop("Origin", None)


@pytest.mark.asyncio
async def test_article_annotation_rejects_invalid_text_quote_anchor(app, client):
    await client.post("/api/auth/login", json={"display_name": "Annotator"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 302,
            "url": "https://example.com/invalid-anchor",
            "title": "Invalid anchor",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "content": "note",
            "anchor": {
                "kind": "text-quote",
                "version": 1,
                "exact": "Body",
                "prefix": "",
                "suffix": "",
                "start": 4,
                "end": 4,
            },
        },
    )

    assert response.status_code == 422


@pytest.mark.asyncio
async def test_article_detail_returns_sources_and_content(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
            "content_text": "Full text",
            "content_html": "<p>Full text</p>",
            "content_source": "miniflux_feed",
            "content_quality": "full",
        }
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 200
    assert response.json()["id"] == article.id
    assert response.json()["content_text"] == "Full text"
    assert response.json()["content_zh"] is None
    assert response.json()["content_zh_status"] is None
    assert response.json()["sources"] == [
        {
            "feed_id": 1,
            "feed_title": None,
            "miniflux_entry_id": 101,
            "source_url": "https://example.com/post",
        }
    ]


@pytest.mark.asyncio
async def test_article_detail_returns_cached_translation(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    translated_at = datetime(2026, 6, 25, 1, tzinfo=UTC)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
            "content_html": "<p>Full text</p>",
        }
    )
    app.state.article_repository.save_translation(
        article.id,
        content_zh="<p>中文正文</p>",
        status="succeeded",
        translated_at=translated_at,
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 200
    assert response.json()["content_zh"] == "<p>中文正文</p>"
    assert response.json()["content_zh_status"] == "succeeded"
    assert response.json()["translated_at"] == translated_at.isoformat()


@pytest.mark.asyncio
async def test_translate_article_returns_cached_translation(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    translated_at = datetime(2026, 6, 25, 1, tzinfo=UTC)
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    app.state.article_repository.save_translation(
        article.id,
        content_zh="<p>中文正文</p>",
        status="succeeded",
        translated_at=translated_at,
    )

    response = await client.post(f"/api/articles/{article.id}/translate")

    assert response.status_code == 200
    assert response.json() == {
        "status": "succeeded",
        "content_zh": "<p>中文正文</p>",
        "translated_at": translated_at.isoformat(),
        "job_id": None,
    }


@pytest.mark.asyncio
async def test_translate_article_enqueues_job_and_marks_translation_queued(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.post(f"/api/articles/{article.id}/translate")
    detail_response = await client.get(f"/api/articles/{article.id}")

    assert response.status_code == 202
    assert response.json()["status"] == "queued"
    assert isinstance(response.json()["job_id"], int)
    assert detail_response.json()["content_zh_status"] == "queued"


@pytest.mark.asyncio
async def test_translate_article_rolls_back_when_enqueue_fails(app, client, monkeypatch):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    before_job_ids = set(app.state.job_repository._jobs)

    def fail_enqueue(*_args, **_kwargs):
        raise RuntimeError("queue unavailable")

    monkeypatch.setattr(app.state.job_repository, "enqueue", fail_enqueue)

    with pytest.raises(RuntimeError, match="queue unavailable"):
        await client.post(f"/api/articles/{article.id}/translate")

    detail_response = await client.get(f"/api/articles/{article.id}")

    assert detail_response.json()["content_zh_status"] is None
    assert set(app.state.job_repository._jobs) == before_job_ids


@pytest.mark.asyncio
async def test_translate_article_missing_returns_typed_404_without_enqueue(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    before_job_ids = set(app.state.job_repository._jobs)

    response = await client.post("/api/articles/999999/translate")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"
    assert set(app.state.job_repository._jobs) == before_job_ids


@pytest.mark.asyncio
async def test_translate_article_dedupes_and_adds_second_watcher(app):
    from httpx import ASGITransport, AsyncClient

    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 102,
            "url": "https://example.com/translate-dedupe",
            "title": "Translate dedupe",
        }
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={"Referer": "https://test/"},
    ) as first_client:
        await first_client.post("/api/auth/login", json={"display_name": "First"})
        first = await first_client.post(f"/api/articles/{article.id}/translate")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={"Referer": "https://test/"},
    ) as second_client:
        await second_client.post("/api/auth/login", json={"display_name": "Second"})
        second = await second_client.post(f"/api/articles/{article.id}/translate")
        visible = await second_client.get(f"/api/jobs/{second.json()['job_id']}")

    assert first.status_code == 202
    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert second.json()["status"] == "queued"
    assert visible.status_code == 200


@pytest.mark.asyncio
async def test_translate_article_reuses_running_job_without_downgrade(app):
    from httpx import ASGITransport, AsyncClient

    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 103,
            "url": "https://example.com/translate-running",
            "title": "Translate running",
        }
    )
    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={"Referer": "https://test/"},
    ) as first_client:
        await first_client.post("/api/auth/login", json={"display_name": "First"})
        first = await first_client.post(f"/api/articles/{article.id}/translate")

    claimed = app.state.job_repository.claim_next("translation-worker")
    assert claimed is not None
    assert claimed.id == first.json()["job_id"]
    assert claimed.status == "running"

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
        headers={"Referer": "https://test/"},
    ) as second_client:
        await second_client.post("/api/auth/login", json={"display_name": "Second"})
        second = await second_client.post(f"/api/articles/{article.id}/translate")
        visible = await second_client.get(f"/api/jobs/{second.json()['job_id']}")
        detail = await second_client.get(f"/api/articles/{article.id}")

    assert second.status_code == 202
    assert second.json()["job_id"] == claimed.id
    assert second.json()["status"] == "running"
    assert visible.status_code == 200
    assert visible.json()["status"] == "running"
    assert detail.json()["content_zh_status"] == "running"


@pytest.mark.asyncio
async def test_articles_require_auth_when_anonymous_demo_disabled(app, client):
    # Production default: no session cookie and the flag off → fail closed.
    assert app.state.anonymous_demo_enabled is False
    response = await client.get("/api/articles")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_article_stats_require_auth_when_anonymous_demo_disabled(app, client):
    assert app.state.anonymous_demo_enabled is False
    response = await client.get("/api/articles/stats")
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_anonymous_demo_serves_articles_but_not_admin(app, client):
    # Staging public demo: anonymous requests resolve to a shared demo user.
    app.state.anonymous_demo_enabled = True
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    articles_response = await client.get("/api/articles")
    admin_response = await client.get("/api/admin/users")

    assert articles_response.status_code == 200
    assert len(articles_response.json()["items"]) == 1
    # Demo user is role=user, so admin endpoints stay protected.
    assert admin_response.status_code == 403


@pytest.mark.asyncio
async def test_article_stats_count_total_scored_and_unscored(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    first = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/first",
            "title": "First",
        }
    )
    second = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 102,
            "url": "https://example.com/second",
            "title": "Second",
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 103,
            "url": "https://example.com/third",
            "title": "Third",
        }
    )
    app.state.scoring_repository.create_score(
        article_id=first.id,
        base_score=82,
        is_active=True,
    )
    app.state.scoring_repository.create_score(
        article_id=second.id,
        base_score=70,
        is_active=False,
    )

    response = await client.get("/api/articles/stats")

    assert response.status_code == 200
    assert response.json() == {"total": 3, "scored": 1, "unscored": 2}


@pytest.mark.asyncio
async def test_article_list_and_detail_surface_active_score(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    app.state.scoring_repository.create_score(
        article_id=article.id,
        base_score=82,
        is_active=True,
    )

    list_response = await client.get("/api/articles")
    detail_response = await client.get(f"/api/articles/{article.id}")

    item = list_response.json()["items"][0]
    assert item["score"]["overall"] == 82
    assert item["score"]["tier"] == "read"
    assert detail_response.json()["score"]["overall"] == 82


@pytest.mark.asyncio
async def test_article_score_is_null_without_active_score(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.get(f"/api/articles/{article.id}")

    assert response.json()["score"] is None


@pytest.mark.asyncio
async def test_article_list_and_detail_surface_real_feed_metadata(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "feed_title": "Primary Feed",
            "category_id": 10,
            "category_title": "Research",
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 2,
            "feed_title": "Syndicated Feed",
            "category_id": 20,
            "category_title": "Mirror",
            "miniflux_entry_id": 201,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    list_response = await client.get("/api/articles")
    detail_response = await client.get(f"/api/articles/{article.id}")

    item = list_response.json()["items"][0]
    detail = detail_response.json()
    assert item["feed"] == {"id": 1, "title": "Primary Feed"}
    assert item["category"] == {"id": 10, "title": "Research"}
    assert item["source_count"] == 2
    assert detail["source_count"] == 2
    assert "content_expired" not in detail
    assert [source["feed_title"] for source in detail["sources"]] == [
        "Primary Feed",
        "Syndicated Feed",
    ]


@pytest.mark.asyncio
async def test_article_state_upserts_for_current_user(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/state",
        json={"status": "read", "saved": True, "read_progress": 0.75},
    )

    assert response.status_code == 200
    assert response.json()["state"] == {
        "status": "read",
        "saved": True,
        "project": False,
        "read_progress": 0.75,
    }


@pytest.mark.asyncio
async def test_read_later_lists_only_unread_partial_progress_articles(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    sources = [
        app.state.article_repository.upsert_from_source(
            {
                "feed_id": 1,
                "miniflux_entry_id": entry_id,
                "url": f"https://example.com/{entry_id}",
                "title": f"Article {entry_id}",
            }
        )
        for entry_id in (101, 102, 103, 104)
    ]
    await client.post(f"/api/articles/{sources[0].id}/state", json={"saved": True, "read_progress": 0})
    await client.post(f"/api/articles/{sources[1].id}/state", json={"read_progress": 0.4})
    await client.post(f"/api/articles/{sources[2].id}/state", json={"status": "read", "read_progress": 0.4})
    await client.post(f"/api/articles/{sources[3].id}/state", json={"read_progress": 1})

    response = await client.get("/api/articles?module=read-later")

    assert response.status_code == 200
    assert [item["id"] for item in response.json()["items"]] == [sources[1].id]


@pytest.mark.asyncio
async def test_article_project_state_requires_saved_candidate(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    rejected = await client.post(
        f"/api/articles/{article.id}/state",
        json={"project": True},
    )
    saved = await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True},
    )
    projected = await client.post(
        f"/api/articles/{article.id}/state",
        json={"project": True},
    )
    removed_from_candidates = await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": False},
    )

    assert rejected.status_code == 409
    assert rejected.json()["error"]["code"] == "article_not_candidate"
    assert saved.status_code == 200
    assert saved.json()["state"]["saved"] is True
    assert saved.json()["state"]["project"] is False
    assert projected.status_code == 200
    assert projected.json()["state"]["saved"] is True
    assert projected.json()["state"]["project"] is True
    assert removed_from_candidates.status_code == 200
    assert removed_from_candidates.json()["state"]["saved"] is False
    assert removed_from_candidates.json()["state"]["project"] is False


@pytest.mark.asyncio
async def test_article_project_state_can_be_set_with_saved_in_same_request(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.post(
        f"/api/articles/{article.id}/state",
        json={"saved": True, "project": True},
    )

    assert response.status_code == 200
    assert response.json()["state"]["saved"] is True
    assert response.json()["state"]["project"] is True


@pytest.mark.asyncio
async def test_article_feedback_upserts_and_surfaces_on_read_paths(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    first_response = await client.put(
        f"/api/articles/{article.id}/feedback",
        json={"user_score": 95, "feedback_type": "underrated", "reason": "More useful than scored."},
    )
    second_response = await client.put(
        f"/api/articles/{article.id}/feedback",
        json={"user_score": 30, "feedback_type": "overrated", "reason": "Too shallow."},
    )
    list_response = await client.get("/api/articles")
    detail_response = await client.get(f"/api/articles/{article.id}")

    assert first_response.status_code == 200
    assert first_response.json()["feedback"]["feedback_type"] == "underrated"
    assert second_response.status_code == 200
    assert second_response.json()["feedback"]["user_score"] == 30
    assert second_response.json()["feedback"]["feedback_type"] == "overrated"
    assert second_response.json()["feedback"]["reason"] == "Too shallow."
    assert list_response.json()["items"][0]["my_feedback"]["feedback_type"] == "overrated"
    assert detail_response.json()["my_feedback"]["user_score"] == 30


@pytest.mark.asyncio
async def test_article_feedback_validates_score_and_type(app, client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    bad_score = await client.put(
        f"/api/articles/{article.id}/feedback",
        json={"user_score": 101, "feedback_type": "underrated"},
    )
    bad_type = await client.put(
        f"/api/articles/{article.id}/feedback",
        json={"user_score": 50, "feedback_type": "not_a_feedback_type"},
    )

    assert bad_score.status_code == 422
    assert bad_type.status_code == 422


@pytest.mark.asyncio
async def test_article_feedback_returns_not_found_for_missing_article(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.put(
        "/api/articles/999/feedback",
        json={"user_score": 50, "feedback_type": "other"},
    )

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


@pytest.mark.asyncio
async def test_anonymous_demo_can_submit_article_feedback(app, client):
    app.state.anonymous_demo_enabled = True
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Article",
        }
    )

    response = await client.put(
        f"/api/articles/{article.id}/feedback",
        json={"user_score": 80, "feedback_type": "other", "reason": "demo feedback"},
    )

    assert response.status_code == 200
    assert response.json()["feedback"]["reason"] == "demo feedback"


@pytest.mark.asyncio
async def test_article_list_q_matches_content_text_body(app, client):
    await client.post("/api/auth/login", json={"display_name": "Searcher"})
    now = datetime(2026, 7, 18, 12, tzinfo=UTC)
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 701,
            "url": "https://example.com/title-only",
            "title": "Completely different headline",
            "published_at": now,
            "content_text": "Unique body token zephyr-quantum appears here only.",
        }
    )
    app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 702,
            "url": "https://example.com/other",
            "title": "Other",
            "published_at": now,
            "content_text": "No match here",
        }
    )

    response = await client.get("/api/articles", params={"q": "zephyr-quantum", "limit": 10})

    assert response.status_code == 200
    ids_titles = [(item["id"], item["title"]) for item in response.json()["items"]]
    assert len(ids_titles) == 1
    assert ids_titles[0][1] == "Completely different headline"


@pytest.mark.asyncio
async def test_annotation_review_queue_is_private_and_due_first(app, client):
    await client.post("/api/auth/login", json={"display_name": "Reviewer"})
    first = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 901,
            "url": "https://example.com/a1",
            "title": "Article One",
            "content_text": "body one",
        }
    )
    second = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 902,
            "url": "https://example.com/a2",
            "title": "Article Two",
            "content_text": "body two",
        }
    )
    older = await client.post(
        f"/api/articles/{first.id}/annotations",
        json={"content": "older note", "selected_text": "old quote"},
    )
    newer = await client.post(
        f"/api/articles/{second.id}/annotations",
        json={"content": "newer note", "selected_text": "new quote"},
    )
    assert older.status_code == 201
    assert newer.status_code == 201
    older_id = older.json()["annotation"]["id"]
    newer_id = newer.json()["annotation"]["id"]
    assert older.json()["annotation"]["interval_days"] == 1
    assert older.json()["annotation"]["next_review_at"] is not None

    response = await client.get("/api/annotations/review", params={"limit": 10})

    assert response.status_code == 200
    items = response.json()["items"]
    assert len(items) >= 2
    # Due queue is ordered by next_review_at ascending (oldest due first).
    assert items[0]["id"] == older_id
    assert items[0]["content"] == "older note"
    assert items[0]["article_title"] == "Article One"
    assert items[1]["id"] == newer_id
    assert items[1]["content"] == "newer note"
    assert "interval_days" in items[0]
    assert "next_review_at" in items[0]


@pytest.mark.asyncio
async def test_annotation_review_advances_interval_and_hides_until_due(app, client):
    await client.post("/api/auth/login", json={"display_name": "Reviewer"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 903,
            "url": "https://example.com/a3",
            "title": "Article Three",
            "content_text": "body three",
        }
    )
    created = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={"content": "to review", "selected_text": "quote three"},
    )
    annotation_id = created.json()["annotation"]["id"]

    remembered = await client.post(
        f"/api/annotations/{annotation_id}/review",
        json={"remembered": True},
    )
    assert remembered.status_code == 200
    body = remembered.json()["annotation"]
    assert body["interval_days"] == 3
    assert body["review_count"] == 1
    assert body["next_review_at"] is not None

    queue = await client.get("/api/annotations/review", params={"limit": 50})
    assert queue.status_code == 200
    assert all(item["id"] != annotation_id for item in queue.json()["items"])

    forgot = await client.post(
        f"/api/annotations/{annotation_id}/review",
        json={"remembered": False},
    )
    assert forgot.status_code == 200
    # Forgotten items reset to 1-day interval but are scheduled into the future.
    assert forgot.json()["annotation"]["interval_days"] == 1
    assert forgot.json()["annotation"]["review_count"] == 2
