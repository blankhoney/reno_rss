from __future__ import annotations

import argparse
from datetime import UTC, datetime
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from time import perf_counter_ns
from uuid import uuid4

from sqlalchemy import create_engine, text

from app.jobs.queue import PostgresJobQueue


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
RECOVERY_DATABASE_URL_ENV = "QUEUE_RECOVERY_DATABASE_URL"


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


def normalize_database_url(value: str) -> str:
    if value.startswith("postgres://"):
        return f"postgresql+psycopg://{value.removeprefix('postgres://')}"
    if value.startswith("postgresql://"):
        return f"postgresql+psycopg://{value.removeprefix('postgresql://')}"
    return value


def write_report(report: dict[str, object], output: Path | None) -> None:
    serialized = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output_path = output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"Queue recovery baseline written to {output_path}")


def run_once(queue: PostgresJobQueue, database_url: str, *, dedupe_key: str) -> dict[str, object]:
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    try:
        with engine.begin() as connection:
            job_id = connection.execute(
                text(
                    """
                    INSERT INTO jobs (job_type, payload, dedupe_key, priority, max_attempts)
                    VALUES ('queue_recovery_baseline', CAST(:payload AS jsonb), :dedupe_key, 0, 2)
                    RETURNING id
                    """
                ),
                {"payload": json.dumps({"baseline": "queue-recovery"}), "dedupe_key": dedupe_key},
            ).scalar_one()

        claimed = queue.claim_next("baseline-worker-before-restart")
        if claimed is None or claimed.id != job_id:
            raise RuntimeError("baseline job was not claimed by the first worker")

        with engine.begin() as connection:
            connection.execute(
                text("UPDATE jobs SET locked_at=NOW() - INTERVAL '2 seconds' WHERE id=:id"),
                {"id": job_id},
            )

        started_at = perf_counter_ns()
        reclaimed = queue.reclaim_stale(
            lease_seconds=1,
            base_backoff_seconds=1,
            max_backoff_seconds=30,
        )
        if [job.id for job in reclaimed] != [job_id]:
            raise RuntimeError("baseline job was not reclaimed after its lease expired")

        with engine.begin() as connection:
            connection.execute(text("UPDATE jobs SET run_after=NOW() WHERE id=:id"), {"id": job_id})

        recovered = queue.claim_next("baseline-worker-after-restart")
        if recovered is None or recovered.id != job_id:
            raise RuntimeError("baseline job was not claimed by the replacement worker")
        completed = queue.mark_succeeded(
            recovered.id,
            {"recovered_after_lease": True},
            worker_id="baseline-worker-after-restart",
        )
        if completed is None or completed.status != "succeeded":
            raise RuntimeError("baseline job did not complete after recovery")

        return {
            "durationMs": (perf_counter_ns() - started_at) / 1_000_000,
            "jobId": job_id,
            "states": ["running", "queued", "running", "succeeded"],
        }
    finally:
        with engine.begin() as connection:
            connection.execute(text("DELETE FROM jobs WHERE dedupe_key=:dedupe_key"), {"dedupe_key": dedupe_key})
        engine.dispose()


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Measure PostgreSQL stale-lease recovery through replacement-worker success."
    )
    parser.add_argument("--iterations", type=positive_integer, default=5)
    parser.add_argument("--warmups", type=positive_integer, default=1)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    report: dict[str, object] = {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "candidate": {"localGitRevision": current_revision(), "runtime": "PostgreSQL lease recovery"},
        "environment": {
            "databaseDialect": "postgresql",
            "iterations": arguments.iterations,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "warmups": arguments.warmups,
        },
    }
    database_url = os.environ.get(RECOVERY_DATABASE_URL_ENV, "").strip()
    if not database_url:
        report.update(
            {
                "status": "NEEDS_BASELINE",
                "missingEvidence": f"{RECOVERY_DATABASE_URL_ENV} is not available",
                "samples": [],
            }
        )
        write_report(report, arguments.output)
        raise SystemExit(2)

    queue = PostgresJobQueue(normalize_database_url(database_url))
    prefix = f"queue-recovery-baseline:{uuid4()}"
    try:
        for warmup_index in range(arguments.warmups):
            run_once(queue, database_url, dedupe_key=f"{prefix}:warmup:{warmup_index}")
        samples = [
            {
                "sampleIndex": sample_index,
                **run_once(queue, database_url, dedupe_key=f"{prefix}:sample:{sample_index}"),
            }
            for sample_index in range(1, arguments.iterations + 1)
        ]
    except Exception as error:
        report.update({"status": "ERROR", "errorType": type(error).__name__, "samples": []})
        write_report(report, arguments.output)
        raise SystemExit(1) from None
    finally:
        queue.dispose()

    report.update(
        {
            "status": "MEASURED",
            "summary": {"recoveryDurationMs": summarize([float(sample["durationMs"]) for sample in samples])},
            "samples": samples,
        }
    )
    write_report(report, arguments.output)


if __name__ == "__main__":
    main()
