"""
TDD: Task 4 — score_entry payload shape test.

This test MUST fail before scoring.py is implemented,
and PASS after the baseline implementation is complete.
"""

import sys
import os
import httpx

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from llm_client import LLMClientError  # noqa: E402
from scoring import score_entry  # noqa: E402


REQUIRED_KEYS = {
    "score",
    "tags",
    "reason",
    "model_version",
    "model_provider",
    "model_name",
    "prompt_version",
    "confidence",
    "scoring_status",
    "error_message",
}


def test_score_payload_shape():
    payload = score_entry({"id": 1, "title": "hello", "content": "world"})
    assert set(payload.keys()) == REQUIRED_KEYS


def test_score_returns_int_score():
    payload = score_entry({"id": 2, "title": "x" * 10, "content": "y" * 100})
    assert isinstance(payload["score"], int)
    assert 0 <= payload["score"] <= 100


def test_score_tags_is_list():
    payload = score_entry({"id": 3, "title": "Tech AI", "content": "about machine learning"})
    assert isinstance(payload["tags"], list)


def test_score_status_on_missing_content():
    payload = score_entry({"id": 4, "title": "no content", "content": ""})
    assert payload["scoring_status"] in ("success", "error")


def test_model_fields_are_strings():
    payload = score_entry({"id": 5, "title": "t", "content": "c"})
    for field in ("model_version", "model_provider", "model_name", "prompt_version"):
        assert isinstance(payload[field], str), f"{field} must be str"


class FakeLLMClient:
    model = "MiniMax-M2.7"

    def __init__(self, content=None, exc=None):
        self.content = content
        self.exc = exc

    def chat_completion(self, messages):
        assert messages
        if self.exc:
            raise self.exc
        return self.content


def test_score_entry_uses_minimax_json_response():
    payload = score_entry(
        {"id": 6, "title": "AI news", "content": "important model release"},
        llm_client=FakeLLMClient(
            '{"score": 88, "tags": ["ai", "release", "extra", "trimmed"], '
            '"reason": "High signal for model updates.", "confidence": 0.82}'
        ),
    )

    assert set(payload.keys()) == REQUIRED_KEYS
    assert payload["score"] == 88
    assert payload["tags"] == ["ai", "release", "extra"]
    assert payload["reason"] == "High signal for model updates."
    assert payload["confidence"] == 0.82
    assert payload["model_provider"] == "minimax"
    assert payload["model_name"] == "MiniMax-M2.7"
    assert payload["prompt_version"] == "rss-score-v1"
    assert payload["scoring_status"] == "success"
    assert payload["error_message"] is None


def test_score_entry_falls_back_on_non_json_response():
    payload = score_entry(
        {"id": 7, "title": "Broken", "content": "not json"},
        llm_client=FakeLLMClient("not json"),
    )

    assert set(payload.keys()) == REQUIRED_KEYS
    assert isinstance(payload["score"], int)
    assert payload["model_provider"] == "baseline"
    assert payload["scoring_status"] == "error"
    assert "invalid llm json" in payload["error_message"]


def test_score_entry_falls_back_on_timeout():
    payload = score_entry(
        {"id": 8, "title": "Timeout", "content": "slow"},
        llm_client=FakeLLMClient(exc=httpx.TimeoutException("too slow")),
    )

    assert isinstance(payload["score"], int)
    assert payload["model_provider"] == "baseline"
    assert payload["scoring_status"] == "error"
    assert "timeout" in payload["error_message"]


def test_score_entry_falls_back_on_unauthorized():
    payload = score_entry(
        {"id": 9, "title": "Auth", "content": "bad key"},
        llm_client=FakeLLMClient(exc=LLMClientError("unauthorized", status_code=401)),
    )

    assert isinstance(payload["score"], int)
    assert payload["model_provider"] == "baseline"
    assert payload["scoring_status"] == "error"
    assert "401" in payload["error_message"]
