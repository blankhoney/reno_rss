from __future__ import annotations

from dataclasses import dataclass
import json
import logging
import os
import re
from collections.abc import Mapping, Sequence
from typing import Protocol, TypedDict

import httpx


DIMENSION_KEYS = (
    "topic_relevance",
    "information_density",
    "source_quality",
    "novelty",
    "timeliness",
    "actionability",
    "reading_cost_fit",
    "risk_uncertainty",
)

RISK_FLAG_ALIASES = {
    "reposted": "duplicate",
    "reprint": "duplicate",
    "syndicated": "duplicate",
}

DEFAULT_MINIMAX_BASE_URL = "https://api.minimax.io/v1"
DEFAULT_MINIMAX_MODEL = "MiniMax-M2.7"
DEFAULT_LLM_TIMEOUT_SECONDS = 30.0
TRANSLATE_INPUT_LIMIT = 12_000

_LOGGER = logging.getLogger(__name__)


class ArticleScore(TypedDict):
    base_score: int
    dimension_scores: dict[str, int]
    dimension_reasons: dict[str, str]
    summary_zh: str
    summary_original: str
    source_language: str
    tags: list[str]
    reason: str
    risk_flags: list[str]
    confidence: float
    scoring_status: str
    recommendation_tier: str


class LLMProvider(Protocol):
    def score_article(
        self,
        article: Mapping[str, object],
        rubric: Mapping[str, object],
    ) -> ArticleScore: ...

    def translate_article(self, article: Mapping[str, object]) -> str: ...


class MockProvider:
    def score_article(
        self,
        article: Mapping[str, object],
        rubric: Mapping[str, object],
    ) -> ArticleScore:
        text = _article_text(article)
        lower_text = text.lower()
        topic_hits = sum(
            1
            for keyword in ("ai", "agent", "rag", "llm", "code", "python", "product")
            if keyword in lower_text
        )
        risk_hits = sum(
            1
            for keyword in ("sponsored", "promo", "advertisement", "clickbait")
            if keyword in lower_text
        )
        length_score = _clamp_int(len(text) // 35)
        risk_score = _clamp_int(20 + risk_hits * 25)
        dimension_scores = {
            "topic_relevance": _clamp_int(45 + topic_hits * 12),
            "information_density": _clamp_int(35 + length_score),
            "source_quality": _clamp_int(65 - risk_hits * 10),
            "novelty": 60,
            "timeliness": 65 if article.get("published_at") else 50,
            "actionability": 75
            if any(word in lower_text for word in ("guide", "code", "how", "deploy"))
            else 52,
            "reading_cost_fit": _clamp_int(78 - max(len(text) - 4000, 0) // 100),
            "risk_uncertainty": risk_score,
        }
        positive_dimensions = [
            score
            for key, score in dimension_scores.items()
            if key != "risk_uncertainty"
        ]
        base_score = _clamp_int(
            round(sum(positive_dimensions) / len(positive_dimensions))
            - round(risk_score * 0.2)
        )
        summary_original = _truncate(_squash_whitespace(text), 420)
        source_language = _detect_language(text)
        summary_zh = (
            summary_original
            if source_language == "zh"
            else "【示例摘要】这是 mock provider 生成的中文占位摘要，未接入真实翻译。"
        )
        score = {
            "base_score": base_score,
            "dimension_scores": dimension_scores,
            "dimension_reasons": {
                key: "MockProvider deterministic rule score."
                for key in DIMENSION_KEYS
            },
            "summary_zh": summary_zh,
            "summary_original": summary_original,
            "source_language": source_language,
            "tags": _mock_tags(text),
            "reason": "MockProvider baseline based on topic, density, source, action, and risk signals.",
            "risk_flags": ["marketing"] if risk_hits else [],
            "confidence": 0.6,
            "scoring_status": "success",
        }
        return normalize_score(score)

    def translate_article(self, article: Mapping[str, object]) -> str:
        text = _squash_whitespace(_article_text(article))
        title = _string(article.get("title")) or "未命名文章"
        return f"<p>中文译文（mock）：{title}</p><p>{_truncate(text, 800)}</p>"


class MiniMaxProvider:
    model_provider = "minimax"

    def __init__(self, client: object) -> None:
        self.client = client
        self.model_name = getattr(client, "model", "unknown")

    def score_article(
        self,
        article: Mapping[str, object],
        rubric: Mapping[str, object],
    ) -> ArticleScore:
        response = self.client.chat_completion(_score_messages(article, rubric))
        content = _response_content(response)
        score = normalize_score(_load_llm_json(content))
        if score["source_language"] != "zh" and not _looks_chinese(score["summary_zh"]):
            _LOGGER.warning("summary_zh not Chinese for non-zh article (provider=minimax)")
        return score

    def translate_article(self, article: Mapping[str, object]) -> str:
        response = self.client.chat_completion(_translation_messages(_limited_translation_article(article)))
        return _strip_think_blocks(_response_content(response)).strip()


@dataclass(frozen=True)
class MinimaxConfig:
    api_key: str
    base_url: str = DEFAULT_MINIMAX_BASE_URL
    model: str = DEFAULT_MINIMAX_MODEL
    timeout_seconds: float = DEFAULT_LLM_TIMEOUT_SECONDS

    @classmethod
    def from_env(cls) -> MinimaxConfig:
        return cls(
            api_key=os.environ.get("MINIMAX_API_KEY", ""),
            base_url=os.environ.get("MINIMAX_BASE_URL", DEFAULT_MINIMAX_BASE_URL).rstrip("/"),
            model=os.environ.get("MINIMAX_MODEL", DEFAULT_MINIMAX_MODEL),
            timeout_seconds=float(
                os.environ.get("LLM_TIMEOUT_SECONDS", str(DEFAULT_LLM_TIMEOUT_SECONDS))
            ),
        )


class MinimaxLLMClient:
    def __init__(self, config: MinimaxConfig | None = None) -> None:
        self.config = config or MinimaxConfig.from_env()
        self.model = self.config.model

    def chat_completion(self, messages: list[dict[str, str]]) -> str:
        if not self.config.api_key or self.config.api_key == "change_me":
            raise RuntimeError("missing MINIMAX_API_KEY")
        response = httpx.post(
            f"{self.config.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.config.api_key}"},
            json={
                "model": self.config.model,
                "messages": messages,
                "temperature": 0.2,
            },
            timeout=self.config.timeout_seconds,
        )
        response.raise_for_status()
        data = response.json()
        try:
            content = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise RuntimeError("llm response missing choices[0].message.content") from exc
        if not isinstance(content, str) or not content.strip():
            raise RuntimeError("llm response content is empty")
        return content


def create_provider(provider_name: str | None = None) -> LLMProvider:
    selected = (provider_name or os.environ.get("LLM_PROVIDER", "mock")).strip().lower()
    if selected == "mock":
        return MockProvider()
    if selected == "minimax":
        config = MinimaxConfig.from_env()
        if not config.api_key or config.api_key == "change_me":
            raise RuntimeError("MINIMAX_API_KEY is required when LLM_PROVIDER=minimax")
        return MiniMaxProvider(MinimaxLLMClient(config))
    raise ValueError("LLM_PROVIDER must be 'mock' or 'minimax'")


def tier_for_score(score: int | float) -> str:
    normalized = _clamp_int(score)
    if normalized >= 85:
        return "must_read"
    if normalized >= 70:
        return "read"
    if normalized >= 50:
        return "skim"
    return "skip"


def normalize_score(raw_score: Mapping[str, object]) -> ArticleScore:
    base_score = _clamp_int(raw_score.get("base_score", 0))
    dimension_scores = _normalize_dimension_scores(
        raw_score.get("dimension_scores"),
        default_score=base_score,
    )
    return {
        "base_score": base_score,
        "dimension_scores": dimension_scores,
        "dimension_reasons": _normalize_dimension_reasons(
            raw_score.get("dimension_reasons")
        ),
        "summary_zh": _truncate(_string(raw_score.get("summary_zh")), 800),
        "summary_original": _truncate(_string(raw_score.get("summary_original")), 420),
        "source_language": _truncate(
            _string(raw_score.get("source_language")) or "unknown",
            24,
        ),
        "tags": _normalize_tags(raw_score.get("tags")),
        "reason": _truncate(_string(raw_score.get("reason")), 240),
        "risk_flags": _normalize_risk_flags(raw_score.get("risk_flags")),
        "confidence": _normalize_confidence(raw_score.get("confidence")),
        "scoring_status": "success",
        "recommendation_tier": tier_for_score(base_score),
    }


def _score_messages(
    article: Mapping[str, object],
    rubric: Mapping[str, object],
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are the AI Reader scoring engine. Score one RSS article with a self-contained "
                "8-dimension rubric and return only a strict JSON object. Dimensions are: "
                "topic_relevance (fit to AI/product/engineering reading goals), "
                "information_density (amount of useful information), source_quality "
                "(credibility and primary-source quality), novelty (new insight vs repeated news), "
                "timeliness (freshness), actionability (clear next steps), reading_cost_fit "
                "(worth the time required), and risk_uncertainty (higher means more risk, hype, "
                "weak evidence, or uncertainty). Each dimension is 0-100. base_score is 0-100; "
                "tiers are must_read 85-100, read 70-84, skim 50-69, skip 0-49. Return exactly "
                "these JSON keys: base_score, dimension_scores, dimension_reasons, summary_zh, "
                "summary_original, source_language, tags, reason, risk_flags, confidence. "
                "summary_zh must be a real Chinese summary, not copied English; for non-Chinese "
                "articles translate and summarize into Chinese with 2-4 concise points. "
                "Do not output markdown, code fences, comments, or <think>."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {"article": dict(article), "rubric": dict(rubric)},
                ensure_ascii=False,
                default=str,
            ),
        },
    ]


def _translation_messages(article: Mapping[str, object]) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "Translate the article body into Simplified Chinese. Preserve paragraph/list/code "
                "structure as a safe HTML fragment. Do not include markdown fences, commentary, or "
                "<think>. Return only the translated HTML fragment."
            ),
        },
        {
            "role": "user",
            "content": json.dumps({"article": dict(article)}, ensure_ascii=False, default=str),
        },
    ]


def _load_llm_json(content: str) -> Mapping[str, object]:
    stripped = _strip_think_blocks(content).strip()
    try:
        loaded = json.loads(stripped)
    except json.JSONDecodeError:
        loaded = json.loads(_extract_first_json_object(stripped))
    if not isinstance(loaded, Mapping):
        raise TypeError("LLM response JSON must be an object")
    return loaded


def _strip_think_blocks(content: str) -> str:
    without_closed_blocks = re.sub(
        r"<think\b[^>]*>.*?</think>",
        "",
        content,
        flags=re.IGNORECASE | re.DOTALL,
    )
    return re.sub(
        r"<think\b[^>]*>.*$",
        "",
        without_closed_blocks,
        flags=re.IGNORECASE | re.DOTALL,
    )


def _limited_translation_article(article: Mapping[str, object]) -> dict[str, object]:
    limited = dict(article)
    for key in ("content_html", "content_text"):
        value = limited.get(key)
        if value is not None:
            limited[key] = _string(value)[:TRANSLATE_INPUT_LIMIT]
    return limited


def _extract_first_json_object(content: str) -> str:
    start = content.find("{")
    while start != -1:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(content)):
            char = content[index]
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
                    return content[start : index + 1]
        start = content.find("{", start + 1)
    raise ValueError("No JSON object found in LLM response")


def _response_content(response: object) -> str:
    if isinstance(response, str):
        return response
    if isinstance(response, Mapping):
        direct_content = response.get("content")
        if direct_content is not None:
            return _string(direct_content)
        choices = response.get("choices")
        if isinstance(choices, Sequence) and choices:
            return _choice_content(choices[0])

    choices = getattr(response, "choices", None)
    if isinstance(choices, Sequence) and choices:
        return _choice_content(choices[0])

    content = getattr(response, "content", None)
    if content is not None:
        return _string(content)
    return _string(response)


def _choice_content(choice: object) -> str:
    if isinstance(choice, Mapping):
        message = choice.get("message")
        if isinstance(message, Mapping):
            return _string(message.get("content"))
        return _string(choice.get("content"))

    message = getattr(choice, "message", None)
    if message is not None:
        return _string(getattr(message, "content", ""))
    return _string(getattr(choice, "content", ""))


def _normalize_dimension_scores(value: object, *, default_score: int) -> dict[str, int]:
    source = value if isinstance(value, Mapping) else {}
    return {
        key: _clamp_int(source.get(key, default_score))
        for key in DIMENSION_KEYS
    }


def _normalize_dimension_reasons(value: object) -> dict[str, str]:
    source = value if isinstance(value, Mapping) else {}
    return {
        key: _truncate(_string(source.get(key)) or "未提供。", 120)
        for key in DIMENSION_KEYS
    }


def _normalize_tags(value: object) -> list[str]:
    tags: list[str] = []
    for raw_tag in _sequence(value):
        tag = _truncate(_string(raw_tag).strip().lower(), 32)
        if tag and tag not in tags:
            tags.append(tag)
        if len(tags) == 3:
            break
    return tags


def _normalize_risk_flags(value: object) -> list[str]:
    flags: list[str] = []
    for raw_flag in _sequence(value):
        flag = _truncate(_string(raw_flag).strip().lower(), 64)
        flag = RISK_FLAG_ALIASES.get(flag, flag)
        if flag and flag not in flags:
            flags.append(flag)
    return flags


def _normalize_confidence(value: object) -> float:
    try:
        confidence = float(value)
    except (TypeError, ValueError):
        confidence = 0.0
    if confidence > 1:
        confidence /= 100
    return round(max(0.0, min(confidence, 1.0)), 3)


def _sequence(value: object) -> list[object]:
    if isinstance(value, str):
        return [value]
    if isinstance(value, Sequence):
        return list(value)
    return []


def _clamp_int(value: object) -> int:
    try:
        number = round(float(value))
    except (TypeError, ValueError):
        number = 0
    return max(0, min(int(number), 100))


def _string(value: object) -> str:
    if value is None:
        return ""
    return str(value)


def _truncate(value: str, limit: int) -> str:
    return value[:limit]


def _article_text(article: Mapping[str, object]) -> str:
    return " ".join(
        _string(article.get(key))
        for key in ("title", "summary", "content_text", "content_html", "url")
        if article.get(key)
    )


def _squash_whitespace(value: str) -> str:
    return " ".join(value.split())


def _detect_language(value: str) -> str:
    return "zh" if re.search(r"[\u4e00-\u9fff]", value) else "en"


def _looks_chinese(text: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", text))


def _mock_tags(value: str) -> list[str]:
    candidates = re.findall(r"[a-z][a-z0-9_-]{1,31}", value.lower())
    tags: list[str] = []
    for candidate in candidates:
        if candidate not in tags:
            tags.append(candidate)
        if len(tags) == 3:
            return tags
    return tags or ["general"]
