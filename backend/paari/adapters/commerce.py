"""Commerce adapter protocol and factory.

The CommerceAdapter Protocol defines the interface that all upstream store
adapters must implement. The tool registry calls executors through this
interface, so swapping between stub and live requires no changes to the
gateway, runtime loop, or LLM context.
"""

from __future__ import annotations

from typing import Protocol, runtime_checkable


@runtime_checkable
class CommerceAdapter(Protocol):
    """Protocol that all commerce adapters must satisfy."""

    async def search_products(self, query: str, limit: int) -> dict:
        """Search the merchant's product catalog."""
        ...

    async def get_product(self, sku: str) -> dict:
        """Look up a single product by SKU."""
        ...

    async def get_inventory(self, sku: str) -> dict:
        """Get current inventory for a product SKU."""
        ...

    async def get_price(self, sku: str, quantity: int) -> dict:
        """Get the current price for a product SKU."""
        ...

    async def get_shipping_policy(self) -> dict:
        """Get the merchant's shipping policy."""
        ...

    async def get_return_policy(self) -> dict:
        """Get the merchant's return policy."""
        ...

    async def request_quote(
        self, sku: str, quantity: int, discount_pct: int, currency: str
    ) -> dict:
        """Request a price quote for a product."""
        ...

    async def request_payment(self, amount_paise: int, currency: str) -> dict:
        """Request payment for an authorized quote."""
        ...

    async def confirm_order(self, transaction_id: str, quote_id: str) -> dict:
        """Confirm a Shopify order after payment is verified."""
        ...

    async def get_order_status(self, transaction_id: str) -> dict:
        """Get the status of a transaction's order."""
        ...

    def source_label(self) -> str:
        """Return the adapter source label ('fixture' or 'shopify_live')."""
        ...


def get_commerce_adapter() -> CommerceAdapter:
    """Return the appropriate CommerceAdapter based on PAARI_SHOPIFY_MODE."""
    from paari.config import settings

    if settings.shopify_mode == "live":
        from paari.adapters.shopify_live import ShopifyLiveAdapter

        return ShopifyLiveAdapter()
    else:
        from paari.adapters.shopify_stub import ShopifyStubAdapter

        return ShopifyStubAdapter()
