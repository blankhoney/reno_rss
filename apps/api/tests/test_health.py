import re

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import create_app


@pytest.mark.parametrize("path", ["/healthz", "/api/healthz"])
@pytest.mark.asyncio
async def test_healthz_returns_public_status(path):
    app = create_app()
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as client:
        response = await client.get(path)

    assert response.status_code == 200
    assert response.json()["ok"] is True
    assert "version" in response.json()

@pytest.mark.asyncio
async def test_api_metrics_exposes_prometheus_text(app, client):
    app.state.job_repository.enqueue(
        "sync_miniflux_entries",
        {"limit": 10},
        dedupe_key=None,
    )
    await client.get("/api/auth/me")
    response = await client.get("/api/metrics")
    assert response.status_code == 200
    body = response.text
    assert "ai_reader_up 1" in body
    assert 'ai_reader_llm_calls_used{account="ask"}' in body
    assert 'ai_reader_llm_calls_limit{account="agent"}' in body
    assert "ai_reader_http_request_duration_seconds_count" in body
    assert "ai_reader_http_errors_total" in body
    assert "ai_reader_http_error_ratio" in body
    assert "ai_reader_job_queue_queued 1" in body
    assert "ai_reader_job_failures_24h 0" in body
    assert "ai_reader_scheduler_enabled 1" in body
    assert re.search(r"ai_reader_http_requests_total [1-9]", body)
