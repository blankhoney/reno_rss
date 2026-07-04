from datetime import UTC, datetime, timedelta

import pytest


class RecordingAskProvider:
    spends_llm_budget = True

    def __init__(self) -> None:
        self.calls = 0

    def answer_article_question(self, messages):
        self.calls += 1
        return ["real answer"]


def test_daily_call_budget_resets_on_utc_day_boundary():
    from app.core.budget import DailyCallBudget

    now = datetime(2026, 7, 4, 23, 59, tzinfo=UTC)
    budget = DailyCallBudget(1, clock=lambda: now)

    assert budget.try_consume() is True
    assert budget.try_consume() is False
    assert budget.remaining() == 0

    now += timedelta(minutes=2)

    assert budget.remaining() == 1
    assert budget.try_consume() is True


def test_zero_daily_call_budget_means_unlimited():
    from app.core.budget import DailyCallBudget

    budget = DailyCallBudget(0)

    assert budget.remaining() is None
    for _index in range(10):
        assert budget.try_consume() is True


@pytest.mark.asyncio
async def test_ask_budget_exhaustion_degrades_without_calling_provider(app, client):
    from app.core.budget import DailyCallBudget

    provider = RecordingAskProvider()
    app.state.ask_provider = provider
    app.state.llm_budget = DailyCallBudget(1)
    await client.post("/api/auth/login", json={"display_name": "Blank"})
    article = app.state.article_repository.upsert_from_source(
        {
            "feed_id": 1,
            "miniflux_entry_id": 101,
            "url": "https://example.com/post",
            "title": "Budgeted Article",
            "content_text": "Enough context for an ask response.",
        }
    )

    first = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})
    second = await client.post(f"/api/articles/{article.id}/ask", json={"question": "总结"})

    assert first.status_code == 200
    assert "real answer" in first.text
    assert second.status_code == 200
    assert "今日 LLM 调用额度已用满" in second.text
    assert provider.calls == 1
