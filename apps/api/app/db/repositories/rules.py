"""Per-user reader rules storage (JSON list of Rule dicts)."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Protocol
from uuid import UUID

from sqlalchemy import Engine, create_engine, select
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models import user_reader_rules
from app.domain.rules import Rule, rule_to_public, rules_from_payload, validate_rule


class RuleStore(Protocol):
    def get_rules(self, user_id: UUID) -> list[Rule]: ...

    def put_rules(self, user_id: UUID, rules: list[Rule]) -> list[Rule]: ...


class MemoryRuleRepository:
    def __init__(self) -> None:
        self._rules: dict[UUID, list[Rule]] = {}

    def get_rules(self, user_id: UUID) -> list[Rule]:
        return list(self._rules.get(user_id, []))

    def put_rules(self, user_id: UUID, rules: list[Rule]) -> list[Rule]:
        stored = [validate_rule(rule) for rule in rules]
        self._rules[user_id] = list(stored)
        return list(stored)


class DatabaseRuleRepository:
    def __init__(self, database_url: str, engine: Engine | None = None) -> None:
        self.engine = engine or create_engine(database_url, pool_pre_ping=True)

    def get_rules(self, user_id: UUID) -> list[Rule]:
        with self.engine.begin() as connection:
            row = (
                connection.execute(
                    select(user_reader_rules.c.rules).where(
                        user_reader_rules.c.user_id == user_id
                    )
                )
                .mappings()
                .one_or_none()
            )
        if row is None:
            return []
        return rules_from_payload(row["rules"] or [])

    def put_rules(self, user_id: UUID, rules: list[Rule]) -> list[Rule]:
        stored = [validate_rule(rule) for rule in rules]
        payload = [rule_to_public(rule) for rule in stored]
        now = datetime.now(UTC)
        with self.engine.begin() as connection:
            connection.execute(
                pg_insert(user_reader_rules)
                .values(
                    user_id=user_id,
                    rules=payload,
                    created_at=now,
                    updated_at=now,
                )
                .on_conflict_do_update(
                    index_elements=[user_reader_rules.c.user_id],
                    set_={
                        "rules": payload,
                        "updated_at": now,
                    },
                )
            )
        return stored

    def dispose(self) -> None:
        self.engine.dispose()


def create_rule_repository(database_url: str | None) -> RuleStore:
    if database_url:
        return DatabaseRuleRepository(database_url)
    return MemoryRuleRepository()
