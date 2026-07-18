from datetime import UTC, datetime
from uuid import UUID, uuid4

import pytest

from app.domain.export_project import (
    ExportAnnotation,
    ExportArticle,
    build_project_export_json,
    build_project_export_markdown,
)


def test_build_project_export_markdown_includes_titles_and_scores():
    body = build_project_export_markdown(
        [
            ExportArticle(
                id=1,
                title="Alpha",
                url="https://example.com/a",
                summary_zh="摘要 A",
                score=88,
                tier="must_read",
                reason="dense",
                tags=["ai"],
                annotations=[
                    ExportAnnotation(
                        selected_text="Evidence quote",
                        note="My note",
                        color="yellow",
                        tags=["review"],
                        created_at="2026-07-18T11:00:00+00:00",
                    )
                ],
            )
        ],
        generated_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )
    assert "# AI Reader 立项导出" in body
    assert "Alpha" in body
    assert "88" in body
    assert "摘要 A" in body
    assert "Evidence quote" in body
    assert "My note" in body
    assert "review" in body


def test_build_project_export_json_shape():
    payload = build_project_export_json(
        [
            ExportArticle(
                id=2,
                title="Beta",
                url="https://example.com/b",
                summary_zh="",
                score=None,
                tier=None,
                reason="",
                tags=[],
            )
        ],
        generated_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )
    assert payload["count"] == 1
    assert payload["items"][0]["id"] == 2
    assert payload["items"][0]["title"] == "Beta"
    assert payload["items"][0]["annotations"] == []


@pytest.mark.asyncio
async def test_export_project_markdown_endpoint(app, client):
    login = await client.post("/api/auth/login", json={"display_name": "Exporter"})
    uid = UUID(login.json()["user"]["id"])
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 909,
            "url": "https://example.com/p",
            "title": "Project piece",
            "content_text": "body",
        }
    )
    app.state.article_repository.upsert_state(uid, article.id, saved=True, project=True)
    annotation = await client.post(
        f"/api/articles/{article.id}/annotations",
        json={
            "selected_text": "Portable evidence",
            "content": "Keep this reasoning",
            "color": "blue",
            "tags": ["portable"],
        },
    )
    assert annotation.status_code == 201
    app.state.article_repository.create_annotation(
        uuid4(),
        article.id,
        selected_text="Other user's private quote",
        content="must not export",
    )

    response = await client.get("/api/export/project", params={"format": "markdown"})
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    assert "立项导出" in response.text
    assert "Project piece" in response.text
    assert "Portable evidence" in response.text
    assert "Keep this reasoning" in response.text
    assert "portable" in response.text
    assert "Other user's private quote" not in response.text

    json_response = await client.get("/api/export/project", params={"format": "json"})
    exported = json_response.json()["items"][0]["annotations"][0]
    assert exported["selected_text"] == "Portable evidence"
    assert exported["note"] == "Keep this reasoning"
    assert exported["color"] == "blue"
    assert exported["tags"] == ["portable"]
