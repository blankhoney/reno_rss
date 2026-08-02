from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast

from app.jobs.payload_contracts import (
    DEFAULT_ALGORITHM_VERSION,
    PayloadGeneration,
    validate_payload_version,
)
_ONLINE_RANKING_MODULE: ModuleType | None = None


@dataclass(frozen=True)
class RecommendationContext:
    user_id: object
    candidates: list[object]
    user_priority_by_feed: dict[int, int]
    feedback_by_article: dict[int, object]
    article_status_by_article: dict[int, str | None]
    now: datetime | None = None
    # User reader rules (boost/mute/keyword/threshold) applied inside rank_b4.
    rules: list[object] | None = None
    titles_by_article: dict[int, str] | None = None
    # Long-term interest keyword weights (term -> weight) for soft ranking boost.
    interest_weights: dict[str, float] | None = None


class RecommendationSink(Protocol):
    def recommendation_context_for_user(self, user_id: object) -> RecommendationContext: ...

    def save_recommendation_edition(
        self,
        user_id: object,
        items: list[object],
        algorithm_version: str,
    ) -> None: ...

    def enqueue_daily_brief(self) -> None: ...


class TargetUserSink(RecommendationSink, Protocol):
    def list_target_users(self) -> list[object]: ...


RecommendationRanker = Callable[[RecommendationContext], Iterable[object]]


def generate_recommendations(
    payload: Mapping[str, object],
    sink: RecommendationSink,
    ranker: RecommendationRanker,
) -> dict[str, object]:
    payload_generation = validate_payload_version(
        payload,
        job_type="generate_recommendations",
    )
    algorithm_version = _algorithm_version(payload, payload_generation=payload_generation)

    user_ids = _user_ids(payload, sink)
    editions_saved = 0
    for user_id in user_ids:
        context = sink.recommendation_context_for_user(user_id)
        ranked_items = [_recommendation_item_dict(item) for item in ranker(context)]
        sink.save_recommendation_edition(user_id, ranked_items, algorithm_version)
        editions_saved += 1

    # The brief must observe the editions created by this job, so it is
    # enqueued only after every target user has been persisted successfully.
    sink.enqueue_daily_brief()

    return {
        "algorithm_version": algorithm_version,
        "editions_saved": editions_saved,
        "users_seen": len(user_ids),
    }


def _user_ids(payload: Mapping[str, object], sink: RecommendationSink) -> list[object]:
    if "user_ids" not in payload:
        return list(cast(TargetUserSink, sink).list_target_users())

    value = payload["user_ids"]
    if isinstance(value, str):
        raise TypeError("payload['user_ids'] must be an iterable of user ids, not a string")
    if not isinstance(value, Iterable):
        raise TypeError("payload['user_ids'] must be an iterable of user ids")
    return list(value)


def _algorithm_version(
    payload: Mapping[str, object],
    *,
    payload_generation: PayloadGeneration,
) -> str:
    if payload_generation == "legacy":
        value = payload.get("algorithm_version", DEFAULT_ALGORITHM_VERSION)
    else:
        if "algorithm_version" not in payload:
            raise ValueError("versioned payload['algorithm_version'] is required")
        value = payload["algorithm_version"]
    if not isinstance(value, str):
        raise TypeError("payload['algorithm_version'] must be a string")
    if value != DEFAULT_ALGORITHM_VERSION:
        raise ValueError("payload['algorithm_version'] must be b4.v1")
    return DEFAULT_ALGORITHM_VERSION


def _recommendation_item_dict(item: object) -> dict[str, object]:
    return {
        "article_id": _item_value(item, "article_id"),
        "rank": _item_value(item, "rank"),
        "rank_score": _item_value(item, "rank_score"),
        "tier": _item_value(item, "tier"),
        "reason": _item_value(item, "reason"),
        "source": _item_value(item, "source"),
    }


def _item_value(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return item[key]
    return getattr(item, key)


def rank_b4_recommendation_context(context: RecommendationContext) -> Iterable[object]:
    """Apply B4 ranking with user rules + interest weights (GOAL §4.A).

    PUT /api/rules is NOT dead: DatabaseRecommendationSink loads rules into
    RecommendationContext.rules, and this function always forwards them.
    """
    ranking_module = _load_online_ranking_module()
    candidates = [
        ranking_module.Candidate(
            article_id=int(candidate["article_id"]),
            feed_ids=[int(feed_id) for feed_id in candidate["feed_ids"]],
            base_score=int(candidate["base_score"]),
            published_at=candidate["published_at"],
            risk_uncertainty=int(candidate.get("risk_uncertainty", 100)),
            risk_flags=list(candidate.get("risk_flags", [])),
        )
        for candidate in context.candidates
        if isinstance(candidate, Mapping)
    ]
    # Critical unattended path: rules / titles / interest must all be passed.
    user_rules = list(context.rules or [])
    titles = dict(context.titles_by_article or {})
    interests = dict(context.interest_weights or {})
    return ranking_module.rank_b4(
        user_priority_by_feed=context.user_priority_by_feed,
        candidates=candidates,
        feedback_by_article=context.feedback_by_article,
        article_status_by_article=context.article_status_by_article,
        now=context.now,
        rules=user_rules,
        titles_by_article=titles,
        interest_weights=interests,
    )


def _load_online_ranking_module() -> ModuleType:
    global _ONLINE_RANKING_MODULE
    if _ONLINE_RANKING_MODULE is not None:
        return _ONLINE_RANKING_MODULE
    ranking_path = _ranking_module_path(Path(__file__).resolve())
    spec = importlib.util.spec_from_file_location("ai_reader_api_ranking", ranking_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load B4 ranking module from {ranking_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    _ONLINE_RANKING_MODULE = module
    return module


def _ranking_module_path(start: Path) -> Path:
    relative_path = Path("apps/api/app/domain/ranking.py")
    for parent in start.parents:
        candidate = parent / relative_path
        if candidate.exists():
            return candidate
    raise ImportError(f"Cannot find B4 ranking module relative to {start}")
