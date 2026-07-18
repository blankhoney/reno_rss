"""Cluster tags/keywords from active scores into theme groups (GOAL §4.C)."""

from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable, Mapping, Sequence


def cluster_themes(
    scores: Sequence[Mapping[str, object]],
    *,
    min_weight: int = 1,
    max_themes: int = 20,
) -> list[dict[str, object]]:
    """
    Group articles by normalized tag/keyword labels.

    Each input score should provide:
      - article_id: int
      - tags: list[str] (optional)
      - keywords: list[str] (optional, merged with tags)
      - base_score: number (optional, boosts weight slightly)
    """
    article_ids_by_label: dict[str, set[int]] = defaultdict(set)
    weight_by_label: dict[str, float] = defaultdict(float)

    for score in scores:
        article_id = _article_id(score)
        if article_id is None:
            continue
        labels = _labels_from_score(score)
        if not labels:
            continue
        base = _base_score(score)
        # weight = distinct articles + mild score boost so higher-quality tags float up
        per_label_boost = 1.0 + (base / 100.0) * 0.25
        for label in labels:
            if article_id not in article_ids_by_label[label]:
                article_ids_by_label[label].add(article_id)
                weight_by_label[label] += per_label_boost
            else:
                weight_by_label[label] += per_label_boost * 0.1

    themes: list[dict[str, object]] = []
    for label, article_ids in article_ids_by_label.items():
        weight = round(weight_by_label[label], 2)
        if weight < min_weight:
            continue
        themes.append(
            {
                "label": label,
                "article_ids": sorted(article_ids),
                "weight": weight,
            }
        )

    themes.sort(key=lambda item: (-float(item["weight"]), str(item["label"])))
    return themes[: max(1, max_themes)] if themes else []


def _labels_from_score(score: Mapping[str, object]) -> list[str]:
    raw: list[object] = []
    tags = score.get("tags")
    keywords = score.get("keywords")
    if isinstance(tags, Iterable) and not isinstance(tags, (str, bytes)):
        raw.extend(tags)
    if isinstance(keywords, Iterable) and not isinstance(keywords, (str, bytes)):
        raw.extend(keywords)

    seen: set[str] = set()
    labels: list[str] = []
    for item in raw:
        label = _normalize_label(item)
        if label is None or label in seen:
            continue
        seen.add(label)
        labels.append(label)
    return labels


def _normalize_label(value: object) -> str | None:
    if value is None:
        return None
    text = str(value).strip().lower()
    if not text:
        return None
    # collapse internal whitespace
    return " ".join(text.split())


def _article_id(score: Mapping[str, object]) -> int | None:
    raw = score.get("article_id")
    if raw is None:
        return None
    try:
        return int(raw)
    except (TypeError, ValueError):
        return None


def _base_score(score: Mapping[str, object]) -> float:
    raw = score.get("base_score")
    if raw is None:
        raw = score.get("overall")
    if raw is None:
        return 0.0
    try:
        return float(raw)
    except (TypeError, ValueError):
        return 0.0
