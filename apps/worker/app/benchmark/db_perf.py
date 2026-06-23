from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class DbPerfReport:
    suite: str = "db_perf"
    status: str = "not_run"
    metrics: dict[str, object] = field(default_factory=dict)

    def artifact_json(self) -> dict[str, object]:
        return {
            "suite": self.suite,
            "status": self.status,
            "metrics": self.metrics,
        }


def run_db_perf_benchmark(*, params: dict[str, object] | None = None) -> DbPerfReport:
    return DbPerfReport(metrics={"params": params or {}, "queries_measured": 0})
