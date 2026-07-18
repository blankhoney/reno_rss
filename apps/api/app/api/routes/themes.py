"""Theme clusters from active score tags (GOAL §4.C)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_scoring_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.scoring import ScoringStore
from app.domain.themes import cluster_themes


router = APIRouter(prefix="/api/themes", tags=["themes"])


@router.get("/latest")
def latest_themes(
    _current_user: UserRecord = Depends(require_user),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    limit: int = Query(default=100, ge=1, le=500),
    max_themes: int = Query(default=20, ge=1, le=50),
) -> dict[str, object]:
    scores = scoring_repository.list_active_scores(limit=limit)
    themes = cluster_themes(
        [
            {
                "article_id": score.article_id,
                "tags": score.tags,
                "base_score": score.base_score,
            }
            for score in scores
        ],
        max_themes=max_themes,
    )
    return {"themes": themes, "source_score_count": len(scores)}
