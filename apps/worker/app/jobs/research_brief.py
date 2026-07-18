"""Corpus research agent: mock brief with citations over TopN / project / topic (GOAL §4.D)."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

RESEARCH_BRIEF_JOB_TYPE = "research_brief"
VALID_SCOPES = frozenset({"topn", "project", "topic"})


class ResearchSink(Protocol):
    def list_topn_articles(self, *, limit: int) -> list[dict[str, object]]: ...

    def list_project_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]: ...

    def search_articles_by_topic(self, *, topic: str, limit: int) -> list[dict[str, object]]: ...


def run_research_brief(
    payload: Mapping[str, object],
    sink: ResearchSink,
    *,
    now: datetime | None = None,
) -> dict[str, object]:
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
    citations = [_citation_from_article(article, question) for article in articles]
    brief = {
        "generated_at": current.isoformat(),
        "scope": scope,
        "topic": topic or None,
        "question": question,
        "answer": _mock_answer(question, citations),
        "citations": citations,
        "article_count": len(citations),
        "provider": "mock",
    }
    return {
        "status": "ok",
        "scope": scope,
        "article_count": len(citations),
        "brief": brief,
    }


def _load_articles(
    sink: ResearchSink,
    *,
    scope: str,
    topic: str,
    user_id: str | None,
    limit: int,
) -> list[dict[str, object]]:
    if scope == "topn":
        return sink.list_topn_articles(limit=limit)
    if scope == "project":
        if not user_id:
            raise ValueError("user_id is required when scope=project")
        return sink.list_project_articles(user_id=user_id, limit=limit)
    if not topic:
        raise ValueError("topic is required when scope=topic")
    return sink.search_articles_by_topic(topic=topic, limit=limit)


def _citation_from_article(article: Mapping[str, object], question: str) -> dict[str, object]:
    article_id = int(article["article_id"]) if article.get("article_id") is not None else int(article["id"])
    title = str(article.get("title") or f"Article {article_id}")
    text = str(article.get("content_text") or article.get("summary_zh") or title).strip()
    quote = _excerpt(text, max_len=180)
    if not quote:
        quote = title
    return {
        "article_id": article_id,
        "title": title,
        "quote": quote,
        "relevance": "mock",
        "question_hint": question[:80],
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
        lines.append(f"{index}. [{citation['title']}] {citation['quote']}")
    lines.append("")
    lines.append("引用见 citations；生产路径可替换为真实 LLM。")
    return "\n".join(lines)


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
