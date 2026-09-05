"""Shopify Admin GraphQL client.

Async httpx-based client with:
- Bearer token auth from SHOPIFY_ADMIN_ACCESS_TOKEN
- 429 rate-limit backoff (exponential, ×3)
- 5xx retry (×2)
- Request timeout (10s)
- Correlation ID header for tracing
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from typing import Any

import httpx

from paari.adapters.exceptions import AdapterError, AuthError, RateLimited

_log = logging.getLogger("paari.shopify_admin.client")


class ShopifyAdminClient:
    """Async Shopify Admin GraphQL client with retry."""

    def __init__(self) -> None:
        from paari.config import settings

        self._domain = settings.shopify_domain
        self._api_version = settings.shopify_api_version
        self._token = settings.shopify_admin_access_token
        self._base_url = f"https://{self._domain}/admin/api/{self._api_version}/graphql.json"
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        try:
            if self._client is not None and not self._client.is_closed:
                return self._client
        except Exception:
            pass
        self._client = httpx.AsyncClient(
            base_url=self._base_url,
            headers={
                "Content-Type": "application/json",
                "X-Shopify-Access-Token": self._token,
            },
            timeout=httpx.Timeout(15.0),
        )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    async def execute(
        self, query: str, variables: dict[str, Any] | None = None, max_retries: int = 3
    ) -> dict[str, Any]:
        """Execute a GraphQL query with retry logic."""
        client = await self._get_client()
        correlation_id = str(uuid.uuid4())
        payload: dict[str, Any] = {"query": query}
        if variables:
            payload["variables"] = variables

        last_error: Exception | None = None
        for attempt in range(max_retries):
            try:
                response = await client.post(
                    "",
                    json=payload,
                    headers={"X-Correlation-ID": correlation_id},
                )

                if response.status_code == 401:
                    raise AuthError("Shopify Admin authentication failed")

                if response.status_code == 429:
                    retry_after = int(response.headers.get("Retry-After", 2))
                    wait = retry_after * (2 ** attempt)
                    _log.warning("Rate limited, waiting %ds (attempt %d)", wait, attempt + 1)
                    await asyncio.sleep(wait)
                    last_error = RateLimited("Rate limited by Shopify")
                    continue

                if response.status_code >= 500:
                    wait = 2 ** (attempt + 1)
                    _log.warning("Server error %d, retrying in %ds", response.status_code, wait)
                    await asyncio.sleep(wait)
                    last_error = AdapterError(f"Shopify returned {response.status_code}")
                    continue

                response.raise_for_status()
                data = response.json()

                if "errors" in data:
                    raise AdapterError(f"GraphQL errors: {data['errors']}")

                return data.get("data", {})

            except httpx.TimeoutException:
                wait = 2 ** (attempt + 1)
                _log.warning("Request timeout, retrying in %ds", wait)
                await asyncio.sleep(wait)
                last_error = AdapterError("Request timed out")
                continue

        raise last_error or AdapterError("Max retries exceeded")

    # ── High-level helpers ──────────────────────────────────────────

    async def get_inventory_quantity(self, inventory_item_id: str) -> int:
        """Get available quantity for an inventory item.

        Accepts either a variant GID or an inventory item GID; resolves via the
        variant (API 2025-01 removed ``inventoryItems(ids:)`` and ``available``).
        """
        from paari.shopify_admin.queries import GET_INVENTORY_LEVELS

        variant_id = inventory_item_id
        if "InventoryItem" in inventory_item_id:
            numeric = inventory_item_id.rstrip("/").split("/")[-1]
            found = await self._find_variant_by_inventory_item(numeric)
            if found is None:
                return 0
            variant_id = found

        data = await self.execute(GET_INVENTORY_LEVELS, {"variantId": variant_id})
        item = data.get("productVariant", {}).get("inventoryItem", {})
        levels = item.get("inventoryLevels", {}).get("edges", [])
        for level in levels:
            for qty in level.get("node", {}).get("quantities", []):
                if qty.get("name") == "available":
                    return int(qty.get("quantity") or 0)
        return 0

    async def _find_variant_by_inventory_item(self, numeric_id: str) -> str | None:
        """Resolve a variant GID from an inventory item numeric id."""
        query = """
        query FindVariant($query: String!) {
          productVariants(first: 1, query: $query) {
            edges { node { id } }
          }
        }
        """
        data = await self.execute(query, {"query": f"inventory_item_id:{numeric_id}"})
        edges = data.get("productVariants", {}).get("edges", [])
        if edges:
            return edges[0].get("node", {}).get("id")
        return None

    async def get_variant_price(self, variant_id: str) -> int:
        """Get price for a variant (in shopify currency units → convert to paise)."""
        from paari.shopify_admin.queries import GET_VARIANT_PRICE

        data = await self.execute(GET_VARIANT_PRICE, {"variantId": variant_id})
        price_str = (
            data.get("productVariant", {}).get("price", "0.00")
        )
        # Shopify stores price as string like "1200.00" → convert to paise
        return int(float(price_str) * 100)

    async def create_draft_order(
        self,
        line_items: list[dict[str, Any]],
        note: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """Create a draft order. Returns draft_order_id (GID)."""
        from paari.shopify_admin.queries import CREATE_DRAFT_ORDER

        input_vars: dict[str, Any] = {
            "lineItems": line_items,
        }
        if note:
            input_vars["note"] = note
        if tags:
            input_vars["tags"] = ",".join(tags)

        data = await self.execute(CREATE_DRAFT_ORDER, {"input": input_vars})
        draft_order = data.get("draftOrderCreate", {}).get("draftOrder", {})
        draft_id = draft_order.get("id", "")
        if not draft_id:
            raise AdapterError("draftOrderCreate returned no ID")
        return draft_id

    async def complete_draft_order(self, draft_order_id: str) -> str:
        """Complete a draft order. Returns order_id (GID)."""
        from paari.shopify_admin.queries import COMPLETE_DRAFT_ORDER

        data = await self.execute(COMPLETE_DRAFT_ORDER, {"draftOrderId": draft_order_id})
        order = data.get("draftOrderComplete", {}).get("draftOrder", {}).get("order", {})
        order_id = order.get("id", "")
        if not order_id:
            raise AdapterError("draftOrderComplete returned no order ID")
        return order_id

    async def create_order(
        self,
        line_items: list[dict[str, Any]],
        note: str = "",
        tags: list[str] | None = None,
    ) -> str:
        """Create a paid order directly via orderCreate (requires write_orders).

        Used as a fallback when the access token lacks write_draft_orders
        scope (draftOrderCreate is ACCESS_DENIED). Returns order_id (GID).
        """
        from paari.shopify_admin.queries import CREATE_ORDER

        order_vars: dict[str, Any] = {
            "lineItems": line_items,
            "financialStatus": "PAID",
        }
        if note:
            order_vars["note"] = note
        if tags:
            order_vars["tags"] = ",".join(tags)

        data = await self.execute(CREATE_ORDER, {"order": order_vars})
        order = data.get("orderCreate", {}).get("order", {})
        order_id = order.get("id", "")
        if not order_id:
            raise AdapterError("orderCreate returned no order ID")
        return order_id

    async def create_webhook_subscription(self, topic: str, callback_url: str) -> str:
        """Register a webhook subscription. Returns webhook_id.

        Idempotent: Shopify rejects a duplicate topic+URL with a userError
        ("Address for this topic has already been taken") and a null
        webhookSubscription. That is treated as success so a server restart
        re-registering the same subscriptions is a no-op, not an error.
        """
        from paari.shopify_admin.queries import CREATE_WEBHOOK_SUBSCRIPTION

        data = await self.execute(
            CREATE_WEBHOOK_SUBSCRIPTION,
            {"topic": topic.upper().replace("/", "_"), "callbackUrl": callback_url},
        )
        created = data.get("webhookSubscriptionCreate", {}) or {}
        webhook = created.get("webhookSubscription") or {}
        webhook_id = webhook.get("id", "")
        if not webhook_id:
            user_errors = created.get("userErrors") or []
            for err in user_errors:
                if "already been taken" in (err.get("message") or ""):
                    _log.info("Webhook %s already registered, skipping", topic)
                    return webhook_id
            raise AdapterError(f"Webhook registration failed: {user_errors}")
        return webhook_id

    async def delete_webhook_subscription(self, webhook_id: str) -> bool:
        """Delete a webhook subscription. Returns True on success."""
        from paari.shopify_admin.queries import DELETE_WEBHOOK_SUBSCRIPTION

        data = await self.execute(DELETE_WEBHOOK_SUBSCRIPTION, {"id": webhook_id})
        deleted = data.get("webhookSubscriptionDelete", {}).get("deletedWebhookSubscriptionId")
        return deleted is not None
