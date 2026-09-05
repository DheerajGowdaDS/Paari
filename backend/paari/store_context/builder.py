"""Store context builder.

Runs at startup and on a 15-minute timer. Fetches live catalog + policies
from Shopify, normalizes, and caches in both in-process cache and DB.
"""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import UTC, datetime
from typing import Any

from paari.store_context import cache as ctx_cache
from paari.store_context.normalizer import normalize_catalog, normalize_policies

_log = logging.getLogger("paari.store_context")


class StoreContextBuilder:
    """Fetches and normalizes Shopify store context for a merchant."""

    def __init__(self) -> None:
        self._task: asyncio.Task | None = None

    async def fetch_and_cache(self, merchant_id: str) -> dict[str, Any]:
        """Fetch live catalog + policies and cache them.

        Returns the normalized context payload.
        """
        # Check cache first
        cached = ctx_cache.get_cached(merchant_id)
        if cached is not None:
            return cached["payload"]

        # Try DB next
        db_entry = await ctx_cache.load_from_db(merchant_id)
        if db_entry is not None:
            ctx_cache.set_cached(merchant_id, db_entry["payload"], db_entry["source"])
            return db_entry["payload"]

        # Fetch live from Shopify
        payload = await self._fetch_live(merchant_id)

        # Persist and cache
        await ctx_cache.persist_to_db(merchant_id, payload, "STOREFRONT_MCP")
        ctx_cache.set_cached(merchant_id, payload, "STOREFRONT_MCP")

        return payload

    async def _fetch_live(self, merchant_id: str) -> dict[str, Any]:
        """Fetch catalog + policies from live Shopify.

        Prefers Storefront MCP; falls back to Admin GraphQL when MCP is
        unavailable (private endpoint, missing mcp package, etc.). The
        fallback is what actually feeds the SKU index that get_price and
        get_inventory depend on at tool-execution time.
        """
        from paari.config import settings

        catalog_payload: dict[str, Any] = {"products": [], "sku_index": {}, "product_count": 0}
        policy_payload: dict[str, Any] = {
            "shipping": {
                "international": False,
                "free_threshold_paise": 0,
                "estimate_days": "5-7 business days",
            },
            "returns": {"window_days": 30, "conditions": "Unworn items with original tags"},
        }
        source = "admin_graphql"

        if settings.shopify_mode == "live":
            # ── Try Storefront MCP first ──────────────────────────────
            try:
                from paari.shopify_storefront.client import ShopifyStorefrontClient

                client = ShopifyStorefrontClient()
                try:
                    raw_products = await client.search_catalog("", limit=50)
                    if raw_products:
                        catalog_payload = normalize_catalog(raw_products)
                        source = "storefront_mcp"
                except Exception as e:
                    _log.warning("Storefront MCP catalog fetch failed: %s", e)

                try:
                    raw_policies = await client.search_policies("policies")
                    if raw_policies:
                        policy_payload = normalize_policies(raw_policies)
                except Exception as e:
                    _log.warning("Storefront MCP policy fetch failed: %s", e)

                await client.close()
            except Exception as e:
                _log.error("Failed to init Storefront client: %s", e)

            # ── Fallback: Admin GraphQL for catalog ───────────────────
            if not catalog_payload.get("products"):
                try:
                    from paari.shopify_admin.client import ShopifyAdminClient
                    from paari.shopify_admin.queries import SEARCH_PRODUCTS

                    admin = ShopifyAdminClient()
                    try:
                        raw = await admin.execute(SEARCH_PRODUCTS, {"query": "", "first": 50})
                        edges = raw.get("products", {}).get("edges", [])
                        if edges:
                            catalog_payload = normalize_catalog(
                                [e["node"] for e in edges]
                            )
                            source = "admin_graphql"
                    finally:
                        await admin.close()
                except Exception as e:
                    _log.error("Admin GraphQL catalog fetch failed: %s", e)

        # Build the full context payload
        return {
            "merchant_id": merchant_id,
            "catalog": catalog_payload,
            "policies": policy_payload,
            "fetched_at": datetime.now(UTC).isoformat(),
            "source": source,
        }

    def start_refresh_timer(self, merchant_id: str, interval_seconds: int = 900) -> None:
        """Start a background task that refreshes context periodically."""
        if self._task is not None and not self._task.done():
            self._task.cancel()

        async def _loop() -> None:
            while True:
                try:
                    # Fetch live from Shopify every cycle — do not short-circuit on the cache.
                    payload = await self._fetch_live(merchant_id)
                    await ctx_cache.persist_to_db(merchant_id, payload, "STOREFRONT_MCP")
                    ctx_cache.set_cached(merchant_id, payload, "STOREFRONT_MCP")
                except Exception as e:
                    _log.error("Context refresh failed: %s", e)
                await asyncio.sleep(interval_seconds)

        self._task = asyncio.create_task(_loop())

    def stop_refresh_timer(self) -> None:
        """Stop the background refresh task."""
        if self._task is not None:
            self._task.cancel()
            self._task = None


# Module-level singleton.
_store_context_builder = StoreContextBuilder()


def get_store_context() -> StoreContextBuilder:
    return _store_context_builder
