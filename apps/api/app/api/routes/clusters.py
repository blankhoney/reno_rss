"""Storyline clusters computed on the fly from recent articles."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.api.deps import get_article_repository, get_scoring_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleStore
from app.db.repositories.scoring import ScoringStore
from app.domain.clusters import ClusterArticle, cluster_articles


# Window of recent articles scanned before clustering (memory-friendly).
DEFAULT_SCAN_LIMIT = 200

router = APIRouter(prefix="/api/clusters", tags=["clusters"])


@router.get("/latest")
def latest_clusters(
    limit: int = Query(default=20, ge=1, le=50),
    current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    del current_user  # auth gate only; clustering is not user-personalized yet
    page = article_repository.list_articles(limit=DEFAULT_SCAN_LIMIT)
    article_ids = [article.id for article in page.items]
    scores = (
        scoring_repository.active_scores_for_articles(article_ids) if article_ids else {}
    )
    cluster_inputs = [
        ClusterArticle(
            id=article.id,
            title=article.title,
            published_at=article.published_at,
            base_score=(
                scores[article.id].base_score
                if article.id in scores and scores[article.id].base_score is not None
                else None
            ),
        )
        for article in page.items
    ]
    clusters = cluster_articles(cluster_inputs, limit=limit)
    return {
        "clusters": [
            {
                "id": cluster.id,
                "label": cluster.label,
                "main_article_id": cluster.main_article_id,
                "related_article_ids": list(cluster.related_article_ids),
                "size": cluster.size,
            }
            for cluster in clusters
        ]
    }
