from datetime import UTC, datetime

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError

from app.api.deps import ApiError, api_error_handler, request_validation_error_handler
from app.api.routes import admin, articles, ask, auth, feeds, jobs, recommendations
from app.core.config import APP_VERSION, get_settings
from app.core.security import has_valid_csrf_origin
from app.db.auth_store import create_auth_store
from app.db.repositories.articles import create_article_repository
from app.db.repositories.feeds import create_feed_repository
from app.db.repositories.jobs import create_job_repository
from app.db.repositories.recommendations import create_recommendation_repository
from app.db.repositories.scoring import create_scoring_repository


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Reader API", version=APP_VERSION)
    app.state.auth_store = create_auth_store(settings.database_url)
    app.state.job_repository = create_job_repository(settings.database_url)
    app.state.feed_repository = create_feed_repository(settings.database_url)
    app.state.article_repository = create_article_repository(settings.database_url)
    app.state.scoring_repository = create_scoring_repository(settings.database_url)
    app.state.recommendation_repository = create_recommendation_repository(settings.database_url)
    app.state.ask_provider = ask.create_ask_provider(settings)
    app.state.csrf_allowed_origins = settings.csrf_allowed_origins or set()
    app.state.anonymous_demo_enabled = settings.anonymous_demo_user_enabled
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)

    @app.middleware("http")
    async def csrf_origin_middleware(request: Request, call_next) -> Response:
        if request.method in WRITE_METHODS and not has_valid_csrf_origin(
            request,
            request.app.state.csrf_allowed_origins,
        ):
            return await api_error_handler(
                request,
                ApiError(403, "forbidden", "Invalid request origin"),
            )
        return await call_next(request)

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    app.include_router(auth.router)
    app.include_router(articles.router)
    app.include_router(ask.router)
    app.include_router(feeds.router)
    app.include_router(admin.router)
    app.include_router(jobs.router)
    app.include_router(recommendations.router)

    return app


app = create_app()
