"""
Smoke test for GET /api/health.

Mocks out the DB/MinIO connectivity checks so this test runs with no real
Postgres or MinIO available -- appropriate for Day 1, before those checks
have real infrastructure behind them in CI.
"""
from unittest.mock import AsyncMock, patch

import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.asyncio
async def test_health_ok_when_dependencies_up():
    with patch("app.api.health.check_database_connection", new=AsyncMock(return_value=True)), \
         patch("app.api.health.check_minio_connection", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "ok"
    assert body["dependencies"] == {"database": True, "minio": True}


@pytest.mark.asyncio
async def test_health_degraded_when_a_dependency_is_down():
    with patch("app.api.health.check_database_connection", new=AsyncMock(return_value=False)), \
         patch("app.api.health.check_minio_connection", return_value=True):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            response = await client.get("/api/health")

    assert response.status_code == 503
    body = response.json()
    assert body["status"] == "degraded"
    assert body["dependencies"]["database"] is False
