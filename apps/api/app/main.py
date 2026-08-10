from datetime import UTC, datetime
import logging
from threading import RLock

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
from app.core.request_timing import RequestMetrics, RequestTimingMiddleware
from app.core.security import has_valid_csrf_origin
from app.db.auth_store import create_auth_store
from app.db.repositories.articles import MemoryArticleRepository, create_article_repository
from app.db.repositories.benchmarks import create_benchmark_repository
from app.db.repositories.feeds import create_feed_repository
from app.db.repositories.jobs import MemoryJobRepository, create_job_repository
from app.db.repositories.translation_enqueue import create_translation_enqueue_store
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
    memory_lock = RLock() if not settings.database_url else None
    app.state.auth_store = create_auth_store(settings.database_url)
    app.state.job_repository = create_job_repository(settings.database_url, lock=memory_lock)
    app.state.benchmark_repository = create_benchmark_repository(settings.database_url)
    app.state.feed_repository = create_feed_repository(settings.database_url)
    app.state.article_repository = create_article_repository(settings.database_url, lock=memory_lock)
    if settings.database_url:
        app.state.translation_enqueue_store = create_translation_enqueue_store(
            settings.database_url
        )
    else:
        assert memory_lock is not None
        assert isinstance(app.state.article_repository, MemoryArticleRepository)
        assert isinstance(app.state.job_repository, MemoryJobRepository)
        app.state.translation_enqueue_store = create_translation_enqueue_store(
            None,
            article_repository=app.state.article_repository,
            job_repository=app.state.job_repository,
            lock=memory_lock,
        )
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
            "translate": settings.translation_daily_call_budget,
        },
    )
    app.state.scheduler_enabled = settings.scheduler_enabled
    app.state.csrf_allowed_origins = settings.csrf_allowed_origins or set()
    if not app.state.csrf_allowed_origins:
        LOGGER.critical(
            "AI_READER_CSRF_ALLOWED_ORIGINS is empty; write requests will be rejected."
        )
    app.state.anonymous_demo_enabled = settings.anonymous_demo_user_enabled
    app.state.request_metrics = RequestMetrics()
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
        metrics=app.state.request_metrics,
    )

    @app.get("/healthz")
    async def healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/healthz")
    async def api_healthz() -> dict[str, object]:
        return {"ok": True, "time": datetime.now(UTC).isoformat(), "version": app.version}

    @app.get("/api/metrics")
    async def api_metrics(request: Request) -> Response:
        """Prometheus exposition for latency, queue, LLM spend, and errors."""
        ledger = request.app.state.cost_ledger
        snapshot = ledger.snapshot()
        accounts = {
            name: dict(values)
            for name, values in dict(snapshot.get("accounts") or {}).items()
        }
        day_start = datetime.now(UTC).replace(hour=0, minute=0, second=0, microsecond=0)
        score_account = accounts.setdefault("score", {})
        score_account["used"] = request.app.state.scoring_repository.count_scores_since(day_start)

        request_snapshot = request.app.state.request_metrics.snapshot()
        request_count = int(request_snapshot["requests_total"])
        error_count = int(request_snapshot["errors_total"])
        error_ratio = error_count / request_count if request_count else 0.0

        queue = request.app.state.job_repository.pipeline_snapshot(admin.PIPELINE_JOB_TYPES)
        oldest = queue.get("oldest_queued_at")
        if isinstance(oldest, str):
            oldest = datetime.fromisoformat(oldest.replace("Z", "+00:00"))
        oldest_age = 0.0
        if isinstance(oldest, datetime):
            normalized = oldest if oldest.tzinfo is not None else oldest.replace(tzinfo=UTC)
            oldest_age = max(0.0, (datetime.now(UTC) - normalized).total_seconds())

        lines = [
            "# HELP ai_reader_up Always 1 when the API process is serving.",
            "# TYPE ai_reader_up gauge",
            "ai_reader_up 1",
            "# HELP ai_reader_http_requests_total Observed API requests since process start.",
            "# TYPE ai_reader_http_requests_total counter",
            f"ai_reader_http_requests_total {request_count}",
            "# HELP ai_reader_http_request_duration_seconds Request latency summary.",
            "# TYPE ai_reader_http_request_duration_seconds summary",
            f'ai_reader_http_request_duration_seconds_count {request_count}',
            f'ai_reader_http_request_duration_seconds_sum {float(request_snapshot["duration_seconds_sum"]):.6f}',
            "# HELP ai_reader_http_errors_total HTTP 5xx responses since process start.",
            "# TYPE ai_reader_http_errors_total counter",
            f"ai_reader_http_errors_total {error_count}",
            "# HELP ai_reader_http_error_ratio Process-lifetime 5xx ratio for error-budget alerts.",
            "# TYPE ai_reader_http_error_ratio gauge",
            f"ai_reader_http_error_ratio {error_ratio:.6f}",
            "# HELP ai_reader_http_slow_requests_total Requests above SLOW_REQUEST_MS.",
            "# TYPE ai_reader_http_slow_requests_total counter",
            f'ai_reader_http_slow_requests_total {int(request_snapshot["slow_requests_total"])}',
            "# HELP ai_reader_job_queue_queued Pipeline jobs waiting to run.",
            "# TYPE ai_reader_job_queue_queued gauge",
            f'ai_reader_job_queue_queued {int(queue["queued"])}',
            "# HELP ai_reader_job_queue_running Pipeline jobs currently leased.",
            "# TYPE ai_reader_job_queue_running gauge",
            f'ai_reader_job_queue_running {int(queue["running"])}',
            "# HELP ai_reader_job_queue_oldest_age_seconds Age of the oldest queued job.",
            "# TYPE ai_reader_job_queue_oldest_age_seconds gauge",
            f"ai_reader_job_queue_oldest_age_seconds {oldest_age:.3f}",
            "# HELP ai_reader_job_failures_24h Pipeline failures during the last 24 hours.",
            "# TYPE ai_reader_job_failures_24h gauge",
            f'ai_reader_job_failures_24h {int(queue["failed_24h"])}',
            "# HELP ai_reader_job_stale_running Jobs whose lease is stale.",
            "# TYPE ai_reader_job_stale_running gauge",
            f'ai_reader_job_stale_running {int(queue["stale_running"])}',
            "# HELP ai_reader_scheduler_enabled Unattended pipeline scheduler flag.",
            "# TYPE ai_reader_scheduler_enabled gauge",
            f'ai_reader_scheduler_enabled {1 if request.app.state.scheduler_enabled else 0}',
        ]
        lines.extend(
            [
                "# HELP ai_reader_llm_calls_used Daily reserved calls by account.",
                "# TYPE ai_reader_llm_calls_used gauge",
            ]
        )
        for account in ("score", "ask", "agent", "translate"):
            values = accounts.get(account, {})
            lines.append(
                f'ai_reader_llm_calls_used{{account="{account}"}} {int(values.get("used", 0) or 0)}'
            )
        lines.extend(
            [
                "# HELP ai_reader_llm_calls_limit Daily configured call limit by account (0=unlimited).",
                "# TYPE ai_reader_llm_calls_limit gauge",
            ]
        )
        for account in ("score", "ask", "agent", "translate"):
            values = accounts.get(account, {})
            lines.append(
                f'ai_reader_llm_calls_limit{{account="{account}"}} {int(values.get("limit", 0) or 0)}'
            )
        lines.append("")
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
