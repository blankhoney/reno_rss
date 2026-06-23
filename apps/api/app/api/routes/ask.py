from __future__ import annotations

from collections.abc import Iterable
from typing import Protocol

from fastapi import APIRouter, Depends, Path
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, ConfigDict, Field

from app.api.deps import (
    ApiError,
    get_article_repository,
    get_ask_provider,
    get_scoring_repository,
    require_user,
)
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleRecord, ArticleStore
from app.db.repositories.scoring import ScoreRecord, ScoringStore
from app.domain.ask_prompt import build_article_ask_context, stream_without_think_blocks


router = APIRouter(prefix="/api/articles", tags=["ask"])


class AskRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    question: str = Field(min_length=1, max_length=1000)
    selected_text: str | None = Field(default=None, max_length=5000)


class AskProvider(Protocol):
    def answer_article_question(self, messages: list[dict[str, str]]) -> Iterable[str]: ...


class DeterministicAskProvider:
    def answer_article_question(self, messages: list[dict[str, str]]) -> Iterable[str]:
        return [
            "结论：当前问答模型未配置。\n"
            "依据：服务端已组装文章上下文，但没有可用的实时 LLM provider。\n"
            "引用：请以文章正文为准。\n"
            "不确定点：模型回答能力尚未接入。\n"
            "行动建议：配置 provider 后重试。"
        ]


@router.post("/{article_id}/ask")
def ask_article(
    payload: AskRequest,
    article_id: int = Path(gt=0),
    _current_user: UserRecord = Depends(require_user),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    ask_provider: AskProvider = Depends(get_ask_provider),
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
    scores = scoring_repository.list_scores(article_id=article.id)
    for score in reversed(scores):
        if score.is_active and score.scoring_status == "success":
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
