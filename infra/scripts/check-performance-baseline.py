#!/usr/bin/env python3
"""Compare equivalent performance baseline reports with explicit noise budgets."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys
from typing import Any


def parse_arguments() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--baseline", type=Path, required=True)
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--max-regression", type=float, default=3.0)
    parser.add_argument(
        "--latency-metric",
        default="durationMs",
        help="per-route/query summary metric to compare (default: durationMs)",
    )
    parser.add_argument("--output", type=Path)
    return parser.parse_args()


def load_report(path: Path) -> dict[str, Any]:
    report = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(report, dict) or report.get("schemaVersion") not in {1, 2}:
        raise ValueError(f"{path} is not a supported schemaVersion 1 or 2 report")
    return report


def entry_label(entry: dict[str, Any]) -> str | None:
    label = entry.get("label") or entry.get("route")
    phase = entry.get("phase")
    if not isinstance(label, str):
        return None
    return f"{label} [{phase}]" if isinstance(phase, str) else label


def latency_metrics(report: dict[str, Any], metric: str) -> dict[str, float]:
    entries = report.get("routes", report.get("queries"))
    if not isinstance(entries, list):
        return {}
    metrics: dict[str, float] = {}
    for entry in entries:
        if not isinstance(entry, dict):
            continue
        label = entry_label(entry)
        p95 = entry.get("summary", {}).get(metric, {}).get("p95")
        if isinstance(label, str) and isinstance(p95, (int, float)) and p95 > 0:
            metrics[label] = float(p95)
    return metrics


def throughput_metrics(report: dict[str, Any]) -> dict[str, float]:
    summary = report.get("summary")
    if not isinstance(summary, dict):
        return {}
    metrics: dict[str, float] = {}
    for label, value in summary.items():
        p95 = value.get("p95") if isinstance(value, dict) else None
        if isinstance(p95, (int, float)) and p95 > 0:
            metrics[label] = float(p95)
    return metrics


def compare(
    baseline: dict[str, float], candidate: dict[str, float], max_regression: float, higher_is_better: bool
) -> list[dict[str, Any]]:
    results = []
    for label, baseline_value in baseline.items():
        candidate_value = candidate.get(label)
        if candidate_value is None:
            results.append({"label": label, "status": "missing"})
            continue
        ratio = candidate_value / baseline_value
        passed = ratio >= 1 / max_regression if higher_is_better else ratio <= max_regression
        results.append(
            {
                "baseline": baseline_value,
                "candidate": candidate_value,
                "label": label,
                "ratio": ratio,
                "status": "pass" if passed else "regression",
            }
        )
    return results


def main() -> None:
    arguments = parse_arguments()
    if arguments.max_regression < 1:
        raise SystemExit("--max-regression must be at least 1")
    baseline = load_report(arguments.baseline)
    candidate = load_report(arguments.candidate)
    latency = compare(
        latency_metrics(baseline, arguments.latency_metric),
        latency_metrics(candidate, arguments.latency_metric),
        arguments.max_regression,
        False,
    )
    throughput = compare(
        throughput_metrics(baseline), throughput_metrics(candidate), arguments.max_regression, True
    )
    if not latency and not throughput:
        raise SystemExit("reports contain no comparable performance metrics")
    result = {
        "baseline": str(arguments.baseline),
        "candidate": str(arguments.candidate),
        "latencyMetric": arguments.latency_metric,
        "maxRegression": arguments.max_regression,
        "latency": latency,
        "throughput": throughput,
    }
    serialized = json.dumps(result, indent=2) + "\n"
    if arguments.output:
        arguments.output.parent.mkdir(parents=True, exist_ok=True)
        arguments.output.write_text(serialized, encoding="utf-8")
    else:
        print(serialized, end="")
    if any(item["status"] != "pass" for item in latency + throughput):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
