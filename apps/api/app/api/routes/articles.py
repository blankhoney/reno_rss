from typing import Literal

from fastapi import APIRouter, Depends, Path, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse, Response
from pydantic import BaseModel, Field, field_validator, model_validator

from app.api.deps import (
    ApiError,
    get_article_repository,
    get_job_repository,
    get_scoring_repository,
    require_user,
)
from app.domain.export_project import (
    ExportAnnotation,
    ExportArticle,
    build_project_export_json,
    build_project_export_markdown,
)
from app.domain.annotations_meta import decode_annotation_content
from app.db.auth_store import UserRecord
from app.db.repositories.articles import (
    AnnotationRecord,
    ArticleFeedbackRecord,
    ArticleRecord,
    ArticleSourceRecord,
    ArticleStateRecord,
    ArticleStore,
)
from app.db.repositories.jobs import JobStore, dedupe_key_for
from app.db.repositories.scoring import ScoreRecord, ScoringStore
from app.core.ratelimit import limiter, llm_rate_limit, write_rate_limit
from app.domain.ranking import FEEDBACK_BASE_ADJUSTMENTS


router = APIRouter(prefix="/api", tags=["articles"])
FEEDBACK_TYPES = tuple(FEEDBACK_BASE_ADJUSTMENTS.keys())


class ArticleStateRequest(BaseModel):
    status: str | None = Field(default=None, pattern="^(read|unread|skipped)$")
    saved: bool | None = None
    project: bool | None = None
    read_progress: float | None = Field(default=None, ge=0, le=1)


class ArticleFeedbackRequest(BaseModel):
    user_score: int = Field(ge=0, le=100)
    feedback_type: str = Field(json_schema_extra={"enum": list(FEEDBACK_TYPES)})
    reason: str = ""

    @field_validator("feedback_type")
    @classmethod
    def validate_feedback_type(cls, value: str) -> str:
        if value not in FEEDBACK_TYPES:
            allowed = ", ".join(FEEDBACK_TYPES)
            raise ValueError(f"feedback_type must be one of: {allowed}")
        return value


class ArticleAnnotationAnchor(BaseModel):
    kind: Literal["text-quote"]
    version: Literal[1]
    exact: str = Field(min_length=1, max_length=4000)
    prefix: str = Field(max_length=160)
    suffix: str = Field(max_length=160)
    start: int = Field(ge=0)
    end: int = Field(gt=0)

    @model_validator(mode="after")
    def validate_offsets(self) -> "ArticleAnnotationAnchor":
        if self.end <= self.start:
            raise ValueError("anchor end must be greater than start")
        return self


class ArticleAnnotationRequest(BaseModel):
    content: str = Field(min_length=1, max_length=4000)
    selected_text: str | None = Field(default=None, max_length=4000)
    type: str = Field(default="annotation", pattern="^(annotation|comment|review)$")
    color: str | None = Field(default=None, max_length=20)
    tags: list[str] | None = Field(default=None, max_length=12)
    anchor: ArticleAnnotationAnchor | None = None


class AnnotationReviewRequest(BaseModel):
    remembered: bool


def article_state_public(state: ArticleStateRecord) -> dict[str, object]:
    return {
        "status": state.status,
        "saved": state.saved,
        "project": state.project,
        "read_progress": state.read_progress,
    }


def article_feedback_public(feedback: ArticleFeedbackRecord) -> dict[str, object]:
    return {
        "user_score": feedback.user_score,
        "feedback_type": feedback.feedback_type,
        "reason": feedback.reason,
        "created_at": feedback.created_at.isoformat() if feedback.created_at else None,
        "updated_at": feedback.updated_at.isoformat() if feedback.updated_at else None,
    }


def annotation_public(annotation: AnnotationRecord) -> dict[str, object]:
    from app.domain.annotations_meta import decode_annotation_content

    meta = decode_annotation_content(annotation.content)
    return {
        "id": annotation.id,
        "article_id": annotation.article_id,
        "type": annotation.type,
        "selected_text": annotation.selected_text,
        "content": meta.body,
        "color": meta.color,
        "tags": list(meta.tags),
        "anchor": meta.anchor,
        "created_at": annotation.created_at.isoformat() if annotation.created_at else None,
        "updated_at": annotation.updated_at.isoformat() if annotation.updated_at else None,
        "next_review_at": (
            annotation.next_review_at.isoformat() if annotation.next_review_at else None
        ),
        "interval_days": annotation.interval_days,
        "review_count": annotation.review_count,
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
    feedback: ArticleFeedbackRecord | None = None,
    *,
    feed_hidden: bool | None = None,
    feed_quality_score: float | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "id": article.id,
        "title": article.title,
        "url": article.url,
        "feed": {"id": article.primary_feed_id, "title": article.feed_title}
        if article.primary_feed_id is not None
        else None,
        "source_count": article.source_count,
        "category": {"id": article.category_id, "title": article.category_title}
        if article.category_id is not None
        else None,
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "content_quality": article.content_quality,
        "score": score_public(score) if score is not None else None,
        "summary_zh": score.summary_zh if score is not None else "",
        "state": article_state_public(state),
        "my_feedback": article_feedback_public(feedback) if feedback is not None else None,
    }
    # Reserved client fields now emitted for source governance (GOAL §4.A).
    if feed_hidden is not None:
        payload["feed_hidden"] = feed_hidden
    if feed_quality_score is not None:
        payload["feed_quality_score"] = feed_quality_score
    return payload


def article_source_public(source: ArticleSourceRecord) -> dict[str, object]:
    return {
        "feed_id": source.feed_id,
        "feed_title": source.feed_title,
        "miniflux_entry_id": source.miniflux_entry_id,
        "source_url": source.source_url,
    }


def article_detail_public(
    article: ArticleRecord,
    state: ArticleStateRecord,
    sources: list[ArticleSourceRecord],
    score: ScoreRecord | None = None,
    feedback: ArticleFeedbackRecord | None = None,
) -> dict[str, object]:
    item = article_list_item_public(article, state, score, feedback)
    item.update(
        {
            "content_html": article.content_html,
            "content_zh": article.content_zh,
            "content_zh_status": article.content_zh_status,
            "translated_at": article.translated_at.isoformat() if article.translated_at else None,
            "content_text": article.content_text,
            "content_source": article.content_source,
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
    module: str | None = Query(default=None, max_length=32),
    q: str | None = Query(default=None, max_length=120),
    sort: str | None = Query(default=None, max_length=32),
) -> dict[str, object]:
    try:
        page = article_repository.list_articles(
            limit=limit,
            cursor=cursor,
            user_id=current_user.id,
            module=module or "all",
            q=q,
            sort=sort,
            score_lookup=scoring_repository.active_scores_for_articles,
        )
    except ValueError as error:
        message = str(error)
        if "cursor" in message.lower():
            raise ApiError(400, "invalid_cursor", "Invalid cursor") from None
        if "unsupported list module" in message:
            raise ApiError(400, "invalid_module", "Unsupported module") from None
        if "unsupported list sort" in message:
            raise ApiError(400, "invalid_sort", "Unsupported sort") from None
        raise ApiError(400, "invalid_request", message) from None
    except KeyError:
        raise ApiError(400, "invalid_cursor", "Invalid cursor") from None

    items = list(page.items)
    article_ids = [article.id for article in items]
    scores = scoring_repository.active_scores_for_articles(article_ids)
    states = article_repository.get_states(current_user.id, [article.id for article in items])
    feedbacks = article_repository.get_feedbacks(current_user.id, [article.id for article in items])
    feed_ids = [
        int(article.primary_feed_id)
        for article in items
        if article.primary_feed_id is not None
    ]
    feed_meta = article_repository.feed_governance_for_user(current_user.id, feed_ids)

    return {
        "items": [
            article_list_item_public(
                article,
                states[article.id],
                scores.get(article.id),
                feedbacks.get(article.id),
                feed_hidden=(
                    feed_meta.get(int(article.primary_feed_id), {}).get("hidden")
                    if article.primary_feed_id is not None
                    else None
                ),
                feed_quality_score=(
                    feed_meta.get(int(article.primary_feed_id), {}).get("quality_score")
                    if article.primary_feed_id is not None
                    else None
                ),
            )
            for article in items
        ],
        "next_cursor": page.next_cursor,
        "has_more": page.has_more,
    }


@router.get("/articles/stats")
def article_stats(
    _current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, int]:
    total = article_repository.count_articles()
    scored = scoring_repository.count_active_scored_articles()
    return {"total": total, "scored": scored, "unscored": max(total - scored, 0)}


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
        article_repository.get_feedback(current_user.id, article.id),
    )


@router.post("/articles/{article_id}/state")
@limiter.limit(write_rate_limit)
def update_article_state(
    payload: ArticleStateRequest,
    request: Request,
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    if article_repository.get_article(article_id) is None:
        raise ApiError(404, "not_found", "Article not found")
    if payload.project is True:
        current_state = article_repository.get_state(current_user.id, article_id)
        next_saved = payload.saved if payload.saved is not None else current_state.saved
        if not next_saved:
            raise ApiError(409, "article_not_candidate", "Article must be saved before project")
    state = article_repository.upsert_state(
        current_user.id,
        article_id,
        status=payload.status,
        saved=payload.saved,
        project=payload.project,
        read_progress=payload.read_progress,
    )
    if state is None:
        raise ApiError(404, "not_found", "Article not found")
    return {"state": article_state_public(state)}


@router.put("/articles/{article_id}/feedback")
@limiter.limit(write_rate_limit)
def update_article_feedback(
    payload: ArticleFeedbackRequest,
    request: Request,
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    feedback = article_repository.upsert_feedback(
        current_user.id,
        article_id,
        user_score=payload.user_score,
        feedback_type=payload.feedback_type,
        reason=payload.reason,
    )
    if feedback is None:
        raise ApiError(404, "not_found", "Article not found")
    return {"feedback": article_feedback_public(feedback)}


@router.get("/articles/{article_id}/annotations")
def list_article_annotations(
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    if article_repository.get_article(article_id) is None:
        raise ApiError(404, "not_found", "Article not found")
    # Private v1: only the current user's annotations are returned.
    items = article_repository.list_annotations(current_user.id, article_id)
    return {"items": [annotation_public(item) for item in items]}


@router.get("/export/project")
def export_project_articles(
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    format: str = Query(default="markdown", pattern="^(markdown|json|zip)$"),
    limit: int = Query(default=100, ge=1, le=200),
) -> Response:
    """Export the current user's project queue as Markdown, JSON, or zip (no secrets)."""
    import io
    import json
    import zipfile

    page = article_repository.list_articles(
        limit=limit,
        user_id=current_user.id,
        module="project",
    )
    scores = scoring_repository.active_scores_for_articles([item.id for item in page.items])
    annotations = article_repository.list_annotations_for_articles(
        current_user.id,
        [item.id for item in page.items],
    )
    export_items = [
        ExportArticle(
            id=article.id,
            title=article.title,
            url=article.url,
            summary_zh=(scores[article.id].summary_zh if article.id in scores else ""),
            score=scores[article.id].base_score if article.id in scores else None,
            tier=scores[article.id].recommendation_tier if article.id in scores else None,
            reason=scores[article.id].reason if article.id in scores else "",
            tags=[str(tag) for tag in (scores[article.id].tags if article.id in scores else [])],
            annotations=_export_annotations(annotations.get(article.id, [])),
        )
        for article in page.items
    ]
    if format == "json":
        return JSONResponse(build_project_export_json(export_items))
    if format == "zip":
        markdown = build_project_export_markdown(export_items)
        payload = build_project_export_json(export_items)
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, mode="w", compression=zipfile.ZIP_DEFLATED) as archive:
            archive.writestr("project.md", markdown)
            archive.writestr(
                "project.json",
                json.dumps(payload, ensure_ascii=False, indent=2),
            )
        return Response(
            content=buffer.getvalue(),
            media_type="application/zip",
            headers={"Content-Disposition": 'attachment; filename="project-export.zip"'},
        )
    body = build_project_export_markdown(export_items)
    return PlainTextResponse(body, media_type="text/markdown; charset=utf-8")


def _export_annotations(records: list[AnnotationRecord]) -> list[ExportAnnotation]:
    exported: list[ExportAnnotation] = []
    for record in records:
        meta = decode_annotation_content(record.content)
        exported.append(
            ExportAnnotation(
                selected_text=record.selected_text or "",
                note=meta.body,
                color=meta.color,
                tags=list(meta.tags),
                created_at=record.created_at.isoformat(),
            )
        )
    return exported


@router.get("/annotations/search")
def search_annotations(
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    q: str = Query(default="", max_length=200),
    limit: int = Query(default=30, ge=1, le=100),
) -> dict[str, object]:
    """Search private notes/highlights by content substring."""
    items = article_repository.search_annotations(current_user.id, q=q, limit=limit)
    articles = article_repository.get_articles([item.article_id for item in items])
    return {
        "items": [
            {
                **annotation_public(item),
                "article_title": (
                    articles[item.article_id].title if item.article_id in articles else None
                ),
                "article_url": (
                    articles[item.article_id].url if item.article_id in articles else None
                ),
            }
            for item in items
        ]
    }


@router.get("/annotations/review")
def list_annotation_review_queue(
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    limit: int = Query(default=20, ge=1, le=100),
) -> dict[str, object]:
    """Private spaced-review queue: only items due now, ordered by due time."""
    items = article_repository.list_due_annotations(current_user.id, limit=limit)
    article_ids = [item.article_id for item in items]
    articles = article_repository.get_articles(article_ids)
    return {
        "items": [
            {
                **annotation_public(item),
                "article_title": (
                    articles[item.article_id].title if item.article_id in articles else None
                ),
                "article_url": (
                    articles[item.article_id].url if item.article_id in articles else None
                ),
            }
            for item in items
        ]
    }


@router.post("/annotations/{annotation_id}/review")
@limiter.limit(write_rate_limit)
def review_annotation(
    payload: AnnotationReviewRequest,
    request: Request,
    annotation_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    """Advance SM-2 lite interval after a remember / forget response."""
    from app.domain.spaced_review import advance_review_schedule

    current = article_repository.get_annotation(current_user.id, annotation_id)
    if current is None:
        raise ApiError(404, "not_found", "Annotation not found")
    schedule = advance_review_schedule(
        interval_days=current.interval_days,
        review_count=current.review_count,
        remembered=payload.remembered,
    )
    updated = article_repository.update_annotation_review(
        current_user.id,
        annotation_id,
        next_review_at=schedule.next_review_at,
        interval_days=schedule.interval_days,
        review_count=schedule.review_count,
    )
    if updated is None:
        raise ApiError(404, "not_found", "Annotation not found")
    article = article_repository.get_article(updated.article_id)
    return {
        "annotation": {
            **annotation_public(updated),
            "article_title": article.title if article is not None else None,
            "article_url": article.url if article is not None else None,
        }
    }


@router.post("/articles/{article_id}/annotations", status_code=201)
@limiter.limit(write_rate_limit)
def create_article_annotation(
    payload: ArticleAnnotationRequest,
    request: Request,
    article_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    from app.domain.annotations_meta import encode_annotation_content

    content = payload.content.strip()
    selected = payload.selected_text.strip() if payload.selected_text else None
    if not content:
        raise ApiError(400, "invalid_request", "content is required")
    try:
        stored_content = encode_annotation_content(
            content,
            color=payload.color,
            tags=payload.tags,
            anchor=payload.anchor.model_dump(mode="json") if payload.anchor else None,
        )
        annotation = article_repository.create_annotation(
            current_user.id,
            article_id,
            content=stored_content,
            selected_text=selected or None,
            annotation_type=payload.type,
        )
    except ValueError as error:
        raise ApiError(400, "invalid_request", str(error)) from None
    if annotation is None:
        raise ApiError(404, "not_found", "Article not found")
    return {"annotation": annotation_public(annotation)}


@router.post("/articles/{article_id}/fetch-content")
@limiter.limit(write_rate_limit)
def enqueue_fetch_content_job(
    request: Request,
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
@limiter.limit(llm_rate_limit)
def enqueue_translate_article_job(
    request: Request,
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
