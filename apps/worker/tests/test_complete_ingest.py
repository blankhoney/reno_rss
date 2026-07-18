import pytest

from app.jobs.complete_ingest import complete_ingest_cycle
from app.runner import RetryableJobError


class FakeIngestSink:
    def __init__(self, statuses):
        self.statuses = dict(statuses)
        self.enqueued = []

    def fetch_job_statuses(self, job_ids):
        return {job_id: self.statuses[job_id] for job_id in job_ids}

    def enqueue_auto_score(self, payload, *, pipeline_cycle):
        self.enqueued.append((dict(payload), pipeline_cycle))


def test_complete_ingest_waits_for_active_content_fetches():
    sink = FakeIngestSink({10: "succeeded", 11: "running"})

    with pytest.raises(RetryableJobError, match="content fetches still active"):
        complete_ingest_cycle(
            {
                "pipeline_cycle": "2026-07-18T12:00:00+00:00",
                "fetch_job_ids": [10, 11],
                "auto_score_payload": {"lookback_hours": 72},
            },
            sink,
        )

    assert sink.enqueued == []


def test_complete_ingest_enqueues_scoring_after_all_fetches_are_terminal():
    sink = FakeIngestSink({10: "succeeded", 11: "failed"})

    result = complete_ingest_cycle(
        {
            "pipeline_cycle": "2026-07-18T12:00:00+00:00",
            "fetch_job_ids": [10, 11],
            "auto_score_payload": {"lookback_hours": 72, "max_articles": 30},
        },
        sink,
    )

    assert sink.enqueued == [
        (
            {"lookback_hours": 72, "max_articles": 30},
            "2026-07-18T12:00:00+00:00",
        )
    ]
    assert result == {
        "pipeline_cycle": "2026-07-18T12:00:00+00:00",
        "fetches_total": 2,
        "fetches_failed": 1,
        "auto_score_enqueued": True,
    }
