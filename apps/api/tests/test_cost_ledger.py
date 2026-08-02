from datetime import date

import pytest
from sqlalchemy import create_engine
from sqlalchemy.pool import StaticPool

from app.domain.cost_ledger import CostLedger


def test_cost_ledger_charges_and_caps_per_account():
    ledger = CostLedger(limits={"score": 2, "ask": 1, "agent": 1, "translate": 1})
    day = date(2026, 7, 18)
    assert ledger.charge("score", 1, day=day) == 1
    assert ledger.charge("score", 1, day=day) == 2
    with pytest.raises(RuntimeError, match="score"):
        ledger.charge("score", 1, day=day)
    assert ledger.charge("translate", 1, day=day) == 1
    with pytest.raises(RuntimeError, match="translate"):
        ledger.charge("translate", 1, day=day)
    snap = ledger.snapshot(day=day)
    assert snap["accounts"]["score"]["used"] == 2
    assert snap["accounts"]["translate"]["used"] == 1
    assert snap["accounts"]["ask"]["remaining"] == 1


def test_database_cost_ledger_persists_usage_across_instances():
    from app.db.models import llm_daily_usage
    from app.db.repositories.cost_ledger import DatabaseCostLedger

    engine = create_engine(
        "sqlite+pysqlite:///:memory:",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    llm_daily_usage.create(engine)
    day = date(2026, 7, 18)
    limits = {"score": 2, "ask": 1, "agent": 1, "translate": 1}

    first = DatabaseCostLedger(limits=limits, engine=engine)
    second = DatabaseCostLedger(limits=limits, engine=engine)

    assert first.charge("ask", day=day) == 1
    assert second.used("ask", day=day) == 1
    with pytest.raises(RuntimeError, match="ask"):
        second.charge("ask", day=day)
    assert first.charge("translate", day=day) == 1
    with pytest.raises(RuntimeError, match="translate"):
        second.charge("translate", day=day)
    assert first.snapshot(day=day)["accounting"] == "database"
