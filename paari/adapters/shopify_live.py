"""Shopify adapter (live).

Implements the CommerceAdapter protocol against a real Shopify store.
Uses Admin GraphQL for inventory/price/order operations and Storefront MCP
for catalog/policy queries. All methods are async and handle retries.
"""

from __future__ import annotations

import logging
from datetime import UTC, datetime
from typing import Any

from paari.adapters.exceptions import AdapterError, AuthError

_log = logging.getLogger("paari.adapters.shopify_live")


class ShopifyLiveAdapter:
    """Live adapter that calls real Shopify Admin + Storefront MCP."""

    def __init__(self) -> None:
        self._admin_client: Any = None
        self._storefront_client: Any = None
        self._sku_index: dict[str, dict[str, Any]] = {}

    def source_label(self) -> str:
        return "shopify_live"

    def _get_admin_client(self) -> Any:
        if self._admin_client is None:
            from paari.shopify_admin.client import ShopifyAdminClient

            self._admin_client = ShopifyAdminClient()
        return self._admin_client

    def _get_storefront_client(self) -> Any:
        if self._storefront_client is None:
            from paari.shopify_storefront.client import ShopifyStorefrontClient

            self._storefront_client = ShopifyStorefrontClient()
        return self._storefront_client

    def _now(self) -> str:
        return datetime.now(UTC).isoformat()

    def _result(self, payload: dict[str, Any]) -> dict[str, Any]:
        return {"source": "shopify_live", "fetched_at": self._now(), **payload}

    def _variant_id_to_inventory_item_id(self, variant_gid: str) -> str:
        """Derive an inventory item GID from a variant GID.

        Shopify GID format:
          Variant:      gid://shopify/ProductVariant/{numeric_id}
          InventoryItem: gid://shopify/InventoryItem/{numeric_id}
        The numeric ID is the same.
        """
        parts = variant_gid.split("/")
        if len(parts) >= 2:
            return f"gid://shopify/InventoryItem/{parts[-1]}"
        return variant_gid  # fallback: return as-is

    async def _load_sku_index(self) -> dict[str, dict[str, Any]]:
        """Load SKU index from store_context cache/DB."""
        if self._sku_index:
            return self._sku_index
        from paari.store_context import cache as ctx_cache

        cached = ctx_cache.get_cached("MER-001")
        if cached:
            payload = cached["payload"]
            self._sku_index = payload.get("catalog", {}).get("sku_index", {})
            return self._sku_index

        # Try DB fallback
        try:
            import json
            from sqlalchemy import text
            from paari.db.engine import get_session_maker

            maker = get_session_maker()
            async with maker() as session:
                row = (
                    await session.execute(
                        text("SELECT payload_json FROM store_contexts WHERE merchant_id = :mid"),
                        {"mid": "MER-001"},
                    )
                ).first()
                if row:
                    data = json.loads(row.payload_json)
                    self._sku_index = data.get("catalog", {}).get("sku_index", {})
                    return self._sku_index
        except Exception:
            pass
        return {}

    async def search_products(self, query: str, limit: int = 5) -> dict:
        """Search via Storefront MCP, fallback to Admin GraphQL."""
        # Try Storefront MCP first
        client = self._get_storefront_client()
        try:
            results = await client.search_catalog(query, limit)
            if results:
                return self._result({"products": results})
        except AdapterError:
            _log.warning("Storefront MCP search failed, trying Admin GraphQL")

        # Fallback: Admin GraphQL search
        admin = self._get_admin_client()
        try:
            from paari.shopify_admin.queries import SEARCH_PRODUCTS

            data = await admin.execute(SEARCH_PRODUCTS, {"query": query, "first": limit})
            edges = data.get("products", {}).get("edges", [])
            products = []
            for edge in edges:
                node = edge.get("node", {})
                variants = []
                for ve in node.get("variants", {}).get("edges", []):
                    vn = ve.get("node", {})
                    variants.append({
                        "variant_id": vn.get("id", ""),
                        "sku": vn.get("sku", ""),
                        "price_paise": int(float(vn.get("price", "0")) * 100),
                        "available": (vn.get("inventoryQuantity", 0) or 0) > 0,
                    })
                primary = variants[0] if variants else {}
                products.append({
                    "sku": primary.get("sku", ""),
                    "product_id": node.get("id", ""),
                    "title": node.get("title", ""),
                    "description": node.get("description", ""),
                    "product_type": node.get("productType", ""),
                    "tags": node.get("tags", []),
                    "price_paise": primary.get("price_paise", 0),
                    "currency": "INR",
                    "variants": variants,
                })
            return self._result({"products": products})
        except Exception as e:
            _log.warning("Admin GraphQL search also failed: %s", e)
            return self._result({"products": []})

    async def get_product(self, sku: str) -> dict:
        """Get product details via Storefront MCP."""
        client = self._get_storefront_client()
        try:
            product = await client.get_product(sku)
            if product is None:
                return self._result({"error": "product_not_found", "sku": sku})
            return self._result({"product": product})
        except AdapterError:
            return self._result({"error": "product_not_found", "sku": sku})

    async def get_inventory(self, sku: str) -> dict:
        """Get live inventory via Admin GraphQL.

        Uses the SKU index's variant_id to look up inventory. If the variant
        isn't indexed, falls back to a live Admin GraphQL search by SKU.
        """
        admin = self._get_admin_client()
        index = await self._load_sku_index()
        entry = index.get(sku)
        variant_id = entry.get("variant_id") if entry else None

        # Live fallback: find the product by SKU and pick the first variant
        if variant_id is None:
            try:
                from paari.shopify_admin.queries import SEARCH_PRODUCTS

                data = await admin.execute(SEARCH_PRODUCTS, {"query": f"sku:{sku}", "first": 1})
                edges = data.get("products", {}).get("edges", [])
                if edges:
                    variants = edges[0]["node"].get("variants", {}).get("edges", [])
                    if variants:
                        variant_id = variants[0]["node"].get("id", "")
            except Exception:
                pass

        if variant_id is None:
            return self._result({"error": "sku_not_found", "sku": sku})

        try:
            # Get inventory_item_id from the variant, then query inventory levels
            inv_item_id = self._variant_id_to_inventory_item_id(variant_id)
            available = await admin.get_inventory_quantity(inv_item_id)
            return self._result({"sku": sku, "available": available, "variant_id": variant_id})
        except AdapterError:
            return self._result({"error": "inventory_query_failed", "sku": sku})

    async def get_price(self, sku: str, quantity: int = 1) -> dict:
        """Get live price via Admin GraphQL.

        Tries the SKU index first. Falls back to a live Admin GraphQL
        variant-by-SKU query so that get_price works even when the store
        context cache hasn't been populated yet.
        """
        admin = self._get_admin_client()
        index = await self._load_sku_index()
        entry = index.get(sku)
        if entry is not None:
            variant_id = entry.get("variant_id", "")
            if variant_id:
                try:
                    price = await admin.get_variant_price(variant_id)
                    return self._result(
                        {
                            "sku": sku,
                            "unit_price_paise": price,
                            "total_paise": price * quantity,
                            "currency": "INR",
                        }
                    )
                except AdapterError:
                    pass

        # Live fallback: search for the product by SKU via Admin GraphQL
        # and pick the first variant to get the price.
        try:
            from paari.shopify_admin.queries import SEARCH_PRODUCTS

            data = await admin.execute(SEARCH_PRODUCTS, {"query": f"sku:{sku}", "first": 1})
            edges = data.get("products", {}).get("edges", [])
            if edges:
                variants = edges[0]["node"].get("variants", {}).get("edges", [])
                if variants:
                    node = variants[0]["node"]
                    price_paise = int(float(node.get("price", "0")) * 100)
                    return self._result(
                        {
                            "sku": sku,
                            "unit_price_paise": price_paise,
                            "total_paise": price_paise * quantity,
                            "currency": "INR",
                            "variant_id": node.get("id", ""),
                        }
                    )
        except Exception:
            pass

        return self._result({"error": "price_query_failed", "sku": sku})

    async def get_shipping_policy(self) -> dict:
        """Get shipping policy via Storefront MCP."""
        client = self._get_storefront_client()
        try:
            policies = await client.search_policies("shipping")
            return self._result(
                {
                    "policy": policies.get("shipping", "Standard shipping within India."),
                    "international_available": False,
                }
            )
        except AdapterError:
            return self._result(
                {"policy": "Standard shipping within India.", "international_available": False}
            )

    async def get_return_policy(self) -> dict:
        """Get return policy via Storefront MCP."""
        client = self._get_storefront_client()
        try:
            policies = await client.search_policies("return")
            return self._result(
                {"policy": policies.get("return", "30-day returns on unworn items.")}
            )
        except AdapterError:
            return self._result({"policy": "30-day returns on unworn items."})

    async def request_quote(
        self, sku: str, quantity: int, discount_pct: int, currency: str = "INR"
    ) -> dict:
        """Compute a quote (local computation from catalog data)."""
        price_result = await self.get_price(sku, quantity)
        if "error" in price_result:
            return price_result
        unit = price_result["unit_price_paise"]
        gross = unit * quantity
        discount_amount = gross * discount_pct // 100
        total = gross - discount_amount
        inventory_result = await self.get_inventory(sku)
        available_qty = inventory_result.get("available", 0)
        return self._result(
            {
                "sku": sku,
                "quantity": quantity,
                "unit_price_paise": unit,
                "discount_pct": discount_pct,
                "gross_paise": gross,
                "discount_paise": discount_amount,
                "total_paise": total,
                "currency": currency,
                "available": available_qty >= quantity,
            }
        )

    async def request_payment(self, amount_paise: int, currency: str = "INR") -> dict:
        """Request payment. Returns PENDING state."""
        import uuid

        payment_id = str(uuid.uuid4())
        return self._result(
            {
                "payment_id": payment_id,
                "state": "PENDING",
                "gateway_ref": f"SHOPIFY-{payment_id[:8]}",
                "amount_paise": amount_paise,
                "currency": currency,
            }
        )

    async def confirm_order(self, transaction_id: str, quote_id: str) -> dict:
        """Create and complete a draft order via Admin GraphQL.

        Builds line items from the SKU index using the transaction's quote data.
        """
        admin = self._get_admin_client()
        try:
            # Load transaction to get quote details
            from sqlalchemy import text
            from paari.db.engine import get_session_maker

            line_items = []
            maker = get_session_maker()
            async with maker() as session:
                # Get the quote for this transaction
                quote_row = (
                    await session.execute(
                        text(
                            "SELECT id, amount_paise, product_sku, quantity FROM quotes "
                            "WHERE transaction_id = :tid AND state = 'ACCEPTED' LIMIT 1"
                        ),
                        {"tid": transaction_id},
                    )
                ).first()

                if quote_row:
                    # Load SKU index to map SKU -> variant_id
                    index = await self._load_sku_index()
                    # Get the transaction to find SKU context
                    tx_row = (
                        await session.execute(
                            text("SELECT amount_paise, currency FROM transactions WHERE id = :id"),
                            {"id": transaction_id},
                        )
                    ).first()

            # Build line items: prefer the quoted SKU so the Shopify order
            # matches the agreed item (blueprint Step 12). Fall back to the
            # whole SKU index only when the quote carries no product reference
            # (legacy rows / scripts that insert bare quotes).
            sku_index = await self._load_sku_index()
            if quote_row and quote_row.product_sku and sku_index:
                entry = sku_index.get(quote_row.product_sku)
                if entry and entry.get("variant_id"):
                    line_items.append(
                        {
                            "variantId": entry["variant_id"],
                            "quantity": int(quote_row.quantity or 1),
                        }
                    )
            if not line_items and sku_index:
                for sku, entry in sku_index.items():
                    variant_id = entry.get("variant_id", "")
                    if variant_id:
                        line_items.append({"variantId": variant_id, "quantity": 1})

            if not line_items:
                _log.warning("No line items built for order %s — using empty draft", transaction_id)

            # Preferred flow: draft order → complete (matches the blueprint).
            # Falls back to direct orderCreate when the token lacks the
            # write_draft_orders scope (draftOrderCreate → ACCESS_DENIED).
            try:
                draft_order_id = await admin.create_draft_order(
                    line_items=line_items,
                    note=f"paari_transaction:{transaction_id}",
                    tags=["paari-agent-order"],
                )
                order_id = await admin.complete_draft_order(draft_order_id)
                return self._result(
                    {"order_id": order_id, "state": "confirmed", "draft_order_id": draft_order_id, "line_items_count": len(line_items)}
                )
            except AdapterError as exc:
                if "ACCESS_DENIED" in str(exc) and "draft_order" in str(exc).lower():
                    _log.warning(
                        "write_draft_orders scope unavailable (%s) — falling back to orderCreate",
                        exc,
                    )
                    order_id = await admin.create_order(
                        line_items=line_items,
                        note=f"paari_transaction:{transaction_id}",
                        tags=["paari-agent-order"],
                    )
                    return self._result(
                        {"order_id": order_id, "state": "confirmed", "line_items_count": len(line_items)}
                    )
                raise
        except AdapterError as e:
            return self._result({"error": "order_creation_failed", "details": str(e)})

    async def get_order_status(self, transaction_id: str) -> dict:
        """Get order status from Shopify Admin."""
        from sqlalchemy import text

        from paari.db.engine import get_session_maker

        maker = get_session_maker()
        async with maker() as session:
            row = (
                await session.execute(
                    text("SELECT state FROM transactions WHERE id = :id"),
                    {"id": transaction_id},
                )
            ).first()
            if row is None:
                return self._result({"error": "transaction_not_found"})
            return self._result({"transaction_id": transaction_id, "state": row.state})
