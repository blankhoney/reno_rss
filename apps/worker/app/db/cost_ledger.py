"""Worker-side access to the shared daily LLM usage table."""

from __future__ import annotations

from datetime import UTC, date, datetime

from sqlalchemy import Engine, create_engine, text


ACCOUNTS = frozenset({"score", "ask", "agent"})


class DatabaseDailyUsageLedger:
    """Atomically reserve units without a check-then-write race."""

    def __init__(
        self,
        database_url: str | None = None,
        *,
        engine: Engine | None = None,
    ) -> None:
        if engine is None and database_url is None:
            raise ValueError("database_url or engine is required")
        self.engine = engine or create_engine(str(database_url), pool_pre_ping=True)

    def charge(
        self,
        account: str,
        units: int = 1,
        *,
        limit: int = 0,
        day: date | None = None,
    ) -> int:
        if account not in ACCOUNTS:
            raise ValueError(f"unknown account: {account}")
        if units < 0:
            raise ValueError("units must be non-negative")
        params = {
            "day": day or datetime.now(UTC).date(),
            "account": account,
            "units": units,
            "limit": max(0, int(limit)),
        }
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

    def dispose(self) -> None:
        self.engine.dispose()
