from __future__ import annotations

from datetime import datetime
import hashlib

from sqlalchemy import Engine, create_engine, text


class DatabaseContentSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def get_article_for_fetch(self, article_id: int) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT
                            a.id,
                            a.title,
                            a.url,
                            a.content_html,
                            a.content_text,
                            s.miniflux_entry_id
                        FROM articles a
                        LEFT JOIN article_sources s ON s.article_id = a.id
                        WHERE a.id = :article_id
                        ORDER BY s.first_seen_at ASC, s.id ASC
                        LIMIT 1;
                        """
                    ),
                    {"article_id": article_id},
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def get_article_for_translation(self, article_id: int) -> dict[str, object] | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    text(
                        """
                        SELECT
                            id,
                            title,
                            url,
                            content_html,
                            content_text,
                            content_zh,
                            content_zh_status
                        FROM articles
                        WHERE id = :article_id;
                        """
                    ),
                    {"article_id": article_id},
                )
                .mappings()
                .one_or_none()
            )
        return dict(row) if row is not None else None

    def save_content(self, article_id: int, content: dict[str, object]) -> None:
        content_text = str(content["content_text"])
        values = {
            "article_id": article_id,
            "content_html": str(content["content_html"]),
            "content_text": content_text,
            "content_source": str(content["content_source"]),
            "content_quality": str(content["content_quality"]),
            "content_hash": hashlib.sha256(content_text.encode("utf-8")).hexdigest(),
            "fetched_at": _timestamp(content["fetched_at"]),
            "content_expires_at": _timestamp(content["content_expires_at"]),
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE articles
                    SET content_html=:content_html,
                        content_text=:content_text,
                        content_source=:content_source,
                        content_quality=:content_quality,
                        content_hash=:content_hash,
                        fetched_at=:fetched_at,
                        content_expires_at=:content_expires_at,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:article_id;
                    """
                ),
                values,
            )

    def save_translation(
        self,
        article_id: int,
        *,
        content_zh: str | None,
        status: str,
        translated_at: datetime | None,
    ) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    UPDATE articles
                    SET content_zh=:content_zh,
                        content_zh_status=:content_zh_status,
                        translated_at=:translated_at,
                        updated_at=CURRENT_TIMESTAMP
                    WHERE id=:article_id;
                    """
                ),
                {
                    "article_id": article_id,
                    "content_zh": content_zh,
                    "content_zh_status": status,
                    "translated_at": _timestamp(translated_at) if translated_at else None,
                },
            )

    def dispose(self) -> None:
        self.engine.dispose()


def _timestamp(value: object) -> str:
    if isinstance(value, datetime):
        return value.isoformat()
    return datetime.fromisoformat(str(value)).isoformat()
