from datetime import UTC, datetime, timedelta

from app.domain.spaced_review import (
    REVIEW_INTERVALS_DAYS,
    advance_review_schedule,
    initial_review_schedule,
    is_due,
    next_interval_days,
)


def test_initial_review_is_immediately_due():
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    schedule = initial_review_schedule(now)
    assert schedule.interval_days == 1
    assert schedule.review_count == 0
    assert is_due(schedule.next_review_at, now=now)


def test_remembered_advances_ladder():
    assert next_interval_days(1, remembered=True) == 3
    assert next_interval_days(3, remembered=True) == 7
    assert next_interval_days(7, remembered=True) == 14
    assert next_interval_days(14, remembered=True) == 30
    assert next_interval_days(30, remembered=True) == 30
    assert next_interval_days(1, remembered=False) == 1
    assert REVIEW_INTERVALS_DAYS == (1, 3, 7, 14, 30)


def test_advance_review_schedule_sets_future_due_date():
    now = datetime(2026, 7, 18, 12, 0, tzinfo=UTC)
    next_state = advance_review_schedule(
        interval_days=1,
        review_count=0,
        remembered=True,
        now=now,
    )
    assert next_state.interval_days == 3
    assert next_state.review_count == 1
    assert next_state.next_review_at == now + timedelta(days=3)
    assert not is_due(next_state.next_review_at, now=now)
    assert is_due(next_state.next_review_at, now=now + timedelta(days=3))
