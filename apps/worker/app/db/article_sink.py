from __future__ import annotations

from collections.abc import Sequence
from datetime import UTC, datetime
import hashlib

from sqlalchemy import Engine, create_engine, text

from app.jobs.queue import PostgresJobQueue


class DatabaseArticleSink:
    def __init__(self, database_url: str | None = None, *, engine: Engine | None = None) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)
        self.queue = PostgresJobQueue(str(database_url or ""), engine=self.engine)

    def upsert_feed(self, feed: dict[str, object]) -> int:
        values = _feed_values(feed)
        with self.engine.begin() as connection:
            row = _existing_feed(connection, values)
            if row is not None:
                _update_existing_feed(connection, int(row["id"]), values)
                return int(row["id"])

            if values["feed_url"] is None:
                raise ValueError("feed_url is required to create an unknown Miniflux feed")

            row = (
                connection.execute(
                    text(
                        """
                        INSERT INTO feeds (
                            feed_url, canonical_url, miniflux_feed_id, title, status
                        )
                        VALUES (
                            :feed_url, :canonical_url, :miniflux_feed_id, :title, 'active'
                        )
                        RETURNING id;
                        """
                    ),
                    values,
                )
                .mappings()
                .one()
            )
        return int(row["id"])

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

    def enqueue_ingest_followups(
        self,
        article_ids: list[int],
        *,
        pipeline_cycle: str,
        auto_score_payload: dict[str, object],
    ) -> dict[str, object]:
        unique_article_ids = list(dict.fromkeys(int(article_id) for article_id in article_ids))
        rows: list[dict[str, object]] = []
        if unique_article_ids:
            placeholders = ", ".join(
                f":article_id_{index}" for index in range(len(unique_article_ids))
            )
            params = {
                f"article_id_{index}": article_id
                for index, article_id in enumerate(unique_article_ids)
            }
            with self.engine.begin() as connection:
                rows = [
                    dict(row)
                    for row in connection.execute(
                        text(
                            f"""
                            SELECT id, content_text, content_html, content_quality,
                                   content_expires_at
                            FROM articles
                            WHERE id IN ({placeholders})
                            ORDER BY id ASC;
                            """
                        ),
                        params,
                    ).mappings().all()
                ]

        fetch_job_ids: list[int] = []
        now = datetime.now(UTC)
        for row in rows:
            if not _needs_content_fetch(row, now=now):
                continue
            article_id = int(row["id"])
            job = self.queue.enqueue(
                "fetch_article_content",
                {"article_id": article_id, "pipeline_cycle": pipeline_cycle},
                dedupe_key=_dedupe_key_for("fetch_article_content", article_id),
                priority=4,
            )
            fetch_job_ids.append(job.id)

        barrier = self.queue.enqueue(
            "complete_ingest_cycle",
            {
                "pipeline_cycle": pipeline_cycle,
                "fetch_job_ids": fetch_job_ids,
                "auto_score_payload": dict(auto_score_payload),
            },
            dedupe_key=f"pipeline:complete_ingest_cycle:{pipeline_cycle}",
            priority=3,
            max_attempts=20,
        )
        return {
            "pipeline_cycle": pipeline_cycle,
            "content_fetches": len(fetch_job_ids),
            "barrier_job_id": barrier.id,
        }

    def fetch_job_statuses(self, job_ids: Sequence[int]) -> dict[int, str]:
        unique_job_ids = list(dict.fromkeys(int(job_id) for job_id in job_ids))
        if not unique_job_ids:
            return {}
        placeholders = ", ".join(f":job_id_{index}" for index in range(len(unique_job_ids)))
        params = {
            f"job_id_{index}": job_id for index, job_id in enumerate(unique_job_ids)
        }
        with self.engine.begin() as connection:
            rows = connection.execute(
                text(
                    f"SELECT id, status FROM jobs WHERE id IN ({placeholders});"
                ),
                params,
            ).mappings().all()
        return {int(row["id"]): str(row["status"]) for row in rows}

    def enqueue_auto_score(
        self,
        payload: dict[str, object],
        *,
        pipeline_cycle: str,
    ) -> None:
        self.queue.enqueue(
            "auto_score_candidates",
            {**payload, "pipeline_cycle": pipeline_cycle},
            dedupe_key=f"pipeline:auto_score_candidates:{pipeline_cycle}",
            priority=3,
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


def _feed_values(feed: dict[str, object]) -> dict[str, object]:
    feed_url = _optional_str(feed.get("feed_url"))
    title = _optional_str(feed.get("feed_title")) or feed_url
    return {
        "fallback_feed_id": int(feed["feed_id"]),
        "feed_url": feed_url,
        "canonical_url": _optional_str(feed.get("feed_site_url")),
        "miniflux_feed_id": int(feed["feed_id"]),
        "title": title,
    }


def _existing_feed(connection, values: dict[str, object]):
    miniflux_feed_id = values["miniflux_feed_id"]
    row = (
        connection.execute(
            text("SELECT id FROM feeds WHERE miniflux_feed_id=:miniflux_feed_id"),
            {"miniflux_feed_id": miniflux_feed_id},
        )
        .mappings()
        .one_or_none()
    )
    if row is not None:
        return row

    feed_url = values["feed_url"]
    if feed_url is not None:
        row = (
            connection.execute(
                text("SELECT id FROM feeds WHERE feed_url=:feed_url"),
                {"feed_url": feed_url},
            )
            .mappings()
            .one_or_none()
        )
        if row is not None:
            return row

    return (
        connection.execute(
            text("SELECT id FROM feeds WHERE id=:feed_id"),
            {"feed_id": values["fallback_feed_id"]},
        )
        .mappings()
        .one_or_none()
    )


def _update_existing_feed(connection, feed_id: int, values: dict[str, object]) -> None:
    connection.execute(
        text(
            """
            UPDATE feeds
            SET feed_url=COALESCE(:feed_url, feed_url),
                canonical_url=COALESCE(:canonical_url, canonical_url),
                miniflux_feed_id=COALESCE(miniflux_feed_id, :miniflux_feed_id),
                title=COALESCE(:title, title),
                updated_at=CURRENT_TIMESTAMP
            WHERE id=:id;
            """
        ),
        {**values, "id": feed_id},
    )


def _content_hash(content_text: str | None) -> str | None:
    if not content_text:
        return None
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _dedupe_key_for(job_type: str, value: object) -> str:
    return hashlib.sha256(f"{job_type}:{value}".encode("utf-8")).hexdigest()


def _needs_content_fetch(row: dict[str, object], *, now: datetime) -> bool:
    current = str(row.get("content_html") or row.get("content_text") or "").strip()
    if not current or str(row.get("content_quality") or "") != "full":
        return True
    expires_at = row.get("content_expires_at")
    if expires_at is None:
        return False
    expires = (
        expires_at
        if isinstance(expires_at, datetime)
        else datetime.fromisoformat(str(expires_at))
    )
    normalized = expires.astimezone(UTC) if expires.tzinfo else expires.replace(tzinfo=UTC)
    return normalized <= now


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
