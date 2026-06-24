from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import json

from sqlalchemy import Engine, create_engine, text


POSTGRES_CLAIM_SQL = """
UPDATE jobs
SET status='running',
    locked_by=:worker_id,
    locked_at=NOW(),
    attempt_count=attempt_count+1,
    updated_at=NOW()
WHERE id = (
  SELECT id FROM jobs
  WHERE status='queued' AND run_after<=NOW()
  ORDER BY priority DESC, id ASC
  FOR UPDATE SKIP LOCKED
  LIMIT 1
)
RETURNING *;
"""


@dataclass(frozen=True)
class QueueJob:
    id: int
    job_type: str
    payload: dict[str, object]
    dedupe_key: str
    status: str
    priority: int
    locked_by: str | None
    locked_at: datetime | None
    attempt_count: int
    max_attempts: int
    run_after: datetime
    result: dict[str, object]
    completed_at: datetime | None
    last_error: str | None


class InMemoryJobQueue:
    def __init__(self) -> None:
        self._jobs: dict[int, QueueJob] = {}
        self._next_id = 1

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        dedupe_key: str,
        priority: int = 0,
        max_attempts: int = 5,
    ) -> QueueJob:
        for job in self._jobs.values():
            if (
                job.job_type == job_type
                and job.dedupe_key == dedupe_key
                and job.status in {"queued", "running"}
            ):
                return job

        job = QueueJob(
            id=self._next_id,
            job_type=job_type,
            payload=dict(payload),
            dedupe_key=dedupe_key,
            status="queued",
            priority=priority,
            locked_by=None,
            locked_at=None,
            attempt_count=0,
            max_attempts=max_attempts,
            run_after=datetime.now(UTC),
            result={},
            completed_at=None,
            last_error=None,
        )
        self._jobs[job.id] = job
        self._next_id += 1
        return job

    def claim_next(self, worker_id: str) -> QueueJob | None:
        now = datetime.now(UTC)
        candidates = [
            job
            for job in self._jobs.values()
            if job.status == "queued" and job.run_after <= now
        ]
        if not candidates:
            return None

        job = sorted(candidates, key=lambda item: (-item.priority, item.id))[0]
        claimed = replace(
            job,
            status="running",
            locked_by=worker_id,
            locked_at=now,
            attempt_count=job.attempt_count + 1,
        )
        self._jobs[job.id] = claimed
        return claimed

    def mark_succeeded(self, job_id: int, result: dict[str, object]) -> QueueJob | None:
        return self._complete(job_id, status="succeeded", result=result, error=None)

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        backoff_seconds: int,
    ) -> QueueJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if job.attempt_count >= job.max_attempts:
            return self.mark_failed(job_id, error)

        updated = replace(
            job,
            status="queued",
            locked_by=None,
            locked_at=None,
            run_after=datetime.now(UTC) + timedelta(seconds=backoff_seconds),
            last_error=error,
        )
        self._jobs[job_id] = updated
        return updated

    def mark_failed(self, job_id: int, error: str) -> QueueJob | None:
        return self._complete(job_id, status="failed", result={}, error=error)

    def _complete(
        self,
        job_id: int,
        *,
        status: str,
        result: dict[str, object],
        error: str | None,
    ) -> QueueJob | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        updated = replace(
            job,
            status=status,
            result=dict(result),
            last_error=error,
            completed_at=datetime.now(UTC),
        )
        self._jobs[job_id] = updated
        return updated


class PostgresJobQueue:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def claim_next(self, worker_id: str) -> QueueJob | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(text(POSTGRES_CLAIM_SQL), {"worker_id": worker_id})
                .mappings()
                .one_or_none()
            )
        return _queue_job_from_row(row) if row is not None else None

    def mark_succeeded(self, job_id: int, result: dict[str, object]) -> QueueJob | None:
        row = self._execute_update(
            """
            UPDATE jobs
            SET status='succeeded',
                result=CAST(:result AS jsonb),
                completed_at=NOW(),
                last_error=NULL,
                updated_at=NOW()
            WHERE id=:job_id
            RETURNING *;
            """,
            {"job_id": job_id, "result": json.dumps(result)},
        )
        return _queue_job_from_row(row) if row is not None else None

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        backoff_seconds: int,
    ) -> QueueJob | None:
        with self.engine.begin() as connection:
            job = (
                connection.execute(
                    text(
                        """
                        SELECT attempt_count, max_attempts
                        FROM jobs
                        WHERE id=:job_id
                        FOR UPDATE;
                        """
                    ),
                    {"job_id": job_id},
                )
                .mappings()
                .one_or_none()
            )
            if job is None:
                return None
            if job["attempt_count"] >= job["max_attempts"]:
                row = (
                    connection.execute(
                        text(
                            """
                            UPDATE jobs
                            SET status='failed',
                                last_error=:error,
                                completed_at=NOW(),
                                updated_at=NOW()
                            WHERE id=:job_id
                            RETURNING *;
                            """
                        ),
                        {"job_id": job_id, "error": error},
                    )
                    .mappings()
                    .one_or_none()
                )
            else:
                row = (
                    connection.execute(
                        text(
                            """
                            UPDATE jobs
                            SET status='queued',
                                locked_by=NULL,
                                locked_at=NULL,
                                run_after=:run_after,
                                last_error=:error,
                                updated_at=NOW()
                            WHERE id=:job_id
                            RETURNING *;
                            """
                        ),
                        {
                            "job_id": job_id,
                            "error": error,
                            "run_after": datetime.now(UTC) + timedelta(seconds=backoff_seconds),
                        },
                    )
                    .mappings()
                    .one_or_none()
                )
        return _queue_job_from_row(row) if row is not None else None

    def mark_failed(self, job_id: int, error: str) -> QueueJob | None:
        row = self._execute_update(
            """
            UPDATE jobs
            SET status='failed',
                last_error=:error,
                completed_at=NOW(),
                updated_at=NOW()
            WHERE id=:job_id
            RETURNING *;
            """,
            {"job_id": job_id, "error": error},
        )
        return _queue_job_from_row(row) if row is not None else None

    def dispose(self) -> None:
        self.engine.dispose()

    def _execute_update(self, statement: str, params: dict[str, object]):
        with self.engine.begin() as connection:
            return connection.execute(text(statement), params).mappings().one_or_none()


def _queue_job_from_row(row) -> QueueJob:
    return QueueJob(
        id=row["id"],
        job_type=row["job_type"],
        payload=row["payload"],
        dedupe_key=row["dedupe_key"],
        status=row["status"],
        priority=row["priority"],
        locked_by=row["locked_by"],
        locked_at=row["locked_at"],
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        run_after=row["run_after"],
        result=row["result"] or {},
        completed_at=row["completed_at"],
        last_error=row["last_error"],
    )
