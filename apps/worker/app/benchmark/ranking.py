from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
import importlib.util
import math
from pathlib import Path
from types import ModuleType


LABEL_RELEVANCE = {
    "must_read": 3,
    "read": 2,
    "skim": 1,
    "skip": 0,
}
VALID_LABELS = {"must_read", "read"}
HEURISTIC_KEYWORDS = {
    "agent",
    "agents",
    "ai",
    "benchmark",
    "code",
    "eval",
    "infrastructure",
    "rag",
}


@dataclass(frozen=True)
class BenchmarkUser:
    user_id: object
    priority_by_feed: dict[int, int]
    feedback_by_article: dict[int, object] = field(default_factory=dict)
    article_status_by_article: dict[int, str | None] = field(default_factory=dict)


@dataclass(frozen=True)
class BenchmarkArticle:
    article_id: int
    feed_ids: list[int]
    title: str
    tags: list[str]
    base_score: int
    published_at: datetime
    risk_uncertainty: int = 100
    risk_flags: list[str] = field(default_factory=list)
    weak_label: str = "skip"


@dataclass(frozen=True)
class BenchmarkDataset:
    users: list[BenchmarkUser]
    articles: list[BenchmarkArticle]
    generated_at: datetime = field(default_factory=lambda: datetime.now(UTC))


@dataclass(frozen=True)
class BaselineMetrics:
    precision_at_10: float
    ndcg_at_10: float
    average_effective_at_10: float
    top10_by_user: dict[str, list[int]]

    def as_dict(self) -> dict[str, object]:
        return {
            "precision_at_10": self.precision_at_10,
            "ndcg_at_10": self.ndcg_at_10,
            "average_effective_at_10": self.average_effective_at_10,
            "top10_by_user": self.top10_by_user,
        }


@dataclass(frozen=True)
class RankingBenchmarkReport:
    provider: str
    mode: str
    baselines: dict[str, BaselineMetrics]
    real_llm_calls: int
    generated_at: datetime
    status: str
    failure_reason: str | None = None

    def metrics_json(self) -> dict[str, object]:
        return {
            "provider": self.provider,
            "mode": self.mode,
            "real_llm_calls": self.real_llm_calls,
            "status": self.status,
            "failure_reason": self.failure_reason,
            "baselines": {
                name: metrics.as_dict()
                for name, metrics in self.baselines.items()
            },
        }

    def artifact_json(self) -> dict[str, object]:
        payload = self.metrics_json()
        payload["suite"] = "ranking"
        payload["generated_at"] = self.generated_at.isoformat()
        return payload


def run_ranking_benchmark(
    dataset: BenchmarkDataset,
    *,
    provider_name: str,
    mode: str = "ci_mini",
) -> RankingBenchmarkReport:
    baselines = {
        "B0": _evaluate(dataset, _rank_b0),
        "B1": _evaluate(dataset, _rank_b1),
        "B2": _evaluate(dataset, _rank_b2),
        "B3": _evaluate(dataset, _rank_b3),
        "B4": _evaluate(dataset, _rank_b4),
    }
    failure_reason = _failure_reason(baselines)
    return RankingBenchmarkReport(
        provider=provider_name,
        mode=mode,
        baselines=baselines,
        real_llm_calls=0,
        generated_at=dataset.generated_at,
        status="failed" if failure_reason is not None else "succeeded",
        failure_reason=failure_reason,
    )


def _evaluate(dataset: BenchmarkDataset, ranker) -> BaselineMetrics:
    labels = {article.article_id: article.weak_label for article in dataset.articles}
    top10_by_user: dict[str, list[int]] = {}
    precisions = []
    ndcgs = []
    effective_counts = []

    for user in dataset.users:
        ranked = ranker(user, dataset)
        top10 = [article.article_id for article in ranked[:10]]
        top10_by_user[str(user.user_id)] = top10
        effective_count = sum(1 for article_id in top10 if labels.get(article_id) in VALID_LABELS)
        effective_counts.append(effective_count)
        precisions.append(effective_count / 10)
        ndcgs.append(_ndcg_at_10(top10, labels))

    return BaselineMetrics(
        precision_at_10=_average(precisions),
        ndcg_at_10=_average(ndcgs),
        average_effective_at_10=_average(effective_counts),
        top10_by_user=top10_by_user,
    )


def _failure_reason(baselines: dict[str, BaselineMetrics]) -> str | None:
    if baselines["B4"].ndcg_at_10 < baselines["B0"].ndcg_at_10:
        return "b4_ndcg_below_b0"
    return None


def _rank_b0(_user: BenchmarkUser, dataset: BenchmarkDataset) -> list[BenchmarkArticle]:
    return sorted(
        dataset.articles,
        key=lambda article: (article.published_at, article.article_id),
        reverse=True,
    )


def _rank_b1(user: BenchmarkUser, dataset: BenchmarkDataset) -> list[BenchmarkArticle]:
    return sorted(
        dataset.articles,
        key=lambda article: (
            _article_priority(user, article),
            article.published_at,
            article.article_id,
        ),
        reverse=True,
    )


def _rank_b2(user: BenchmarkUser, dataset: BenchmarkDataset) -> list[BenchmarkArticle]:
    return sorted(
        dataset.articles,
        key=lambda article: (
            _keyword_score(article) + _article_priority(user, article),
            article.published_at,
            article.article_id,
        ),
        reverse=True,
    )


def _rank_b3(_user: BenchmarkUser, dataset: BenchmarkDataset) -> list[BenchmarkArticle]:
    return sorted(
        dataset.articles,
        key=lambda article: (article.base_score, article.published_at, article.article_id),
        reverse=True,
    )


def _rank_b4(user: BenchmarkUser, dataset: BenchmarkDataset) -> list[BenchmarkArticle]:
    ranking_module = _load_online_ranking_module()
    candidates = [
        ranking_module.Candidate(
            article_id=article.article_id,
            feed_ids=article.feed_ids,
            base_score=article.base_score,
            published_at=article.published_at,
            risk_uncertainty=article.risk_uncertainty,
            risk_flags=article.risk_flags,
        )
        for article in dataset.articles
    ]
    ranked = ranking_module.rank_b4(
        user_priority_by_feed=user.priority_by_feed,
        candidates=candidates,
        feedback_by_article=user.feedback_by_article,
        article_status_by_article=user.article_status_by_article,
        now=dataset.generated_at,
    )
    articles_by_id = {article.article_id: article for article in dataset.articles}
    return [
        articles_by_id[item.article_id]
        for item in ranked
        if item.article_id in articles_by_id
    ]


def _article_priority(user: BenchmarkUser, article: BenchmarkArticle) -> int:
    priorities = [
        user.priority_by_feed.get(feed_id, 0)
        for feed_id in article.feed_ids
    ]
    return max(priorities, default=0)


def _keyword_score(article: BenchmarkArticle) -> int:
    words = set(article.title.lower().split()) | {tag.lower() for tag in article.tags}
    return 10 * len(words & HEURISTIC_KEYWORDS)


def _ndcg_at_10(top10: list[int], labels: dict[int, str]) -> float:
    gains = [
        LABEL_RELEVANCE.get(labels.get(article_id, "skip"), 0)
        for article_id in top10[:10]
    ]
    ideal = sorted(
        (LABEL_RELEVANCE.get(label, 0) for label in labels.values()),
        reverse=True,
    )[:10]
    ideal_dcg = _dcg(ideal)
    if ideal_dcg == 0:
        return 0
    return _dcg(gains) / ideal_dcg


def _dcg(relevances: list[int]) -> float:
    total = 0.0
    for index, relevance in enumerate(relevances, start=1):
        discount = 1 if index == 1 else math.log2(index + 1)
        total += relevance / discount
    return total


def _average(values: list[float] | list[int]) -> float:
    if not values:
        return 0
    return round(sum(values) / len(values), 4)


def _load_online_ranking_module() -> ModuleType:
    repo_root = Path(__file__).resolve().parents[4]
    ranking_path = repo_root / "apps" / "api" / "app" / "domain" / "ranking.py"
    spec = importlib.util.spec_from_file_location("ai_reader_api_ranking", ranking_path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load B4 ranking module from {ranking_path}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module
