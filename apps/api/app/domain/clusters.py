"""Storyline clustering by same-day title similarity (GOAL §4.A).

Memory-friendly: pure functions over a small recent-article window; no
persisted cluster graph. Callers load last N articles by published_at and
cluster on the fly.
"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from datetime import UTC, date, datetime
import hashlib
import re
import unicodedata


# Token overlap (Jaccard) above this merges same-day articles into one cluster.
DEFAULT_MIN_SIMILARITY = 0.45
# Tokens shorter than this are noise for Latin/CJK mixed titles.
_MIN_TOKEN_LEN = 2
_SPLIT_RE = re.compile(r"[\W_]+", re.UNICODE)


@dataclass(frozen=True)
class ClusterArticle:
    id: int
    title: str
    published_at: datetime | None
    base_score: int | None = None


@dataclass(frozen=True)
class StorylineCluster:
    id: str
    label: str
    main_article_id: int
    related_article_ids: list[int]
    size: int


def normalize_title(title: str) -> str:
    """Lowercase, strip accents, collapse punctuation/whitespace."""
    text = unicodedata.normalize("NFKD", title or "")
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    text = text.casefold().strip()
    text = _SPLIT_RE.sub(" ", text)
    return " ".join(text.split())


def title_tokens(title: str) -> frozenset[str]:
    normalized = normalize_title(title)
    if not normalized:
        return frozenset()
    return frozenset(
        token for token in normalized.split(" ") if len(token) >= _MIN_TOKEN_LEN
    )


def title_similarity(left: str, right: str) -> float:
    """Jaccard similarity over normalized title tokens; 1.0 for identical empty."""
    left_tokens = title_tokens(left)
    right_tokens = title_tokens(right)
    if not left_tokens and not right_tokens:
        return 1.0 if normalize_title(left) == normalize_title(right) else 0.0
    if not left_tokens or not right_tokens:
        return 0.0
    union = left_tokens | right_tokens
    if not union:
        return 0.0
    return len(left_tokens & right_tokens) / len(union)


def published_day(published_at: datetime | None) -> date | None:
    if published_at is None:
        return None
    if published_at.tzinfo is None:
        return published_at.replace(tzinfo=UTC).date()
    return published_at.astimezone(UTC).date()


def cluster_articles(
    articles: Sequence[ClusterArticle],
    *,
    min_similarity: float = DEFAULT_MIN_SIMILARITY,
    limit: int = 20,
    min_cluster_size: int = 2,
) -> list[StorylineCluster]:
    """Group same-day articles with high title overlap into storyline clusters.

    - Only pairs that share a calendar day (UTC) are eligible to merge.
    - Union-find over pairs whose title Jaccard ≥ min_similarity.
    - Clusters with size < min_cluster_size are dropped (default: multi-source only).
    - Ordered by size desc, then main article published_at desc, then id.
    """
    if limit < 1 or not articles:
        return []

    items = list(articles)
    parent = {article.id: article.id for article in items}
    by_id = {article.id: article for article in items}

    def find(article_id: int) -> int:
        while parent[article_id] != article_id:
            parent[article_id] = parent[parent[article_id]]
            article_id = parent[article_id]
        return article_id

    def union(left_id: int, right_id: int) -> None:
        root_left = find(left_id)
        root_right = find(right_id)
        if root_left == root_right:
            return
        # Prefer lower id as root for stable cluster ids.
        if root_left < root_right:
            parent[root_right] = root_left
        else:
            parent[root_left] = root_right

    # Bucket by day so we never pairwise-scan the full N×N matrix across days.
    by_day: dict[date | None, list[ClusterArticle]] = {}
    for article in items:
        by_day.setdefault(published_day(article.published_at), []).append(article)

    for day, day_articles in by_day.items():
        if day is None:
            # Articles without published_at never merge (no same-day anchor).
            continue
        for index, left in enumerate(day_articles):
            for right in day_articles[index + 1 :]:
                if title_similarity(left.title, right.title) >= min_similarity:
                    union(left.id, right.id)

    members: dict[int, list[ClusterArticle]] = {}
    for article in items:
        members.setdefault(find(article.id), []).append(article)

    clusters: list[StorylineCluster] = []
    for group in members.values():
        if len(group) < min_cluster_size:
            continue
        main = _pick_main(group)
        related = sorted(
            (article.id for article in group if article.id != main.id),
            reverse=True,
        )
        ordered_ids = [main.id, *related]
        clusters.append(
            StorylineCluster(
                id=_cluster_id(ordered_ids),
                label=main.title.strip() or f"Cluster {main.id}",
                main_article_id=main.id,
                related_article_ids=related,
                size=len(group),
            )
        )

    clusters.sort(
        key=lambda cluster: (
            cluster.size,
            by_id[cluster.main_article_id].published_at
            or datetime.min.replace(tzinfo=UTC),
            cluster.main_article_id,
        ),
        reverse=True,
    )
    return clusters[:limit]


def _pick_main(group: Sequence[ClusterArticle]) -> ClusterArticle:
    return max(
        group,
        key=lambda article: (
            article.base_score if article.base_score is not None else -1,
            article.published_at or datetime.min.replace(tzinfo=UTC),
            -article.id,
        ),
    )


def _cluster_id(article_ids: Sequence[int]) -> str:
    digest = hashlib.sha1(
        ",".join(str(article_id) for article_id in sorted(article_ids)).encode("utf-8")
    ).hexdigest()[:12]
    return f"cl_{digest}"
