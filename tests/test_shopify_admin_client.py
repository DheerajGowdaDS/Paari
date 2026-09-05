"""Tests for paari.shopify_admin.client — Shopify Admin GraphQL client."""

from __future__ import annotations

import pytest


def test_queries_module_importable() -> None:
    from paari.shopify_admin.queries import (
        COMPLETE_DRAFT_ORDER,
        CREATE_DRAFT_ORDER,
        CREATE_WEBHOOK_SUBSCRIPTION,
        DELETE_WEBHOOK_SUBSCRIPTION,
        GET_INVENTORY_LEVELS,
        GET_PAGES,
        GET_PRODUCT_BY_SKU,
        GET_VARIANT_PRICE,
        SEARCH_PRODUCTS,
    )

    assert "query" in SEARCH_PRODUCTS.lower() or "mutation" in SEARCH_PRODUCTS.lower()
    assert "query" in GET_INVENTORY_LEVELS.lower()
    assert "mutation" in CREATE_DRAFT_ORDER.lower()
    assert "mutation" in COMPLETE_DRAFT_ORDER.lower()
    assert "mutation" in CREATE_WEBHOOK_SUBSCRIPTION.lower()
    assert "mutation" in DELETE_WEBHOOK_SUBSCRIPTION.lower()


def test_queries_are_valid_graphql_strings() -> None:
    """All query strings should start with query or mutation."""
    from paari.shopify_admin.queries import (
        COMPLETE_DRAFT_ORDER,
        CREATE_DRAFT_ORDER,
        CREATE_WEBHOOK_SUBSCRIPTION,
        DELETE_WEBHOOK_SUBSCRIPTION,
        GET_INVENTORY_LEVELS,
        GET_PAGES,
        GET_PRODUCT_BY_SKU,
        GET_VARIANT_PRICE,
        SEARCH_PRODUCTS,
    )

    for q in [
        SEARCH_PRODUCTS,
        GET_PRODUCT_BY_SKU,
        GET_INVENTORY_LEVELS,
        GET_VARIANT_PRICE,
        CREATE_DRAFT_ORDER,
        COMPLETE_DRAFT_ORDER,
        CREATE_WEBHOOK_SUBSCRIPTION,
        DELETE_WEBHOOK_SUBSCRIPTION,
        GET_PAGES,
    ]:
        stripped = q.strip()
        assert stripped.startswith("query") or stripped.startswith("mutation"), (
            f"Query should start with 'query' or 'mutation': {stripped[:50]}"
        )


def test_admin_client_module_importable() -> None:
    from paari.shopify_admin.client import ShopifyAdminClient

    assert ShopifyAdminClient is not None


def test_webhooks_module_importable() -> None:
    from paari.shopify_admin.webhooks import register_webhooks

    assert callable(register_webhooks)
