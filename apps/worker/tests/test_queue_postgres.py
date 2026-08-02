from __future__ import annotations

import json
import os
from pathlib import Path
import subprocess
import sys
from uuid import uuid4

import pytest
from sqlalchemy import create_engine, text

from app.jobs.queue import PostgresJobQueue
from app.main import normalize_database_url


REPO_ROOT = Path(__file__).resolve().parents[3]
API_ROOT = REPO_ROOT / "apps" / "api"
WORKER_ROOT = REPO_ROOT / "apps" / "worker"


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

        renewed = queue.renew_lease(claimed.id, worker_id="worker-1")
        assert renewed is not None
        assert renewed.status == "running"
        assert renewed.locked_by == "worker-1"
        assert renewed.attempt_count == claimed.attempt_count
        assert queue.renew_lease(claimed.id, worker_id="worker-2") is None

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

        stale_job_id = _enqueue_job(database_url, "worker_postgres_stale", max_attempts=2)
        stale_claim = queue.claim_next("worker-before-restart")
        assert stale_claim is not None
        assert stale_claim.id == stale_job_id

        with engine.begin() as connection:
            connection.execute(
                text(
                    "UPDATE jobs SET locked_at=NOW() - INTERVAL '2 seconds' WHERE id=:id"
                ),
                {"id": stale_job_id},
            )

        reclaimed = queue.reclaim_stale(
            lease_seconds=1,
            base_backoff_seconds=1,
            max_backoff_seconds=30,
        )
        assert [job.id for job in reclaimed] == [stale_job_id]
        assert reclaimed[0].status == "queued"
        assert reclaimed[0].locked_by is None
        assert reclaimed[0].last_error == "job lease expired"

        with engine.begin() as connection:
            connection.execute(text("UPDATE jobs SET run_after=NOW() WHERE id=:id"), {"id": stale_job_id})

        recovered_claim = queue.claim_next("worker-after-restart")
        assert recovered_claim is not None
        assert recovered_claim.id == stale_job_id
        assert recovered_claim.attempt_count == 2
        recovered = queue.mark_succeeded(
            recovered_claim.id,
            {"recovered_after_lease": True},
            worker_id="worker-after-restart",
        )
        assert recovered is not None
        assert recovered.status == "succeeded"
        assert recovered.result == {"recovered_after_lease": True}

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


def test_queue_recovery_baseline_claims_its_synthetic_job_when_other_work_is_ready(tmp_path):
    database_url = os.environ.get("WORKER_QUEUE_POSTGRES_TEST_URL")
    if not database_url:
        pytest.skip("set WORKER_QUEUE_POSTGRES_TEST_URL to run the real Postgres queue test")

    _run_api_command(database_url, "alembic", "upgrade", "head")

    normalized_url = normalize_database_url(database_url) or database_url
    engine = create_engine(normalized_url, pool_pre_ping=True)
    competing_dedupe_key = f"queue-recovery-competing-job:{uuid4()}"
    output_path = tmp_path / "queue-recovery.json"
    try:
        with engine.begin() as connection:
            competing_job_id = connection.execute(
                text(
                    """
                    INSERT INTO jobs (job_type, payload, dedupe_key, priority)
                    VALUES ('queue_recovery_competitor', '{}'::jsonb, :dedupe_key, 1)
                    RETURNING id
                    """
                ),
                {"dedupe_key": competing_dedupe_key},
            ).scalar_one()

        env = os.environ.copy()
        env["QUEUE_RECOVERY_DATABASE_URL"] = database_url
        result = subprocess.run(
            [
                sys.executable,
                "scripts/queue-recovery-baseline.py",
                "--iterations",
                "1",
                "--warmups",
                "1",
                "--output",
                str(output_path),
            ],
            cwd=WORKER_ROOT,
            env=env,
            capture_output=True,
            text=True,
        )

        assert result.returncode == 0, result.stdout + result.stderr
        report = json.loads(output_path.read_text(encoding="utf-8"))
        assert report["status"] == "MEASURED"
        assert len(report["samples"]) == 1
        with engine.begin() as connection:
            competing_status = connection.execute(
                text("SELECT status FROM jobs WHERE id=:id"),
                {"id": competing_job_id},
            ).scalar_one()
        assert competing_status == "queued"
    finally:
        with engine.begin() as connection:
            connection.execute(
                text("DELETE FROM jobs WHERE dedupe_key=:dedupe_key"),
                {"dedupe_key": competing_dedupe_key},
            )
        engine.dispose()


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
