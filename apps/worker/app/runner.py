from __future__ import annotations

from collections.abc import Callable, Mapping
import logging
from threading import Event
from typing import Protocol


LOGGER = logging.getLogger(__name__)

Handler = Callable[[Mapping[str, object]], Mapping[str, object] | None]


class JobQueue(Protocol):
    def reclaim_stale(
        self,
        *,
        lease_seconds: int,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> list[object]: ...

    def claim_next(self, worker_id: str): ...

    def mark_succeeded(
        self,
        job_id: int,
        result: dict[str, object],
        *,
        worker_id: str,
    ): ...

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        *,
        worker_id: str,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ): ...

    def mark_failed(self, job_id: int, error: str, *, worker_id: str): ...


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
) -> bool:
    queue.reclaim_stale(
        lease_seconds=job_lease_seconds,
        base_backoff_seconds=retry_backoff_seconds,
        max_backoff_seconds=retry_backoff_max_seconds,
    )
    job = queue.claim_next(worker_id)
    if job is None:
        return False

    handler = registry.get(job.job_type)
    if handler is None:
        queue.mark_failed(job.id, f"unknown job_type: {job.job_type}", worker_id=worker_id)
        return True

    try:
        result = _normalize_result(handler(job.payload))
    except RetryableJobError as error:
        queue.mark_retryable_failure(
            job.id,
            str(error),
            worker_id=worker_id,
            base_backoff_seconds=retry_backoff_seconds,
            max_backoff_seconds=retry_backoff_max_seconds,
        )
    except Exception as error:
        LOGGER.exception("worker job failed: job_id=%s job_type=%s", job.id, job.job_type)
        queue.mark_failed(job.id, str(error), worker_id=worker_id)
    else:
        queue.mark_succeeded(job.id, result, worker_id=worker_id)
    return True


def run_forever(
    queue: JobQueue,
    registry: Mapping[str, Handler],
    *,
    worker_id: str,
    poll_seconds: float = 2.0,
    retry_backoff_seconds: int = 60,
    retry_backoff_max_seconds: int = 3600,
    job_lease_seconds: int = 900,
    stop_event: Event | None = None,
) -> None:
    stop_event = stop_event or Event()
    while not stop_event.is_set():
        handled = run_once(
            queue,
            registry,
            worker_id=worker_id,
            retry_backoff_seconds=retry_backoff_seconds,
            retry_backoff_max_seconds=retry_backoff_max_seconds,
            job_lease_seconds=job_lease_seconds,
        )
        if not handled:
            stop_event.wait(poll_seconds)


def _normalize_result(result: Mapping[str, object] | None) -> dict[str, object]:
    if result is None:
        return {}
    if not isinstance(result, Mapping):
        raise TypeError("job handler must return a mapping or None")
    return dict(result)
