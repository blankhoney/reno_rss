from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, desc, select

from app.db.models import benchmark_runs


@dataclass(frozen=True)
class BenchmarkRunRecord:
    id: int
    suite: str
    mode: str
    status: str
    params: dict[str, object]
    metrics: dict[str, object]
    artifact_path: str | None
    cost_estimate: dict[str, object]
    created_by: UUID | None
    created_at: datetime
    completed_at: datetime | None


class BenchmarkStore(Protocol):
    def create_run(
        self,
        *,
        suite: str,
        mode: str,
        params: dict[str, object],
        created_by: UUID | None,
    ) -> BenchmarkRunRecord: ...

    def get_run(self, benchmark_run_id: int) -> BenchmarkRunRecord | None: ...


class MemoryBenchmarkRepository:
    def __init__(self) -> None:
        self._runs: dict[int, BenchmarkRunRecord] = {}
        self._next_id = 1

    def create_run(
        self,
        *,
        suite: str,
        mode: str,
        params: dict[str, object],
        created_by: UUID | None,
    ) -> BenchmarkRunRecord:
        now = datetime.now(UTC)
        run = BenchmarkRunRecord(
            id=self._next_id,
            suite=suite,
            mode=mode,
            status="queued",
            params=dict(params),
            metrics={},
            artifact_path=None,
            cost_estimate={},
            created_by=created_by,
            created_at=now,
            completed_at=None,
        )
        self._runs[run.id] = run
        self._next_id += 1
        return run

    def get_run(self, benchmark_run_id: int) -> BenchmarkRunRecord | None:
        return self._runs.get(benchmark_run_id)

    def mark_run(
        self,
        benchmark_run_id: int,
        *,
        status: str,
        metrics: dict[str, object] | None = None,
    ) -> BenchmarkRunRecord | None:
        run = self._runs.get(benchmark_run_id)
        if run is None:
            return None
        updated = replace(
            run,
            status=status,
            metrics=metrics or run.metrics,
            completed_at=datetime.now(UTC) if status in {"succeeded", "failed"} else None,
        )
        self._runs[benchmark_run_id] = updated
        return updated


class DatabaseBenchmarkRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def create_run(
        self,
        *,
        suite: str,
        mode: str,
        params: dict[str, object],
        created_by: UUID | None,
    ) -> BenchmarkRunRecord:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    benchmark_runs.insert()
                    .values(
                        suite=suite,
                        mode=mode,
                        status="queued",
                        params=params,
                        created_by=created_by,
                    )
                    .returning(benchmark_runs)
                )
                .mappings()
                .one()
            )
        return _run_from_row(row)

    def get_run(self, benchmark_run_id: int) -> BenchmarkRunRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(benchmark_runs)
                    .where(benchmark_runs.c.id == benchmark_run_id)
                    .order_by(desc(benchmark_runs.c.id))
                )
                .mappings()
                .one_or_none()
            )
        return _run_from_row(row) if row is not None else None

    def dispose(self) -> None:
        self.engine.dispose()


def create_benchmark_repository(database_url: str | None) -> BenchmarkStore:
    if database_url:
        return DatabaseBenchmarkRepository(database_url)
    return MemoryBenchmarkRepository()


def _run_from_row(row) -> BenchmarkRunRecord:
    return BenchmarkRunRecord(
        id=int(row["id"]),
        suite=row["suite"],
        mode=row["mode"],
        status=row["status"],
        params=dict(row["params"] or {}),
        metrics=dict(row["metrics"] or {}),
        artifact_path=row["artifact_path"],
        cost_estimate=dict(row["cost_estimate"] or {}),
        created_by=row["created_by"],
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )
