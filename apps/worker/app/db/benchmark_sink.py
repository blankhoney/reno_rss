from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import Engine, create_engine, text

from app.benchmark.ranking import BenchmarkArticle, BenchmarkDataset, BenchmarkUser


class DatabaseBenchmarkSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def load_benchmark_dataset(self, _benchmark_run_id: object) -> BenchmarkDataset:
        generated_at = datetime.now(UTC)
        users = self._users()
        priority_by_user = self._priority_by_user()
        feedback_by_user = self._feedback_by_user()
        state_by_user = self._state_by_user()
        articles = self._articles(generated_at)

        return BenchmarkDataset(
            users=[
                BenchmarkUser(
                    user_id=user_id,
                    priority_by_feed=priority_by_user.get(user_id, {}),
                    feedback_by_article=feedback_by_user.get(user_id, {}),
                    article_status_by_article=state_by_user.get(user_id, {}),
                )
                for user_id in users
            ],
            articles=articles,
            generated_at=generated_at,
        )

    def dry_run_benchmark_cost(self, benchmark_run_id: object) -> dict[str, object]:
        dataset = self.load_benchmark_dataset(benchmark_run_id)
        return {
            "pair_count": len(dataset.users) * len(dataset.articles),
            "estimated_cost_usd": 0.0,
        }

    def save_benchmark_result(
        self,
        benchmark_run_id: object,
        metrics: dict[str, object],
        artifact_path: str | None,
        cost_estimate: dict[str, object],
    ) -> None:
        status = str(metrics.get("status", "succeeded"))
        if status not in {"succeeded", "failed"}:
            status = "succeeded"
        with self.engine.begin() as connection:
            connection.execute(
                text(_update_benchmark_run_sql(self.engine.dialect.name)),
                {
                    "benchmark_run_id": benchmark_run_id,
                    "status": status,
                    "metrics": json.dumps(metrics, ensure_ascii=False),
                    "artifact_path": artifact_path,
                    "cost_estimate": json.dumps(cost_estimate, ensure_ascii=False),
                    "completed_at": datetime.now(UTC).isoformat(),
                },
            )

    def dispose(self) -> None:
        self.engine.dispose()

    def _users(self) -> list[object]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(text("SELECT id FROM app_users ORDER BY created_at ASC, id ASC;"))
                .mappings()
                .all()
            )
        return [row["id"] for row in rows]

    def _priority_by_user(self) -> dict[object, dict[int, int]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT user_id, feed_id, user_priority
                        FROM user_feed_subscriptions
                        WHERE enabled = TRUE
                        ORDER BY user_id ASC, feed_id ASC;
                        """
                    )
                )
                .mappings()
                .all()
            )
        priorities: dict[object, dict[int, int]] = {}
        for row in rows:
            priorities.setdefault(row["user_id"], {})[int(row["feed_id"])] = int(
                row["user_priority"] or 0
            )
        return priorities

    def _feedback_by_user(self) -> dict[object, dict[int, object]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT user_id, article_id, feedback_type, user_score
                        FROM user_article_feedback_scores
                        ORDER BY user_id ASC, article_id ASC;
                        """
                    )
                )
                .mappings()
                .all()
            )
        feedback: dict[object, dict[int, object]] = {}
        for row in rows:
            feedback.setdefault(row["user_id"], {})[int(row["article_id"])] = {
                "feedback_type": row["feedback_type"],
                "user_score": row["user_score"],
            }
        return feedback

    def _state_by_user(self) -> dict[object, dict[int, str | None]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT user_id, article_id, status
                        FROM user_article_states
                        ORDER BY user_id ASC, article_id ASC;
                        """
                    )
                )
                .mappings()
                .all()
            )
        states: dict[object, dict[int, str | None]] = {}
        for row in rows:
            states.setdefault(row["user_id"], {})[int(row["article_id"])] = row["status"]
        return states

    def _articles(self, generated_at: datetime) -> list[BenchmarkArticle]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            a.id AS article_id,
                            a.primary_feed_id,
                            a.title,
                            a.published_at,
                            bs.base_score,
                            bs.recommendation_tier,
                            bs.tags,
                            bs.dimension_scores,
                            bs.risk_flags,
                            src.feed_id
                        FROM articles a
                        JOIN article_base_scores bs ON bs.article_id = a.id
                        LEFT JOIN article_sources src ON src.article_id = a.id
                        WHERE bs.is_active = TRUE AND bs.scoring_status = 'success'
                        ORDER BY a.id ASC, src.feed_id ASC;
                        """
                    )
                )
                .mappings()
                .all()
            )

        grouped: dict[int, dict[str, object]] = {}
        for row in rows:
            article_id = int(row["article_id"])
            article = grouped.setdefault(
                article_id,
                {
                    "article_id": article_id,
                    "feed_ids": [],
                    "title": str(row["title"] or ""),
                    "tags": _json_list(row["tags"]),
                    "base_score": int(row["base_score"] or 0),
                    "published_at": _parse_datetime(row["published_at"], generated_at),
                    "risk_uncertainty": _risk_uncertainty(row["dimension_scores"]),
                    "risk_flags": _json_list(row["risk_flags"]),
                    "weak_label": _weak_label(row["recommendation_tier"], row["base_score"]),
                },
            )
            feed_id = row["feed_id"] if row["feed_id"] is not None else row["primary_feed_id"]
            if feed_id is not None:
                feed_ids = article["feed_ids"]
                assert isinstance(feed_ids, list)
                int_feed_id = int(feed_id)
                if int_feed_id not in feed_ids:
                    feed_ids.append(int_feed_id)

        return [BenchmarkArticle(**values) for values in grouped.values()]


def _update_benchmark_run_sql(dialect_name: str) -> str:
    metrics = "CAST(:metrics AS jsonb)" if dialect_name == "postgresql" else ":metrics"
    cost_estimate = "CAST(:cost_estimate AS jsonb)" if dialect_name == "postgresql" else ":cost_estimate"
    return f"""
        UPDATE benchmark_runs
        SET status = :status,
            metrics = {metrics},
            artifact_path = :artifact_path,
            cost_estimate = {cost_estimate},
            completed_at = :completed_at
        WHERE id = :benchmark_run_id;
        """


def _parse_datetime(value: object, default: datetime) -> datetime:
    if value is None:
        return default
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=UTC)
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_list(value: object) -> list[str]:
    if value is None:
        return []
    if isinstance(value, list):
        return [str(item) for item in value]
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return []
    if not isinstance(loaded, list):
        return []
    return [str(item) for item in loaded]


def _json_dict(value: object) -> dict[str, object]:
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    try:
        loaded = json.loads(str(value))
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _risk_uncertainty(value: object) -> int:
    raw = _json_dict(value).get("risk_uncertainty", 100)
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 100


def _weak_label(recommendation_tier: object, base_score: object) -> str:
    tier = str(recommendation_tier or "")
    if tier in {"must_read", "read", "skim", "skip"}:
        return tier
    try:
        score = int(base_score or 0)
    except (TypeError, ValueError):
        score = 0
    if score >= 85:
        return "must_read"
    if score >= 70:
        return "read"
    if score >= 50:
        return "skim"
    return "skip"
