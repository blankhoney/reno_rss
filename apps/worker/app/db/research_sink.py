"""Load corpus articles for research_brief jobs (recommendations / project / title search)."""

from __future__ import annotations

from sqlalchemy import Engine, create_engine, text


class DatabaseResearchSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def list_topn_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            edition_id = connection.execute(
                text(
                    """
                    SELECT id FROM recommendation_editions
                    WHERE user_id = CAST(:user_id AS uuid)
                    ORDER BY generated_at DESC, id DESC
                    LIMIT 1
                    """
                ),
                {"user_id": user_id},
            ).scalar_one_or_none()
            if edition_id is None:
                return []
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT i.article_id, a.title, a.content_text, s.summary_zh
                        FROM recommendation_items i
                        LEFT JOIN articles a ON a.id = i.article_id
                        LEFT JOIN article_base_scores s
                          ON s.article_id = i.article_id AND s.is_active = true
                        WHERE i.edition_id = :edition_id
                        ORDER BY i.rank ASC
                        LIMIT :limit
                        """
                    ),
                    {"edition_id": edition_id, "limit": limit},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def list_project_articles(self, *, user_id: str, limit: int) -> list[dict[str, object]]:
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT a.id AS article_id, a.title, a.content_text, s.summary_zh
                        FROM user_article_states u
                        JOIN articles a ON a.id = u.article_id
                        LEFT JOIN article_base_scores s
                          ON s.article_id = a.id AND s.is_active = true
                        WHERE u.user_id = CAST(:user_id AS uuid)
                          AND u.project = true
                        ORDER BY u.updated_at DESC NULLS LAST, a.id DESC
                        LIMIT :limit
                        """
                    ),
                    {"user_id": user_id, "limit": limit},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def search_articles_by_topic(self, *, topic: str, limit: int) -> list[dict[str, object]]:
        pattern = f"%{topic}%"
        with self.engine.begin() as connection:
            rows = (
                connection.execute(
                    text(
                        """
                        SELECT a.id AS article_id, a.title, a.content_text, s.summary_zh
                        FROM articles a
                        LEFT JOIN article_base_scores s
                          ON s.article_id = a.id AND s.is_active = true
                        WHERE a.title ILIKE :pattern
                           OR a.content_text ILIKE :pattern
                           OR s.summary_zh ILIKE :pattern
                           OR CAST(s.tags AS text) ILIKE :pattern
                        ORDER BY
                          CASE
                            WHEN a.title ILIKE :pattern THEN 0
                            WHEN s.summary_zh ILIKE :pattern THEN 1
                            ELSE 2
                          END,
                          a.published_at DESC NULLS LAST,
                          a.id DESC
                        LIMIT :limit
                        """
                    ),
                    {"pattern": pattern, "limit": limit},
                )
                .mappings()
                .all()
            )
        return [dict(row) for row in rows]

    def dispose(self) -> None:
        self.engine.dispose()
