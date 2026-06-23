import pytest


pytestmark = pytest.mark.asyncio


async def test_duplicate_fetch_content_job_returns_existing_job(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    first = await client.post("/api/articles/1/fetch-content")
    second = await client.post("/api/articles/1/fetch-content")

    assert first.status_code == 202
    assert second.status_code == 202
    assert first.json()["job_id"] == second.json()["job_id"]
    assert first.json()["status"] == "queued"


async def test_current_user_can_view_own_job(client):
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    created = await client.post("/api/articles/1/fetch-content")

    response = await client.get(f"/api/jobs/{created.json()['job_id']}")

    assert response.status_code == 200
    assert response.json()["id"] == created.json()["job_id"]
    assert response.json()["job_type"] == "fetch_article_content"
    assert set(response.json()) == {
        "id",
        "job_type",
        "status",
        "progress",
        "result",
        "last_error",
        "created_at",
        "updated_at",
        "completed_at",
    }


async def test_second_user_can_poll_deduped_fetch_content_job(app):
    from httpx import ASGITransport, AsyncClient

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
    ) as first_client:
        await first_client.post("/api/auth/login", json={"display_name": "First"})
        first = await first_client.post("/api/articles/1/fetch-content")

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://test",
    ) as second_client:
        await second_client.post("/api/auth/login", json={"display_name": "Second"})
        second = await second_client.post("/api/articles/1/fetch-content")
        response = await second_client.get(f"/api/jobs/{second.json()['job_id']}")

    assert second.status_code == 202
    assert second.json()["job_id"] == first.json()["job_id"]
    assert response.status_code == 200
    assert response.json()["id"] == first.json()["job_id"]


async def test_user_cannot_view_system_job(app, client):
    system_job = app.state.job_repository.enqueue(
        "sync_miniflux_entries",
        {"since": "latest"},
        dedupe_key="sync:latest",
        created_by=None,
    )
    await client.post("/api/auth/login", json={"display_name": "Blank"})

    response = await client.get(f"/api/jobs/{system_job.id}")

    assert response.status_code == 404
    assert response.json()["error"]["code"] == "not_found"


async def test_admin_can_view_system_job(app, client):
    system_job = app.state.job_repository.enqueue(
        "sync_miniflux_entries",
        {"since": "latest"},
        dedupe_key="sync:latest",
        created_by=None,
    )
    _admin, session_token, _recovery_code = app.state.auth_store.create_user(
        display_name="Admin",
        role="admin",
    )
    client.cookies.set("ar_session", session_token)

    response = await client.get(f"/api/jobs/{system_job.id}")

    assert response.status_code == 200
    assert response.json()["id"] == system_job.id


async def test_database_job_repository_claim_uses_skip_locked():
    from app.db.repositories.jobs import DatabaseJobRepository

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

    class FakeDialect:
        name = "postgresql"

    class FakeEngine:
        def __init__(self):
            self.dialect = FakeDialect()
            self.connection = FakeConnection()

        def begin(self):
            return FakeBegin(self.connection)

    engine = FakeEngine()
    repository = DatabaseJobRepository(
        "postgresql+psycopg://postgres:postgres@localhost/test",
        engine=engine,
    )

    claimed = repository.claim_next("worker-1")

    assert claimed is None
    assert "FOR UPDATE SKIP LOCKED" in str(engine.connection.statement)
    assert engine.connection.params == {"worker_id": "worker-1"}


async def test_database_enqueue_retries_when_conflicting_job_finishes_before_reselect():
    from datetime import UTC, datetime
    from uuid import uuid4

    from app.db.repositories.jobs import DatabaseJobRepository

    user_id = uuid4()
    now = datetime.now(UTC)
    inserted_job = {
        "id": 42,
        "job_type": "fetch_article_content",
        "status": "queued",
        "priority": 0,
        "payload": {"article_id": 1},
        "dedupe_key": "fetch:1",
        "progress": {},
        "result": {},
        "locked_by": None,
        "locked_at": None,
        "attempt_count": 0,
        "max_attempts": 5,
        "run_after": now,
        "completed_at": None,
        "last_error": None,
        "created_by": user_id,
        "created_at": now,
        "updated_at": now,
    }

    class FakeScalarResult:
        def __init__(self, row):
            self.row = row

        def one_or_none(self):
            return self.row

        def one(self):
            return self.row

    class FakeMappingResult:
        def __init__(self, row):
            self.row = row

        def mappings(self):
            return FakeScalarResult(self.row)

    class FakeConnection:
        def __init__(self):
            self.insert_attempts = 0
            self.select_attempts = 0
            self.watcher_inserts = 0

        def execute(self, statement):
            statement_text = str(statement)
            if "INSERT INTO jobs" in statement_text:
                self.insert_attempts += 1
                if self.insert_attempts == 1:
                    return FakeMappingResult(None)
                return FakeMappingResult(inserted_job)
            if "SELECT jobs.id" in statement_text:
                self.select_attempts += 1
                return FakeMappingResult(None)
            if "INSERT INTO job_watchers" in statement_text:
                self.watcher_inserts += 1
                return FakeMappingResult(None)
            return FakeMappingResult(None)

    class FakeBegin:
        def __init__(self, connection):
            self.connection = connection

        def __enter__(self):
            return self.connection

        def __exit__(self, *_args):
            return None

    class FakeDialect:
        name = "postgresql"

    class FakeEngine:
        def __init__(self):
            self.dialect = FakeDialect()
            self.connection = FakeConnection()

        def begin(self):
            return FakeBegin(self.connection)

    engine = FakeEngine()
    repository = DatabaseJobRepository(
        "postgresql+psycopg://postgres:postgres@localhost/test",
        engine=engine,
    )

    job = repository.enqueue(
        "fetch_article_content",
        {"article_id": 1},
        dedupe_key="fetch:1",
        created_by=user_id,
    )

    assert job.id == 42
    assert engine.connection.insert_attempts == 2
    assert engine.connection.select_attempts == 1
    assert engine.connection.watcher_inserts == 1
