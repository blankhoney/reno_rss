import logging
import signal
from threading import Event

from app.composition import (
    WorkerRuntimeSettings,
    build_handler_registry,
    close_queue,
    create_worker_queue,
    normalize_database_url,
    touch_worker_heartbeat,
)
from app.runner import run_forever
from app.scheduler import make_tick_callback


LOGGER = logging.getLogger(__name__)

# Compatibility re-exports for existing worker-side callers and tests.
__all__ = [
    "build_handler_registry",
    "create_worker_queue",
    "main",
    "normalize_database_url",
]


def main() -> None:
    settings = WorkerRuntimeSettings.from_env()
    logging.basicConfig(level=settings.log_level)
    queue = create_worker_queue(settings)
    active_error: BaseException | None = None
    try:
        registry = build_handler_registry(settings)
        stop_event = Event()

        def request_stop(_signum, _frame) -> None:
            stop_event.set()

        signal.signal(signal.SIGTERM, request_stop)
        signal.signal(signal.SIGINT, request_stop)

        on_tick = make_tick_callback(queue, enabled=settings.scheduler_enabled)
        LOGGER.info(
            "worker runtime started: worker_id=%s handlers=%s scheduler_enabled=%s",
            settings.worker_id,
            sorted(registry),
            settings.scheduler_enabled,
        )
        run_forever(
            queue,
            registry,
            worker_id=settings.worker_id,
            poll_seconds=settings.poll_seconds,
            retry_backoff_seconds=settings.retry_backoff_seconds,
            retry_backoff_max_seconds=settings.retry_backoff_max_seconds,
            job_lease_seconds=settings.job_lease_seconds,
            stop_event=stop_event,
            on_heartbeat=lambda: touch_worker_heartbeat(settings.heartbeat_file),
            on_tick=on_tick,
        )
    except BaseException as error:
        active_error = error
        raise
    finally:
        try:
            close_queue(queue)
        except BaseException:
            if active_error is None:
                raise
            LOGGER.exception("worker queue disposal failed while preserving runtime error")
    LOGGER.info("worker runtime stopped: worker_id=%s", settings.worker_id)


if __name__ == "__main__":
    main()
