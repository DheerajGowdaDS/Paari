"""Step 8 validation: tool registry and stub adapters."""

from __future__ import annotations

import pytest

from paari.schemas.capability import Capability
from paari.schemas.tool_inputs import (
    GetInventoryInput,
    GetPriceInput,
    GetProductInput,
    SearchProductsInput,
)
from paari.tools.adapters.razorpay_stub import build_verified_event, verify_webhook_signature
from paari.tools.adapters.shopify_stub import get_inventory, get_price, get_product, search_products
from paari.tools.registry import REGISTRY


def test_registry_has_all_tools() -> None:
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


def test_tools_for_capabilities_filters() -> None:
    tools = REGISTRY.tools_for([Capability.CATALOG_READ.value])
    names = {t.name for t in tools}
    assert "search_products" in names
    assert "get_price" in names
    assert "get_product" not in names  # needs product.read
    assert "request_payment" not in names  # needs payment.request


def test_request_payment_requires_payment_capability() -> None:
    tool = REGISTRY.get("request_payment")
    assert tool.required_capability == Capability.PAYMENT_REQUEST
    assert tool.risk_level.value == "HIGH"


def test_unknown_tool_raises() -> None:
    with pytest.raises(KeyError):
        REGISTRY.get("does_not_exist")


def test_get_product_returns_fixture() -> None:
    result = get_product(GetProductInput(sku="SKU-001"), "merchant-demo-001")
    assert result["source"] == "fixture"
    assert result["product"]["sku"] == "SKU-001"
    assert result["product"]["price_paise"] == 120000
    assert "fetched_at" in result


def test_get_product_unknown_sku() -> None:
    result = get_product(GetProductInput(sku="NOPE"), "merchant-demo-001")
    assert result["error"] == "product_not_found"


def test_get_inventory() -> None:
    result = get_inventory(GetInventoryInput(sku="SKU-001"), "merchant-demo-001")
    assert result["available"] == 12


def test_get_price_total() -> None:
    result = get_price(GetPriceInput(sku="SKU-001", quantity=2), "merchant-demo-001")
    assert result["total_paise"] == 240000


def test_search_products() -> None:
    result = search_products(SearchProductsInput(query="sneaker"), "merchant-demo-001")
    assert any(p["sku"] == "SKU-001" for p in result["products"])


def test_webhook_signature_round_trip() -> None:
    event = build_verified_event("tx-1", 120000)
    sig = event.pop("signature")
    assert verify_webhook_signature(event, sig)
    # Tampered signature fails.
    assert not verify_webhook_signature(event, "badsig")
