from __future__ import annotations

from collections.abc import Callable, Generator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
import logging
import os
from pathlib import Path
import socket
from typing import Any, Protocol, TypeVar, cast, runtime_checkable

from app.db.article_sink import DatabaseArticleSink
from app.db.benchmark_sink import DatabaseBenchmarkSink
from app.db.brief_sink import DatabaseBriefSink
from app.db.content_sink import DatabaseContentSink
from app.db.cost_ledger import DatabaseDailyUsageLedger
from app.db.governance_sink import DatabaseGovernanceSink
from app.db.recommendation_sink import DatabaseRecommendationSink
from app.db.research_sink import DatabaseResearchSink
from app.db.score_sink import DatabaseScoreSink
from app.jobs.auto_score import run_auto_score_candidates
from app.jobs.complete_ingest import complete_ingest_cycle
from app.jobs.daily_brief import generate_daily_brief
from app.jobs.fetch_content import fetch_article_content
from app.jobs.generate_recommendations import generate_recommendations, rank_b4_recommendation_context
from app.jobs.govern_sources import govern_sources
from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue
from app.jobs.research_brief import run_budgeted_research_brief
from app.jobs.run_benchmark import run_benchmark
from app.jobs.score_batch import score_batch
from app.jobs.sync_miniflux import run_sync_miniflux_entries
from app.jobs.translate_article import translate_article
from app.providers.external_content import NoExternalContentProvider
from app.providers.llm import create_provider
from app.providers.miniflux import MinifluxClient, MinifluxConfig
from app.runner import Handler, JobQueue
from app.scheduler import env_flag_enabled
from app.webhooks import webhook_client_from_env


LOGGER = logging.getLogger(__name__)


@runtime_checkable
class Closable(Protocol):
    def dispose(self) -> None: ...


@dataclass(frozen=True)
class WorkerRuntimeSettings:
    database_url: str | None = None
    log_level: str = "INFO"
    worker_id: str = "worker"
    poll_seconds: float = 2.0
    retry_backoff_seconds: int = 60
    retry_backoff_max_seconds: int = 3600
    job_lease_seconds: int = 900
    scheduler_enabled: bool = True
    heartbeat_file: Path = Path("/tmp/worker-heartbeat")

    @classmethod
    def from_env(cls) -> WorkerRuntimeSettings:
        return cls(
            database_url=normalize_database_url(os.environ.get("SCORING_DATABASE_URL")),
            log_level=os.environ.get("WORKER_LOG_LEVEL", "INFO"),
            worker_id=os.environ.get("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}",
            poll_seconds=float(os.environ.get("WORKER_POLL_SECONDS", "2")),
            retry_backoff_seconds=int(os.environ.get("WORKER_RETRY_BACKOFF_SECONDS", "60")),
            retry_backoff_max_seconds=int(
                os.environ.get("WORKER_RETRY_BACKOFF_MAX_SECONDS", "3600")
            ),
            job_lease_seconds=int(os.environ.get("WORKER_JOB_LEASE_SECONDS", "900")),
            scheduler_enabled=env_flag_enabled(
                os.environ.get("SCHEDULER_ENABLED"),
                default=True,
            ),
            heartbeat_file=Path(
                os.environ.get("WORKER_HEARTBEAT_FILE", "/tmp/worker-heartbeat")
            ),
        )


@dataclass(frozen=True)
class CompositionFactories:
    score_sink: Callable[..., Any] = DatabaseScoreSink
    article_sink: Callable[..., Any] = DatabaseArticleSink
    brief_sink: Callable[..., Any] = DatabaseBriefSink
    research_sink: Callable[..., Any] = DatabaseResearchSink
    content_sink: Callable[..., Any] = DatabaseContentSink
    usage_ledger: Callable[..., Any] = DatabaseDailyUsageLedger
    recommendation_sink: Callable[..., Any] = DatabaseRecommendationSink
    governance_sink: Callable[..., Any] = DatabaseGovernanceSink
    benchmark_sink: Callable[..., Any] = DatabaseBenchmarkSink
    provider: Callable[[], Any] = create_provider
    miniflux_config: Callable[[], Any] = MinifluxConfig.from_env
    miniflux_client: Callable[[Any], Any] = MinifluxClient
    external_content_provider: Callable[[], Any] = NoExternalContentProvider
    webhook_client: Callable[[], Any] = webhook_client_from_env


def normalize_database_url(database_url: str | None) -> str | None:
    # Keep in parity with apps/api/app/core/config.py; both sides have golden tests.
    if database_url is None:
        return None
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    return database_url


def create_worker_queue(
    settings: WorkerRuntimeSettings | None = None,
) -> InMemoryJobQueue | PostgresJobQueue:
    runtime = settings or WorkerRuntimeSettings.from_env()
    if runtime.database_url:
        return PostgresJobQueue(runtime.database_url)
    return InMemoryJobQueue()


def build_handler_registry(
    settings: WorkerRuntimeSettings | None = None,
    *,
    factories: CompositionFactories | None = None,
) -> dict[str, Handler]:
    runtime = settings or WorkerRuntimeSettings.from_env()
    adapters = factories or CompositionFactories()

    def database_url(job_type: str) -> str:
        if not runtime.database_url:
            raise RuntimeError(f"SCORING_DATABASE_URL is required for {job_type}")
        return runtime.database_url

    def worker_echo(payload: Mapping[str, object]) -> dict[str, object]:
        return {"payload": dict(payload)}

    def auto_score_candidates(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(adapters.score_sink(database_url("auto_score_candidates"))) as sink:
            return run_auto_score_candidates(
                dict(payload),
                sink,
                daily_article_cap=_env_non_negative_int("SCHEDULE_SCORE_DAILY_ARTICLE_CAP", 60),
            )

    def complete_ingest(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(adapters.article_sink(database_url("complete_ingest_cycle"))) as sink:
            return complete_ingest_cycle(dict(payload), sink)

    def daily_brief(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(adapters.brief_sink(database_url("generate_daily_brief"))) as sink:
            return generate_daily_brief(
                dict(payload),
                sink,
                webhook=adapters.webhook_client(),
            )

    def research_brief(payload: Mapping[str, object]) -> dict[str, object]:
        url = database_url("research_brief")
        with _managed_resource(adapters.research_sink(url)) as sink:
            with _managed_resource(adapters.usage_ledger(url)) as ledger:
                return run_budgeted_research_brief(
                    dict(payload),
                    sink,
                    provider=adapters.provider(),
                    ledger=ledger,
                    daily_limit=_env_non_negative_int("AGENT_DAILY_CALL_BUDGET", 20),
                )

    def sync_miniflux_entries(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(
            adapters.article_sink(database_url("sync_miniflux_entries"))
        ) as sink:
            with adapters.miniflux_client(adapters.miniflux_config()) as client:
                return run_sync_miniflux_entries(
                    dict(payload),
                    sink=sink,
                    client=client,
                )

    def fetch_content(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(
            adapters.content_sink(database_url("fetch_article_content"))
        ) as sink:
            with adapters.miniflux_client(adapters.miniflux_config()) as client:
                return fetch_article_content(
                    dict(payload),
                    sink=sink,
                    miniflux_client=client,
                    external_provider=adapters.external_content_provider(),
                )

    def translate(payload: Mapping[str, object]) -> dict[str, object]:
        url = database_url("translate_article")
        with _managed_resource(adapters.content_sink(url)) as sink:
            with _managed_resource(adapters.usage_ledger(url)) as ledger:
                return translate_article(
                    dict(payload),
                    sink=sink,
                    provider=adapters.provider(),
                    budget=ledger,
                    daily_limit=_env_non_negative_int("TRANSLATION_DAILY_CALL_BUDGET", 60),
                )

    def score(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(adapters.score_sink(database_url("score_batch"))) as sink:
            return score_batch(
                dict(payload),
                sink,
                adapters.provider(),
                daily_article_cap=_env_non_negative_int("SCHEDULE_SCORE_DAILY_ARTICLE_CAP", 60),
                score_budget=sink,
                webhook=adapters.webhook_client(),
                high_score_threshold=_env_non_negative_int(
                    "AI_READER_WEBHOOK_HIGH_SCORE_THRESHOLD",
                    85,
                ),
            )

    def recommendations(payload: Mapping[str, object]) -> dict[str, object]:
        source_batch_id = payload.get("source_batch_id")
        sink = adapters.recommendation_sink(
            database_url("generate_recommendations"),
            source_batch_id=int(cast(Any, source_batch_id))
            if source_batch_id is not None
            else None,
        )
        with _managed_resource(sink) as managed_sink:
            return generate_recommendations(
                dict(payload),
                managed_sink,
                rank_b4_recommendation_context,
            )

    def govern(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(
            adapters.governance_sink(database_url("govern_sources"))
        ) as sink:
            return govern_sources(dict(payload), sink)

    def benchmark(payload: Mapping[str, object]) -> dict[str, object]:
        with _managed_resource(
            adapters.benchmark_sink(database_url("run_benchmark"))
        ) as sink:
            return run_benchmark(dict(payload), sink)

    return {
        "auto_score_candidates": auto_score_candidates,
        "complete_ingest_cycle": complete_ingest,
        "fetch_article_content": fetch_content,
        "generate_daily_brief": daily_brief,
        "generate_recommendations": recommendations,
        "govern_sources": govern,
        "research_brief": research_brief,
        "run_benchmark": benchmark,
        "score_batch": score,
        "translate_article": translate,
        "worker_echo": worker_echo,
        "sync_miniflux_entries": sync_miniflux_entries,
    }


def close_queue(queue: JobQueue | Closable) -> None:
    dispose = getattr(queue, "dispose", None)
    if dispose is None:
        return
    if not callable(dispose):
        raise TypeError("queue dispose attribute must be callable")
    if not isinstance(queue, Closable):
        raise TypeError("queue dispose method does not satisfy Closable")
    queue.dispose()


TClosable = TypeVar("TClosable", bound=Closable)


@contextmanager
def _managed_resource(resource: TClosable) -> Generator[TClosable, None, None]:
    try:
        yield resource
    except BaseException:
        try:
            _dispose_resource(resource)
        except BaseException:
            LOGGER.exception("worker resource disposal failed while preserving job error")
        raise
    else:
        _dispose_resource(resource)


def _dispose_resource(resource: Closable) -> None:
    dispose = getattr(resource, "dispose", None)
    if not callable(dispose):
        raise TypeError(f"{type(resource).__name__} dispose attribute must be callable")
    dispose()


def touch_worker_heartbeat(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.touch()


def _env_non_negative_int(name: str, default: int) -> int:
    raw = os.environ.get(name)
    if raw is None or not raw.strip():
        return default
    value = int(raw)
    if value < 0:
        raise ValueError(f"{name} must be greater than or equal to 0")
    return value
