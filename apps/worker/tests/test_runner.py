from datetime import UTC, datetime

from app.jobs.queue import InMemoryJobQueue
from app.runner import RetryableJobError, run_once


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
