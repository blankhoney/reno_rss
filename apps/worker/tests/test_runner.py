from dataclasses import replace
from datetime import UTC, datetime, timedelta
import logging
from threading import Event

from app.jobs.queue import InMemoryJobQueue
from app.runner import RetryableJobError, run_forever, run_once


def test_run_once_marks_job_succeeded_with_result():
    queue = InMemoryJobQueue()
    job = queue.enqueue("worker_echo", {"message": "ok"}, dedupe_key="echo:ok")

    handled = run_once(
        queue,
        {"worker_echo": lambda payload: {"echo": payload["message"]}},
        worker_id="worker-1",
    )

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "succeeded"
    assert stored.result == {"echo": "ok"}
    assert stored.completed_at is not None
    assert stored.last_error is None
    assert stored.attempt_count == 1


def test_run_once_requeues_retryable_failure_with_backoff():
    queue = InMemoryJobQueue()
    job = queue.enqueue("transient", {}, dedupe_key="transient:1")
    before = datetime.now(UTC)

    def handler(_payload):
        raise RetryableJobError("upstream timeout")

    handled = run_once(
        queue,
        {"transient": handler},
        worker_id="worker-1",
        retry_backoff_seconds=30,
    )

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "queued"
    assert stored.locked_by is None
    assert stored.locked_at is None
    assert stored.last_error == "upstream timeout"
    assert stored.completed_at is None
    assert stored.run_after >= before
    assert (stored.run_after - before).total_seconds() >= 29
    assert stored.attempt_count == 1


def test_run_once_fails_retryable_job_when_attempts_exhausted():
    queue = InMemoryJobQueue()
    job = queue.enqueue("transient", {}, dedupe_key="transient:1", max_attempts=1)

    def handler(_payload):
        raise RetryableJobError("still unavailable")

    handled = run_once(
        queue,
        {"transient": handler},
        worker_id="worker-1",
        retry_backoff_seconds=30,
    )

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "failed"
    assert stored.last_error == "still unavailable"
    assert stored.completed_at is not None
    assert stored.attempt_count == 1


def test_run_once_marks_unknown_job_type_failed_without_crashing():
    queue = InMemoryJobQueue()
    job = queue.enqueue("missing_handler", {}, dedupe_key="missing:1")

    handled = run_once(queue, {}, worker_id="worker-1")

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "failed"
    assert "unknown job_type" in (stored.last_error or "")
    assert stored.completed_at is not None


def test_run_once_marks_fatal_exception_failed():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fatal", {}, dedupe_key="fatal:1")

    def handler(_payload):
        raise ValueError("bad payload")

    handled = run_once(queue, {"fatal": handler}, worker_id="worker-1")

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "failed"
    assert stored.result == {}
    assert stored.last_error == "bad payload"
    assert stored.completed_at is not None


def test_run_once_returns_false_when_no_job_is_ready():
    queue = InMemoryJobQueue()

    handled = run_once(queue, {"worker_echo": lambda payload: payload}, worker_id="worker-1")

    assert handled is False


def test_run_once_logs_stale_lease_recovery(caplog):
    queue = InMemoryJobQueue()
    job = queue.enqueue("worker_echo", {"message": "recover"}, dedupe_key="recover:1")
    claimed = queue.claim_next(worker_id="worker-before-restart")
    assert claimed is not None
    queue._jobs[job.id] = replace(
        claimed,
        locked_at=datetime.now(UTC) - timedelta(seconds=2),
    )

    caplog.set_level(logging.INFO, logger="app.runner")
    handled = run_once(
        queue,
        {"worker_echo": lambda payload: {"echo": payload["message"]}},
        worker_id="worker-after-restart",
        job_lease_seconds=1,
        retry_backoff_seconds=1,
        retry_backoff_max_seconds=30,
    )

    assert handled is False
    assert "worker stale lease recovery: worker_id=worker-after-restart recovered_count=1 lease_seconds=1" in caplog.text


def test_run_forever_survives_transient_queue_outage_and_processes_jobs_after_recovery():
    queue = InMemoryJobQueue()
    outage_active = True

    class OutageQueue:
        def __getattr__(self, name):
            return getattr(queue, name)

        def reclaim_stale(self, **kwargs):
            if outage_active:
                raise RuntimeError("connection refused")
            return queue.reclaim_stale(**kwargs)

        def claim_next(self, worker_id):
            if outage_active:
                raise RuntimeError("connection refused")
            return queue.claim_next(worker_id)

    job = queue.enqueue("worker_echo", {"message": "after-outage"}, dedupe_key="outage:1")
    stop = Event()
    ticks = []

    def on_tick():
        ticks.append(1)
        if len(ticks) >= 3:
            nonlocal outage_active
            outage_active = False
        if len(ticks) >= 5:
            stop.set()

    run_forever(
        OutageQueue(),
        {"worker_echo": lambda payload: {"echo": payload["message"]}},
        worker_id="worker-resilient",
        poll_seconds=0.01,
        stop_event=stop,
        on_tick=on_tick,
    )

    stored = queue._jobs[job.id]
    assert stored.status == "succeeded"
    assert stored.result == {"echo": "after-outage"}


def test_run_once_logs_permanent_failure_for_observability(caplog):
    queue = InMemoryJobQueue()
    queue.enqueue("doomed", {"attempt": 1}, dedupe_key="doomed:1", max_attempts=1)

    def handler(_payload):
        raise RetryableJobError("service gone")

    caplog.set_level(logging.ERROR, logger="app.runner")
    run_once(queue, {"doomed": handler}, worker_id="worker-obs")

    stored = list(queue._jobs.values())[0]
    assert stored.status == "failed"
    assert stored.last_error == "service gone"


def test_run_forever_emits_heartbeat_while_idle():
    queue = InMemoryJobQueue()
    stop_event = Event()
    heartbeats = 0

    def heartbeat():
        nonlocal heartbeats
        heartbeats += 1
        if heartbeats >= 2:
            stop_event.set()

    run_forever(
        queue,
        {"worker_echo": lambda payload: payload},
        worker_id="worker-1",
        poll_seconds=0,
        stop_event=stop_event,
        on_heartbeat=heartbeat,
    )

    assert heartbeats == 2
