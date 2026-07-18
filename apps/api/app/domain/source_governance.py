"""Source quality demotion heuristics (GOAL §4.A 源治理)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class FeedQualitySample:
    feed_id: int
    content_quality: str  # full | snippet | failed | partial | blocked
    base_score: int | None = None


@dataclass(frozen=True)
class FeedDemoteDecision:
    feed_id: int
    demote: bool
    reason: str
    bad_ratio: float
    sample_count: int


def decide_feed_demotions(
    samples: Sequence[FeedQualitySample],
    *,
    min_samples: int = 5,
    bad_ratio_threshold: float = 0.6,
) -> list[FeedDemoteDecision]:
    """Demote feeds when recent content quality is mostly partial/failed/blocked."""
    by_feed: dict[int, list[FeedQualitySample]] = {}
    for sample in samples:
        by_feed.setdefault(int(sample.feed_id), []).append(sample)

    decisions: list[FeedDemoteDecision] = []
    for feed_id, rows in by_feed.items():
        if len(rows) < min_samples:
            continue
        bad = 0
        for row in rows:
            quality = (row.content_quality or "").strip().lower()
            if quality in {"snippet", "partial", "failed", "blocked", "error"}:
                bad += 1
            elif row.base_score is not None and row.base_score < 35:
                bad += 1
        ratio = bad / len(rows)
        demote = ratio >= bad_ratio_threshold
        decisions.append(
            FeedDemoteDecision(
                feed_id=feed_id,
                demote=demote,
                reason=(
                    f"low_quality_ratio={ratio:.2f} over {len(rows)} samples"
                    if demote
                    else "healthy"
                ),
                bad_ratio=round(ratio, 3),
                sample_count=len(rows),
            )
        )
    decisions.sort(key=lambda item: (-item.bad_ratio, item.feed_id))
    return decisions
