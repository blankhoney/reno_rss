"""Interest vector GET / reset / export (GOAL §4.A personalization)."""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from fastapi import APIRouter, Depends, Request
from sqlalchemy import text

from app.api.deps import get_article_repository, get_scoring_repository, require_user
from app.core.config import get_settings
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleStore
from app.db.repositories.scoring import ScoringStore
from app.domain.personalization import InterestSignal, build_interest_profile


router = APIRouter(prefix="/api/me", tags=["interest"])


def _memory_reset_store(request: Request) -> dict[str, datetime]:
    store = getattr(request.app.state, "interest_reset_at", None)
    if store is None:
        store = {}
        request.app.state.interest_reset_at = store
    return store


def _load_reset_at(request: Request, user_id: UUID) -> datetime | None:
    memory = _memory_reset_store(request).get(str(user_id))
    if memory is not None:
        return memory
    # Durable table when Postgres is available (best-effort).
    try:
        from sqlalchemy import create_engine

        database_url = get_settings().database_url
        if not database_url or database_url.startswith("sqlite"):
            return None
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.begin() as connection:
            row = (
                connection.execute(
                    text("SELECT reset_at FROM user_interest_resets WHERE user_id = :user_id"),
                    {"user_id": str(user_id)},
                )
                .mappings()
                .first()
            )
        engine.dispose()
        if row is None:
            return None
        value = row["reset_at"]
        if isinstance(value, datetime):
            return value if value.tzinfo else value.replace(tzinfo=UTC)
        return datetime.fromisoformat(str(value))
    except Exception:
        return None


def _persist_reset_at(request: Request, user_id: UUID, reset_at: datetime) -> None:
    _memory_reset_store(request)[str(user_id)] = reset_at
    try:
        from sqlalchemy import create_engine

        database_url = get_settings().database_url
        if not database_url or database_url.startswith("sqlite"):
            return
        engine = create_engine(database_url, pool_pre_ping=True)
        with engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO user_interest_resets (user_id, reset_at, updated_at)
                    VALUES (:user_id, :reset_at, :reset_at)
                    ON CONFLICT (user_id) DO UPDATE
                      SET reset_at = EXCLUDED.reset_at,
                          updated_at = EXCLUDED.updated_at
                    """
                ),
                {"user_id": str(user_id), "reset_at": reset_at.isoformat()},
            )
        engine.dispose()
    except Exception:
        # Memory map still applies for this process.
        return


@router.get("/interest")
def get_interest(
    request: Request,
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    return _profile_for_user(
        current_user,
        article_repository,
        scoring_repository,
        reset_at=_load_reset_at(request, current_user.id),
    )


@router.get("/interest/export")
def export_interest(
    request: Request,
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    profile = _profile_for_user(
        current_user,
        article_repository,
        scoring_repository,
        reset_at=_load_reset_at(request, current_user.id),
    )
    return {"export": profile, "format": "interest_vector.v1"}


@router.post("/interest/reset")
def reset_interest(
    request: Request,
    current_user: UserRecord = Depends(require_user),
) -> dict[str, object]:
    now = datetime.now(UTC)
    _persist_reset_at(request, current_user.id, now)
    return {
        "status": "ok",
        "reset_at": now.isoformat(),
        "profile": build_interest_profile(
            [],
            project_count=0,
            annotation_count=0,
            reset_at=now,
        ),
    }


def _profile_for_user(
    current_user: UserRecord,
    article_repository: ArticleStore,
    scoring_repository: ScoringStore,
    *,
    reset_at: datetime | None,
) -> dict[str, object]:
    annotations = article_repository.list_recent_annotations(current_user.id, limit=100)
    if reset_at is not None:
        annotations = [
            item
            for item in annotations
            if item.created_at is None or item.created_at >= reset_at
        ]

    project_page = article_repository.list_articles(
        limit=50,
        user_id=current_user.id,
        module="project",
    )
    project_items = project_page.items
    if reset_at is not None:
        # Projects lack created_at on state in all stores; keep titles for post-reset rebuild
        # only when annotations/feedback still provide signal. Titles always contribute lightly.
        pass

    signals: list[InterestSignal] = []
    for annotation in annotations:
        text = " ".join(
            part
            for part in (annotation.selected_text or "", annotation.content or "")
            if part
        )
        if text.strip():
            signals.append(InterestSignal(text=text, weight=2.0, kind="annotation"))

    for article in project_items:
        signals.append(InterestSignal(text=article.title or "", weight=1.5, kind="project"))

    article_ids = [article.id for article in project_items]
    starred_page = article_repository.list_articles(
        limit=50,
        user_id=current_user.id,
        module="starred",
    )
    for article in starred_page.items:
        signals.append(InterestSignal(text=article.title or "", weight=1.2, kind="starred"))
        article_ids.append(article.id)

    feedbacks = article_repository.get_feedbacks(current_user.id, article_ids)
    if reset_at is not None:
        feedbacks = {
            article_id: feedback
            for article_id, feedback in feedbacks.items()
            if feedback.updated_at is None or feedback.updated_at >= reset_at
        }

    feedback_types = [feedback.feedback_type for feedback in feedbacks.values()]
    for feedback in feedbacks.values():
        if feedback.feedback_type == "underrated":
            # Positive signal: reason text is a preference hint.
            if feedback.reason:
                signals.append(
                    InterestSignal(text=feedback.reason, weight=1.8, kind="feedback")
                )
        elif feedback.feedback_type in {"overrated", "too_promotional", "low_density", "outdated"}:
            if feedback.reason:
                signals.append(
                    InterestSignal(text=feedback.reason, weight=0.4, kind="negative_feedback")
                )

    scores = scoring_repository.active_scores_for_articles(list(dict.fromkeys(article_ids)))
    for score in scores.values():
        for tag in score.tags or []:
            signals.append(InterestSignal(text=str(tag), weight=1.3, kind="tag"))

    return build_interest_profile(
        signals,
        feedback_types=feedback_types,
        project_count=len(project_items),
        annotation_count=len(annotations),
        reset_at=reset_at,
    )
