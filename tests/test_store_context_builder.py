"""Tests for paari.store_context — builder, cache, normalizer."""

from __future__ import annotations

import pytest


def test_normalizer_normalize_product() -> None:
    from paari.store_context.normalizer import normalize_product

    shopify_product = {
        "id": "gid://shopify/Product/123",
        "title": "Test Shoe",
        "description": "A test shoe",
        "productType": "Footwear",
        "tags": ["shoe", "test"],
        "variants": {
            "edges": [
                {
                    "node": {
                        "id": "gid://shopify/ProductVariant/456",
                        "sku": "TEST-001",
                        "price": "1200.00",
                        "inventoryQuantity": 10,
                    }
                }
            ]
        },
    }
    result = normalize_product(shopify_product)
    assert result["sku"] == "TEST-001"
    assert result["title"] == "Test Shoe"
    assert result["price_paise"] == 120000
    assert result["currency"] == "INR"
    assert len(result["variants"]) == 1
    assert result["variants"][0]["variant_id"] == "gid://shopify/ProductVariant/456"


def test_normalizer_normalize_catalog() -> None:
    from paari.store_context.normalizer import normalize_catalog

    products = [
        {
            "id": "gid://shopify/Product/1",
            "title": "Shoe A",
            "description": "",
            "productType": "",
            "tags": [],
            "variants": {
                "edges": [
                    {
                        "node": {
                            "id": "gid://shopify/ProductVariant/1",
                            "sku": "A-001",
                            "price": "100.00",
                            "inventoryQuantity": 5,
                        }
                    }
                ]
            },
        }
    ]
    catalog = normalize_catalog(products)
    assert catalog["product_count"] == 1
    assert "A-001" in catalog["sku_index"]
    assert catalog["sku_index"]["A-001"]["price"] == 10000


def test_normalizer_normalize_policies_dict() -> None:
    from paari.store_context.normalizer import normalize_policies

    policies = {
        "shipping": {"international": True, "free_threshold_paise": 500000, "estimate_days": "3-5 days"},
        "returns": {"window_days": 15, "conditions": "Unworn only"},
    }
    result = normalize_policies(policies)
    assert result["shipping"]["international"] is True
    assert result["shipping"]["free_threshold_paise"] == 500000
    assert result["returns"]["window_days"] == 15


def test_normalizer_normalize_policies_string() -> None:
    from paari.store_context.normalizer import normalize_policies

    policies = {
        "shipping_policy": "Free shipping on orders above ₹5000. 5-7 day delivery.",
        "return_policy": "15-day returns on all items.",
    }
    result = normalize_policies(policies)
    assert result["shipping"]["international"] is False
    assert result["shipping"]["free_threshold_paise"] == 500000
    assert result["returns"]["window_days"] == 15


def test_normalizer_shopify_price_to_paise() -> None:
    from paari.store_context.normalizer import _shopify_price_to_paise

    assert _shopify_price_to_paise("1200.00") == 120000
    assert _shopify_price_to_paise("0.00") == 0
    assert _shopify_price_to_paise("invalid") == 0


def test_cache_get_returns_none_when_empty() -> None:
    from paari.store_context import cache as ctx_cache

    result = ctx_cache.get_cached("nonexistent-merchant")
    assert result is None


def test_cache_set_and_get() -> None:
    from paari.store_context import cache as ctx_cache

    ctx_cache.set_cached("test-cache-merchant", {"products": []}, "fixture")
    result = ctx_cache.get_cached("test-cache-merchant")
    assert result is not None
    assert result["payload"]["products"] == []
    assert result["source"] == "fixture"
    # Clean up
    ctx_cache.invalidate("test-cache-merchant")


def test_cache_invalidate() -> None:
    from paari.store_context import cache as ctx_cache

    ctx_cache.set_cached("invalidate-test", {"data": 1}, "fixture")
    ctx_cache.invalidate("invalidate-test")
    assert ctx_cache.get_cached("invalidate-test") is None


def test_cache_invalidate_all() -> None:
    from paari.store_context import cache as ctx_cache

    ctx_cache.set_cached("inv-all-1", {"data": 1}, "fixture")
    ctx_cache.set_cached("inv-all-2", {"data": 2}, "fixture")
    ctx_cache.invalidate()
    assert ctx_cache.get_cached("inv-all-1") is None
    assert ctx_cache.get_cached("inv-all-2") is None


def test_store_context_builder_importable() -> None:
    from paari.store_context.builder import StoreContextBuilder, get_store_context

    builder = get_store_context()
    assert isinstance(builder, StoreContextBuilder)
