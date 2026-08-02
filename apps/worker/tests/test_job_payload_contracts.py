import logging

import pytest

from app.jobs.queue import InMemoryJobQueue
from app.jobs.score_batch import score_batch
from app.runner import run_once


class RecordingSink:
    def __init__(self) -> None:
        self.list_calls = 0
        self.saved = []

    def list_batch_articles(self, batch_id):
        self.list_calls += 1
        return [{"id": 101, "title": "Fixture article"}]

    def save_score(self, article_id, score):
        self.saved.append((article_id, dict(score)))


class RecordingProvider:
    def __init__(self) -> None:
        self.calls = 0

    def score_article(self, article, rubric):
        self.calls += 1
        return {
            "base_score": 80,
            "recommendation_tier": "read",
            "scoring_status": "success",
        }


def test_score_batch_accepts_explicit_v1_before_provider_work():
    sink = RecordingSink()
    provider = RecordingProvider()

    result = score_batch({"payload_version": 1, "batch_id": 7}, sink, provider)

    assert result["batch_id"] == 7
    assert sink.list_calls == 1
    assert provider.calls == 1


def test_score_batch_accepts_unversioned_payload_as_explicit_legacy(caplog):
    sink = RecordingSink()
    provider = RecordingProvider()

    with caplog.at_level(logging.WARNING):
        score_batch({"batch_id": 7}, sink, provider)

    assert sink.list_calls == 1
    assert provider.calls == 1
    assert "legacy" in caplog.text
    assert "score_batch" in caplog.text


@pytest.mark.parametrize("payload_version", [2, "1", True, None])
def test_score_batch_rejects_unknown_payload_version_before_side_effects(payload_version):
    sink = RecordingSink()
    provider = RecordingProvider()

    with pytest.raises(ValueError, match="payload_version"):
        score_batch(
            {"payload_version": payload_version, "batch_id": 7},
            sink,
            provider,
        )

    assert sink.list_calls == 0
    assert provider.calls == 0
    assert sink.saved == []


def test_runner_marks_unsupported_score_payload_failed_without_retrying():
    sink = RecordingSink()
    provider = RecordingProvider()
    queue = InMemoryJobQueue()
    job = queue.enqueue(
        "score_batch",
        {"payload_version": 2, "batch_id": 7},
        dedupe_key="score-contract:7",
    )

    handled = run_once(
        queue,
        {"score_batch": lambda payload: score_batch(payload, sink, provider)},
        worker_id="worker-contract",
    )

    stored = queue._jobs[job.id]
    assert handled is True
    assert stored.status == "failed"
    assert stored.last_error is not None
    assert "payload_version" in stored.last_error
    assert sink.list_calls == 0
    assert provider.calls == 0
