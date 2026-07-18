"""Daily intelligence brief read API (GOAL §3.1)."""

from __future__ import annotations

from uuid import UUID

from fastapi import APIRouter, Depends

from app.api.deps import (
    get_article_repository,
    get_job_repository,
    get_recommendation_repository,
    get_scoring_repository,
    require_user,
)
from app.db.auth_store import UserRecord
from app.db.repositories.articles import ArticleRecord, ArticleStore
from app.db.repositories.jobs import JobRecord, JobStore
from app.db.repositories.recommendations import RecommendationStore
from app.db.repositories.scoring import ScoreRecord, ScoringStore

router = APIRouter(prefix="/api/briefs", tags=["briefs"])

BRIEF_TIER_KEYS = ("must_read", "worth_scan", "can_skip")


def extract_brief_payload(result: object) -> dict[str, object] | None:
    """Accept sink-shaped brief rows or worker results that nest under `brief`."""
    if not isinstance(result, dict):
        return None
    nested = result.get("brief")
    if isinstance(nested, dict) and _looks_like_brief(nested):
        return nested
    if _looks_like_brief(result):
        return result
    return None


def _looks_like_brief(payload: dict[str, object]) -> bool:
    if "must_read" not in payload:
        return False
    return "title" in payload or "generated_at" in payload


def brief_item_public(
    raw: object,
    articles_by_id: dict[int, ArticleRecord],
    scores_by_id: dict[int, ScoreRecord],
) -> dict[str, object] | None:
    if not isinstance(raw, dict):
        return None
    article_id_raw = raw.get("article_id")
    try:
        article_id = int(article_id_raw) if article_id_raw is not None else None
    except (TypeError, ValueError):
        article_id = None
    if article_id is None:
        return None

    article = articles_by_id.get(article_id)
    score = scores_by_id.get(article_id)

    title = raw.get("title")
    if not isinstance(title, str) or not title.strip():
        title = article.title if article is not None else f"Article #{article_id}"

    rank_score = _optional_float(raw.get("rank_score"))
    overall_score = score.base_score if score is not None else rank_score
    summary_zh = score.summary_zh if score is not None and score.summary_zh else None
    if summary_zh is None:
        summary_raw = raw.get("summary_zh")
        summary_zh = str(summary_raw) if isinstance(summary_raw, str) and summary_raw.strip() else None

    rank = _optional_int(raw.get("rank"))
    tier = str(raw.get("tier") or "")
    reason = raw.get("reason")
    if not isinstance(reason, str):
        reason = str(reason) if reason is not None else ""
    risk_flags = list(score.risk_flags) if score is not None else []
    if not risk_flags:
        raw_flags = raw.get("risk_flags")
        if isinstance(raw_flags, list):
            risk_flags = [str(flag) for flag in raw_flags]

    source_quality = None
    if score is not None and isinstance(score.dimension_scores, dict):
        raw_sq = score.dimension_scores.get("source_quality")
        try:
            source_quality = float(raw_sq) if raw_sq is not None else None
        except (TypeError, ValueError):
            source_quality = None
    if source_quality is None:
        source_quality = _optional_float(raw.get("source_quality"))

    return {
        "article_id": article_id,
        "title": title,
        "rank": rank,
        "tier": tier,
        "rank_score": rank_score,
        "reason": reason,
        "summary_zh": summary_zh,
        "overall_score": overall_score,
        "risk_flags": risk_flags,
        "source_quality": source_quality,
        "content_quality": (
            article.content_quality if article is not None else raw.get("content_quality")
        ),
    }


def latest_brief_from_jobs(jobs: list[JobRecord]) -> dict[str, object] | None:
    for job in jobs:
        brief = extract_brief_payload(job.result)
        if brief is not None:
            return brief
    return None


@router.get("/latest")
def latest_brief(
    current_user: UserRecord = Depends(require_user),
    job_repository: JobStore = Depends(get_job_repository),
    article_repository: ArticleStore = Depends(get_article_repository),
    scoring_repository: ScoringStore = Depends(get_scoring_repository),
    recommendation_repository: RecommendationStore = Depends(get_recommendation_repository),
) -> dict[str, object]:
    jobs = job_repository.latest_succeeded("generate_daily_brief", limit=10)
    raw_brief = latest_brief_from_jobs(jobs)
    if raw_brief is None:
        raw_brief = brief_from_recommendations(
            current_user.id,
            recommendation_repository,
            article_repository,
            scoring_repository,
        )
    if raw_brief is None:
        return {"brief": None}

    article_ids = _collect_article_ids(raw_brief)
    articles_by_id = article_repository.get_articles(article_ids) if article_ids else {}
    scores_by_id = (
        scoring_repository.active_scores_for_articles(article_ids) if article_ids else {}
    )

    return {
        "brief": {
            "generated_at": raw_brief.get("generated_at"),
            "title": raw_brief.get("title") or "今日情报",
            "source": raw_brief.get("source") or "jobs",
            "must_read": _map_tier(raw_brief.get("must_read"), articles_by_id, scores_by_id),
            "worth_scan": _map_tier(raw_brief.get("worth_scan"), articles_by_id, scores_by_id),
            "can_skip": _map_tier(raw_brief.get("can_skip"), articles_by_id, scores_by_id),
        }
    }


def brief_from_recommendations(
    user_id: UUID,
    recommendation_repository: RecommendationStore,
    article_repository: ArticleStore,
    scoring_repository: ScoringStore,
) -> dict[str, object] | None:
    edition = recommendation_repository.latest_for_user(user_id)
    if edition is None or not edition.items:
        return None
    article_ids = [item.article_id for item in edition.items]
    articles = article_repository.get_articles(article_ids)
    scores = scoring_repository.active_scores_for_articles(article_ids)
    rows: list[dict[str, object]] = []
    for item in edition.items:
        article = articles.get(item.article_id)
        score = scores.get(item.article_id)
        rows.append(
            {
                "article_id": item.article_id,
                "rank": item.rank,
                "tier": item.tier,
                "rank_score": item.rank_score,
                "reason": item.reason or "",
                "title": article.title if article else "",
                "summary_zh": score.summary_zh if score else "",
                "overall_score": score.base_score if score else None,
            }
        )
    return {
        "generated_at": edition.generated_at.isoformat(),
        "title": f"今日情报 {edition.generated_at.date().isoformat()}",
        "source": "recommendations_fallback",
        # Disjoint tiers: must_read-only / read-only / skim|skip (no overlap).
        "must_read": [row for row in rows if row["tier"] == "must_read"],
        "worth_scan": [row for row in rows if row["tier"] == "read"],
        "can_skip": [row for row in rows if row["tier"] in {"skim", "skip"}],
    }


def _map_tier(
    raw_items: object,
    articles_by_id: dict[int, ArticleRecord],
    scores_by_id: dict[int, ScoreRecord],
) -> list[dict[str, object]]:
    if not isinstance(raw_items, list):
        return []
    items: list[dict[str, object]] = []
    for raw in raw_items:
        item = brief_item_public(raw, articles_by_id, scores_by_id)
        if item is not None:
            items.append(item)
    return items


def _collect_article_ids(brief: dict[str, object]) -> list[int]:
    ids: list[int] = []
    seen: set[int] = set()
    for key in BRIEF_TIER_KEYS:
        raw_items = brief.get(key)
        if not isinstance(raw_items, list):
            continue
        for raw in raw_items:
            if not isinstance(raw, dict):
                continue
            try:
                article_id = int(raw["article_id"])
            except (KeyError, TypeError, ValueError):
                continue
            if article_id not in seen:
                seen.add(article_id)
                ids.append(article_id)
    return ids


def _optional_float(value: object) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    if number != number:  # NaN
        return None
    return number


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
