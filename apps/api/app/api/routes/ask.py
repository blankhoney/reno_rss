from __future__ import annotations

from collections.abc import Callable, Iterable
import json
from typing import Protocol

import httpx
from fastapi import APIRouter, Depends, Path, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    ApiError,
    get_article_repository,
    get_ask_provider,
    get_scoring_repository,
    require_user,
)
from app.core.config import Settings
from app.core.ratelimit import limiter, llm_rate_limit
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleRecord, ArticleStore
from app.db.repositories.scoring import ScoreRecord, ScoringStore
from app.domain.ask_prompt import build_article_ask_context, stream_without_think_blocks


router = APIRouter(prefix="/api/articles", tags=["ask"])
_STREAM_DONE = object()


class AskRequest(BaseModel):
    # extra=forbid: multi-turn history payloads are rejected until a capped contract ships.
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    selected_text: str | None = Field(default=None, max_length=5000)


class AskProvider(Protocol):
    def answer_article_question(self, messages: list[dict[str, str]]) -> Iterable[str]: ...


class DeterministicAskProvider:
    spends_llm_budget = False

    def __init__(self, *, reason: str = "unconfigured") -> None:
        self.reason = reason

    def answer_article_question(self, messages: list[dict[str, str]]) -> Iterable[str]:
        if self.reason == "budget_exhausted":
            return [
                "结论：今日 LLM 调用额度已用满，已切换为占位回答。\n"
                "依据：服务端没有继续调用真实模型，因此不会产生额外费用。\n"
                "引用：请以文章正文和已有评分摘要为准。\n"
                "不确定点：占位回答未重新分析文章。\n"
                "行动建议：明天额度重置后重试，或请管理员调整预算。"
            ]
        return [
            "结论：当前问答模型未配置。\n"
            "依据：服务端已组装文章上下文，但没有可用的实时 LLM provider。\n"
            "引用：请以文章正文为准。\n"
            "不确定点：模型回答能力尚未接入。\n"
            "行动建议：配置 provider 后重试。"
        ]


class MiniMaxAskProvider:
    spends_llm_budget = True

    def __init__(
        self,
        *,
        api_key: str,
        base_url: str,
        model: str,
        temperature: float,
        top_p: float,
        max_completion_tokens: int | None,
        reasoning_split: bool,
        thinking_type: str | None,
        timeout_seconds: float,
        stream_factory: Callable[..., object] | None = None,
    ) -> None:
        self.api_key = api_key
        self.base_url = base_url.rstrip("/")
        self.model = model
        self.temperature = temperature
        self.top_p = top_p
        self.max_completion_tokens = max_completion_tokens
        self.reasoning_split = reasoning_split
        self.thinking_type = thinking_type
        self.timeout_seconds = timeout_seconds
        self._stream_factory = stream_factory or httpx.stream

    def answer_article_question(self, messages: list[dict[str, str]]) -> Iterable[str]:
        if not self.api_key or self.api_key == "change_me":
            raise RuntimeError("missing MINIMAX_API_KEY")
        request_json = self._request_json(messages)
        with self._stream_factory(
            "POST",
            f"{self.base_url}/chat/completions",
            headers={"Authorization": f"Bearer {self.api_key}"},
            json=request_json,
            timeout=self.timeout_seconds,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
                content = _stream_content_from_line(line)
                if content is _STREAM_DONE:
                    break
                if isinstance(content, str) and content:
                    yield content

    def _request_json(self, messages: list[dict[str, str]]) -> dict[str, object]:
        # Keep in parity with worker MinimaxLLMClient._request_json, with the
        # API-only addition of stream=True for SSE answers.
        payload: dict[str, object] = {
            "model": self.model,
            "messages": messages,
            "temperature": self.temperature,
            "top_p": self.top_p,
            "stream": True,
        }
        if self.max_completion_tokens is not None:
            payload["max_completion_tokens"] = self.max_completion_tokens
        if self.reasoning_split:
            payload["reasoning_split"] = True
        if self.thinking_type:
            payload["thinking"] = {"type": self.thinking_type}
        return payload


def create_ask_provider(settings: Settings) -> AskProvider:
    selected = settings.llm_provider.strip().lower()
    if selected in {"", "mock"}:
        return DeterministicAskProvider()
    if selected == "minimax":
        if not settings.minimax_api_key or settings.minimax_api_key == "change_me":
            return DeterministicAskProvider()
        return MiniMaxAskProvider(
            api_key=settings.minimax_api_key,
            base_url=settings.minimax_base_url,
            model=settings.minimax_model,
            temperature=settings.minimax_temperature,
            top_p=settings.minimax_top_p,
            max_completion_tokens=settings.minimax_max_completion_tokens,
            reasoning_split=settings.minimax_reasoning_split,
            thinking_type=settings.minimax_thinking_type,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    if selected in {"local", "openai_compatible"}:
        import os

        return MiniMaxAskProvider(
            api_key=os.environ.get("LOCAL_LLM_API_KEY", "local"),
            base_url=os.environ.get("LOCAL_LLM_BASE_URL", "http://127.0.0.1:11434/v1").rstrip("/"),
            model=os.environ.get("LOCAL_LLM_MODEL", "llama3.2"),
            temperature=settings.minimax_temperature,
            top_p=settings.minimax_top_p,
            max_completion_tokens=settings.minimax_max_completion_tokens,
            reasoning_split=False,
            thinking_type=None,
            timeout_seconds=settings.llm_timeout_seconds,
        )
    raise ValueError("LLM_PROVIDER must be 'mock', 'minimax', or 'local'")


@router.post("/{article_id}/ask")
@limiter.limit(llm_rate_limit)
def ask_article(
    payload: AskRequest,
    request: Request,
    article_id: int = Path(gt=0),
    _current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
) -> StreamingResponse:
    article = article_repository.get_article(article_id)
    if article is None:
        raise ApiError(404, "not_found", "Article not found")

    score = _active_score(scoring_repository, article)
    context = build_article_ask_context(
        question=payload.question,
        title=article.title,
        url=article.url,
        content_text=article.content_text,
        content_html=article.content_html,
        summary_zh=_score_text(score, "summary_zh"),
        scoring_reason=_score_text(score, "reason"),
        tags=_score_values(score, "tags"),
        risk_flags=_score_values(score, "risk_flags"),
        selected_text=payload.selected_text,
    )
    if not context.has_usable_context:
        raise ApiError(409, "content_required", "Article content is required before asking")

    ask_provider = get_ask_provider(request)
    messages = [
        {"role": "system", "content": context.messages.system},
        {"role": "user", "content": context.messages.user},
    ]
    return StreamingResponse(
        _sse_answer(ask_provider.answer_article_question(messages)),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache, no-transform",
            "X-Agent-Search-Status": "disabled",
        },
    )


def _active_score(
    scoring_repository: ScoringStore,
    article: ArticleRecord,
) -> ScoreRecord | None:
    score = scoring_repository.active_scores_for_articles([article.id]).get(article.id)
    if score is not None and score.scoring_status == "success":
        return score
    return None


def _score_text(score: ScoreRecord | None, attr: str) -> str | None:
    if score is None:
        return None
    value = getattr(score, attr)
    return str(value) if value else None


def _score_values(score: ScoreRecord | None, attr: str) -> list[object]:
    if score is None:
        return []
    value = getattr(score, attr)
    return list(value) if isinstance(value, list) else []


def _sse_answer(chunks: Iterable[str]) -> Iterable[str]:
    for cleaned in stream_without_think_blocks(chunks):
        if cleaned:
            yield _sse_data(cleaned)
    yield "event: done\ndata: {}\n\n"


def _sse_data(text: str) -> str:
    lines = text.splitlines() or [text]
    return "".join(f"data: {line}\n" for line in lines) + "\n"


def _stream_content_from_line(line: object) -> str | object | None:
    text = _normalize_stream_line(line)
    if not text or text.startswith(":") or not text.startswith("data:"):
        return None
    data = text.removeprefix("data:").strip()
    if data == "[DONE]":
        return _STREAM_DONE
    try:
        payload = json.loads(data)
    except json.JSONDecodeError as exc:
        raise RuntimeError("llm stream returned invalid JSON") from exc

    try:
        choice = payload["choices"][0]
    except (KeyError, IndexError, TypeError) as exc:
        raise RuntimeError("llm stream missing choices[0]") from exc
    message = choice.get("delta") or choice.get("message") or {}
    content = message.get("content", "")
    return content if isinstance(content, str) else ""


def _normalize_stream_line(line: object) -> str:
    if isinstance(line, bytes):
        return line.decode("utf-8", errors="replace").strip()
    return str(line).strip()
