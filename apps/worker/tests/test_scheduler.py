from datetime import UTC, datetime, timedelta

from app.jobs.queue import InMemoryJobQueue
from app.scheduler import (
    AUTO_SCORE_JOB_TYPE,
    SYNC_JOB_TYPE,
    ScheduleSpec,
    bucket_start,
    due_jobs,
    env_flag_enabled,
    sched_dedupe_key,
    tick,
)


def test_bucket_start_floors_to_interval():
    now = datetime(2026, 7, 18, 13, 45, tzinfo=UTC)
    assert bucket_start(now, timedelta(hours=1)) == datetime(2026, 7, 18, 13, 0, tzinfo=UTC)
    assert bucket_start(now, timedelta(hours=6)) == datetime(2026, 7, 18, 12, 0, tzinfo=UTC)


def test_due_jobs_skips_known_dedupe_keys():
    now = datetime(2026, 7, 18, 13, 10, tzinfo=UTC)
    specs = (
        ScheduleSpec(SYNC_JOB_TYPE, timedelta(hours=1), {"limit": 50}),
        ScheduleSpec(AUTO_SCORE_JOB_TYPE, timedelta(hours=6), {"max_articles": 10}),
    )
    sync_key = sched_dedupe_key(SYNC_JOB_TYPE, bucket_start(now, timedelta(hours=1)))
    due = due_jobs(now, specs, existing_dedupe_keys={sync_key})
    assert [job.job_type for job in due] == [AUTO_SCORE_JOB_TYPE]


def test_tick_enqueues_once_per_bucket_even_after_success():
    queue = InMemoryJobQueue()
    now = datetime(2026, 7, 18, 13, 10, tzinfo=UTC)
    specs = (ScheduleSpec(SYNC_JOB_TYPE, timedelta(hours=1), {"limit": 25}, priority=5),)

    first = tick(queue, now=now, specs=specs, enabled=True)
    assert len(first) == 1
    job = queue.claim_next("w1")
    assert job is not None
    queue.mark_succeeded(job.id, {"ok": True}, worker_id="w1")

    second = tick(queue, now=now, specs=specs, enabled=True)
    assert second == []
    assert queue.has_dedupe_key(first[0].dedupe_key)


def test_tick_disabled_is_noop():
    queue = InMemoryJobQueue()
    now = datetime(2026, 7, 18, 13, 10, tzinfo=UTC)
    assert tick(queue, now=now, enabled=False) == []
    assert queue.claim_next("w1") is None


def test_env_flag_enabled():
    assert env_flag_enabled(None) is False
    assert env_flag_enabled("true") is True
    assert env_flag_enabled("0") is False
    assert env_flag_enabled("yes") is True
