from fastapi import APIRouter, Depends, Path, Response
from pydantic import BaseModel, Field, field_validator

from app.api.deps import ApiError, get_feed_repository, require_user
from app.db.auth_store import UserRecord
from app.db.repositories.feeds import CategoryRecord, FeedRecord, FeedStore


router = APIRouter(prefix="/api", tags=["feeds"])


class CreateFeedRequest(BaseModel):
    feed_url: str = Field(min_length=1, max_length=2048)
    category_id: int = Field(gt=0)

    @field_validator("feed_url")
    @classmethod
    def feed_url_must_not_be_blank(cls, value: str) -> str:
        normalized = value.strip()
        if not normalized:
            raise ValueError("feed_url must not be blank")
        return normalized


class SetPriorityRequest(BaseModel):
    user_priority: int = Field(ge=-20, le=20)


def category_public(category: CategoryRecord) -> dict[str, object]:
    return {
        "id": category.id,
        "slug": category.slug,
        "name": category.name,
        "sort_order": category.sort_order,
    }


def feed_public(feed: FeedRecord) -> dict[str, object]:
    return {
        "id": feed.id,
        "title": feed.title,
        "feed_url": feed.feed_url,
        "canonical_url": feed.canonical_url,
        "category": category_public(feed.category),
        "status": feed.status,
        "subscribed": feed.subscribed,
        "user_priority": feed.user_priority,
        "article_count": 0,
    }


@router.get("/categories")
def list_categories(
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, list[dict[str, object]]]:
    return {"items": [category_public(category) for category in feed_repository.list_categories()]}


@router.get("/feeds")
def list_feeds(
    current_user: UserRecord = Depends(require_user),
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, list[dict[str, object]]]:
    return {
        "items": [
            feed_public(feed) for feed in feed_repository.list_feeds(current_user.id)
        ]
    }


@router.post("/feeds")
def create_or_subscribe_feed(
    payload: CreateFeedRequest,
    response: Response,
    current_user: UserRecord = Depends(require_user),
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, object]:
    try:
        mutation = feed_repository.create_or_subscribe(
            payload.feed_url,
            payload.category_id,
            current_user.id,
        )
    except KeyError:
        raise ApiError(404, "not_found", "Category not found") from None

    response.status_code = 200 if mutation.already_exists else 201
    return {
        "feed": feed_public(mutation.feed),
        "already_exists": mutation.already_exists,
        "job_id": None,
    }


@router.post("/feeds/{feed_id}/subscribe")
def subscribe_feed(
    feed_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, object]:
    feed = feed_repository.subscribe(feed_id, current_user.id)
    if feed is None:
        raise ApiError(404, "not_found", "Feed not found")
    return {"subscribed": feed.subscribed}


@router.delete("/feeds/{feed_id}/subscribe")
def unsubscribe_feed(
    feed_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, object]:
    feed = feed_repository.unsubscribe(feed_id, current_user.id)
    if feed is None:
        raise ApiError(404, "not_found", "Feed not found")
    return {"subscribed": feed.subscribed}


@router.put("/feeds/{feed_id}/priority")
def set_feed_priority(
    payload: SetPriorityRequest,
    feed_id: int = Path(gt=0),
    current_user: UserRecord = Depends(require_user),
    feed_repository: FeedStore = Depends(get_feed_repository),
) -> dict[str, object]:
    feed = feed_repository.set_priority(feed_id, current_user.id, payload.user_priority)
    if feed is None:
        raise ApiError(404, "not_found", "Feed not found")
    return {"feed_id": feed.id, "user_priority": feed.user_priority}
