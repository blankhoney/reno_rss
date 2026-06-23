from dataclasses import dataclass

from fastapi import Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse

from app.core.security import SESSION_COOKIE_NAME
from app.db.auth_store import AuthStore, UserRecord
from app.db.repositories.articles import ArticleStore
from app.db.repositories.feeds import FeedStore
from app.db.repositories.jobs import JobStore
from app.db.repositories.recommendations import RecommendationStore
from app.db.repositories.scoring import ScoringStore


@dataclass
class ApiError(Exception):
    status_code: int
    code: str
    message: str
    details: dict[str, object] | None = None


def _validation_error_details(exc: RequestValidationError) -> list[dict[str, object]]:
    details = []
    for error in exc.errors():
        details.append(
            {
                "loc": error.get("loc", ()),
                "msg": error.get("msg", ""),
                "type": error.get("type", ""),
            }
        )
    return details


async def api_error_handler(_request: Request, exc: ApiError) -> JSONResponse:
    return JSONResponse(
        status_code=exc.status_code,
        content={
            "error": {
                "code": exc.code,
                "message": exc.message,
                "details": exc.details or {},
            }
        },
    )


async def request_validation_error_handler(
    _request: Request,
    exc: RequestValidationError,
) -> JSONResponse:
    return JSONResponse(
        status_code=422,
        content={
            "error": {
                "code": "unprocessable",
                "message": "Request validation failed",
                "details": {"errors": _validation_error_details(exc)},
            }
        },
    )


def get_auth_store(request: Request) -> AuthStore:
    return request.app.state.auth_store


def get_job_repository(request: Request) -> JobStore:
    return request.app.state.job_repository


def get_feed_repository(request: Request) -> FeedStore:
    return request.app.state.feed_repository


def get_article_repository(request: Request) -> ArticleStore:
    return request.app.state.article_repository


def get_scoring_repository(request: Request) -> ScoringStore:
    return request.app.state.scoring_repository


def get_recommendation_repository(request: Request) -> RecommendationStore:
    return request.app.state.recommendation_repository


def get_current_user_optional(request: Request) -> UserRecord | None:
    store = get_auth_store(request)
    token = request.cookies.get(SESSION_COOKIE_NAME)
    return store.get_user_by_session(token)


def require_user(request: Request) -> UserRecord:
    user = get_current_user_optional(request)
    if user is None:
        raise ApiError(401, "unauthenticated", "Authentication required")
    return user


def require_admin(request: Request) -> UserRecord:
    user = require_user(request)
    if user.role != "admin":
        raise ApiError(403, "forbidden", "Admin access required")
    return user
