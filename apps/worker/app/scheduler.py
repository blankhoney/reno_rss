"""Worker-side schedule tick for unattended intelligence pipeline (GOAL §4.A).

Enabled only when SCHEDULER_ENABLED=true. Defaults off so prod cannot
accidentally burn LLM budget without an explicit operator action.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
import logging
from typing import Protocol


LOGGER = logging.getLogger(__name__)

SYNC_JOB_TYPE = "sync_miniflux_entries"
AUTO_SCORE_JOB_TYPE = "auto_score_candidates"
RECS_JOB_TYPE = "generate_recommendations"
BRIEF_JOB_TYPE = "generate_daily_brief"
GOVERN_JOB_TYPE = "govern_sources"


@dataclass(frozen=True)
class ScheduleSpec:
    job_type: str
    interval: timedelta
    payload: Mapping[str, object]
    priority: int = 0


@dataclass(frozen=True)
class DueJob:
    job_type: str
    payload: dict[str, object]
    dedupe_key: str
    priority: int
    bucket_start: datetime


class SchedulerQueue(Protocol):
    def has_dedupe_key(self, dedupe_key: str) -> bool: ...

    def enqueue(
        self,
        job_type: str,
        payload: dict[str, object],
        *,
        dedupe_key: str,
        priority: int = 0,
        max_attempts: int = 5,
    ) -> object: ...


def default_schedule_specs(
    *,
    sync_limit: int = 100,
    score_lookback_hours: int = 72,
    score_max_articles: int = 30,
) -> tuple[ScheduleSpec, ...]:
    """Full unattended intel loop: sync → score → recs → brief → source governance.

    Still gated by SCHEDULER_ENABLED so operators must opt in before spend.
    """
    return (
        ScheduleSpec(
            job_type=SYNC_JOB_TYPE,
            interval=timedelta(hours=1),
            payload={"limit": sync_limit, "trigger": "scheduled"},
            priority=5,
        ),
        ScheduleSpec(
            job_type=AUTO_SCORE_JOB_TYPE,
            interval=timedelta(hours=6),
            payload={
                "lookback_hours": score_lookback_hours,
                "max_articles": score_max_articles,
                "trigger": "scheduled",
            },
            priority=3,
        ),
        ScheduleSpec(
            job_type=RECS_JOB_TYPE,
            interval=timedelta(hours=6),
            payload={"algorithm_version": "b4.v1", "trigger": "scheduled"},
            priority=2,
        ),
        ScheduleSpec(
            job_type=BRIEF_JOB_TYPE,
            interval=timedelta(hours=6),
            payload={"limit": 10, "trigger": "scheduled"},
            priority=1,
        ),
        ScheduleSpec(
            job_type=GOVERN_JOB_TYPE,
            interval=timedelta(hours=12),
            payload={
                "limit": 500,
                "min_samples": 5,
                "bad_ratio_threshold": 0.6,
                "dry_run": False,
                "trigger": "scheduled",
            },
            priority=0,
        ),
    )


def bucket_start(now: datetime, interval: timedelta) -> datetime:
    """Floor `now` to the start of its interval bucket in UTC."""
    if now.tzinfo is None:
        now = now.replace(tzinfo=UTC)
    else:
        now = now.astimezone(UTC)
    if interval <= timedelta(0):
        raise ValueError("interval must be positive")
    epoch = datetime(1970, 1, 1, tzinfo=UTC)
    seconds = int(interval.total_seconds())
    elapsed = int((now - epoch).total_seconds())
    floored = elapsed - (elapsed % seconds)
    return epoch + timedelta(seconds=floored)


def sched_dedupe_key(job_type: str, bucket: datetime) -> str:
    if bucket.tzinfo is None:
        bucket = bucket.replace(tzinfo=UTC)
    else:
        bucket = bucket.astimezone(UTC)
    return f"sched:{job_type}:{bucket.isoformat()}"


def due_jobs(
    now: datetime,
    specs: Sequence[ScheduleSpec],
    *,
    existing_dedupe_keys: set[str] | None = None,
) -> list[DueJob]:
    """Return jobs that should be enqueued for the current time buckets.

    Dedupe keys are time-bucket scoped and intended to apply to **any** job
    status (not only queued/running) so a finished short job cannot be
    re-enqueued in the same bucket.
    """
    known = existing_dedupe_keys or set()
    due: list[DueJob] = []
    for spec in specs:
        start = bucket_start(now, spec.interval)
        key = sched_dedupe_key(spec.job_type, start)
        if key in known:
            continue
        due.append(
            DueJob(
                job_type=spec.job_type,
                payload=dict(spec.payload),
                dedupe_key=key,
                priority=spec.priority,
                bucket_start=start,
            )
        )
    return due


def tick(
    queue: SchedulerQueue,
    *,
    now: datetime | None = None,
    specs: Sequence[ScheduleSpec] | None = None,
    enabled: bool = True,
) -> list[DueJob]:
    """Enqueue any due scheduled jobs. Returns the jobs that were enqueued."""
    if not enabled:
        return []
    current = now or datetime.now(UTC)
    schedule = specs if specs is not None else default_schedule_specs()
    enqueued: list[DueJob] = []
    for job in due_jobs(current, schedule):
        if queue.has_dedupe_key(job.dedupe_key):
            continue
        queue.enqueue(
            job.job_type,
            job.payload,
            dedupe_key=job.dedupe_key,
            priority=job.priority,
        )
        enqueued.append(job)
        LOGGER.info(
            "scheduler enqueued job_type=%s dedupe_key=%s bucket=%s",
            job.job_type,
            job.dedupe_key,
            job.bucket_start.isoformat(),
        )
    return enqueued


def env_flag_enabled(raw: str | None, *, default: bool = False) -> bool:
    if raw is None or not str(raw).strip():
        return default
    return str(raw).strip().lower() in {"1", "true", "yes", "on"}


def make_tick_callback(
    queue: SchedulerQueue,
    *,
    enabled: bool,
    specs: Sequence[ScheduleSpec] | None = None,
    now_fn: Callable[[], datetime] | None = None,
) -> Callable[[], None]:
    def _on_tick() -> None:
        tick(
            queue,
            now=(now_fn or (lambda: datetime.now(UTC)))(),
            specs=specs,
            enabled=enabled,
        )

    return _on_tick
