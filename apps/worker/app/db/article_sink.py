from __future__ import annotations

from datetime import datetime
import hashlib

from sqlalchemy import Engine, create_engine, text


class DatabaseArticleSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def upsert_article(self, article: dict[str, object]) -> int:
        values = _article_values(article)
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                row = (
                    connection.execute(
                        text(
                            """
                            INSERT INTO articles (
                                primary_feed_id, title, url, canonical_url, author, published_at,
                                content_text, content_html, content_source, content_quality,
                                content_hash, dedup_key, fetched_at, content_expires_at
                            )
                            VALUES (
                                :primary_feed_id, :title, :url, :canonical_url, :author,
                                :published_at, :content_text, :content_html, :content_source,
                                :content_quality, :content_hash, :dedup_key, :fetched_at,
                                :content_expires_at
                            )
                            ON CONFLICT (dedup_key) WHERE dedup_key IS NOT NULL DO NOTHING
                            RETURNING id;
                            """
                        ),
                        values,
                    )
                    .mappings()
                    .one_or_none()
                )
            else:
                connection.execute(
                    text(
                        """
                        INSERT OR IGNORE INTO articles (
                            primary_feed_id, title, url, canonical_url, author, published_at,
                            content_text, content_html, content_source, content_quality,
                            content_hash, dedup_key, fetched_at, content_expires_at
                        )
                        VALUES (
                            :primary_feed_id, :title, :url, :canonical_url, :author,
                            :published_at, :content_text, :content_html, :content_source,
                            :content_quality, :content_hash, :dedup_key, :fetched_at,
                            :content_expires_at
                        );
                        """
                    ),
                    values,
                )
                row = None

            if row is None:
                row = (
                    connection.execute(
                        text("SELECT id FROM articles WHERE dedup_key=:dedup_key"),
                        {"dedup_key": values["dedup_key"]},
                    )
                    .mappings()
                    .one()
                )
        return int(row["id"])

    def upsert_article_source(self, source: dict[str, object]) -> None:
        values = {
            "article_id": int(source["article_id"]),
            "feed_id": int(source["feed_id"]),
            "miniflux_entry_id": int(source["miniflux_entry_id"]),
            "miniflux_category_id": _optional_int(source.get("miniflux_category_id")),
            "source_url": _optional_str(source.get("source_url")),
            "source_title": _optional_str(source.get("source_title")),
            "published_at": _optional_datetime(source.get("published_at")),
        }
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO article_sources (
                        article_id, feed_id, miniflux_entry_id, miniflux_category_id,
                        source_url, source_title, published_at, last_seen_at
                    )
                    VALUES (
                        :article_id, :feed_id, :miniflux_entry_id, :miniflux_category_id,
                        :source_url, :source_title, :published_at, CURRENT_TIMESTAMP
                    )
                    ON CONFLICT(feed_id, miniflux_entry_id) DO UPDATE SET
                        article_id=excluded.article_id,
                        miniflux_category_id=excluded.miniflux_category_id,
                        source_url=excluded.source_url,
                        source_title=excluded.source_title,
                        published_at=excluded.published_at,
                        last_seen_at=CURRENT_TIMESTAMP;
                    """
                ),
                values,
            )

    def dispose(self) -> None:
        self.engine.dispose()


def _article_values(article: dict[str, object]) -> dict[str, object]:
    title = str(article["title"])
    url = str(article["url"])
    canonical_url = _optional_str(article.get("canonical_url"))
    content_text = _optional_str(article.get("content_text"))
    content_hash = _content_hash(content_text)
    dedup_key = canonical_url or hashlib.sha256(
        f"{title.strip().lower()}:{content_hash or ''}".encode("utf-8")
    ).hexdigest()
    return {
        "primary_feed_id": int(article["primary_feed_id"]),
        "title": title,
        "url": url,
        "canonical_url": canonical_url,
        "author": _optional_str(article.get("author")),
        "published_at": _optional_datetime(article.get("published_at")),
        "content_text": content_text,
        "content_html": _optional_str(article.get("content_html")),
        "content_source": _optional_str(article.get("content_source")),
        "content_quality": _optional_str(article.get("content_quality")),
        "content_hash": content_hash,
        "dedup_key": dedup_key,
        "fetched_at": _optional_datetime(article.get("fetched_at")),
        "content_expires_at": _optional_datetime(article.get("content_expires_at")),
    }


def _content_hash(content_text: str | None) -> str | None:
    if not content_text:
        return None
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_int(value: object) -> int | None:
    if value is None:
        return None
    return int(value)


def _optional_datetime(value: object) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return datetime.fromisoformat(str(value)).isoformat()
