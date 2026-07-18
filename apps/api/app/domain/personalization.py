"""Long-term interest vectors from feedback, highlights, and project signals (GOAL §4.A)."""

from __future__ import annotations

import re
from collections import Counter
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime


_TOKEN_RE = re.compile(r"[\w\u4e00-\u9fff]{2,}", re.UNICODE)


@dataclass(frozen=True)
class InterestSignal:
    text: str
    weight: float = 1.0
    kind: str = "generic"


def tokenize(text: str) -> list[str]:
    if not text:
        return []
    return [match.group(0).casefold() for match in _TOKEN_RE.finditer(text)]


def build_interest_profile(
    signals: Sequence[InterestSignal],
    *,
    feedback_types: Iterable[str] = (),
    project_count: int = 0,
    annotation_count: int = 0,
    generated_at: datetime | None = None,
    reset_at: datetime | None = None,
    max_keywords: int = 40,
) -> dict[str, object]:
    weights: Counter[str] = Counter()
    for signal in signals:
        for token in tokenize(signal.text):
            weights[token] += float(signal.weight)

    keywords = [
        {"term": term, "weight": round(weight, 3)}
        for term, weight in weights.most_common(max_keywords)
    ]
    feedback_counts: Counter[str] = Counter(str(item) for item in feedback_types if item)
    stamp = (generated_at or datetime.now(UTC)).astimezone(UTC)
    return {
        "generated_at": stamp.isoformat(),
        "keywords": keywords,
        "feedback_counts": dict(feedback_counts),
        "project_count": int(project_count),
        "annotation_count": int(annotation_count),
        "reset_at": reset_at.astimezone(UTC).isoformat() if reset_at is not None else None,
    }
