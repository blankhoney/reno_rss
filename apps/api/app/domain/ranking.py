from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta


FEEDBACK_BASE_ADJUSTMENTS = {
    "underrated": 8,
    "overrated": -10,
    "too_promotional": -12,
    "low_density": -12,
    "outdated": -12,
    "duplicate": -12,
    "wrong_category": -12,
    "other": 0,
}


@dataclass(frozen=True)
class Candidate:
    article_id: int
    feed_ids: list[int]
    base_score: int
    published_at: datetime
    risk_uncertainty: int = 100
    risk_flags: list[str] | None = None


@dataclass(frozen=True)
class Feedback:
    feedback_type: str
    user_score: int | None = None


@dataclass(frozen=True)
class RankedItem:
    article_id: int
    rank: int
    rank_score: float
    tier: str
    reason: str
    source: str


def rank_b4(
    *,
    user_priority_by_feed: dict[int, int],
    candidates: list[Candidate],
    feedback_by_article: dict[int, Feedback | dict[str, object]],
    article_status_by_article: dict[int, str | None] | None = None,
    now: datetime | None = None,
) -> list[RankedItem]:
    reference_time = now or datetime.now(UTC)
    subscribed: list[tuple[Candidate, float]] = []
    exploration: list[Candidate] = []

    for candidate in _eligible_candidates(
        candidates,
        article_status_by_article or {},
        reference_time,
    ):
        subscribed_feed_ids = [
            feed_id for feed_id in candidate.feed_ids if feed_id in user_priority_by_feed
        ]
        if subscribed_feed_ids:
            priority = max(_clamp(user_priority_by_feed[feed_id], -20, 20) for feed_id in subscribed_feed_ids)
            score = (
                candidate.base_score
                + priority
                + _feedback_adjustment(candidate, feedback_by_article.get(candidate.article_id))
                + _freshness_adjustment(candidate.published_at, reference_time)
            )
            subscribed.append((candidate, float(score)))
            continue

        if candidate.base_score >= 80 and candidate.risk_uncertainty <= 50:
            exploration.append(candidate)

    subscribed.sort(
        key=lambda item: (item[1], item[0].published_at, item[0].article_id),
        reverse=True,
    )
    exploration.sort(
        key=lambda candidate: (candidate.base_score, candidate.published_at, candidate.article_id),
        reverse=True,
    )

    selected: list[tuple[Candidate, float, str]] = [
        (candidate, score, "subscription") for candidate, score in subscribed[:8]
    ]
    selected.extend(
        (candidate, float(candidate.base_score), "exploration") for candidate in exploration[:2]
    )
    if len(selected) < 10:
        selected.extend(
            (candidate, score, "subscription") for candidate, score in subscribed[8 : 10 - len(selected) + 8]
        )

    return [
        RankedItem(
            article_id=candidate.article_id,
            rank=index,
            rank_score=round(score, 2),
            tier=_tier_for_score(candidate.base_score),
            reason="B4 deterministic ranking",
            source=source,
        )
        for index, (candidate, score, source) in enumerate(selected[:10], start=1)
    ]


def _eligible_candidates(
    candidates: list[Candidate],
    article_status_by_article: dict[int, str | None],
    reference_time: datetime,
) -> list[Candidate]:
    filtered = [
        candidate
        for candidate in _dedupe_candidates(candidates)
        if article_status_by_article.get(candidate.article_id) not in {"read", "skipped"}
        and not _is_duplicate_hard_filtered(candidate)
    ]
    recent = _within_days(filtered, reference_time, 3)
    if len(recent) >= 10:
        return recent
    return _within_days(filtered, reference_time, 14)


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_id: dict[int, Candidate] = {}
    feed_ids_by_id: dict[int, set[int]] = {}
    risk_flags_by_id: dict[int, set[str]] = {}
    for candidate in candidates:
        existing = by_id.get(candidate.article_id)
        feed_ids_by_id.setdefault(candidate.article_id, set()).update(candidate.feed_ids)
        risk_flags_by_id.setdefault(candidate.article_id, set()).update(candidate.risk_flags or [])
        if existing is None or candidate.published_at > existing.published_at:
            by_id[candidate.article_id] = candidate
        by_id[candidate.article_id] = replace(
            by_id[candidate.article_id],
            feed_ids=sorted(feed_ids_by_id[candidate.article_id]),
            risk_flags=sorted(risk_flags_by_id[candidate.article_id]) or None,
        )
    return list(by_id.values())


def _is_duplicate_hard_filtered(candidate: Candidate) -> bool:
    return "duplicate" in (candidate.risk_flags or []) and candidate.base_score < 70


def _within_days(
    candidates: list[Candidate],
    reference_time: datetime,
    days: int,
) -> list[Candidate]:
    earliest = reference_time - timedelta(days=days)
    return [
        candidate
        for candidate in candidates
        if earliest <= candidate.published_at <= reference_time
    ]


def _feedback_adjustment(candidate: Candidate, feedback: Feedback | dict[str, object] | None) -> float:
    if feedback is None:
        return 0
    if isinstance(feedback, Feedback):
        feedback_type = feedback.feedback_type
        user_score = feedback.user_score
    else:
        feedback_type = str(feedback.get("feedback_type", "other"))
        raw_user_score = feedback.get("user_score")
        user_score = int(raw_user_score) if raw_user_score is not None else None
    adjustment = FEEDBACK_BASE_ADJUSTMENTS.get(feedback_type, 0)
    if user_score is not None:
        adjustment += (user_score - candidate.base_score) * 0.2
    return _clamp(adjustment, -20, 12)


def _freshness_adjustment(published_at: datetime, now: datetime) -> int:
    age = now - published_at
    if age <= timedelta(hours=24):
        return 3
    if age <= timedelta(hours=72):
        return 1
    if age > timedelta(days=7):
        return -4
    return 0


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _tier_for_score(score: int) -> str:
    if score >= 85:
        return "must_read"
    if score >= 70:
        return "read"
    if score >= 50:
        return "skim"
    return "skip"
