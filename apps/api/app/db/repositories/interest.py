"""Durable personalization reset watermarks.

Resetting interest does not delete private reading data. Instead, this store
records the point after which new highlights, feedback, and article-state
interactions are allowed to rebuild the user's interest profile.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import user_interest_resets


class InterestResetStore(Protocol):
    def get_reset_at(self, user_id: UUID) -> datetime | None: ...

    def set_reset_at(self, user_id: UUID, reset_at: datetime) -> None: ...


class MemoryInterestResetRepository:
    """Process-local fallback used only when no database is configured."""

    def __init__(self) -> None:
        self._reset_at_by_user: dict[UUID, datetime] = {}

    def get_reset_at(self, user_id: UUID) -> datetime | None:
        return self._reset_at_by_user.get(user_id)

    def set_reset_at(self, user_id: UUID, reset_at: datetime) -> None:
        self._reset_at_by_user[user_id] = _as_utc(reset_at)


class DatabaseInterestResetRepository:
    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def get_reset_at(self, user_id: UUID) -> datetime | None:
        with self.engine.begin() as connection:
            value = connection.execute(
                select(user_interest_resets.c.reset_at).where(
                    user_interest_resets.c.user_id == user_id
                )
            ).scalar_one_or_none()
        return _as_utc(value) if value is not None else None

    def set_reset_at(self, user_id: UUID, reset_at: datetime) -> None:
        normalized = _as_utc(reset_at)
        values = {
            "user_id": user_id,
            "reset_at": normalized,
            "updated_at": normalized,
        }
        with self.engine.begin() as connection:
            if self.engine.dialect.name == "postgresql":
                connection.execute(
                    pg_insert(user_interest_resets)
                    .values(**values)
                    .on_conflict_do_update(
                        index_elements=[user_interest_resets.c.user_id],
                        set_={
                            "reset_at": normalized,
                            "updated_at": normalized,
                        },
                    )
                )
                return
            existing = connection.execute(
                select(user_interest_resets.c.user_id).where(
                    user_interest_resets.c.user_id == user_id
                )
            ).scalar_one_or_none()
            if existing is None:
                connection.execute(user_interest_resets.insert().values(**values))
            else:
                connection.execute(
                    user_interest_resets.update()
                    .where(user_interest_resets.c.user_id == user_id)
                    .values(reset_at=normalized, updated_at=normalized)
                )

    def dispose(self) -> None:
        self.engine.dispose()


def create_interest_reset_repository(database_url: str | None) -> InterestResetStore:
    if database_url:
        return DatabaseInterestResetRepository(database_url)
    return MemoryInterestResetRepository()


def _as_utc(value: datetime) -> datetime:
    return value.astimezone(UTC) if value.tzinfo else value.replace(tzinfo=UTC)
