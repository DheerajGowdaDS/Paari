"""Tests for paari.api.discovery — agent card endpoint."""

from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from paari.main import app


@pytest.mark.asyncio
async def test_agent_card_endpoint_exists() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/merchants/nonexistent/agent-card")
        assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_card_returns_404_for_missing_merchant() -> None:
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/api/v1/merchants/DOES-NOT-EXIST/agent-card")
        assert response.status_code == 404
        data = response.json()
        assert "detail" in data


def test_discovery_module_importable() -> None:
    from paari.api.discovery import router

    assert router is not None
