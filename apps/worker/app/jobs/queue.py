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


def retry_backoff_seconds(attempt_count: int, *, base_seconds: int, max_seconds: int) -> int:
    effective_attempt = max(1, attempt_count)
    return min(max_seconds, max(0, base_seconds) * (2 ** (effective_attempt - 1)))


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

    def reclaim_stale(
        self,
        *,
        lease_seconds: int,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> list[QueueJob]:
        cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        reclaimed: list[QueueJob] = []
        for job in list(self._jobs.values()):
            if job.status != "running":
                continue
            if job.locked_at is not None and job.locked_at >= cutoff:
                continue
            reclaimed.append(
                self._retry_or_fail(
                    job,
                    "job lease expired",
                    base_backoff_seconds=base_backoff_seconds,
                    max_backoff_seconds=max_backoff_seconds,
                )
            )
        return reclaimed

    def mark_succeeded(
        self,
        job_id: int,
        result: dict[str, object],
        *,
        worker_id: str,
    ) -> QueueJob | None:
        return self._complete(
            job_id,
            status="succeeded",
            result=result,
            error=None,
            worker_id=worker_id,
        )

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        *,
        worker_id: str,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> QueueJob | None:
        job = self._jobs.get(job_id)
        if not self._is_running_owner(job, worker_id):
            return None
        return self._retry_or_fail(
            job,
            error,
            base_backoff_seconds=base_backoff_seconds,
            max_backoff_seconds=max_backoff_seconds,
        )

    def mark_failed(self, job_id: int, error: str, *, worker_id: str) -> QueueJob | None:
        return self._complete(job_id, status="failed", result={}, error=error, worker_id=worker_id)

    def mark_cancelled(self, job_id: int, *, worker_id: str | None = None) -> QueueJob | None:
        job = self._jobs.get(job_id)
        if job is None or job.status not in {"queued", "running"}:
            return None
        if worker_id is not None and not self._is_running_owner(job, worker_id):
            return None
        updated = replace(
            job,
            status="cancelled",
            locked_by=None,
            locked_at=None,
            completed_at=datetime.now(UTC),
        )
        self._jobs[job_id] = updated
        return updated

    def _retry_or_fail(
        self,
        job: QueueJob,
        error: str,
        *,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> QueueJob:
        if job.attempt_count >= job.max_attempts:
            updated = replace(
                job,
                status="failed",
                result={},
                last_error=error,
                completed_at=datetime.now(UTC),
            )
            self._jobs[job.id] = updated
            return updated

        updated = replace(
            job,
            status="queued",
            locked_by=None,
            locked_at=None,
            run_after=datetime.now(UTC)
            + timedelta(
                seconds=retry_backoff_seconds(
                    job.attempt_count,
                    base_seconds=base_backoff_seconds,
                    max_seconds=max_backoff_seconds,
                )
            ),
            last_error=error,
        )
        self._jobs[job.id] = updated
        return updated

    def _complete(
        self,
        job_id: int,
        *,
        status: str,
        result: dict[str, object],
        error: str | None,
        worker_id: str,
    ) -> QueueJob | None:
        job = self._jobs.get(job_id)
        if not self._is_running_owner(job, worker_id):
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

    @staticmethod
    def _is_running_owner(job: QueueJob | None, worker_id: str) -> bool:
        return job is not None and job.status == "running" and job.locked_by == worker_id


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

    def reclaim_stale(
        self,
        *,
        lease_seconds: int,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> list[QueueJob]:
        cutoff = datetime.now(UTC) - timedelta(seconds=lease_seconds)
        reclaimed: list[QueueJob] = []
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT *
                        FROM jobs
                        WHERE status='running'
                          AND (locked_at IS NULL OR locked_at < :cutoff)
                        ORDER BY id ASC
                        FOR UPDATE SKIP LOCKED;
                        """
                    ),
                    {"cutoff": cutoff},
                )
                .mappings()
                .all()
            )
            for job in rows:
                row = self._retry_or_fail_postgres(
                    connection,
                    job,
                    "job lease expired",
                    base_backoff_seconds=base_backoff_seconds,
                    max_backoff_seconds=max_backoff_seconds,
                )
                if row is not None:
                    reclaimed.append(_queue_job_from_row(row))
        return reclaimed

    def mark_succeeded(
        self,
        job_id: int,
        result: dict[str, object],
        *,
        worker_id: str,
    ) -> QueueJob | None:
        row = self._execute_update(
            """
            UPDATE jobs
            SET status='succeeded',
                result=CAST(:result AS jsonb),
                completed_at=NOW(),
                last_error=NULL,
                updated_at=NOW()
            WHERE id=:job_id
              AND status='running'
              AND locked_by=:worker_id
            RETURNING *;
            """,
            {"job_id": job_id, "result": json.dumps(result), "worker_id": worker_id},
        )
        return _queue_job_from_row(row) if row is not None else None

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        *,
        worker_id: str,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ) -> QueueJob | None:
        with self.engine.begin() as connection:
            job = (
                connection.execute(
                    text(
                        """
                        SELECT *
                        FROM jobs
                        WHERE id=:job_id
                          AND status='running'
                          AND locked_by=:worker_id
                        FOR UPDATE;
                        """
                    ),
                    {"job_id": job_id, "worker_id": worker_id},
                )
                .mappings()
                .one_or_none()
            )
            if job is None:
                return None
            row = self._retry_or_fail_postgres(
                connection,
                job,
                error,
                base_backoff_seconds=base_backoff_seconds,
                max_backoff_seconds=max_backoff_seconds,
            )
        return _queue_job_from_row(row) if row is not None else None

    def mark_failed(self, job_id: int, error: str, *, worker_id: str) -> QueueJob | None:
        row = self._execute_update(
            """
            UPDATE jobs
            SET status='failed',
                last_error=:error,
                completed_at=NOW(),
                updated_at=NOW()
            WHERE id=:job_id
              AND status='running'
              AND locked_by=:worker_id
            RETURNING *;
            """,
            {"job_id": job_id, "error": error, "worker_id": worker_id},
        )
        return _queue_job_from_row(row) if row is not None else None

    def mark_cancelled(self, job_id: int, *, worker_id: str | None = None) -> QueueJob | None:
        if worker_id is None:
            where_clause = "id=:job_id AND status IN ('queued', 'running')"
            params = {"job_id": job_id}
        else:
            where_clause = "id=:job_id AND status='running' AND locked_by=:worker_id"
            params = {"job_id": job_id, "worker_id": worker_id}
        row = self._execute_update(
            f"""
            UPDATE jobs
            SET status='cancelled',
                locked_by=NULL,
                locked_at=NULL,
                completed_at=NOW(),
                updated_at=NOW()
            WHERE {where_clause}
            RETURNING *;
            """,
            params,
        )
        return _queue_job_from_row(row) if row is not None else None

    def dispose(self) -> None:
        self.engine.dispose()

    def _execute_update(self, statement: str, params: dict[str, object]):
        with self.engine.begin() as connection:
            return connection.execute(text(statement), params).mappings().one_or_none()

    def _retry_or_fail_postgres(
        self,
        connection,
        job,
        error: str,
        *,
        base_backoff_seconds: int,
        max_backoff_seconds: int,
    ):
        if job["attempt_count"] >= job["max_attempts"]:
            statement = text(
                """
                UPDATE jobs
                SET status='failed',
                    last_error=:error,
                    completed_at=NOW(),
                    updated_at=NOW()
                WHERE id=:job_id
                  AND status='running'
                RETURNING *;
                """
            )
            params = {"job_id": job["id"], "error": error}
        else:
            statement = text(
                """
                UPDATE jobs
                SET status='queued',
                    locked_by=NULL,
                    locked_at=NULL,
                    run_after=:run_after,
                    last_error=:error,
                    updated_at=NOW()
                WHERE id=:job_id
                  AND status='running'
                RETURNING *;
                """
            )
            params = {
                "job_id": job["id"],
                "error": error,
                "run_after": datetime.now(UTC)
                + timedelta(
                    seconds=retry_backoff_seconds(
                        job["attempt_count"],
                        base_seconds=base_backoff_seconds,
                        max_seconds=max_backoff_seconds,
                    )
                ),
            }
        return connection.execute(statement, params).mappings().one_or_none()


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
