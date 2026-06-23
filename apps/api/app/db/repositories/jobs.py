from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
import hashlib
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, desc, select, text, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.models import job_watchers, jobs


ACTIVE_DEDUPE_STATUSES = {"queued", "running"}


@dataclass(frozen=True)
class JobRecord:
    id: int
    job_type: str
    status: str
    priority: int
    payload: dict[str, object]
    dedupe_key: str
    progress: dict[str, object]
    result: dict[str, object]
    locked_by: str | None
    locked_at: datetime | None
    attempt_count: int
    max_attempts: int
    run_after: datetime
    completed_at: datetime | None
    last_error: str | None
    created_by: UUID | None
    created_at: datetime
    updated_at: datetime


class JobStore(Protocol):
    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        dedupe_key: str,
        created_by: UUID | None = None,
        priority: int = 0,
    ) -> JobRecord: ...

    def get_visible_job(self, job_id: int, *, current_user_id: UUID, is_admin: bool) -> JobRecord | None: ...

    def claim_next(self, worker_id: str) -> JobRecord | None: ...

    def mark_succeeded(self, job_id: int, result: dict[str, object]) -> JobRecord | None: ...

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        backoff_seconds: int,
    ) -> JobRecord | None: ...

    def mark_failed(self, job_id: int, error: str) -> JobRecord | None: ...


def dedupe_key_for(job_type: str, value: object) -> str:
    return hashlib.sha256(f"{job_type}:{value}".encode("utf-8")).hexdigest()


class MemoryJobRepository:
    def __init__(self) -> None:
        self._jobs: dict[int, JobRecord] = {}
        self._watchers_by_job: dict[int, set[UUID]] = {}
        self._next_id = 1

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        dedupe_key: str,
        created_by: UUID | None = None,
        priority: int = 0,
    ) -> JobRecord:
        for job in self._jobs.values():
            if (
                job.job_type == job_type
                and job.dedupe_key == dedupe_key
                and job.status in ACTIVE_DEDUPE_STATUSES
            ):
                self._watch_job(job.id, created_by)
                return job

        now = datetime.now(UTC)
        job = JobRecord(
            id=self._next_id,
            job_type=job_type,
            status="queued",
            priority=priority,
            payload=dict(payload),
            dedupe_key=dedupe_key,
            progress={},
            result={},
            locked_by=None,
            locked_at=None,
            attempt_count=0,
            max_attempts=5,
            run_after=now,
            completed_at=None,
            last_error=None,
            created_by=created_by,
            created_at=now,
            updated_at=now,
        )
        self._jobs[job.id] = job
        self._watch_job(job.id, created_by)
        self._next_id += 1
        return job

    def get_visible_job(self, job_id: int, *, current_user_id: UUID, is_admin: bool) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        if is_admin:
            return job
        if current_user_id in self._watchers_by_job.get(job_id, set()):
            return job
        return None

    def _watch_job(self, job_id: int, user_id: UUID | None) -> None:
        if user_id is None:
            return
        self._watchers_by_job.setdefault(job_id, set()).add(user_id)

    def claim_next(self, worker_id: str) -> JobRecord | None:
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
            updated_at=now,
        )
        self._jobs[job.id] = claimed
        return claimed

    def mark_succeeded(self, job_id: int, result: dict[str, object]) -> JobRecord | None:
        return self._complete(job_id, status="succeeded", result=result, error=None)

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        backoff_seconds: int,
    ) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        now = datetime.now(UTC)
        updated = replace(
            job,
            status="queued",
            locked_by=None,
            locked_at=None,
            run_after=now + timedelta(seconds=backoff_seconds),
            last_error=error,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        return updated

    def mark_failed(self, job_id: int, error: str) -> JobRecord | None:
        return self._complete(job_id, status="failed", result={}, error=error)

    def _complete(
        self,
        job_id: int,
        *,
        status: str,
        result: dict[str, object],
        error: str | None,
    ) -> JobRecord | None:
        job = self._jobs.get(job_id)
        if job is None:
            return None
        now = datetime.now(UTC)
        updated = replace(
            job,
            status=status,
            result=result,
            last_error=error,
            completed_at=now,
            updated_at=now,
        )
        self._jobs[job_id] = updated
        return updated


class DatabaseJobRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        dedupe_key: str,
        created_by: UUID | None = None,
        priority: int = 0,
    ) -> JobRecord:
        with self.engine.begin() as connection:
            row = self._insert_job(connection, job_type, payload, dedupe_key, created_by, priority)
            if row is None:
                row = self._select_active_deduped_job(connection, job_type, dedupe_key)
            if row is None:
                row = self._insert_job(connection, job_type, payload, dedupe_key, created_by, priority)
            if row is None:
                row = self._select_active_deduped_job(connection, job_type, dedupe_key)
            if row is None:
                raise RuntimeError("failed to enqueue or find active deduped job")
            job = _job_from_row(row)
            self._watch_job(connection, job.id, created_by)
        return job

    def get_visible_job(self, job_id: int, *, current_user_id: UUID, is_admin: bool) -> JobRecord | None:
        statement = select(jobs).where(jobs.c.id == job_id)
        if not is_admin:
            statement = statement.join(job_watchers, job_watchers.c.job_id == jobs.c.id).where(
                job_watchers.c.user_id == current_user_id
            )

        with self.engine.begin() as connection:
            row = connection.execute(statement).mappings().one_or_none()
        return _job_from_row(row) if row is not None else None

    def claim_next(self, worker_id: str) -> JobRecord | None:
        if self.engine.dialect.name == "postgresql":
            return self._claim_next_postgres(worker_id)
        return self._claim_next_generic(worker_id)

    def mark_succeeded(self, job_id: int, result: dict[str, object]) -> JobRecord | None:
        return self._update_job(
            job_id,
            status="succeeded",
            result=result,
            completed_at=datetime.now(UTC),
            updated_at=datetime.now(UTC),
        )

    def mark_retryable_failure(
        self,
        job_id: int,
        error: str,
        backoff_seconds: int,
    ) -> JobRecord | None:
        now = datetime.now(UTC)
        return self._update_job(
            job_id,
            status="queued",
            locked_by=None,
            locked_at=None,
            run_after=now + timedelta(seconds=backoff_seconds),
            last_error=error,
            updated_at=now,
        )

    def mark_failed(self, job_id: int, error: str) -> JobRecord | None:
        now = datetime.now(UTC)
        return self._update_job(
            job_id,
            status="failed",
            last_error=error,
            completed_at=now,
            updated_at=now,
        )

    def dispose(self) -> None:
        self.engine.dispose()

    def _claim_next_postgres(self, worker_id: str) -> JobRecord | None:
        statement = text(
            """
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
        )
        with self.engine.begin() as connection:
            row = connection.execute(statement, {"worker_id": worker_id}).mappings().one_or_none()
        return _job_from_row(row) if row is not None else None

    def _insert_job(
        self,
        connection,
        job_type: str,
        payload: dict[str, object],
        dedupe_key: str,
        created_by: UUID | None,
        priority: int,
    ):
        values = {
            "job_type": job_type,
            "payload": payload,
            "dedupe_key": dedupe_key,
            "created_by": created_by,
            "priority": priority,
        }
        if self.engine.dialect.name == "postgresql":
            statement = (
                pg_insert(jobs)
                .values(**values)
                .on_conflict_do_nothing(
                    index_elements=[jobs.c.job_type, jobs.c.dedupe_key],
                    index_where=jobs.c.status.in_(ACTIVE_DEDUPE_STATUSES),
                )
                .returning(jobs)
            )
            return connection.execute(statement).mappings().one_or_none()

        try:
            return (
                connection.execute(jobs.insert().values(**values).returning(jobs))
                .mappings()
                .one()
            )
        except IntegrityError:
            return None

    def _select_active_deduped_job(self, connection, job_type: str, dedupe_key: str):
        return (
            connection.execute(
                select(jobs).where(
                    jobs.c.job_type == job_type,
                    jobs.c.dedupe_key == dedupe_key,
                    jobs.c.status.in_(ACTIVE_DEDUPE_STATUSES),
                )
            )
            .mappings()
            .one_or_none()
        )

    def _watch_job(self, connection, job_id: int, user_id: UUID | None) -> None:
        if user_id is None:
            return
        values = {"job_id": job_id, "user_id": user_id}
        if self.engine.dialect.name == "postgresql":
            statement = (
                pg_insert(job_watchers)
                .values(**values)
                .on_conflict_do_nothing(index_elements=[job_watchers.c.job_id, job_watchers.c.user_id])
            )
            connection.execute(statement)
            return

        try:
            connection.execute(job_watchers.insert().values(**values))
        except IntegrityError:
            return

    def _claim_next_generic(self, worker_id: str) -> JobRecord | None:
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            candidate_id = connection.execute(
                select(jobs.c.id)
                .where(jobs.c.status == "queued", jobs.c.run_after <= now)
                .order_by(desc(jobs.c.priority), jobs.c.id.asc())
                .limit(1)
            ).scalar_one_or_none()
            if candidate_id is None:
                return None
            row = (
                connection.execute(
                    update(jobs)
                    .where(jobs.c.id == candidate_id)
                    .values(
                        status="running",
                        locked_by=worker_id,
                        locked_at=now,
                        attempt_count=jobs.c.attempt_count + 1,
                        updated_at=now,
                    )
                    .returning(jobs)
                )
                .mappings()
                .one()
            )
        return _job_from_row(row)

    def _update_job(self, job_id: int, **values: object) -> JobRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    update(jobs).where(jobs.c.id == job_id).values(**values).returning(jobs)
                )
                .mappings()
                .one_or_none()
            )
        return _job_from_row(row) if row is not None else None


def create_job_repository(database_url: str | None) -> JobStore:
    if database_url:
        return DatabaseJobRepository(database_url)
    return MemoryJobRepository()


def _job_from_row(row) -> JobRecord:
    return JobRecord(
        id=row["id"],
        job_type=row["job_type"],
        status=row["status"],
        priority=row["priority"],
        payload=row["payload"],
        dedupe_key=row["dedupe_key"],
        progress=row["progress"],
        result=row["result"],
        locked_by=row["locked_by"],
        locked_at=row["locked_at"],
        attempt_count=row["attempt_count"],
        max_attempts=row["max_attempts"],
        run_after=row["run_after"],
        completed_at=row["completed_at"],
        last_error=row["last_error"],
        created_by=row["created_by"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )
