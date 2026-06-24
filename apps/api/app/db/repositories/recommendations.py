from collections.abc import Mapping
from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, desc, select

from app.db.models import recommendation_editions, recommendation_items


@dataclass(frozen=True)
class RecommendationItemRecord:
    rank: int
    article_id: int
    rank_score: float
    tier: str
    reason: str | None
    source: str


@dataclass(frozen=True)
class RecommendationEditionRecord:
    id: int
    user_id: UUID
    edition_type: str
    algorithm_version: str
    generated_at: datetime
    items: list[RecommendationItemRecord]


class RecommendationStore(Protocol):
    def save_edition(
        self,
        *,
        user_id: UUID | str,
        items: list[object],
        algorithm_version: str,
    ) -> RecommendationEditionRecord: ...

    def latest_for_user(self, user_id: UUID) -> RecommendationEditionRecord | None: ...


class MemoryRecommendationRepository:
    def __init__(self) -> None:
        self._editions: dict[int, RecommendationEditionRecord] = {}
        self._next_id = 1

    def save_edition(
        self,
        *,
        user_id: UUID | str,
        items: list[object],
        algorithm_version: str,
    ) -> RecommendationEditionRecord:
        edition_id = self._next_id
        self._next_id += 1
        edition = RecommendationEditionRecord(
            id=edition_id,
            user_id=UUID(str(user_id)),
            edition_type="homepage_top10",
            algorithm_version=algorithm_version,
            generated_at=datetime.now(UTC),
            items=[
                RecommendationItemRecord(
                    rank=int(_item_value(item, "rank")),
                    article_id=int(_item_value(item, "article_id")),
                    rank_score=float(_item_value(item, "rank_score")),
                    tier=str(_item_value(item, "tier")),
                    reason=_optional_item_str(item, "reason"),
                    source=str(_item_value(item, "source")),
                )
                for item in items
            ],
        )
        self._editions[edition.id] = edition
        return edition

    def latest_for_user(self, user_id: UUID) -> RecommendationEditionRecord | None:
        editions = [
            edition for edition in self._editions.values() if edition.user_id == user_id
        ]
        if not editions:
            return None
        return sorted(editions, key=lambda edition: edition.generated_at, reverse=True)[0]


class DatabaseRecommendationRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def save_edition(
        self,
        *,
        user_id: UUID | str,
        items: list[object],
        algorithm_version: str,
    ) -> RecommendationEditionRecord:
        with self.engine.begin() as connection:
            edition_row = (
                connection.execute(
                    recommendation_editions.insert()
                    .values(
                        user_id=UUID(str(user_id)),
                        edition_type="homepage_top10",
                        algorithm_version=algorithm_version,
                    )
                    .returning(recommendation_editions)
                )
                .mappings()
                .one()
            )
            item_rows = []
            for item in items:
                item_rows.append(
                    connection.execute(
                        recommendation_items.insert()
                        .values(
                            edition_id=edition_row["id"],
                            article_id=int(_item_value(item, "article_id")),
                            rank=int(_item_value(item, "rank")),
                            rank_score=float(_item_value(item, "rank_score")),
                            tier=str(_item_value(item, "tier")),
                            reason=_optional_item_str(item, "reason"),
                            source=str(_item_value(item, "source")),
                        )
                        .returning(recommendation_items)
                    )
                    .mappings()
                    .one()
                )
        return _edition_from_rows(edition_row, item_rows)

    def latest_for_user(self, user_id: UUID) -> RecommendationEditionRecord | None:
        with self.engine.begin() as connection:
            edition_row = (
                connection.execute(
                    select(recommendation_editions)
                    .where(recommendation_editions.c.user_id == user_id)
                    .order_by(desc(recommendation_editions.c.generated_at))
                    .limit(1)
                )
                .mappings()
                .one_or_none()
            )
            if edition_row is None:
                return None
            item_rows = (
                connection.execute(
                    select(recommendation_items)
                    .where(recommendation_items.c.edition_id == edition_row["id"])
                    .order_by(recommendation_items.c.rank.asc())
                )
                .mappings()
                .all()
            )
        return _edition_from_rows(edition_row, item_rows)

    def dispose(self) -> None:
        self.engine.dispose()


def create_recommendation_repository(database_url: str | None) -> RecommendationStore:
    if database_url:
        return DatabaseRecommendationRepository(database_url)
    return MemoryRecommendationRepository()


def _edition_from_rows(edition_row, item_rows) -> RecommendationEditionRecord:
    return RecommendationEditionRecord(
        id=edition_row["id"],
        user_id=edition_row["user_id"],
        edition_type=edition_row["edition_type"],
        algorithm_version=edition_row["algorithm_version"],
        generated_at=edition_row["generated_at"],
        items=[
            RecommendationItemRecord(
                rank=row["rank"],
                article_id=row["article_id"],
                rank_score=_float(row["rank_score"]),
                tier=row["tier"],
                reason=row["reason"],
                source=row["source"],
            )
            for row in item_rows
        ],
    )


def _float(value: object) -> float:
    return float(value) if isinstance(value, Decimal) else float(value)


def _item_value(item: object, key: str) -> object:
    if isinstance(item, Mapping):
        return item[key]
    return getattr(item, key)


def _optional_item_str(item: object, key: str) -> str | None:
    if isinstance(item, Mapping):
        value = item.get(key)
    else:
        value = getattr(item, key, None)
    return str(value) if value is not None else None
