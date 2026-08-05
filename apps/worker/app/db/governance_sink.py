"""Postgres sink for source governance demotions."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text


class DatabaseGovernanceSink:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def list_recent_quality_samples(self, *, limit: int = 500) -> list[dict[str, object]]:
        capped = max(1, min(int(limit), 2000))
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT
                            s.feed_id AS feed_id,
                            a.content_quality AS content_quality,
                            bs.base_score AS base_score
                        FROM articles a
                        JOIN article_sources s ON s.article_id = a.id
                        LEFT JOIN article_base_scores bs
                          ON bs.article_id = a.id AND bs.is_active = TRUE
                        WHERE a.content_quality IS NOT NULL
                        ORDER BY a.id DESC
                        LIMIT :limit
                        """
                    ),
                    {"limit": capped},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def demote_feed(self, feed_id: int, *, reason: str) -> int:
        """Hide feed for all subscribers (soft demote) and lower priority."""
        del reason  # retained for future audit log table
        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    UPDATE user_feed_subscriptions
                    SET user_priority = CASE
                      WHEN user_priority IS NULL OR user_priority > -20 THEN -20
                      ELSE user_priority
                    END
                    WHERE feed_id = :feed_id
                    """
                ),
                {"feed_id": int(feed_id)},
            )
        return int(result.rowcount or 0)

    def dispose(self) -> None:
        self.engine.dispose()
