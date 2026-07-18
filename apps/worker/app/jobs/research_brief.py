"""Corpus research agent: brief with citations over TopN / project / topic (GOAL §4.D)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from datetime import UTC, datetime
import re
from typing import Protocol
from uuid import UUID

from app.runner import RetryableJobError

RESEARCH_BRIEF_JOB_TYPE = "research_brief"
VALID_SCOPES = frozenset({"topn", "project", "topic"})


class ResearchSink(Protocol):
    def list_topn_articles(
        self,
        *,
        user_id: str,
        limit: int,
    ) -> list[dict[str, object]]: ...

    def list_project_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]: ...

    def search_articles_by_topic(self, *, topic: str, limit: int) -> list[dict[str, object]]: ...


class ResearchProvider(Protocol):
    def research_answer(
        self,
        *,
        question: str,
        citations: Sequence[Mapping[str, object]],
        scope: str,
    ) -> str: ...


class AgentBudgetLedger(Protocol):
    def charge(
        self,
        account: str,
        units: int = 1,
        *,
        limit: int = 0,
    ) -> int: ...


@dataclass(frozen=True)
class PreparedResearch:
    generated_at: datetime
    scope: str
    topic: str
    question: str
    citations: list[dict[str, object]]


def run_budgeted_research_brief(
    payload: Mapping[str, object],
    sink: ResearchSink,
    *,
    provider: ResearchProvider,
    ledger: AgentBudgetLedger,
    daily_limit: int = 0,
    now: datetime | None = None,
) -> dict[str, object]:
    """Retrieve first, then reserve one agent unit immediately before a real call."""
    prepared = _prepare_research(payload, sink, now=now)
    if getattr(provider, "model_provider", "unknown") != "mock":
        if not prepared.citations:
            return _research_result(
                prepared,
                answer=_empty_answer(prepared.question),
                provider_name="none",
                status="empty",
            )
        try:
            ledger.charge("agent", 1, limit=daily_limit)
        except RuntimeError:
            return {
                "status": "skipped_cap",
                "account": "agent",
                "article_count": 0,
                "brief": None,
            }
    return _answer_prepared(prepared, provider)


def run_research_brief(
    payload: Mapping[str, object],
    sink: ResearchSink,
    *,
    now: datetime | None = None,
    provider: ResearchProvider | None = None,
) -> dict[str, object]:
    prepared = _prepare_research(payload, sink, now=now)
    return _answer_prepared(prepared, provider or MockResearchProvider())


def _prepare_research(
    payload: Mapping[str, object],
    sink: ResearchSink,
    *,
    now: datetime | None,
) -> PreparedResearch:
    current = now or datetime.now(UTC)
    if current.tzinfo is None:
        current = current.replace(tzinfo=UTC)
    else:
        current = current.astimezone(UTC)

    scope = str(payload.get("scope") or "topn").strip().lower()
    if scope not in VALID_SCOPES:
        raise ValueError(f"scope must be one of: {', '.join(sorted(VALID_SCOPES))}")

    question = str(payload.get("question") or "").strip()
    if not question:
        raise ValueError("question is required")

    max_articles = int(payload.get("max_articles") or 10)
    max_articles = max(1, min(max_articles, 30))

    topic = str(payload.get("topic") or "").strip()
    user_id = _optional_user_id(payload.get("user_id"))

    articles = _load_articles(sink, scope=scope, topic=topic, user_id=user_id, limit=max_articles)
    query = " ".join(part for part in (topic, question) if part)
    citations = [_citation_from_article(article, query) for article in articles]
    return PreparedResearch(
        generated_at=current,
        scope=scope,
        topic=topic,
        question=question,
        citations=citations,
    )


def _answer_prepared(
    prepared: PreparedResearch,
    provider: ResearchProvider,
) -> dict[str, object]:
    provider_name = getattr(provider, "model_provider", "unknown")
    try:
        answer = provider.research_answer(
            question=prepared.question,
            citations=prepared.citations,
            scope=prepared.scope,
        )
    except Exception as exc:
        raise RetryableJobError(f"research provider failed: {exc}") from exc
    if not answer.strip():
        raise RetryableJobError("research provider failed: empty answer")
    if prepared.citations and not _has_valid_citation_markers(answer, len(prepared.citations)):
        raise RetryableJobError("research provider failed: missing or invalid citation markers")
    return _research_result(
        prepared,
        answer=answer,
        provider_name=str(provider_name),
        status="ok",
    )


def _research_result(
    prepared: PreparedResearch,
    *,
    answer: str,
    provider_name: str,
    status: str,
) -> dict[str, object]:
    brief = {
        "generated_at": prepared.generated_at.isoformat(),
        "scope": prepared.scope,
        "topic": prepared.topic or None,
        "question": prepared.question,
        "answer": answer,
        "citations": prepared.citations,
        "article_count": len(prepared.citations),
        "provider": provider_name,
    }
    return {
        "status": status,
        "scope": prepared.scope,
        "article_count": len(prepared.citations),
        "brief": brief,
    }


class MockResearchProvider:
    model_provider = "mock"

    def research_answer(
        self,
        *,
        question: str,
        citations: Sequence[Mapping[str, object]],
        scope: str,
    ) -> str:
        del scope
        return _mock_answer(question, citations)


def _load_articles(
    sink: ResearchSink,
    *,
    scope: str,
    topic: str,
    user_id: str | None,
    limit: int,
) -> list[dict[str, object]]:
    if scope == "topn":
        if not user_id:
            raise ValueError("user_id is required when scope=topn")
        return sink.list_topn_articles(user_id=user_id, limit=limit)
    if scope == "project":
        if not user_id:
            raise ValueError("user_id is required when scope=project")
        return sink.list_project_articles(user_id=user_id, limit=limit)
    if not topic:
        raise ValueError("topic is required when scope=topic")
    return sink.search_articles_by_topic(topic=topic, limit=limit)


def _citation_from_article(article: Mapping[str, object], query: str) -> dict[str, object]:
    article_id = int(article["article_id"]) if article.get("article_id") is not None else int(article["id"])
    title = str(article.get("title") or f"Article {article_id}")
    text = str(article.get("content_text") or article.get("summary_zh") or title).strip()
    quote, start_hint, relevance_score = _relevant_excerpt(text, query, max_len=180)
    title_lower = title.casefold()
    relevance_score = max(
        relevance_score,
        float(sum(token in title_lower for token in _query_tokens(query))),
    )
    if not quote:
        quote = title
    return {
        "article_id": article_id,
        "title": title,
        "quote": quote,
        "start_hint": start_hint,
        "relevance_score": relevance_score,
        "question_hint": query[:80],
    }


def _mock_answer(question: str, citations: Sequence[Mapping[str, object]]) -> str:
    if not citations:
        return (
            f"（mock）未找到与「{question}」匹配的语料条目。"
            "请扩大 scope、提高 max_articles，或先同步/评分。"
        )
    lines = [
        f"（mock）基于 {len(citations)} 篇语料回答：「{question}」",
        "",
        "要点：",
    ]
    for index, citation in enumerate(citations[:5], start=1):
        lines.append(f"{index}. {citation['quote']} [{index}]")
    lines.append("")
    lines.append("引用见 citations；生产路径可替换为真实 LLM。")
    return "\n".join(lines)


def _empty_answer(question: str) -> str:
    return (
        f"未找到与「{question}」匹配的语料条目。"
        "请扩大范围、提高文章上限，或先同步与评分。"
    )


def _has_valid_citation_markers(answer: str, citation_count: int) -> bool:
    markers = [int(value) for value in re.findall(r"\[(\d+)\]", answer)]
    return bool(markers) and all(1 <= marker <= citation_count for marker in markers)


def _relevant_excerpt(text: str, query: str, *, max_len: int) -> tuple[str, int, float]:
    sentences = [
        sentence.strip()
        for sentence in re.split(r"(?<=[.!?。！？])\s+", text)
        if sentence.strip()
    ]
    if not sentences:
        return "", 0, 0.0
    tokens = _query_tokens(query)
    best_sentence = sentences[0]
    best_score = 0
    for sentence in sentences:
        lowered = sentence.casefold()
        score = sum(token in lowered for token in tokens)
        if score > best_score:
            best_sentence = sentence
            best_score = score
    start_hint = max(0, text.find(best_sentence))
    return _excerpt(best_sentence, max_len=max_len), start_hint, float(best_score)


def _query_tokens(query: str) -> list[str]:
    lowered = query.casefold()
    tokens = re.findall(r"[a-z0-9][a-z0-9_-]+", lowered)
    for chunk in re.findall(r"[\u4e00-\u9fff]+", lowered):
        tokens.append(chunk)
        if len(chunk) > 2:
            tokens.extend(chunk[index : index + 2] for index in range(len(chunk) - 1))
    return list(dict.fromkeys(token for token in tokens if len(token) >= 2))


def _excerpt(text: str, *, max_len: int) -> str:
    collapsed = " ".join(text.split())
    if len(collapsed) <= max_len:
        return collapsed
    return collapsed[: max_len - 1].rstrip() + "…"


def _optional_user_id(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, UUID):
        return str(value)
    text = str(value).strip()
    return text or None
