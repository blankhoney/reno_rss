from dataclasses import replace
from datetime import UTC, datetime, timedelta

from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue, retry_backoff_seconds


def test_worker_claims_one_queued_job():
    queue = InMemoryJobQueue()
    queue.enqueue("fetch_article_content", {"article_id": 1}, dedupe_key="fetch:1")

    claimed = queue.claim_next(worker_id="test-worker")

    assert claimed is not None
    assert claimed.job_type == "fetch_article_content"
    assert claimed.status == "running"
    assert claimed.locked_by == "test-worker"
    assert claimed.attempt_count == 1


def test_worker_claims_highest_priority_then_lowest_id():
    queue = InMemoryJobQueue()
    low = queue.enqueue("fetch_article_content", {"article_id": 1}, dedupe_key="fetch:1")
    high = queue.enqueue("fetch_article_content", {"article_id": 2}, dedupe_key="fetch:2", priority=10)

    first = queue.claim_next(worker_id="test-worker")
    second = queue.claim_next(worker_id="test-worker")

    assert first is not None
    assert second is not None
    assert first.id == high.id
    assert second.id == low.id


def test_postgres_worker_claim_uses_skip_locked():
    class FakeScalarResult:
        def one_or_none(self):
            return None

    class FakeMappingResult:
        def mappings(self):
            return FakeScalarResult()

    class FakeConnection:
        def __init__(self):
            self.statement = None
            self.params = None

        def execute(self, statement, params=None):
            self.statement = statement
            self.params = params
            return FakeMappingResult()

    class FakeBegin:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *_args):
            return None

    class FakeEngine:
        def __init__(self):
            self.connection = FakeConnection()

        def begin(self):
            return FakeBegin(self.connection)

    engine = FakeEngine()
    queue = PostgresJobQueue("postgresql+psycopg://postgres:postgres@localhost/test", engine=engine)

    claimed = queue.claim_next("worker-1")

    assert claimed is None
    assert "FOR UPDATE SKIP LOCKED" in str(engine.connection.statement)
    assert engine.connection.params == {"worker_id": "worker-1"}


def test_worker_queue_factory_normalizes_postgres_url(monkeypatch):
    from app.main import create_worker_queue

    monkeypatch.setenv("SCORING_DATABASE_URL", "postgres://postgres:postgres@localhost/test")

    queue = create_worker_queue()

    assert isinstance(queue, PostgresJobQueue)
    assert queue.engine.url.drivername == "postgresql+psycopg"
    queue.dispose()


def test_retry_backoff_is_exponential_and_capped():
    assert retry_backoff_seconds(1, base_seconds=30, max_seconds=300) == 30
    assert retry_backoff_seconds(2, base_seconds=30, max_seconds=300) == 60
    assert retry_backoff_seconds(4, base_seconds=30, max_seconds=300) == 240
    assert retry_backoff_seconds(5, base_seconds=30, max_seconds=300) == 300


def test_reclaim_stale_running_job_requeues_with_backoff():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fetch_article_content", {"article_id": 1}, dedupe_key="fetch:1")
    claimed = queue.claim_next(worker_id="worker-1")
    assert claimed is not None
    stale_locked_at = datetime.now(UTC) - timedelta(seconds=901)
    queue._jobs[job.id] = replace(claimed, locked_at=stale_locked_at)

    reclaimed = queue.reclaim_stale(
        lease_seconds=900,
        base_backoff_seconds=30,
        max_backoff_seconds=300,
    )

    stored = queue._jobs[job.id]
    assert [item.id for item in reclaimed] == [job.id]
    assert stored.status == "queued"
    assert stored.locked_by is None
    assert stored.locked_at is None
    assert stored.last_error == "job lease expired"
    assert stored.run_after > datetime.now(UTC)


def test_reclaim_stale_running_job_does_not_steal_fresh_job():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fetch_article_content", {"article_id": 1}, dedupe_key="fetch:1")
    claimed = queue.claim_next(worker_id="worker-1")
    assert claimed is not None
    queue._jobs[job.id] = replace(claimed, locked_at=datetime.now(UTC))

    reclaimed = queue.reclaim_stale(
        lease_seconds=900,
        base_backoff_seconds=30,
        max_backoff_seconds=300,
    )

    assert reclaimed == []
    assert queue._jobs[job.id].status == "running"
    assert queue._jobs[job.id].locked_by == "worker-1"


def test_reclaim_stale_running_job_fails_when_attempts_are_exhausted():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fetch_article_content", {}, dedupe_key="fetch:1", max_attempts=1)
    claimed = queue.claim_next(worker_id="worker-1")
    assert claimed is not None
    stale_locked_at = datetime.now(UTC) - timedelta(seconds=901)
    queue._jobs[job.id] = replace(claimed, locked_at=stale_locked_at)

    queue.reclaim_stale(
        lease_seconds=900,
        base_backoff_seconds=30,
        max_backoff_seconds=300,
    )

    stored = queue._jobs[job.id]
    assert stored.status == "failed"
    assert stored.last_error == "job lease expired"
    assert stored.completed_at is not None


def test_terminal_writes_require_running_owner():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fetch_article_content", {}, dedupe_key="fetch:1")
    claimed = queue.claim_next(worker_id="worker-1")
    assert claimed is not None

    assert queue.mark_succeeded(job.id, {"ok": True}, worker_id="worker-2") is None
    assert queue.mark_failed(job.id, "wrong owner", worker_id="worker-2") is None
    assert (
        queue.mark_retryable_failure(
            job.id,
            "wrong owner",
            worker_id="worker-2",
            base_backoff_seconds=30,
            max_backoff_seconds=300,
        )
        is None
    )

    stored = queue._jobs[job.id]
    assert stored.status == "running"
    assert stored.locked_by == "worker-1"
    assert stored.last_error is None


def test_cancelled_job_is_not_claimed_or_overwritten_by_terminal_write():
    queue = InMemoryJobQueue()
    job = queue.enqueue("fetch_article_content", {}, dedupe_key="fetch:1")
    cancelled = queue.mark_cancelled(job.id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"

    assert queue.claim_next(worker_id="worker-1") is None
    assert queue.mark_succeeded(job.id, {"ok": True}, worker_id="worker-1") is None
    stored = queue._jobs[job.id]
    assert stored.status == "cancelled"
    assert stored.result == {}
