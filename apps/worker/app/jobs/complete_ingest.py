"""Barrier between asynchronous content fetches and automatic scoring."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Protocol

from app.runner import RetryableJobError


ACTIVE_JOB_STATUSES = frozenset({"queued", "running"})


class IngestPipelineSink(Protocol):
    def fetch_job_statuses(self, job_ids: Sequence[int]) -> dict[int, str]: ...

    def enqueue_auto_score(
        self,
        payload: dict[str, object],
        *,
        pipeline_cycle: str,
    ) -> None: ...


def complete_ingest_cycle(
    payload: Mapping[str, object],
    sink: IngestPipelineSink,
) -> dict[str, object]:
    pipeline_cycle = str(payload.get("pipeline_cycle") or "").strip()
    if not pipeline_cycle:
        raise ValueError("pipeline_cycle is required")
    raw_job_ids = payload.get("fetch_job_ids", [])
    if not isinstance(raw_job_ids, list) or any(
        isinstance(job_id, bool) or not isinstance(job_id, int)
        for job_id in raw_job_ids
    ):
        raise TypeError("fetch_job_ids must be a list of integers")
    raw_auto_score = payload.get("auto_score_payload", {})
    if not isinstance(raw_auto_score, Mapping):
        raise TypeError("auto_score_payload must be an object")

    job_ids = list(dict.fromkeys(raw_job_ids))
    statuses = sink.fetch_job_statuses(job_ids)
    missing = [job_id for job_id in job_ids if job_id not in statuses]
    if missing:
        raise RuntimeError(f"content fetch jobs missing: {missing}")
    active = [
        job_id for job_id in job_ids if statuses[job_id] in ACTIVE_JOB_STATUSES
    ]
    if active:
        raise RetryableJobError(
            f"content fetches still active for pipeline cycle: {len(active)}"
        )

    sink.enqueue_auto_score(dict(raw_auto_score), pipeline_cycle=pipeline_cycle)
    return {
        "pipeline_cycle": pipeline_cycle,
        "fetches_total": len(job_ids),
        "fetches_failed": sum(statuses[job_id] == "failed" for job_id in job_ids),
        "auto_score_enqueued": True,
    }
