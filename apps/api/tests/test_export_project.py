from datetime import UTC, datetime
from uuid import UUID

import pytest

from app.domain.export_project import ExportArticle, build_project_export_json, build_project_export_markdown


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
            )
        ],
        generated_at=datetime(2026, 7, 18, 12, tzinfo=UTC),
    )
    assert "# AI Reader 立项导出" in body
    assert "Alpha" in body
    assert "88" in body
    assert "摘要 A" in body


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

    response = await client.get("/api/export/project", params={"format": "markdown"})
    assert response.status_code == 200
    assert "text/markdown" in response.headers.get("content-type", "")
    assert "立项导出" in response.text
    assert "Project piece" in response.text
