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




import pytest

@pytest.mark.asyncio
async def test_api_metrics_exposes_prometheus_text(client):
    response = await client.get("/api/metrics")
    assert response.status_code == 200
    body = response.text
    assert "ai_reader_up 1" in body
    assert "ai_reader_ask_calls_used" in body
