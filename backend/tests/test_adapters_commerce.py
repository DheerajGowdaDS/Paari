"""Tests for paari.adapters.commerce — Protocol and adapter selection."""

from __future__ import annotations

import pytest

from paari.adapters.commerce import CommerceAdapter, get_commerce_adapter
from paari.adapters.shopify_stub import ShopifyStubAdapter


def test_commerce_adapter_protocol_is_satisfied_by_stub() -> None:
    adapter = ShopifyStubAdapter()
    assert isinstance(adapter, CommerceAdapter)


def test_get_commerce_adapter_returns_stub_in_stub_mode() -> None:
    adapter = get_commerce_adapter()
    assert isinstance(adapter, ShopifyStubAdapter)
    assert adapter.source_label() == "fixture"


def test_stub_source_label() -> None:
    adapter = ShopifyStubAdapter()
    assert adapter.source_label() == "fixture"


def test_stub_search_products() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.search_products("sneaker", 5))
    assert result["source"] == "fixture"
    assert any(p["sku"] == "SKU-001" for p in result["products"])


def test_stub_get_product() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_product("SKU-001"))
    assert result["product"]["sku"] == "SKU-001"
    assert result["product"]["price_paise"] == 120000


def test_stub_get_product_not_found() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_product("NOPE"))
    assert result["error"] == "product_not_found"


def test_stub_get_inventory() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_inventory("SKU-001"))
    assert result["available"] == 12


def test_stub_get_price() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_price("SKU-001", 3))
    assert result["unit_price_paise"] == 120000
    assert result["total_paise"] == 360000


def test_stub_get_shipping_policy() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_shipping_policy())
    assert "shipping" in result["policy"].lower() or "Standard" in result["policy"]
    assert result["international_available"] is False


def test_stub_get_return_policy() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.get_return_policy())
    assert "30-day" in result["policy"]


def test_stub_request_quote() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.request_quote("SKU-001", 2, 10, "INR"))
    assert result["gross_paise"] == 240000
    assert result["discount_paise"] == 24000
    assert result["total_paise"] == 216000


def test_stub_request_payment() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.request_payment(120000, "INR"))
    assert result["state"] == "PENDING"
    assert result["amount_paise"] == 120000


def test_stub_confirm_order() -> None:
    adapter = ShopifyStubAdapter()
    import asyncio

    result = asyncio.run(adapter.confirm_order("tx-123", "q-456"))
    assert result["state"] == "confirmed"
    assert "MOCK-ORDER-" in result["order_id"]


def test_adapter_exceptions_importable() -> None:
    from paari.adapters.exceptions import (
        AdapterError,
        AdapterTimeout,
        AuthError,
        RateLimited,
        StoreNotFoundError,
    )

    assert issubclass(AdapterTimeout, AdapterError)
    assert issubclass(RateLimited, AdapterError)
    assert issubclass(AuthError, AdapterError)
    assert issubclass(StoreNotFoundError, AdapterError)
