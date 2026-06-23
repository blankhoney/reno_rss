from dataclasses import dataclass, replace
from datetime import UTC, datetime

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
    run_after: datetime


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
            run_after=datetime.now(UTC),
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

    def dispose(self) -> None:
        self.engine.dispose()


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
        run_after=row["run_after"],
    )
