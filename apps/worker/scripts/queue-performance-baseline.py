from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import math
from pathlib import Path
import platform
import subprocess
from time import perf_counter_ns

from app.jobs.queue import InMemoryJobQueue


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]


def positive_integer(value: str) -> int:
    parsed = int(value)
    if parsed < 1:
        raise argparse.ArgumentTypeError("value must be a positive integer")
    return parsed


def percentile(values: list[float], quantile: float) -> float:
    ordered = sorted(values)
    index = max(0, math.ceil(quantile * len(ordered)) - 1)
    return ordered[index]


def summarize(values: list[float]) -> dict[str, float]:
    return {
        "median": percentile(values, 0.5),
        "p95": percentile(values, 0.95),
        "min": min(values),
        "max": max(values),
    }


def current_revision() -> str:
    try:
        return subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=REPOSITORY_ROOT,
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return "UNKNOWN"


def enqueue_jobs(queue: InMemoryJobQueue, count: int, prefix: str) -> list[float]:
    durations = []
    for index in range(count):
        started_at = perf_counter_ns()
        queue.enqueue(
            "baseline",
            {"index": index},
            dedupe_key=f"{prefix}:{index}",
            priority=index % 4,
        )
        durations.append((perf_counter_ns() - started_at) / 1_000_000)
    return durations


def drain_jobs(queue: InMemoryJobQueue, count: int, worker_id: str) -> list[float]:
    durations = []
    for index in range(count):
        started_at = perf_counter_ns()
        job = queue.claim_next(worker_id)
        if job is None:
            raise RuntimeError(f"queue drained early at job {index}")
        completed = queue.mark_succeeded(job.id, {"ok": True}, worker_id=worker_id)
        if completed is None or completed.status != "succeeded":
            raise RuntimeError(f"job {job.id} did not complete")
        durations.append((perf_counter_ns() - started_at) / 1_000_000)
    if queue.claim_next(worker_id) is not None:
        raise RuntimeError("queue retained an unexpected claimable job")
    return durations


def run_once(count: int, prefix: str) -> dict[str, object]:
    queue = InMemoryJobQueue()
    started_at = perf_counter_ns()
    enqueue_durations = enqueue_jobs(queue, count, prefix)
    enqueue_elapsed_ms = (perf_counter_ns() - started_at) / 1_000_000

    started_at = perf_counter_ns()
    drain_durations = drain_jobs(queue, count, "baseline-worker")
    drain_elapsed_ms = (perf_counter_ns() - started_at) / 1_000_000

    return {
        "enqueue": {
            "operationDurationMs": summarize(enqueue_durations),
            "operations": count,
            "throughputPerSecond": count / (enqueue_elapsed_ms / 1_000),
            "totalMs": enqueue_elapsed_ms,
        },
        "claimAndComplete": {
            "operationDurationMs": summarize(drain_durations),
            "operations": count,
            "throughputPerSecond": count / (drain_elapsed_ms / 1_000),
            "totalMs": drain_elapsed_ms,
        },
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the synthetic in-memory queue baseline.")
    parser.add_argument("--jobs", type=positive_integer, default=1_000)
    parser.add_argument("--iterations", type=positive_integer, default=5)
    parser.add_argument("--warmups", type=positive_integer, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    for index in range(arguments.warmups):
        run_once(min(arguments.jobs, 100), f"warmup-{index}")

    samples = [
        {
            "sampleIndex": index + 1,
            **run_once(arguments.jobs, f"measured-{index}"),
        }
        for index in range(arguments.iterations)
    ]
    report = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "candidate": {
            "localGitRevision": current_revision(),
            "runtime": "synthetic InMemoryJobQueue",
        },
        "environment": {
            "iterations": arguments.iterations,
            "jobsPerIteration": arguments.jobs,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "warmups": arguments.warmups,
        },
        "summary": {
            "enqueueThroughputPerSecond": summarize(
                [float(sample["enqueue"]["throughputPerSecond"]) for sample in samples]
            ),
            "claimAndCompleteThroughputPerSecond": summarize(
                [
                    float(sample["claimAndComplete"]["throughputPerSecond"])
                    for sample in samples
                ]
            ),
        },
        "samples": samples,
    }
    serialized = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if arguments.output is None:
        print(serialized, end="")
        return
    output_path = arguments.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"Queue performance baseline written to {output_path}")


if __name__ == "__main__":
    main()
