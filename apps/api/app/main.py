from datetime import UTC, datetime
import logging

from fastapi import FastAPI, Request, Response
from fastapi.exceptions import RequestValidationError
from slowapi.errors import RateLimitExceeded
from slowapi.middleware import SlowAPIMiddleware

from app.api.deps import ApiError, api_error_handler, request_validation_error_handler
from app.api.routes import (
    acl,
    admin,
    articles,
    ask,
    auth,
    briefs,
    clusters,
    feeds,
    interest,
    jobs,
    recommendations,
    research,
    rules,
    saved_searches,
    themes,
)
from app.core.config import APP_VERSION, get_settings
from app.core.ratelimit import limiter
from app.core.request_timing import RequestTimingMiddleware
from app.core.security import has_valid_csrf_origin
from app.db.auth_store import create_auth_store
from app.db.repositories.articles import create_article_repository
from app.db.repositories.benchmarks import create_benchmark_repository
from app.db.repositories.feeds import create_feed_repository
from app.db.repositories.jobs import create_job_repository
from app.db.repositories.cost_ledger import create_cost_ledger
from app.db.repositories.interest import create_interest_reset_repository
from app.db.repositories.project_acl import create_project_acl_repository
from app.db.repositories.recommendations import create_recommendation_repository
from app.db.repositories.rules import create_rule_repository
from app.db.repositories.saved_searches import create_saved_search_repository
from app.db.repositories.scoring import create_scoring_repository


WRITE_METHODS = {"POST", "PUT", "PATCH", "DELETE"}
LOGGER = logging.getLogger(__name__)


def create_app() -> FastAPI:
    settings = get_settings()
    app = FastAPI(title="AI Reader API", version=APP_VERSION)
    app.state.auth_store = create_auth_store(settings.database_url)
    app.state.job_repository = create_job_repository(settings.database_url)
    app.state.benchmark_repository = create_benchmark_repository(settings.database_url)
    app.state.feed_repository = create_feed_repository(settings.database_url)
    app.state.article_repository = create_article_repository(settings.database_url)
    app.state.scoring_repository = create_scoring_repository(settings.database_url)
    app.state.recommendation_repository = create_recommendation_repository(settings.database_url)
    app.state.rule_repository = create_rule_repository(settings.database_url)
    app.state.saved_search_repository = create_saved_search_repository(settings.database_url)
    app.state.interest_reset_repository = create_interest_reset_repository(settings.database_url)
    app.state.project_acl_repository = create_project_acl_repository(settings.database_url)
    app.state.ask_provider = ask.create_ask_provider(settings)
    app.state.cost_ledger = create_cost_ledger(
        settings.database_url,
        limits={
            "score": settings.score_daily_call_budget,
            "ask": settings.llm_daily_call_budget,
            "agent": settings.agent_daily_call_budget,
        },
    )
    app.state.scheduler_enabled = settings.scheduler_enabled
    app.state.csrf_allowed_origins = settings.csrf_allowed_origins or set()
    if not app.state.csrf_allowed_origins:
        LOGGER.critical(
            "AI_READER_CSRF_ALLOWED_ORIGINS is empty; write requests will be rejected."
        )
    app.state.anonymous_demo_enabled = settings.anonymous_demo_user_enabled
    limiter.reset()
    app.state.limiter = limiter
    app.add_exception_handler(ApiError, api_error_handler)
    app.add_exception_handler(RequestValidationError, request_validation_error_handler)
    app.add_exception_handler(RateLimitExceeded, rate_limit_error_handler)
    app.add_middleware(SlowAPIMiddleware)

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

    app.add_middleware(
        RequestTimingMiddleware,
        slow_request_ms=settings.slow_request_ms,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/metrics")
    async def api_metrics(request: Request) -> Response:
        """Lightweight Prometheus text exposition (no extra deps)."""
        ledger = request.app.state.cost_ledger
        snapshot = ledger.snapshot()
        ask_account = dict(snapshot["accounts"]["ask"])
        used = int(ask_account.get("used", 0) or 0)
        limit = int(ask_account.get("limit", 0) or 0)
        lines = [
            "# HELP ai_reader_up Always 1 when the API process is serving.",
            "# TYPE ai_reader_up gauge",
            "ai_reader_up 1",
            "# HELP ai_reader_ask_calls_used Ask budget units reserved today.",
            "# TYPE ai_reader_ask_calls_used gauge",
            f"ai_reader_ask_calls_used {used}",
            "# HELP ai_reader_ask_calls_limit Ask budget daily limit (0=unlimited).",
            "# TYPE ai_reader_ask_calls_limit gauge",
            f"ai_reader_ask_calls_limit {limit}",
            "",
        ]
        return Response("\n".join(lines), media_type="text/plain; version=0.0.4; charset=utf-8")

    app.include_router(auth.router)
    app.include_router(articles.router)
    app.include_router(ask.router)
    app.include_router(feeds.router)
    app.include_router(admin.router)
    app.include_router(jobs.router)
    app.include_router(recommendations.router)
    app.include_router(briefs.router)
    app.include_router(clusters.router)
    app.include_router(rules.router)
    app.include_router(research.router)
    app.include_router(themes.router)
    app.include_router(saved_searches.router)
    app.include_router(interest.router)
    app.include_router(acl.router)

    return app


async def rate_limit_error_handler(request: Request, exc: RateLimitExceeded) -> Response:
    return await api_error_handler(
        request,
        ApiError(
            429,
            "rate_limited",
            "Rate limit exceeded",
            {"detail": str(getattr(exc, "detail", exc))},
        ),
    )


app = create_app()
