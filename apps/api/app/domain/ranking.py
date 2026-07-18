from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import UTC, datetime, timedelta
from typing import Any


_RULES_MODULE: Any | None = None
_RULES_LOAD_ATTEMPTED = False


def _load_rules_module() -> Any:
    """Load rules.py for rank_b4 rule application.

    Prefer a normal package import when ranking runs inside the API. When the
    worker loads this file via importlib (no ``app.domain`` on sys.path), fall
    back to loading sibling ``rules.py`` the same way so mute/boost still run.
    """
    global _RULES_MODULE, _RULES_LOAD_ATTEMPTED
    if _RULES_MODULE is not None:
        return _RULES_MODULE
    if _RULES_LOAD_ATTEMPTED and _RULES_MODULE is None:
        # Keep retrying importlib path even after a failed package import.
        pass
    try:
        from app.domain import rules as rules_module

        _RULES_MODULE = rules_module
        _RULES_LOAD_ATTEMPTED = True
        return rules_module
    except ImportError:
        pass

    import importlib.util
    import sys
    from pathlib import Path

    rules_path = Path(__file__).resolve().with_name("rules.py")
    if not rules_path.exists():
        _RULES_LOAD_ATTEMPTED = True
        return None
    module_name = "ai_reader_api_rules"
    spec = importlib.util.spec_from_file_location(module_name, rules_path)
    if spec is None or spec.loader is None:
        _RULES_LOAD_ATTEMPTED = True
        return None
    module = importlib.util.module_from_spec(spec)
    # dataclasses needs the module registered before exec_module.
    sys.modules[module_name] = module
    try:
        spec.loader.exec_module(module)
    except Exception:
        sys.modules.pop(module_name, None)
        _RULES_LOAD_ATTEMPTED = True
        return None
    _RULES_MODULE = module
    _RULES_LOAD_ATTEMPTED = True
    return module


FEEDBACK_BASE_ADJUSTMENTS = {
    "underrated": 8,
    "overrated": -10,
    "too_promotional": -12,
    "low_density": -12,
    "outdated": -12,
    "duplicate": -12,
    "wrong_category": -12,
    "other": 0,
}


@dataclass(frozen=True)
class Candidate:
    article_id: int
    feed_ids: list[int]
    base_score: int
    published_at: datetime
    risk_uncertainty: int = 100
    risk_flags: list[str] | None = None


@dataclass(frozen=True)
class Feedback:
    feedback_type: str
    user_score: int | None = None


@dataclass(frozen=True)
class RankedItem:
    article_id: int
    rank: int
    rank_score: float
    tier: str
    reason: str
    source: str


def rank_b4(
    *,
    user_priority_by_feed: dict[int, int],
    candidates: list[Candidate],
    feedback_by_article: dict[int, Feedback | dict[str, object]],
    article_status_by_article: dict[int, str | None] | None = None,
    now: datetime | None = None,
    rules: Sequence[Any] | None = None,
    titles_by_article: dict[int, str] | None = None,
    interest_weights: dict[str, float] | None = None,
) -> list[RankedItem]:
    reference_time = now or datetime.now(UTC)
    subscribed: list[tuple[Candidate, float]] = []
    exploration: list[Candidate] = []
    titles = titles_by_article or {}
    interests = interest_weights or {}

    eligible = _eligible_candidates(
        candidates,
        article_status_by_article or {},
        reference_time,
    )
    if rules:
        eligible = _apply_rules_to_candidates(
            eligible,
            rules,
            titles,
        )

    for candidate in eligible:
        subscribed_feed_ids = [
            feed_id for feed_id in candidate.feed_ids if feed_id in user_priority_by_feed
        ]
        if subscribed_feed_ids:
            priority = max(_clamp(user_priority_by_feed[feed_id], -20, 20) for feed_id in subscribed_feed_ids)
            score = (
                candidate.base_score
                + priority
                + _feedback_adjustment(candidate, feedback_by_article.get(candidate.article_id))
                + _freshness_adjustment(candidate.published_at, reference_time)
                + _interest_adjustment(titles.get(candidate.article_id, ""), interests)
            )
            subscribed.append((candidate, float(score)))
            continue

        if candidate.base_score >= 80 and candidate.risk_uncertainty <= 50:
            exploration.append(candidate)

    subscribed.sort(
        key=lambda item: (item[1], item[0].published_at, item[0].article_id),
        reverse=True,
    )
    exploration.sort(
        key=lambda candidate: (candidate.base_score, candidate.published_at, candidate.article_id),
        reverse=True,
    )

    selected: list[tuple[Candidate, float, str]] = [
        (candidate, score, "subscription") for candidate, score in subscribed[:8]
    ]
    selected.extend(
        (candidate, float(candidate.base_score), "exploration") for candidate in exploration[:2]
    )
    if len(selected) < 10:
        selected.extend(
            (candidate, score, "subscription") for candidate, score in subscribed[8 : 10 - len(selected) + 8]
        )

    return [
        RankedItem(
            article_id=candidate.article_id,
            rank=index,
            rank_score=round(score, 2),
            tier=_tier_for_score(candidate.base_score),
            reason="B4 deterministic ranking",
            source=source,
        )
        for index, (candidate, score, source) in enumerate(selected[:10], start=1)
    ]


def _apply_rules_to_candidates(
    candidates: list[Candidate],
    rules: Sequence[Any],
    titles_by_article: dict[int, str],
) -> list[Candidate]:
    """Optional reader-rule pass before B4 subscription/exploration split."""
    rules_module = _load_rules_module()
    if rules_module is None:
        return candidates
    rule_articles = rules_module.apply_rules(
        [
            rules_module.RuleArticle(
                article_id=candidate.article_id,
                feed_ids=list(candidate.feed_ids),
                title=titles_by_article.get(candidate.article_id, ""),
                score=float(candidate.base_score),
            )
            for candidate in candidates
        ],
        rules,
    )
    by_id = {candidate.article_id: candidate for candidate in candidates}
    adjusted: list[Candidate] = []
    for item in rule_articles:
        original = by_id.get(item.article_id)
        if original is None:
            continue
        # Keep base_score as int for tier math; clamp non-negative after boosts.
        next_score = max(0, int(round(item.score)))
        if next_score != original.base_score:
            adjusted.append(replace(original, base_score=next_score))
        else:
            adjusted.append(original)
    return adjusted


def _eligible_candidates(
    candidates: list[Candidate],
    article_status_by_article: dict[int, str | None],
    reference_time: datetime,
) -> list[Candidate]:
    filtered = [
        candidate
        for candidate in _dedupe_candidates(candidates)
        if article_status_by_article.get(candidate.article_id) not in {"read", "skipped"}
        and not _is_duplicate_hard_filtered(candidate)
    ]
    recent = _within_days(filtered, reference_time, 3)
    if len(recent) >= 10:
        return recent
    return _within_days(filtered, reference_time, 14)


def _dedupe_candidates(candidates: list[Candidate]) -> list[Candidate]:
    by_id: dict[int, Candidate] = {}
    feed_ids_by_id: dict[int, set[int]] = {}
    risk_flags_by_id: dict[int, set[str]] = {}
    for candidate in candidates:
        existing = by_id.get(candidate.article_id)
        feed_ids_by_id.setdefault(candidate.article_id, set()).update(candidate.feed_ids)
        risk_flags_by_id.setdefault(candidate.article_id, set()).update(candidate.risk_flags or [])
        if existing is None or candidate.published_at > existing.published_at:
            by_id[candidate.article_id] = candidate
        by_id[candidate.article_id] = replace(
            by_id[candidate.article_id],
            feed_ids=sorted(feed_ids_by_id[candidate.article_id]),
            risk_flags=sorted(risk_flags_by_id[candidate.article_id]) or None,
        )
    return list(by_id.values())


def _is_duplicate_hard_filtered(candidate: Candidate) -> bool:
    return "duplicate" in (candidate.risk_flags or []) and candidate.base_score < 70


def _within_days(
    candidates: list[Candidate],
    reference_time: datetime,
    days: int,
) -> list[Candidate]:
    earliest = reference_time - timedelta(days=days)
    return [
        candidate
        for candidate in candidates
        if earliest <= candidate.published_at <= reference_time
    ]


def _feedback_adjustment(candidate: Candidate, feedback: Feedback | dict[str, object] | None) -> float:
    if feedback is None:
        return 0
    if isinstance(feedback, Feedback):
        feedback_type = feedback.feedback_type
        user_score = feedback.user_score
    else:
        feedback_type = str(feedback.get("feedback_type", "other"))
        raw_user_score = feedback.get("user_score")
        user_score = int(raw_user_score) if raw_user_score is not None else None
    adjustment = FEEDBACK_BASE_ADJUSTMENTS.get(feedback_type, 0)
    if user_score is not None:
        adjustment += (user_score - candidate.base_score) * 0.2
    return _clamp(adjustment, -20, 12)


def _freshness_adjustment(published_at: datetime, now: datetime) -> int:
    age = now - published_at
    if age <= timedelta(hours=24):
        return 3
    if age <= timedelta(hours=72):
        return 1
    if age > timedelta(days=7):
        return -4
    return 0


def _interest_adjustment(title: str, interest_weights: dict[str, float]) -> float:
    """Soft boost when title tokens overlap long-term interest keywords."""
    if not interest_weights or not title:
        return 0.0
    haystack = title.casefold()
    total = 0.0
    for term, weight in interest_weights.items():
        token = str(term or "").casefold().strip()
        if len(token) < 2:
            continue
        if token in haystack:
            try:
                total += min(float(weight), 5.0)
            except (TypeError, ValueError):
                continue
    # Cap so interest cannot dominate base score / feedback.
    return _clamp(total, 0.0, 8.0)


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def _tier_for_score(score: int) -> str:
    if score >= 85:
        return "must_read"
    if score >= 70:
        return "read"
    if score >= 50:
        return "skim"
    return "skip"
