from __future__ import annotations

import argparse
import asyncio
from datetime import UTC, datetime, timedelta
import json
import math
import os
from pathlib import Path
import platform
import subprocess
from time import perf_counter_ns

from httpx import ASGITransport, AsyncClient

# This harness is intentionally synthetic and must never inherit a live database
# or model provider from the caller's shell.
os.environ.pop("SCORING_DATABASE_URL", None)
os.environ["AI_READER_CSRF_ALLOWED_ORIGINS"] = "https://baseline.invalid"
os.environ["LLM_PROVIDER"] = "mock"

from app.main import create_app


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


def seed_articles(app, count: int) -> int:
    published_at = datetime(2026, 7, 26, 8, tzinfo=UTC)
    first_id = 0
    for index in range(count):
        article = app.state.article_repository.upsert_from_source(
            {
                "feed_id": 1 + index % 8,
                "miniflux_entry_id": 100_000 + index,
                "url": f"https://baseline.invalid/articles/{index}",
                "title": f"Synthetic baseline article {index:04d}",
                "content_text": "Fixed synthetic research evidence for API timing.",
                "content_html": "<p>Fixed synthetic research evidence for API timing.</p>",
                "published_at": published_at - timedelta(minutes=index),
            }
        )
        if index == 0:
            first_id = article.id
    return first_id


async def run_baseline(arguments: argparse.Namespace) -> dict[str, object]:
    app = create_app()
    app.state.csrf_allowed_origins = {"https://baseline.invalid"}
    article_id = seed_articles(app, arguments.articles)
    routes = [
        ("health", "/api/healthz"),
        ("article-list", "/api/articles?limit=50&module=all&sort=latest"),
        ("article-search", "/api/articles?limit=30&q=baseline"),
        ("article-detail", f"/api/articles/{article_id}"),
    ]
    results = []

    async with AsyncClient(
        transport=ASGITransport(app=app),
        base_url="https://baseline.invalid",
        headers={"Referer": "https://baseline.invalid/"},
    ) as client:
        login = await client.post("/api/auth/login", json={"display_name": "Baseline User"})
        if login.status_code != 200:
            raise RuntimeError(f"fixture login failed with status {login.status_code}")

        for label, path in routes:
            for _ in range(arguments.warmups):
                response = await client.get(path)
                if response.status_code != 200:
                    raise RuntimeError(f"warmup {label} failed with status {response.status_code}")

            samples = []
            for sample_index in range(1, arguments.iterations + 1):
                started_at = perf_counter_ns()
                response = await client.get(path)
                duration_ms = (perf_counter_ns() - started_at) / 1_000_000
                samples.append(
                    {
                        "durationMs": duration_ms,
                        "responseBytes": len(response.content),
                        "sampleIndex": sample_index,
                        "status": response.status_code,
                    }
                )

            if any(sample["status"] != 200 for sample in samples):
                raise RuntimeError(f"measured {label} request returned a non-200 status")
            results.append(
                {
                    "label": label,
                    "path": path.split("?", 1)[0],
                    "samples": samples,
                    "summary": {
                        "durationMs": summarize(
                            [float(sample["durationMs"]) for sample in samples]
                        ),
                        "responseBytes": summarize(
                            [float(sample["responseBytes"]) for sample in samples]
                        ),
                    },
                }
            )

    return {
        "schemaVersion": 1,
        "generatedAt": datetime.now(UTC).isoformat(),
        "candidate": {
            "localGitRevision": current_revision(),
            "runtime": "in-process ASGI with memory repositories",
        },
        "environment": {
            "articleFixtures": arguments.articles,
            "iterations": arguments.iterations,
            "platform": platform.platform(),
            "python": platform.python_version(),
            "warmups": arguments.warmups,
        },
        "routes": results,
    }


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the synthetic AI Reader API baseline.")
    parser.add_argument("--articles", type=positive_integer, default=500)
    parser.add_argument("--iterations", type=positive_integer, default=20)
    parser.add_argument("--warmups", type=positive_integer, default=3)
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def main() -> None:
    arguments = parse_arguments()
    report = asyncio.run(run_baseline(arguments))
    serialized = json.dumps(report, ensure_ascii=True, indent=2) + "\n"
    if arguments.output is None:
        print(serialized, end="")
        return
    output_path = arguments.output.resolve()
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(serialized, encoding="utf-8")
    print(f"API performance baseline written to {output_path}")


if __name__ == "__main__":
    main()
