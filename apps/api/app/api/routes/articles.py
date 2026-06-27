from fastapi import APIRouter, Depends, Path, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.api.deps import (
    ApiError,
    get_article_repository,
    get_job_repository,
    get_scoring_repository,
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
from app.db.repositories.scoring import ScoreRecord, ScoringStore


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


def score_public(score: ScoreRecord) -> dict[str, object]:
    return {
        "overall": score.base_score,
        "tier": score.recommendation_tier,
        "dimensions": score.dimension_scores,
        "dimension_reasons": score.dimension_reasons,
        "tags": score.tags,
        "reason": score.reason,
        "summary_zh": score.summary_zh,
        "summary_original": score.summary_original,
        "source_language": score.source_language,
        "confidence": score.confidence,
        "scored_at": score.scored_at.isoformat() if score.scored_at else None,
    }


def article_list_item_public(
    article: ArticleRecord,
    state: ArticleStateRecord,
    score: ScoreRecord | None = None,
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
        "score": score_public(score) if score is not None else None,
        "summary_zh": score.summary_zh if score is not None else "",
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
    score: ScoreRecord | None = None,
) -> dict[str, object]:
    item = article_list_item_public(article, state, score)
    item.update(
        {
            "content_html": article.content_html,
            "content_zh": article.content_zh,
            "content_zh_status": article.content_zh_status,
            "translated_at": article.translated_at.isoformat() if article.translated_at else None,
            "content_text": article.content_text,
            "content_source": article.content_source,
            "content_expired": False,
            "summary_original": score.summary_original if score is not None else None,
            "source_language": score.source_language if score is not None else None,
            "dimension_scores": score.dimension_scores if score is not None else {},
            "dimension_reasons": score.dimension_reasons if score is not None else {},
            "sources": [article_source_public(source) for source in sources],
        }
    )
    return item


@router.get("/articles")
async def list_articles(
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    limit: int = Query(default=50, ge=1, le=100),
    cursor: str | None = None,
) -> dict[str, object]:
    try:
        page = article_repository.list_articles(limit=limit, cursor=cursor)
    except (ValueError, KeyError):
        raise ApiError(400, "invalid_cursor", "Invalid cursor") from None

    scores = scoring_repository.active_scores_for_articles([article.id for article in page.items])

    return {
        "items": [
            article_list_item_public(
                article,
                article_repository.get_state(current_user.id, article.id),
                scores.get(article.id),
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
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    article = article_repository.get_article(article_id)
    if article is None:
        raise ApiError(404, "not_found", "Article not found")
    score = scoring_repository.active_scores_for_articles([article.id]).get(article.id)
    return article_detail_public(
        article,
        article_repository.get_state(current_user.id, article.id),
        article_repository.sources_for_article(article.id),
        score,
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


@router.post("/articles/{article_id}/translate")
def enqueue_translate_article_job(
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    job_repository: JobStore = Depends(get_job_repository),
) -> JSONResponse:
    article = article_repository.get_article(article_id)
    if article is None:
        raise ApiError(404, "not_found", "Article not found")
    if article.content_zh and article.content_zh_status == "succeeded":
        return JSONResponse(
            status_code=200,
            content={
                "status": "succeeded",
                "content_zh": article.content_zh,
                "translated_at": article.translated_at.isoformat() if article.translated_at else None,
                "job_id": None,
            },
        )

    article_repository.save_translation(
        article_id,
        content_zh=article.content_zh,
        status="queued",
        translated_at=article.translated_at,
    )
    job = job_repository.enqueue(
        "translate_article",
        {"article_id": article_id},
        dedupe_key=dedupe_key_for("translate_article", article_id),
        created_by=current_user.id,
    )
    return JSONResponse(
        status_code=202,
        content={"status": job.status, "content_zh": None, "translated_at": None, "job_id": job.id},
    )
