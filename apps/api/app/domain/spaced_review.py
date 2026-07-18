"""SM-2 lite spaced-review scheduling for private annotations."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

# Readwise-style ladder: each successful review advances one step.
REVIEW_INTERVALS_DAYS: tuple[int, ...] = (1, 3, 7, 14, 30)


@dataclass(frozen=True)
class ReviewSchedule:
    next_review_at: datetime
    interval_days: int
    review_count: int


def initial_review_schedule(now: datetime | None = None) -> ReviewSchedule:
    """New highlights are due immediately (interval ladder starts at 1 day)."""
    moment = _as_utc(now or datetime.now(UTC))
    return ReviewSchedule(
        next_review_at=moment,
        interval_days=REVIEW_INTERVALS_DAYS[0],
        review_count=0,
    )


def next_interval_days(current_interval_days: int, *, remembered: bool) -> int:
    """Advance or reset the interval ladder (pure)."""
    if not remembered:
        return REVIEW_INTERVALS_DAYS[0]
    try:
        index = REVIEW_INTERVALS_DAYS.index(int(current_interval_days))
    except (ValueError, TypeError):
        return REVIEW_INTERVALS_DAYS[0]
    return REVIEW_INTERVALS_DAYS[min(index + 1, len(REVIEW_INTERVALS_DAYS) - 1)]


def advance_review_schedule(
    *,
    interval_days: int,
    review_count: int,
    remembered: bool,
    now: datetime | None = None,
) -> ReviewSchedule:
    """Compute the next review state after a remember/forget response."""
    moment = _as_utc(now or datetime.now(UTC))
    next_interval = next_interval_days(interval_days, remembered=remembered)
    return ReviewSchedule(
        next_review_at=moment + timedelta(days=next_interval),
        interval_days=next_interval,
        review_count=max(0, int(review_count)) + 1,
    )


def is_due(
    next_review_at: datetime | None,
    *,
    now: datetime | None = None,
    created_at: datetime | None = None,
) -> bool:
    """NULL next_review_at falls back to created_at, then treats as due."""
    moment = _as_utc(now or datetime.now(UTC))
    due_at = next_review_at if next_review_at is not None else created_at
    if due_at is None:
        return True
    return _as_utc(due_at) <= moment


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=UTC)
    return value.astimezone(UTC)
