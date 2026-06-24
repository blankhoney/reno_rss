from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, and_, create_engine, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import IntegrityError

from app.db.models import categories, feeds, user_feed_subscriptions


SEEDED_CATEGORIES = [
    {"id": 1, "slug": "ai_infra", "name": "AI Infra", "sort_order": 10},
    {"id": 2, "slug": "agent", "name": "Agent", "sort_order": 20},
    {"id": 3, "slug": "rag", "name": "RAG", "sort_order": 30},
    {"id": 4, "slug": "paper", "name": "论文学术", "sort_order": 40},
    {"id": 5, "slug": "programming", "name": "编程", "sort_order": 50},
    {"id": 6, "slug": "tooling", "name": "工具软件版本", "sort_order": 60},
    {"id": 7, "slug": "product", "name": "产品", "sort_order": 70},
    {"id": 8, "slug": "business", "name": "商业", "sort_order": 80},
    {"id": 9, "slug": "game", "name": "游戏", "sort_order": 90},
    {"id": 10, "slug": "other", "name": "其他", "sort_order": 100},
]


@dataclass(frozen=True)
class CategoryRecord:
    id: int
    slug: str
    name: str
    sort_order: int


@dataclass(frozen=True)
class FeedRecord:
    id: int
    feed_url: str
    canonical_url: str | None
    title: str | None
    category: CategoryRecord
    status: str
    subscribed: bool
    user_priority: int


@dataclass(frozen=True)
class FeedMutation:
    feed: FeedRecord
    already_exists: bool


class FeedStore(Protocol):
    def list_categories(self) -> list[CategoryRecord]: ...

    def list_feeds(self, current_user_id: UUID) -> list[FeedRecord]: ...

    def create_or_subscribe(
        self,
        feed_url: str,
        category_id: int,
        current_user_id: UUID,
    ) -> FeedMutation: ...

    def subscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None: ...

    def unsubscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None: ...

    def set_priority(
        self,
        feed_id: int,
        current_user_id: UUID,
        user_priority: int,
    ) -> FeedRecord | None: ...


class MemoryFeedRepository:
    def __init__(self) -> None:
        self._categories = [
            CategoryRecord(
                id=row["id"],
                slug=row["slug"],
                name=row["name"],
                sort_order=row["sort_order"],
            )
            for row in SEEDED_CATEGORIES
        ]
        self._feeds: dict[int, dict[str, object]] = {}
        self._feed_ids_by_url: dict[str, int] = {}
        self._subscriptions: dict[tuple[UUID, int], dict[str, object]] = {}
        self._next_feed_id = 1

    def list_categories(self) -> list[CategoryRecord]:
        return sorted(self._categories, key=lambda category: category.sort_order)

    def list_feeds(self, current_user_id: UUID) -> list[FeedRecord]:
        records = [self._feed_record(feed_id, current_user_id) for feed_id in self._feeds]
        return sorted(records, key=lambda feed: ((feed.title or feed.feed_url).lower(), feed.id))

    def create_or_subscribe(
        self,
        feed_url: str,
        category_id: int,
        current_user_id: UUID,
    ) -> FeedMutation:
        self._category_by_id(category_id)
        existing_id = self._feed_ids_by_url.get(feed_url)
        already_exists = existing_id is not None

        if existing_id is None:
            feed_id = self._next_feed_id
            self._next_feed_id += 1
            self._feeds[feed_id] = {
                "id": feed_id,
                "feed_url": feed_url,
                "canonical_url": None,
                "title": feed_url,
                "category_id": category_id,
                "status": "active",
            }
            self._feed_ids_by_url[feed_url] = feed_id
        else:
            feed_id = existing_id

        self._upsert_subscription(feed_id, current_user_id, enabled=True)
        return FeedMutation(
            feed=self._feed_record(feed_id, current_user_id),
            already_exists=already_exists,
        )

    def subscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None:
        if feed_id not in self._feeds:
            return None
        self._upsert_subscription(feed_id, current_user_id, enabled=True)
        return self._feed_record(feed_id, current_user_id)

    def unsubscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None:
        if feed_id not in self._feeds:
            return None
        self._upsert_subscription(feed_id, current_user_id, enabled=False)
        return self._feed_record(feed_id, current_user_id)

    def set_priority(
        self,
        feed_id: int,
        current_user_id: UUID,
        user_priority: int,
    ) -> FeedRecord | None:
        if feed_id not in self._feeds:
            return None
        self._upsert_subscription(feed_id, current_user_id, enabled=True)
        self._subscriptions[(current_user_id, feed_id)]["user_priority"] = user_priority
        return self._feed_record(feed_id, current_user_id)

    def _upsert_subscription(self, feed_id: int, user_id: UUID, *, enabled: bool) -> None:
        subscription = self._subscriptions.setdefault(
            (user_id, feed_id),
            {"enabled": enabled, "user_priority": 0},
        )
        subscription["enabled"] = enabled

    def _feed_record(self, feed_id: int, user_id: UUID) -> FeedRecord:
        feed = self._feeds[feed_id]
        subscription = self._subscriptions.get((user_id, feed_id), {})
        return FeedRecord(
            id=feed_id,
            feed_url=str(feed["feed_url"]),
            canonical_url=feed["canonical_url"] if feed["canonical_url"] is not None else None,
            title=feed["title"] if feed["title"] is not None else None,
            category=self._category_by_id(int(feed["category_id"])),
            status=str(feed["status"]),
            subscribed=bool(subscription.get("enabled", False)),
            user_priority=int(subscription.get("user_priority", 0)),
        )

    def _category_by_id(self, category_id: int) -> CategoryRecord:
        for category in self._categories:
            if category.id == category_id:
                return category
        raise KeyError(category_id)


class DatabaseFeedRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def list_categories(self) -> list[CategoryRecord]:
        statement = select(categories).order_by(categories.c.sort_order.asc(), categories.c.id.asc())
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        return [_category_from_row(row) for row in rows]

    def list_feeds(self, current_user_id: UUID) -> list[FeedRecord]:
        statement = (
            select(
                feeds,
                categories.c.id.label("category_id"),
                categories.c.slug.label("category_slug"),
                categories.c.name.label("category_name"),
                categories.c.sort_order.label("category_sort_order"),
                user_feed_subscriptions.c.enabled.label("subscription_enabled"),
                user_feed_subscriptions.c.user_priority.label("subscription_priority"),
            )
            .join(categories, categories.c.id == feeds.c.category_id)
            .outerjoin(
                user_feed_subscriptions,
                and_(
                    user_feed_subscriptions.c.feed_id == feeds.c.id,
                    user_feed_subscriptions.c.user_id == current_user_id,
                ),
            )
            .order_by(feeds.c.title.asc(), feeds.c.id.asc())
        )
        with self.engine.begin() as connection:
            rows = connection.execute(statement).mappings().all()
        return [_feed_from_row(row) for row in rows]

    def create_or_subscribe(
        self,
        feed_url: str,
        category_id: int,
        current_user_id: UUID,
    ) -> FeedMutation:
        with self.engine.begin() as connection:
            category = connection.execute(
                select(categories).where(categories.c.id == category_id)
            ).mappings().one_or_none()
            if category is None:
                raise KeyError(category_id)

            row = connection.execute(
                select(feeds).where(feeds.c.feed_url == feed_url)
            ).mappings().one_or_none()
            already_exists = row is not None
            if row is None:
                values = {
                    "feed_url": feed_url,
                    "title": feed_url,
                    "category_id": category_id,
                    "status": "active",
                    "added_by_user_id": current_user_id,
                }
                if self.engine.dialect.name == "postgresql":
                    row = (
                        connection.execute(
                            pg_insert(feeds)
                            .values(**values)
                            .on_conflict_do_nothing(index_elements=[feeds.c.feed_url])
                            .returning(feeds)
                        )
                        .mappings()
                        .one_or_none()
                    )
                else:
                    try:
                        row = (
                            connection.execute(feeds.insert().values(**values).returning(feeds))
                            .mappings()
                            .one()
                        )
                    except IntegrityError:
                        row = None

                if row is None:
                    row = (
                        connection.execute(select(feeds).where(feeds.c.feed_url == feed_url))
                        .mappings()
                        .one()
                    )
                    already_exists = True

            self._upsert_subscription(connection, int(row["id"]), current_user_id, enabled=True)
            feed = self._select_feed(connection, int(row["id"]), current_user_id)
        return FeedMutation(feed=feed, already_exists=already_exists)

    def subscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None:
        with self.engine.begin() as connection:
            if not self._feed_exists(connection, feed_id):
                return None
            self._upsert_subscription(connection, feed_id, current_user_id, enabled=True)
            return self._select_feed(connection, feed_id, current_user_id)

    def unsubscribe(self, feed_id: int, current_user_id: UUID) -> FeedRecord | None:
        with self.engine.begin() as connection:
            if not self._feed_exists(connection, feed_id):
                return None
            self._upsert_subscription(connection, feed_id, current_user_id, enabled=False)
            return self._select_feed(connection, feed_id, current_user_id)

    def set_priority(
        self,
        feed_id: int,
        current_user_id: UUID,
        user_priority: int,
    ) -> FeedRecord | None:
        with self.engine.begin() as connection:
            if not self._feed_exists(connection, feed_id):
                return None
            self._upsert_subscription(connection, feed_id, current_user_id, enabled=True)
            connection.execute(
                update(user_feed_subscriptions)
                .where(
                    user_feed_subscriptions.c.feed_id == feed_id,
                    user_feed_subscriptions.c.user_id == current_user_id,
                )
                .values(user_priority=user_priority, updated_at=datetime.now(UTC))
            )
            return self._select_feed(connection, feed_id, current_user_id)

    def dispose(self) -> None:
        self.engine.dispose()

    def _upsert_subscription(
        self,
        connection,
        feed_id: int,
        user_id: UUID,
        *,
        enabled: bool,
    ) -> None:
        now = datetime.now(UTC)
        values = {
            "user_id": user_id,
            "feed_id": feed_id,
            "enabled": enabled,
            "updated_at": now,
        }
        if self.engine.dialect.name == "postgresql":
            connection.execute(
                pg_insert(user_feed_subscriptions)
                .values(**values)
                .on_conflict_do_update(
                    index_elements=[
                        user_feed_subscriptions.c.user_id,
                        user_feed_subscriptions.c.feed_id,
                    ],
                    set_={"enabled": enabled, "updated_at": now},
                )
            )
            return

        existing = connection.execute(
            select(user_feed_subscriptions).where(
                user_feed_subscriptions.c.user_id == user_id,
                user_feed_subscriptions.c.feed_id == feed_id,
            )
        ).mappings().one_or_none()
        if existing is None:
            connection.execute(user_feed_subscriptions.insert().values(**values))
            return
        connection.execute(
            update(user_feed_subscriptions)
            .where(
                user_feed_subscriptions.c.user_id == user_id,
                user_feed_subscriptions.c.feed_id == feed_id,
            )
            .values(enabled=enabled, updated_at=now)
        )

    def _feed_exists(self, connection, feed_id: int) -> bool:
        return (
            connection.execute(select(feeds.c.id).where(feeds.c.id == feed_id))
            .scalar_one_or_none()
            is not None
        )

    def _select_feed(self, connection, feed_id: int, user_id: UUID) -> FeedRecord:
        statement = (
            select(
                feeds,
                categories.c.id.label("category_id"),
                categories.c.slug.label("category_slug"),
                categories.c.name.label("category_name"),
                categories.c.sort_order.label("category_sort_order"),
                user_feed_subscriptions.c.enabled.label("subscription_enabled"),
                user_feed_subscriptions.c.user_priority.label("subscription_priority"),
            )
            .join(categories, categories.c.id == feeds.c.category_id)
            .outerjoin(
                user_feed_subscriptions,
                and_(
                    user_feed_subscriptions.c.feed_id == feeds.c.id,
                    user_feed_subscriptions.c.user_id == user_id,
                ),
            )
            .where(feeds.c.id == feed_id)
        )
        row = connection.execute(statement).mappings().one()
        return _feed_from_row(row)


def create_feed_repository(database_url: str | None) -> FeedStore:
    if database_url:
        return DatabaseFeedRepository(database_url)
    return MemoryFeedRepository()


def _category_from_row(row) -> CategoryRecord:
    return CategoryRecord(
        id=row["id"],
        slug=row["slug"],
        name=row["name"],
        sort_order=row["sort_order"],
    )


def _feed_from_row(row) -> FeedRecord:
    return FeedRecord(
        id=row["id"],
        feed_url=row["feed_url"],
        canonical_url=row["canonical_url"],
        title=row["title"],
        category=CategoryRecord(
            id=row["category_id"],
            slug=row["category_slug"],
            name=row["category_name"],
            sort_order=row["category_sort_order"],
        ),
        status=row["status"],
        subscribed=bool(row["subscription_enabled"]),
        user_priority=int(row["subscription_priority"] or 0),
    )
