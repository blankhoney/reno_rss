from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
from threading import Event, Thread
from typing import Protocol

from app.jobs.queue import QueueJob


LOGGER = logging.getLogger(__name__)

Handler = Callable[[Mapping[str, object]], object]


class JobQueue(Protocol):
    def reclaim_stale(
        self,
        *,
        lease_seconds: int,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> list[QueueJob]: ...

    def claim_next(self, worker_id: str) -> QueueJob | None: ...

    def renew_lease(self, job_id: int, *, worker_id: str) -> QueueJob | None: ...

    def mark_succeeded(
        self,
        job_id: int,
        result: dict[str, object],
        *,
        worker_id: str,
    ) -> QueueJob | None: ...

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        *,
        worker_id: str,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> QueueJob | None: ...

    def mark_failed(self, job_id: int, error: str, *, worker_id: str) -> QueueJob | None: ...


class RetryableJobError(RuntimeError):
    """Transient failure; queue may retry according to max_attempts."""


def run_once(
    queue: JobQueue,
    registry: Mapping[str, Handler],
    *,
    worker_id: str,
    retry_backoff_seconds: int = 60,
    retry_backoff_max_seconds: int = 3600,
    job_lease_seconds: int = 900,
    lease_renew_interval_seconds: float | None = None,
) -> bool:
    reclaimed = queue.reclaim_stale(
        lease_seconds=job_lease_seconds,
        base_backoff_seconds=retry_backoff_seconds,
        max_backoff_seconds=retry_backoff_max_seconds,
    )
    if reclaimed:
        LOGGER.info(
            "worker stale lease recovery: worker_id=%s recovered_count=%s lease_seconds=%s",
            worker_id,
            len(reclaimed),
            job_lease_seconds,
        )
    job = queue.claim_next(worker_id)
    if job is None:
        return False

    handler = registry.get(job.job_type)
    if handler is None:
        queue.mark_failed(job.id, f"unknown job_type: {job.job_type}", worker_id=worker_id)
        return True

    renewal_stop = Event()
    renewal_thread = _start_lease_renewer(
        queue,
        job.id,
        worker_id=worker_id,
        interval_seconds=lease_renew_interval_seconds
        if lease_renew_interval_seconds is not None
        else _lease_renew_interval_seconds(job_lease_seconds),
        stop_event=renewal_stop,
    )
    terminal_action: tuple[str, object]
    try:
        try:
            result = _normalize_result(handler(job.payload))
        except RetryableJobError as error:
            terminal_action = ("retry", str(error))
        except Exception as error:
            LOGGER.exception("worker job failed: job_id=%s job_type=%s", job.id, job.job_type)
            terminal_action = ("failed", str(error))
        else:
            terminal_action = ("succeeded", result)
    finally:
        renewal_stop.set()
        renewal_thread.join()

    action, value = terminal_action
    if action == "retry":
        queue.mark_retryable_failure(
            job.id,
            str(value),
            worker_id=worker_id,
            base_backoff_seconds=retry_backoff_seconds,
            max_backoff_seconds=retry_backoff_max_seconds,
        )
    elif action == "failed":
        queue.mark_failed(job.id, str(value), worker_id=worker_id)
    else:
        queue.mark_succeeded(job.id, value if isinstance(value, dict) else {}, worker_id=worker_id)
    return True


def _lease_renew_interval_seconds(job_lease_seconds: int) -> float:
    return max(0.1, job_lease_seconds / 3)


def _start_lease_renewer(
    queue: JobQueue,
    job_id: int,
    *,
    worker_id: str,
    interval_seconds: float,
    stop_event: Event,
) -> Thread:
    interval_seconds = max(0.01, interval_seconds)

    def renew_until_stopped() -> None:
        while not stop_event.wait(interval_seconds):
            try:
                renewed = queue.renew_lease(job_id, worker_id=worker_id)
            except Exception:
                LOGGER.exception(
                    "worker lease renewal failed: job_id=%s worker_id=%s",
                    job_id,
                    worker_id,
                )
                continue
            if renewed is None:
                LOGGER.warning(
                    "worker lease ownership lost: job_id=%s worker_id=%s",
                    job_id,
                    worker_id,
                )
                return

    thread = Thread(target=renew_until_stopped, name=f"lease-renew-{job_id}", daemon=True)
    thread.start()
    return thread


def run_forever(
    queue: JobQueue,
    registry: Mapping[str, Handler],
    *,
    worker_id: str,
    poll_seconds: float = 2.0,
    retry_backoff_seconds: int = 60,
    retry_backoff_max_seconds: int = 3600,
    job_lease_seconds: int = 900,
    lease_renew_interval_seconds: float | None = None,
    stop_event: Event | None = None,
    on_heartbeat: Callable[[], None] | None = None,
    on_tick: Callable[[], None] | None = None,
) -> None:
    stop_event = stop_event or Event()
    while not stop_event.is_set():
        _emit_heartbeat(on_heartbeat)
        if on_tick is not None:
            try:
                on_tick()
            except Exception:
                LOGGER.exception("scheduler tick failed")
        try:
            handled = run_once(
                queue,
                registry,
                worker_id=worker_id,
                retry_backoff_seconds=retry_backoff_seconds,
                retry_backoff_max_seconds=retry_backoff_max_seconds,
                job_lease_seconds=job_lease_seconds,
                lease_renew_interval_seconds=lease_renew_interval_seconds,
            )
        except Exception:
            LOGGER.exception("worker queue unavailable, will retry")
            handled = False
        _emit_heartbeat(on_heartbeat)
        if not handled:
            stop_event.wait(poll_seconds)


def _normalize_result(result: object) -> dict[str, object]:
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise TypeError("job handler must return a mapping or None")
    return dict(result)


def _emit_heartbeat(on_heartbeat: Callable[[], None] | None) -> None:
    if on_heartbeat is not None:
        on_heartbeat()
