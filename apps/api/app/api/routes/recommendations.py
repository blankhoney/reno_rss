from fastapi import APIRouter, Depends

from app.api.deps import (
    get_article_repository,
    get_recommendation_repository,
    require_user,
)
from app.api.routes.articles import article_list_item_public
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleStore
from app.db.repositories.recommendations import (
    RecommendationItemRecord,
    RecommendationStore,
)


router = APIRouter(prefix="/api/recommendations", tags=["recommendations"])


def recommendation_item_public(
    item: RecommendationItemRecord,
    article_repository: ArticleStore,
    current_user: UserRecord,
) -> dict[str, object]:
    article = article_repository.get_article(item.article_id)
    article_payload = None
    if article is not None:
        article_payload = article_list_item_public(
            article,
            article_repository.get_state(current_user.id, article.id),
        )
    return {
        "rank": item.rank,
        "article": article_payload,
        "rank_score": item.rank_score,
        "tier": item.tier,
        "reason": item.reason,
        "source": item.source,
    }


@router.get("/latest")
def latest_recommendations(
    current_user: UserRecord = Depends(require_user),
    recommendation_repository: RecommendationStore = Depends(get_recommendation_repository),
    article_repository: ArticleStore = Depends(get_article_repository),
) -> dict[str, object]:
    edition = recommendation_repository.latest_for_user(current_user.id)
    if edition is None:
        return {"edition": None, "items": [], "candidates": []}
    return {
        "edition": {
            "id": edition.id,
            "generated_at": edition.generated_at.isoformat(),
            "edition_type": edition.edition_type,
            "algorithm_version": edition.algorithm_version,
        },
        "items": [
            recommendation_item_public(item, article_repository, current_user)
            for item in edition.items
        ],
        "candidates": [],
    }
