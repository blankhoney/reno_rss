"""Database-backed atomic daily LLM budget ledger."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Engine, create_engine, select, text

from app.db.models import llm_daily_usage
from app.domain.cost_ledger import ACCOUNTS, CostLedger


class DatabaseCostLedger:
    """Reserve daily units with one atomic upsert shared across API processes."""

    def __init__(
        self,
        *,
        limits: dict[str, int],
        database_url: str | None = None,
        engine: Engine | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)
        self.limits = {account: int(limits.get(account, 0)) for account in ACCOUNTS}

    def _day(self, day: date | None = None) -> date:
        return day or datetime.now(UTC).date()

    def used(self, account: str, *, day: date | None = None) -> int:
        _validate_account(account)
        with self.engine.begin() as connection:
            value = connection.execute(
                select(llm_daily_usage.c.used).where(
                    llm_daily_usage.c.day == self._day(day),
                    llm_daily_usage.c.account == account,
                )
            ).scalar_one_or_none()
        return int(value or 0)

    def remaining(self, account: str, *, day: date | None = None) -> int:
        _validate_account(account)
        limit = int(self.limits.get(account, 0))
        if limit <= 0:
            return 10**9
        return max(0, limit - self.used(account, day=day))

    def can_charge(self, account: str, units: int = 1, *, day: date | None = None) -> bool:
        _validate_account(account)
        if units < 0:
            raise ValueError("units must be non-negative")
        limit = int(self.limits.get(account, 0))
        return limit <= 0 or self.used(account, day=day) + units <= limit

    def charge(self, account: str, units: int = 1, *, day: date | None = None) -> int:
        _validate_account(account)
        if units < 0:
            raise ValueError("units must be non-negative")
        limit = int(self.limits.get(account, 0))
        params = {
            "day": self._day(day),
            "account": account,
            "units": units,
            "limit": limit,
        }
        # INSERT .. SELECT handles a first charge larger than the cap; the
        # conflict WHERE handles subsequent charges. RETURNING distinguishes a
        # reservation from an exhausted cap without a check-then-write race.
        statement = text(
            """
            INSERT INTO llm_daily_usage (day, account, used, updated_at)
            SELECT :day, :account, :units, CURRENT_TIMESTAMP
            WHERE :limit <= 0 OR :units <= :limit
            ON CONFLICT (day, account) DO UPDATE
              SET used = llm_daily_usage.used + excluded.used,
                  updated_at = CURRENT_TIMESTAMP
              WHERE :limit <= 0
                 OR llm_daily_usage.used + excluded.used <= :limit
            RETURNING used
            """
        )
        with self.engine.begin() as connection:
            used = connection.execute(statement, params).scalar_one_or_none()
        if used is None:
            raise RuntimeError(f"daily budget exceeded for {account}")
        return int(used)

    def snapshot(self, *, day: date | None = None) -> dict[str, object]:
        target_day = self._day(day)
        accounts: dict[str, object] = {}
        for account in ACCOUNTS:
            limit = int(self.limits.get(account, 0))
            used = self.used(account, day=target_day)
            accounts[account] = {
                "used": used,
                "limit": limit,
                "remaining": max(0, limit - used) if limit > 0 else None,
            }
        return {
            "day": target_day.isoformat(),
            "accounts": accounts,
            "accounting": "database",
        }

    def dispose(self) -> None:
        self.engine.dispose()


def create_cost_ledger(
    database_url: str | None,
    *,
    limits: dict[str, int],
) -> CostLedger | DatabaseCostLedger:
    if database_url:
        return DatabaseCostLedger(database_url=database_url, limits=limits)
    return CostLedger(limits=limits)


def _validate_account(account: str) -> None:
    if account not in ACCOUNTS:
        raise ValueError(f"unknown account: {account}")
