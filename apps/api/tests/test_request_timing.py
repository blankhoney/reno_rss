import asyncio
import logging

import pytest
from httpx import ASGITransport, AsyncClient

from app.core.request_timing import LOGGER
from app.main import create_app


pytestmark = pytest.mark.asyncio


def _timing_records(caplog):
    return [record for record in caplog.records if record.name == LOGGER.name]


async def test_request_timing_logs_requests_without_query_string(monkeypatch, caplog):
    monkeypatch.setenv("SLOW_REQUEST_MS", "100000")
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/auth/me?token=secret")

    assert response.status_code == 401
    records = _timing_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert "method=GET" in records[0].getMessage()
    assert "path=/api/auth/me" in records[0].getMessage()
    assert "status=401" in records[0].getMessage()
    assert "token=secret" not in records[0].getMessage()


async def test_request_timing_warns_for_slow_requests(monkeypatch, caplog):
    monkeypatch.setenv("SLOW_REQUEST_MS", "1")
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    app = create_app()

    @app.get("/api/test-slow")
    async def slow_route() -> dict[str, bool]:
        await asyncio.sleep(0.01)
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/test-slow")

    assert response.status_code == 200
    records = _timing_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.WARNING
    assert "path=/api/test-slow" in records[0].getMessage()
    assert "status=200" in records[0].getMessage()


async def test_request_timing_skips_healthz(monkeypatch, caplog):
    monkeypatch.setenv("SLOW_REQUEST_MS", "1")
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    app = create_app()

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        health = await client.get("/healthz")
        api_health = await client.get("/api/healthz")

    assert health.status_code == 200
    assert api_health.status_code == 200
    assert _timing_records(caplog) == []


async def test_request_timing_zero_threshold_disables_slow_warnings(monkeypatch, caplog):
    monkeypatch.setenv("SLOW_REQUEST_MS", "0")
    caplog.set_level(logging.INFO, logger=LOGGER.name)
    app = create_app()

    @app.get("/api/test-slow-disabled")
    async def slow_route() -> dict[str, bool]:
        await asyncio.sleep(0.01)
        return {"ok": True}

    async with AsyncClient(transport=ASGITransport(app=app), base_url="https://test") as client:
        response = await client.get("/api/test-slow-disabled")

    assert response.status_code == 200
    records = _timing_records(caplog)
    assert len(records) == 1
    assert records[0].levelno == logging.INFO
    assert "path=/api/test-slow-disabled" in records[0].getMessage()
