"""
Baseline scoring module.

Scoring strategy: length-based heuristic.
- Score is derived from combined title+content length, capped at 100.
- Tags are keyword-extracted from title words (simple split).
- This is intentionally trivial; replace with an LLM call in a later phase.
"""

from __future__ import annotations

import hashlib

_MODEL_PROVIDER = "baseline"
_MODEL_NAME = "length-baseline"
_MODEL_VERSION = "0.1.0"
_PROMPT_VERSION = "none"


def score_entry(entry: dict) -> dict:
    """
    Score a single Miniflux entry dict.

    Args:
        entry: dict with at least "id", "title", "content" keys.

    Returns:
        Scoring payload dict with all required fields.
    """
    title: str = entry.get("title") or ""
    content: str = entry.get("content") or ""
    combined = (title + " " + content).strip()

    if not combined:
        return {
            "score": 0,
            "tags": [],
            "reason": "empty content",
            "model_version": _MODEL_VERSION,
            "model_provider": _MODEL_PROVIDER,
            "model_name": _MODEL_NAME,
            "prompt_version": _PROMPT_VERSION,
            "confidence": 0.0,
            "scoring_status": "error",
            "error_message": "title and content are both empty",
        }

    # Length-based score: every 50 chars = 1 point, capped at 100
    raw_score = min(100, len(combined) // 50)

    # Naive tag extraction: unique lowercase words from title (≥4 chars)
    tags = list({w.lower() for w in title.split() if len(w) >= 4})[:5]

    content_hash = hashlib.sha256(combined.encode()).hexdigest()[:16]

    return {
        "score": raw_score,
        "tags": tags,
        "reason": f"length={len(combined)} hash={content_hash}",
        "model_version": _MODEL_VERSION,
        "model_provider": _MODEL_PROVIDER,
        "model_name": _MODEL_NAME,
        "prompt_version": _PROMPT_VERSION,
        "confidence": round(min(1.0, len(combined) / 500), 3),
        "scoring_status": "success",
        "error_message": None,
    }
