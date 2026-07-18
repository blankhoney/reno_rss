from fastapi import APIRouter, Depends

from app.api.deps import (
    get_article_repository,
    get_recommendation_repository,
    get_scoring_repository,
    require_user,
)
from app.api.routes.articles import article_list_item_public
from app.db.auth_store import UserRecord
from app.db.repositories.articles import (
    ArticleFeedbackRecord,
    ArticleRecord,
    ArticleStateRecord,
    ArticleStore,
)
from app.db.repositories.recommendations import (
    RecommendationItemRecord,
    RecommendationStore,
)
from app.db.repositories.scoring import ScoreRecord, ScoringStore


router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def recommendation_explain_factors(
    item: RecommendationItemRecord,
    score: ScoreRecord | None,
) -> dict[str, object]:
    """Why this item is in TopN — derived at read time (no extra storage)."""
    risk_flags = list(score.risk_flags) if score is not None else []
    dimensions = dict(score.dimension_scores) if score is not None else {}
    return {
        "rank_score": item.rank_score,
        "tier": item.tier,
        "source": item.source,
        "reason": item.reason,
        "base_score": score.base_score if score is not None else None,
        "risk_flags": risk_flags,
        "risk_uncertainty": dimensions.get("risk_uncertainty"),
        "dimensions": dimensions,
    }


def recommendation_item_public(
    item: RecommendationItemRecord,
    articles_by_id: dict[int, ArticleRecord],
    state: ArticleStateRecord,
    score: ScoreRecord | None,
    feedback: ArticleFeedbackRecord | None,
) -> dict[str, object]:
    article = articles_by_id.get(item.article_id)
    article_payload = None
    if article is not None:
        article_payload = article_list_item_public(
            article,
            state,
            score,
            feedback,
        )
    factors = recommendation_explain_factors(item, score)
    return {
        "rank": item.rank,
        "article": article_payload,
        "rank_score": item.rank_score,
        "tier": item.tier,
        "reason": item.reason,
        "source": item.source,
        "risk_flags": factors["risk_flags"],
        "risk_uncertainty": factors["risk_uncertainty"],
        "factors": factors,
    }


@router.get("/latest")
def latest_recommendations(
    current_user: UserRecord = Depends(require_user),
    recommendation_repository: RecommendationStore = Depends(get_recommendation_repository),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> dict[str, object]:
    edition = recommendation_repository.latest_for_user(current_user.id)
    if edition is None:
        return {"edition": None, "items": [], "candidates": []}
    article_ids = [item.article_id for item in edition.items]
    articles_by_id = article_repository.get_articles(article_ids)
    states = article_repository.get_states(current_user.id, article_ids)
    scores = scoring_repository.active_scores_for_articles(article_ids)
    feedbacks = article_repository.get_feedbacks(current_user.id, article_ids)
    return {
        "edition": {
            "id": edition.id,
            "generated_at": edition.generated_at.isoformat(),
            "edition_type": edition.edition_type,
            "algorithm_version": edition.algorithm_version,
        },
        "items": [
            recommendation_item_public(
                item,
                articles_by_id,
                states[item.article_id],
                scores.get(item.article_id),
                feedbacks.get(item.article_id),
            )
            for item in edition.items
        ],
        "candidates": [],
    }
