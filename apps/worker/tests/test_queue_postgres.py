from __future__ import annotations

import os
from pathlib import Path
import subprocess
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.jobs.queue import PostgresJobQueue
from app.main import normalize_database_url


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"


def test_postgres_queue_state_machine_sql():
    database_url = os.environ.get("WORKER_QUEUE_POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("set WORKER_QUEUE_POSTGRES_TEST_URL to run the real Postgres queue test")

    _run_api_command(database_url, "alembic", "upgrade", "head")

    normalized_url = normalize_database_url(database_url) or database_url
    engine = create_engine(normalized_url, pool_pre_ping=True)
    queue = PostgresJobQueue(normalized_url, engine=engine)

    try:
        retry_job_id = _enqueue_job(database_url, "worker_postgres_retry", max_attempts=2)
        claimed = queue.claim_next("worker-1")
        assert claimed is not None
        assert claimed.id == retry_job_id
        assert claimed.status == "running"
        assert claimed.attempt_count == 1

        retried = queue.mark_retryable_failure(
            claimed.id,
            "temporary outage",
            worker_id="worker-1",
            base_backoff_seconds=1,
            max_backoff_seconds=30,
        )
        assert retried is not None
        assert retried.status == "queued"
        assert retried.locked_by is None

        with engine.begin() as connection:
            connection.execute(text("UPDATE jobs SET run_after=NOW() WHERE id=:id"), {"id": retry_job_id})

        claimed_again = queue.claim_next("worker-1")
        assert claimed_again is not None
        assert claimed_again.id == retry_job_id
        assert claimed_again.attempt_count == 2

        succeeded = queue.mark_succeeded(
            claimed_again.id,
            {"processed": True},
            worker_id="worker-1",
        )
        assert succeeded is not None
        assert succeeded.status == "succeeded"
        assert succeeded.result == {"processed": True}

        exhausted_job_id = _enqueue_job(database_url, "worker_postgres_exhausted", max_attempts=1)
        exhausted_claim = queue.claim_next("worker-1")
        assert exhausted_claim is not None
        assert exhausted_claim.id == exhausted_job_id

        exhausted = queue.mark_retryable_failure(
            exhausted_claim.id,
            "still down",
            worker_id="worker-1",
            base_backoff_seconds=1,
            max_backoff_seconds=30,
        )
        assert exhausted is not None
        assert exhausted.status == "failed"
        assert exhausted.completed_at is not None
        assert exhausted.last_error == "still down"
    finally:
        queue.dispose()


def _enqueue_job(database_url: str, job_type: str, *, max_attempts: int) -> int:
    dedupe_key = f"{job_type}:{uuid4()}"
    script = f"""
from app.db.repositories.jobs import create_job_repository
repo = create_job_repository({database_url!r})
job = repo.enqueue({job_type!r}, {{"source": "worker-postgres-test"}}, dedupe_key={dedupe_key!r})
with repo.engine.begin() as connection:
    connection.exec_driver_sql("UPDATE jobs SET max_attempts = %s WHERE id = %s", ({max_attempts}, job.id))
print(job.id)
"""
    result = _run_api_command(database_url, "python", "-c", script)
    return int(result.stdout.strip())


def _run_api_command(database_url: str, *command: str) -> subprocess.CompletedProcess[str]:
    env = os.environ.copy()
    env["SCORING_DATABASE_URL"] = database_url
    return subprocess.run(
        ["uv", "run", "--isolated", "--with-editable", ".", "--extra", "dev", *command],
        cwd=API_ROOT,
        env=env,
        check=True,
        capture_output=True,
        text=True,
    )
