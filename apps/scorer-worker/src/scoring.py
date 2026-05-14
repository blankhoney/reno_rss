"""Scoring module backed by Minimax with a baseline fallback."""

from __future__ import annotations

import json
from typing import Any

import httpx

from llm_client import LLMClientError, MinimaxLLMClient

_MODEL_PROVIDER = "baseline"
_MODEL_NAME = "length-baseline"
_MODEL_VERSION = "0.1.0"
_PROMPT_VERSION = "rss-score-v3"
_LLM_MODEL_PROVIDER = "minimax"
_DIMENSION_KEYS = (
    "importance",
    "usefulness",
    "timeliness",
    "depth",
    "technical_value",
    "business_value",
    "trend_value",
)
_MAX_TAGS = 3
_MAX_REASON_LENGTH = 240
_MAX_SUMMARY_LENGTH = 420
_MAX_DIMENSION_REASON_LENGTH = 120
_MAX_CONTENT_CHARS = 6000


def score_entry(entry: dict, llm_client: MinimaxLLMClient | None = None) -> dict:
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
        return _baseline_payload(title, combined, "title and content are both empty")

    client = llm_client or MinimaxLLMClient()
    try:
        result = _parse_llm_json(client.chat_completion(_build_messages(title, content)))
    except Exception as exc:  # noqa: BLE001
        return _baseline_payload(title, combined, _format_error(exc))

    model_name = getattr(client, "model", "unknown")
    return {
        "score": result["score"],
        "dimension_scores": result["dimension_scores"],
        "tags": result["tags"],
        "reason": result["reason"],
        "summary_zh": result["summary_zh"],
        "summary_original": result["summary_original"],
        "source_language": result["source_language"],
        "dimension_reasons": result["dimension_reasons"],
        "model_version": f"{_LLM_MODEL_PROVIDER}:{model_name}:{_PROMPT_VERSION}",
        "model_provider": _LLM_MODEL_PROVIDER,
        "model_name": model_name,
        "prompt_version": _PROMPT_VERSION,
        "confidence": result["confidence"],
        "scoring_status": "success",
        "error_message": None,
    }


def _baseline_payload(title: str, combined: str, error_message: str | None) -> dict:
    # Length-based score: every 50 chars = 1 point, capped at 100
    raw_score = min(100, len(combined) // 50)

    # Naive tag extraction: unique lowercase words from title (≥4 chars)
    tags = list({w.lower() for w in title.split() if len(w) >= 4})[:5]

    return {
        "score": raw_score,
        "dimension_scores": {key: raw_score for key in _DIMENSION_KEYS},
        "tags": tags,
        "reason": "评分失败，需重新评分。",
        "summary_zh": "",
        "summary_original": "",
        "source_language": "unknown",
        "dimension_reasons": {},
        "model_version": _MODEL_VERSION,
        "model_provider": _MODEL_PROVIDER,
        "model_name": _MODEL_NAME,
        "prompt_version": _PROMPT_VERSION,
        "confidence": round(min(1.0, len(combined) / 500), 3),
        "scoring_status": "error" if error_message else "success",
        "error_message": error_message,
    }


def _build_messages(title: str, content: str) -> list[dict[str, str]]:
    clipped_content = content[:_MAX_CONTENT_CHARS]
    return [
        {
            "role": "system",
            "content": (
                "You score RSS entries for a personal reading digest. "
                "Return strict JSON only (no markdown fences, no comments, no text outside JSON). "
                "The JSON object must include keys: overall, importance, usefulness, timeliness, "
                "depth, technical_value, business_value, trend_value, tags, reason, summary_zh, "
                "summary_original, source_language, dimension_reasons, confidence. "
                "overall and the seven dimension keys (importance, usefulness, timeliness, depth, "
                "technical_value, business_value, trend_value) must be integers from 0 to 100. "
                "Judge each dimension independently; do not copy the same score across dimensions "
                "unless the content truly warrants it. "
                "confidence may be a float from 0.0 to 1.0 or a number from 0 to 100; values above 1 "
                "are treated as a 0-100 scale and normalized to 0.0-1.0. "
                "tags must be a JSON array of short strings. reason must be a short Chinese string. "
                "summary_zh must be a one or two sentence Chinese summary for a Chinese reader. "
                "summary_original must be a one or two sentence summary in the source language. "
                "source_language must be a short language code such as zh, en, ja, ko, or unknown. "
                "dimension_reasons must be an object with one short Chinese reason for each score "
                "dimension key."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Title:\n{title}\n\n"
                f"Content:\n{clipped_content}\n\n"
                "JSON response only."
            ),
        },
    ]


def _parse_llm_json(raw: str) -> dict[str, Any]:
    data = _load_llm_json(raw)

    _require_fields(
        data,
        [
            "overall",
            *_DIMENSION_KEYS,
            "tags",
            "reason",
            "summary_zh",
            "summary_original",
            "source_language",
            "dimension_reasons",
            "confidence",
        ],
    )

    score = _clamp_int(data["overall"], minimum=0, maximum=100)

    dimension_scores = {
        key: _clamp_int(data[key], minimum=0, maximum=100) for key in _DIMENSION_KEYS
    }

    tags = _normalize_tags(data.get("tags"))
    reason = _trim_reason(str(data.get("reason") or "No reason provided."))
    summary_zh = _trim_text(data.get("summary_zh"), _MAX_SUMMARY_LENGTH)
    summary_original = _trim_text(data.get("summary_original"), _MAX_SUMMARY_LENGTH)
    source_language = _trim_text(data.get("source_language"), 24).lower() or "unknown"
    dimension_reasons = _normalize_dimension_reasons(data.get("dimension_reasons"))
    confidence = _parse_confidence(data.get("confidence"))
    return {
        "score": score,
        "dimension_scores": dimension_scores,
        "tags": tags,
        "reason": reason,
        "summary_zh": summary_zh,
        "summary_original": summary_original,
        "source_language": source_language,
        "dimension_reasons": dimension_reasons,
        "confidence": confidence,
    }


def _require_fields(data: dict[str, Any], keys: list[str]) -> None:
    for key in keys:
        if key not in data:
            raise ValueError(f"missing required llm field: {key}")


def _load_llm_json(raw: str) -> dict[str, Any]:
    cleaned = _strip_think_blocks(raw).strip()
    candidates = [cleaned]
    extracted = _extract_first_json_object(cleaned)
    if extracted is not None and extracted != cleaned:
        candidates.append(extracted)

    last_error: Exception | None = None
    for candidate in candidates:
        try:
            data = json.loads(candidate)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
        if isinstance(data, dict):
            return data
        last_error = ValueError("llm json root is not an object")

    raise ValueError("invalid llm json") from last_error


def _strip_think_blocks(raw: str) -> str:
    output: list[str] = []
    cursor = 0
    lowered = raw.lower()

    while cursor < len(raw):
        start = lowered.find("<think>", cursor)
        if start == -1:
            output.append(raw[cursor:])
            break

        output.append(raw[cursor:start])
        end = lowered.find("</think>", start + len("<think>"))
        if end == -1:
            break
        cursor = end + len("</think>")

    return "".join(output)


def _extract_first_json_object(text: str) -> str | None:
    start = text.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False

        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue

            if char == '"':
                in_string = True
            elif char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]

        start = text.find("{", start + 1)

    return None


def _normalize_tags(raw_tags: Any) -> list[str]:
    if not isinstance(raw_tags, list):
        return []
    tags: list[str] = []
    for tag in raw_tags:
        normalized = str(tag).strip().lower()
        if normalized and normalized not in tags:
            tags.append(normalized[:32])
        if len(tags) >= _MAX_TAGS:
            break
    return tags


def _normalize_dimension_reasons(raw_reasons: Any) -> dict[str, str]:
    if not isinstance(raw_reasons, dict):
        raise ValueError("dimension_reasons must be an object")
    reasons: dict[str, str] = {}
    for key in _DIMENSION_KEYS:
        if key not in raw_reasons:
            raise ValueError(f"missing required llm field: dimension_reasons.{key}")
        reasons[key] = _trim_text(raw_reasons[key], _MAX_DIMENSION_REASON_LENGTH)
    return reasons


def _trim_reason(reason: str) -> str:
    clean = " ".join(reason.split())
    return clean[:_MAX_REASON_LENGTH]


def _trim_text(value: Any, max_length: int) -> str:
    clean = " ".join(str(value or "").split())
    return clean[:max_length]


def _parse_confidence(value: Any) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return round(0.0, 3)
    if parsed > 1.0:
        parsed = parsed / 100.0
    return round(max(0.0, min(1.0, parsed)), 3)


def _clamp_int(value: Any, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = minimum
    return max(minimum, min(maximum, parsed))


def _format_error(exc: Exception) -> str:
    if isinstance(exc, httpx.TimeoutException):
        return "timeout while calling llm provider"
    if isinstance(exc, LLMClientError) and exc.status_code:
        return f"llm provider HTTP {exc.status_code}: {exc}"
    return str(exc)[:_MAX_REASON_LENGTH]
