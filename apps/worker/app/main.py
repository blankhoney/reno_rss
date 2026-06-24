import os
import signal
import socket
from threading import Event

from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue
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
    return {"worker_echo": _worker_echo}


def main() -> None:
    import logging

    logging.basicConfig(level=os.environ.get("WORKER_LOG_LEVEL", "INFO"))
    queue = create_worker_queue()
    registry = build_handler_registry()
    stop_event = Event()
    worker_id = os.environ.get("WORKER_ID") or f"{socket.gethostname()}:{os.getpid()}"
    poll_seconds = float(os.environ.get("WORKER_POLL_SECONDS", "2"))
    retry_backoff_seconds = int(os.environ.get("WORKER_RETRY_BACKOFF_SECONDS", "60"))

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
        stop_event=stop_event,
    )
    logging.info("worker runtime stopped: worker_id=%s", worker_id)


def _worker_echo(payload) -> dict[str, object]:
    return {"payload": dict(payload)}


if __name__ == "__main__":
    main()
