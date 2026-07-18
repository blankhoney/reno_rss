from datetime import date

import pytest

from app.domain.cost_ledger import CostLedger


def test_cost_ledger_charges_and_caps_per_account():
    ledger = CostLedger(limits={"score": 2, "ask": 1, "agent": 1})
    day = date(2026, 7, 18)
    assert ledger.charge("score", 1, day=day) == 1
    assert ledger.charge("score", 1, day=day) == 2
    with pytest.raises(RuntimeError, match="score"):
        ledger.charge("score", 1, day=day)
    snap = ledger.snapshot(day=day)
    assert snap["accounts"]["score"]["used"] == 2
    assert snap["accounts"]["ask"]["remaining"] == 1
