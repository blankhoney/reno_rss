"""Per-user saved list filters (name, q, module, sort). Same dual store pattern as rules."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import user_saved_searches


@dataclass(frozen=True)
class SavedSearchRecord:
    id: int
    name: str
    q: str
    module: str
    sort: str


class SavedSearchStore(Protocol):
    def list_for_user(self, user_id: UUID) -> list[SavedSearchRecord]: ...

    def replace_for_user(
        self,
        user_id: UUID,
        items: list[dict[str, str]],
    ) -> list[SavedSearchRecord]: ...


class MemorySavedSearchRepository:
    def __init__(self) -> None:
        self._by_user: dict[UUID, list[SavedSearchRecord]] = {}
        self._next_id = 1

    def list_for_user(self, user_id: UUID) -> list[SavedSearchRecord]:
        return list(self._by_user.get(user_id, []))

    def replace_for_user(
        self,
        user_id: UUID,
        items: list[dict[str, str]],
    ) -> list[SavedSearchRecord]:
        records: list[SavedSearchRecord] = []
        for item in items:
            records.append(
                SavedSearchRecord(
                    id=self._next_id,
                    name=item["name"],
                    q=item.get("q", ""),
                    module=item.get("module", "all"),
                    sort=item.get("sort", "published_desc"),
                )
            )
            self._next_id += 1
        self._by_user[user_id] = records
        return list(records)


class DatabaseSavedSearchRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def list_for_user(self, user_id: UUID) -> list[SavedSearchRecord]:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(user_saved_searches.c.items).where(
                        user_saved_searches.c.user_id == user_id
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return []
        return _records_from_payload(row["items"] or [])

    def replace_for_user(
        self,
        user_id: UUID,
        items: list[dict[str, str]],
    ) -> list[SavedSearchRecord]:
        records = _records_from_payload(items, assign_ids=True)
        payload = [
            {
                "id": record.id,
                "name": record.name,
                "q": record.q,
                "module": record.module,
                "sort": record.sort,
            }
            for record in records
        ]
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                pg_insert(user_saved_searches)
                .values(
                    user_id=user_id,
                    items=payload,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[user_saved_searches.c.user_id],
                    set_={
                        "items": payload,
                        "updated_at": now,
                    },
                )
            )
        return records

    def dispose(self) -> None:
        self.engine.dispose()


def create_saved_search_repository(database_url: str | None) -> SavedSearchStore:
    if database_url:
        return DatabaseSavedSearchRepository(database_url)
    return MemorySavedSearchRepository()


def _records_from_payload(
    raw_items: list[object] | list[dict[str, str]],
    *,
    assign_ids: bool = False,
) -> list[SavedSearchRecord]:
    records: list[SavedSearchRecord] = []
    for index, item in enumerate(raw_items, start=1):
        if not isinstance(item, dict):
            continue
        name = str(item.get("name") or "").strip()
        if not name:
            continue
        raw_id = item.get("id")
        try:
            item_id = int(raw_id) if raw_id is not None else index
        except (TypeError, ValueError):
            item_id = index
        if assign_ids and raw_id is None:
            item_id = index
        records.append(
            SavedSearchRecord(
                id=item_id,
                name=name,
                q=str(item.get("q") or ""),
                module=str(item.get("module") or "all"),
                sort=str(item.get("sort") or "published_desc"),
            )
        )
    return records
