from app.jobs.queue import InMemoryJobQueue, PostgresJobQueue


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
