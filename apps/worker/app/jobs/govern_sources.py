"""Auto-demote low-quality / residual feeds (GOAL §4.A 源治理)."""

from __future__ import annotations

import importlib.util
import sys
from collections.abc import Mapping
from pathlib import Path
from types import ModuleType
from typing import Protocol

_GOVERNANCE_MODULE: ModuleType | None = None


class SourceGovernanceSink(Protocol):
    def list_recent_quality_samples(self, *, limit: int = 500) -> list[dict[str, object]]: ...

    def demote_feed(self, feed_id: int, *, reason: str) -> int: ...


def govern_sources(
    payload: Mapping[str, object],
    sink: SourceGovernanceSink,
) -> dict[str, object]:
    """Evaluate recent quality samples and demote unhealthy feeds for all users."""
    limit = int(payload.get("limit", 500) or 500)
    min_samples = int(payload.get("min_samples", 5) or 5)
    bad_ratio = float(payload.get("bad_ratio_threshold", 0.6) or 0.6)
    dry_run = bool(payload.get("dry_run", False))

    samples_raw = sink.list_recent_quality_samples(limit=max(1, min(limit, 2000)))
    module = _load_governance_module()
    domain_samples = [
        module.FeedQualitySample(
            feed_id=int(row["feed_id"]),
            content_quality=str(row.get("content_quality") or ""),
            base_score=(
                int(row["base_score"]) if row.get("base_score") is not None else None
            ),
        )
        for row in samples_raw
        if row.get("feed_id") is not None
    ]
    decisions = module.decide_feed_demotions(
        domain_samples,
        min_samples=min_samples,
        bad_ratio_threshold=bad_ratio,
    )
    demoted = 0
    demotions: list[dict[str, object]] = []
    for decision in decisions:
        if not decision.demote:
            continue
        payload_row: dict[str, object] = {
            "feed_id": decision.feed_id,
            "reason": decision.reason,
            "bad_ratio": decision.bad_ratio,
            "sample_count": decision.sample_count,
        }
        if not dry_run:
            affected = sink.demote_feed(decision.feed_id, reason=decision.reason)
            payload_row["users_affected"] = affected
            demoted += 1
        demotions.append(payload_row)
    return {
        "status": "ok",
        "dry_run": dry_run,
        "samples_seen": len(domain_samples),
        "demotions": demotions,
        "feeds_demoted": demoted if not dry_run else len(demotions),
    }


def _load_governance_module() -> ModuleType:
    global _GOVERNANCE_MODULE
    if _GOVERNANCE_MODULE is not None:
        return _GOVERNANCE_MODULE
    domain_path = _governance_module_path(Path(__file__).resolve())
    module_name = "ai_reader_source_governance"
    spec = importlib.util.spec_from_file_location(module_name, domain_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load source governance from {domain_path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    _GOVERNANCE_MODULE = module
    return module


def _governance_module_path(start: Path) -> Path:
    relative = Path("apps/api/app/domain/source_governance.py")
    for parent in start.parents:
        candidate = parent / relative
        if candidate.exists():
            return candidate
    raise ImportError(f"Cannot find source_governance relative to {start}")
