from datetime import date

import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.pool import StaticPool

from app.db.cost_ledger import DatabaseDailyUsageLedger


def test_database_daily_usage_ledger_is_shared_and_atomic():
    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    with engine.begin() as connection:
        connection.execute(
            text(
                """
                CREATE TABLE llm_daily_usage (
                  day DATE NOT NULL,
                  account TEXT NOT NULL,
                  used INTEGER NOT NULL DEFAULT 0,
                  updated_at TIMESTAMP,
                  PRIMARY KEY (day, account)
                )
                """
            )
        )
    day = date(2026, 7, 18)
    first = DatabaseDailyUsageLedger(engine=engine)
    second = DatabaseDailyUsageLedger(engine=engine)

    assert first.charge("agent", limit=1, day=day) == 1
    with pytest.raises(RuntimeError, match="agent"):
        second.charge("agent", limit=1, day=day)
