"""
TDD: Task 4 — score_entry payload shape test.

This test MUST fail before scoring.py is implemented,
and PASS after the baseline implementation is complete.
"""

import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

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
