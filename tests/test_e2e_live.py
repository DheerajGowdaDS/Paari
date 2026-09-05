"""Tests for the live adapter e2e flow (runs in stub mode)."""

from __future__ import annotations

import pytest

from paari.adapters.commerce import get_commerce_adapter
from paari.tools.registry import REGISTRY, build_registry


def test_build_registry_with_stub_mode() -> None:
    """build_registry should work in stub mode (default)."""
    registry = build_registry()
    assert len(registry.names()) == 10
    assert "search_products" in registry.names()
    assert "confirm_order" in registry.names()


def test_registry_singleton_has_all_tools() -> None:
    """Module-level REGISTRY singleton should have all 10 tools."""
    expected = {
        "search_products",
        "get_product",
        "get_inventory",
        "get_price",
        "get_shipping_policy",
        "get_return_policy",
        "request_quote",
        "request_payment",
        "confirm_order",
        "get_order_status",
    }
    assert expected.issubset(set(REGISTRY.names()))


def test_adapter_source_label() -> None:
    adapter = get_commerce_adapter()
    assert adapter.source_label() in ("fixture", "shopify_live")


def test_stub_adapter_full_flow() -> None:
    """Run the full adapter flow: search -> get -> inventory -> price -> quote."""
    import asyncio

    adapter = get_commerce_adapter()

    # Search
    search_result = asyncio.run(adapter.search_products("shoe", 5))
    assert len(search_result["products"]) > 0

    # Get product
    sku = search_result["products"][0]["sku"]
    product_result = asyncio.run(adapter.get_product(sku))
    assert product_result["product"]["sku"] == sku

    # Inventory
    inv_result = asyncio.run(adapter.get_inventory(sku))
    assert "available" in inv_result

    # Price
    price_result = asyncio.run(adapter.get_price(sku, 2))
    assert price_result["total_paise"] > 0

    # Quote
    quote_result = asyncio.run(adapter.request_quote(sku, 1, 5, "INR"))
    assert quote_result["total_paise"] > 0
    assert quote_result["discount_pct"] == 5


def test_main_app_has_new_routes() -> None:
    """Verify the new routes are registered via OpenAPI schema."""
    from paari.main import app

    schema = app.openapi()
    paths = list(schema.get("paths", {}).keys())
    assert "/webhooks/shopify/{topic}" in paths
    assert "/api/v1/merchants/{merchant_id}/agent-card" in paths
    assert "/api/v1/health" in paths
