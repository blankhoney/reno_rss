from __future__ import annotations

from collections.abc import Mapping
import os
from typing import Protocol

from app.benchmark.db_perf import run_db_perf_benchmark
from app.benchmark.ranking import BenchmarkDataset, run_ranking_benchmark


DEFAULT_MAX_PAIRS = 3_000
DEFAULT_MAX_COST_USD = 10.0


class BenchmarkRunRejected(RuntimeError):
    pass


class BenchmarkSink(Protocol):
    def load_benchmark_dataset(self, benchmark_run_id: object) -> BenchmarkDataset: ...

    def save_benchmark_result(
        self,
        benchmark_run_id: object,
        metrics: dict[str, object],
        artifact_path: str | None,
        cost_estimate: dict[str, object],
    ) -> None: ...


def run_benchmark(payload: Mapping[str, object], sink: BenchmarkSink) -> dict[str, object]:
    benchmark_run_id = payload.get("benchmark_run_id")
    if benchmark_run_id is None:
        raise KeyError("payload['benchmark_run_id'] is required")

    suite = str(payload.get("suite", "ranking"))
    mode = str(payload.get("mode", "ci_mini"))
    provider = str(payload.get("provider", "mock"))
    if mode == "ci_mini" and provider != "mock":
        raise BenchmarkRunRejected("ci_mini benchmark must use mock provider")
    if mode == "manual_full":
        _enforce_manual_full_cost_limits(payload, sink, benchmark_run_id)

    if suite == "ranking":
        dataset = sink.load_benchmark_dataset(benchmark_run_id)
        report = run_ranking_benchmark(dataset, provider_name=provider, mode=mode)
        metrics = report.metrics_json()
        artifact_path = f"benchmark_runs/{benchmark_run_id}/ranking.json"
        cost_estimate = {
            "provider": provider,
            "real_llm_calls": report.real_llm_calls,
        }
        status = report.status
    elif suite == "db_perf":
        report = run_db_perf_benchmark(params=_mapping_payload(payload.get("params", {})))
        metrics = report.artifact_json()
        artifact_path = f"benchmark_runs/{benchmark_run_id}/db_perf.json"
        cost_estimate = {"provider": "none", "real_llm_calls": 0}
        status = "succeeded"
    else:
        raise ValueError("payload['suite'] must be ranking or db_perf")

    sink.save_benchmark_result(
        benchmark_run_id,
        metrics,
        artifact_path,
        cost_estimate,
    )
    return {
        "benchmark_run_id": benchmark_run_id,
        "suite": suite,
        "mode": mode,
        "status": status,
        "artifact_path": artifact_path,
    }


def _enforce_manual_full_cost_limits(
    payload: Mapping[str, object],
    sink: object,
    benchmark_run_id: object,
) -> None:
    if not hasattr(sink, "dry_run_benchmark_cost"):
        raise BenchmarkRunRejected("manual_full benchmark requires a dry-run cost estimate")
    estimate = getattr(sink, "dry_run_benchmark_cost")(benchmark_run_id)
    pair_count = int(estimate.get("pair_count", 0))
    estimated_cost = float(estimate.get("estimated_cost_usd", 0))
    max_pairs = int(payload.get("max_pairs", os.environ.get("BENCHMARK_MAX_PAIRS", DEFAULT_MAX_PAIRS)))
    max_cost = float(
        payload.get("max_cost_usd", os.environ.get("BENCHMARK_MAX_COST_USD", DEFAULT_MAX_COST_USD))
    )
    if pair_count > max_pairs or estimated_cost > max_cost:
        raise BenchmarkRunRejected("manual_full benchmark exceeds cost limits")


def _mapping_payload(value: object) -> dict[str, object]:
    if not isinstance(value, Mapping):
        raise TypeError("payload['params'] must be a mapping")
    return dict(value)
