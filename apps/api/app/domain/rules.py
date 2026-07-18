"""User reader rules: boost / mute / keyword radar / score threshold (GOAL §4.A)."""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass, replace


RULE_TYPES = frozenset({"boost", "mute", "keyword", "score_threshold"})
DEFAULT_BOOST_WEIGHT = 10.0


@dataclass(frozen=True)
class Rule:
    type: str
    feed_id: int | None = None
    keyword: str | None = None
    weight: float | None = None

    def normalized(self) -> Rule:
        rule_type = (self.type or "").strip().lower()
        keyword = self.keyword.strip() if isinstance(self.keyword, str) else self.keyword
        if keyword == "":
            keyword = None
        return Rule(
            type=rule_type,
            feed_id=self.feed_id,
            keyword=keyword,
            weight=self.weight,
        )


@dataclass(frozen=True)
class RuleArticle:
    """Ranking candidate fields needed to apply reader rules."""

    article_id: int
    feed_ids: list[int]
    title: str
    score: float


def validate_rule(rule: Rule | dict[str, object]) -> Rule:
    """Validate and normalize a rule; raises ValueError on bad input."""
    if isinstance(rule, Rule):
        candidate = rule.normalized()
    else:
        raw_type = rule.get("type")
        raw_feed = rule.get("feed_id")
        raw_keyword = rule.get("keyword")
        raw_weight = rule.get("weight")
        candidate = Rule(
            type=str(raw_type) if raw_type is not None else "",
            feed_id=int(raw_feed) if raw_feed is not None else None,
            keyword=str(raw_keyword) if raw_keyword is not None else None,
            weight=float(raw_weight) if raw_weight is not None else None,
        ).normalized()

    if candidate.type not in RULE_TYPES:
        raise ValueError(f"unsupported rule type: {candidate.type!r}")

    if candidate.type == "mute":
        if candidate.feed_id is None and not candidate.keyword:
            raise ValueError("mute rule requires feed_id or keyword")
    elif candidate.type == "boost":
        if candidate.feed_id is None and not candidate.keyword:
            raise ValueError("boost rule requires feed_id or keyword")
    elif candidate.type == "keyword":
        if not candidate.keyword:
            raise ValueError("keyword rule requires keyword")
    elif candidate.type == "score_threshold":
        if candidate.weight is None:
            raise ValueError("score_threshold rule requires weight")

    return candidate


def rules_from_payload(raw_rules: Sequence[object]) -> list[Rule]:
    return [validate_rule(item if isinstance(item, (Rule, dict)) else {}) for item in raw_rules]


def rule_to_public(rule: Rule) -> dict[str, object]:
    payload: dict[str, object] = {"type": rule.type}
    if rule.feed_id is not None:
        payload["feed_id"] = rule.feed_id
    if rule.keyword is not None:
        payload["keyword"] = rule.keyword
    if rule.weight is not None:
        payload["weight"] = rule.weight
    return payload


def apply_rules(
    candidates: Sequence[RuleArticle],
    rules: Sequence[Rule],
) -> list[RuleArticle]:
    """Filter and re-score candidates according to reader rules.

    Order of application:
    1. mute (drop matching feed or title keyword)
    2. score_threshold (drop below max configured threshold weight)
    3. boost / keyword (add weight when feed or keyword matches)
    """
    if not candidates:
        return []

    normalized = [validate_rule(rule) for rule in rules]
    muted = [
        article
        for article in candidates
        if not _is_muted(article, normalized)
    ]

    thresholds = [
        rule.weight
        for rule in normalized
        if rule.type == "score_threshold" and rule.weight is not None
    ]
    if thresholds:
        minimum = max(thresholds)
        muted = [article for article in muted if article.score >= minimum]

    adjusted: list[RuleArticle] = []
    for article in muted:
        bonus = 0.0
        for rule in normalized:
            if rule.type not in {"boost", "keyword"}:
                continue
            if not _matches_target(article, rule):
                continue
            weight = rule.weight if rule.weight is not None else DEFAULT_BOOST_WEIGHT
            bonus += float(weight)
        if bonus:
            adjusted.append(replace(article, score=article.score + bonus))
        else:
            adjusted.append(article)
    return adjusted


def _is_muted(article: RuleArticle, rules: Sequence[Rule]) -> bool:
    for rule in rules:
        if rule.type != "mute":
            continue
        if rule.feed_id is not None and rule.feed_id in article.feed_ids:
            return True
        if rule.keyword and _title_has_keyword(article.title, rule.keyword):
            return True
    return False


def _matches_target(article: RuleArticle, rule: Rule) -> bool:
    feed_ok = rule.feed_id is None or rule.feed_id in article.feed_ids
    if rule.keyword:
        return feed_ok and _title_has_keyword(article.title, rule.keyword)
    return feed_ok and rule.feed_id is not None


def _title_has_keyword(title: str, keyword: str) -> bool:
    return keyword.casefold() in (title or "").casefold()
