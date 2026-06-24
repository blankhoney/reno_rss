from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass
from datetime import datetime
import importlib.util
from pathlib import Path
from types import ModuleType
from typing import Protocol, cast


DEFAULT_ALGORITHM_VERSION = "b4.v1"


@dataclass(frozen=True)
class RecommendationContext:
    user_id: object
    candidates: list[object]
    user_priority_by_feed: dict[int, int]
    feedback_by_article: dict[int, object]
    article_status_by_article: dict[int, str | None]
    now: datetime | None = None


class RecommendationSink(Protocol):
    def recommendation_context_for_user(self, user_id: object) -> RecommendationContext: ...

    def save_recommendation_edition(
        self,
        user_id: object,
        items: list[object],
        algorithm_version: str,
    ) -> None: ...


class TargetUserSink(RecommendationSink, Protocol):
    def list_target_users(self) -> list[object]: ...


RecommendationRanker = Callable[[RecommendationContext], Iterable[object]]


def generate_recommendations(
    payload: Mapping[str, object],
    sink: RecommendationSink,
    ranker: RecommendationRanker,
) -> dict[str, object]:
    algorithm_version = _algorithm_version(payload)

    user_ids = _user_ids(payload, sink)
    editions_saved = 0
    for user_id in user_ids:
        context = sink.recommendation_context_for_user(user_id)
        ranked_items = [_recommendation_item_dict(item) for item in ranker(context)]
        sink.save_recommendation_edition(user_id, ranked_items, algorithm_version)
        editions_saved += 1

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


def _algorithm_version(payload: Mapping[str, object]) -> str:
    value = payload.get("algorithm_version", DEFAULT_ALGORITHM_VERSION)
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
    return ranking_module.rank_b4(
        user_priority_by_feed=context.user_priority_by_feed,
        candidates=candidates,
        feedback_by_article=context.feedback_by_article,
        article_status_by_article=context.article_status_by_article,
        now=context.now,
    )


def _load_online_ranking_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[4]
    ranking_path = repo_root / "apps" / "api" / "app" / "domain" / "ranking.py"
    spec = importlib.util.spec_from_file_location("ai_reader_api_ranking", ranking_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load B4 ranking module from {ranking_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
