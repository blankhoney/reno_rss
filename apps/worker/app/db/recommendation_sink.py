from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import Engine, create_engine, text

from app.jobs.generate_recommendations import RecommendationContext


class DatabaseRecommendationSink:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
        source_batch_id: int | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)
        self.source_batch_id = source_batch_id

    def list_target_users(self) -> list[object]:
        with self.engine.begin() as connection:
            rows = connection.execute(text("SELECT id FROM app_users ORDER BY id")).mappings().all()
        return [row["id"] for row in rows]

    def recommendation_context_for_user(self, user_id: object) -> RecommendationContext:
        now = datetime.now(UTC)
        priorities = self._user_priorities(user_id)
        return RecommendationContext(
            user_id=user_id,
            candidates=self._candidate_rows(),
            user_priority_by_feed=priorities,
            feedback_by_article=self._feedback_by_article(user_id),
            article_status_by_article=self._state_by_article(user_id),
            now=now,
        )

    def save_recommendation_edition(
        self,
        user_id: object,
        items: list[object],
        algorithm_version: str,
    ) -> None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        INSERT INTO recommendation_editions (
                            user_id, source_batch_id, edition_type, algorithm_version, generated_at
                        )
                        VALUES (
                            :user_id, :source_batch_id, 'homepage_top10',
                            :algorithm_version, :generated_at
                        )
                        RETURNING id;
                        """
                    ),
                    {
                        "user_id": user_id,
                        "source_batch_id": self.source_batch_id,
                        "algorithm_version": algorithm_version,
                        "generated_at": datetime.now(UTC).isoformat(),
                    },
                )
                .mappings()
                .one()
            )
            edition_id = row["id"]
            for item in items:
                connection.execute(
                    text(
                        """
                        INSERT INTO recommendation_items (
                            edition_id, article_id, rank, rank_score, tier, reason, source
                        )
                        VALUES (
                            :edition_id, :article_id, :rank, :rank_score, :tier, :reason, :source
                        );
                        """
                    ),
                    {
                        "edition_id": edition_id,
                        "article_id": item["article_id"],
                        "rank": item["rank"],
                        "rank_score": item["rank_score"],
                        "tier": item["tier"],
                        "reason": item["reason"],
                        "source": item["source"],
                    },
                )

    def dispose(self) -> None:
        self.engine.dispose()

    def _user_priorities(self, user_id: object) -> dict[int, int]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT feed_id, user_priority
                        FROM user_feed_subscriptions
                        WHERE user_id=:user_id AND enabled=1;
                        """
                    ),
                    {"user_id": user_id},
                )
                .mappings()
                .all()
            )
        return {int(row["feed_id"]): int(row["user_priority"] or 0) for row in rows}

    def _candidate_rows(self) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            a.id AS article_id,
                            a.published_at,
                            s.feed_id,
                            bs.base_score,
                            bs.dimension_scores,
                            bs.risk_flags
                        FROM articles a
                        JOIN article_base_scores bs ON bs.article_id = a.id
                        JOIN article_sources s ON s.article_id = a.id
                        WHERE bs.is_active = 1 AND bs.scoring_status = 'success'
                        ORDER BY a.id ASC, s.feed_id ASC;
                        """
                    )
                )
                .mappings()
                .all()
            )

        candidates: dict[int, dict[str, object]] = {}
        for row in rows:
            article_id = int(row["article_id"])
            candidate = candidates.setdefault(
                article_id,
                {
                    "article_id": article_id,
                    "feed_ids": [],
                    "base_score": int(row["base_score"]),
                    "published_at": _parse_datetime(row["published_at"]),
                    "risk_uncertainty": _risk_uncertainty(row["dimension_scores"]),
                    "risk_flags": _json_list(row["risk_flags"]),
                },
            )
            candidate["feed_ids"].append(int(row["feed_id"]))
        return list(candidates.values())

    def _feedback_by_article(self, user_id: object) -> dict[int, object]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT article_id, feedback_type, user_score
                        FROM user_article_feedback_scores
                        WHERE user_id=:user_id;
                        """
                    ),
                    {"user_id": user_id},
                )
                .mappings()
                .all()
            )
        return {
            int(row["article_id"]): {
                "feedback_type": row["feedback_type"],
                "user_score": row["user_score"],
            }
            for row in rows
        }

    def _state_by_article(self, user_id: object) -> dict[int, str | None]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT article_id, status
                        FROM user_article_states
                        WHERE user_id=:user_id;
                        """
                    ),
                    {"user_id": user_id},
                )
                .mappings()
                .all()
            )
        return {int(row["article_id"]): row["status"] for row in rows}


def _parse_datetime(value: object) -> datetime:
    if isinstance(value, datetime):
        return value
    parsed = datetime.fromisoformat(str(value))
    return parsed if parsed.tzinfo else parsed.replace(tzinfo=UTC)


def _json_list(value: object) -> list[object]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    loaded = json.loads(str(value))
    return loaded if isinstance(loaded, list) else []


def _risk_uncertainty(value: object) -> int:
    if value is None:
        return 100
    if isinstance(value, dict):
        raw = value.get("risk_uncertainty", 100)
    else:
        loaded = json.loads(str(value))
        raw = loaded.get("risk_uncertainty", 100) if isinstance(loaded, dict) else 100
    try:
        return int(raw)
    except (TypeError, ValueError):
        return 100
