from dataclasses import dataclass, replace
from datetime import UTC, datetime
import base64
import hashlib
import json
from typing import Protocol
from uuid import UUID
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from sqlalchemy import Engine, and_, create_engine, desc, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.models import article_sources, articles, user_article_states


TRACKING_PARAMS = {"fbclid", "gclid", "mc_cid", "mc_eid"}


@dataclass(frozen=True)
class ArticleRecord:
    id: int
    primary_feed_id: int | None
    title: str
    url: str
    canonical_url: str | None
    author: str | None
    published_at: datetime | None
    content_text: str | None
    content_html: str | None
    content_source: str | None
    content_quality: str | None
    content_hash: str | None
    dedup_key: str | None
    fetched_at: datetime | None
    content_expires_at: datetime | None
    created_at: datetime
    updated_at: datetime


@dataclass(frozen=True)
class ArticleSourceRecord:
    article_id: int
    feed_id: int
    miniflux_entry_id: int
    source_url: str | None
    source_title: str | None
    published_at: datetime | None


@dataclass(frozen=True)
class ArticleStateRecord:
    status: str
    saved: bool
    read_progress: float


@dataclass(frozen=True)
class ArticlePage:
    items: list[ArticleRecord]
    next_cursor: str | None
    has_more: bool


class ArticleStore(Protocol):
    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord: ...

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]: ...

    def list_articles(self, *, limit: int, cursor: str | None = None) -> ArticlePage: ...

    def get_article(self, article_id: int) -> ArticleRecord | None: ...

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord: ...

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None: ...


def canonicalize_url(url: str) -> str:
    parts = urlsplit(url.strip())
    query_items = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not key.lower().startswith("utm_") and key.lower() not in TRACKING_PARAMS
    ]
    query = urlencode(sorted(query_items), doseq=True)
    return urlunsplit(
        (
            parts.scheme.lower(),
            parts.netloc.lower(),
            parts.path or "/",
            query,
            "",
        )
    )


def dedup_key_for_entry(url: str, title: str, content_text: str | None = None) -> str:
    canonical_url = canonicalize_url(url)
    if canonical_url:
        return canonical_url
    content_hash = _content_hash(content_text)
    return hashlib.sha256(f"{title.strip().lower()}:{content_hash}".encode("utf-8")).hexdigest()


def encode_article_cursor(article: ArticleRecord) -> str:
    payload = {
        "published_at": article.published_at.isoformat() if article.published_at else None,
        "id": article.id,
    }
    return base64.urlsafe_b64encode(json.dumps(payload).encode("utf-8")).decode("ascii")


def decode_article_cursor(cursor: str) -> tuple[datetime | None, int]:
    payload = json.loads(base64.urlsafe_b64decode(cursor.encode("ascii")).decode("utf-8"))
    published_at = payload.get("published_at")
    return (
        datetime.fromisoformat(published_at) if published_at is not None else None,
        int(payload["id"]),
    )


class MemoryArticleRepository:
    def __init__(self) -> None:
        self._articles: dict[int, ArticleRecord] = {}
        self._article_ids_by_dedup_key: dict[str, int] = {}
        self._sources_by_feed_entry: dict[tuple[int, int], ArticleSourceRecord] = {}
        self._states: dict[tuple[UUID, int], ArticleStateRecord] = {}
        self._next_id = 1

    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord:
        feed_id = int(entry["feed_id"])
        miniflux_entry_id = int(entry["miniflux_entry_id"])
        url = str(entry["url"])
        title = str(entry["title"])
        content_text = _optional_str(entry.get("content_text"))
        dedup_key = dedup_key_for_entry(url, title, content_text)
        article_id = self._article_ids_by_dedup_key.get(dedup_key)
        now = datetime.now(UTC)

        if article_id is None:
            article_id = self._next_id
            self._next_id += 1
            article = ArticleRecord(
                id=article_id,
                primary_feed_id=feed_id,
                title=title,
                url=url,
                canonical_url=canonicalize_url(url),
                author=_optional_str(entry.get("author")),
                published_at=_optional_datetime(entry.get("published_at")),
                content_text=content_text,
                content_html=_optional_str(entry.get("content_html")),
                content_source=_optional_str(entry.get("content_source")),
                content_quality=_optional_str(entry.get("content_quality")),
                content_hash=_content_hash(content_text),
                dedup_key=dedup_key,
                fetched_at=_optional_datetime(entry.get("fetched_at")),
                content_expires_at=_optional_datetime(entry.get("content_expires_at")),
                created_at=now,
                updated_at=now,
            )
            self._articles[article_id] = article
            self._article_ids_by_dedup_key[dedup_key] = article_id
        else:
            article = self._articles[article_id]

        source = ArticleSourceRecord(
            article_id=article_id,
            feed_id=feed_id,
            miniflux_entry_id=miniflux_entry_id,
            source_url=url,
            source_title=title,
            published_at=_optional_datetime(entry.get("published_at")),
        )
        self._sources_by_feed_entry[(feed_id, miniflux_entry_id)] = source
        return article

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]:
        return sorted(
            [
                source
                for source in self._sources_by_feed_entry.values()
                if source.article_id == article_id
            ],
            key=lambda source: (source.feed_id, source.miniflux_entry_id),
        )

    def list_articles(self, *, limit: int, cursor: str | None = None) -> ArticlePage:
        items = sorted(
            self._articles.values(),
            key=lambda article: (
                article.published_at or datetime.min.replace(tzinfo=UTC),
                article.id,
            ),
            reverse=True,
        )
        if cursor:
            cursor_published_at, cursor_id = decode_article_cursor(cursor)
            items = [
                article
                for article in items
                if _is_after_cursor(article, cursor_published_at, cursor_id)
            ]

        page_items = items[:limit]
        has_more = len(items) > limit
        next_cursor = encode_article_cursor(page_items[-1]) if has_more and page_items else None
        return ArticlePage(items=page_items, next_cursor=next_cursor, has_more=has_more)

    def get_article(self, article_id: int) -> ArticleRecord | None:
        return self._articles.get(article_id)

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord:
        return self._states.get((user_id, article_id), _default_state())

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None:
        if article_id not in self._articles:
            return None
        current = self.get_state(user_id, article_id)
        updated = replace(
            current,
            status=status if status is not None else current.status,
            saved=saved if saved is not None else current.saved,
            read_progress=read_progress if read_progress is not None else current.read_progress,
        )
        self._states[(user_id, article_id)] = updated
        return updated


class DatabaseArticleRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def upsert_from_source(self, entry: dict[str, object]) -> ArticleRecord:
        feed_id = int(entry["feed_id"])
        miniflux_entry_id = int(entry["miniflux_entry_id"])
        url = str(entry["url"])
        title = str(entry["title"])
        content_text = _optional_str(entry.get("content_text"))
        dedup_key = dedup_key_for_entry(url, title, content_text)

        with self.engine.begin() as connection:
            row = connection.execute(
                select(articles).where(articles.c.dedup_key == dedup_key)
            ).mappings().one_or_none()
            if row is None:
                row = self._insert_article(connection, entry, dedup_key)

            article = _article_from_row(row)
            self._upsert_source(
                connection,
                article.id,
                feed_id,
                miniflux_entry_id,
                url,
                title,
                _optional_datetime(entry.get("published_at")),
            )
        return article

    def sources_for_article(self, article_id: int) -> list[ArticleSourceRecord]:
        statement = (
            select(article_sources)
            .where(article_sources.c.article_id == article_id)
            .order_by(article_sources.c.feed_id.asc(), article_sources.c.miniflux_entry_id.asc())
        )
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        return [_source_from_row(row) for row in rows]

    def list_articles(self, *, limit: int, cursor: str | None = None) -> ArticlePage:
        statement = select(articles)
        if cursor:
            cursor_published_at, cursor_id = decode_article_cursor(cursor)
            if cursor_published_at is None:
                statement = statement.where(articles.c.id < cursor_id)
            else:
                statement = statement.where(
                    (articles.c.published_at < cursor_published_at)
                    | and_(
                        articles.c.published_at == cursor_published_at,
                        articles.c.id < cursor_id,
                    )
                )
        statement = statement.order_by(desc(articles.c.published_at), desc(articles.c.id)).limit(
            limit + 1
        )
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        items = [_article_from_row(row) for row in rows[:limit]]
        has_more = len(rows) > limit
        next_cursor = encode_article_cursor(items[-1]) if has_more and items else None
        return ArticlePage(items=items, next_cursor=next_cursor, has_more=has_more)

    def get_article(self, article_id: int) -> ArticleRecord | None:
        with self.engine.begin() as connection:
            row = (
                connection.execute(select(articles).where(articles.c.id == article_id))
                .mappings()
                .one_or_none()
            )
        return _article_from_row(row) if row is not None else None

    def get_state(self, user_id: UUID, article_id: int) -> ArticleStateRecord:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(user_article_states).where(
                        user_article_states.c.user_id == user_id,
                        user_article_states.c.article_id == article_id,
                    )
                )
                .mappings()
                .one_or_none()
            )
        return _state_from_row(row) if row is not None else _default_state()

    def upsert_state(
        self,
        user_id: UUID,
        article_id: int,
        *,
        status: str | None = None,
        saved: bool | None = None,
        read_progress: float | None = None,
    ) -> ArticleStateRecord | None:
        if self.get_article(article_id) is None:
            return None
        current = self.get_state(user_id, article_id)
        values = {
            "user_id": user_id,
            "article_id": article_id,
            "status": status if status is not None else current.status,
            "saved": saved if saved is not None else current.saved,
            "read_progress": read_progress if read_progress is not None else current.read_progress,
            "updated_at": datetime.now(UTC),
        }
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                row = (
                    connection.execute(
                        pg_insert(user_article_states)
                        .values(**values)
                        .on_conflict_do_update(
                            index_elements=[
                                user_article_states.c.user_id,
                                user_article_states.c.article_id,
                            ],
                            set_=values,
                        )
                        .returning(user_article_states)
                    )
                    .mappings()
                    .one()
                )
            else:
                row = self._upsert_state_generic(connection, values)
        return _state_from_row(row)

    def dispose(self) -> None:
        self.engine.dispose()

    def _insert_article(self, connection, entry: dict[str, object], dedup_key: str):
        content_text = _optional_str(entry.get("content_text"))
        values = {
            "primary_feed_id": int(entry["feed_id"]),
            "title": str(entry["title"]),
            "url": str(entry["url"]),
            "canonical_url": canonicalize_url(str(entry["url"])),
            "author": _optional_str(entry.get("author")),
            "published_at": _optional_datetime(entry.get("published_at")),
            "content_text": content_text,
            "content_html": _optional_str(entry.get("content_html")),
            "content_source": _optional_str(entry.get("content_source")),
            "content_quality": _optional_str(entry.get("content_quality")),
            "content_hash": _content_hash(content_text),
            "dedup_key": dedup_key,
            "fetched_at": _optional_datetime(entry.get("fetched_at")),
            "content_expires_at": _optional_datetime(entry.get("content_expires_at")),
        }
        if self.engine.dialect.name == "postgresql":
            row = (
                connection.execute(
                    pg_insert(articles)
                    .values(**values)
                    .on_conflict_do_nothing(
                        index_elements=[articles.c.dedup_key],
                        index_where=articles.c.dedup_key.is_not(None),
                    )
                    .returning(articles)
                )
                .mappings()
                .one_or_none()
            )
            if row is not None:
                return row
            return (
                connection.execute(select(articles).where(articles.c.dedup_key == dedup_key))
                .mappings()
                .one()
            )
        try:
            return connection.execute(articles.insert().values(**values).returning(articles)).mappings().one()
        except IntegrityError:
            return connection.execute(select(articles).where(articles.c.dedup_key == dedup_key)).mappings().one()

    def _upsert_source(
        self,
        connection,
        article_id: int,
        feed_id: int,
        miniflux_entry_id: int,
        source_url: str,
        source_title: str,
        published_at: datetime | None,
    ) -> None:
        values = {
            "article_id": article_id,
            "feed_id": feed_id,
            "miniflux_entry_id": miniflux_entry_id,
            "source_url": source_url,
            "source_title": source_title,
            "published_at": published_at,
            "last_seen_at": datetime.now(UTC),
        }
        if self.engine.dialect.name == "postgresql":
            connection.execute(
                pg_insert(article_sources)
                .values(**values)
                .on_conflict_do_update(
                    constraint="uq_article_sources_feed_entry",
                    set_=values,
                )
            )
            return
        existing = (
            connection.execute(
                select(article_sources).where(
                    article_sources.c.feed_id == feed_id,
                    article_sources.c.miniflux_entry_id == miniflux_entry_id,
                )
            )
            .mappings()
            .one_or_none()
        )
        if existing is None:
            connection.execute(article_sources.insert().values(**values))
            return
        connection.execute(
            update(article_sources)
            .where(article_sources.c.id == existing["id"])
            .values(**values)
        )

    def _upsert_state_generic(self, connection, values: dict[str, object]):
        row = (
            connection.execute(
                select(user_article_states).where(
                    user_article_states.c.user_id == values["user_id"],
                    user_article_states.c.article_id == values["article_id"],
                )
            )
            .mappings()
            .one_or_none()
        )
        if row is None:
            return (
                connection.execute(
                    user_article_states.insert().values(**values).returning(user_article_states)
                )
                .mappings()
                .one()
            )
        return (
            connection.execute(
                update(user_article_states)
                .where(
                    user_article_states.c.user_id == values["user_id"],
                    user_article_states.c.article_id == values["article_id"],
                )
                .values(**values)
                .returning(user_article_states)
            )
            .mappings()
            .one()
        )


def create_article_repository(database_url: str | None) -> ArticleStore:
    if database_url:
        return DatabaseArticleRepository(database_url)
    return MemoryArticleRepository()


def _article_from_row(row) -> ArticleRecord:
    return ArticleRecord(
        id=row["id"],
        primary_feed_id=row["primary_feed_id"],
        title=row["title"],
        url=row["url"],
        canonical_url=row["canonical_url"],
        author=row["author"],
        published_at=row["published_at"],
        content_text=row["content_text"],
        content_html=row["content_html"],
        content_source=row["content_source"],
        content_quality=row["content_quality"],
        content_hash=row["content_hash"],
        dedup_key=row["dedup_key"],
        fetched_at=row["fetched_at"],
        content_expires_at=row["content_expires_at"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


def _source_from_row(row) -> ArticleSourceRecord:
    return ArticleSourceRecord(
        article_id=row["article_id"],
        feed_id=row["feed_id"],
        miniflux_entry_id=row["miniflux_entry_id"],
        source_url=row["source_url"],
        source_title=row["source_title"],
        published_at=row["published_at"],
    )


def _state_from_row(row) -> ArticleStateRecord:
    progress = row["read_progress"]
    return ArticleStateRecord(
        status=row["status"],
        saved=bool(row["saved"]),
        read_progress=float(progress) if progress is not None else 0,
    )


def _default_state() -> ArticleStateRecord:
    return ArticleStateRecord(status="unread", saved=False, read_progress=0)


def _content_hash(content_text: str | None) -> str | None:
    if not content_text:
        return None
    return hashlib.sha256(content_text.encode("utf-8")).hexdigest()


def _optional_str(value: object) -> str | None:
    return str(value) if value is not None else None


def _optional_datetime(value: object) -> datetime | None:
    if value is None or isinstance(value, datetime):
        return value
    return datetime.fromisoformat(str(value))


def _is_after_cursor(
    article: ArticleRecord,
    cursor_published_at: datetime | None,
    cursor_id: int,
) -> bool:
    published_at = article.published_at or datetime.min.replace(tzinfo=UTC)
    if cursor_published_at is None:
        return article.id < cursor_id
    return published_at < cursor_published_at or (
        published_at == cursor_published_at and article.id < cursor_id
    )
