import logging
import os
import signal
import socket
from threading import Event

from app.db.article_sink import DatabaseArticleSink
from app.db.content_sink import DatabaseContentSink
from app.db.recommendation_sink import DatabaseRecommendationSink
from app.db.score_sink import DatabaseScoreSink
from app.jobs.fetch_content import fetch_article_content
from app.jobs.generate_recommendations import generate_recommendations, rank_b4_recommendation_context
from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue
from app.jobs.score_batch import score_batch
from app.jobs.sync_miniflux import run_sync_miniflux_entries
from app.providers.external_content import NoExternalContentProvider
from app.providers.llm import create_provider
from app.providers.miniflux import MinifluxClient, MinifluxConfig
from app.runner import Handler, run_forever


def normalize_database_url(database_url: str | None) -> str | None:
    if database_url is None:
        return None
    if database_url.startswith("postgres://"):
        return f"postgresql+psycopg://{database_url.removeprefix('postgres://')}"
    return database_url


def create_worker_queue() -> InMemoryJobQueue | PostgresJobQueue:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if database_url:
        return PostgresJobQueue(database_url)
    return InMemoryJobQueue()


def build_handler_registry() -> dict[str, Handler]:
    return {
        "fetch_article_content": _fetch_article_content,
        "generate_recommendations": _generate_recommendations,
        "score_batch": _score_batch,
        "worker_echo": _worker_echo,
        "sync_miniflux_entries": _sync_miniflux_entries,
    }


def main() -> None:
    logging.basicConfig(level=os.environ.get("WORKER_LOG_LEVEL", "INFO"))
    queue = create_worker_queue()
    registry = build_handler_registry()
    stop_event = Event()
    worker_id = os.environ.get("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
    poll_seconds = float(os.environ.get("WORKER_POLL_SECONDS", "2"))
    retry_backoff_seconds = int(os.environ.get("WORKER_RETRY_BACKOFF_SECONDS", "60"))
    retry_backoff_max_seconds = int(os.environ.get("WORKER_RETRY_BACKOFF_MAX_SECONDS", "3600"))
    job_lease_seconds = int(os.environ.get("WORKER_JOB_LEASE_SECONDS", "900"))

    def request_stop(_signum, _frame) -> None:
        stop_event.set()

    signal.signal(signal.SIGTERM, request_stop)
    signal.signal(signal.SIGINT, request_stop)

    logging.info("worker runtime started: worker_id=%s handlers=%s", worker_id, sorted(registry))
    run_forever(
        queue,
        registry,
        worker_id=worker_id,
        poll_seconds=poll_seconds,
        retry_backoff_seconds=retry_backoff_seconds,
        retry_backoff_max_seconds=retry_backoff_max_seconds,
        job_lease_seconds=job_lease_seconds,
        stop_event=stop_event,
    )
    logging.info("worker runtime stopped: worker_id=%s", worker_id)


def _worker_echo(payload) -> dict[str, object]:
    return {"payload": dict(payload)}


def _sync_miniflux_entries(payload) -> dict[str, object]:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if not database_url:
        raise RuntimeError("SCORING_DATABASE_URL is required for sync_miniflux_entries")
    sink = DatabaseArticleSink(database_url)
    try:
        return run_sync_miniflux_entries(
            dict(payload),
            sink=sink,
            client=MinifluxClient(MinifluxConfig.from_env()),
        )
    finally:
        sink.dispose()


def _fetch_article_content(payload) -> dict[str, object]:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if not database_url:
        raise RuntimeError("SCORING_DATABASE_URL is required for fetch_article_content")
    sink = DatabaseContentSink(database_url)
    try:
        return fetch_article_content(
            dict(payload),
            sink=sink,
            miniflux_client=MinifluxClient(MinifluxConfig.from_env()),
            external_provider=NoExternalContentProvider(),
        )
    finally:
        sink.dispose()


def _score_batch(payload) -> dict[str, object]:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if not database_url:
        raise RuntimeError("SCORING_DATABASE_URL is required for score_batch")
    sink = DatabaseScoreSink(database_url)
    try:
        return score_batch(dict(payload), sink, create_provider())
    finally:
        sink.dispose()


def _generate_recommendations(payload) -> dict[str, object]:
    database_url = normalize_database_url(os.environ.get("SCORING_DATABASE_URL"))
    if not database_url:
        raise RuntimeError("SCORING_DATABASE_URL is required for generate_recommendations")
    source_batch_id = payload.get("source_batch_id")
    sink = DatabaseRecommendationSink(
        database_url,
        source_batch_id=int(source_batch_id) if source_batch_id is not None else None,
    )
    try:
        return generate_recommendations(dict(payload), sink, rank_b4_recommendation_context)
    finally:
        sink.dispose()


if __name__ == "__main__":
    main()
