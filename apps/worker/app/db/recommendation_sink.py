from __future__ import annotations

from datetime import UTC, datetime
import json

from sqlalchemy import Engine, create_engine, text
from sqlalchemy.engine import Connection

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
        self._candidate_rows_cache: list[dict[str, object]] | None = None

    def list_target_users(self) -> list[object]:
        with self.engine.begin() as connection:
            rows = connection.execute(text("SELECT id FROM app_users ORDER BY id")).mappings().all()
        return [row["id"] for row in rows]

    def recommendation_context_for_user(self, user_id: object) -> RecommendationContext:
        now = datetime.now(UTC)
        priorities = self._user_priorities(user_id)
        candidates = self._candidate_rows_once()
        return RecommendationContext(
            user_id=user_id,
            candidates=candidates,
            user_priority_by_feed=priorities,
            feedback_by_article=self._feedback_by_article(user_id),
            article_status_by_article=self._state_by_article(user_id),
            now=now,
            rules=self._rules_for_user(user_id),
            titles_by_article=self._titles_from_candidates(candidates),
        )

    def save_recommendation_edition(
        self,
        user_id: object,
        items: list[object],
        algorithm_version: str,
    ) -> None:
        with self.engine.begin() as connection:
            if self.source_batch_id is not None:
                self._delete_existing_source_edition(connection, user_id, algorithm_version)

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

    def _delete_existing_source_edition(
        self,
        connection: Connection,
        user_id: object,
        algorithm_version: str,
    ) -> None:
        params = {
            "user_id": user_id,
            "source_batch_id": self.source_batch_id,
            "algorithm_version": algorithm_version,
        }
        connection.execute(
            text(
                """
                DELETE FROM recommendation_items
                WHERE edition_id IN (
                    SELECT id
                    FROM recommendation_editions
                    WHERE user_id = :user_id
                      AND source_batch_id = :source_batch_id
                      AND edition_type = 'homepage_top10'
                      AND algorithm_version = :algorithm_version
                );
                """
            ),
            params,
        )
        connection.execute(
            text(
                """
                DELETE FROM recommendation_editions
                WHERE user_id = :user_id
                  AND source_batch_id = :source_batch_id
                  AND edition_type = 'homepage_top10'
                  AND algorithm_version = :algorithm_version;
                """
            ),
            params,
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
                        WHERE user_id=:user_id AND enabled = TRUE;
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
                            a.title,
                            a.published_at,
                            s.feed_id,
                            bs.base_score,
                            bs.dimension_scores,
                            bs.risk_flags
                        FROM articles a
                        JOIN article_base_scores bs ON bs.article_id = a.id
                        JOIN article_sources s ON s.article_id = a.id
                        WHERE bs.is_active = TRUE AND bs.scoring_status = 'success'
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
                    "title": str(row["title"] or "") if row.get("title") is not None else "",
                    "feed_ids": [],
                    "base_score": int(row["base_score"]),
                    "published_at": _parse_datetime(row["published_at"]),
                    "risk_uncertainty": _risk_uncertainty(row["dimension_scores"]),
                    "risk_flags": _json_list(row["risk_flags"]),
                },
            )
            candidate["feed_ids"].append(int(row["feed_id"]))
        return list(candidates.values())

    def _candidate_rows_once(self) -> list[dict[str, object]]:
        if self._candidate_rows_cache is None:
            self._candidate_rows_cache = self._candidate_rows()
        return self._candidate_rows_cache

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

    def _rules_for_user(self, user_id: object) -> list[object]:
        """Load boost/mute/keyword/threshold rules for the ranking pipeline."""
        try:
            with self.engine.begin() as connection:
                row = (
                    connection.execute(
                        text(
                            """
                            SELECT rules
                            FROM user_reader_rules
                            WHERE user_id = :user_id;
                            """
                        ),
                        {"user_id": user_id},
                    )
                    .mappings()
                    .first()
                )
        except Exception:
            # Table may be missing in older schemas/tests; ranking still works.
            return []
        if row is None:
            return []
        raw = row["rules"]
        if raw is None:
            return []
        if isinstance(raw, str):
            try:
                raw = json.loads(raw)
            except json.JSONDecodeError:
                return []
        if not isinstance(raw, list):
            return []
        return [item for item in raw if isinstance(item, dict)]

    @staticmethod
    def _titles_from_candidates(candidates: list[dict[str, object]]) -> dict[int, str]:
        titles: dict[int, str] = {}
        for candidate in candidates:
            try:
                article_id = int(candidate["article_id"])  # type: ignore[arg-type]
            except (KeyError, TypeError, ValueError):
                continue
            title = candidate.get("title")
            titles[article_id] = str(title) if title is not None else ""
        return titles


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
