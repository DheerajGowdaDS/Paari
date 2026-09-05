"""Tests for paari.shopify_storefront — MCP client wrapper."""

from __future__ import annotations

import pytest


def test_client_module_importable() -> None:
    from paari.shopify_storefront.client import ShopifyStorefrontClient

    assert ShopifyStorefrontClient is not None


def test_tools_module_importable() -> None:
    from paari.shopify_storefront.tools import (
        get_product,
        search_shop_catalog,
        search_shop_policies_and_faqs,
    )

    assert callable(search_shop_catalog)
    assert callable(get_product)
    assert callable(search_shop_policies_and_faqs)


def test_storefront_package_init() -> None:
    import paari.shopify_storefront

    assert hasattr(paari.shopify_storefront, "ShopifyStorefrontClient")
