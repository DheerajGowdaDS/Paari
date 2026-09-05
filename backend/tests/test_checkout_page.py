"""Tests for Checkout Page and API.

NOTE: These are integration tests that require a properly configured database.
They are skipped by default. To run them, use a test database fixture.
"""

from __future__ import annotations

import pytest


@pytest.mark.skip(reason="Integration test - requires database fixture")
class TestCheckoutPageEndpoint:
    """Test GET /checkout/{transaction_id}."""

    def test_checkout_returns_html(self):
        from fastapi.testclient import TestClient
        from paari.main import app

        client = TestClient(app)
        response = client.get("/checkout/TXN-123")

        assert response.status_code == 200
        assert "text/html" in response.headers.get("content-type", "")


@pytest.mark.skip(reason="Integration test - requires database fixture")
class TestCreateCheckoutOrderEndpoint:
    """Test POST /checkout/{transaction_id}/order."""

    def test_create_order_returns_order_details(self):
        from fastapi.testclient import TestClient
        from paari.main import app

        client = TestClient(app)
        response = client.post(
            "/checkout/tx-123/order",
            json={"session_id": "ps-123"},
        )

        assert response.status_code == 200
        data = response.json()
        assert "order_id" in data
