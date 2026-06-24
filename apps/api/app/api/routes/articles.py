from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    ApiError,
    get_article_repository,
    get_job_repository,
    require_user,
)
from app.db.auth_store import UserRecord
from app.db.repositories.articles import (
    ArticleRecord,
    ArticleSourceRecord,
    ArticleStateRecord,
    ArticleStore,
)
from app.db.repositories.jobs import JobStore, dedupe_key_for


router = APIRouter(prefix="/api", tags=["articles"])


class ArticleStateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(read|unread|skipped)$")
    saved: bool | None = None
    read_progress: float | None = Field(default=None, ge=0, le=1)


def article_state_public(state: ArticleStateRecord) -> dict[str, object]:
    return {
        "status": state.status,
        "saved": state.saved,
        "read_progress": state.read_progress,
    }


def article_list_item_public(
    article: ArticleRecord,
    state: ArticleStateRecord,
) -> dict[str, object]:
    return {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "feed": {"id": article.primary_feed_id, "title": None}
        if article.primary_feed_id is not None
        else None,
        "source_count": 0,
        "category": None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "content_quality": article.content_quality,
        "score": None,
        "state": article_state_public(state),
        "my_feedback": None,
    }


def article_source_public(source: ArticleSourceRecord) -> dict[str, object]:
    return {
        "feed_id": source.feed_id,
        "feed_title": None,
        "miniflux_entry_id": source.miniflux_entry_id,
        "source_url": source.source_url,
    }


def article_detail_public(
    article: ArticleRecord,
    state: ArticleStateRecord,
    sources: list[ArticleSourceRecord],
) -> dict[str, object]:
    item = article_list_item_public(article, state)
    item.update(
        {
            "content_html": article.content_html,
            "content_text": article.content_text,
            "content_source": article.content_source,
            "content_expired": False,
            "summary_original": None,
            "source_language": None,
            "dimension_scores": {},
            "dimension_reasons": {},
            "sources": [article_source_public(source) for source in sources],
        }
    )
    return item


@router.get("/articles")
async def list_articles(
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, object]:
    try:
        page = article_repository.list_articles(limit=limit, cursor=cursor)
    except (ValueError, KeyError):
        raise ApiError(400, "invalid_cursor", "Invalid cursor") from None

    return {
        "items": [
            article_list_item_public(
                article,
                article_repository.get_state(current_user.id, article.id),
            )
            for article in page.items
        ],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


@router.get("/articles/{article_id}")
def get_article(
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    article = article_repository.get_article(article_id)
    if article is None:
        raise ApiError(404, "not_found", "Article not found")
    return article_detail_public(
        article,
        article_repository.get_state(current_user.id, article.id),
        article_repository.sources_for_article(article.id),
    )


@router.post("/articles/{article_id}/state")
def update_article_state(
    payload: ArticleStateRequest,
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    state = article_repository.upsert_state(
        current_user.id,
        article_id,
        status=payload.status,
        saved=payload.saved,
        read_progress=payload.read_progress,
    )
    if state is None:
        raise ApiError(404, "not_found", "Article not found")
    return {"state": article_state_public(state)}


@router.post("/articles/{article_id}/fetch-content")
def enqueue_fetch_content_job(
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    job = job_repository.enqueue(
        "fetch_article_content",
        {"article_id": article_id},
        dedupe_key=dedupe_key_for("fetch_article_content", article_id),
        created_by=current_user.id,
    )
    return JSONResponse(status_code=202, content={"job_id": job.id, "status": job.status})
