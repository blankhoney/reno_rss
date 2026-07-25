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

from sqlalchemy import create_engine, text


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
QUERIES = [
    (
        "latest-articles",
        """
        SELECT id
        FROM articles
        ORDER BY published_at DESC NULLS LAST, id DESC
        LIMIT 50
        """,
        {},
    ),
    (
        "article-title-search",
        """
        SELECT id
        FROM articles
        WHERE title ILIKE :query
        ORDER BY published_at DESC NULLS LAST, id DESC
        LIMIT 30
        """,
        {"query": "%baseline%"},
    ),
    (
        "ready-job",
        """
        SELECT id
        FROM jobs
        WHERE status = 'queued' AND run_after <= NOW()
        ORDER BY priority DESC, id ASC
        LIMIT 1
        """,
        {},
    ),
    (
        "due-review",
        """
        SELECT id
        FROM article_annotations
        WHERE deleted_at IS NULL AND next_review_at <= NOW()
        ORDER BY next_review_at ASC, id ASC
        LIMIT 20
        """,
        {},
    ),
]


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


def base_report(arguments: argparse.Namespace) -> dict[str, object]:
    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "candidate": {
            "localGitRevision": current_revision(),
            "runtime": "read-only PostgreSQL",
        },
        "environment": {
            "databaseDialect": "postgresql",
            "iterations": arguments.iterations,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "warmups": arguments.warmups,
        },
    }


def write_report(report: dict[str, object], output: Path | None) -> None:
    serialized = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if output is None:
        print(serialized, end="")
        return
    output_path = output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"DB performance baseline written to {output_path}")


def run_queries(database_url: str, arguments: argparse.Namespace) -> list[dict[str, object]]:
    engine = create_engine(normalize_database_url(database_url), pool_pre_ping=True)
    results = []
    try:
        with engine.connect() as connection:
            transaction = connection.begin()
            connection.execute(text("SET TRANSACTION READ ONLY"))
            try:
                for label, statement, parameters in QUERIES:
                    for _ in range(arguments.warmups):
                        connection.execute(text(statement), parameters).all()
                    samples = []
                    for sample_index in range(1, arguments.iterations + 1):
                        started_at = perf_counter_ns()
                        rows = connection.execute(text(statement), parameters).all()
                        duration_ms = (perf_counter_ns() - started_at) / 1_000_000
                        samples.append(
                            {
                                "durationMs": duration_ms,
                                "rowCount": len(rows),
                                "sampleIndex": sample_index,
                            }
                        )
                    results.append(
                        {
                            "label": label,
                            "samples": samples,
                            "summary": {
                                "durationMs": summarize(
                                    [float(sample["durationMs"]) for sample in samples]
                                ),
                                "rowCount": summarize(
                                    [float(sample["rowCount"]) for sample in samples]
                                ),
                            },
                        }
                    )
            finally:
                transaction.rollback()
    finally:
        engine.dispose()
    return results


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the read-only PostgreSQL baseline.")
    parser.add_argument("--iterations", type=positive_integer, default=20)
    parser.add_argument("--warmups", type=positive_integer, default=3)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    report = base_report(arguments)
    database_url = os.environ.get("DB_PERF_DATABASE_URL", "").strip()
    if not database_url:
        report.update(
            {
                "status": "NEEDS_BASELINE",
                "missingEvidence": "DB_PERF_DATABASE_URL is not available",
                "queries": [],
            }
        )
        write_report(report, arguments.output)
        raise SystemExit(2)

    try:
        report.update({"status": "MEASURED", "queries": run_queries(database_url, arguments)})
    except Exception as error:
        report.update(
            {
                "status": "ERROR",
                "errorType": type(error).__name__,
                "queries": [],
            }
        )
        write_report(report, arguments.output)
        raise SystemExit(1) from None
    write_report(report, arguments.output)


if __name__ == "__main__":
    main()
